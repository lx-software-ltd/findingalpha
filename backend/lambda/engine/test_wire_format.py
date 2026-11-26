"""The shared wire-format cases, and the rule that tests go through the helper."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

import wire_format

_CASES = Path(__file__).resolve().parents[3] / "contracts" / "wire-format-cases.json"
_ENGINE = Path(__file__).resolve().parent


class WireFormatCasesTest(unittest.TestCase):
    def test_shared_cases_round_trip(self) -> None:
        document = json.loads(_CASES.read_text(encoding="utf-8"))
        contract = document["contract"]
        self.assertEqual(len(set(contract["renames"].values())), len(contract["renames"]))
        for case in document["cases"]:
            route = case.get("route", "")
            wire = wire_format.to_wire(case["value"], contract, route)
            self.assertEqual(wire, case["wire"], case["name"])
            self.assertEqual(wire_format.from_wire(wire, contract, route), case["value"], case["name"])

    def test_camel_and_snake_are_inverses(self) -> None:
        contract: dict[str, Any] = {
            "renames": {},
            "verbatimKeys": [],
            "mapFields": {},
            "opaqueFields": [],
            "rootMaps": {},
        }
        for key in ("s3Key", "top10Items", "portfolioSize", "shareFlows"):
            wire = next(iter(wire_format.to_wire({key: 1}, contract)))
            back = next(iter(wire_format.from_wire({wire: 1}, contract)))
            self.assertEqual(back, key)

    def test_only_the_helper_calls_the_http_handler(self) -> None:
        for path in _ENGINE.glob("test_*.py"):
            if path.name == "test_wire_format.py":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("api_handler.lambda_handler(", text, str(path.name))
