"""SEC EDGAR reads.

The User-Agent is ``findingalpha <contact>``. The contact address is
never written to a log. Calls stay at or under five a second.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import http_client
from config import MissingSetting

_DATA = "https://data.sec.gov"
_WWW = "https://www.sec.gov"
_TICKERS = f"{_WWW}/files/company_tickers_exchange.json"
_PER_SECOND = 5
# The SEC answers 403 when a caller is over its rate, not 429.
_RETRY = frozenset({403})
_CLIENT: SecEdgar | None = None


def _pad_cik(cik: str | int) -> str:
    text = str(cik).strip()
    if not text.isdigit():
        raise ValueError("cik must be digits")
    return text.zfill(10)


def _quarter(month: int) -> int:
    return (month - 1) // 3 + 1


def _listing_names(payload: Any) -> set[str]:
    directory = payload.get("directory") if isinstance(payload, dict) else None
    items = directory.get("item") if isinstance(directory, dict) else None
    if isinstance(items, dict):
        items = [items]
    names: set[str] = set()
    for item in items or []:
        if isinstance(item, dict) and item.get("name"):
            names.add(str(item["name"]))
    return names


def parse_master(text: str) -> list[dict[str, str]]:
    """Rows under the dashed line of a daily master index."""
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if len(stripped) >= 10 and set(stripped) == {"-"}:
            start = index + 1
            break
    if start is None:
        return []
    rows: list[dict[str, str]] = []
    for line in lines[start:]:
        if not line.strip():
            continue
        parts = line.split("|", 4)
        if len(parts) != 5:
            continue
        cik, company, form, filed, path = (part.strip() for part in parts)
        if not cik.isdigit():
            continue
        rows.append(
            {
                "cik": cik.zfill(10),
                "company": company,
                "form": form,
                "filed": filed,
                "path": path,
            }
        )
    return rows


class SecEdgar:
    """One client shares the rate limit across its calls."""

    def __init__(
        self,
        *,
        contact: str | None = None,
        opener: http_client.Opener | None = None,
        limiter: Any = None,
    ) -> None:
        if contact is None:
            import os

            contact = os.environ.get("SEC_CONTACT_EMAIL", "")
        self._contact = contact.strip()
        if not self._contact or any(char in self._contact for char in "\r\n"):
            raise MissingSetting("SEC_CONTACT_EMAIL")
        self._opener = opener
        self._limiter = limiter if limiter is not None else http_client.RateLimiter(_PER_SECOND)
        self._quarters: dict[str, set[str]] = {}

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": f"findingalpha {self._contact}"}

    def _text(self, url: str, *, errors: str = "strict", attempts: int = 4) -> str:
        self._limiter.wait()
        return http_client.get_text(
            url,
            self._headers(),
            opener=self._opener,
            retry_on=_RETRY,
            errors=errors,
            attempts=attempts,
        )

    def _json(self, url: str) -> Any:
        self._limiter.wait()
        return http_client.get_json(url, self._headers(), opener=self._opener, retry_on=_RETRY)

    def ticker_map(self) -> dict[str, dict[str, str]]:
        """Ticker to CIK, name and exchange. Blank tickers are skipped."""
        payload = self._json(_TICKERS)
        fields = list(payload.get("fields") or [])
        index = {str(name): position for position, name in enumerate(fields)}
        required = ("cik", "name", "ticker", "exchange")
        if any(name not in index for name in required):
            raise ValueError("ticker file is missing a column")
        found: dict[str, dict[str, str]] = {}
        for row in payload.get("data") or []:
            ticker = str(row[index["ticker"]] or "").strip()
            if not ticker:
                continue
            cik = row[index["cik"]]
            if not str(cik).strip().isdigit():
                continue
            entry = {
                "cik": _pad_cik(cik),
                "name": str(row[index["name"]] or ""),
                "exchange": str(row[index["exchange"]] or ""),
            }
            canonical = ticker.upper()
            found[canonical] = entry
            # Share classes are written with a dash here and sometimes with a dot elsewhere.
            alternate = canonical.replace("-", ".") if "-" in canonical else canonical.replace(".", "-")
            if alternate != canonical and alternate not in found:
                found[alternate] = entry
        return found

    def submissions(self, cik: str | int) -> dict[str, Any]:
        return self._json(f"{_DATA}/submissions/CIK{_pad_cik(cik)}.json")

    def company_facts(self, cik: str | int) -> dict[str, Any]:
        return self._json(f"{_DATA}/api/xbrl/companyfacts/CIK{_pad_cik(cik)}.json")

    def filing(self, cik: str | int, accession: str, document: str) -> str:
        """One primary document. The contact stays in the request header only."""
        folder = str(accession).replace("-", "")
        name = str(document).split("/")[-1]
        url = f"{_WWW}/Archives/edgar/data/{int(_pad_cik(cik))}/{folder}/{name}"
        return self._text(url, errors="fallback")

    def daily_index(self, on: date | str) -> list[dict[str, str]]:
        """The day's master index.

        A 404 is an empty list. A 403 is an empty list when the quarter's
        ``index.json`` does not name the file, which is how a closed SEC
        day answers. A listed file that returns 403 is a real failure.
        """
        day = on if isinstance(on, date) else date.fromisoformat(str(on)[:10])
        name = f"master.{day.strftime('%Y%m%d')}.idx"
        folder = f"{_WWW}/Archives/edgar/daily-index/{day.year}/QTR{_quarter(day.month)}"
        url = f"{folder}/{name}"
        try:
            text = self._text(url, errors="fallback", attempts=1)
        except http_client.HttpStatusError as exc:
            if exc.status == 404:
                return []
            if exc.status == 403 and not self._listed(f"{folder}/index.json", name):
                return []
            if exc.status != 403 and not 500 <= exc.status <= 599:
                raise
            text = self._text(url, errors="fallback")
        return parse_master(text)

    def _listed(self, url: str, filename: str) -> bool:
        """True when the name is in the listing, or when the listing cannot be read."""
        names = self._quarters.get(url)
        if names is None:
            try:
                payload = self._json(url)
            except (http_client.HttpStatusError, TypeError, ValueError):
                return True
            names = _listing_names(payload)
            self._quarters[url] = names
        return filename in names


def _shared() -> SecEdgar:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = SecEdgar()
    return _CLIENT


def ticker_map() -> dict[str, dict[str, str]]:
    return _shared().ticker_map()


def submissions(cik: str | int) -> dict[str, Any]:
    return _shared().submissions(cik)


def company_facts(cik: str | int) -> dict[str, Any]:
    return _shared().company_facts(cik)


def filing(cik: str | int, accession: str, document: str) -> str:
    return _shared().filing(cik, accession, document)


def daily_index(on: date | str) -> list[dict[str, str]]:
    return _shared().daily_index(on)
