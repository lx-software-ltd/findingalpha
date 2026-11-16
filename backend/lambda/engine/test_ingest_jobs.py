"""The ingest jobs keep a saved window and resume a universe build."""

from __future__ import annotations

import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

import ingest_jobs

DAY = date(2024, 6, 3)
FRIDAY = date(2024, 6, 7)
NOON = datetime(2024, 6, 4, 12, tzinfo=ingest_jobs.NEW_YORK)
HKT = ZoneInfo("Asia/Hong_Kong")
TUESDAY_OPEN = datetime(2024, 6, 4, 6, tzinfo=HKT)
SATURDAY_OPEN = datetime(2024, 6, 8, 6, tzinfo=HKT)
ASSET = {"symbol": "EXMPL", "exchange": "NYSE", "status": "active", "tradable": True, "marginable": True}
TICKERS = {"EXMPL": {"cik": "0000000001", "name": "Example Co"}}


class IngestJobsTest(unittest.TestCase):
    def test_a_resume_reads_a_parameter_block_kept_in_the_state_row(self) -> None:
        from unittest.mock import patch

        saved = {"symbols": ["EXMPL"], "start": "2016-01-01", "end": "2024-06-03"}
        with patch("store.get", return_value={"params": saved}) as loaded:
            found = ingest_jobs._params({"job": "backfill_prices", "paramsInState": True})
        self.assertEqual(found, saved)
        self.assertEqual(loaded.call_args.args, ("JOB#backfill_prices", "STATE"))
        self.assertEqual(ingest_jobs._params({"job": "backfill_prices"}), {})
        self.assertEqual(ingest_jobs._params({"params": {"symbols": ["EXMPL"]}}), {"symbols": ["EXMPL"]})

    def test_a_closed_session_does_no_work(self) -> None:
        def refuse(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("called")

        result = ingest_jobs.ingest_daily(
            {},
            None,
            now=NOON,
            sessions=[date(2024, 6, 4)],
            raw=refuse,
            actions=refuse,
            filings=refuse,
            headlines=refuse,
        )
        self.assertEqual(result["status"], "skipped_no_session")

    def test_the_daily_job_refreshes_corporate_actions(self) -> None:
        seen: dict[str, object] = {}

        def actions(start: date, end: date, sessions: list[date]) -> None:
            seen["window"] = (start, end, sessions)

        ingest_jobs.ingest_daily(
            {"params": {"day": "2024-06-03"}},
            None,
            sessions=[DAY],
            symbols=["EXMPL"],
            ciks=["0000000001"],
            raw=lambda *_args: None,
            actions=actions,
            filings=lambda *_args, **_kwargs: None,
            headlines=lambda *_args: None,
        )
        self.assertEqual(seen["window"], (date(2024, 5, 27), DAY, [DAY]))

    def test_the_hong_kong_open_takes_the_session_that_just_closed(self) -> None:
        seen: list[date] = []

        def raw(day: date, _symbols: list[str]) -> None:
            seen.append(day)

        def quiet(*_args: object, **_kwargs: object) -> dict[str, str]:
            return {"status": "done"}

        week = [date(2024, 6, 3), date(2024, 6, 4), date(2024, 6, 5), date(2024, 6, 6), FRIDAY]
        ingest_jobs.ingest_daily(
            {},
            None,
            now=TUESDAY_OPEN,
            sessions=week,
            symbols=["EXMPL"],
            ciks=["0000000001"],
            raw=raw,
            actions=quiet,
            filings=quiet,
            headlines=quiet,
        )
        ingest_jobs.ingest_daily(
            {},
            None,
            now=SATURDAY_OPEN,
            sessions=week,
            symbols=["EXMPL"],
            ciks=["0000000001"],
            raw=raw,
            actions=quiet,
            filings=quiet,
            headlines=quiet,
        )
        self.assertEqual(seen, [DAY, FRIDAY])

    def test_a_filings_timeout_does_not_fetch_news(self) -> None:
        def news(*_args: object) -> None:
            raise AssertionError("news")

        result = ingest_jobs.ingest_daily(
            {"params": {"day": "2024-06-03"}},
            None,
            sessions=[DAY],
            symbols=["EXMPL"],
            ciks=["0000000001"],
            raw=lambda *_args: None,
            actions=lambda *_args: None,
            filings=lambda *_args, **_kwargs: {"status": "running"},
            headlines=news,
        )
        self.assertEqual(result["status"], "running")

    def test_a_weekly_run_refuses_an_empty_asset_list(self) -> None:
        def build(*_args: object, **_kwargs: object) -> dict[str, str]:
            raise AssertionError("built")

        result = ingest_jobs.weekly_refresh(
            {},
            None,
            now=SATURDAY_OPEN,
            sessions=[FRIDAY],
            assets=[],
            tickers=TICKERS,
            build=build,
        )
        self.assertEqual(result["status"], "missing_inputs")

    def test_noon_in_hong_kong_takes_the_session_whose_index_is_out(self) -> None:
        seen: list[date] = []

        def raw(day: date, _symbols: list[str]) -> None:
            seen.append(day)

        def quiet(*_args: object, **_kwargs: object) -> dict[str, str]:
            return {"status": "done"}

        ingest_jobs.ingest_daily(
            {},
            None,
            now=datetime(2024, 1, 9, 12, tzinfo=HKT),
            sessions=[date(2024, 1, 8), date(2024, 1, 9)],
            symbols=["EXMPL"],
            ciks=["0000000001"],
            raw=raw,
            actions=quiet,
            filings=quiet,
            headlines=quiet,
        )
        ingest_jobs.ingest_daily(
            {},
            None,
            now=datetime(2024, 6, 4, 12, tzinfo=HKT),
            sessions=[date(2024, 6, 3), date(2024, 6, 4)],
            symbols=["EXMPL"],
            ciks=["0000000001"],
            raw=raw,
            actions=quiet,
            filings=quiet,
            headlines=quiet,
        )
        self.assertEqual(seen, [date(2024, 1, 8), date(2024, 6, 3)])

    def test_news_is_not_sent_the_price_symbols(self) -> None:
        seen: dict[str, list[str]] = {}

        def headlines(symbols: list[str], _day: date) -> None:
            seen["symbols"] = list(symbols)

        ingest_jobs.ingest_daily(
            {"params": {"day": "2024-06-03"}},
            None,
            sessions=[DAY],
            symbols=["EXMPL", "FUND"],
            ciks=["0000000001"],
            raw=lambda *_args: None,
            actions=lambda *_args: None,
            filings=lambda *_args, **_kwargs: {"status": "done"},
            headlines=headlines,
        )
        self.assertEqual(seen["symbols"], [])

    def test_coverage_and_adjusted_prices_use_the_members(self) -> None:
        seen: dict[str, object] = {}

        def build(_day: date, _context: object, **kwargs: object) -> dict[str, object]:
            exchanges = [row.get("exchange") for row in kwargs["assets"]]  # type: ignore[union-attr]
            self.assertIn("ARCA", exchanges)
            return {"status": "done", "symbols": ["EXMPL"], "ciks": ["0000000001"]}

        def adjusted(symbols: list[str], _start: str, _end: date, _context: object) -> dict[str, str]:
            seen["symbols"] = symbols
            return {"status": "done"}

        def coverage(ciks: list[str], _day: date) -> None:
            seen["ciks"] = ciks

        assets = [
            ASSET,
            {"symbol": "FUND", "exchange": "ARCA", "status": "active", "tradable": True, "marginable": True},
        ]
        ingest_jobs.weekly_refresh(
            {},
            None,
            now=SATURDAY_OPEN,
            sessions=[FRIDAY],
            assets=assets,
            tickers=TICKERS,
            build=build,
            adjusted=adjusted,
            coverage=coverage,
            note_build=lambda *_args: None,
        )
        self.assertEqual(seen["symbols"], ["EXMPL"])
        self.assertEqual(seen["ciks"], ["0000000001"])

    def test_adjusted_prices_add_a_name_that_was_liquid_and_still_has_a_cik(self) -> None:
        from unittest.mock import patch

        seen: dict[str, object] = {}

        def build(_day: date, _context: object, **_kwargs: object) -> dict[str, object]:
            return {"status": "done", "symbols": ["EXMPL"], "ciks": ["0000000001"]}

        def adjusted(symbols: list[str], _start: str, _end: date, _context: object) -> dict[str, str]:
            seen["symbols"] = symbols
            return {"status": "done"}

        tickers = {**TICKERS, "SMALL": {"cik": "0000000002", "name": "Small Co"}}
        with patch("monthly_stats._covered_symbols", return_value=({"SMALL", "GONE"}, False)):
            result = ingest_jobs.weekly_refresh(
                {},
                None,
                now=SATURDAY_OPEN,
                sessions=[FRIDAY],
                assets=[ASSET],
                tickers=tickers,
                build=build,
                adjusted=adjusted,
                coverage=lambda *_args: None,
                note_build=lambda *_args: None,
            )
        self.assertEqual(seen["symbols"], ["EXMPL", "SMALL"])
        self.assertEqual(result["adjustedScope"], 2)
        self.assertFalse(result["monthlyStatsMissing"])

    def test_a_stopped_coverage_report_leaves_the_adjusted_refresh(self) -> None:
        from unittest.mock import patch

        saved: dict[tuple[str, str], dict[str, object]] = {}

        def put(item: dict[str, object]) -> None:
            saved[(str(item["pk"]), str(item["sk"]))] = dict(item)

        def build(_day: date, _context: object, **_kwargs: object) -> dict[str, object]:
            return {"status": "done", "symbols": ["EXMPL"], "ciks": ["0000000001"]}

        def coverage(_ciks: list[str], _day: date) -> None:
            raise RuntimeError("stopped")

        with patch("store.put", put), self.assertRaises(RuntimeError):
            ingest_jobs.weekly_refresh(
                {},
                None,
                now=SATURDAY_OPEN,
                sessions=[FRIDAY],
                assets=[ASSET],
                tickers=TICKERS,
                build=build,
                coverage=coverage,
            )
        row = saved[("JOB#refresh_adjusted", "STATE")]
        self.assertEqual(row["status"], "running")
        self.assertGreater(str(row["leaseUntil"]), str(row["updatedAt"]))
        self.assertEqual(row["params"]["symbols"], ["EXMPL"])

    def test_this_run_drops_the_adjusted_lease_before_it_claims_the_job(self) -> None:
        from unittest.mock import patch

        order: list[str] = []

        def put(item: dict[str, object]) -> None:
            if item.get("pk") != "JOB#refresh_adjusted":
                return
            order.append("held" if "leaseUntil" in item else "open")

        def adjusted(_symbols: list[str], _start: str, _end: date, _context: object) -> dict[str, str]:
            order.append("claim")
            return {"status": "done"}

        def build(_day: date, _context: object, **_kwargs: object) -> dict[str, object]:
            return {"status": "done", "symbols": ["EXMPL"], "ciks": ["0000000001"]}

        with patch("store.put", put), patch.object(ingest_jobs, "_adjusted", adjusted):
            ingest_jobs.weekly_refresh(
                {},
                None,
                now=SATURDAY_OPEN,
                sessions=[FRIDAY],
                assets=[ASSET],
                tickers=TICKERS,
                build=build,
                coverage=lambda *_args: None,
            )
        self.assertEqual(order, ["held", "open", "claim"])

    def test_an_empty_member_list_still_starts_the_adjusted_refresh(self) -> None:
        from unittest.mock import patch

        seen: dict[str, list[str]] = {}

        def adjusted(symbols: list[str], _start: str, _end: date, _context: object) -> dict[str, str]:
            seen["symbols"] = symbols
            return {"status": "done"}

        with patch.object(ingest_jobs, "_adjusted", adjusted):
            missing = ingest_jobs.resume_adjusted({"params": {"symbols": []}}, None)
            started = ingest_jobs.resume_adjusted(
                {"params": {"symbols": [], "end": "2024-06-07"}},
                None,
            )
        self.assertEqual(missing["status"], "missing_inputs")
        self.assertEqual(started["status"], "done")
        self.assertEqual(seen["symbols"], [])

    def test_a_build_waiting_on_facts_is_not_started_again(self) -> None:
        from unittest.mock import patch

        noted: list[str] = []

        def build(_day: date, _context: object, **_kwargs: object) -> dict[str, object]:
            return {"status": "running", "pending": 2}

        def note(_day: date, status: str) -> None:
            noted.append(status)

        waiting = {"status": "running"}
        with patch("store.get", return_value=waiting):
            result = ingest_jobs.weekly_refresh(
                {},
                None,
                now=SATURDAY_OPEN,
                sessions=[FRIDAY],
                assets=[ASSET],
                tickers=TICKERS,
                build=build,
                note_build=note,
            )
        self.assertEqual(result["status"], "running")
        self.assertEqual(noted, [])
        waiting["status"] = "done"
        with patch("store.get", return_value=waiting):
            ingest_jobs.weekly_refresh(
                {},
                None,
                now=SATURDAY_OPEN,
                sessions=[FRIDAY],
                assets=[ASSET],
                tickers=TICKERS,
                build=build,
                note_build=note,
            )
        self.assertEqual(noted, ["running"])

    def test_a_resumed_backfill_keeps_the_saved_end(self) -> None:
        seen: dict[str, str] = {}

        def run(start: str, end: str, _sessions: list[date], _context: object, *, symbols: list[str]) -> dict[str, str]:
            seen["start"] = start
            seen["end"] = end
            seen["symbols"] = ",".join(symbols)
            return {"status": "running"}

        result = ingest_jobs.backfill_prices(
            {"params": {"start": "2016-01-01", "end": "2024-06-03", "symbols": ["EXMPL"]}},
            None,
            now=datetime(2024, 6, 10, 12, tzinfo=ingest_jobs.NEW_YORK),
            sessions=[DAY],
            run=run,
        )
        self.assertEqual(result["end"], "2024-06-03")
        self.assertEqual(seen["end"], "2024-06-03")
        self.assertEqual(seen["symbols"], "EXMPL")

    def test_an_unfinished_universe_refresh_keeps_its_status(self) -> None:
        result = ingest_jobs.resume_universe(
            {"params": {"ciks": ["0000000001"], "asOf": "2024-06-03"}},
            None,
            refresh=lambda *_args, **_kwargs: {"status": "running", "cursor": 1, "total": 4},
        )
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["refresh"]["cursor"], 1)
        self.assertNotIn("build", result)

    def test_a_finished_universe_refresh_builds_that_date(self) -> None:
        built: dict[str, object] = {}

        def refresh(_ciks: list[str], _context: object, *, job: str, as_of: str | None = None) -> dict[str, str]:
            self.assertEqual(job, ingest_jobs.UNIVERSE_REFRESH_JOB)
            self.assertEqual(as_of, "2024-06-03")
            return {"status": "done"}

        def build(day: str, _context: object, **kwargs: object) -> dict[str, object]:
            built["day"] = day
            built["assets"] = kwargs["assets"]
            return {"status": "done", "members": 1}

        result = ingest_jobs.resume_universe(
            {
                "params": {
                    "ciks": ["0000000001"],
                    "asOf": "2024-06-03",
                    "assets": [ASSET],
                    "tickers": TICKERS,
                    "sessions": ["2024-06-03"],
                }
            },
            None,
            refresh=refresh,
            build=build,
            adjusted=lambda *_args, **_kwargs: {"status": "done"},
            note_build=lambda *_args: None,
            coverage=lambda *_args: None,
        )
        self.assertEqual(built["day"], DAY)
        self.assertEqual(built["assets"], [ASSET])
        self.assertEqual(result["build"]["members"], 1)

    def test_a_resumed_build_loads_the_lists_the_facts_job_did_not_save(self) -> None:
        loaded = {"assets": 0}

        def refresh(*_args: object, **_kwargs: object) -> dict[str, str]:
            return {"status": "done"}

        def assets(include_inactive: bool) -> list[dict[str, object]]:
            self.assertFalse(include_inactive)
            loaded["assets"] += 1
            return [ASSET]

        def build(day: date, _context: object, **kwargs: object) -> dict[str, object]:
            self.assertEqual(day, DAY)
            self.assertEqual(kwargs["tickers"], TICKERS)
            self.assertEqual(kwargs["sessions"], [DAY])
            return {"status": "done", "members": 1}

        ingest_jobs.resume_universe(
            {"params": {"ciks": ["0000000001"], "asOf": "2024-06-03"}},
            None,
            refresh=refresh,
            build=build,
            load_assets=assets,
            load_tickers=lambda: TICKERS,
            load_sessions=lambda _start, _end: [DAY],
            adjusted=lambda *_args, **_kwargs: {"status": "done"},
            note_build=lambda *_args: None,
            coverage=lambda *_args: None,
        )
        self.assertEqual(loaded["assets"], 1)

    def test_tick_can_name_a_filings_refresh(self) -> None:
        import jobs_handler

        self.assertIs(jobs_handler.handler_for("ingest_filings_refresh#2024-06-03"), jobs_handler._filings)
        self.assertEqual(jobs_handler.switch_for("ingest_filings_refresh#2024-06-03"), "ingestEnabled")
        self.assertIs(jobs_handler.handler_for(ingest_jobs.ADJUSTED_JOB), jobs_handler._adjusted)
        self.assertIs(jobs_handler.handler_for(ingest_jobs.UNIVERSE_BUILD_JOB), jobs_handler._universe_build)


if __name__ == "__main__":
    unittest.main()
