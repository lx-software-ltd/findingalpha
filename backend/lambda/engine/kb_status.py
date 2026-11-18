"""Read the knowledge base for the dashboard.

This module does not start a sync and does not retrieve passages.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import kb_eval
import kb_sync
import store
import timeutil

_BUDGETS = Path(__file__).resolve().parent / "contracts" / "budgets.json"
_GIGABYTE = 1_000_000_000
_PROBLEMS = {"too_large", "unsupported", "sidecar_too_large", "orphan_sidecar"}


def status_payload() -> dict[str, Any]:
    """Documents, caps, the last sync, and the estimated monthly cost."""
    state = store.get(kb_sync.STATE_PK, kb_sync.STATE_SK) or {}
    evaluation = store.get(kb_eval.STATE_PK, kb_eval.STATE_SK) or {}
    rates = _rates()
    retrievals = _retrievals()
    stored = int(state.get("bytes") or 0)
    cap = kb_sync._cap()
    storage = stored / _GIGABYTE * float(rates["storageUsdPerGb"])
    retrieval = retrievals / 1000 * float(rates["retrievalUsdPerThousand"])
    blocked = state.get("blocked") if isinstance(state.get("blocked"), dict) else None
    return {
        "documents": int(state.get("documents") or 0),
        "bytes": stored,
        "capBytes": cap,
        "retrievals": retrievals,
        "retrievalCap": int(rates["maxRetrievalsPerMonth"]),
        "syncedAt": state.get("syncedAt"),
        "status": state.get("status") or "never",
        "running": bool(state.get("jobs")),
        "stopping": bool(state.get("stopRequested")),
        "evaluation": {
            "ranAt": evaluation.get("ranAt"),
            "questions": int(evaluation.get("questions") or 0),
            "hitAt8": evaluation.get("hitAt8"),
            "hitAt3": evaluation.get("hitAt3"),
        },
        "problems": _problems(state.get("problems")),
        "failedDocuments": _names(state.get("failedKeys")),
        "blocked": blocked,
        "blockedReason": _blocked_reason(blocked),
        "cost": {
            "storageUsd": round(storage, 2),
            "retrievalUsd": round(retrieval, 2),
            "totalUsd": round(storage + retrieval, 2),
        },
    }


def eval_payload() -> dict[str, Any]:
    """The latest evaluation: question id and hit rank. Passage text stays out."""
    row = store.get(kb_eval.STATE_PK, kb_eval.STATE_SK) or {}
    results = [
        {"id": str(item.get("id") or ""), "rank": item.get("rank")}
        for item in row.get("results") or []
        if isinstance(item, dict)
    ]
    return {
        "ranAt": row.get("ranAt"),
        "questions": int(row.get("questions") or 0),
        "hitAt8": row.get("hitAt8"),
        "hitAt3": row.get("hitAt3"),
        "results": results,
    }


def _rates() -> dict[str, Any]:
    loaded = json.loads(_BUDGETS.read_text(encoding="utf-8"))
    kb = loaded.get("kb") if isinstance(loaded, dict) else None
    if not isinstance(kb, dict):
        raise RuntimeError("retrieval budget is missing")
    return kb


def _retrievals() -> int:
    month = f"USAGE#{timeutil.utc_now():%Y-%m}"
    row = store.get(month, "KB") or {}
    count = row.get("count") or 0
    return int(count) if isinstance(count, int) and not isinstance(count, bool) else 0


def _problems(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    found: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        problem = str(item.get("problem") or "")
        if problem not in _PROBLEMS:
            continue
        found.append({"key": str(item.get("key") or ""), "problem": problem})
    return found


def _names(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def _blocked_reason(blocked: dict[str, Any] | None) -> str | None:
    if not blocked:
        return None
    status = str(blocked.get("status") or "")
    if status == "blocked_deletion":
        parts = [
            f"{item.get('prefix')} lost {item.get('gone')} of {item.get('previous')}"
            for item in blocked.get("deletions") or []
            if isinstance(item, dict)
        ]
        detail = ", ".join(parts)
        return f"More than 15% of a folder is gone: {detail}." if detail else "More than 15% of a folder is gone."
    if status == "blocked_size":
        return f"The files are {blocked.get('bytes')} bytes, above the cap of {blocked.get('cap')}."
    return status or None
