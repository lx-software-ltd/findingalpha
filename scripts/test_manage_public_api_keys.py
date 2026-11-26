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
            args.plaintext_out = None
            shown = io.StringIO()
            with patch("sys.stdout", shown):
                keys.cmd_create(args)
            example = shown.getvalue()
            self.assertIn("Authorization: Bearer fapk_short", example)
            self.assertIn("/v1/partner/system/status", example)
            self.assertNotIn("x-api-key", example)
        self.assertEqual(stored["tier"], "admin")
        self.assertEqual(stored["gsi1pk"], "APIKEYS")
        self.assertTrue(str(stored["gsi1sk"]).endswith("#abc123abc123"))
        self.assertNotIn("scope", stored)
        self.assertTrue(stored["pk"].startswith("APIKEY#"))
        self.assertNotIn("fapk_short", stored["pk"])

    def test_workflow_encrypts_the_key_and_refuses_an_empty_passphrase(self) -> None:
        text = (ROOT / ".github" / "workflows" / "manage-api-keys.yml").read_text(encoding="utf-8")
        validate = (ROOT / "scripts" / "deploy" / "validate-api-key-inputs.sh").read_text(encoding="utf-8")
        create = (ROOT / "scripts" / "deploy" / "create-api-key.sh").read_text(encoding="utf-8")
        self.assertIn("PUBLIC_API_KEY_GPG_PASSPHRASE", text)
        self.assertIn("PUBLIC_API_KEY_GPG_PASSPHRASE is not set", validate)
        self.assertIn("cat key.asc", create)
        self.assertNotIn('cat "$KEY_FILE"', create)
        self.assertIn("secrets.AWS_ACCOUNT_ID", text)
        self.assertNotIn("vars.AWS_ACCOUNT_ID", text)
        self.assertIn("lx-software-ltd/actions/aws-oidc@", text)

    def test_set_scopes_replaces_the_list(self) -> None:
        table = type("Table", (), {})()
        updates: list[dict] = []
        item = {
            "pk": "APIKEY#digest",
            "sk": "META",
            "keyId": "abc123",
            "label": "monitor",
            "tier": "admin",
            "scopes": ["system"],
        }

        def update_item(**kwargs: object) -> None:
            updates.append(kwargs)

        table.update_item = update_item
        args = type("Args", (), {"key_id": "abc123", "scopes": "system,operate"})()
        printed = io.StringIO()
        with (
            patch.object(keys, "_table", return_value=table),
            patch.object(keys, "_matches", return_value=[item]),
            patch("sys.stdout", printed),
        ):
            keys.cmd_set_scopes(args)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["Key"], {"pk": "APIKEY#digest", "sk": "META"})
        self.assertEqual(updates[0]["UpdateExpression"], "SET scopes = :s")
        self.assertEqual(updates[0]["ExpressionAttributeValues"], {":s": ["operate", "system"]})
        text = printed.getvalue()
        self.assertIn("scopes system -> operate,system", text)
        self.assertIn("label='monitor'", text)
        self.assertIn("60 seconds", text)
        self.assertNotIn("APIKEY#", text)
        self.assertNotIn("digest", text)

    def test_set_scopes_rejects_an_unknown_scope_and_a_missing_key(self) -> None:
        with self.assertRaises(SystemExit) as unknown:
            keys.cmd_set_scopes(type("Args", (), {"key_id": "abc123", "scopes": "finance"})())
        self.assertIn("unknown scopes", str(unknown.exception))
        with (
            patch.object(keys, "_query_keys", return_value=[]),
            self.assertRaises(SystemExit) as missing,
        ):
            keys.cmd_set_scopes(type("Args", (), {"key_id": "missing", "scopes": "system,operate"})())
        self.assertIn("no API key", str(missing.exception))

    def test_set_scopes_refuses_a_scope_the_tier_would_drop(self) -> None:
        table = type("Table", (), {})()
        updates: list[dict] = []
        table.update_item = lambda **kwargs: updates.append(kwargs)
        disabled = {
            "pk": "APIKEY#digest",
            "sk": "META",
            "keyId": "abc123",
            "label": "monitor",
            "tier": "user",
            "scopes": ["research"],
        }
        with (
            patch.object(keys, "_table", return_value=table),
            patch.object(keys, "_matches", return_value=[disabled]),
            self.assertRaises(SystemExit) as disabled_tier,
        ):
            keys.cmd_set_scopes(type("Args", (), {"key_id": "abc123", "scopes": "research"})())
        self.assertIn("not enabled", str(disabled_tier.exception))
        limited = {**disabled, "tier": "admin", "scopes": ["system"]}
        with (
            patch.object(keys, "_table", return_value=table),
            patch.object(keys, "_matches", return_value=[limited]),
            patch.object(keys, "tier_record", return_value={"enabled": True, "scopes": ("system",)}),
            self.assertRaises(SystemExit) as refused,
        ):
            keys.cmd_set_scopes(type("Args", (), {"key_id": "abc123", "scopes": "system,operate"})())
        self.assertIn("cannot hold operate", str(refused.exception))
        self.assertEqual(updates, [])

    def test_workflow_can_replace_scopes_without_printing_a_key(self) -> None:
        text = (ROOT / ".github" / "workflows" / "manage-api-keys.yml").read_text(encoding="utf-8")
        validate = (ROOT / "scripts" / "deploy" / "validate-api-key-inputs.sh").read_text(encoding="utf-8")
        self.assertIn("\n          - set-scopes\n", text)
        self.assertIn("inputs.action == 'set-scopes'", text)
        self.assertIn('set-scopes --key-id "$KEY_ID" --scopes "$SCOPES"', text)
        self.assertIn("'key_id' and 'scopes' are required for action=set-scopes", validate)
        scopes = text[text.index("      scopes:\n") : text.index("      allow_write:\n")]
        self.assertNotIn("default:", scopes)
        self.assertIn("Empty on create means system", scopes)


if __name__ == "__main__":
    unittest.main()
