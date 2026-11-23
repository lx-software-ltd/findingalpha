"""Raw days, the month backfill, and adjusted parts."""

from __future__ import annotations

import io
import unittest
from datetime import date, timedelta
from unittest.mock import patch

import ingest_prices
import s3io
import store

DAY = date(2024, 6, 10)


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
        from botocore.exceptions import ClientError

        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str = "") -> dict[str, object]:
        keys = sorted(key for bucket, key in self.objects if bucket == Bucket and key.startswith(Prefix))
        start = int(ContinuationToken or "0")
        page = keys[start : start + 1]
        result: dict[str, object] = {
            "Contents": [{"Key": key} for key in page],
            "IsTruncated": start + 1 < len(keys),
        }
        if start + 1 < len(keys):
            result["NextContinuationToken"] = str(start + 1)
        return result

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)


class _Memory:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {}

    def get(self, pk: str, sk: str) -> dict[str, object] | None:
        item = self.items.get((pk, sk))
        return dict(item) if item else None

    def put(self, item: dict[str, object]) -> None:
        self.items[(str(item["pk"]), str(item["sk"]))] = dict(item)

    def delete(self, pk: str, sk: str) -> None:
        self.items.pop((pk, sk), None)

    def update(
        self,
        pk: str,
        sk: str,
        expression: str,
        values: dict[str, object],
        names: dict[str, str] | None = None,
    ) -> None:
        row = dict(self.items.get((pk, sk), {"pk": pk, "sk": sk}))
        row["pk"] = pk
        row["sk"] = sk
        body = expression.split("SET", 1)[1]
        for part in body.split(","):
            left, right = [piece.strip() for piece in part.split("=", 1)]
            row[(names or {}).get(left, left)] = values[right]
        self.items[(pk, sk)] = row

    def query_gsi1(self, gsi1pk: str, prefix: str = "") -> list[dict[str, object]]:
        return [
            dict(item)
            for item in self.items.values()
            if item.get("gsi1pk") == gsi1pk and str(item.get("gsi1sk") or "").startswith(prefix)
        ]

    def update_conditional(
        self,
        pk: str,
        sk: str,
        expression: str,
        values: dict[str, str],
        condition: str,
        names: dict[str, str] | None = None,
    ) -> dict[str, object] | None:
        del names
        previous: dict[str, object] | None
        if "coverage" in expression:
            from boto3.dynamodb.types import TypeSerializer

            TypeSerializer().serialize(values[":c"])
            current = self.items.get((pk, sk))
            if not current:
                raise store.ConditionNotMet(pk)
            previous = dict(current)
            row = dict(current)
            row["coverage"] = values[":c"]
            self.items[(pk, sk)] = row
            return previous
        del condition
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


class _Context:
    def get_remaining_time_in_millis(self) -> int:
        return 900_000


def _bar(symbol: str, day: date, close: float = 10) -> dict[str, object]:
    return {
        "symbol": symbol,
        "date": day.isoformat(),
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 100,
        "vwap": close,
    }


def _action(ex: str, process: str) -> dict[str, object]:
    return {
        "symbol": "EXMPL",
        "type": "cash_dividend",
        "exDate": ex,
        "processDate": process,
        "payDate": process,
        "cashPerShare": 0.25,
        "special": False,
        "foreign": False,
        "subType": None,
        "newSymbol": None,
        "splitFrom": None,
        "splitTo": None,
    }


def _bind(memory: _Memory):
    return (
        patch("store.get", memory.get),
        patch("store.put", memory.put),
        patch("store.update_conditional", memory.update_conditional),
        patch("store.delete", memory.delete),
    )


