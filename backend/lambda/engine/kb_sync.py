"""Decide when the knowledge base should sync, and poll the jobs it starts.

The daily schedule never starts the first sync. Run now does. A deletion
above 15% is judged per data source and waits for confirmDeletion.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Any, Callable

import store
import timeutil
from http_common import _log_event

PREFIXES = ("theory/", "formula-notes/", "journal/")
EXTENSIONS = frozenset({".pdf", ".md", ".txt", ".html", ".doc", ".docx", ".xls", ".xlsx", ".csv"})
MAX_FILE_BYTES = 50_000_000
MAX_SIDECAR_BYTES = 10 * 1024
STATE_PK = "KB#state"
STATE_SK = "META"
JOB = "kb_sync_check"
_ACTIVE = frozenset({"STARTING", "IN_PROGRESS", "STOPPING"})
_FAILED_JOB = frozenset({"FAILED", "STOPPED"})
_FAILED_DOCUMENT = frozenset({"FAILED", "METADATA_UPDATE_FAILED"})
_EXPIRED_LEASE = "1970-01-01T00:00:00.000Z"

Loader = Callable[[], list[dict[str, Any]]]
Clock = Callable[[], datetime]


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


def decide(
    built: dict[str, Any],
    state: dict[str, Any],
    *,
    confirm: bool = False,
    cap: int | None = None,
) -> dict[str, Any]:
    """Choose what this run should do. ``start`` names the prefixes whose files changed."""
    found = problems(built)
    if found:
        return {"status": "blocked_problems", "problems": found}
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
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Poll a sync that is already running, or decide whether a new one may start."""
    moment = (clock or timeutil.utc_now)()
    state = store.get(STATE_PK, STATE_SK) or {}
    if state.get("jobs"):
        return _poll(state, agent or _agent(), moment)
    if str(event.get("trigger") or "") != "manual" and not state.get("manifestHash"):
        return {"ok": True, "status": "awaiting_first_sync"}
    built = manifest((loader or _load)())
    choice = decide(built, state, confirm=_confirmed(event))
    if choice["status"] != "start":
        ok = choice["status"] == "unchanged"
        _log_event("info", tag="kb_sync", status=choice["status"])
        return {"ok": ok, **choice}
    return _start(built, choice, agent or _agent(), moment)


def _start(built: dict[str, Any], choice: dict[str, Any], agent: Any, moment: datetime) -> dict[str, Any]:
    ids = _source_ids()
    knowledge_base = os.environ.get("KNOWLEDGE_BASE_ID", "")
    if ids is None or not knowledge_base:
        return {"ok": False, "status": "failed", "error": "knowledge base is not configured"}
    _job_row("running", timeutil.format_iso_millis(moment + timedelta(minutes=16)))
    jobs: dict[str, str] = {}
    for prefix in choice["prefixes"]:
        token = _digest(_rows(built, prefix))[:40]
        try:
            response = agent.start_ingestion_job(
                knowledgeBaseId=knowledge_base,
                dataSourceId=ids[prefix],
                clientToken=token,
            )
            jobs[prefix] = response["ingestionJob"]["ingestionJobId"]
        except Exception as exc:
            if _error_code(exc) != "ConflictException":
                raise
            adopted = _running_job(agent, knowledge_base, ids[prefix])
            if not adopted:
                return {"ok": False, "status": "failed", "error": "ingestion already running"}
            jobs[prefix] = adopted
    store.put(
        {
            "pk": STATE_PK,
            "sk": STATE_SK,
            "status": "running",
            "jobs": jobs,
            "pending": snapshot(built),
            "expectedDeletions": {prefix: choice["expectedDeletions"].get(prefix, 0) for prefix in jobs},
            "updatedAt": timeutil.format_iso_millis(moment),
        }
    )
    _job_row("running", _EXPIRED_LEASE)
    _log_event("info", tag="kb_sync", status="running", sources=len(jobs))
    return {"ok": True, "status": "running", "prefixes": list(jobs)}


