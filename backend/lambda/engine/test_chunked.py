"""The chunked cursor, the lease, and stalled-job resume."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import chunked
import timeutil

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


class _Memory:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {}

    def get(self, pk: str, sk: str) -> dict[str, object] | None:
        item = self.items.get((pk, sk))
        return dict(item) if item else None

    def put(self, item: dict[str, object]) -> None:
        self.items[(str(item["pk"]), str(item["sk"]))] = dict(item)

    def update_conditional(
        self,
        pk: str,
        sk: str,
        expression: str,
        values: dict[str, str],
        condition: str,
        names: dict[str, str] | None = None,
    ) -> bool:
        del expression, condition, names
        current = self.items.get((pk, sk), {})
        lease = str(current.get("leaseUntil") or "")
        if lease and lease >= values[":now"]:
            return False
        row = dict(current)
        row.update(
            {
                "pk": pk,
                "sk": sk,
                "status": values[":running"],
                "leaseUntil": values[":lease"],
                "updatedAt": values[":now"],
            }
        )
        self.items[(pk, sk)] = row
        return True

    def scan_pk_prefix(self, prefix: str) -> list[dict[str, object]]:
        return [dict(item) for (pk, _sk), item in self.items.items() if pk.startswith(prefix)]


class _Context:
    def __init__(self, remaining: int) -> None:
        self.remaining = remaining

    def get_remaining_time_in_millis(self) -> int:
        return self.remaining


def _bind(memory: _Memory):
    return (
        patch("store.get", memory.get),
        patch("store.put", memory.put),
        patch("store.update_conditional", memory.update_conditional),
        patch("store.scan_pk_prefix", memory.scan_pk_prefix),
    )


class ChunkedTest(unittest.TestCase):
    def test_a_finished_run_releases_the_lease(self) -> None:
        memory = _Memory()
        seen: list[str] = []
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            result = chunked.run("prices", ["a", "b"], seen.append, _Context(200_000), now=lambda: NOW)
        self.assertEqual(result["status"], "done")
        self.assertEqual(seen, ["a", "b"])
        saved = memory.items[("JOB#prices", "STATE")]
        self.assertEqual(saved["cursor"], 2)
        self.assertNotIn("leaseUntil", saved)

    def test_it_stops_with_two_minutes_left(self) -> None:
        memory = _Memory()
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            result = chunked.run("prices", ["a"], lambda _item: None, _Context(100_000), now=lambda: NOW)
        self.assertEqual(result, {"status": "running", "cursor": 0, "total": 1})
        saved = memory.items[("JOB#prices", "STATE")]
        self.assertNotIn("leaseUntil", saved)

    def test_a_failure_keeps_the_failed_index(self) -> None:
        memory = _Memory()

        def process(item: str) -> None:
            if item == "b":
                raise RuntimeError("bad row")

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            with self.assertRaises(RuntimeError):
                chunked.run("prices", ["a", "b"], process, _Context(200_000), now=lambda: NOW)
        saved = memory.items[("JOB#prices", "STATE")]
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["cursor"], 1)
        self.assertNotIn("leaseUntil", saved)

    def test_a_second_caller_does_not_get_the_lease(self) -> None:
        memory = _Memory()
        memory.put(
            {
                "pk": "JOB#prices",
                "sk": "STATE",
                "status": "running",
                "cursor": 1,
                "leaseUntil": timeutil.format_iso_millis(NOW + timedelta(minutes=5)),
            }
        )
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            with self.assertRaises(chunked.Busy):
                chunked.run("prices", ["a", "b"], lambda _item: None, _Context(200_000), now=lambda: NOW)
        self.assertEqual(memory.items[("JOB#prices", "STATE")]["cursor"], 1)

    def test_a_finished_job_starts_again_from_zero(self) -> None:
        memory = _Memory()
        memory.put({"pk": "JOB#prices", "sk": "STATE", "status": "done", "cursor": 2, "total": 2})
        seen: list[str] = []
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            chunked.run("prices", ["a"], seen.append, _Context(200_000), now=lambda: NOW)
        self.assertEqual(seen, ["a"])

    def test_resume_starts_only_an_expired_running_job(self) -> None:
        memory = _Memory()
        memory.put({"pk": "JOB#prices", "sk": "STATE", "status": "running", "cursor": 1})
        memory.put(
            {
                "pk": "JOB#news",
                "sk": "STATE",
                "status": "running",
                "leaseUntil": timeutil.format_iso_millis(NOW + timedelta(minutes=5)),
            }
        )
        memory.put({"pk": "JOB#fundamentals", "sk": "STATE", "status": "done"})
        started: list[str] = []
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            chunked.resume_stalled(now=lambda: NOW, invoke=started.append)
        self.assertEqual(started, ["prices"])

    def test_invoke_uses_the_function_name_and_does_nothing_without_it(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
            chunked._invoke_self("prices")
        calls: list[dict[str, object]] = []

        class _Lambda:
            def invoke(self, **kwargs: object) -> dict[str, str]:
                calls.append(kwargs)
                return {"StatusCode": "202"}

        with (
            patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "engine"}),
            patch("boto3.client", return_value=_Lambda()),
        ):
            chunked._invoke_self("prices")
        self.assertEqual(calls[0]["FunctionName"], "engine")
        self.assertEqual(calls[0]["InvocationType"], "Event")
        self.assertIn(b'"job": "prices"', calls[0]["Payload"])


if __name__ == "__main__":
    unittest.main()
