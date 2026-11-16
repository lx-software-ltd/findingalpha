"""Five invented companies. Expected values were calculated independently of these functions."""

from __future__ import annotations

import importlib
import json
import unittest
from pathlib import Path

import methodology


class FactorGoldenTest(unittest.TestCase):
    def test_every_factor_matches_the_golden_file(self) -> None:
        register = methodology.load()
        params = {item["id"]: item.get("parameters") or {} for item in register["factors"]}
        functions = {}
        for item in register["factors"]:
            module_name, func_name = str(item["implementation"]).split(".")
            functions[item["id"]] = getattr(importlib.import_module(module_name), func_name)
        golden = json.loads(
            Path(__file__).resolve().parent.joinpath("test_fixtures", "factor_golden.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(golden["companies"]), 5)
        for company in golden["companies"]:
            self.assertEqual(set(company["expected"]), set(functions))
            for factor_id, expected in company["expected"].items():
                got = functions[factor_id](company["snapshot"], params[factor_id])
                label = f"{company['symbol']} {factor_id}"
                if expected is None:
                    self.assertIsNone(got, label)
                else:
                    self.assertAlmostEqual(got, expected, delta=1e-9, msg=label)


if __name__ == "__main__":
    unittest.main()
