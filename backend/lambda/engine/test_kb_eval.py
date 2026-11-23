"""Retrieval evaluation, with the questions and the client stubbed."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any, Protocol
from unittest.mock import patch

import kb_eval

NOW = datetime(2026, 11, 18, 2, 30, tzinfo=timezone.utc)


class _Patch(Protocol):
    def start(self) -> Any: ...

    def stop(self) -> None: ...


def _question(name: str, text: str = "return on invested capital") -> dict[str, Any]:
    return {
        "id": name,
        "question": f"how is {name} defined",
        "expectedDocument": "example.pdf",
        "expectedText": text,
        "page": 12,
        "formula": "a formula that is not scored",
    }


def _passage(document: str, text: str, index: int = 0) -> dict[str, Any]:
    return {"document": document, "text": text, "locator": "", "score": 0.2, "sourceType": "theory"}


class _Store:
    def __init__(self) -> None:
        self.item: dict[str, Any] | None = None

    def put(self, item: dict[str, Any]) -> None:
        self.item = dict(item)


class KbEvalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _Store()
        self.state: dict[str, Any] = {"manifestHash": "done"}
        self.patches: list[_Patch] = [
            patch("kb_eval.store.put", self.store.put),
            patch("kb_eval.store.get", lambda _pk, _sk: dict(self.state) if self.state else None),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in self.patches:
            item.stop()

    def test_hits_are_counted_at_eight_and_at_three(self) -> None:
        caches: list[dict[Any, Any] | None] = []

        def retrieve(query: str, cache: dict | None = None, **_kwargs: Any) -> list[dict[str, Any]]:
            del query
            caches.append(cache)
            if len(caches) == 1:
                return [_passage("other.pdf", "no"), _passage("example.pdf", "Return   on\ninvested capital")]
            if len(caches) == 2:
                return [_passage("example.pdf", "unrelated")] * 4 + [
                    _passage("example.pdf", "return on invested capital")
                ]
            return [_passage("example.pdf", "nothing like it")]

        result = kb_eval.run(
            loader=lambda: [_question("one"), _question("two"), _question("three")],
            retrieve=retrieve,
            clock=lambda: NOW,
        )
        self.assertEqual(result["status"], "below_target")
        self.assertEqual(result["hitAt8"], 2)
        self.assertEqual(result["hitAt3"], 1)
        self.assertEqual(result["error"], "below target: 2 of 3 at 8, 1 of 3 at 3")
        saved = self.store.item or {}
        self.assertEqual([row["rank"] for row in saved["results"]], [2, 5, None])
        self.assertEqual(caches[0], caches[1])
        self.assertNotIn("return on invested capital", str(saved))
        self.assertNotIn("formula", str(saved))

    def test_the_targets_are_a_plain_success(self) -> None:
        plan = [1] * 12 + [5] * 4 + [None] * 4
        seen: list[int] = []

        def retrieve(_query: str, cache: dict | None = None, **_kwargs: Any) -> list[dict[str, Any]]:
            del cache
            rank = plan[len(seen)]
            seen.append(rank or 0)
            if rank is None:
                return [_passage("other.pdf", "no")]
            misses = [_passage("other.pdf", "no")] * (rank - 1)
            return [*misses, _passage("example.pdf", "return on invested capital")]

        questions = [_question(f"q{index:02d}") for index in range(20)]
        result = kb_eval.run(loader=lambda: questions, retrieve=retrieve, clock=lambda: NOW)
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["message"], "16 of 20 at 8, 12 of 20 at 3")

    def test_a_sync_that_has_not_finished_does_not_retrieve(self) -> None:
        self.state.clear()

        def retrieve(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            raise AssertionError("retrieved")

        result = kb_eval.run(loader=lambda: [_question("one")], retrieve=retrieve, clock=lambda: NOW)
        self.assertEqual(result["error"], "the knowledge base has not been synced")
        self.assertIsNone(self.store.item)

    def test_a_missing_file_does_not_retrieve(self) -> None:
        def retrieve(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            raise AssertionError("retrieved")

        result = kb_eval.run(loader=lambda: None, retrieve=retrieve, clock=lambda: NOW)
        self.assertEqual(result["error"], "questions file is missing")
        self.assertIsNone(self.store.item)

    def test_the_same_question_uses_one_cache(self) -> None:
        seen: list[dict[Any, Any] | None] = []

        def retrieve(_query: str, cache: dict | None = None, **_kwargs: Any) -> list[dict[str, Any]]:
            seen.append(cache)
            return [_passage("example.pdf", "return on invested capital")]

        kb_eval.run(loader=lambda: [_question("one"), _question("one")], retrieve=retrieve, clock=lambda: NOW)
        self.assertIs(seen[0], seen[1])
