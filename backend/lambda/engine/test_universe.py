"""Each universe rule removes only the companies that fail it."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

import s3io
import universe
from test_ingest_prices import _bind, _Bucket, _Context, _Memory

AS_OF = date(2024, 6, 3)
SHARES = 200_000_000
SMALL_SHARES = 100_000_000


def _cik(number: int) -> str:
    return str(number).zfill(10)


def _asset(
    symbol: str, exchange: str = "NASDAQ", status: str = "active", tradable: bool = True, marginable: bool = True
) -> dict[str, object]:
    return {"symbol": symbol, "exchange": exchange, "status": status, "tradable": tradable, "marginable": marginable}


def _annual(end: str, filed: str, form: str = "10-K") -> dict[str, object]:
    return {
        "field": "revenue",
        "kind": "flow",
        "start": f"{end[:4]}-01-01",
        "end": end,
        "value": 10,
        "filed": filed,
        "form": form,
    }


def _shares(value: int, filed: str = "2024-02-01", form: str = "10-K") -> dict[str, object]:
    return {
        "field": "sharesOutstanding",
        "kind": "stock",
        "start": "2023-12-31",
        "end": "2023-12-31",
        "value": value,
        "filed": filed,
        "form": form,
    }


def _history(
    shares: int,
    filed: str = "2024-02-01",
    form: str = "10-K",
    years: tuple[str, ...] = ("2021-12-31", "2022-12-31", "2023-12-31"),
) -> list[dict[str, object]]:
    return [_annual(end, filed, form) for end in years] + [_shares(shares, filed, form)]


class UniverseTest(unittest.TestCase):
    def test_ranges_cover_the_sic_list_once(self) -> None:
        ranges = universe.load_sectors()
        covered = 0
        previous = 99
        for row in ranges:
            self.assertEqual(row["from"], previous + 1)
            self.assertGreaterEqual(row["to"], row["from"])
            covered += row["to"] - row["from"] + 1
            previous = row["to"]
        self.assertEqual(ranges[0]["from"], 100)
        self.assertEqual(ranges[-1]["to"], 9999)
        self.assertEqual(covered, 9999 - 100 + 1)
        samples = {
            1311: "Energy",
            1221: "Energy",
            1000: "Materials",
            2834: "Health Care",
            3571: "Technology",
            3674: "Technology",
            7372: "Technology",
            3711: "Consumer Discretionary",
            5411: "Consumer Staples",
            6021: "Financials",
            6798: "Real Estate",
            4911: "Utilities",
            4813: "Communication",
            4011: "Industrials",
        }
        for code, sector in samples.items():
            self.assertEqual(universe.sector_for(code, ranges), sector, code)
        self.assertEqual(universe.sector_for(50, ranges), "Other")
        self.assertEqual(universe.sector_for("nope", ranges), "Other")

    def test_each_rule_removes_only_its_own_rows(self) -> None:
        sessions = [AS_OF - timedelta(days=offset) for offset in range(59, -1, -1)]
        symbols = {
            "PASS": (_cik(1), 10, 3_000_000),
            "GROW": (_cik(2), 10, 3_000_000),
            "LATE": (_cik(3), 10, 3_000_000),
            "BANK": (_cik(4), 10, 3_000_000),
            "FORM": (_cik(5), 10, 3_000_000),
            "YOUNG": (_cik(6), 10, 3_000_000),
            "SMALL": (_cik(7), 10, 3_000_000),
            "CHEAP": (_cik(8), 4, 3_000_000),
            "THIN": (_cik(9), 10, 100),
            "OTHER": (_cik(10), 10, 3_000_000),
            "OIL": (_cik(11), 10, 3_000_000),
            "NONE": (_cik(12), 10, 3_000_000),
        }
        bars = {
            day: [
                {"symbol": symbol, "close": close, "volume": volume, "date": day.isoformat()}
                for symbol, (_cik_value, close, volume) in symbols.items()
            ]
            for day in sessions
        }
        facts: dict[str, list[dict[str, object]] | None] = {
            _cik(1): _history(SHARES),
            _cik(3): _history(SHARES, filed="2024-07-01"),
            _cik(4): _history(SHARES),
            _cik(5): _history(SHARES, form="10-Q"),
            _cik(6): _history(SHARES, years=("2022-12-31", "2023-12-31")),
            _cik(7): _history(SMALL_SHARES),
            _cik(8): _history(SHARES),
            _cik(9): _history(SHARES),
            _cik(10): _history(SHARES),
            _cik(11): _history(SHARES),
        }
        sics = {
            _cik(1): "7372",
            _cik(2): "3571",
            _cik(4): "6021",
            _cik(5): "7372",
            _cik(6): "7372",
            _cik(7): "7372",
            _cik(10): "50",
            _cik(11): "1311",
        }
        refreshed: list[str] = []
        asked: list[str] = []

        def refresh(ciks: list[str], _context: object) -> dict[str, str]:
            refreshed.extend(ciks)
            facts[_cik(2)] = _history(SHARES)
            return {"status": "done"}

        def submissions(cik: str) -> dict[str, str]:
            asked.append(cik)
            return {"sic": sics[cik]}

        assets = [_asset(symbol) for symbol in symbols] + [
            _asset("NOCIK"),
            _asset("ARCA", exchange="ARCA"),
            _asset("GONE", status="inactive"),
            _asset("DARK", tradable=False),
            _asset("CASH", marginable=False),
            _asset("AMEX", exchange="AMEX"),
        ]
        tickers = {
            symbol: {"cik": cik, "name": f"Example {symbol}"} for symbol, (cik, _close, _volume) in symbols.items()
        }
        bucket = _Bucket()
        memory = _Memory()
        memory.put({"pk": "UNIVERSE#2024-06-03", "sk": "META", "coverage": {"asOf": "2024-06-03"}, "members": 1})
        with _bind(memory)[0], _bind(memory)[1], _bind(memory)[2]:
            result = universe.build(
                AS_OF,
                _Context(),
                assets=assets,
                tickers=tickers,
                sessions=sessions,
                read_bars=lambda day: bars[day],
                read_facts=facts.get,
                read_submissions=submissions,
                refresh=refresh,
                bucket="data",
                client=bucket,
                ingest_enabled=lambda: True,
            )
        self.assertEqual(
            result["counts"],
            {
                "assets": 13,
                "withCik": 12,
                "price": 11,
                "dollarVolume": 10,
                "fundamentals": 8,
                "sic": 7,
                "annualReport": 6,
                "history": 5,
                "marketCap": 4,
            },
        )
        self.assertEqual(refreshed, [_cik(2), _cik(12)])
        self.assertNotIn(_cik(3), asked)
        self.assertEqual(
            [
                row["symbol"]
                for row in s3io.get_jsonl_gz("data", "universe/date=2024-06-03/members.jsonl.gz", client=bucket)
            ],
            ["GROW", "OIL", "OTHER", "PASS"],
        )
        stored = {
            row["symbol"]: row
            for row in s3io.get_jsonl_gz("data", "universe/date=2024-06-03/members.jsonl.gz", client=bucket)
        }
        self.assertEqual(stored["PASS"]["sector"], "Technology")
        self.assertEqual(stored["OIL"]["sector"], "Energy")
        self.assertEqual(stored["OTHER"]["sector"], "Other")
        self.assertEqual(stored["PASS"]["sic"], "7372")
        self.assertEqual(stored["PASS"]["close"], 10)
        self.assertEqual(stored["PASS"]["marketCap"], SHARES * 10)
        self.assertGreaterEqual(stored["PASS"]["medianDollarVolume"], 20_000_000)
        saved = memory.items[("UNIVERSE#2024-06-03", "META")]
        self.assertEqual(saved["gsi1pk"], "UNIVERSE")
        self.assertEqual(saved["gsi1sk"], "2024-06-03")
        self.assertEqual(saved["members"], 4)
        self.assertEqual(saved["coverage"], {"asOf": "2024-06-03"})
        self.assertEqual(result["sectors"], {"Technology": 2, "Energy": 1, "Other": 1})

    def test_ingest_off_makes_no_request(self) -> None:
        def refuse(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
            raise AssertionError("requested")

        with self.assertRaises(universe.IngestDisabled):
            universe.build(
                AS_OF,
                _Context(),
                assets=[],
                tickers={},
                sessions=[],
                read_bars=refuse,
                read_facts=refuse,
                read_submissions=refuse,
                refresh=refuse,
                ingest_enabled=lambda: False,
            )


if __name__ == "__main__":
    unittest.main()
