"""The chunked cursor, the lease, and stalled-job resume."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
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
        self.assertEqual(saved["failures"], 1)
        self.assertEqual(saved["failedCursor"], 1)
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

    def test_a_paused_job_waits_until_the_switch_is_on(self) -> None:
        memory = _Memory()
        memory.put(
            {
                "pk": "JOB#prices",
                "sk": "STATE",
                "status": "paused",
                "gsi1pk": "JOBSTATE",
                "gsi1sk": "prices",
                "cursor": 1,
            }
        )
        started: list[str] = []
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            held = chunked.resume_stalled(now=lambda: NOW, invoke=started.append, enabled=lambda _job: False)
            released = chunked.resume_stalled(now=lambda: NOW, invoke=started.append, enabled=lambda _job: True)
        self.assertEqual(held, [])
        self.assertEqual(released, ["prices"])
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
            patch("store.get", return_value={}),
        ):
            chunked._invoke_self("prices")
        self.assertEqual(calls[0]["FunctionName"], "engine")
        self.assertEqual(calls[0]["InvocationType"], "Event")
        self.assertEqual(calls[0]["Payload"], b'{"job": "prices"}')

    def test_a_changed_list_starts_again_and_the_same_list_resumes(self) -> None:
        memory = _Memory()

        def fail(item: str) -> None:
            if item == "b":
                raise RuntimeError("bad row")

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            with self.assertRaises(RuntimeError):
                chunked.run("prices", ["a", "b"], fail, _Context(200_000), now=lambda: NOW)
            resumed: list[str] = []
            chunked.run("prices", ["a", "b"], resumed.append, _Context(200_000), now=lambda: NOW)
            self.assertEqual(resumed, ["b"])
            memory.items.pop(("JOB#prices", "STATE"))
            with self.assertRaises(RuntimeError):
                chunked.run("prices", ["a", "b"], fail, _Context(200_000), now=lambda: NOW)
            restarted: list[str] = []
            chunked.run("prices", ["x", "y"], restarted.append, _Context(200_000), now=lambda: NOW)
        self.assertEqual(restarted, ["x", "y"])

    def test_the_switch_is_read_before_the_next_item(self) -> None:
        memory = _Memory()
        seen: list[str] = []
        checks = {"n": 0}

        def enabled() -> bool:
            checks["n"] += 1
            return checks["n"] == 1

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            result = chunked.run(
                "prices",
                ["a", "b"],
                seen.append,
                _Context(200_000),
                now=lambda: NOW,
                enabled=enabled,
            )
        self.assertEqual(seen, ["a"])
        self.assertEqual(result["status"], "paused")
        self.assertEqual(result["cursor"], 1)
        saved = memory.items[("JOB#prices", "STATE")]
        self.assertEqual(saved["status"], "paused")
        self.assertNotIn("leaseUntil", saved)

    def test_a_failed_job_is_resumed_until_three_failures(self) -> None:
        memory = _Memory()
        for job, failures in (("decimal", Decimal("2")), ("once", 1), ("spent", 3), ("universe_build", None)):
            item: dict[str, object] = {
                "pk": f"JOB#{job}",
                "sk": "STATE",
                "status": "failed",
                "gsi1pk": "JOBSTATE",
                "gsi1sk": job,
                "cursor": 1,
            }
            if failures is not None:
                item["failures"] = failures
            memory.put(item)
        started: list[str] = []
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            chunked.resume_stalled(now=lambda: NOW, invoke=started.append)
        self.assertEqual(started, ["decimal", "once"])

    def test_the_same_cursor_counts_failures_and_a_later_one_resets(self) -> None:
        memory = _Memory()
        items = ["a", "b", "c"]

        def fail_at(stop: str):
            def process(item: str) -> None:
                if item == stop:
                    raise RuntimeError("bad row")

            return process

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2], _bind(memory)[3]:
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    chunked.run("prices", items, fail_at("b"), _Context(200_000), now=lambda: NOW)
            saved = memory.items[("JOB#prices", "STATE")]
            self.assertEqual(saved["failures"], 2)
            self.assertEqual(saved["cursor"], 1)
            with self.assertRaises(RuntimeError):
                chunked.run("prices", items, fail_at("c"), _Context(200_000), now=lambda: NOW)
            saved = memory.items[("JOB#prices", "STATE")]
        self.assertEqual(saved["cursor"], 2)
        self.assertEqual(saved["failures"], 1)
        self.assertEqual(saved["failedCursor"], 2)

    def test_a_large_parameter_block_stays_in_the_state_row(self) -> None:
        calls: list[dict[str, object]] = []

        class _Lambda:
            def invoke(self, **kwargs: object) -> dict[str, str]:
                calls.append(kwargs)
                return {"StatusCode": "202"}

        symbols = [f"{index:08d}" for index in range(30_000)]
        with (
            patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "engine"}),
            patch("boto3.client", return_value=_Lambda()),
            patch("store.get", return_value={"params": {"symbols": symbols}}),
        ):
            chunked._invoke_self("backfill_prices")
        payload = calls[0]["Payload"]
        self.assertIsInstance(payload, bytes)
        self.assertLess(len(payload), 1000)  # type: ignore[arg-type]
        self.assertEqual(payload, b'{"job": "backfill_prices", "paramsInState": true}')

    def test_invoke_sends_the_stored_params(self) -> None:
        calls: list[dict[str, object]] = []

        class _Lambda:
            def invoke(self, **kwargs: object) -> dict[str, str]:
                calls.append(kwargs)
                return {"StatusCode": "202"}

        with (
            patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "engine"}),
            patch("boto3.client", return_value=_Lambda()),
            patch("store.get", return_value={"params": {"start": "2016-01-01"}}),
        ):
            chunked._invoke_self("backfill_prices")
        self.assertIn(b'"start": "2016-01-01"', calls[0]["Payload"])


if __name__ == "__main__":
    unittest.main()
