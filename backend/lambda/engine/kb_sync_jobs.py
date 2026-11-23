"""Start, stop, and poll knowledge base ingestion jobs.

The last good manifest is kept until a sync finishes. A failed job is
cleared so the next run can start, and its id changes the idempotency
token. An ingestion still running after 24 hours is stopped.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

import kb_sync
import store
import timeutil
from http_common import _log_event

INGESTION_LIMIT = timedelta(hours=24)
_ACTIVE = frozenset({"STARTING", "IN_PROGRESS", "STOPPING"})
_FAILED_DOCUMENT = frozenset({"FAILED", "METADATA_UPDATE_FAILED"})
_EXPIRED_LEASE = "1970-01-01T00:00:00.000Z"
_KEPT = (
    "status",
    "manifestHash",
    "bytes",
    "documents",
    "sources",
    "syncedAt",
    "lastJobs",
    "problems",
    "blocked",
    "failure",
    "failedKeys",
    "deletionShortfall",
    "progress",
)
_OPEN = ("jobs", "pending", "expectedDeletions", "jobStartedAt", "stopRequested")
_STOP_IGNORED = frozenset({"ConflictException", "ResourceNotFoundException", "ValidationException"})

Clock = Callable[[], datetime]


class _IngestionBusy(Exception):
    """The service rejected a start and no running job could be adopted."""


def run(
    event: dict[str, Any],
    _context: Any = None,
    *,
    loader: kb_sync.Loader | None = None,
    agent: Any = None,
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Poll a sync that is already running, or decide whether a new one may start."""
    moment = (clock or timeutil.utc_now)()
    state = store.get(kb_sync.STATE_PK, kb_sync.STATE_SK) or {}
    refusal = _owner_refusal(event)
    if refusal:
        return _pack(False, "failed", error=refusal)
    if _flag(event, "stop"):
        if not state.get("jobs"):
            return _pack(False, "failed", error="no sync is running")
        return _stop(state, agent or _agent())
    if state.get("jobs"):
        return _poll(state, agent or _agent(), moment)
    if str(event.get("trigger") or "") != "manual" and not kb_sync.started_once(state):
        return _pack(True, "awaiting_first_sync")
    if str(event.get("by") or "").startswith("apikey:") and not kb_sync.started_once(state):
        return _pack(False, "failed", error="the owner starts the first sync")
    built = kb_sync.manifest((loader or kb_sync._load)())
    cleaned, found = kb_sync.syncable(built)
    choice = kb_sync.decide(cleaned, state, confirm=_flag(event, "confirmDeletion"))
    if found and choice["status"] == "start" and not cleaned["documents"] and not cleaned["sidecars"]:
        choice = {"status": "unchanged"}
    if found:
        choice = {**choice, "problems": found}
    if choice["status"] != "start":
        _remember(state, choice, moment)
        result = _pack(choice["status"] == "unchanged", choice["status"], **_choice_fields(choice))
        _log_event("info", tag="kb_sync", status=choice["status"], detail=result["message"])
        return result
    return _start(cleaned, choice, state, agent or _agent(), moment)


def _start(
    built: dict[str, Any], choice: dict[str, Any], state: dict[str, Any], agent: Any, moment: datetime
) -> dict[str, Any]:
    ids = kb_sync._source_ids()
    knowledge_base = _knowledge_base()
    if ids is None or not knowledge_base:
        return _pack(False, "failed", error="knowledge base is not configured")
    jobs: dict[str, str] = {}
    try:
        for prefix in choice["prefixes"]:
            jobs[prefix] = _begin(agent, knowledge_base, ids[prefix], _token(built, prefix, state))
    except _IngestionBusy:
        if not jobs:
            return _pack(False, "failed", error="ingestion already running")
    except Exception:
        if not jobs:
            raise
    _save_running(state, built, choice, jobs, moment)
    _log_event("info", tag="kb_sync", status="running", sources=len(jobs))
    return _pack(True, "running", prefixes=list(jobs), **_choice_fields(choice))


