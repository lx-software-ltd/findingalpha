"""Retrieve passages from the managed knowledge base.

The monthly cap is read before the call and incremented after it. A
repeat of the same query in one run uses ``cache`` and is not counted
again. Passage text is returned to the caller and is never logged.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import kb_sync
import store
import timeutil
from http_common import _log_event

_BUDGETS = Path(__file__).resolve().parent / "contracts" / "budgets.json"
_SOURCE_TYPES = {"theory": "theory/", "formula-notes": "formula-notes/", "journal": "journal/"}
_PAGE = "x-amz-bedrock-kb-document-page-number"
_QUERY_LIMIT = 1000

Clock = Callable[[], Any]


class KbBudgetExceeded(Exception):
    """The monthly retrieval cap is already used."""


class KbNotConfigured(Exception):
    """The knowledge base id is not set."""


def retrieve(
    query: str,
    top_k: int | None = None,
    source_types: list[str] | None = None,
    *,
    cache: dict[tuple[Any, ...], list[dict[str, Any]]] | None = None,
    client: Any = None,
    clock: Clock | None = None,
) -> list[dict[str, Any]]:
    """Passages for ``query``. ``source_types`` limits the folders."""
    text = str(query or "")[:_QUERY_LIMIT]
    if not text.strip():
        return []
    limits = _limits()
    chosen = _top_k(top_k, limits)
    folders = _folders(source_types)
    if source_types is not None and not folders:
        return []
    key = (text, chosen, tuple(folders))
    if cache is not None and key in cache:
        return [dict(item) for item in cache[key]]
    moment = (clock or timeutil.utc_now)()
    month = f"USAGE#{moment:%Y-%m}"
    cap = int(limits["maxRetrievalsPerMonth"])
    used = _reserve(month, cap)
    if used + 1 >= int(cap * float(limits["warnShare"])):
        _log_event("warning", tag="kb_retrieve", status="near_cap", used=used + 1, cap=cap)
    started = time.perf_counter()
    try:
        passages = _map(_call(text, chosen, folders, client), folders if _filter_ids(folders) is None else None)
    except Exception:
        _release(month)
        raise
    _add(f"USAGE#{moment:%Y-%m-%d}")
    _log_event(
        "info",
        tag="kb_retrieve",
        queryHash=hashlib.sha256(text.encode()).hexdigest()[:16],
        results=len(passages),
        latencyMs=int((time.perf_counter() - started) * 1000),
    )
    if cache is not None:
        cache[key] = [dict(item) for item in passages]
    return passages


def _limits() -> dict[str, Any]:
    loaded = json.loads(_BUDGETS.read_text(encoding="utf-8"))
    kb = loaded.get("kb") if isinstance(loaded, dict) else None
    if not isinstance(kb, dict):
        raise KbNotConfigured("retrieval budget is missing")
    return kb


def _top_k(value: int | None, limits: dict[str, Any]) -> int:
    chosen = limits["defaultTopK"] if not isinstance(value, int) or isinstance(value, bool) else value
    return max(1, min(int(chosen), int(limits["maxTopK"])))


def _folders(source_types: list[str] | None) -> list[str]:
    if source_types is None:
        return []
    return [name for name in source_types if name in _SOURCE_TYPES]


def _filter_ids(folders: list[str]) -> list[str] | None:
    """Data source ids for the filter, or None when the map is not configured."""
    if not folders:
        return []
    ids = kb_sync._source_ids()
    if ids is None:
        return None
    return [ids[_SOURCE_TYPES[name]] for name in folders]


def _call(text: str, top_k: int, folders: list[str], client: Any) -> list[dict[str, Any]]:
    knowledge_base = os.environ.get("KNOWLEDGE_BASE_ID", "")
    if not knowledge_base:
        raise KbNotConfigured("knowledge base is not configured")
    search: dict[str, Any] = {"numberOfResults": top_k}
    selected = _filter_ids(folders)
    if selected:
        search["filter"] = {"in": {"key": "_data_source_id", "value": selected}}
    agent = client or _agent()
    response = agent.retrieve(
        knowledgeBaseId=knowledge_base,
        retrievalQuery={"text": text},
        retrievalConfiguration={"managedSearchConfiguration": search},
    )
    found = response.get("retrievalResults")
    return found if isinstance(found, list) else []


def _map(results: list[dict[str, Any]], folders: list[str] | None) -> list[dict[str, Any]]:
    passages: list[dict[str, Any]] = []
    for item in results:
        uri = str(((item.get("location") or {}).get("s3Location") or {}).get("uri") or "")
        key = uri.split("/", 3)[-1] if "://" in uri else uri
        source_type = next((name for name, prefix in _SOURCE_TYPES.items() if key.startswith(prefix)), "")
        if folders is not None and source_type not in folders:
            continue
        page = (item.get("metadata") or {}).get(_PAGE)
        passages.append(
            {
                "text": str((item.get("content") or {}).get("text") or ""),
                "document": key.rsplit("/", 1)[-1],
                "locator": ""
                if page is None
                else str(int(page) if isinstance(page, float) and page.is_integer() else page),
                "score": item.get("score"),
                "sourceType": source_type,
            }
        )
    return passages


def _reserve(pk: str, cap: int) -> int:
    """Take one retrieval before the call. The condition stops two runs crossing the cap."""
    try:
        previous = store.update_conditional(
            pk,
            "KB",
            "ADD #n :one",
            {":one": 1, ":cap": cap},
            "attribute_not_exists(#n) OR #n < :cap",
            {"#n": "count"},
        )
    except store.ConditionNotMet:
        raise KbBudgetExceeded("monthly retrieval cap reached") from None
    return int((previous or {}).get("count") or 0)


def _release(pk: str) -> None:
    store.update(pk, "KB", "ADD #n :minus", {":minus": -1}, {"#n": "count"})


def _add(pk: str) -> None:
    store.update(pk, "KB", "ADD #n :one", {":one": 1}, {"#n": "count"})


def _agent() -> Any:
    import boto3

    return boto3.client("bedrock-agent-runtime")
