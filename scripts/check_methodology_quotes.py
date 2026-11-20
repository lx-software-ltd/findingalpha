#!/usr/bin/env python3
"""Confirm each register quote appears on its PDF page.

The textbooks stay out of the repository. Pass the directory that holds
the PDF file names stored in the register:

    python3 scripts/check_methodology_quotes.py /path/to/pdfs

Exit 2 when a file or extractor is missing. Exit 1 when a quote is not
on that page. Locator is the 1-based PDF page number.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "contracts" / "methodology.json"


def normalised(text: str) -> str:
    return " ".join(text.split())


def quote_on_page(quote: str, page_text: str) -> bool:
    """True when ``quote`` appears in ``page_text``, ignoring line breaks."""
    return normalised(quote) in normalised(page_text)


def citations(doc: dict) -> list[tuple[str, dict]]:
    """``(label, citation)`` for every entry that carries a citation."""
    found: list[tuple[str, dict]] = []
    for factor in doc.get("factors") or []:
        citation = factor.get("citation")
        if isinstance(citation, dict):
            found.append((str(factor.get("id")), citation))
    for name in ("universe", "composite", "screen", "fundamentals", "backtest"):
        block = doc.get(name)
        citation = block.get("citation") if isinstance(block, dict) else None
        if isinstance(citation, dict):
            found.append((name, citation))
    return found


def extract_page(pdf: Path, page: int) -> str:
    """Text of one 1-based page. Prefers pypdf, then pdftotext."""
    try:
        from pypdf import PdfReader
    except ImportError:
        extractor = None
    else:
        extractor = PdfReader
    if extractor is not None:
        reader = extractor(str(pdf))
        if page < 1 or page > len(reader.pages):
            raise ValueError(f"{pdf.name} has no page {page}")
        return reader.pages[page - 1].extract_text() or ""
    if shutil.which("pdftotext") is None:
        raise RuntimeError("neither pypdf nor pdftotext is available")
    completed = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), "-enc", "UTF-8", str(pdf), "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"pdftotext failed for {pdf.name}")
    return completed.stdout


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 scripts/check_methodology_quotes.py <pdf-directory>", file=sys.stderr)
        return 2
    folder = Path(argv[1])
    doc = json.loads(REGISTER.read_text(encoding="utf-8"))
    missing = False
    failed = False
    for label, citation in citations(doc):
        document = str(citation.get("document") or "")
        quote = str(citation.get("quote") or "")
        try:
            page = int(str(citation.get("locator") or ""))
        except ValueError:
            print(f"{label}: locator {citation.get('locator')!r} is not a page number")
            failed = True
            continue
        pdf = folder / document
        if not pdf.is_file():
            print(f"{label}: missing {pdf}")
            missing = True
            continue
        try:
            text = extract_page(pdf, page)
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"{label}: {exc}")
            missing = True
            continue
        if quote_on_page(quote, text):
            print(f"{label}: page {page} contains the quote")
        else:
            print(f"{label}: quote not on page {page} of {document}")
            failed = True
    if missing:
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
