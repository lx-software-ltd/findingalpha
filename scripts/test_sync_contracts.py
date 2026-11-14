#!/usr/bin/env python3
"""Tests for contract sync and roadmap validation."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load(name: str, filename: str):
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = _load("sync_contracts", "sync-contracts.py")
check = _load("check_contracts", "check-contracts.py")


class SyncContractsTest(unittest.TestCase):
    def test_skips_outputs_whose_parents_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts").mkdir()
            (root / "contracts" / "roadmap.json").write_text("{}\n", encoding="utf-8")
            notes = sync.sync(root)
            self.assertTrue(any("engine" in note for note in notes))
            self.assertTrue(any("generated.ts" in note for note in notes))
            self.assertTrue(any("shared-contracts.ts" in note for note in notes))
            self.assertFalse((root / "backend").exists())

    def test_copies_json_except_the_roadmap_and_writes_typescript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts").mkdir()
            (root / "contracts" / "roadmap.json").write_text('{"version": 1}\n', encoding="utf-8")
            (root / "contracts" / "jobs.json").write_text('{"jobs": []}\n', encoding="utf-8")
            (root / "backend" / "lambda" / "engine").mkdir(parents=True)
            (root / "backend" / "infrastructure" / "lib").mkdir(parents=True)
            (root / "apps" / "admin_web" / "src" / "lib" / "contracts").mkdir(parents=True)
            (root / "contracts" / "admin-domains.json").write_text(
                '{"storageKeyPrefix": "fa_admin", "cognitoDomainPrefix": "findingalpha-admin-auth"}\n',
                encoding="utf-8",
            )
            notes = sync.sync(root)
            self.assertEqual(notes, [])
            copied = root / "backend" / "lambda" / "engine" / "contracts"
            self.assertTrue((copied / "jobs.json").is_file())
            self.assertFalse((copied / "roadmap.json").exists())
            text = (root / "apps" / "admin_web" / "src" / "lib" / "contracts" / "generated.ts").read_text()
            self.assertIn("export const jobs", text)
            self.assertIn("export const roadmap", text)
            shared = (root / "backend" / "infrastructure" / "lib" / "shared-contracts.ts").read_text(
                encoding="utf-8"
            )
            self.assertIn('export const storageKeyPrefix = "fa_admin"', shared)
            self.assertIn('export const cognitoDomainPrefix = "findingalpha-admin-auth"', shared)

    def test_repository_roadmap_is_valid(self) -> None:
        errors = check.validate_roadmap(check.ROOT / "contracts" / "roadmap.json")
        self.assertEqual(errors, [])

    def test_unknown_dependency_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(
                json.dumps(
                    {
                        "milestones": [
                            {"id": "M01", "status": "done", "dependsOn": ["M99"], "steps": []}
                        ],
                        "ownerTasks": [{"id": "O01", "blocks": ["M02"]}],
                    }
                ),
                encoding="utf-8",
            )
            errors = check.validate_roadmap(path)
            self.assertTrue(any("M99" in error for error in errors))
            self.assertTrue(any("M02" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