class PriceIngestTest(unittest.TestCase):
    def test_symbols_keep_inactive_names_only_for_the_backfill(self) -> None:
        assets = [
            {"symbol": "LIVE", "exchange": "NASDAQ", "status": "active"},
            {"symbol": "GONE", "exchange": "NYSE", "status": "inactive"},
            {"symbol": "FUND", "exchange": "ARCA", "status": "active"},
            {"symbol": "OTHR", "exchange": "AMEX", "status": "inactive"},
        ]
        self.assertEqual(ingest_prices.raw_symbols(assets, include_inactive=False), ["LIVE", "SPY"])
        self.assertEqual(ingest_prices.raw_symbols(assets, include_inactive=True), ["GONE", "LIVE", "SPY"])

    def test_placeholder_identifiers_are_not_priced(self) -> None:
        assets = [
            {"symbol": "LIVE", "exchange": "NASDAQ", "status": "active"},
            {"symbol": "000CVR019", "exchange": "NASDAQ", "status": "inactive"},
            {"symbol": "00000x0e0", "exchange": "NYSE", "status": "inactive"},
            {"symbol": "X00000019", "exchange": "NYSE", "status": "inactive"},
            {"symbol": "00000XCAL", "exchange": "NYSE", "status": "inactive"},
            {"symbol": "X000019", "exchange": "NASDAQ", "status": "inactive"},
            {"symbol": "EXM_DELISTED", "exchange": "NASDAQ", "status": "inactive"},
            {"symbol": "X000019_DELISTED", "exchange": "NASDAQ", "status": "inactive"},
            {"symbol": "EXM.RT", "exchange": "NYSE", "status": "inactive"},
            {"symbol": "EXMPL.U", "exchange": "NYSE", "status": "inactive"},
            {"symbol": "ABCDEFGHI", "exchange": "NYSE", "status": "inactive"},
            {"symbol": "EXM-A", "exchange": "NYSE", "status": "inactive"},
        ]
        with self.assertLogs("ingest_prices", level="INFO") as logged:
            found = ingest_prices.raw_symbols(assets, include_inactive=True)
        self.assertEqual(found, ["ABCDEFGHI", "EXM-A", "EXM.RT", "EXMPL.U", "LIVE", "SPY"])
        self.assertIn("dropped count=7", logged.output[0])
        self.assertIn("count=1 sample=['EXM-A']", logged.output[1])

    def test_a_saved_symbol_list_drops_placeholder_identifiers(self) -> None:
        bucket = _Bucket()
        memory = _Memory()
        asked: list[list[str]] = []
        saved = ["000CVR019", "GONE", "GONE_DELISTED", "X000019"]

        def bars(symbols: list[str], start: date, end: date, adjustment: str) -> list[dict[str, object]]:
            del end, adjustment
            asked.append(symbols)
            return [_bar(symbol, start) for symbol in symbols]

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            ingest_prices.backfill_raw(
                DAY,
                DAY,
                [DAY],
                _Context(),
                symbols=saved,
                fetch_bars=bars,
                fetch_actions=lambda _start, _end: [],
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
            state = memory.items[("JOB#backfill_prices", "STATE")]
            ingest_prices.ingest_raw_day(
                DAY,
                saved,
                fetch_bars=bars,
                fetch_actions=lambda _start, _end: [],
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
            ingest_prices.refresh_adjusted(
                saved, DAY, DAY, _Context(), fetch_bars=bars, bucket="data", client=bucket, ingest_enabled=lambda: True
            )
        self.assertEqual(state["params"]["symbols"], ["GONE", "SPY"])  # type: ignore[index]
        self.assertEqual(asked[:2], [["GONE", "SPY"], ["GONE", "SPY"]])
        self.assertEqual(asked[2:], [["BIL", "GONE", "SPY"], ["BIL", "GONE", "SPY"]])

    def test_a_day_keeps_the_session_ex_date_and_rejects_a_bad_bar(self) -> None:
        bucket = _Bucket()
        seen: dict[str, object] = {}

        def bars(symbols: list[str], start: date, end: date, adjustment: str) -> list[dict[str, object]]:
            seen["symbols"] = symbols
            seen["adjustment"] = adjustment
            self.assertEqual(start, DAY)
            self.assertEqual(end, DAY)
            return [_bar("EXMPL", DAY, 12), _bar("SPY", DAY, 11), _bar("EXMPL", DAY + timedelta(days=1))]

        def actions(start: date, end: date) -> list[dict[str, object]]:
            seen["window"] = (start, end)
            return [
                _action("2024-06-10", "2024-07-15"),
                _action("2024-06-10", "2024-08-24"),
                _action("2024-06-11", "2024-06-12"),
            ]

        result = ingest_prices.ingest_raw_day(
            DAY,
            ["EXMPL"],
            fetch_bars=bars,
            fetch_actions=actions,
            bucket="data",
            client=bucket,
            ingest_enabled=lambda: True,
        )
        self.assertEqual(result, {"bars": 2, "actions": 2})
        self.assertEqual(seen["symbols"], ["EXMPL", "SPY"])
        self.assertEqual(seen["window"], (DAY - timedelta(days=7), DAY + timedelta(days=75)))
        stored = list(s3io.get_jsonl_gz("data", "prices/raw/date=2024-06-10/bars.jsonl.gz", client=bucket))
        self.assertEqual([row["symbol"] for row in stored], ["EXMPL", "SPY"])
        kept = list(s3io.get_jsonl_gz("data", "corporate-actions/date=2024-06-10/actions.jsonl.gz", client=bucket))
        self.assertEqual([row["exDate"] for row in kept], ["2024-06-10", "2024-06-10"])
        self.assertEqual(kept[0]["processDate"], "2024-07-15")
        self.assertEqual(kept[1]["processDate"], "2024-08-24")

        def bad_bars(symbols: list[str], start: date, end: date, adjustment: str) -> list[dict[str, object]]:
            del symbols, end, adjustment
            broken = _bar("SPY", start)
            broken["close"] = 0
            return [broken]

        with self.assertRaises(ingest_prices.DataQualityError) as raised:
            ingest_prices.ingest_raw_day(
                date(2024, 6, 11),
                ["SPY"],
                fetch_bars=bad_bars,
                fetch_actions=lambda _start, _end: [],
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(raised.exception.check, "non_positive_price")
        self.assertNotIn(("data", "prices/raw/date=2024-06-11/bars.jsonl.gz"), bucket.objects)

    def test_the_bar_count_stays_within_fifteen_percent(self) -> None:
        bucket = _Bucket()
        previous = [_bar("SPY", date(2024, 6, 7))] + [_bar(f"S{index}", date(2024, 6, 7)) for index in range(19)]
        s3io.put_jsonl_gz("data", "prices/raw/date=2024-06-07/bars.jsonl.gz", previous, client=bucket)

        def bars_for(count: int):
            def bars(symbols: list[str], start: date, end: date, adjustment: str) -> list[dict[str, object]]:
                del symbols, end, adjustment
                return [_bar("SPY", start)] + [_bar(f"N{index}", start) for index in range(count - 1)]

            return bars

        with self.assertRaises(ingest_prices.DataQualityError) as raised:
            ingest_prices.ingest_raw_day(
                DAY,
                ["SPY"],
                fetch_bars=bars_for(24),
                fetch_actions=lambda _start, _end: [],
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(raised.exception.check, "bar_count")
        self.assertNotIn(("data", "prices/raw/date=2024-06-10/bars.jsonl.gz"), bucket.objects)
        ingest_prices.ingest_raw_day(
            DAY,
            ["SPY"],
            fetch_bars=bars_for(23),
            fetch_actions=lambda _start, _end: [],
            bucket="data",
            client=bucket,
            ingest_enabled=lambda: True,
        )
        self.assertIn(("data", "prices/raw/date=2024-06-10/bars.jsonl.gz"), bucket.objects)

    def test_backfill_is_one_month_per_chunk_and_keeps_inactive_names(self) -> None:
        bucket = _Bucket()
        memory = _Memory()
        calls: list[tuple[date, date, list[str]]] = []
        sessions = [date(2024, 1, 31), date(2024, 2, 1)]

        def bars(symbols: list[str], start: date, end: date, adjustment: str) -> list[dict[str, object]]:
            self.assertEqual(adjustment, "raw")
            calls.append((start, end, symbols))
            return [_bar(symbol, day) for day in sessions if start <= day <= end for symbol in ("SPY", "GONE")]

        def actions(start: date, end: date) -> list[dict[str, object]]:
            self.assertEqual(end - start, timedelta(days=7 + 75 + (calls[-1][1] - calls[-1][0]).days))
            return []

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            result = ingest_prices.backfill_raw(
                date(2024, 1, 31),
                date(2024, 2, 1),
                sessions,
                _Context(),
                symbols=["GONE", "LIVE"],
                fetch_bars=bars,
                fetch_actions=actions,
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(result["status"], "done")
        self.assertEqual([item[0] for item in calls], [date(2024, 1, 31), date(2024, 2, 1)])
        self.assertEqual(calls[0][1], date(2024, 1, 31))
        self.assertIn("GONE", calls[0][2])
        self.assertIn(("data", "prices/raw/date=2024-01-31/bars.jsonl.gz"), bucket.objects)
        self.assertIn(("data", "prices/raw/date=2024-02-01/bars.jsonl.gz"), bucket.objects)

    def test_a_bad_month_does_not_write_and_ingest_off_does_not_fetch(self) -> None:
        bucket = _Bucket()
        memory = _Memory()

        def bars(symbols: list[str], start: date, end: date, adjustment: str) -> list[dict[str, object]]:
            del symbols, end, adjustment
            if start.month == 2:
                return [_bar("SPY", date(2024, 2, 1), 0)]
            return [_bar("SPY", date(2024, 1, 31))]

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            with self.assertRaises(ingest_prices.DataQualityError):
                ingest_prices.backfill_raw(
                    date(2024, 1, 31),
                    date(2024, 2, 1),
                    [date(2024, 1, 31), date(2024, 2, 1)],
                    _Context(),
                    symbols=["SPY"],
                    fetch_bars=bars,
                    fetch_actions=lambda _start, _end: [],
                    bucket="data",
                    client=bucket,
                    ingest_enabled=lambda: True,
                )
        self.assertIn(("data", "prices/raw/date=2024-01-31/bars.jsonl.gz"), bucket.objects)
        self.assertNotIn(("data", "prices/raw/date=2024-02-01/bars.jsonl.gz"), bucket.objects)
        self.assertEqual(memory.items[("JOB#backfill_prices", "STATE")]["status"], "failed")

        def refuse(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
            raise AssertionError("requested")

        with self.assertRaises(ingest_prices.IngestDisabled):
            ingest_prices.ingest_raw_day(
                DAY, ["SPY"], fetch_bars=refuse, fetch_actions=refuse, ingest_enabled=lambda: False
            )

    def test_one_bad_print_does_not_fail_the_month(self) -> None:
        bucket = _Bucket()
        memory = _Memory()
        sessions = [date(2024, 1, 31), date(2024, 2, 1)]

        def bars(symbols: list[str], start: date, end: date, adjustment: str) -> list[dict[str, object]]:
            del symbols, adjustment
            rows = [_bar("SPY", day) for day in sessions if start <= day <= end]
            if start.month == 1:
                broken = _bar("GONE", date(2024, 1, 31))
                broken["close"] = 0
                rows.append(broken)
            return rows

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            result = ingest_prices.backfill_raw(
                date(2024, 1, 31),
                date(2024, 2, 1),
                sessions,
                _Context(),
                symbols=["GONE"],
                fetch_bars=bars,
                fetch_actions=lambda _start, _end: [],
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(result["status"], "done")
        stored = list(s3io.get_jsonl_gz("data", "prices/raw/date=2024-01-31/bars.jsonl.gz", client=bucket))
        self.assertEqual([row["symbol"] for row in stored], ["SPY"])

    def test_adjusted_parts_include_spy_and_bil(self) -> None:
        bucket = _Bucket()
        memory = _Memory()
        calls: list[tuple[str, int]] = []

        def bars(symbols: list[str], start: date, end: date, adjustment: str) -> list[dict[str, object]]:
            calls.append((adjustment, len(symbols)))
            self.assertEqual(start, date(2016, 1, 4))
            self.assertEqual(end, date(2024, 6, 3))
            close = 2 if adjustment == "all" else 1
            return [_bar(symbol, date(2024, 6, 3), close) for symbol in symbols]

        symbols = [f"S{chr(65 + index // 26)}{chr(65 + index % 26)}" for index in range(99)]
        bucket.objects[("data", "prices/adj/part=002/bars.jsonl.gz")] = b"stale"
        bucket.objects[("data", "prices/split/part=002/bars.jsonl.gz")] = b"stale"
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            result = ingest_prices.refresh_adjusted(
                symbols,
                "2016-01-04",
                "2024-06-03",
                _Context(),
                fetch_bars=bars,
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(result["status"], "done")
        self.assertEqual(calls, [("all", 100), ("split", 100), ("all", 1), ("split", 1)])
        rows = list(s3io.get_jsonl_gz("data", "prices/adj/part=000/bars.jsonl.gz", client=bucket))
        split_rows = list(s3io.get_jsonl_gz("data", "prices/split/part=000/bars.jsonl.gz", client=bucket))
        spy = list(s3io.get_jsonl_gz("data", "prices/adj/part=001/bars.jsonl.gz", client=bucket))
        self.assertEqual(rows[0]["close"], 2)
        self.assertEqual(split_rows[0]["close"], 1)
        self.assertIn("BIL", {row["symbol"] for row in rows})
        self.assertEqual([row["symbol"] for row in spy], ["SPY"])
        self.assertNotIn(("data", "prices/adj/part=002/bars.jsonl.gz"), bucket.objects)
        self.assertNotIn(("data", "prices/split/part=002/bars.jsonl.gz"), bucket.objects)
        self.assertEqual(s3io.get_json("data", "prices/manifest.json", client=bucket), {"parts": 2})

    def test_a_month_outside_the_sessions_writes_no_prices(self) -> None:
        bucket = _Bucket()
        memory = _Memory()

        def bars(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
            raise AssertionError("requested")

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            result = ingest_prices.backfill_raw(
                date(2024, 1, 31),
                date(2024, 2, 1),
                [date(2024, 3, 1)],
                _Context(),
                symbols=["GONE"],
                fetch_bars=bars,
                fetch_actions=bars,
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(result["status"], "done")
        self.assertFalse(any(key.startswith("prices/") for _bucket, key in bucket.objects))

    def test_reused_tickers_are_requested_once_and_listed(self) -> None:
        bucket = _Bucket()
        memory = _Memory()
        assets = [
            {"symbol": "EXMPL", "exchange": "NASDAQ", "status": "active", "id": "aaa"},
            {"symbol": "EXMPL", "exchange": "NYSE", "status": "inactive", "id": "bbb"},
            {"symbol": "ONLY", "exchange": "NASDAQ", "status": "active", "id": "ccc"},
        ]
        seen: list[list[str]] = []

        def bars(symbols: list[str], start: date, end: date, adjustment: str) -> list[dict[str, object]]:
            del end, adjustment
            seen.append(symbols)
            return [_bar(symbol, start) for symbol in symbols]

        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            ingest_prices.backfill_raw(
                DAY,
                DAY,
                [DAY],
                _Context(),
                symbols=ingest_prices.raw_symbols(assets, include_inactive=True),
                assets=assets,
                fetch_bars=bars,
                fetch_actions=lambda _start, _end: [],
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
            listed = s3io.get_json("data", "reference/symbol-reuse.json", client=bucket)
            ingest_prices.backfill_raw(
                DAY,
                DAY,
                [DAY],
                _Context(),
                symbols=["EXMPL", "ONLY", "SPY"],
                assets=[],
                fetch_bars=bars,
                fetch_actions=lambda _start, _end: [],
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
            self.assertEqual(s3io.get_json("data", "reference/symbol-reuse.json", client=bucket), listed)
        self.assertEqual(seen, [["EXMPL", "ONLY", "SPY"], ["EXMPL", "ONLY", "SPY"]])
        self.assertEqual(
            listed,
            [
                {
                    "symbol": "EXMPL",
                    "assets": [
                        {"id": "aaa", "status": "active", "exchange": "NASDAQ"},
                        {"id": "bbb", "status": "inactive", "exchange": "NYSE"},
                    ],
                }
            ],
        )

    def test_corporate_actions_can_be_rewritten_without_touching_bars(self) -> None:
        bucket = _Bucket()
        s3io.put_jsonl_gz("data", "prices/raw/date=2024-06-10/bars.jsonl.gz", [_bar("SPY", DAY)], client=bucket)
        before = bucket.objects[("data", "prices/raw/date=2024-06-10/bars.jsonl.gz")]
        result = ingest_prices.refresh_corporate_actions(
            DAY,
            DAY,
            [DAY],
            fetch_actions=lambda start, end: (
                [_action("2024-06-10", "2024-08-24")] if end == DAY + timedelta(days=75) else []
            ),
            bucket="data",
            client=bucket,
            ingest_enabled=lambda: True,
        )
        self.assertEqual(result, {"days": 1})
        kept = list(s3io.get_jsonl_gz("data", "corporate-actions/date=2024-06-10/actions.jsonl.gz", client=bucket))
        self.assertEqual(kept[0]["processDate"], "2024-08-24")
        self.assertEqual(bucket.objects[("data", "prices/raw/date=2024-06-10/bars.jsonl.gz")], before)


if __name__ == "__main__":
    unittest.main()
