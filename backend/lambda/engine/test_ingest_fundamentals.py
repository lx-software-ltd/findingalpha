"""Trimmed facts, the daily index, and the coverage report."""

from __future__ import annotations

import unittest
from datetime import date

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
        memory.put({"pk": "UNIVERSE#2024-06-03", "sk": "META", "members": 2})
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
        self.assertEqual(saved["coverage"]["flows"]["revenue"], 0.5)

    def test_ingest_off_makes_no_request(self) -> None:
        def refuse(_cik: str) -> dict[str, object]:
            raise AssertionError("requested")

        with self.assertRaises(ingest_fundamentals.IngestDisabled):
            ingest_fundamentals.refresh(["1"], _Context(), fetch_facts=refuse, ingest_enabled=lambda: False)


if __name__ == "__main__":
    unittest.main()
