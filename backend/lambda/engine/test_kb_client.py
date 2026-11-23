"""Retrieval client, with a stubbed Bedrock runtime."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from typing import Any, Protocol
from unittest.mock import patch

import kb_client

NOW = datetime(2026, 11, 18, 2, 30, tzinfo=timezone.utc)


class _Patch(Protocol):
    def start(self) -> Any: ...

    def stop(self) -> None: ...
_PHRASE = "secret passage words"


def _result(key: str, text: str = _PHRASE, score: float = 0.4, page: float | None = 12.0) -> dict[str, Any]:
    metadata = {} if page is None else {kb_client._PAGE: page}
    return {
        "content": {"text": text},
        "location": {"s3Location": {"uri": f"s3://kb-bucket/{key}"}},
        "score": score,
        "metadata": metadata,
    }


class _Store:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.updates: list[str] = []

    def get(self, pk: str, sk: str) -> dict[str, Any] | None:
        item = self.items.get((pk, sk))
        return dict(item) if item else None

    def update(
        self, pk: str, sk: str, expression: str, values: dict[str, Any], names: dict[str, str] | None = None
    ) -> None:
        del expression, names
        self.updates.append(pk)
        item = self.items.setdefault((pk, sk), {"count": 0})
        delta = int(values.get(":one") or 0) + int(values.get(":minus") or 0)
        item["count"] = int(item.get("count") or 0) + delta

    def update_conditional(
        self,
        pk: str,
        sk: str,
        expression: str,
        values: dict[str, Any],
        condition: str,
        names: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        del expression, condition, names
        current = self.items.get((pk, sk))
        count = int((current or {}).get("count") or 0)
        if current is not None and "count" in current and count >= int(values[":cap"]):
            raise kb_client.store.ConditionNotMet(pk)
        previous = dict(current) if current else None
        self.update(pk, sk, "", {":one": values[":one"]})
        return previous


class _Agent:
    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.results = results if results is not None else [_result("theory/example.pdf")]
        self.fail = False

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("bedrock down")
        return {"retrievalResults": self.results}


class KbClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _Store()
        self.agent = _Agent()
        self.logs: list[dict[str, Any]] = []
        self.env = patch.dict(
            os.environ,
            {
                "KNOWLEDGE_BASE_ID": "KBID123456",
                "KB_DATA_SOURCE_IDS": '{"theory/": "ds-theory", "formula-notes/": "ds-notes", "journal/": "ds-journal"}',
            },
        )
        self.env.start()
        self.patches: list[_Patch] = [
            patch("kb_client.store.get", self.store.get),
            patch("kb_client.store.update", self.store.update),
            patch("kb_client.store.update_conditional", self.store.update_conditional),
            patch("kb_client._log_event", lambda level, **fields: self.logs.append({"level": level, **fields})),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in self.patches:
            item.stop()
        self.env.stop()

    def _retrieve(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        kwargs.setdefault("client", self.agent)
        kwargs.setdefault("clock", lambda: NOW)
        return kb_client.retrieve(*args, **kwargs)

    def test_a_passage_is_mapped_and_counted_once(self) -> None:
        cache: dict = {}
        first = self._retrieve("how is it defined", cache=cache)
        second = self._retrieve("how is it defined", cache=cache)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["document"], "example.pdf")
        self.assertEqual(first[0]["sourceType"], "theory")
        self.assertEqual(first[0]["locator"], "12")
        self.assertEqual(first[0]["score"], 0.4)
        self.assertEqual(len(self.agent.calls), 1)
        self.assertEqual(
            self.agent.calls[0]["retrievalConfiguration"]["managedSearchConfiguration"]["numberOfResults"], 8
        )
        self.assertEqual(self.store.updates, ["USAGE#2026-11", "USAGE#2026-11-18"])
        self.assertNotIn(_PHRASE, str(self.logs))

    def test_a_managed_location_maps_to_the_plain_file_name(self) -> None:
        self.agent.results = [
            {
                "content": {"text": _PHRASE},
                "location": {
                    "s3Location": {
                        "uri": "https://kb-bucket.s3.ap-southeast-1.amazonaws.com/theory/"
                        "Security%20Analysis%2C%20Graham%20%26%20Dodd.pdf"
                    },
                    "type": "S3",
                },
                "score": 0.5,
                "metadata": {"_excerpt_page_number": 437.0, "_data_source_id": "ds-theory"},
            }
        ]
        found = self._retrieve("margin of safety", source_types=["theory"])
        self.assertEqual(found[0]["document"], "Security Analysis, Graham & Dodd.pdf")
        self.assertEqual(found[0]["sourceType"], "theory")
        self.assertEqual(found[0]["locator"], "437")

    def test_the_cap_refuses_at_the_limit(self) -> None:
        self.store.items[("USAGE#2026-11", "KB")] = {"count": 5000}
        with self.assertRaises(kb_client.KbBudgetExceeded):
            self._retrieve("another question")
        self.assertEqual(self.agent.calls, [])
        self.assertEqual(self.store.updates, [])

    def test_the_warn_line_still_allows_the_call(self) -> None:
        self.store.items[("USAGE#2026-11", "KB")] = {"count": 4000}
        self._retrieve("another question")
        self.assertEqual(len(self.agent.calls), 1)
        self.assertEqual(self.logs[0]["status"], "near_cap")

    def test_top_k_and_the_query_are_clamped(self) -> None:
        self._retrieve("x" * 1001, top_k=99)
        sent = self.agent.calls[0]
        self.assertEqual(len(sent["retrievalQuery"]["text"]), 1000)
        self.assertEqual(sent["retrievalConfiguration"]["managedSearchConfiguration"]["numberOfResults"], 12)

    def test_a_folder_filter_uses_the_data_source_id(self) -> None:
        self._retrieve("where is it", source_types=["journal"])
        search = self.agent.calls[0]["retrievalConfiguration"]["managedSearchConfiguration"]
        self.assertEqual(search["filter"], {"in": {"key": "_data_source_id", "value": ["ds-journal"]}})

    def test_results_are_filtered_by_prefix_when_ids_are_missing(self) -> None:
        os.environ.pop("KB_DATA_SOURCE_IDS")
        self.agent.results = [_result("theory/example.pdf"), _result("journal/note.md", page=None)]
        found = self._retrieve("where is it", source_types=["journal"])
        self.assertNotIn("filter", self.agent.calls[0]["retrievalConfiguration"]["managedSearchConfiguration"])
        self.assertEqual([item["document"] for item in found], ["note.md"])
        self.assertEqual(found[0]["locator"], "")

    def test_a_failed_call_releases_the_reservation(self) -> None:
        self.agent.fail = True
        with self.assertRaises(RuntimeError):
            self._retrieve("how is it defined")
        self.assertEqual(self.store.items[("USAGE#2026-11", "KB")]["count"], 0)
        self.assertEqual(self.store.updates, ["USAGE#2026-11", "USAGE#2026-11"])

    def test_an_unknown_folder_does_not_call(self) -> None:
        self.assertEqual(self._retrieve("where is it", source_types=["scans"]), [])
        self.assertEqual(self.agent.calls, [])
        self.assertEqual(self.store.updates, [])