def _poll(state: dict[str, Any], agent: Any, moment: datetime) -> dict[str, Any]:
    knowledge_base = _knowledge_base()
    ids = kb_sync._source_ids() or {}
    seen: dict[str, dict[str, Any]] = {}
    for prefix, job_id in (state.get("jobs") or {}).items():
        response = agent.get_ingestion_job(
            knowledgeBaseId=knowledge_base,
            dataSourceId=ids.get(prefix, ""),
            ingestionJobId=job_id,
        )
        seen[prefix] = response["ingestionJob"]
    if any(item.get("status") in _ACTIVE for item in seen.values()):
        message = "running"
        if state.get("stopRequested") or _stale(state, moment):
            _request_stop(state, agent)
            message = "stopping"
        _job_row("running", _EXPIRED_LEASE)
        store.put(
            _row(state, progress=_progress_counts(seen), updatedAt=timeutil.format_iso_millis(moment))
        )
        return _pack(True, "running", message=message)
    if any(item.get("status") != "COMPLETE" for item in seen.values()):
        _close_failed(state, seen, agent, moment)
        _job_row("failed", None)
        named = ", ".join(
            f"{prefix} {item.get('status') or 'UNKNOWN'}"
            for prefix, item in seen.items()
            if item.get("status") != "COMPLETE"
        )
        _log_event("warning", tag="kb_sync", status="failed")
        return _pack(False, "failed", error=f"ingestion failed: {named}")
    return _close_done(state, seen, agent, moment)


def _stop(state: dict[str, Any], agent: Any) -> dict[str, Any]:
    _request_stop(state, agent)
    _job_row("running", _EXPIRED_LEASE)
    return _pack(True, "running", message="stopping")


def _request_stop(state: dict[str, Any], agent: Any) -> None:
    state["stopRequested"] = True
    store.put(_row(state, stopRequested=True, updatedAt=timeutil.now_iso()))
    knowledge_base = _knowledge_base()
    ids = kb_sync._source_ids() or {}
    for prefix, job_id in (state.get("jobs") or {}).items():
        try:
            agent.stop_ingestion_job(
                knowledgeBaseId=knowledge_base,
                dataSourceId=ids.get(prefix, ""),
                ingestionJobId=job_id,
            )
        except Exception as exc:
            code = _error_code(exc)
            if code not in _STOP_IGNORED:
                _log_event("warning", tag="kb_sync", status="stop_failed", error=code or type(exc).__name__)


def _save_running(
    state: dict[str, Any], built: dict[str, Any], choice: dict[str, Any], jobs: dict[str, str], moment: datetime
) -> None:
    store.put(
        _row(
            state,
            status="running",
            jobs=jobs,
            pending=kb_sync.snapshot(built),
            expectedDeletions={prefix: choice["expectedDeletions"].get(prefix, 0) for prefix in jobs},
            jobStartedAt=state.get("jobStartedAt") or timeutil.format_iso_millis(moment),
            problems=choice.get("problems") or None,
            progress={"scanned": 0, "indexed": 0, "failed": 0},
            blocked=None,
            failure=None,
            updatedAt=timeutil.format_iso_millis(moment),
        )
    )
    _job_row("running", _EXPIRED_LEASE)


def _close_failed(state: dict[str, Any], seen: dict[str, dict[str, Any]], agent: Any, moment: datetime) -> None:
    """Keep every folder whose job completed, and clear the rest so a retry starts only those."""
    complete = {prefix: item for prefix, item in seen.items() if item.get("status") == "COMPLETE"}
    pending = (state.get("pending") or {}).get("sources") or {}
    sources = dict(state.get("sources") or {})
    for prefix in complete:
        if isinstance(pending.get(prefix), dict):
            sources[prefix] = pending[prefix]
    failed_keys: list[str] = []
    shortfall: dict[str, int] = {}
    if complete:
        failed_keys, shortfall = _outcomes(state, complete, agent)
    last = dict(state.get("lastJobs") or {})
    last.update({prefix: job_id for prefix, job_id in (state.get("jobs") or {}).items()})
    updates: dict[str, Any] = {
        "status": "failed",
        "lastJobs": last,
        "failure": {"jobs": {prefix: str(item.get("status") or "") for prefix, item in seen.items()}},
        "jobs": None,
        "pending": None,
        "expectedDeletions": None,
        "jobStartedAt": None,
        "stopRequested": None,
        "progress": None,
        "updatedAt": timeutil.format_iso_millis(moment),
    }
    if sources:
        updates["sources"] = sources
    if complete:
        updates["syncedAt"] = timeutil.format_iso_millis(moment)
    if failed_keys:
        updates["failedKeys"] = failed_keys
    if shortfall:
        updates["deletionShortfall"] = shortfall
    store.put(_row(state, **updates))


