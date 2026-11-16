"""Daily bars requests that survive one rejected symbol."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

import http_client

logger = logging.getLogger(__name__)

Fetch = Callable[[str, dict[str, str]], Iterator[dict[str, Any]]]
Rows = Callable[[dict[str, Any]], Iterator[dict[str, Any]]]
Shape = dict[tuple[str, str, str], bool]


def bars(
    fetch: Fetch,
    params: dict[str, str],
    symbols: list[str],
    *,
    endpoint: str,
    rows_of: Rows,
    probe: str = "SPY",
) -> Iterator[dict[str, Any]]:
    """Yield bars for ``symbols``.

    A 400 on several symbols is split in half. One symbol is skipped when
    ``probe`` still answers for the same window. A 400 on ``probe`` is raised.
    """
    yield from _batch(fetch, params, symbols, endpoint=endpoint, rows_of=rows_of, probe=probe, shape={})


def _batch(
    fetch: Fetch,
    params: dict[str, str],
    symbols: list[str],
    *,
    endpoint: str,
    rows_of: Rows,
    probe: str,
    shape: Shape,
) -> Iterator[dict[str, Any]]:
    if not symbols:
        return
    query = dict(params)
    query["symbols"] = ",".join(symbols)
    try:
        pages = list(fetch(endpoint, query))
    except http_client.HttpStatusError as exc:
        if exc.status != 400:
            raise
        if len(symbols) > 1:
            if not _probe_ok(fetch, params, endpoint, probe, shape):
                raise
            mid = len(symbols) // 2
            yield from _batch(
                fetch, params, symbols[:mid], endpoint=endpoint, rows_of=rows_of, probe=probe, shape=shape
            )
            yield from _batch(
                fetch, params, symbols[mid:], endpoint=endpoint, rows_of=rows_of, probe=probe, shape=shape
            )
            return
        if symbols[0] != probe and _probe_ok(fetch, params, endpoint, probe, shape):
            logger.info("alpaca bars skipped symbol=%s", symbols[0])
            return
        raise
    shape[_key(params)] = True
    for payload in pages:
        yield from rows_of(payload)


def _key(params: dict[str, str]) -> tuple[str, str, str]:
    return (params.get("start", ""), params.get("end", ""), params.get("adjustment", ""))


def _probe_ok(fetch: Fetch, params: dict[str, str], endpoint: str, probe: str, shape: Shape) -> bool:
    key = _key(params)
    if key in shape:
        return shape[key]
    query = dict(params)
    query["symbols"] = probe
    try:
        list(fetch(endpoint, query))
    except http_client.HttpStatusError as exc:
        if exc.status != 400:
            raise
        shape[key] = False
        return False
    shape[key] = True
    return True
