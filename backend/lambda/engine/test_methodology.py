"""Register rules, the stable hash, and the factor catalogue."""

from __future__ import annotations

import importlib
import json
import unittest
from pathlib import Path

import methodology


def _doc() -> dict:
    return json.loads(Path(__file__).resolve().parent.joinpath("contracts", "methodology.json").read_text())


class MethodologyTest(unittest.TestCase):
    def test_the_bundled_register_is_valid_and_the_hash_ignores_key_order(self) -> None:
        doc = _doc()
        methodology.validate(doc)
        self.assertEqual(methodology.register_hash(doc), methodology.register_hash(json.loads(json.dumps(doc))))
        shuffled = {"factors": doc["factors"], "version": doc["version"], "screen": doc["screen"]}
        shuffled["universe"] = doc["universe"]
        shuffled["composite"] = doc["composite"]
        shuffled["fundamentals"] = doc["fundamentals"]
        shuffled["backtest"] = doc["backtest"]
        self.assertEqual(methodology.register_hash(doc), methodology.register_hash(shuffled))
        changed = json.loads(json.dumps(doc))
        changed["screen"]["shortlistSize"] = 61
        self.assertNotEqual(methodology.register_hash(doc), methodology.register_hash(changed))
        self.assertEqual(len(methodology.register_hash(doc)), 16)
        self.assertEqual(doc["version"], 6)
        self.assertEqual(doc["composite"]["winsoriseStdDevs"], 3)
        entries = [
            doc["universe"],
            doc["composite"],
            doc["screen"],
            doc["fundamentals"],
            doc["backtest"],
            *doc["factors"],
        ]
        self.assertEqual([item["status"] for item in entries].count("provisional"), 0)
        self.assertEqual([item["status"] for item in entries].count("cited"), 1)
        self.assertEqual([item["status"] for item in entries].count("owner_accepted"), 16)
        cited = [item["id"] for item in doc["factors"] if item["status"] == "cited"]
        self.assertEqual(cited, ["freeCashFlow_ttm"])

    def test_each_validation_error(self) -> None:
        doc = _doc()
        extra = dict(doc)
        extra["note"] = True
        with self.assertRaises(methodology.MethodologyError):
            methodology.validate(extra)
        broken = json.loads(json.dumps(doc))
        del broken["factors"][0]["formula"]
        with self.assertRaises(methodology.MethodologyError):
            methodology.validate(broken)
        duplicate = json.loads(json.dumps(doc))
        duplicate["factors"].append(dict(duplicate["factors"][0]))
        with self.assertRaises(methodology.MethodologyError):
            methodology.validate(duplicate)
        weights = json.loads(json.dumps(doc))
        weights["composite"]["groupWeights"] = {"quality": 0.5}
        with self.assertRaises(methodology.MethodologyError):
            methodology.validate(weights)
        status = json.loads(json.dumps(doc))
        status["factors"][0]["status"] = "draft"
        with self.assertRaises(methodology.MethodologyError):
            methodology.validate(status)
        cited = json.loads(json.dumps(doc))
        cited["factors"][0]["status"] = "cited"
        cited["factors"][0]["citation"] = None
        with self.assertRaises(methodology.MethodologyError):
            methodology.validate(cited)
        typo = json.loads(json.dumps(doc))
        typo["composite"]["groupWeights"] = {"qualty": 0.4, "value": 0.3, "trend": 0.3}
        with self.assertRaises(methodology.MethodologyError):
            methodology.validate(typo)
        share = json.loads(json.dumps(doc))
        share["composite"]["minFactorsPerGroupShare"] = 1.5
        with self.assertRaises(methodology.MethodologyError):
            methodology.validate(share)
        missing_param = json.loads(json.dumps(doc))
        interest = next(item for item in missing_param["factors"] if item["id"] == "interestCoverage")
        interest["parameters"] = {}
        with self.assertRaises(methodology.MethodologyError):
            methodology.validate(missing_param)
        unknown = json.loads(json.dumps(doc))
        unknown["factors"][0]["implementation"] = "factors_quality.missing"
        with self.assertRaises(methodology.MethodologyError):
            methodology.validate(unknown)
        unknown_field = json.loads(json.dumps(doc))
        unknown_field["screen"]["hardFilters"][0]["field"] = "notAField"
        with self.assertRaises(methodology.MethodologyError):
            methodology.validate(unknown_field)

    def test_load_returns_a_copy(self) -> None:
        first = methodology.load()
        first["screen"]["shortlistSize"] = 1
        self.assertEqual(methodology.load()["screen"]["shortlistSize"], 60)

    def test_accessors_read_the_bundled_register(self) -> None:
        self.assertEqual(methodology.parameter("roic", "defaultTaxRate"), 0.21)
        self.assertEqual(methodology.factor("roic")["group"], "quality")
        self.assertEqual(methodology.composite()["groupWeights"]["quality"], 0.4)
        self.assertEqual(methodology.screen()["shortlistSize"], 60)
        self.assertIn("NYSE", methodology.universe()["exchanges"])
        with self.assertRaises(methodology.MethodologyError):
            methodology.factor("missing")

    def test_parameter_reads_follow_get_and_an_alias(self) -> None:
        self.assertEqual(methodology._parameters_read(_reads_get), ["coverageCap"])
        self.assertEqual(methodology._parameters_read(_reads_alias), ["maxTaxRate"])
        self.assertEqual(methodology.unreported_debt(), "zero")

    def test_owner_accepted_needs_a_note_and_winsorise_std_devs_are_positive(self) -> None:
        missing = json.loads(json.dumps(_doc()))
        factor = missing["factors"][0]
        factor["status"] = "owner_accepted"
        factor.pop("acceptedNote", None)
        with self.assertRaisesRegex(methodology.MethodologyError, "accepted note"):
            methodology.validate(missing)
        long_note = json.loads(json.dumps(_doc()))
        long_note["factors"][0]["status"] = "owner_accepted"
        long_note["factors"][0]["acceptedNote"] = "n" * 301
        with self.assertRaisesRegex(methodology.MethodologyError, "accepted note"):
            methodology.validate(long_note)
        blank = json.loads(json.dumps(_doc()))
        blank["factors"][0]["status"] = "owner_accepted"
        blank["factors"][0]["acceptedNote"] = "   "
        with self.assertRaisesRegex(methodology.MethodologyError, "accepted note"):
            methodology.validate(blank)
        bad_citation = json.loads(json.dumps(_doc()))
        bad_citation["factors"][0]["status"] = "owner_accepted"
        bad_citation["factors"][0]["acceptedNote"] = "Kept, with the book's definition recorded."
        bad_citation["factors"][0]["citation"] = {"document": "Book.pdf", "locator": "1"}
        with self.assertRaisesRegex(methodology.MethodologyError, "citation"):
            methodology.validate(bad_citation)
        for value in (0, -1):
            non_positive = json.loads(json.dumps(_doc()))
            non_positive["composite"]["winsoriseStdDevs"] = value
            with self.assertRaisesRegex(methodology.MethodologyError, "winsoriseStdDevs"):
                methodology.validate(non_positive)

    def test_register_quotes_match_the_formula_notes(self) -> None:
        notes = Path(__file__).resolve().parents[3] / "docs" / "knowledge-base" / "formula-notes"
        cited = {
            "volatility252": "annualised-volatility.md",
            "freeCashFlow_ttm": "free-cash-flow.md",
            "roic": "roic.md",
            "interestCoverage": "interest-coverage.md",
            "earningsYield": "earnings-yield.md",
            "momentum12_1": "momentum.md",
        }
        doc = _doc()
        blocks = {item["id"]: item for item in doc["factors"]}
        blocks["composite"] = doc["composite"]
        cited["composite"] = "outlier-limits.md"
        for name, filename in cited.items():
            quote = " ".join(blocks[name]["citation"]["quote"].split())
            page = " ".join((notes / filename).read_text(encoding="utf-8").split())
            self.assertIn(quote, page, name)
        moving = " ".join((notes / "moving-average.md").read_text(encoding="utf-8").split())
        above = blocks["aboveSma200"]["citation"]["quote"]
        self.assertIn("When the market price breaks through the moving average line from below", moving)
        self.assertIn("it is taken as a bullish signal", moving)
        self.assertIn("as at point A in Figure 12.5", above)

    def test_every_implementation_is_callable_and_every_public_function_is_registered(self) -> None:
        named = {item["implementation"] for item in methodology.load()["factors"]}
        for path in named:
            module_name, func_name = path.split(".")
            module = importlib.import_module(module_name)
            self.assertTrue(callable(getattr(module, func_name)))
        for module_name in ("factors_quality", "factors_value", "factors_trend"):
            module = importlib.import_module(module_name)
            for name, value in vars(module).items():
                if name.startswith("_") or not callable(value):
                    continue
                self.assertIn(f"{module_name}.{name}", named)


def _reads_get(_snapshot: dict, settings: dict) -> object:
    return settings.get("coverageCap")


def _reads_alias(_snapshot: dict, params: dict) -> object:
    chosen = params
    return chosen["maxTaxRate"]


if __name__ == "__main__":
    unittest.main()
