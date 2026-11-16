"""Point-in-time membership, monthly stats, and the compact price marks."""

from __future__ import annotations

import io
import unittest

import backtest_inputs
import methodology
import s3io
from botocore.exceptions import ClientError


class BacktestInputsTest(unittest.TestCase):
    def test_a_name_that_left_the_latest_file_keeps_its_cik(self) -> None:
        bucket = _Bucket()
        s3io.put_jsonl_gz(
            "data",
            "universe/date=2017-01-31/members.jsonl.gz",
            [{"symbol": "OLD", "cik": "0000000001", "sector": "Energy", "sic": "1311", "name": "Old Co"}],
            client=bucket,
        )
        s3io.put_jsonl_gz(
            "data",
            "universe/date=2024-01-31/members.jsonl.gz",
            [{"symbol": "NEW", "cik": "0000000002", "sector": "Technology", "sic": "7372", "name": "New Co"}],
            client=bucket,
        )
        table = backtest_inputs.identities("data", bucket)
        self.assertEqual(backtest_inputs.identity_on(table, "OLD", "2024-06-01")["cik"], "0000000001")
        self.assertEqual(backtest_inputs.identity_on(table, "NEW", "2017-06-01")["cik"], "0000000002")
        self.assertEqual(backtest_inputs.identity_on(table, "GONE", "2024-06-01")["cik"], "")

    def test_a_name_never_listed_uses_todays_cik_and_a_later_filing_does_not_change_old_shares(self) -> None:
        bucket = _Bucket()
        s3io.put_jsonl_gz(
            "data",
            "universe/date=2017-01-31/members.jsonl.gz",
            [{"symbol": "OLD", "cik": "0000000001", "sector": "Energy", "name": "Old Co"}],
            client=bucket,
        )
        tickers = {"OLD": {"cik": "0000000099", "name": "Reused"}, "SMALL": {"cik": "2", "name": "Small Co"}}
        table = backtest_inputs.identities("data", bucket, tickers=tickers)
        self.assertEqual(backtest_inputs.identity_on(table, "OLD", "2018-01-31")["cik"], "0000000001")
        self.assertEqual(backtest_inputs.identity_on(table, "SMALL", "2018-01-31")["cik"], "0000000002")
        self.assertEqual(backtest_inputs.identity_on(table, "SMALL", "2018-01-31")["sector"], "")
        pit = [
            _shares("2017-01-31", 100, "2017-02-10"),
            _shares("2026-07-31", 400, "2026-08-10"),
        ]
        splits = [("2017-03-15", 4.0)]
        self.assertEqual(backtest_inputs.shares_on(pit, splits, "2017-02-28"), 100)
        self.assertEqual(backtest_inputs.shares_on(pit, splits, "2017-06-01"), 400)
        self.assertEqual(backtest_inputs.shares_on(pit, splits, "2026-08-31"), 400)

    def test_monthly_stats_are_read_per_month_for_the_requested_names(self) -> None:
        bucket = _Bucket()
        s3io.put_jsonl_gz(
            "data",
            "prices/monthly/month=2017-01/stats.jsonl.gz",
            [
                {"symbol": "AAA", "close": 10, "medianDollarVolume": 100, "monthEnd": "2017-01-31"},
                {"symbol": "BBB", "close": 9, "medianDollarVolume": 50, "monthEnd": "2017-01-31"},
            ],
            client=bucket,
        )
        s3io.put_jsonl_gz(
            "data",
            "prices/monthly/month=2017-02/stats.jsonl.gz",
            [{"symbol": "AAA", "close": 12, "medianDollarVolume": 110, "monthEnd": "2017-02-28"}],
            client=bucket,
        )
        found = backtest_inputs.monthly_for({"AAA"}, "data", bucket)
        self.assertEqual(found["AAA"]["2017-01"]["close"], 10)
        self.assertEqual(found["AAA"]["2017-02"]["close"], 12)
        self.assertNotIn("BBB", found)

    def test_marks_keep_only_held_names_and_the_benchmarks(self) -> None:
        bucket = _Bucket()
        s3io.put_json(
            "data",
            "backtests/run/holdings/month=2017-02.json",
            {"monthEnd": "2017-02-28", "holdings": [{"symbol": "AAA"}]},
            client=bucket,
        )
        bars = [
            {"symbol": "AAA", "date": "2017-02-01", "close": 10},
            {"symbol": "ZZZ", "date": "2017-02-01", "close": 99},
            {"symbol": "SPY", "date": "2017-02-01", "close": 20},
        ]
        s3io.put_jsonl_gz("data", "prices/adj/part=000/bars.jsonl.gz", bars, client=bucket)
        s3io.put_jsonl_gz("data", "prices/split/part=000/bars.jsonl.gz", bars, client=bucket)
        register = methodology.load()
        backtest_inputs.write_marks("000", "run", register, bucket="data", client=bucket)
        book = backtest_inputs.price_book("run", {"AAA", "SPY", "ZZZ"}, bucket="data", client=bucket)
        self.assertEqual(book["AAA"][0]["date"], "2017-02-01")
        self.assertEqual(book["AAA"][0]["adj"], 10)
        self.assertEqual(book["SPY"][0]["adj"], 20)
        self.assertEqual(book["ZZZ"], [])

    def test_one_month_of_factors_does_not_read_the_other_months(self) -> None:
        bucket = _Bucket()
        s3io.put_jsonl_gz(
            "data",
            "backtests/run/factors/month=2017-01/part=000.jsonl.gz",
            [{"symbol": "AAA", "month": "2017-01"}],
            client=bucket,
        )
        s3io.put_jsonl_gz(
            "data",
            "backtests/run/factors/month=2017-02/part=000.jsonl.gz",
            [{"symbol": "BBB", "month": "2017-02"}],
            client=bucket,
        )
        rows = backtest_inputs.factor_rows("run", "2017-02", "data", bucket)
        self.assertEqual([row["symbol"] for row in rows], ["BBB"])


def _shares(end: str, value: float, filed: str) -> dict[str, object]:
    return {
        "field": "sharesOutstanding",
        "kind": "share",
        "tag": "dei:EntityCommonStockSharesOutstanding",
        "start": end,
        "end": end,
        "value": value,
        "filed": filed,
    }


class _Body:
    def __init__(self, payload: bytes) -> None:
        self._buffer = io.BytesIO(payload)

    def read(self, n: int = -1) -> bytes:
        return self._buffer.read(n)

    def close(self) -> None:
        self._buffer.close()


class _Bucket:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        del ContentType
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
        return {"Body": _Body(self.objects[(Bucket, Key)])}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, str]:
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str = "") -> dict[str, object]:
        del ContinuationToken
        keys = sorted(key for bucket, key in self.objects if bucket == Bucket and key.startswith(Prefix))
        return {"Contents": [{"Key": key} for key in keys], "IsTruncated": False}


if __name__ == "__main__":
    unittest.main()
