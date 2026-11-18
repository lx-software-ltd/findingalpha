"""Retrieval evaluation, with the questions and the client stubbed."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import kb_eval

NOW = datetime(2026, 11, 18, 2, 30, tzinfo=timezone.utc)


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
        self.patch = patch("kb_eval.store.put", self.store.put)
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()

    def test_hits_are_counted_at_eight_and_at_three(self) -> None:
        caches: list[dict] = []

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
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["hitAt8"], 2)
        self.assertEqual(result["hitAt3"], 1)
        self.assertEqual(result["message"], "2 of 3 at 8, 1 of 3 at 3")
        saved = self.store.item or {}
        self.assertEqual([row["rank"] for row in saved["results"]], [2, 5, None])
        self.assertEqual(caches[0], caches[1])
        self.assertNotIn("return on invested capital", str(saved))
        self.assertNotIn("formula", str(saved))

    def test_a_missing_file_does_not_retrieve(self) -> None:
        def retrieve(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            raise AssertionError("retrieved")

        result = kb_eval.run(loader=lambda: None, retrieve=retrieve, clock=lambda: NOW)
        self.assertEqual(result["error"], "questions file is missing")
        self.assertIsNone(self.store.item)

    def test_the_same_question_uses_one_cache(self) -> None:
        seen: list[dict] = []

        def retrieve(_query: str, cache: dict | None = None, **_kwargs: Any) -> list[dict[str, Any]]:
            seen.append(cache)
            return [_passage("example.pdf", "return on invested capital")]

        kb_eval.run(loader=lambda: [_question("one"), _question("one")], retrieve=retrieve, clock=lambda: NOW)
        self.assertIs(seen[0], seen[1])
