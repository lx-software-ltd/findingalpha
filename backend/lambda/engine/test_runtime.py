"""The DynamoDB resource is created once, and not at import."""

from __future__ import annotations

import importlib
import unittest
from unittest.mock import patch

import runtime


class RuntimeTest(unittest.TestCase):
    def tearDown(self) -> None:
        runtime._ddb = None

    def test_import_does_not_create_a_client(self) -> None:
        with patch("boto3.resource") as resource:
            importlib.reload(runtime)
        resource.assert_not_called()
        self.assertIsNone(runtime._ddb)

    def test_one_resource_is_reused(self) -> None:
        runtime._ddb = None
        sentinel = object()
        with patch("runtime.boto3.resource", return_value=sentinel) as resource:
            self.assertIs(runtime.ddb(), sentinel)
            self.assertIs(runtime.ddb(), sentinel)
        resource.assert_called_once_with("dynamodb")


if __name__ == "__main__":
    unittest.main()
