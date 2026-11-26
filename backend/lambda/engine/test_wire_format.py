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

    def test_contract_keeps_ticker_and_date_keys_in_a_data_map(self) -> None:
        contract = wire_format.load_contract()
        for name in (
            "done",
            "sectors",
            "shareSources",
            "flows",
            "stocks",
            "shareFlows",
            "groups",
            "factors",
            "z",
        ):
            self.assertGreaterEqual(contract["mapFields"][name], 1, name)
        payload = {
            "shareSources": {
                "600519.SH": 1,
                "2024-01-15": 2,
                "coverClasses": 3,
            }
        }
        wire = wire_format.to_wire(payload, contract)
        self.assertEqual(wire, {"share_sources": payload["shareSources"]})
        self.assertEqual(wire_format.from_wire(wire, contract), payload)
        self.assertEqual(wire_format.from_wire(payload, contract)["shareSources"], payload["shareSources"])

    def test_unprotected_data_key_is_renamed(self) -> None:
        contract = wire_format.load_contract()
        wire = wire_format.to_wire({"coverClasses": 1, "600519.SH": 2, "2024-01-15": 3}, contract)
        self.assertEqual(wire["600519.SH"], 2)
        self.assertEqual(wire["2024-01-15"], 3)
        self.assertEqual(wire["cover_classes"], 1)
        self.assertNotIn("coverClasses", wire)

    def test_camel_case_object_round_trips_through_to_wire_from_wire(self) -> None:
        contract = wire_format.load_contract()
        camel = {"portfolioSize": 12, "lastPriceDate": "2024-01-15", "nested": {"closePrice": 1}}
        wire = wire_format.to_wire(wire_format.from_wire(camel, contract), contract)
        self.assertEqual(wire_format.from_wire(wire, contract), camel)
        self.assertEqual(wire_format.to_wire(wire_format.from_wire(wire, contract), contract), wire)

    def test_only_the_helper_calls_the_http_handler(self) -> None:
        for path in _ENGINE.glob("test_*.py"):
            if path.name == "test_wire_format.py":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("api_handler.lambda_handler(", text, str(path.name))
