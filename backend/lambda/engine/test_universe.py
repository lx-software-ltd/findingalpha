"""Each universe rule removes only the companies that fail it."""

from __future__ import annotations

import json
import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import s3io
import universe
import universe_data
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
    same_filing: bool = False,
) -> list[dict[str, object]]:
    """One 10-K per fiscal year, unless ``same_filing`` puts every column on one date."""
    rows: list[dict[str, object]] = []
    for end in years:
        when = filed if same_filing or end == years[-1] else f"{int(end[:4]) + 1}-02-15"
        rows.append(_annual(end, when, form))
    rows.append(_shares(shares, filed, form))
    return rows


def _built_sectors(
    cases: list[tuple[str, str, str]], *, sectors: list[dict[str, object]] | None = None
) -> dict[str, str]:
    """Run one build and return ``symbol -> sector`` for the members it writes."""
    sessions = [AS_OF - timedelta(days=offset) for offset in range(59, -1, -1)]
    bars = {
        day: [
            {"symbol": symbol, "close": 10, "volume": 3_000_000, "date": day.isoformat()}
            for symbol, _cik, _sic in cases
        ]
        for day in sessions
    }
    facts = {universe._cik(cik): _history(SHARES) for _symbol, cik, _sic in cases}
    sics = {universe._cik(cik): sic for _symbol, cik, sic in cases}
    bucket = _Bucket()
    memory = _Memory()
    with (
        _bind(memory)[0],
        _bind(memory)[1],
        _bind(memory)[2],
        patch("store.update", memory.update),
        patch("store.query_gsi1", memory.query_gsi1),
    ):
        universe.build(
            AS_OF,
            _Context(),
            assets=[_asset(symbol) for symbol, _cik, _sic in cases],
            tickers={symbol: {"cik": cik, "name": f"Example {symbol}"} for symbol, cik, _sic in cases},
            sessions=sessions,
            read_bars=lambda day: bars[day],
            read_facts=facts.get,
            read_submissions=lambda cik: {"sic": sics[cik]},
            refresh=lambda _ciks, _context: {"status": "done"},
            read_actions=lambda _day: [],
            read_cover=lambda _cik, _day: None,
            bucket="data",
            client=bucket,
            ingest_enabled=lambda: True,
            sectors=sectors,
        )
    rows = s3io.get_jsonl_gz("data", "universe/date=2024-06-03/members.jsonl.gz", client=bucket)
    return {str(row["symbol"]): str(row["sector"]) for row in rows}


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

    def test_the_owner_sector_decisions(self) -> None:
        rules = universe.load_rules()
        excluded = rules["excludeSicRanges"]
        self.assertFalse(universe._excluded(6324, excluded))
        self.assertTrue(universe._excluded(6321, excluded))
        self.assertTrue(universe._excluded(6311, excluded))
        self.assertTrue(universe._excluded(6331, excluded))
        self.assertTrue(universe._excluded(6021, excluded))
        self.assertEqual(universe.sector_for(5331), "Consumer Staples")
        self.assertEqual(universe.sector_for(5399), "Consumer Staples")
        self.assertEqual(universe.sector_for(5311), "Consumer Discretionary")
        self.assertEqual(universe.sector_for(6324), "Health Care")
        self.assertEqual(universe.sector_for(6321), "Financials")
        self.assertEqual(universe.sector_for(7389, cik="0001403161"), "Financials")
        self.assertEqual(universe.sector_for(7389, cik="0001141391"), "Financials")
        self.assertEqual(universe.sector_for(5331, cik="0001177609"), "Consumer Discretionary")
        self.assertEqual(universe.sector_for(5331, cik="0001639300"), "Consumer Discretionary")
        self.assertEqual(universe.sector_for(7389, cik="0000000099"), "Industrials")
        sectors = json.loads(universe._SECTORS.read_text(encoding="utf-8"))
        self.assertEqual(sectors["version"], 2)
        self.assertEqual(sectors["status"], "confirmed")
        self.assertNotIn("symbolSectors", sectors)
        self.assertEqual(json.loads(universe._RULES.read_text(encoding="utf-8"))["version"], 5)
        self.assertEqual(int(rules["minFundamentalsYears"]), 3)
        two_filings = _history(SHARES, years=("2022-12-31", "2023-12-31"))
        self.assertLess(len(set(universe._annual_filings(two_filings, "10-K").values())), 3)

    def test_company_sectors_are_written_on_the_members(self) -> None:
        found = _built_sectors(
            [
                ("CARD", "0001403161", "7389"),
                ("SHOP", "0001177609", "5331"),
                ("STAP", "0000000099", "5331"),
                ("PLAN", "0000006324", "6324"),
            ]
        )
        self.assertEqual(
            found,
            {
                "CARD": "Financials",
                "SHOP": "Consumer Discretionary",
                "STAP": "Consumer Staples",
                "PLAN": "Health Care",
            },
        )

    def test_injected_ranges_do_not_use_the_contract_overrides(self) -> None:
        found = _built_sectors(
            [("CARD", "0001403161", "7389")],
            sectors=[{"from": 100, "to": 9999, "sector": "Industrials"}],
        )
        self.assertEqual(found, {"CARD": "Industrials"})

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
            _cik(3): _history(SHARES, filed="2024-07-01", same_filing=True),
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
        with (
            _bind(memory)[0],
            _bind(memory)[1],
            _bind(memory)[2],
            patch("store.update", memory.update),
            patch("store.query_gsi1", memory.query_gsi1),
        ):
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
        self.assertEqual(saved["lastPriceDate"], "2024-06-03")
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