def _close_done(state: dict[str, Any], seen: dict[str, dict[str, Any]], agent: Any, moment: datetime) -> dict[str, Any]:
    sources, fully = _sources_after(state)
    last = dict(state.get("lastJobs") or {})
    last.update(state.get("jobs") or {})
    failed, shortfall = _outcomes(state, seen, agent)
    pending = state.get("pending") or {}
    updates: dict[str, Any] = {
        "status": "done",
        "sources": sources,
        "lastJobs": last,
        "syncedAt": timeutil.format_iso_millis(moment),
        "jobs": None,
        "pending": None,
        "expectedDeletions": None,
        "jobStartedAt": None,
        "stopRequested": None,
        "progress": None,
        "failure": None,
        "blocked": None,
        "failedKeys": failed or None,
        "deletionShortfall": shortfall or None,
        "updatedAt": timeutil.format_iso_millis(moment),
    }
    if fully:
        updates["manifestHash"] = pending.get("manifestHash")
        updates["bytes"] = pending.get("bytes")
        updates["documents"] = pending.get("documents")
    store.put(_row(state, **updates))
    _job_row("done", None)
    _log_event("info", tag="kb_sync", status="done", failed=len(failed))
    return _pack(True, "done", failedKeys=failed, deletionShortfall=shortfall or None)


