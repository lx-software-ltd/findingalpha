#!/usr/bin/env python3
"""Public workflows must not print owner emails.

The account id is a repository variable. A secret of the same name
still wins when it is set. Either way it is masked after the first
settings block, and the job does not warn about it.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Read as a secret, or as `secrets.NAME || vars.NAME`. Never the variable alone.
SECRET_NAMES = (
    "AWS_ACCOUNT_ID",
    "ADMIN_FEDERATED_EMAIL_ALLOWLIST",
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
    """A secret wins when set. The variable may be the value in use, but never the only expression."""
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

    def test_deploy_backend_passes_cognito_custom_domain_like_api(self) -> None:
        text = _workflow("deploy-backend.yml")
        expressions = _expressions(text)
        self.assertIn("vars.API_CUSTOM_DOMAIN_NAME", expressions)
        self.assertIn("vars.API_CUSTOM_DOMAIN_CERTIFICATE_ARN", expressions)
        self.assertIn("vars.ADMIN_COGNITO_CUSTOM_DOMAIN_NAME", expressions)
        self.assertIn("vars.ADMIN_COGNITO_CUSTOM_DOMAIN_CERTIFICATE_ARN", expressions)
        self.assertNotIn("vars.ADMIN_COGNITO_SERVE_CUSTOM_DOMAIN", expressions)
        self.assertNotIn("vars.ADMIN_COGNITO_ORIGIN", expressions)
        self.assertNotIn("CognitoServeCustomDomain", text)
        self.assertIn(
            "findingalpha:CognitoCustomDomainName=${P_COGNITO_DOMAIN}",
            text,
        )
        self.assertIn(
            "findingalpha:CognitoCustomDomainCertificateArn=${P_COGNITO_CERT}",
            text,
        )
        self.assertIn(
            "findingalpha-admin-web:CspCognitoConnectOrigin=${COGNITO_ORIGIN}",
            text,
        )
        self.assertIn('COGNITO_ORIGIN="https://${P_COGNITO_DOMAIN}"', text)
        self.assertIn(
            'COGNITO_ORIGIN="https://${COGNITO_PREFIX}.auth.${AWS_REGION}.amazoncognito.com"',
            text,
        )
        self.assertIn(
            "Set both ADMIN_COGNITO_CUSTOM_DOMAIN_NAME and ADMIN_COGNITO_CUSTOM_DOMAIN_CERTIFICATE_ARN, or leave both empty.",
            text,
        )

    def test_other_workflows_prefer_the_account_secret(self) -> None:
        for filename in ("deploy-admin-web.yml", "cdk-diff.yml", "manage-api-keys.yml"):
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

    def test_account_id_is_masked_without_a_warning(self) -> None:
        for filename in ("deploy-backend.yml", "deploy-admin-web.yml", "cdk-diff.yml"):
            text = _workflow(filename)
            self.assertIn("::add-mask::", text, filename)
            self.assertNotIn("AWS_ACCOUNT_ID is read from a variable", text, filename)
            self.assertNotIn("ACCOUNT_FROM_VARIABLE", text, filename)
            self.assertNotIn("ADMIN_BOOTSTRAP_EMAIL", text, filename)
        backend = _workflow("deploy-backend.yml")
        self.assertIn("is read from a variable, so this log shows it", backend)
        self.assertIn(
            'warn_if_variable "${ALLOWLIST_FROM_VARIABLE}" "ADMIN_FEDERATED_EMAIL_ALLOWLIST"',
            backend,
        )

    def test_cdk_diff_strips_the_account_from_the_summary(self) -> None:
        text = _workflow("cdk-diff.yml")
        self.assertIn('sed "s/${AWS_ACCOUNT_ID}/***/g"', text)
        self.assertNotIn("AWS_ACCOUNT_ID is unset", text)
