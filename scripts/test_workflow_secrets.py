#!/usr/bin/env python3
"""Public workflows must not print the account id or owner emails."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Printed in a public Actions log when stored as variables.
SECRET_NAMES = (
    "AWS_ACCOUNT_ID",
    "ADMIN_FEDERATED_EMAIL_ALLOWLIST",
    "ADMIN_BOOTSTRAP_EMAIL",
    "BRIEF_RECIPIENT_EMAIL",
    "SEC_CONTACT_EMAIL",
)

_EXPRESSION = re.compile(r"\$\{\{\s*([^}]+?)\s*\}\}")


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def _expressions(text: str) -> set[str]:
    """Return the insides of GitHub expressions, ignoring comments and prose."""
    return {match.group(1).strip() for match in _EXPRESSION.finditer(text)}


class WorkflowSecretTest(unittest.TestCase):
    def test_deploy_backend_reads_identifiers_from_secrets(self) -> None:
        text = _workflow("deploy-backend.yml")
        expressions = _expressions(text)
        for name in SECRET_NAMES:
            self.assertNotIn(f"vars.{name}", expressions, name)
            self.assertIn(f"secrets.{name}", expressions, name)
        self.assertIn("github.ref == 'refs/heads/main'", text)
        self.assertNotIn("$AWS_ACCOUNT_ID", text)

    def test_other_workflows_read_the_account_from_a_secret(self) -> None:
        for filename in ("deploy-admin-web.yml", "cdk-diff.yml"):
            text = _workflow(filename)
            expressions = _expressions(text)
            self.assertNotIn("vars.AWS_ACCOUNT_ID", expressions, filename)
            self.assertIn("secrets.AWS_ACCOUNT_ID", expressions, filename)
            self.assertIn("vars.AWS_REGION", expressions, filename)
            self.assertNotIn("$AWS_ACCOUNT_ID", text, filename)
        admin = _workflow("deploy-admin-web.yml")
        self.assertIn("github.ref == 'refs/heads/main'", admin)

    def test_cdk_diff_strips_the_account_from_the_summary(self) -> None:
        text = _workflow("cdk-diff.yml")
        self.assertIn('sed "s/${AWS_ACCOUNT_ID}/***/g"', text)
        self.assertNotIn("AWS_ACCOUNT_ID is unset", text)
