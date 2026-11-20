"""The quote checker matches across line breaks and lists register citations."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parent / "check_methodology_quotes.py"
    spec = importlib.util.spec_from_file_location("check_methodology_quotes", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


quotes = _load()


class CheckMethodologyQuotesTest(unittest.TestCase):
    def test_a_quote_matches_across_line_breaks(self) -> None:
        page = "pull in all outliers in the Xn,k(t) to ±3\nstandard deviations about the mean."
        quote = "pull in all outliers in the Xn,k(t) to ±3 standard deviations about the mean."
        self.assertTrue(quotes.quote_on_page(quote, page))
        self.assertFalse(quotes.quote_on_page("a sentence that is not on the page", page))

    def test_citations_skip_entries_without_one(self) -> None:
        found = quotes.citations(
            {
                "factors": [
                    {"id": "roic", "citation": {"document": "Book.pdf", "locator": "1", "quote": "ROIC"}},
                    {"id": "accruals", "citation": None},
                ],
                "composite": {"citation": {"document": "Grinold.pdf", "locator": "255", "quote": "±3"}},
                "screen": {"citation": None},
            }
        )
        self.assertEqual([label for label, _citation in found], ["roic", "composite"])


if __name__ == "__main__":
    unittest.main()
