#!/usr/bin/env python3
"""The public logo site uses the shared Lighthouse CI action."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = "936d3fad83b00b4cc23a603717fdf804576c300c"


class LighthouseWorkflowTest(unittest.TestCase):
    def test_workflow_calls_the_shared_action(self) -> None:
        text = (ROOT / ".github" / "workflows" / "lighthouse-public-www.yml").read_text(encoding="utf-8")
        self.assertIn("name: Lighthouse Public Website\n", text)
        self.assertIn("permissions:\n  contents: read\n", text)
        self.assertIn("runs-on: ubuntu-26.04", text)
        self.assertIn('cron: "15 6 * * 1"', text)
        self.assertRegex(
            text,
            rf"uses: lx-software-ltd/actions/lighthouse-ci@{PIN} # main \d{{4}}-\d{{2}}-\d{{2}}",
        )
        self.assertRegex(
            text,
            rf"uses: lx-software-ltd/actions/setup-node@{PIN} # main \d{{4}}-\d{{2}}-\d{{2}}",
        )
        self.assertIn("working-directory: apps/public_www", text)
        self.assertIn("default-paths: /", text)
        self.assertIn("github-token: ${{ secrets.GITHUB_TOKEN }}", text)
        self.assertIn("statuses: write", text)
        self.assertIn("name: lighthouse-public-www-results", text)
        self.assertIn("path: apps/public_www/.lighthouseci/**", text)
        self.assertIn("include-hidden-files: true", text)
        self.assertNotIn("environment: production", text)
        self.assertNotIn("describe-stacks", text)
        self.assertIsNone(re.search(r"uses: actions/setup-node@", text))

    def test_config_file_is_the_action_default(self) -> None:
        config = ROOT / "apps" / "public_www" / ".lighthouserc.json"
        self.assertTrue(config.is_file())
        text = config.read_text(encoding="utf-8")
        self.assertIn('"staticDistDir": "./dist"', text)
        self.assertIn('"http://localhost:9000/"', text)
