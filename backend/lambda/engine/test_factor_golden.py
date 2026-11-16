"""Five invented companies. The hand values below are the check against the functions."""

from __future__ import annotations

import importlib
import json
import math
import unittest
from pathlib import Path

import methodology


def _closes(spec: dict) -> list[float]:
    count = int(spec["count"])
    if "flat" in spec:
        return [float(spec["flat"])] * count
    pair = spec["alternate"]
    return [float(pair[index % len(pair)]) for index in range(count)]


def _hand(symbol: str) -> dict[str, float | None]:
    """Arithmetic for the fixture, written out here and not taken from the factor functions."""
    if symbol == "AAA":
        invested = 400 + 50 + 50 - 100
        rate = min(max(21 / 100, 0), 0.35)
        return {
            "roic": 100 * (1 - rate) / invested,
            "grossProfitability": 200 / 1000,
            "fcfMargin": (90 - 10) / 500,
            "accruals": (70 - 90) / 1000,
            "netDebtToEbitda": (40 + 10 - 20) / (100 + 15),
            "interestCoverage": 100 / 5,
            "earningsYield": 100 / 1030,
            "fcfYield": (90 - 10) / 1030,
            "freeCashFlow_ttm": 90 - 10,
            "momentum12_1": 0,
            "aboveSma200": 0,
            "volatility252": 0,
        }
    if symbol == "BBB":
        return {
            "roic": 200 * (1 - 40 / 200) / 500,
            "grossProfitability": (400 - 100) / 800,
            "fcfMargin": (50 - 20) / 400,
            "accruals": (40 - 50) / 800,
            "netDebtToEbitda": (0 + 0 - 10) / (200 + 0),
            "interestCoverage": 100,
            "earningsYield": 200 / 500,
            "fcfYield": (50 - 20) / 500,
            "freeCashFlow_ttm": 50 - 20,
            "momentum12_1": None,
            "aboveSma200": None,
            "volatility252": None,
        }
    if symbol == "CCC":
        return {
            "roic": 80 * (1 - 0.21) / 100,
            "grossProfitability": 50 / 200,
            "fcfMargin": (40 - 10) / 100,
            "accruals": (10 - 40) / 200,
            "netDebtToEbitda": (20 + 5 - 5) / 80,
            "interestCoverage": 80 / 8,
            "earningsYield": 80 / 200,
            "fcfYield": (40 - 10) / 200,
            "freeCashFlow_ttm": 40 - 10,
            "momentum12_1": 2 / 1 - 1,
            "aboveSma200": 1 / 1.5 - 1,
            "volatility252": math.log(2) * math.sqrt(252),
        }
    if symbol == "DDD":
        return {
            "roic": -5 * (1 - 0.21) / 100,
            "grossProfitability": 10 / 100,
            "fcfMargin": (5 - 1) / 20,
            "accruals": (-8 - 5) / 100,
            "netDebtToEbitda": None,
            "interestCoverage": 100,
            "earningsYield": None,
            "fcfYield": None,
            "freeCashFlow_ttm": 5 - 1,
            "momentum12_1": None,
            "aboveSma200": 0,
            "volatility252": None,
        }
    return {
        "roic": None,
        "grossProfitability": 20 / 100,
        "fcfMargin": None,
        "accruals": (5 - 10) / 100,
        "netDebtToEbitda": None,
        "interestCoverage": None,
        "earningsYield": None,
        "fcfYield": None,
        "freeCashFlow_ttm": None,
        "momentum12_1": None,
        "aboveSma200": None,
        "volatility252": None,
    }


class FactorGoldenTest(unittest.TestCase):
    def test_every_factor_matches_the_hand_values_and_the_golden_file(self) -> None:
        register = methodology.load()
        params = {item["id"]: item.get("parameters") or {} for item in register["factors"]}
        functions = {}
        for item in register["factors"]:
            module_name, func_name = str(item["implementation"]).split(".")
            functions[item["id"]] = getattr(importlib.import_module(module_name), func_name)
        golden = json.loads(
            Path(__file__).resolve().parent.joinpath("test_fixtures", "factor_golden.json").read_text(encoding="utf-8")
        )
        self.assertEqual([company["symbol"] for company in golden["companies"]], ["AAA", "BBB", "CCC", "DDD", "EEE"])
        for company in golden["companies"]:
            closes = _closes(company["price"])
            self.assertEqual(set(company["expected"]), set(functions))
            if company["symbol"] == "CCC":
                self.assertEqual(closes[0], 1)
                self.assertEqual(closes[-22], 2)
                self.assertEqual(closes[-1], 1)
                self.assertEqual(len(closes), 253)
            hand = _hand(company["symbol"])
            self.assertEqual(set(hand), set(company["expected"]))
            snapshot = dict(company["inputs"])
            snapshot["closes"] = closes
            for factor_id, expected in company["expected"].items():
                label = f"{company['symbol']} {factor_id}"
                got = functions[factor_id](snapshot, params[factor_id])
                if expected is None:
                    self.assertIsNone(hand[factor_id], label)
                    self.assertIsNone(got, label)
                else:
                    self.assertAlmostEqual(hand[factor_id], expected, delta=1e-12, msg=label)
                    self.assertAlmostEqual(got, expected, delta=1e-9, msg=label)


if __name__ == "__main__":
    unittest.main()
