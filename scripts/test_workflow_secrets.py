#!/usr/bin/env python3
"""Public workflows must not print owner emails.

The account id is a repository secret. Deploy workflows, CDK Diff,
and key management pass secrets.AWS_ACCOUNT_ID only.
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
        self.assertIn(
            'COGNITO_PREFIX_ORIGIN="https://${COGNITO_PREFIX}.auth.${AWS_REGION}.amazoncognito.com"',
            text,
        )
        self.assertIn(
            'COGNITO_ORIGIN="${COGNITO_PREFIX_ORIGIN} https://${P_COGNITO_DOMAIN}"',
            text,
        )
        self.assertIn('COGNITO_ORIGIN="${COGNITO_PREFIX_ORIGIN}"', text)
        self.assertIn(
            "Set both ADMIN_COGNITO_CUSTOM_DOMAIN_NAME and ADMIN_COGNITO_CUSTOM_DOMAIN_CERTIFICATE_ARN, or leave both empty.",
            text,
        )

    def test_cdk_diff_calls_aws_oidc(self) -> None:
        text = _workflow("cdk-diff.yml")
        expressions = _expressions(text)
        self.assertIn("secrets.AWS_ACCOUNT_ID", expressions)
        self.assertNotIn("vars.AWS_ACCOUNT_ID", expressions)
        self.assertIn("vars.AWS_REGION", expressions)
        self.assertRegex(
            text,
            r"uses: lx-software-ltd/actions/aws-oidc@[0-9a-f]{40} # main \d{4}-\d{2}-\d{2}",
        )
        self.assertRegex(
            text,
            r"uses: lx-software-ltd/actions/cdk-bootstrap-check@[0-9a-f]{40} # main \d{4}-\d{2}-\d{2}",
        )
        self.assertRegex(
            text,
            r"uses: lx-software-ltd/actions/cdk-diff@[0-9a-f]{40} # main \d{4}-\d{2}-\d{2}",
        )
        self.assertNotIn("subject:", text)
        self.assertNotIn("::add-mask::", text)
        self.assertNotIn("$AWS_ACCOUNT_ID", text)

    def test_manage_api_keys_calls_aws_oidc(self) -> None:
        text = _workflow("manage-api-keys.yml")
        expressions = _expressions(text)
        self.assertIn("secrets.AWS_ACCOUNT_ID", expressions)
        self.assertNotIn("vars.AWS_ACCOUNT_ID", expressions)
        self.assertNotIn("secrets.AWS_ACCOUNT_ID || vars.AWS_ACCOUNT_ID", text)
        self.assertIn("vars.AWS_REGION", expressions)
        self.assertNotIn("$AWS_ACCOUNT_ID", text)
        self.assertNotIn("configure-aws-credentials", text)
        self.assertRegex(
            text,
            r"uses: lx-software-ltd/actions/aws-oidc@[0-9a-f]{40} # main \d{4}-\d{2}-\d{2}",
        )

    def test_deploy_workflows_call_aws_oidc(self) -> None:
        pin = r"uses: lx-software-ltd/actions/aws-oidc@[0-9a-f]{40} # main \d{4}-\d{2}-\d{2}"
        for filename in (
            "deploy-backend.yml",
            "deploy-admin-web.yml",
            "deploy-public-website.yml",
        ):
            text = _workflow(filename)
            expressions = _expressions(text)
            self.assertIn("secrets.AWS_ACCOUNT_ID", expressions, filename)
            self.assertNotIn("vars.AWS_ACCOUNT_ID", expressions, filename)
            self.assertNotIn("secrets.AWS_ACCOUNT_ID || vars.AWS_ACCOUNT_ID", text, filename)
            self.assertIn("vars.AWS_REGION", expressions, filename)
            self.assertRegex(text, pin, filename)
            self.assertNotIn("configure-aws-credentials", text, filename)
            self.assertNotIn("$AWS_ACCOUNT_ID", text, filename)
        admin = _workflow("deploy-admin-web.yml")
        self.assertIn("github.ref == 'refs/heads/main'", admin)
        self.assertIn('".github/workflows/deploy-admin-web.yml"', admin)
        self.assertRegex(
            admin,
            r"uses: lx-software-ltd/actions/cfn-stack-outputs@[0-9a-f]{40} # main \d{4}-\d{2}-\d{2}",
        )
        self.assertIn("UserPoolClientId CognitoDomain AdminApiBaseUrl", admin)
        self.assertIn("CognitoDomain on findingalpha must be an https origin", admin)
        self.assertIn("AdminApiBaseUrl on findingalpha must be an https origin", admin)
        self.assertNotIn("describe-stacks", admin)
        self.assertNotIn("::add-mask::", admin)
        public = _workflow("deploy-public-website.yml")
        self.assertIn("findingalpha-public-www", public)
        self.assertIn("Skip when the stack is not deployed yet", public)
        self.assertLess(public.index("npm ci"), public.index("actions/aws-oidc@"))
        self.assertLess(public.index("Build public website"), public.index("actions/aws-oidc@"))
        self.assertLess(public.index("actions/aws-oidc@"), public.index("Skip when the stack is not deployed yet"))

    def test_account_id_is_masked_without_a_warning(self) -> None:
        for filename in ("deploy-backend.yml", "deploy-admin-web.yml"):
            text = _workflow(filename)
            self.assertNotIn("AWS_ACCOUNT_ID is read from a variable", text, filename)
            self.assertNotIn("ACCOUNT_FROM_VARIABLE", text, filename)
            self.assertNotIn("ADMIN_BOOTSTRAP_EMAIL", text, filename)
        backend = _workflow("deploy-backend.yml")
        self.assertIn("::add-mask::", backend)
        admin = _workflow("deploy-admin-web.yml")
        self.assertNotIn("::add-mask::", admin)
        self.assertIn("is read from a variable, so this log shows it", backend)
        self.assertIn(
            'warn_if_variable "${ALLOWLIST_FROM_VARIABLE}" "ADMIN_FEDERATED_EMAIL_ALLOWLIST"',
            backend,
        )

    def test_cdk_diff_strips_the_account_from_the_summary(self) -> None:
        text = _workflow("cdk-diff.yml")
        self.assertIn("account-id: ${{ secrets.AWS_ACCOUNT_ID }}", text)
        self.assertNotIn('sed "s/${AWS_ACCOUNT_ID}/***/g"', text)
        self.assertNotIn("secrets.AWS_ACCOUNT_ID || vars.AWS_ACCOUNT_ID", text)
        self.assertNotIn("AWS_ACCOUNT_ID is unset", text)
