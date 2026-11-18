"""Decide when the knowledge base should sync.

The daily schedule never starts the first sync. Run now does. A deletion
above 15% is judged per data source and waits for the owner to confirm.
A problem file is recorded and left out of the sync. Starting and polling
the ingestion jobs lives in ``kb_sync_jobs``.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Callable

PREFIXES = ("theory/", "formula-notes/", "journal/")
EXTENSIONS = frozenset(
    {".pdf", ".md", ".markdown", ".txt", ".html", ".htm", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".pptx"}
)
MAX_FILE_BYTES = 50_000_000
MAX_SIDECAR_BYTES = 10 * 1024
STATE_PK = "KB#state"
STATE_SK = "META"
JOB = "kb_sync_check"

Loader = Callable[[], list[dict[str, Any]]]


def manifest(objects: list[dict[str, Any]]) -> dict[str, Any]:
    """Split listed objects into documents and sidecars. Objects outside the three prefixes are ignored."""
    documents: dict[str, dict[str, Any]] = {}
    sidecars: dict[str, dict[str, Any]] = {}
    for item in objects:
        key = str(item["key"])
        prefix = _prefix(key)
        if prefix is None or key.endswith("/"):
            continue
        entry = {"size": int(item["size"]), "etag": str(item["etag"]), "prefix": prefix}
        if key.endswith(".metadata.json"):
            sidecars[key] = {**entry, "document": key[: -len(".metadata.json")]}
        else:
            documents[key] = entry
    total = sum(item["size"] for item in documents.values()) + sum(item["size"] for item in sidecars.values())
    return {"documents": documents, "sidecars": sidecars, "bytes": total}


def problems(built: dict[str, Any]) -> list[dict[str, str]]:
    """Files the sync should not send: too large, an unknown type, or a sidecar that does not match."""
    found: list[dict[str, str]] = []
    for key, item in sorted(built["documents"].items()):
        extension = os.path.splitext(key)[1].lower()
        if extension not in EXTENSIONS:
            found.append({"key": key, "problem": "unsupported"})
        elif item["size"] > MAX_FILE_BYTES:
            found.append({"key": key, "problem": "too_large"})
    for key, item in sorted(built["sidecars"].items()):
        if item["size"] > MAX_SIDECAR_BYTES:
            found.append({"key": key, "problem": "sidecar_too_large"})
        elif item["document"] not in built["documents"]:
            found.append({"key": key, "problem": "orphan_sidecar"})
    return found


def syncable(built: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """The manifest with problem files removed, and the problems themselves."""
    found = problems(built)
    bad_documents = {item["key"] for item in found if item["problem"] in {"unsupported", "too_large"}}
    bad_sidecars = {item["key"] for item in found if item["problem"] in {"sidecar_too_large", "orphan_sidecar"}}
    documents = {key: item for key, item in built["documents"].items() if key not in bad_documents}
    sidecars = {
        key: item
        for key, item in built["sidecars"].items()
        if key not in bad_sidecars and item["document"] in documents
    }
    total = sum(item["size"] for item in documents.values()) + sum(item["size"] for item in sidecars.values())
    return {"documents": documents, "sidecars": sidecars, "bytes": total}, found


def fingerprint(built: dict[str, Any]) -> str:
    """A hash of every object. Listing order does not change it."""
    return _digest(_rows(built, None))


def snapshot(built: dict[str, Any]) -> dict[str, Any]:
    """The manifest hash and, per prefix, the hash and document keys to compare next time."""
    sources = {}
    for prefix in PREFIXES:
        keys = sorted(key for key, item in built["documents"].items() if item["prefix"] == prefix)
        sources[prefix] = {"hash": _digest(_rows(built, prefix)), "keys": keys}
    return {
        "manifestHash": fingerprint(built),
        "bytes": built["bytes"],
        "documents": len(built["documents"]),
        "sources": sources,
    }


def started_once(state: dict[str, Any]) -> bool:
    """True once a sync has committed a manifest or any data source."""
    return bool(state.get("manifestHash") or state.get("sources") or state.get("syncedAt"))


def decide(
    built: dict[str, Any],
    state: dict[str, Any],
    *,
    confirm: bool = False,
    cap: int | None = None,
) -> dict[str, Any]:
    """Choose what this run should do. ``start`` names the prefixes whose files changed.

    ``built`` is the syncable manifest: problem files are already removed.
    """
    limit = _cap() if cap is None else cap
    if limit is None:
        return {"status": "failed", "error": "KB_MAX_RAW_BYTES"}
    if built["bytes"] > limit:
        return {"status": "blocked_size", "bytes": built["bytes"], "cap": limit}
    blocked, expected = _deletions(built, state)
    if blocked and not confirm:
        return {"status": "blocked_deletion", "deletions": blocked}
    if fingerprint(built) == state.get("manifestHash") and not state.get("jobs"):
        return {"status": "unchanged"}
    changed = [
        prefix
        for prefix in PREFIXES
        if _digest(_rows(built, prefix)) != ((state.get("sources") or {}).get(prefix) or {}).get("hash")
        and (_has_files(built, prefix) or _saved_keys(state, prefix))
    ]
    if not changed:
        return {"status": "unchanged"}
    return {"status": "start", "prefixes": changed, "expectedDeletions": expected}


def run(
    event: dict[str, Any],
    _context: Any = None,
    *,
    loader: Loader | None = None,
    agent: Any = None,
    clock: Any = None,
) -> dict[str, Any]:
    """Poll a sync that is already running, or decide whether a new one may start."""
    import kb_sync_jobs

    return kb_sync_jobs.run(event, _context, loader=loader, agent=agent, clock=clock)


def _has_files(built: dict[str, Any], prefix: str) -> bool:
    groups = (built["documents"], built["sidecars"])
    return any(item["prefix"] == prefix for group in groups for item in group.values())


def _saved_keys(state: dict[str, Any], prefix: str) -> list[Any]:
    return list(((state.get("sources") or {}).get(prefix) or {}).get("keys") or [])


def _deletions(built: dict[str, Any], state: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    blocked: list[dict[str, Any]] = []
    expected: dict[str, int] = {}
    saved = state.get("sources") or {}
    for prefix in PREFIXES:
        previous = set((saved.get(prefix) or {}).get("keys") or [])
        current = {key for key, item in built["documents"].items() if item["prefix"] == prefix}
        gone = len(previous - current)
        expected[prefix] = gone
        if previous and gone * 100 > len(previous) * 15:
            blocked.append({"prefix": prefix, "gone": gone, "previous": len(previous)})
    return blocked, expected


def _rows(built: dict[str, Any], prefix: str | None) -> list[str]:
    rows: list[str] = []
    for kind, group in (("d", built["documents"]), ("s", built["sidecars"])):
        for key, item in group.items():
            if prefix is not None and item["prefix"] != prefix:
                continue
            rows.append(f"{kind}\t{key}\t{item['size']}\t{item['etag']}")
    return rows


def _digest(rows: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()


def _prefix(key: str) -> str | None:
    return next((prefix for prefix in PREFIXES if key.startswith(prefix)), None)


def _cap() -> int | None:
    raw = os.environ.get("KB_MAX_RAW_BYTES", "")
    return int(raw) if raw.isdigit() else None


def _source_ids() -> dict[str, str] | None:
    try:
        parsed = json.loads(os.environ.get("KB_DATA_SOURCE_IDS", ""))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or any(prefix not in parsed for prefix in PREFIXES):
        return None
    return {prefix: str(parsed[prefix]) for prefix in PREFIXES}


def _load() -> list[dict[str, Any]]:
    import boto3

    client = boto3.client("s3")
    bucket = os.environ["KB_BUCKET_NAME"]
    found: list[dict[str, Any]] = []
    for prefix in PREFIXES:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents") or []:
                if not str(item["Key"]).endswith("/"):
                    found.append({"key": item["Key"], "size": int(item["Size"]), "etag": str(item["ETag"])})
    return found