def _sources_after(state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    pending = (state.get("pending") or {}).get("sources") or {}
    sources = dict(state.get("sources") or {})
    jobs = state.get("jobs") or {}
    empty = {"hash": kb_sync._digest([]), "keys": []}
    for prefix in kb_sync.PREFIXES:
        pending_source = pending.get(prefix)
        if prefix in jobs and isinstance(pending_source, dict):
            sources[prefix] = pending_source
        elif prefix not in sources and pending_source == empty:
            sources[prefix] = empty
    fully = all(sources.get(prefix) == pending.get(prefix) for prefix in kb_sync.PREFIXES)
    return sources, fully


def _outcomes(state: dict[str, Any], seen: dict[str, dict[str, Any]], agent: Any) -> tuple[list[str], dict[str, int]]:
    failed: list[str] = []
    shortfall: dict[str, int] = {}
    expected = state.get("expectedDeletions") or {}
    ids = kb_sync._source_ids() or {}
    knowledge_base = _knowledge_base()
    for prefix, item in seen.items():
        deleted = int((item.get("statistics") or {}).get("numberOfDocumentsDeleted") or 0)
        if int(expected.get(prefix) or 0) > deleted:
            shortfall[prefix] = int(expected[prefix]) - deleted
        failed.extend(_failed_keys(agent, knowledge_base, ids.get(prefix, "")))
    return sorted(set(failed)), shortfall


def _remember(state: dict[str, Any], choice: dict[str, Any], moment: datetime) -> None:
    updates: dict[str, Any] = {
        "updatedAt": timeutil.format_iso_millis(moment),
        "problems": choice.get("problems") or None,
    }
    status = str(choice["status"])
    if status in {"blocked_deletion", "blocked_size"}:
        blocked: dict[str, Any] = {"status": status}
        if status == "blocked_deletion":
            blocked["deletions"] = choice["deletions"]
        else:
            blocked["bytes"] = choice["bytes"]
            blocked["cap"] = choice["cap"]
        updates["blocked"] = blocked
        updates["status"] = status
    else:
        updates["blocked"] = None
    store.put(_row(state, **updates))


def _row(state: dict[str, Any], **updates: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"pk": kb_sync.STATE_PK, "sk": kb_sync.STATE_SK}
    for key in (*_KEPT, *_OPEN):
        if key in state:
            item[key] = state[key]
    item.update(updates)
    return {key: value for key, value in item.items() if value is not None}


def _token(built: dict[str, Any], prefix: str, state: dict[str, Any]) -> str:
    rows = kb_sync._rows(built, prefix)
    previous = str((state.get("lastJobs") or {}).get(prefix) or "")
    if previous:
        rows = [*rows, f"job\t{previous}"]
    return kb_sync._digest(rows)[:40]


def _flag(event: dict[str, Any], name: str) -> bool:
    if event.get(name) is True:
        return True
    params = event.get("params")
    return isinstance(params, dict) and params.get(name) is True


def _owner_refusal(event: dict[str, Any]) -> str:
    if not str(event.get("by") or "").startswith("apikey:"):
        return ""
    if _flag(event, "confirmDeletion"):
        return "only the owner can confirm a deletion"
    if _flag(event, "stop"):
        return "only the owner can stop a sync"
    return ""


def _pack(ok: bool, status: str, *, message: str = "", error: str = "", **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": ok, "status": status}
    payload.update({key: value for key, value in extra.items() if value is not None})
    if error:
        payload["error"] = error
    payload["message"] = message or _detail(payload)
    if not ok and "error" not in payload:
        payload["error"] = payload["message"]
    return payload


def _choice_fields(choice: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in choice.items() if key not in {"status", "prefixes"}}


def _detail(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "")
    found = payload.get("problems") if isinstance(payload.get("problems"), list) else []
    if status == "blocked_deletion":
        parts = [
            f"{item['prefix']} {item['gone']} of {item['previous']}"
            for item in payload.get("deletions") or []
            if isinstance(item, dict)
        ]
        text = "blocked_deletion: " + ", ".join(parts)
    elif status == "blocked_size":
        text = f"blocked_size: {payload.get('bytes')} of {payload.get('cap')}"
    elif status == "done" and payload.get("failedKeys"):
        text = f"{len(payload['failedKeys'])} documents failed"
    elif found:
        text = _problem_text(found)
    elif payload.get("error"):
        text = str(payload["error"])
    else:
        text = status
    if found and status in {"blocked_deletion", "blocked_size"}:
        text = f"{text}; {_problem_text(found)}"
    return text[:300]


def _problem_text(found: list[dict[str, str]]) -> str:
    shown = ", ".join(f"{item['key']} {item['problem']}" for item in found[:8])
    extra = len(found) - 8
    suffix = f" (+{extra} more)" if extra > 0 else ""
    return f"problems: {shown}{suffix}"


def _progress_counts(seen: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Scanned, indexed, and failed documents across the running ingestion jobs."""
    scanned = indexed = failed = 0
    for item in seen.values():
        raw_stats = item.get("statistics")
        stats = raw_stats if isinstance(raw_stats, dict) else {}
        scanned += _stat(stats.get("numberOfDocumentsScanned"))
        indexed += _stat(stats.get("numberOfNewDocumentsIndexed"))
        indexed += _stat(stats.get("numberOfModifiedDocumentsIndexed"))
        failed += _stat(stats.get("numberOfDocumentsFailed"))
    return {"scanned": scanned, "indexed": indexed, "failed": failed}


def _stat(value: Any) -> int:
    from decimal import Decimal

    if type(value) is int:
        return value
    if isinstance(value, Decimal) and value == int(value):
        return int(value)
    return 0


def _knowledge_base() -> str:
    import os

    return os.environ.get("KNOWLEDGE_BASE_ID", "")


def _agent() -> Any:
    import boto3

    return boto3.client("bedrock-agent")


def _begin(agent: Any, knowledge_base: str, source_id: str, token: str) -> str:
    try:
        response = agent.start_ingestion_job(
            knowledgeBaseId=knowledge_base,
            dataSourceId=source_id,
            clientToken=token,
        )
    except Exception as exc:
        if _error_code(exc) != "ConflictException":
            raise
        adopted = _running_job(agent, knowledge_base, source_id)
        if not adopted:
            raise _IngestionBusy() from exc
        return adopted
    return str(response["ingestionJob"]["ingestionJobId"])


def _running_job(agent: Any, knowledge_base: str, source_id: str) -> str:
    response = agent.list_ingestion_jobs(knowledgeBaseId=knowledge_base, dataSourceId=source_id, maxResults=20)
    for item in response.get("ingestionJobSummaries") or []:
        if item.get("status") in {"STARTING", "IN_PROGRESS"}:
            return str(item.get("ingestionJobId") or "")
    return ""


def _failed_keys(agent: Any, knowledge_base: str, source_id: str) -> list[str]:
    found: list[str] = []
    # Empty pagination cursor, not a password.
    token = ""  # nosec B105
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


def _stale(state: dict[str, Any], moment: datetime) -> bool:
    started = timeutil.parse_iso(state.get("jobStartedAt"))
    if started is None:
        return False
    return moment - started >= INGESTION_LIMIT


def _job_row(status: str, lease: str | None) -> None:
    item: dict[str, Any] = {
        "pk": f"JOB#{kb_sync.JOB}",
        "sk": "STATE",
        "status": status,
        "gsi1pk": "JOBSTATE",
        "gsi1sk": kb_sync.JOB,
        "updatedAt": timeutil.now_iso(),
    }
    if lease is not None:
        item["leaseUntil"] = lease
    store.put(item)


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return str((response.get("Error") or {}).get("Code") or "")
    return ""
