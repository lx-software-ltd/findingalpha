"""Hard filters and the shortlist."""

from __future__ import annotations

import unittest

import methodology
import screen


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


if __name__ == "__main__":
    unittest.main()
