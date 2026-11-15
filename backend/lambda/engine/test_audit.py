"""Audit writes survive a client-side AWS failure."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import audit
from botocore.exceptions import BotoCoreError


class AuditWriteTest(unittest.TestCase):
    def test_a_client_side_error_is_not_raised(self) -> None:
        os.environ["AUDIT_LOG_TABLE_NAME"] = "findingalpha-audit-log"
        with patch("runtime.ddb", side_effect=BotoCoreError()):
            audit.write("user-1", "settings.put", "SETTINGS#global", {})


if __name__ == "__main__":
    unittest.main()
