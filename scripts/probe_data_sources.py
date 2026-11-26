#!/usr/bin/env python3
"""Re-run the M04-T01 shape probe.

Reads ALPACA_PAPER_KEY_ID, ALPACA_PAPER_SECRET_KEY, and SEC_CONTACT_EMAIL
from the environment. Prints status codes, field names, and counts.
Does not print the keys, the contact address, prices, or article text.
Not part of CI.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

KEY = os.environ["ALPACA_PAPER_KEY_ID"]
SECRET = os.environ["ALPACA_PAPER_SECRET_KEY"]
CONTACT = os.environ["SEC_CONTACT_EMAIL"]
ALPACA = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET, "Accept": "application/json"}
SEC = {"User-Agent": f"findingalpha {CONTACT}", "Accept": "application/json,text/plain"}


def _redact(text: str) -> str:
    for secret in (KEY, SECRET, CONTACT):
        if secret:
            text = text.replace(secret, "[redacted]")
    return text[:240]


def fetch(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("only https URLs are fetched")
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(request, timeout=120) as response:  # nosec B310
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def keys(value: object) -> list[str] | str:
    if isinstance(value, dict):
        return sorted(str(name) for name in value)
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def bars(symbols: str, start: str, end: str, feed: str) -> dict[str, object]:
    query = urllib.parse.urlencode(
        {
            "symbols": symbols,
            "timeframe": "1Day",
            "start": start,
            "end": end,
            "adjustment": "raw",
            "feed": feed,
            "limit": "2",
        }
    )
    status, body = fetch(f"https://data.alpaca.markets/v2/stocks/bars?{query}", ALPACA)
    if status != 200:
        return {"status": status, "error": _redact(body.decode("utf-8", "replace"))}
    payload = json.loads(body)
    found = payload.get("bars") or {}
    summary: dict[str, object] = {
        "status": status,
        "symbols": sorted(found) if isinstance(found, dict) else keys(found),
        "next": bool(payload.get("next_page_token")),
    }
    if isinstance(found, dict):
        summary["counts"] = {symbol: len(rows) for symbol, rows in found.items()}
        summary["volume_positive"] = {
            symbol: bool(rows and isinstance(rows[0].get("v"), (int, float)) and rows[0]["v"] > 0)
            for symbol, rows in found.items()
        }
    return summary


def main() -> None:
    report: dict[str, object] = {}
    status, body = fetch(
        "https://paper-api.alpaca.markets/v2/calendar?start=2026-11-01&end=2026-11-14",
        ALPACA,
    )
    calendar = json.loads(body) if status == 200 else []
    report["calendar"] = {
        "status": status,
        "count": len(calendar) if isinstance(calendar, list) else None,
        "item_keys": keys(calendar[0]) if calendar else _redact(body.decode("utf-8", "replace")),
    }
    last = calendar[-1]["date"] if calendar else "2024-06-03"
    report["bars_sip"] = bars("AAPL,SPY", last, last, "sip")
    report["bars_iex"] = bars("AAPL", last, last, "iex")
    report["bars_2016_sip"] = bars("AAPL,SPY", "2016-01-04", "2016-01-04", "sip")
    report["bars_2016_iex"] = bars("AAPL", "2016-01-04", "2016-01-04", "iex")

    query = urllib.parse.urlencode(
        {
            "types": "cash_dividend,forward_split,reverse_split",
            "start": "2024-06-10",
            "end": "2024-06-10",
            "limit": "1000",
        }
    )
    status, body = fetch(f"https://data.alpaca.markets/v1/corporate-actions?{query}", ALPACA)
    if status == 200:
        payload = json.loads(body)
        groups = payload.get("corporate_actions") or {}
        rows = [row for group in groups.values() if isinstance(group, list) for row in group]
        report["corporate_actions"] = {
            "status": status,
            "count": len(rows),
            "groups": sorted(groups),
            "process_date_matches": sum(1 for row in rows if row.get("process_date") == "2024-06-10"),
            "ex_date_matches": sum(1 for row in rows if row.get("ex_date") == "2024-06-10"),
            "dividend_keys": keys(next((row for row in rows if "rate" in row), {})),
            "has_new_symbol_field": any("new_symbol" in row for row in rows),
        }
    else:
        report["corporate_actions"] = {"status": status, "error": _redact(body.decode("utf-8", "replace"))}

    status, body = fetch("https://www.sec.gov/files/company_tickers_exchange.json", SEC)
    if status == 200:
        payload = json.loads(body)
        report["sec_tickers"] = {
            "status": status,
            "fields": payload.get("fields"),
            "rows": len(payload.get("data") or []),
        }
    else:
        report["sec_tickers"] = {"status": status, "error": _redact(body.decode("utf-8", "replace"))}
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
