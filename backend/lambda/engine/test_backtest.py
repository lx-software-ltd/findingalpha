"""A small invented market for the screen replay."""

from __future__ import annotations

import unittest

import backtest
import methodology

_ENDS = ["2017-01-31", "2017-02-28", "2017-03-31"]
_SESSIONS = ["2017-01-31", "2017-02-01", "2017-02-15", "2017-02-28", "2017-03-01", "2017-03-31", "2017-04-03"]


class BacktestTest(unittest.TestCase):
    def test_two_months_match_the_hand_equity_curve(self) -> None:
        register = methodology.load()
        played = backtest.replay(
            _ENDS,
            {},
            _prices(),
            _SESSIONS,
            register,
            holdings_by_month={
                "2017-01-31": [_holding("AAA"), _holding("BBB")],
                "2017-02-28": [_holding("AAA"), _holding("BBB")],
            },
        )
        self.assertAlmostEqual(played["curves"]["strategy"][1], 108.3, delta=1e-9)
        self.assertAlmostEqual(played["curves"]["strategy"][2], 117.5055, delta=1e-9)
        self.assertEqual(played["periods"][0]["turnover"], 1)
        self.assertEqual(played["periods"][1]["turnover"], 0)

    def test_withholding_lowers_only_a_dividend_payer(self) -> None:
        payer_net = backtest.holding_return(110, 121, 100, 100, 0.30)
        payer_gross = backtest.holding_return(110, 121, 100, 100, 0)
        self.assertAlmostEqual(payer_net, 0.07)
        self.assertLess(payer_net, payer_gross)
        self.assertAlmostEqual(
            backtest.holding_return(55, 60.5, 55, 60.5, 0.30),
            backtest.holding_return(55, 60.5, 55, 60.5, 0),
        )

    def test_the_first_month_pays_a_round_trip_and_an_unchanged_book_pays_nothing(self) -> None:
        self.assertAlmostEqual(backtest.period_return([0.1, 0.1], 1, 10), 0.1 - 0.002)
        self.assertEqual(backtest.one_way_turnover({"AAA": 0.5, "BBB": 0.5}, {"AAA": 0.5, "BBB": 0.5}), 0)
        self.assertAlmostEqual(backtest.period_return([0.1], 0, 10), 0.1)

    def test_the_sector_cap_skips_the_sixth_name(self) -> None:
        ranked = [{"symbol": f"S{index}", "sector": "tech", "rank": index} for index in range(1, 7)]
        chosen = backtest.choose(ranked, 20, 5)
        self.assertEqual([row["symbol"] for row in chosen], ["S1", "S2", "S3", "S4", "S5"])

    def test_a_delisted_name_uses_its_last_price_and_is_counted(self) -> None:
        series = [
            {"date": "2017-02-01", "adj": 100, "split": 100},
            {"date": "2017-02-15", "adj": 90, "split": 90},
        ]
        value, used = backtest.name_return(series, "2017-02-01", "2017-03-01", 0)
        self.assertEqual(used, 1)
        self.assertAlmostEqual(value or 0, -0.1)

    def test_a_filing_the_day_after_month_end_ranks_from_the_next_month(self) -> None:
        register = methodology.load()
        pit = [
            {
                "field": "operatingIncome",
                "kind": "flow",
                "start": "2016-01-01",
                "end": "2016-12-31",
                "filed": "2017-02-01",
                "value": 40,
            }
        ]
        built = backtest.rows_for_symbol("LATE", ["2017-01-31", "2017-02-28"], pit, [], 10, 10, None, register)
        self.assertIsNone(built[0]["operatingIncome_ttm"])
        self.assertEqual(built[1]["operatingIncome_ttm"], 40)
        january = backtest.replay(
            ["2017-01-31", "2017-02-28"],
            {"2017-01-31": [_scored("STABLE", 1, income=40), _scored("LATE", 2, income=None)]},
            _prices(),
            _SESSIONS,
            register,
            portfolio_size=10,
        )
        february = backtest.replay(
            ["2017-02-28", "2017-03-31"],
            {"2017-02-28": [_scored("STABLE", 1, income=40), _scored("LATE", 2, income=40)]},
            _prices(),
            _SESSIONS,
            register,
            portfolio_size=10,
        )
        self.assertEqual(january["periods"][0]["holdings"], ["STABLE"])
        self.assertEqual(february["periods"][0]["holdings"], ["LATE", "STABLE"])

    def test_a_cheap_or_excluded_name_is_out_and_the_size_stays_in_range(self) -> None:
        rules = methodology.load()["universe"]
        cheap = {"close": 1, "medianDollarVolume": 10**9, "marketCap": 10**10, "historyYears": 5, "sic": "1000"}
        bank = {"close": 20, "medianDollarVolume": 10**9, "marketCap": 10**10, "historyYears": 5, "sic": "6200"}
        kept = {"close": 20, "medianDollarVolume": 10**9, "marketCap": 10**10, "historyYears": 5, "sic": "1000"}
        self.assertFalse(backtest.eligible(cheap, rules))
        self.assertFalse(backtest.eligible(bank, rules))
        self.assertTrue(backtest.eligible(kept, rules))
        register = methodology.load()
        self.assertEqual(backtest.portfolio_size(None, register), 20)
        self.assertEqual(backtest.portfolio_size(15, register), 15)
        self.assertIsNone(backtest.portfolio_size(9, register))
        self.assertIsNone(backtest.portfolio_size(True, register))


def _holding(symbol: str) -> dict:
    return {"symbol": symbol, "weight": 0.5, "sector": "tech"}


def _bar(day: str, price: float, split: float | None = None) -> dict:
    return {"date": day, "adj": price, "split": price if split is None else split}


def _prices() -> dict[str, list[dict]]:
    flat = [_bar(day, 100) for day in ("2017-02-01", "2017-03-01", "2017-04-03")]
    return {
        "AAA": [_bar("2017-02-01", 100), _bar("2017-03-01", 110, 100), _bar("2017-04-03", 121, 100)],
        "BBB": [_bar("2017-02-01", 50), _bar("2017-03-01", 55), _bar("2017-04-03", 60.5)],
        "SPY": flat,
        "BIL": flat,
        "STABLE": flat,
        "LATE": flat,
    }


def _scored(symbol: str, level: int, *, income: float | None) -> dict:
    register = methodology.load()
    weights = register["composite"]["groupWeights"]
    row: dict = {
        "symbol": symbol,
        "sector": "tech",
        "operatingIncome_ttm": income,
        "freeCashFlow_ttm": None if income is None else 4,
        "longTermDebt": 0,
        "shortTermDebt": 0,
        "cash": 1,
    }
    for factor in register["factors"]:
        if factor["id"] in {"netDebtToEbitda", "accruals"}:
            row[factor["id"]] = None if income is None else 1
        elif factor["group"] in weights or factor["group"] == "reported":
            row[factor["id"]] = None if income is None else level
    return row


if __name__ == "__main__":
    unittest.main()
