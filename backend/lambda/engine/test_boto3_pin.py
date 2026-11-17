"""AdminApiFn and EngineFn bundle a boto3 that can call a managed knowledge base."""

from __future__ import annotations

import unittest
from pathlib import Path


class Boto3PinTest(unittest.TestCase):
    def test_requirements_pin_boto3_and_botocore_at_the_checked_release(self) -> None:
        text = (Path(__file__).resolve().parent / "requirements.txt").read_text()
        pins = [line.split("#", 1)[0].strip() for line in text.splitlines() if line.split("#", 1)[0].strip()]
        self.assertEqual(pins, ["boto3==1.44.3", "botocore==1.44.3"])


if __name__ == "__main__":
    unittest.main()
