"""Storage error classes and their log codes."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import config
from botocore.exceptions import BotoCoreError, ClientError, NoRegionError
from storage_errors import STORAGE_ERRORS, error_code


class StorageErrorsTest(unittest.TestCase):
    def test_every_storage_failure_is_covered(self) -> None:
        for error in (
            ClientError({"Error": {"Code": "ThrottlingException"}}, "GetItem"),
            BotoCoreError(),
            NoRegionError(),
            config.MissingSetting("RECORDS_TABLE_NAME"),
        ):
            with self.subTest(error=type(error).__name__):
                self.assertIsInstance(error, STORAGE_ERRORS)

    def test_a_programming_error_is_not_covered(self) -> None:
        self.assertNotIsInstance(KeyError("x"), STORAGE_ERRORS)
        self.assertNotIsInstance(TypeError("x"), STORAGE_ERRORS)

    def test_error_code(self) -> None:
        self.assertEqual(
            error_code(ClientError({"Error": {"Code": "ThrottlingException"}}, "GetItem")), "ThrottlingException"
        )
        self.assertEqual(error_code(NoRegionError()), "NoRegionError")
        self.assertEqual(error_code(config.MissingSetting("RECORDS_TABLE_NAME")), "MissingSetting")

    def test_table_names_require_a_value(self) -> None:
        for name, getter in (
            ("RECORDS_TABLE_NAME", config.records_table_name),
            ("AUDIT_LOG_TABLE_NAME", config.audit_table_name),
        ):
            with self.subTest(name=name):
                with patch.dict(os.environ, {name: ""}):
                    with self.assertRaises(config.MissingSetting):
                        getter()
                with patch.dict(os.environ, {name: "table"}):
                    self.assertEqual(getter(), "table")


if __name__ == "__main__":
    unittest.main()
