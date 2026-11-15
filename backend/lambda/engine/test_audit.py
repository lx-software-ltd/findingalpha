"""Audit writes log a warning when storage cannot be reached."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import audit
from botocore.exceptions import BotoCoreError, ClientError, NoRegionError


class AuditWriteTest(unittest.TestCase):
    def test_storage_errors_are_logged_not_raised(self) -> None:
        cases = {
            "InternalServerError": ClientError({"Error": {"Code": "InternalServerError"}}, "PutItem"),
            "BotoCoreError": BotoCoreError(),
            "NoRegionError": NoRegionError(),
        }
        for code, error in cases.items():
            with self.subTest(code=code):
                with (
                    patch.dict(os.environ, {"AUDIT_LOG_TABLE_NAME": "findingalpha-audit-log"}),
                    patch("runtime.ddb", side_effect=error),
                    patch("audit._log_event") as log,
                ):
                    audit.write("user-1", "settings.put", "SETTINGS#global", {})
                log.assert_called_once_with("warning", tag="audit_write_failed", action="settings.put", error=code)

    def test_a_missing_table_variable_is_logged_not_raised(self) -> None:
        with patch.dict(os.environ, {}), patch("runtime.ddb"), patch("audit._log_event") as log:
            os.environ.pop("AUDIT_LOG_TABLE_NAME", None)
            audit.write("user-1", "settings.put", "SETTINGS#global", {})
        log.assert_called_once_with("warning", tag="audit_write_failed", action="settings.put", error="MissingSetting")

    def test_no_actor_writes_nothing(self) -> None:
        with patch("runtime.ddb") as ddb:
            audit.write(None, "settings.put", "SETTINGS#global", {})
        ddb.assert_not_called()


if __name__ == "__main__":
    unittest.main()
