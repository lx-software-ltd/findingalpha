"""Key mint rules. No realistic key is written into the repository."""

from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "manage-public-api-keys.py"
    spec = importlib.util.spec_from_file_location("manage_public_api_keys", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


keys = _load()


class ManageKeysTest(unittest.TestCase):
    def test_only_the_admin_tier_can_be_minted(self) -> None:
        self.assertEqual(keys.require_tier("admin"), "admin")
        with self.assertRaises(SystemExit) as user:
            keys.require_tier("user")
        self.assertIn("tier user is not built yet", str(user.exception))
        with self.assertRaises(SystemExit):
            keys.require_tier("other")

    def test_default_scope_is_system_and_unknown_scopes_fail(self) -> None:
        self.assertEqual(keys._parse_scopes(None), ["system"])
        with self.assertRaises(SystemExit):
            keys._parse_scopes("finance")

    def test_create_writes_the_plaintext_to_a_file_and_not_to_stdout(self) -> None:
        table = type("Table", (), {})()
        stored: dict = {}

        def put_item(Item, ConditionExpression):
            del ConditionExpression
            stored.update(Item)

        table.put_item = put_item
        with (
            patch.object(keys, "_table", return_value=table),
            patch.object(keys.secrets, "token_urlsafe", return_value="short"),
            patch.object(keys.uuid, "uuid4") as uuid4,
        ):
            uuid4.return_value.hex = "abc123abc123"
            args = type(
                "Args",
                (),
                {
                    "tier": "admin",
                    "label": "monitor",
                    "scopes": "system",
                    "allow_write": False,
                    "expires_at": "2027-01-01",
                    "allowed_cidrs": None,
                    "plaintext_out": None,
                },
            )()
            with tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "key.txt"
                args.plaintext_out = str(target)
                printed = io.StringIO()
                with patch("sys.stdout", printed):
                    keys.cmd_create(args)
                self.assertEqual(target.read_text(encoding="utf-8"), "fapk_short\n")
                self.assertNotIn("fapk_short", printed.getvalue())
        self.assertEqual(stored["tier"], "admin")
        self.assertEqual(stored["gsi1pk"], "APIKEYS")
        self.assertTrue(str(stored["gsi1sk"]).endswith("#abc123abc123"))
        self.assertNotIn("scope", stored)
        self.assertTrue(stored["pk"].startswith("APIKEY#"))
        self.assertNotIn("fapk_short", stored["pk"])

    def test_workflow_encrypts_the_key_and_refuses_an_empty_passphrase(self) -> None:
        text = (ROOT / ".github" / "workflows" / "manage-api-keys.yml").read_text(encoding="utf-8")
        self.assertIn("PUBLIC_API_KEY_GPG_PASSPHRASE", text)
        self.assertIn("Set PUBLIC_API_KEY_GPG_PASSPHRASE", text)
        self.assertIn("cat key.asc", text)
        self.assertNotIn('cat "$KEY_FILE"', text)
        self.assertIn("secrets.AWS_ACCOUNT_ID || vars.AWS_ACCOUNT_ID", text)


if __name__ == "__main__":
    unittest.main()