def _poll(state: dict[str, Any], agent: Any, moment: datetime) -> dict[str, Any]:
    knowledge_base = os.environ.get("KNOWLEDGE_BASE_ID", "")
    ids = _source_ids() or {}
    seen: dict[str, dict[str, Any]] = {}
    for prefix, job_id in (state.get("jobs") or {}).items():
        response = agent.get_ingestion_job(
            knowledgeBaseId=knowledge_base,
            dataSourceId=ids.get(prefix, ""),
            ingestionJobId=job_id,
        )
        seen[prefix] = response["ingestionJob"]
    if any(item.get("status") in _ACTIVE for item in seen.values()):
        _job_row("running", _EXPIRED_LEASE)
        return {"ok": True, "status": "running"}
    if any(item.get("status") in _FAILED_JOB for item in seen.values()):
        _job_row("failed", None, failures=3)
        return {"ok": False, "status": "failed", "error": "ingestion failed"}
    failed: list[str] = []
    shortfall: dict[str, int] = {}
    expected = state.get("expectedDeletions") or {}
    for prefix, item in seen.items():
        deleted = int((item.get("statistics") or {}).get("numberOfDocumentsDeleted") or 0)
        if int(expected.get(prefix) or 0) > deleted:
            shortfall[prefix] = int(expected[prefix]) - deleted
        failed.extend(_failed_keys(agent, knowledge_base, ids.get(prefix, "")))
    pending = state.get("pending") or {}
    saved = {
        "pk": STATE_PK,
        "sk": STATE_SK,
        "status": "done",
        "syncedAt": timeutil.format_iso_millis(moment),
        "manifestHash": pending.get("manifestHash"),
        "bytes": pending.get("bytes"),
        "documents": pending.get("documents"),
        "sources": pending.get("sources") or {},
        "updatedAt": timeutil.format_iso_millis(moment),
    }
    if failed:
        saved["failedKeys"] = sorted(failed)
    if shortfall:
        saved["deletionShortfall"] = shortfall
    store.put(saved)
    _job_row("done", None)
    _log_event("info", tag="kb_sync", status="done", failed=len(failed))
    result: dict[str, Any] = {"ok": True, "status": "done", "failedKeys": sorted(failed)}
    if shortfall:
        result["deletionShortfall"] = shortfall
    return result


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


def _confirmed(event: dict[str, Any]) -> bool:
    if event.get("confirmDeletion") is True:
        return True
    params = event.get("params")
    return isinstance(params, dict) and params.get("confirmDeletion") is True


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


def _agent() -> Any:
    import boto3

    return boto3.client("bedrock-agent")


def _running_job(agent: Any, knowledge_base: str, source_id: str) -> str:
    response = agent.list_ingestion_jobs(knowledgeBaseId=knowledge_base, dataSourceId=source_id, maxResults=20)
    for item in response.get("ingestionJobSummaries") or []:
        if item.get("status") in {"STARTING", "IN_PROGRESS"}:
            return str(item.get("ingestionJobId") or "")
    return ""


def _failed_keys(agent: Any, knowledge_base: str, source_id: str) -> list[str]:
    found: list[str] = []
    token = ""
    while True:
        kwargs: dict[str, Any] = {"knowledgeBaseId": knowledge_base, "dataSourceId": source_id, "maxResults": 100}
        if token:
            kwargs["nextToken"] = token
        page = agent.list_knowledge_base_documents(**kwargs)
        for item in page.get("documentDetails") or []:
            if item.get("status") not in _FAILED_DOCUMENT:
                continue
            uri = str(((item.get("identifier") or {}).get("s3") or {}).get("uri") or "")
            found.append(uri.split("/", 3)[-1] if "://" in uri else uri)
        token = str(page.get("nextToken") or "")
        if not token:
            return found


def _job_row(status: str, lease: str | None, failures: int = 0) -> None:
    item: dict[str, Any] = {
        "pk": f"JOB#{JOB}",
        "sk": "STATE",
        "status": status,
        "gsi1pk": "JOBSTATE",
        "gsi1sk": JOB,
        "updatedAt": timeutil.now_iso(),
    }
    if lease is not None:
        item["leaseUntil"] = lease
    if failures:
        item["failures"] = failures
    store.put(item)


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return str((response.get("Error") or {}).get("Code") or "")
    return ""
