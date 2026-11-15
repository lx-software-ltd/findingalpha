#!/usr/bin/env python3
"""Fail when generated contract files drift, and validate the roadmap."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_sync():
    path = ROOT / "scripts" / "sync-contracts.py"
    spec = importlib.util.spec_from_file_location("sync_contracts", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync_contracts = _load_sync()

MILESTONE_STATUS = {"not_started", "in_progress", "blocked", "done"}
STEP_STATUS = {"todo", "doing", "done"}
GENERATED = [
    Path("backend/lambda/engine/contracts"),
    Path("backend/lambda/engine/contract_constants.py"),
    Path("backend/lambda/public_api_authorizer/public_api_scopes_generated.py"),
    Path("apps/admin_web/src/lib/contracts/generated.ts"),
    Path("backend/infrastructure/lib/shared-contracts.ts"),
]


def validate_scopes(path: Path) -> list[str]:
    """Every tier scope is a known scope, and a read-only tier has no operate."""
    if not path.is_file():
        return [f"missing {path}"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"scopes json: {exc}"]
    known = {item["value"] for item in doc.get("scopes", [])}
    errors: list[str] = []
    for tier in doc.get("tiers", []):
        name = tier.get("value", "?")
        for scope in tier.get("scopes", []):
            if scope not in known:
                errors.append(f"tier {name} lists unknown scope {scope}")
        if not tier.get("mayWrite") and "operate" in tier.get("scopes", []):
            errors.append(f"tier {name} may not write and must not list operate")
    return errors


def validate_roadmap(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"roadmap.json: {exc}"]
    milestones = doc.get("milestones")
    if not isinstance(milestones, list):
        return ["roadmap.json: milestones must be a list"]
    ids: set[str] = set()
    for milestone in milestones:
        mid = milestone.get("id")
        if not isinstance(mid, str) or not mid:
            errors.append("roadmap milestone is missing id")
            continue
        if mid in ids:
            errors.append(f"duplicate milestone id {mid}")
        ids.add(mid)
        status = milestone.get("status")
        if status not in MILESTONE_STATUS:
            errors.append(f"{mid}: unknown status {status!r}")
        steps = milestone.get("steps")
        if not isinstance(steps, list):
            errors.append(f"{mid}: steps must be a list")
            continue
        seen: set[str] = set()
        for step in steps:
            sid = step.get("id")
            if not isinstance(sid, str) or not sid:
                errors.append(f"{mid}: step is missing id")
                continue
            if sid in seen:
                errors.append(f"duplicate step id {sid}")
            seen.add(sid)
            if step.get("status") not in STEP_STATUS:
                errors.append(f"{sid}: unknown status {step.get('status')!r}")
    for milestone in milestones:
        mid = milestone.get("id")
        for dep in milestone.get("dependsOn") or []:
            if dep not in ids:
                errors.append(f"{mid}: dependsOn {dep} does not exist")
    for task in doc.get("ownerTasks") or []:
        tid = task.get("id")
        for block in task.get("blocks") or []:
            if block not in ids:
                errors.append(f"{tid}: blocks {block} does not exist")
    return errors


def _generated_files(root: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for relative in GENERATED:
        path = root / relative
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    found[child.relative_to(root).as_posix()] = child.read_text(encoding="utf-8")
        elif path.is_file():
            found[relative.as_posix()] = path.read_text(encoding="utf-8")
    return found


def check_generated() -> list[str]:
    """Sync into a temporary tree and compare with the committed files."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shutil.copytree(ROOT / "contracts", root / "contracts")
        engine_parent = ROOT / "backend" / "lambda" / "engine"
        if engine_parent.exists():
            (root / "backend" / "lambda" / "engine").mkdir(parents=True)
            source = engine_parent / "contracts"
            if source.exists():
                shutil.copytree(source, root / "backend" / "lambda" / "engine" / "contracts")
        ts = ROOT / "apps" / "admin_web" / "src" / "lib" / "contracts" / "generated.ts"
        if ts.parent.exists():
            (root / ts.parent.relative_to(ROOT)).mkdir(parents=True, exist_ok=True)
            if ts.exists():
                shutil.copy2(ts, root / ts.relative_to(ROOT))
        shared = ROOT / "backend" / "infrastructure" / "lib" / "shared-contracts.ts"
        if shared.parent.exists():
            (root / shared.parent.relative_to(ROOT)).mkdir(parents=True, exist_ok=True)
            if shared.exists():
                shutil.copy2(shared, root / shared.relative_to(ROOT))
        sync_contracts.sync(root)
        expected = _generated_files(root)
        actual = _generated_files(ROOT)
        errors: list[str] = []
        for name in sorted(set(expected) | set(actual)):
            if expected.get(name) != actual.get(name):
                errors.append(f"generated file differs: {name}")
        return errors


def main() -> int:
    errors = validate_roadmap(ROOT / "contracts" / "roadmap.json")
    errors.extend(validate_scopes(ROOT / "contracts" / "public-api-scopes.json"))
    errors.extend(check_generated())
    if errors:
        print("Contract check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Contract check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
