"""Trimmed facts, the daily index, and the coverage report."""

from __future__ import annotations

import unittest
from datetime import date

import http_client
import ingest_fundamentals
import s3io
from test_ingest_prices import _bind, _Bucket, _Context, _Memory

DAY = date(2024, 6, 3)
CIK = "0000000001"


def _facts() -> dict[str, object]:
    return {
        "cik": 1,
        "entityName": "Example Co",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 100,
                                "filed": "2024-02-01",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                            }
                        ]
                    }
                },
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "end": "2023-12-31",
                                "val": 50,
                                "filed": "2024-02-01",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                            }
                        ]
                    }
                },
                "UnusedTag": {
                    "units": {"USD": [{"end": "2023-12-31", "val": 9, "filed": "2024-02-01", "form": "10-K"}]}
                },
            }
        },
    }


class FundamentalsIngestTest(unittest.TestCase):
    def test_refresh_trims_the_payload_and_writes_pit_rows(self) -> None:
        bucket = _Bucket()
        memory = _Memory()
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            result = ingest_fundamentals.refresh(
                ["1"],
                _Context(),
                fetch_facts=lambda _cik: _facts(),
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(result["status"], "done")
        stored = s3io.get_gzip_json("data", f"fundamentals/raw/cik={CIK}/companyfacts.json.gz", client=bucket)
        self.assertNotIn("entityName", stored)
        self.assertNotIn("UnusedTag", stored["facts"]["us-gaap"])
        self.assertIn("Revenues", stored["facts"]["us-gaap"])
        rows = list(s3io.get_jsonl_gz("data", f"fundamentals/pit/cik={CIK}/facts.jsonl.gz", client=bucket))
        self.assertIn("revenue", {row["field"] for row in rows})

    def test_daily_refreshes_a_10k_and_leaves_an_empty_index_alone(self) -> None:
        bucket = _Bucket()
        memory = _Memory()
        fetched: list[str] = []

        def index(day: date) -> list[dict[str, str]]:
            self.assertEqual(day, DAY)
            return [
                {"cik": CIK, "company": "Example", "form": "10-K", "filed": "2024-06-03", "path": "a"},
                {"cik": CIK, "company": "Example", "form": "8-K", "filed": "2024-06-03", "path": "b"},
                {"cik": CIK, "company": "Example", "form": "4", "filed": "2024-06-03", "path": "c"},
                {"cik": "0000000009", "company": "Other", "form": "10-Q", "filed": "2024-06-03", "path": "d"},
                {"cik": "nope", "company": "Bad", "form": "10-K", "filed": "2024-06-03", "path": "e"},
            ]

        def facts(cik: str) -> dict[str, object]:
            fetched.append(cik)
            return _facts()

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            waiting = ingest_fundamentals.daily(
                [CIK],
                DAY,
                _Context(),
                fetch_index=lambda _day: [],
                fetch_facts=facts,
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
            self.assertEqual(waiting["status"], "not_ready")
            self.assertEqual(bucket.objects, {})
            result = ingest_fundamentals.daily(
                [CIK],
                DAY,
                _Context(),
                fetch_index=index,
                fetch_facts=facts,
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["filings"], 2)
        self.assertEqual(fetched, [CIK])
        filings = list(s3io.get_jsonl_gz("data", "filings/date=2024-06-03/index.jsonl.gz", client=bucket))
        self.assertEqual(sorted(row["form"] for row in filings), ["10-K", "8-K"])
        self.assertEqual(memory.items[("JOB#ingest_filings", "CURSOR")]["lastDate"], "2024-06-03")

    def test_coverage_counts_only_companies_with_a_value(self) -> None:
        bucket = _Bucket()
        memory = _Memory()
        memory.put({"pk": "UNIVERSE#2024-06-03", "sk": "META", "members": 2, "gsi1pk": "UNIVERSE"})
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            ingest_fundamentals.refresh(
                [CIK],
                _Context(),
                fetch_facts=lambda _cik: _facts(),
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
            report = ingest_fundamentals.coverage_report([CIK, "2"], DAY, bucket="data", client=bucket)
        self.assertEqual(report["companies"], 2)
        self.assertEqual(report["flows"]["revenue"], 0.5)
        self.assertEqual(report["flows"]["netIncome"], 0.0)
        self.assertEqual(report["stocks"]["totalAssets"], 0.5)
        saved = memory.items[("UNIVERSE#2024-06-03", "META")]
        self.assertEqual(saved["members"], 2)
        self.assertEqual(saved["gsi1pk"], "UNIVERSE")
        self.assertEqual(saved["coverage"]["flows"]["revenue"], 0.5)

    def test_a_missing_company_facts_file_is_stored_empty(self) -> None:
        bucket = _Bucket()
        memory = _Memory()

        def facts(cik: str) -> dict[str, object]:
            if cik == CIK:
                raise http_client.HttpStatusError(404, "missing")
            return _facts()

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            result = ingest_fundamentals.refresh(
                [CIK, "2"],
                _Context(),
                fetch_facts=facts,
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(result["status"], "done")
        empty = s3io.get_gzip_json("data", f"fundamentals/raw/cik={CIK}/companyfacts.json.gz", client=bucket)
        self.assertEqual(empty["facts"], {})
        self.assertEqual(
            list(s3io.get_jsonl_gz("data", f"fundamentals/pit/cik={CIK}/facts.jsonl.gz", client=bucket)), []
        )
        kept = s3io.get_gzip_json("data", "fundamentals/raw/cik=0000000002/companyfacts.json.gz", client=bucket)
        self.assertIn("Revenues", kept["facts"]["us-gaap"])

        def denied(_cik: str) -> dict[str, object]:
            raise http_client.HttpStatusError(500, "down")

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            with self.assertRaises(http_client.HttpStatusError):
                ingest_fundamentals.refresh(
                    ["3"],
                    _Context(),
                    fetch_facts=denied,
                    bucket="data",
                    client=bucket,
                    ingest_enabled=lambda: True,
                )

    def test_a_timed_out_refresh_does_not_move_the_filings_cursor(self) -> None:
        bucket = _Bucket()
        memory = _Memory()

        class _Short:
            def get_remaining_time_in_millis(self) -> int:
                return 100_000

        def index(_day: date) -> list[dict[str, str]]:
            return [{"cik": CIK, "company": "Example", "form": "10-K", "filed": "2024-06-03", "path": "a"}]

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            waiting = ingest_fundamentals.daily(
                [CIK],
                DAY,
                _Short(),
                fetch_index=index,
                fetch_facts=lambda _cik: _facts(),
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
            self.assertEqual(waiting["status"], "running")
            self.assertNotIn(("JOB#ingest_filings", "CURSOR"), memory.items)
            done = ingest_fundamentals.daily(
                [CIK],
                DAY,
                _Context(),
                fetch_index=index,
                fetch_facts=lambda _cik: _facts(),
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(done["status"], "done")
        self.assertEqual(memory.items[("JOB#ingest_filings", "CURSOR")]["lastDate"], "2024-06-03")

    def test_catch_up_reads_the_cursor_and_stops_on_an_empty_index(self) -> None:
        bucket = _Bucket()
        memory = _Memory()
        memory.put({"pk": "JOB#ingest_filings", "sk": "CURSOR", "lastDate": "2024-06-03"})
        fetched: list[date] = []
        sessions = [date(2024, 6, 3), date(2024, 6, 5)]

        def index(day: date) -> list[dict[str, str]]:
            fetched.append(day)
            return [{"cik": CIK, "company": "Example", "form": "8-K", "filed": day.isoformat(), "path": "a"}]

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            result = ingest_fundamentals.daily(
                [CIK],
                date(2024, 6, 5),
                _Context(),
                sessions=sessions,
                fetch_index=index,
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(result["status"], "done")
        self.assertEqual(fetched, [date(2024, 6, 5)])
        self.assertEqual(memory.items[("JOB#ingest_filings", "CURSOR")]["lastDate"], "2024-06-05")

        memory.put({"pk": "JOB#ingest_filings", "sk": "CURSOR", "lastDate": "2024-06-03"})
        fetched.clear()
        stopped = [date(2024, 6, 3), date(2024, 6, 4), date(2024, 6, 5)]

        def gap(day: date) -> list[dict[str, str]]:
            fetched.append(day)
            return [] if day == date(2024, 6, 4) else index(day)

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            held = ingest_fundamentals.daily(
                [CIK],
                date(2024, 6, 5),
                _Context(),
                sessions=stopped,
                fetch_index=gap,
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(held["status"], "not_ready")
        self.assertEqual(fetched, [date(2024, 6, 4)])
        self.assertEqual(memory.items[("JOB#ingest_filings", "CURSOR")]["lastDate"], "2024-06-03")

    def test_coverage_needs_the_universe_row_and_ignores_a_stale_stock(self) -> None:
        bucket = _Bucket()
        memory = _Memory()
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            report = ingest_fundamentals.coverage_report([CIK], DAY, bucket="data", client=bucket)
        self.assertEqual(report["companies"], 1)
        self.assertEqual(memory.items, {})
        stale = {
            "field": "totalAssets",
            "kind": "stock",
            "start": "2020-01-01",
            "end": "2020-01-01",
            "value": 1,
            "filed": "2020-02-01",
            "form": "10-K",
        }
        s3io.put_jsonl_gz("data", "fundamentals/pit/cik=0000000002/facts.jsonl.gz", [stale], client=bucket)
        memory.put({"pk": "UNIVERSE#2024-06-03", "sk": "META", "members": 2, "gsi1pk": "UNIVERSE"})
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            ingest_fundamentals.refresh(
                [CIK],
                _Context(),
                fetch_facts=lambda _cik: _facts(),
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
            counted = ingest_fundamentals.coverage_report([CIK, "2"], DAY, bucket="data", client=bucket)
        self.assertEqual(counted["stocks"]["totalAssets"], 0.5)
        saved = memory.items[("UNIVERSE#2024-06-03", "META")]
        self.assertEqual(saved["members"], 2)
        self.assertEqual(saved["gsi1pk"], "UNIVERSE")

    def test_ingest_off_makes_no_request(self) -> None:
        def refuse(_cik: str) -> dict[str, object]:
            raise AssertionError("requested")

        with self.assertRaises(ingest_fundamentals.IngestDisabled):
            ingest_fundamentals.refresh(["1"], _Context(), fetch_facts=refuse, ingest_enabled=lambda: False)


if __name__ == "__main__":
    unittest.main()
