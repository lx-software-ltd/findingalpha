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


def _accepts_secret_or_variable(expressions: set[str], name: str) -> bool:
    """A secret wins. The variable is only the fallback, never the only source."""
    allowed = {
        f"secrets.{name}",
        f"secrets.{name} || vars.{name}",
        f"secrets.{name} == '' && vars.{name} != ''",
    }
    hits = [expr for expr in expressions if f"secrets.{name}" in expr or f"vars.{name}" in expr]
    return bool(hits) and all(expr in allowed for expr in hits)


class WorkflowSecretTest(unittest.TestCase):
    def test_deploy_backend_prefers_secrets(self) -> None:
        text = _workflow("deploy-backend.yml")
        expressions = _expressions(text)
        for name in SECRET_NAMES:
            self.assertTrue(_accepts_secret_or_variable(expressions, name), name)
        self.assertIn("github.ref == 'refs/heads/main'", text)
        self.assertNotIn("$AWS_ACCOUNT_ID", text)

    def test_other_workflows_prefer_the_account_secret(self) -> None:
        for filename in ("deploy-admin-web.yml", "cdk-diff.yml"):
            text = _workflow(filename)
            expressions = _expressions(text)
            self.assertTrue(_accepts_secret_or_variable(expressions, "AWS_ACCOUNT_ID"), filename)
            self.assertIn("vars.AWS_REGION", expressions, filename)
            self.assertNotIn("$AWS_ACCOUNT_ID", text, filename)
        admin = _workflow("deploy-admin-web.yml")
        self.assertIn("github.ref == 'refs/heads/main'", admin)
        self.assertIn('".github/workflows/deploy-admin-web.yml"', admin)
        self.assertIn("Require the account id", admin)
        self.assertNotIn("Require the account secret", admin)

    def test_a_variable_fallback_warns_and_is_masked(self) -> None:
        for filename in ("deploy-backend.yml", "deploy-admin-web.yml", "cdk-diff.yml"):
            text = _workflow(filename)
            self.assertIn("::add-mask::", text, filename)
            self.assertIn("is read from a variable, so this log shows it", text, filename)
            self.assertIn("AWS_ACCOUNT_ID", text, filename)

    def test_cdk_diff_strips_the_account_from_the_summary(self) -> None:
        text = _workflow("cdk-diff.yml")
        self.assertIn('sed "s/${AWS_ACCOUNT_ID}/***/g"', text)
        self.assertNotIn("AWS_ACCOUNT_ID is unset", text)
