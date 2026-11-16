"""Winsorising, sector z-scores, and the weighted composite."""

from __future__ import annotations

import math
import unittest

import composite
import methodology


def _factor(name: str, group: str, direction: str = "higher") -> dict:
    return {"id": name, "group": group, "direction": direction}


def _register(weights: dict[str, float] | None = None) -> dict:
    doc = methodology.load()
    copied = {
        "version": doc["version"],
        "universe": doc["universe"],
        "factors": [
            _factor("qualityA", "quality"),
            _factor("qualityB", "quality", "lower"),
            _factor("valueA", "value"),
            _factor("trendA", "trend"),
        ],
        "composite": dict(doc["composite"]),
        "screen": doc["screen"],
    }
    if weights is not None:
        copied["composite"]["groupWeights"] = weights
    copied["composite"]["minSectorSize"] = 4
    copied["composite"]["winsorisePercentiles"] = [0, 100]
    return copied


class CompositeTest(unittest.TestCase):
    def test_percentile_and_winsorise(self) -> None:
        self.assertEqual(composite.percentile([1, 2, 3, 4, 100], 0), 1)
        self.assertEqual(composite.percentile([1, 2, 3, 4, 100], 100), 100)
        self.assertEqual(composite.percentile([4, 1, 3], 50), 3)
        clipped = composite.winsorise([1, 2, 3, 4, 100], 0, 100)
        self.assertEqual(clipped, [1, 2, 3, 4, 100])
        inner = composite.winsorise([1, 2, 3, 4, 100], 50, 50)
        self.assertTrue(all(value == 3 for value in inner if value is not None))

    def test_a_small_sector_uses_the_universe_and_a_constant_is_zero(self) -> None:
        values = [1.0, 3.0, 5.0]
        scores = composite.zscores(values, ["a", "a", "b"], min_sector_size=3)
        mean = 3
        deviation = math.sqrt(((1 - 3) ** 2 + 0 + (5 - 3) ** 2) / 3)
        self.assertAlmostEqual(scores[0] or 0, (1 - mean) / deviation)
        rows = [{"sector": "a", "flat": 5}, {"sector": "b", "flat": 5}]
        self.assertEqual(composite.zscores_within_sector(rows, "flat", 1), [0.0, 0.0])

    def test_a_sector_of_three_falls_back_and_a_lower_factor_flips(self) -> None:
        register = _register()
        rows = [
            {"symbol": "A", "sector": "ind", "qualityA": 1, "qualityB": 1, "valueA": 1, "trendA": 1},
            {"symbol": "B", "sector": "ind", "qualityA": 2, "qualityB": 2, "valueA": 1, "trendA": 1},
            {"symbol": "C", "sector": "ind", "qualityA": 3, "qualityB": 3, "valueA": 1, "trendA": 1},
            {"symbol": "D", "sector": "fin", "qualityA": 100, "qualityB": 100, "valueA": 1, "trendA": 1},
        ]
        scored = composite.composite(rows, register)
        # Sector ind has three names and the minimum is four, so the z-score uses all four.
        universe = composite.zscores([1, 2, 3, 100], ["ind", "ind", "ind", "fin"], min_sector_size=4)
        self.assertAlmostEqual(scored[0]["z"]["qualityA"], universe[0])
        self.assertAlmostEqual(scored[0]["z"]["qualityB"], -universe[0])
        self.assertEqual(scored[0]["registerHash"], methodology.register_hash(register))

    def test_a_missing_group_is_none_and_the_weights_come_from_the_register(self) -> None:
        register = _register()
        row = {"symbol": "A", "sector": "ind", "qualityA": None, "qualityB": None, "valueA": 1, "trendA": 1}
        scored = composite.composite([row, {**row, "symbol": "B"}], register)
        self.assertIsNone(scored[0]["groups"]["quality"])
        self.assertIsNone(scored[0]["composite"])
        heavy = _register({"quality": 1, "value": 0, "trend": 0})
        light = _register({"quality": 0, "value": 1, "trend": 0})
        full = {"symbol": "A", "sector": "ind", "qualityA": 2, "qualityB": 2, "valueA": 8, "trendA": 1}
        other = {"symbol": "B", "sector": "ind", "qualityA": 4, "qualityB": 4, "valueA": 0, "trendA": 1}
        self.assertNotEqual(
            composite.composite([full, other], heavy)[0]["composite"],
            composite.composite([full, other], light)[0]["composite"],
        )

    def test_a_blank_sector_uses_the_universe(self) -> None:
        values = [1.0, 3.0, 10.0, 30.0]
        sectors = ["", "", "tech", "tech"]
        scores = composite.zscores(values, sectors, min_sector_size=2)
        universe = composite.zscores(values, ["a", "b", "c", "d"], min_sector_size=10)
        self.assertEqual(scores[0], universe[0])
        self.assertEqual(scores[1], universe[1])
        self.assertNotEqual(scores[2], universe[2])


if __name__ == "__main__":
    unittest.main()
