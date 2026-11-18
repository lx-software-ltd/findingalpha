"""Score retrieval against the questions file in the knowledge base bucket.

A question hits when a passage comes from ``expectedDocument`` and
contains ``expectedText``. The stored result names the rank and the
documents. It does not keep passage text. ``page`` and ``formula`` are
accepted and not scored.
"""

from __future__ import annotations

import os
from typing import Any, Callable

import kb_client
import kb_sync
import s3io
import store
import timeutil

QUESTIONS_KEY = "eval/questions.json"
STATE_PK = "KB#eval"
STATE_SK = "LATEST"
HIT_AT_8 = 16
HIT_AT_3 = 12

Loader = Callable[[], Any]
Ask = Callable[..., list[dict[str, Any]]]


def run(
    _event: dict[str, Any] | None = None,
    _context: Any = None,
    *,
    loader: Loader | None = None,
    retrieve: Ask | None = None,
    clock: kb_client.Clock | None = None,
) -> dict[str, Any]:
    """Retrieve once per question and store the hit counts."""
    if not _synced():
        return {"ok": False, "status": "failed", "error": "the knowledge base has not been synced"}
    questions = (loader or _load)()
    if not isinstance(questions, list) or not questions or any(not isinstance(item, dict) for item in questions):
        return {"ok": False, "status": "failed", "error": "questions file is missing"}
    moment = (clock or timeutil.utc_now)()
    ask = retrieve or kb_client.retrieve
    cache: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    results: list[dict[str, Any]] = []
    for item in questions:
        passages = ask(str(item.get("question") or ""), cache=cache)
        results.append(
            {
                "id": str(item.get("id") or ""),
                "rank": _rank(passages, item),
                "documents": [str(passage.get("document") or "") for passage in passages],
            }
        )
    hit_at_8 = sum(rank is not None and rank <= 8 for rank in (row["rank"] for row in results))
    hit_at_3 = sum(rank is not None and rank <= 3 for rank in (row["rank"] for row in results))
    store.put(
        {
            "pk": STATE_PK,
            "sk": STATE_SK,
            "ranAt": timeutil.format_iso_millis(moment),
            "questions": len(results),
            "hitAt8": hit_at_8,
            "hitAt3": hit_at_3,
            "results": results,
        }
    )
    summary = f"{hit_at_8} of {len(results)} at 8, {hit_at_3} of {len(results)} at 3"
    met = hit_at_8 >= HIT_AT_8 and hit_at_3 >= HIT_AT_3
    if not met:
        return {
            "ok": False,
            "status": "below_target",
            "questions": len(results),
            "hitAt8": hit_at_8,
            "hitAt3": hit_at_3,
            "error": f"below target: {summary}",
        }
    return {
        "ok": True,
        "status": "done",
        "questions": len(results),
        "hitAt8": hit_at_8,
        "hitAt3": hit_at_3,
        "message": summary,
    }


def _synced() -> bool:
    return bool((store.get(kb_sync.STATE_PK, kb_sync.STATE_SK) or {}).get("manifestHash"))


def _load() -> Any:
    from botocore.exceptions import ClientError

    try:
        return s3io.get_json(os.environ["KB_BUCKET_NAME"], QUESTIONS_KEY)
    except ClientError as exc:
        code = str((exc.response.get("Error") or {}).get("Code") or "")
        if code in {"NoSuchKey", "404", "NotFound"}:
            return None
        raise


def _rank(passages: list[dict[str, Any]], item: dict[str, Any]) -> int | None:
    document = str(item.get("expectedDocument") or "")
    expected = _fold(item.get("expectedText"))
    if not document or not expected:
        return None
    for index, passage in enumerate(passages, start=1):
        if passage.get("document") == document and expected in _fold(passage.get("text")):
            return index
    return None


def _fold(value: Any) -> str:
    return " ".join(str(value or "").lower().split())
