"""The chunked cursor, the lease, and stalled-job resume."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import chunked
import store
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
    ) -> dict[str, object] | None:
        del expression, condition, names
        current = self.items.get((pk, sk), {})
        lease = str(current.get("leaseUntil") or "")
        if lease and lease >= values[":now"]:
            raise store.ConditionNotMet(pk)
        previous = dict(current) if current else None
        row = dict(current)
        row.update(
            {
                "pk": pk,
                "sk": sk,
                "status": values[":running"],
                "leaseUntil": values[":lease"],
                "updatedAt": values[":now"],
                "gsi1pk": values[":gsi1pk"],
                "gsi1sk": values[":gsi1sk"],
            }
        )
        self.items[(pk, sk)] = row
        return previous

    def query_gsi1(self, gsi1pk: str, prefix: str = "") -> list[dict[str, object]]:
        rows = [
            dict(item)
            for item in self.items.values()
            if item.get("gsi1pk") == gsi1pk and str(item.get("gsi1sk") or "").startswith(prefix)
        ]
        return sorted(rows, key=lambda item: str(item.get("gsi1sk")))


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
        patch("store.query_gsi1", memory.query_gsi1),
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
        self.assertEqual(saved["gsi1pk"], "JOBSTATE")
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

    def test_the_cursor_is_the_one_present_when_the_lease_is_taken(self) -> None:
        memory = _Memory()
        memory.put({"pk": "JOB#prices", "sk": "STATE", "status": "running", "cursor": 1, "total": 5})
        real = memory.update_conditional

        def raced(
            pk: str,
            sk: str,
            expression: str,
            values: dict[str, str],
            condition: str,
            names: dict[str, str] | None = None,
        ) -> dict[str, object] | None:
            memory.items[(pk, sk)]["cursor"] = 4
            return real(pk, sk, expression, values, condition, names)

        memory.update_conditional = raced  # type: ignore[method-assign]
        seen: list[str] = []
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            chunked.run("prices", ["a", "b", "c", "d", "e"], seen.append, _Context(200_000), now=lambda: NOW)
        self.assertEqual(seen, ["e"])

    def test_resume_starts_only_an_expired_running_job(self) -> None:
        memory = _Memory()
        memory.put(
            {
                "pk": "JOB#prices",
                "sk": "STATE",
                "status": "running",
                "cursor": 1,
                "gsi1pk": "JOBSTATE",
                "gsi1sk": "prices",
            }
        )
        memory.put(
            {
                "pk": "JOB#news",
                "sk": "STATE",
                "status": "running",
                "leaseUntil": timeutil.format_iso_millis(NOW + timedelta(minutes=5)),
                "gsi1pk": "JOBSTATE",
                "gsi1sk": "news",
            }
        )
        memory.put(
            {
                "pk": "JOB#fundamentals",
                "sk": "STATE",
                "status": "done",
                "gsi1pk": "JOBSTATE",
                "gsi1sk": "fundamentals",
            }
        )
        memory.put({"pk": "JOB#orphan", "sk": "STATE", "status": "running"})
        started: list[str] = []
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            chunked.resume_stalled(now=lambda: NOW, invoke=started.append)
        self.assertEqual(started, ["prices"])

    def test_one_failed_start_does_not_drop_the_next_job(self) -> None:
        memory = _Memory()
        for job in ("alpha", "beta"):
            memory.put(
                {
                    "pk": f"JOB#{job}",
                    "sk": "STATE",
                    "status": "running",
                    "gsi1pk": "JOBSTATE",
                    "gsi1sk": job,
                }
            )

        def invoke(job: str) -> None:
            if job == "alpha":
                raise RuntimeError("down")
            started.append(job)

        started: list[str] = []
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            result = chunked.resume_stalled(now=lambda: NOW, invoke=invoke)
        self.assertEqual(result, ["beta"])
        self.assertEqual(started, ["beta"])

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
