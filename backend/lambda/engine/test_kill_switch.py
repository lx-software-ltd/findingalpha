"""Kill switches fail closed."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import kill_switch


class KillSwitchTest(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("INGEST_ENABLED", None)

    def test_missing_environment_is_false(self) -> None:
        self.assertFalse(kill_switch.is_enabled("ingestEnabled", {"ingestEnabled": True}))

    def test_environment_without_a_row_is_false(self) -> None:
        os.environ["INGEST_ENABLED"] = "true"
        with patch.object(kill_switch, "_read_settings", return_value=None):
            self.assertFalse(kill_switch.is_enabled("ingestEnabled"))

    def test_row_without_the_attribute_is_false(self) -> None:
        os.environ["INGEST_ENABLED"] = "true"
        self.assertFalse(kill_switch.is_enabled("ingestEnabled", {}))

    def test_read_error_is_false(self) -> None:
        os.environ["INGEST_ENABLED"] = "true"
        with patch.object(kill_switch, "_read_settings", return_value=None):
            self.assertFalse(kill_switch.is_enabled("ingestEnabled"))

    def test_both_true_is_enabled(self) -> None:
        os.environ["INGEST_ENABLED"] = "true"
        self.assertTrue(kill_switch.is_enabled("ingestEnabled", {"ingestEnabled": True}))

    def test_false_string_is_off(self) -> None:
        os.environ["INGEST_ENABLED"] = "false"
        self.assertFalse(kill_switch.is_enabled("ingestEnabled", {"ingestEnabled": True}))


if __name__ == "__main__":
    unittest.main()
