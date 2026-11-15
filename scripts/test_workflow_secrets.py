#!/usr/bin/env python3
"""Public workflows must not print the account id or owner emails."""

from __future__ import annotations

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


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


class WorkflowSecretTest(unittest.TestCase):
    def test_deploy_backend_reads_identifiers_from_secrets(self) -> None:
        text = _workflow("deploy-backend.yml")
        for name in SECRET_NAMES:
            self.assertNotIn(f"vars.{name}", text, name)
            self.assertIn(f"secrets.{name}", text, name)
        self.assertIn("github.ref == 'refs/heads/main'", text)
        self.assertNotIn("$AWS_ACCOUNT_ID", text)

    def test_other_workflows_read_the_account_from_a_secret(self) -> None:
        for filename in ("deploy-admin-web.yml", "cdk-diff.yml"):
            text = _workflow(filename)
            self.assertNotIn("vars.AWS_ACCOUNT_ID", text, filename)
            self.assertIn("secrets.AWS_ACCOUNT_ID", text, filename)
            self.assertNotIn("$AWS_ACCOUNT_ID", text, filename)
        admin = _workflow("deploy-admin-web.yml")
        self.assertIn("github.ref == 'refs/heads/main'", admin)

    def test_cdk_diff_names_the_secret_when_it_skips(self) -> None:
        text = _workflow("cdk-diff.yml")
        self.assertIn("Set the repository secret", text)
        self.assertNotIn("Set the repository variables", text)
        self.assertIn('sed "s/${AWS_ACCOUNT_ID}/***/g"', text)
