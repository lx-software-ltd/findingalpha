"""Hard filters, the shortlist, and a stored screen."""

from __future__ import annotations

import io
import unittest

import methodology
import s3io
import screen
from botocore.exceptions import ClientError


def _row(symbol: str, **overrides: object) -> dict:
    base: dict = {
        "symbol": symbol,
        "composite": 1,
        "operatingIncome_ttm": 10,
        "freeCashFlow_ttm": 4,
        "netDebtToEbitda": 1,
        "longTermDebt": 10,
        "shortTermDebt": 0,
        "cash": 0,
    }
    base.update(overrides)
    return base


class ScreenTest(unittest.TestCase):
    def test_negative_ebitda_passes_only_when_the_company_has_net_cash(self) -> None:
        register = methodology.load()
        cash = _row("CASH", netDebtToEbitda=None, longTermDebt=0, shortTermDebt=0, cash=5)
        levered = _row("DEBT", netDebtToEbitda=None, longTermDebt=10, shortTermDebt=0, cash=0)
        self.assertTrue(screen.passes(cash, register))
        self.assertEqual(screen.failed_filters(cash, register), [])
        self.assertEqual(screen.failed_filters(levered, register), ["debtCeiling"])

    def test_a_missing_composite_or_a_failed_filter_stays_off_the_shortlist(self) -> None:
        register = methodology.load()
        register["screen"]["shortlistSize"] = 1
        rows = [
            _row("LOW", composite=1),
            _row("HIGH", composite=5),
            _row("LOSS", operatingIncome_ttm=-1, composite=9),
            _row("EMPTY", composite=None),
        ]
        picked = screen.shortlist(rows, register)
        self.assertEqual([row["symbol"] for row in picked], ["HIGH"])

    def test_thirty_companies_rank_only_the_names_that_pass(self) -> None:
        register = methodology.load()
        register["screen"]["shortlistSize"] = 5
        rows = [_company(register, f"S{index:02d}", index) for index in range(30)]
        rows.append(_company(register, "FAIL", 100, income=-1))
        rows.append(_company(register, "EMPTY", 100, present=False))
        rows.extend([_company(register, symbol, 12) for symbol in ("MMM", "AAA")])
        scored = screen.score(rows, register)
        by_symbol = {row["symbol"]: row for row in scored}
        self.assertIsNone(by_symbol["FAIL"]["rank"])
        self.assertEqual(by_symbol["FAIL"]["failedFilters"], ["positiveOperatingIncome"])
        self.assertIsNone(by_symbol["EMPTY"]["rank"])
        self.assertEqual(by_symbol["EMPTY"]["failedFilters"], ["composite"])
        ranked = sorted((row for row in scored if row["rank"] is not None), key=lambda row: row["rank"])
        self.assertEqual([row["symbol"] for row in ranked[:5]], ["S29", "S28", "S27", "S26", "S25"])
        self.assertLess(by_symbol["AAA"]["rank"], by_symbol["MMM"]["rank"])
        table = _Table()
        bucket = _Bucket()
        screen.publish("2017-02-28", scored, register, bucket="data", client=bucket, table=table)
        screen.publish("2017-02-28", scored, register, bucket="data", client=bucket, table=table)
        stored = list(s3io.get_jsonl_gz("data", "screens/date=2017-02-28/scores.jsonl.gz", client=bucket))
        self.assertEqual([row["symbol"] for row in stored], sorted(row["symbol"] for row in scored))
        self.assertEqual(len(table.query_pk("SCREEN#2017-02-28", "RANK#")), 5)

    def test_the_screen_uses_the_close_on_its_date(self) -> None:
        bucket = _Bucket()
        pit = [
            {
                "field": "sharesOutstanding",
                "kind": "stock",
                "tag": "dei:EntityCommonStockSharesOutstanding",
                "start": "2017-02-28",
                "end": "2017-02-28",
                "value": 10,
                "filed": "2017-02-28",
                "form": "10-Q",
            }
        ]
        s3io.put_json("data", "reference/calendar/year=2017.json", {"sessions": ["2017-02-28"]}, client=bucket)
        s3io.put_jsonl_gz(
            "data",
            "prices/raw/date=2017-02-28/bars.jsonl.gz",
            [{"symbol": "AAA", "close": 12, "volume": 1}],
            client=bucket,
        )
        s3io.put_jsonl_gz(
            "data",
            "prices/adj/part=000/bars.jsonl.gz",
            [{"symbol": "AAA", "date": "2017-02-28", "close": 12}, {"symbol": "BBB", "date": "2017-02-28", "close": 8}],
            client=bucket,
        )
        s3io.put_jsonl_gz("data", "fundamentals/pit/cik=0000000001/facts.jsonl.gz", pit, client=bucket)
        market = screen.load_market("2017-02-28", bucket="data", client=bucket)
        self.assertEqual(sorted(market["bars"]), ["AAA", "BBB"])
        body = screen._snapshot(
            {"symbol": "AAA", "cik": "0000000001", "close": 999, "marketCap": 9990},
            "2017-02-28",
            bucket,
            market,
            bucket="data",
        )
        self.assertEqual(body["marketCap"], 120)


def _company(register: dict, symbol: str, level: int, *, income: float = 10, present: bool = True) -> dict:
    weights = register["composite"]["groupWeights"]
    row = {
        "symbol": symbol,
        "name": symbol,
        "sector": "tech",
        "operatingIncome_ttm": income,
        "freeCashFlow_ttm": 4,
        "longTermDebt": 0,
        "shortTermDebt": 0,
        "cash": 1,
    }
    for factor in register["factors"]:
        if not present:
            row[factor["id"]] = None
            continue
        if factor["id"] in {"netDebtToEbitda", "accruals"}:
            row[factor["id"]] = 1
        elif factor["group"] in weights or factor["group"] == "reported":
            row[factor["id"]] = level
    return row


class _Table:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}

    def put(self, item: dict) -> None:
        self.rows[(item["pk"], item["sk"])] = dict(item)

    def delete(self, pk: str, sk: str) -> None:
        self.rows.pop((pk, sk), None)

    def query_pk(self, pk: str, prefix: str = "") -> list[dict]:
        return [item for (key, sk), item in self.rows.items() if key == pk and sk.startswith(prefix)]


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

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        return {"Body": _Body(self.objects[(Bucket, Key)])}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, str]:
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str = "") -> dict[str, object]:
        keys = sorted(key for bucket, key in self.objects if bucket == Bucket and key.startswith(Prefix))
        start = int(ContinuationToken or "0")
        page = keys[start : start + 1000]
        return {"Contents": [{"Key": key} for key in page], "IsTruncated": False}


if __name__ == "__main__":
    unittest.main()