_AUTO = object()
_MEMBERS = "universe/date=2024-06-03/members.jsonl.gz"


def _sessions(days: int = 60) -> list[date]:
    return [AS_OF - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def _company(
    symbol: str,
    cik: int = 1,
    *,
    close: float = 10,
    volume: float = 3_000_000,
    sic: str | None = "7372",
    shares: int = SHARES,
    facts: object = _AUTO,
    same_filing: bool = False,
    filed: str = "2024-02-01",
    years: tuple[str, ...] = ("2021-12-31", "2022-12-31", "2023-12-31"),
    bar_days: int | None = None,
) -> dict[str, object]:
    stored = _history(shares, filed=filed, years=years, same_filing=same_filing) if facts is _AUTO else facts
    return {
        "symbol": symbol,
        "cik": _cik(cik),
        "close": close,
        "volume": volume,
        "sic": sic,
        "facts": stored,
        "bar_days": bar_days,
    }


def _build(
    companies: list[dict[str, object]],
    *,
    on: date = AS_OF,
    sessions: list[date] | None = None,
    read_bars: object = None,
    refresh: object = None,
    read_actions: object = None,
    read_cover: object = None,
    memory: _Memory | None = None,
    bucket: _Bucket | None = None,
    fact_reads: list[str] | None = None,
    context: object = None,
) -> tuple[dict[str, object], _Bucket, _Memory]:
    chosen = sessions if sessions is not None else _sessions()
    memory = memory or _Memory()
    bucket = bucket or _Bucket()
    facts = {str(company["cik"]): company["facts"] for company in companies if company["facts"] is not None}
    sics = {str(company["cik"]): company["sic"] for company in companies}

    def bars(day: date) -> list[dict[str, object]]:
        if read_bars is not None:
            return read_bars(day)  # type: ignore[operator]
        rows = []
        for company in companies:
            limit = company["bar_days"]
            if isinstance(limit, int) and day not in chosen[-limit:]:
                continue
            rows.append(
                {
                    "symbol": company["symbol"],
                    "close": company["close"],
                    "volume": company["volume"],
                    "date": day.isoformat(),
                }
            )
        return rows

    def submissions(cik: str) -> dict[str, object]:
        return {"sic": sics.get(cik)}

    assets = [_asset(str(company["symbol"])) for company in companies]
    tickers = {
        str(company["symbol"]): {"cik": company["cik"], "name": f"Example {company['symbol']}"} for company in companies
    }
    with (
        _bind(memory)[0],
        _bind(memory)[1],
        _bind(memory)[2],
        patch("store.update", memory.update),
        patch("store.query_gsi1", memory.query_gsi1),
    ):
        result = universe.build(
            on,
            context or _Context(),
            assets=assets,
            tickers=tickers,
            sessions=chosen,
            read_bars=bars,
            read_facts=_counted_facts(facts, fact_reads),
            read_submissions=submissions,
            refresh=refresh or (lambda _ciks, _context: {"status": "done"}),
            read_actions=read_actions,
            read_cover=read_cover,
            bucket="data",
            client=bucket,
            ingest_enabled=lambda: True,
        )
    return result, bucket, memory


def _counted_facts(facts: dict[str, object], reads: list[str] | None):
    def read(cik: str) -> object:
        if reads is not None:
            reads.append(cik)
        return facts.get(cik)

    return read


def _symbols(bucket: _Bucket) -> list[str]:
    if ("data", _MEMBERS) not in bucket.objects:
        return []
    return [str(row["symbol"]) for row in s3io.get_jsonl_gz("data", _MEMBERS, client=bucket)]


class UniverseReviewTest(unittest.TestCase):
    def test_one_ten_k_does_not_count_its_comparative_years(self) -> None:
        result, bucket, _memory = _build([_company("ONCE", same_filing=True)])
        self.assertEqual(result["counts"]["annualReport"], 1)
        self.assertEqual(result["counts"]["history"], 0)
        self.assertEqual(_symbols(bucket), [])

    def test_an_amendment_does_not_add_a_fiscal_year(self) -> None:
        rows = _history(SHARES, years=("2022-12-31", "2023-12-31"))
        rows.append(_annual("2023-12-31", "2024-03-01", "10-K/A"))
        result, bucket, _memory = _build([_company("AMEND", facts=rows)])
        self.assertEqual(result["counts"]["annualReport"], 1)
        self.assertEqual(result["counts"]["history"], 0)
        self.assertEqual(_symbols(bucket), [])

    def test_a_ten_k_older_than_the_contract_age_does_not_qualify(self) -> None:
        def filings(age: int) -> list[dict[str, object]]:
            latest = AS_OF - timedelta(days=age)
            rows = [
                _annual(str(2018 + index) + "-12-31", (latest - timedelta(days=365 * (2 - index))).isoformat())
                for index in range(3)
            ]
            rows.append(_shares(SHARES, latest.isoformat()))
            return rows

        kept, fresh_bucket, _memory = _build([_company("FRESH", facts=filings(500))])
        dropped, stale_bucket, _memory = _build([_company("STALE", facts=filings(501))])
        self.assertEqual(_symbols(fresh_bucket), ["FRESH"])
        self.assertEqual(kept["counts"]["annualReport"], 1)
        self.assertEqual(dropped["counts"]["annualReport"], 0)
        self.assertEqual(_symbols(stale_bucket), [])

    def test_two_classes_become_one_listing_with_combined_shares(self) -> None:
        shared = _history(120_000_000)
        shared.append(_shares(100_000_000))
        result, bucket, _memory = _build(
            [
                _company("CLB", volume=4_000_000, facts=shared),
                _company("CLASS", volume=5_000_000, facts=shared),
            ]
        )
        self.assertEqual(result["counts"]["withCik"], 2)
        self.assertEqual(result["counts"]["price"], 1)
        self.assertEqual(result["counts"]["dollarVolume"], 1)
        self.assertEqual(_symbols(bucket), ["CLASS"])
        stored = list(s3io.get_jsonl_gz("data", _MEMBERS, client=bucket))
        self.assertEqual(stored[0]["marketCap"], 220_000_000 * 10)

    def test_a_short_listing_fails_the_volume_rule(self) -> None:
        result, bucket, _memory = _build([_company("NEW", volume=50_000_000, bar_days=5)])
        self.assertEqual(result["counts"]["price"], 1)
        self.assertEqual(result["counts"]["dollarVolume"], 0)
        self.assertEqual(_symbols(bucket), [])

    def test_a_split_after_the_share_count_adjusts_market_cap(self) -> None:
        def actions(day: date) -> list[dict[str, object]]:
            if day.isoformat() != "2024-04-15":
                return []
            return [
                {
                    "symbol": "SPLIT",
                    "type": "forward_split",
                    "exDate": "2024-04-15",
                    "splitFrom": 1,
                    "splitTo": 10,
                },
                {
                    "symbol": "SPLIT",
                    "type": "cash_dividend",
                    "exDate": "2024-04-15",
                    "splitFrom": None,
                    "splitTo": None,
                },
            ]

        result, bucket, _memory = _build(
            [_company("SPLIT", shares=SMALL_SHARES)],
            read_actions=actions,
        )
        self.assertEqual(result["members"], 1)
        stored = list(s3io.get_jsonl_gz("data", _MEMBERS, client=bucket))
        self.assertEqual(stored[0]["marketCap"], SMALL_SHARES * 10 * 10)

    def test_a_blank_sic_fails_and_an_unmapped_code_stays_other(self) -> None:
        result, bucket, _memory = _build([_company("BLANK", cik=1, sic=None), _company("ODD", cik=2, sic="50")])
        self.assertEqual(result["counts"]["fundamentals"], 2)
        self.assertEqual(result["counts"]["sic"], 1)
        self.assertEqual(_symbols(bucket), ["ODD"])
        stored = list(s3io.get_jsonl_gz("data", _MEMBERS, client=bucket))
        self.assertEqual(stored[0]["sector"], "Other")

    def test_a_missing_last_price_file_writes_nothing(self) -> None:
        sessions = _sessions()
        bucket = _Bucket()

        def bars(day: date) -> list[dict[str, object]]:
            if day == sessions[-1]:
                return []
            return [{"symbol": "PASS", "close": 10, "volume": 3_000_000, "date": day.isoformat()}]

        with self.assertRaises(universe.PriceSessionMissing):
            _build([_company("PASS")], sessions=sessions, read_bars=bars, bucket=bucket)
        self.assertNotIn(("data", _MEMBERS), bucket.objects)

    def test_a_short_calendar_writes_nothing(self) -> None:
        bucket = _Bucket()
        with self.assertRaises(universe.PriceWindowShort):
            _build([_company("PASS")], sessions=_sessions(10), bucket=bucket)
        self.assertNotIn(("data", _MEMBERS), bucket.objects)

    def test_an_unfinished_refresh_writes_nothing(self) -> None:
        bucket = _Bucket()

        def refresh(ciks: list[str], _context: object) -> dict[str, object]:
            self.assertEqual(ciks, [_cik(1)])
            return {"status": "running", "cursor": 0, "total": 1}

        result, _bucket, memory = _build([_company("NEED", facts=None)], refresh=refresh, bucket=bucket)
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["pending"], 1)
        self.assertNotIn(("data", _MEMBERS), bucket.objects)
        self.assertNotIn(("UNIVERSE#2024-06-03", "META"), memory.items)

    def test_half_the_previous_build_is_kept_and_less_is_refused(self) -> None:
        allowed = _Memory()
        allowed.put(
            {
                "pk": "UNIVERSE#2024-05-31",
                "sk": "META",
                "gsi1pk": "UNIVERSE",
                "gsi1sk": "2024-05-31",
                "members": 2,
                "counts": {"marketCap": 2},
            }
        )
        kept, _bucket, _memory = _build([_company("PASS")], memory=allowed)
        self.assertEqual(kept["members"], 1)

        refused = _Memory()
        refused.put(
            {
                "pk": "UNIVERSE#2024-05-31",
                "sk": "META",
                "gsi1pk": "UNIVERSE",
                "gsi1sk": "2024-05-31",
                "members": Decimal("4"),
                "counts": {"marketCap": 4},
                "coverage": {"asOf": "2024-05-31"},
            }
        )
        bucket = _Bucket()
        with self.assertRaises(universe_data.UniverseShrink):
            _build([_company("PASS")], memory=refused, bucket=bucket)
        self.assertNotIn(("data", _MEMBERS), bucket.objects)
        self.assertEqual(refused.items[("UNIVERSE#2024-05-31", "META")]["members"], Decimal("4"))
        self.assertEqual(refused.items[("UNIVERSE#2024-05-31", "META")]["coverage"], {"asOf": "2024-05-31"})

    def test_sic_is_cached_and_a_blank_code_is_not(self) -> None:
        calls: list[str] = []
        bucket = _Bucket()

        def submissions(cik: str) -> dict[str, str]:
            calls.append(cik)
            return {"sic": "" if cik.endswith("2") else "7372"}

        with patch("sec_edgar.submissions", submissions):
            reader = universe_data.submissions_reader("data", bucket)
            self.assertEqual(reader(_cik(1))["sic"], "7372")
            self.assertEqual(reader(_cik(1))["sic"], "7372")
            self.assertIsNone(reader(_cik(2))["sic"])
            self.assertIsNone(reader(_cik(2))["sic"])
        self.assertEqual(calls, [_cik(1), _cik(2), _cik(2)])

    def test_each_company_file_is_read_once(self) -> None:
        reads: list[str] = []
        _build([_company("PASS", cik=1), _company("ALSO", cik=2)], fact_reads=reads)
        self.assertEqual(reads, [_cik(1), _cik(2)])

    def test_the_refresh_job_is_not_the_backfill(self) -> None:
        seen: dict[str, str] = {}

        def fake(_ciks: list[str], _context: object, **kwargs: object) -> dict[str, str]:
            seen["job"] = str(kwargs["job"])
            return {"status": "done"}

        with patch("ingest_fundamentals.refresh", fake):
            universe_data.refresh_runner("data", None)([_cik(1)], None)
        self.assertEqual(seen["job"], "universe_fundamentals_refresh")

    def test_a_missing_price_file_inside_the_window_writes_nothing(self) -> None:
        sessions = _sessions()
        bucket = _Bucket()

        def bars(day: date) -> list[dict[str, object]] | None:
            if day == sessions[10]:
                return None
            return [{"symbol": "PASS", "close": 10, "volume": 3_000_000, "date": day.isoformat()}]

        with self.assertRaises(universe.PriceSessionMissing) as caught:
            _build([_company("PASS")], sessions=sessions, read_bars=bars, bucket=bucket)
        self.assertIn(sessions[10].isoformat(), str(caught.exception))
        self.assertIn("backfill_prices", str(caught.exception))
        self.assertNotIn(("data", _MEMBERS), bucket.objects)

    def test_sic_lookups_stop_before_the_invocation_ends(self) -> None:
        bucket = _Bucket()

        class AlmostDone(_Context):
            def get_remaining_time_in_millis(self) -> int:
                return 60_000

        result, _bucket, memory = _build([_company("PASS")], bucket=bucket, context=AlmostDone())
        self.assertEqual(result["status"], "running")
        self.assertGreaterEqual(result["pending"], 1)
        self.assertNotIn(("data", _MEMBERS), bucket.objects)
        self.assertNotIn(("UNIVERSE#2024-06-03", "META"), memory.items)

    def test_a_balance_sheet_count_ignores_a_split_before_the_filing(self) -> None:
        rows = _history(SHARES, filed="2024-04-26")
        rows[-1]["tag"] = "CommonStockSharesOutstanding"

        def actions(day: date) -> list[dict[str, object]]:
            if day.isoformat() != "2024-04-15":
                return []
            return [{"symbol": "SHEET", "type": "forward_split", "exDate": "2024-04-15", "splitFrom": 1, "splitTo": 10}]

        _result, bucket, _memory = _build([_company("SHEET", facts=rows, shares=SMALL_SHARES)], read_actions=actions)
        stored = list(s3io.get_jsonl_gz("data", _MEMBERS, client=bucket))
        self.assertEqual(stored[0]["sharesSource"], "balanceSheet")
        self.assertEqual(stored[0]["marketCap"], SHARES * 10)

    def test_a_stale_count_uses_one_weighted_average_duration(self) -> None:
        rows = _history(SHARES)
        rows[-1]["end"] = "2022-01-31"
        rows[-1]["start"] = "2022-01-31"
        rows.append(_weighted("2023-04-01", "2024-03-31", 300_000_000))
        rows.append(_weighted("2024-01-01", "2024-03-31", 250_000_000))
        _result, bucket, _memory = _build([_company("AVG", facts=rows)])
        stored = list(s3io.get_jsonl_gz("data", _MEMBERS, client=bucket))
        self.assertEqual(stored[0]["sharesSource"], "weightedDiluted")
        self.assertEqual(stored[0]["marketCap"], 250_000_000 * 10)

    def test_a_missing_count_uses_the_cover_page_class_sum(self) -> None:
        rows = _history(SHARES)
        rows[-1]["end"] = "2022-01-31"
        rows[-1]["start"] = "2022-01-31"

        def cover(_cik: str, _on: date) -> dict[str, object]:
            return {"filed": "2024-04-24", "end": "2024-04-17", "value": 300_000_000}

        _result, bucket, _memory = _build([_company("CLASS", facts=rows)], read_cover=cover)
        stored = list(s3io.get_jsonl_gz("data", _MEMBERS, client=bucket))
        self.assertEqual(stored[0]["sharesSource"], "coverClasses")
        self.assertEqual(stored[0]["marketCap"], 300_000_000 * 10)
        self.assertEqual(_result["shareSources"], {"coverClasses": 1})

    def test_a_cover_page_is_downloaded_once_per_filing(self) -> None:
        downloads: list[str] = []
        payload = {
            "filings": {
                "recent": {
                    "form": ["10-Q", "8-K"],
                    "filingDate": ["2024-04-24", "2024-04-01"],
                    "accessionNumber": ["0000000001-24-000001", "0000000001-24-000000"],
                    "primaryDocument": ["cover.htm", "other.htm"],
                }
            }
        }
        document = (
            '<xbrli:context id="c"><xbrli:instant>2024-04-17</xbrli:instant></xbrli:context>'
            '<ix:nonFraction contextRef="c" name="dei:EntityCommonStockSharesOutstanding" scale="0">300</ix:nonFraction>'
        )

        def filing(_cik: str, accession: str, name: str) -> str:
            downloads.append(f"{accession}:{name}")
            return document

        bucket = _Bucket()
        with (
            patch("sec_edgar.submissions", return_value=payload),
            patch("sec_edgar.filing", side_effect=filing),
        ):
            reader = universe_data.cover_reader("data", bucket)
            first = reader(_cik(1), AS_OF)
            second = reader(_cik(1), AS_OF)
        self.assertEqual(first["value"], 300)
        self.assertEqual(second["accession"], "0000000001-24-000001")
        self.assertEqual(downloads, ["0000000001-24-000001:cover.htm"])

    def test_an_empty_amendment_falls_back_to_the_previous_filing(self) -> None:
        downloads: list[str] = []
        payload = {
            "filings": {
                "recent": {
                    "form": ["10-Q/A", "10-Q"],
                    "filingDate": ["2024-05-01", "2024-04-24"],
                    "accessionNumber": ["0000000001-24-000002", "0000000001-24-000001"],
                    "primaryDocument": ["amend.htm", "cover.htm"],
                }
            }
        }
        documents = {
            "amend.htm": "<html>no shares</html>",
            "cover.htm": (
                '<xbrli:context id="c"><xbrli:instant>2024-04-17</xbrli:instant></xbrli:context>'
                '<ix:nonFraction contextRef="c" name="dei:EntityCommonStockSharesOutstanding" scale="0">300</ix:nonFraction>'
            ),
        }

        def filing(_cik: str, accession: str, name: str) -> str:
            downloads.append(f"{accession}:{name}")
            return documents[name]

        bucket = _Bucket()
        with (
            patch("sec_edgar.submissions", return_value=payload),
            patch("sec_edgar.filing", side_effect=filing),
        ):
            reader = universe_data.cover_reader("data", bucket)
            first = reader(_cik(1), AS_OF)
            second = reader(_cik(1), AS_OF)
        self.assertEqual(first["value"], 300)
        self.assertEqual(first["accession"], "0000000001-24-000001")
        self.assertEqual(second["accession"], first["accession"])
        self.assertEqual(downloads, ["0000000001-24-000002:amend.htm", "0000000001-24-000001:cover.htm"])

    def test_empty_inputs_do_not_publish_a_universe(self) -> None:
        bucket = _Bucket()
        result = universe.build(
            AS_OF,
            _Context(),
            assets=[],
            tickers={},
            sessions=_sessions(),
            bucket="data",
            client=bucket,
            ingest_enabled=lambda: True,
        )
        self.assertEqual(result["status"], "missing_inputs")
        self.assertNotIn(("data", _MEMBERS), bucket.objects)

    def test_the_price_date_is_the_last_session(self) -> None:
        _result, _bucket, memory = _build([_company("PASS")], on=date(2024, 6, 4))
        saved = memory.items[("UNIVERSE#2024-06-04", "META")]
        self.assertEqual(saved["asOf"], "2024-06-04")
        self.assertEqual(saved["lastPriceDate"], "2024-06-03")


def _weighted(start: str, end: str, value: int) -> dict[str, object]:
    return {
        "field": "weightedDilutedShares",
        "kind": "share",
        "tag": "WeightedAverageNumberOfDilutedSharesOutstanding",
        "start": start,
        "end": end,
        "value": value,
        "filed": "2024-05-01",
        "form": "10-Q",
    }


if __name__ == "__main__":
    unittest.main()
