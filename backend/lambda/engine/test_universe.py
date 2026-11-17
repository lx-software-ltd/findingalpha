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
import universe_screen
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
    on_submissions: object = None,
    use_bucket_facts: bool = False,
    read_facts: object = None,
    listed: list[str] | None = None,
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
        if on_submissions is not None:
            on_submissions(cik)  # type: ignore[operator]
        return {"sic": sics.get(cik)}

    if use_bucket_facts:
        for company in companies:
            stored = company["facts"]
            if not isinstance(stored, list):
                continue
            s3io.put_jsonl_gz(
                "data",
                f"fundamentals/pit/cik={company['cik']}/facts.jsonl.gz",
                stored,  # type: ignore[arg-type]
                client=bucket,
            )
    shown = companies if listed is None else [company for company in companies if str(company["symbol"]) in set(listed)]
    assets = [_asset(str(company["symbol"])) for company in shown]
    tickers = {
        str(company["symbol"]): {"cik": company["cik"], "name": f"Example {company['symbol']}"} for company in shown
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
            read_facts=None if use_bucket_facts else read_facts or _counted_facts(facts, fact_reads),
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


def _liquid(symbol: str, cik: int) -> dict[str, object]:
    return {
        "symbol": symbol,
        "cik": _cik(cik),
        "name": f"Example {symbol}",
        "close": 10,
        "medianDollarVolume": 3_000_000,
    }


def _refuse_facts(_cik: str) -> None:
    raise AssertionError("facts")


def _collect(companies: list[dict[str, object]], bucket: _Bucket, **kwargs: object) -> dict[str, object]:
    return universe_screen.collect(  # type: ignore[return-value]
        companies,  # type: ignore[arg-type]
        AS_OF,
        universe.load_rules(),
        kwargs.get("context"),
        facts_of=kwargs["facts_of"],  # type: ignore[arg-type]
        probe=kwargs.get("probe"),  # type: ignore[arg-type]
        subs_of=lambda cik: {"sic": "7372"},
        cover_of=lambda _cik, _day: None,
        bucket="data",
        client=bucket,
    )


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
        stored = s3io.get_json("data", f"reference/shares/cik={_cik(1)}.json", client=bucket)
        self.assertEqual(stored["attempts"]["0000000001-24-000001"]["filed"], "2024-04-24")

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

    def test_a_company_file_is_dropped_before_the_next_one_is_read(self) -> None:
        import gc
        import weakref

        class Rows(list[dict[str, object]]):
            """A list that can be watched after the build releases it."""

        companies = [_company("PASS", cik=1), _company("ALSO", cik=2)]
        source = {str(company["cik"]): company["facts"] for company in companies}
        held: list[weakref.ReferenceType[Rows]] = []

        def read(cik: str) -> Rows:
            if held:
                self.assertIsNone(held[-1]())
            rows = Rows(dict(row) for row in source[cik])  # type: ignore[union-attr]
            held.append(weakref.ref(rows))
            return rows

        _build(companies, read_facts=read)
        gc.collect()
        self.assertEqual(len(held), 2)
        self.assertTrue(all(ref() is None for ref in held))

    def test_facts_stop_before_the_next_company_and_the_next_run_continues(self) -> None:
        clock = {"open": True}
        first_reads: list[str] = []
        second_reads: list[str] = []
        bucket = _Bucket()
        memory = _Memory()

        class Clock:
            def get_remaining_time_in_millis(self) -> int:
                return 900_000 if clock["open"] else 60_000

        def saw(_cik: str) -> None:
            clock["open"] = False

        stopped, _bucket, _memory = _build(
            [_company("PASS", cik=1), _company("ALSO", cik=2)],
            bucket=bucket,
            memory=memory,
            fact_reads=first_reads,
            context=Clock(),
            on_submissions=saw,
        )
        progress = s3io.get_json("data", "universe/date=2024-06-03/build.json", client=bucket)
        self.assertEqual(stopped["status"], "running")
        self.assertEqual(first_reads, [_cik(1)])
        self.assertEqual(progress["cursor"], 1)
        self.assertEqual(_symbols(bucket), [])

        finished, _bucket, _memory = _build(
            [_company("PASS", cik=1), _company("ALSO", cik=2)],
            bucket=bucket,
            memory=memory,
            fact_reads=second_reads,
        )
        self.assertEqual(finished["status"], "done")
        self.assertEqual(second_reads, [_cik(2)])
        self.assertEqual(_symbols(bucket), ["ALSO", "PASS"])
        kept = s3io.get_json("data", "universe/date=2024-06-03/build.json", client=bucket)
        self.assertEqual(kept["phase"], "written")
        stored = list(s3io.get_jsonl_gz("data", _MEMBERS, client=bucket))
        self.assertEqual([row["marketCap"] for row in stored], [SHARES * 10, SHARES * 10])
        third_reads: list[str] = []
        again, _bucket, _memory = _build(
            [_company("PASS", cik=1), _company("ALSO", cik=2)],
            bucket=bucket,
            memory=memory,
            fact_reads=third_reads,
        )
        self.assertEqual(third_reads, [])
        self.assertEqual(again["status"], "done")
        self.assertEqual(again["members"], finished["members"])

    def test_a_missing_company_file_is_not_downloaded(self) -> None:
        def download(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
            raise AssertionError("downloaded")

        def refresh(ciks: list[str], _context: object) -> dict[str, object]:
            self.assertEqual(ciks, [_cik(1)])
            return {"status": "running"}

        with patch("s3io.get_jsonl_gz", side_effect=download):
            result, bucket, _memory = _build(
                [_company("NEED", facts=None)],
                refresh=refresh,
                bucket=_Bucket(),
                use_bucket_facts=True,
            )
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["pending"], 1)
        self.assertNotIn(("data", _MEMBERS), bucket.objects)

    def test_a_stored_company_file_is_read_once(self) -> None:
        calls: list[str] = []
        real = s3io.get_jsonl_gz

        def wrapped(bucket: str, key: str, *, client: object = None) -> object:
            calls.append(key)
            return real(bucket, key, client=client)

        with patch("s3io.get_jsonl_gz", side_effect=wrapped):
            result, _bucket, _memory = _build([_company("PASS")], use_bucket_facts=True)
        self.assertEqual(result["members"], 1)
        self.assertEqual(calls, [f"fundamentals/pit/cik={_cik(1)}/facts.jsonl.gz"])

    def test_the_price_date_is_the_last_session(self) -> None:
        _result, _bucket, memory = _build([_company("PASS")], on=date(2024, 6, 4))
        saved = memory.items[("UNIVERSE#2024-06-04", "META")]
        self.assertEqual(saved["asOf"], "2024-06-04")
        self.assertEqual(saved["lastPriceDate"], "2024-06-03")

    def test_a_short_clock_after_the_screen_does_not_write_members(self) -> None:
        reads: list[str] = []

        class Clock:
            def __init__(self) -> None:
                self.calls = 0

            def get_remaining_time_in_millis(self) -> int:
                self.calls += 1
                return 60_000 if self.calls >= 4 else 900_000

        stopped, bucket, memory = _build([_company("PASS")], fact_reads=reads, context=Clock())
        progress = s3io.get_json("data", "universe/date=2024-06-03/build.json", client=bucket)
        self.assertEqual(stopped["status"], "running")
        self.assertEqual(reads, [_cik(1)])
        self.assertEqual(_symbols(bucket), [])
        self.assertEqual(progress["phase"], "qualify")
        self.assertEqual(progress["cursor"], 1)
        self.assertEqual(progress["companies"][0]["cik"], _cik(1))
        again: list[str] = []
        finished, bucket, _memory = _build([_company("PASS")], bucket=bucket, memory=memory, fact_reads=again)
        self.assertEqual(again, [])
        self.assertEqual(finished["status"], "done")
        self.assertEqual(_symbols(bucket), ["PASS"])

    def test_a_changed_company_list_keeps_the_saved_screen(self) -> None:
        clock = {"open": True}
        first_reads: list[str] = []
        second_reads: list[str] = []
        bucket = _Bucket()
        memory = _Memory()

        class Clock:
            def get_remaining_time_in_millis(self) -> int:
                return 900_000 if clock["open"] else 60_000

        stopped, _bucket, _memory = _build(
            [_company("PASS", cik=1), _company("ALSO", cik=2)],
            bucket=bucket,
            memory=memory,
            fact_reads=first_reads,
            context=Clock(),
            on_submissions=lambda _cik: clock.__setitem__("open", False),
        )
        self.assertEqual(stopped["status"], "running")
        self.assertEqual(first_reads, [_cik(1)])
        finished, bucket, _memory = _build(
            [_company("PASS", cik=1), _company("ALSO", cik=2)],
            bucket=bucket,
            memory=memory,
            fact_reads=second_reads,
            listed=["PASS"],
        )
        self.assertEqual(second_reads, [_cik(2)])
        self.assertEqual(finished["status"], "done")
        self.assertEqual(_symbols(bucket), ["ALSO", "PASS"])

    def test_a_checkpoint_is_written_every_batch(self) -> None:
        snaps: list[object] = []

        def read(cik: str) -> object:
            key = ("data", "universe/date=2024-06-03/build.json")
            snaps.append(s3io.get_json("data", key[1], client=bucket) if key in bucket.objects else None)
            reads.append(cik)
            return facts[cik]

        reads: list[str] = []
        companies = [_company("DROP", facts=[]), _company("PASS", cik=2), _company("ALSO", cik=3)]
        facts = {str(company["cik"]): company["facts"] for company in companies}
        bucket = _Bucket()
        with patch.object(universe_screen, "_BATCH", 1):
            _build(companies, bucket=bucket, read_facts=read)
        self.assertEqual(reads, [_cik(1), _cik(2), _cik(3)])
        self.assertEqual(snaps[1]["cursor"], 1)  # type: ignore[index]
        self.assertEqual(snaps[1]["prepared"], [])  # type: ignore[index]
        self.assertEqual(snaps[2]["cursor"], 2)  # type: ignore[index]
        self.assertEqual(len(snaps[2]["prepared"]), 1)  # type: ignore[index]

    def test_the_exists_scan_stops_and_the_next_run_continues(self) -> None:
        probes: list[str] = []

        class Clock:
            def get_remaining_time_in_millis(self) -> int:
                return 60_000 if probes else 900_000

        def probe(cik: str) -> bool:
            probes.append(cik)
            return False

        companies = [_liquid("ONE", 1), _liquid("TWO", 2), _liquid("THREE", 3)]
        bucket = _Bucket()
        first = _collect(companies, bucket, probe=probe, context=Clock(), facts_of=_refuse_facts)
        progress = s3io.get_json("data", "universe/date=2024-06-03/build.json", client=bucket)
        self.assertEqual(first["status"], "running")
        self.assertEqual(probes, [_cik(1)])
        self.assertEqual(progress["phase"], "exists")
        self.assertEqual(progress["cursor"], 1)
        self.assertEqual(progress["missing"], [_cik(1)])
        self.assertEqual([row["symbol"] for row in progress["companies"]], ["ONE", "TWO", "THREE"])
        later: list[str] = []
        second = _collect(
            companies,
            bucket,
            probe=lambda cik: later.append(cik) or False,
            context=_Context(),
            facts_of=_refuse_facts,
        )
        self.assertEqual(later, [_cik(2), _cik(3)])
        self.assertEqual(second["status"], "refresh")
        self.assertEqual(second["missing"], [_cik(1), _cik(2), _cik(3)])

    def test_the_exists_scan_checkpoints_each_batch(self) -> None:
        seen: list[str] = []
        bucket = _Bucket()

        def probe(cik: str) -> bool:
            seen.append(cik)
            if len(seen) == 3:
                progress = s3io.get_json("data", "universe/date=2024-06-03/build.json", client=bucket)
                snaps.append(progress["cursor"])
            return True

        snaps: list[int] = []
        companies = [_liquid("ONE", 1), _liquid("TWO", 2), _liquid("THREE", 3)]
        with patch.object(universe_screen, "_BATCH", 2):
            _collect(companies, bucket, probe=probe, context=_Context(), facts_of=lambda _cik: [])
        self.assertEqual(snaps, [2])

    def test_a_damaged_progress_row_starts_the_screen_again(self) -> None:
        companies = [_liquid("ONE", 1), _liquid("TWO", 2)]
        bucket = _Bucket()
        universe_data.write_build_progress(
            AS_OF,
            {
                "phase": "qualify",
                "cursor": 9,
                "ciks": [_cik(1), _cik(2)],
                "companies": companies,
                "missing": [],
                "counts": {},
                "prepared": [{}],
                "funnel": {},
            },
            "data",
            bucket,
        )
        reads: list[str] = []
        result = _collect(
            companies,
            bucket,
            probe=None,
            context=_Context(),
            facts_of=lambda cik: reads.append(cik) or _history(SHARES),
        )
        self.assertEqual(reads, [_cik(1), _cik(2)])
        self.assertEqual(result["status"], "ready")

    def test_a_missing_file_does_not_download_the_ones_after_it(self) -> None:
        companies = [_liquid("ONE", 1), _liquid("TWO", 2)]
        bucket = _Bucket()
        universe_data.write_build_progress(
            AS_OF,
            {
                "phase": "qualify",
                "cursor": 0,
                "ciks": [_cik(1), _cik(2)],
                "companies": companies,
                "missing": [],
                "counts": {},
                "prepared": [],
                "funnel": {},
            },
            "data",
            bucket,
        )
        reads: list[str] = []
        probes: list[str] = []

        def facts(cik: str) -> list[dict[str, object]] | None:
            reads.append(cik)
            return None if cik == _cik(1) else _history(SHARES)

        result = _collect(
            companies,
            bucket,
            probe=lambda cik: probes.append(cik) or False,
            context=_Context(),
            facts_of=facts,
        )
        self.assertEqual(reads, [_cik(1)])
        self.assertEqual(probes, [_cik(2)])
        self.assertEqual(result["status"], "refresh")
        self.assertEqual(result["missing"], [_cik(1), _cik(2)])

    def test_a_short_clock_during_the_rules_retries_that_company(self) -> None:
        reads: list[str] = []

        class Clock:
            def get_remaining_time_in_millis(self) -> int:
                return 60_000 if reads else 900_000

        stopped, bucket, memory = _build(
            [_company("PASS", cik=1), _company("ALSO", cik=2)],
            fact_reads=reads,
            context=Clock(),
        )
        progress = s3io.get_json("data", "universe/date=2024-06-03/build.json", client=bucket)
        self.assertEqual(stopped["status"], "running")
        self.assertEqual(reads, [_cik(1)])
        self.assertEqual(progress["cursor"], 0)
        again: list[str] = []
        finished, bucket, _memory = _build(
            [_company("PASS", cik=1), _company("ALSO", cik=2)],
            bucket=bucket,
            memory=memory,
            fact_reads=again,
        )
        self.assertEqual(again, [_cik(1), _cik(2)])
        self.assertEqual(finished["status"], "done")
        self.assertEqual(_symbols(bucket), ["ALSO", "PASS"])

    def test_a_short_clock_before_the_cover_does_not_download_it(self) -> None:
        covers: list[str] = []

        class Clock:
            def __init__(self) -> None:
                self.calls = 0

            def get_remaining_time_in_millis(self) -> int:
                self.calls += 1
                return 60_000 if self.calls >= 4 else 900_000

        years = ("2021-12-31", "2022-12-31", "2023-12-31")
        rows = [_annual(end, "2024-02-01" if end == years[-1] else f"{int(end[:4]) + 1}-02-15") for end in years]
        seen: list[str] = []
        stopped, bucket, memory = _build(
            [_company("PASS", facts=rows)],
            context=Clock(),
            on_submissions=lambda cik: seen.append(cik),
            read_cover=lambda cik, _day: covers.append(cik),
        )
        self.assertEqual(stopped["status"], "running")
        self.assertEqual(seen, [_cik(1)])
        self.assertEqual(covers, [])
        finished, bucket, _memory = _build(
            [_company("PASS", facts=rows)],
            bucket=bucket,
            memory=memory,
            read_cover=lambda cik, _day: covers.append(cik),
        )
        self.assertEqual(covers, [_cik(1)])
        self.assertEqual(finished["status"], "done")
        self.assertEqual(_symbols(bucket), [])


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
