"""Alpaca client against invented fixtures. No network."""

from __future__ import annotations

import io
import json
import logging
import os
import unittest
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import alpaca_bars
import alpaca_data
import http_client
import secrets_read

_FIXTURES = Path(__file__).resolve().parent / "test_fixtures"
_KEY = "kid"
_SECRET = "sek"  # nosec B105


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


class _Limiter:
    def __init__(self) -> None:
        self.calls = 0

    def wait(self) -> None:
        self.calls += 1


class _Script:
    def __init__(self, bodies: list[bytes]) -> None:
        self._bodies = list(bodies)
        self.urls: list[str] = []
        self.headers: list[tuple[str | None, str | None]] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> _Response:
        del timeout
        self.urls.append(request.full_url)
        self.headers.append((request.get_header("Apca-api-key-id"), request.get_header("Apca-api-secret-key")))
        if not self._bodies:
            raise AssertionError(request.full_url)
        return _Response(self._bodies.pop(0))


def _load(name: str) -> bytes:
    return (_FIXTURES / name).read_bytes()


def _query(url: str) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)


def _allow() -> bool:
    return True


def _status(status: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.com/x", status, "err", Message(), io.BytesIO(body))


def _client(
    *bodies: bytes, ingest_enabled: Callable[[], bool] | None = _allow
) -> tuple[alpaca_data.AlpacaData, _Script, _Limiter]:
    script = _Script(list(bodies))
    limiter = _Limiter()
    client = alpaca_data.AlpacaData(
        key_id=_KEY,
        secret_key=_SECRET,
        opener=script,
        limiter=limiter,
        ingest_enabled=ingest_enabled,
    )
    return client, script, limiter


class _SecretClient:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.ids: list[str] = []

    def get_secret_value(self, SecretId: str) -> dict[str, str]:
        self.ids.append(SecretId)
        return {"SecretString": self.payload}


class AlpacaDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self._reset()
        self._secret_env = os.environ.pop("ALPACA_SECRET_ID", None)

    def tearDown(self) -> None:
        self._reset()
        if self._secret_env is None:
            os.environ.pop("ALPACA_SECRET_ID", None)
        else:
            os.environ["ALPACA_SECRET_ID"] = self._secret_env

    def _reset(self) -> None:
        alpaca_data._CLIENT = None
        alpaca_data._LIMITER = None
        alpaca_data._SECRET_CLIENT = None
        alpaca_data._OPENER = None
        alpaca_data._INGEST = None
        alpaca_data._RESERVE = None
        alpaca_data._HOLD = False
        secrets_read.clear_cache()

    def test_list_assets_maps_our_fields(self) -> None:
        client, script, limiter = _client(_load("alpaca_assets.json"))
        assets = client.list_assets()
        self.assertEqual([row["symbol"] for row in assets], ["EXMPL", "SECND"])
        self.assertEqual(assets[0]["name"], "EXAMPLE INDUSTRIES INC")
        self.assertEqual(assets[0]["exchange"], "NASDAQ")
        self.assertTrue(assets[0]["tradable"])
        self.assertTrue(assets[0]["marginable"])
        self.assertFalse(assets[0]["fractionable"])
        self.assertEqual(assets[0]["assetClass"], "us_equity")
        self.assertFalse(assets[1]["marginable"])
        self.assertFalse(assets[1]["tradable"])
        query = _query(script.urls[0])
        self.assertTrue(script.urls[0].startswith(f"{alpaca_data._PAPER}/v2/assets?"))
        self.assertEqual(query["status"], ["active"])
        self.assertEqual(query["asset_class"], ["us_equity"])
        self.assertEqual(script.headers[0], (_KEY, _SECRET))
        self.assertEqual(limiter.calls, 1)
        self.assertEqual(assets[0]["id"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(assets[1]["id"], "")

    def test_a_held_check_skips_the_kill_switch(self) -> None:
        body = _load("alpaca_assets.json")
        client, script, _limiter = _client(body, body, ingest_enabled=None)
        calls = {"count": 0}

        def enabled(_name: str) -> bool:
            calls["count"] += 1
            return True

        with patch("kill_switch.is_enabled", enabled), alpaca_data.hold_ingest_check():
            client.list_assets()
            client.list_assets()
        self.assertEqual(calls["count"], 0)
        self.assertEqual(len(script.urls), 2)

    def test_inactive_assets_and_a_bad_status(self) -> None:
        client, script, limiter = _client(_load("alpaca_assets.json"))
        self.assertEqual(client.list_assets("inactive")[0]["symbol"], "EXMPL")
        self.assertEqual(_query(script.urls[0])["status"], ["inactive"])
        with self.assertRaises(ValueError):
            client.list_assets("all")
        self.assertEqual(limiter.calls, 1)
        broken, _broken_script, _broken_limiter = _client(b'{"bars":{}}')
        with self.assertRaises(ValueError):
            broken.list_assets()

    def test_daily_bars_use_the_new_york_date_and_the_next_page(self) -> None:
        client, script, limiter = _client(_load("alpaca_bars_page1.json"), _load("alpaca_bars_page2.json"))
        bars = list(client.daily_bars(["aapl", "AAPL", " "], "2016-01-04", "2024-06-03", "raw"))
        self.assertEqual(
            bars,
            [
                {
                    "symbol": "EXMPL",
                    "date": "2024-06-03",
                    "open": 10.5,
                    "high": 11,
                    "low": 10,
                    "close": 10.25,
                    "volume": 1000,
                    "vwap": 10.4,
                },
                {
                    "symbol": "EXMPL",
                    "date": "2016-01-04",
                    "open": 9,
                    "high": 9.5,
                    "low": 8.5,
                    "close": 9.25,
                    "volume": 900,
                    "vwap": 9.1,
                },
            ],
        )
        self.assertEqual(len(script.urls), 2)
        first = _query(script.urls[0])
        second = _query(script.urls[1])
        self.assertEqual(first["symbols"], ["AAPL"])
        self.assertEqual(first["feed"], ["sip"])
        self.assertEqual(first["adjustment"], ["raw"])
        self.assertEqual(first["timeframe"], ["1Day"])
        self.assertEqual(first["limit"], ["10000"])
        self.assertEqual(first["start"], ["2016-01-04"])
        self.assertEqual(first["end"], ["2024-06-03"])
        self.assertNotIn("page_token", first)
        self.assertEqual(second["page_token"], ["page-2"])
        self.assertEqual(second["symbols"], ["AAPL"])
        self.assertEqual(limiter.calls, 2)
        self.assertNotIn("n", bars[0])

    def test_the_current_new_york_day_ends_before_the_sip_window(self) -> None:
        client, script, _limiter = _client(b'{"bars":{},"next_page_token":null}')
        now = datetime(2026, 11, 16, 19, 20, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(list(client.daily_bars(["AAPL"], "2026-11-16", "2026-11-16", "raw", now=now)), [])
        query = _query(script.urls[0])
        self.assertEqual(query["feed"], ["sip"])
        self.assertEqual(query["start"], ["2026-11-16"])
        self.assertEqual(query["end"], ["2026-11-16T19:04:00-05:00"])

    def test_a_close_inside_the_sip_window_is_not_requested(self) -> None:
        client, script, _limiter = _client(b'{"bars":{},"next_page_token":null}', b'{"bars":{}}')
        now = datetime(2026, 11, 16, 16, 10, tzinfo=ZoneInfo("America/New_York"))
        list(client.daily_bars(["AAPL"], "2026-11-01", "2026-11-16", "raw", now=now))
        query = _query(script.urls[0])
        self.assertEqual(query["start"], ["2026-11-01"])
        self.assertEqual(query["end"], ["2026-11-15"])
        opened = datetime(2026, 11, 16, 16, 16, tzinfo=ZoneInfo("America/New_York"))
        list(client.daily_bars(["AAPL"], "2026-11-16", "2026-11-16", "raw", now=opened))
        self.assertEqual(_query(script.urls[1])["end"], ["2026-11-16T16:00:00-05:00"])

    def test_the_first_minutes_after_midnight_still_use_a_timestamp(self) -> None:
        client, script, _limiter = _client(b'{"bars":{}}', b'{"bars":{}}', b'{"bars":{}}')
        winter = datetime(2026, 11, 17, 0, 10, tzinfo=ZoneInfo("America/New_York"))
        summer = datetime(2026, 7, 16, 0, 10, tzinfo=ZoneInfo("America/New_York"))
        later = datetime(2026, 11, 17, 0, 20, tzinfo=ZoneInfo("America/New_York"))
        list(client.daily_bars(["AAPL"], "2026-11-16", "2026-11-16", "raw", now=winter))
        list(client.daily_bars(["AAPL"], "2026-07-15", "2026-07-15", "raw", now=summer))
        list(client.daily_bars(["AAPL"], "2026-11-16", "2026-11-16", "raw", now=later))
        self.assertEqual(_query(script.urls[0])["end"], ["2026-11-16T23:54:00-05:00"])
        self.assertEqual(_query(script.urls[1])["end"], ["2026-07-15T23:54:00-04:00"])
        self.assertEqual(_query(script.urls[2])["end"], ["2026-11-16"])

    def test_daily_bars_batch_two_hundred_symbols(self) -> None:
        empty = b'{"bars":{},"next_page_token":null}'
        client, script, limiter = _client(empty, empty)
        symbols = [f"S{index:03d}" for index in range(alpaca_data._BATCH + 1)]
        self.assertEqual(list(client.daily_bars(symbols, "2024-06-03", "2024-06-03", "all")), [])
        self.assertEqual(len(script.urls), 2)
        self.assertEqual(len(_query(script.urls[0])["symbols"][0].split(",")), alpaca_data._BATCH)
        self.assertEqual(_query(script.urls[1])["symbols"], ["S200"])
        self.assertEqual(_query(script.urls[1])["adjustment"], ["all"])
        self.assertNotIn("page_token", _query(script.urls[0]))
        self.assertEqual(limiter.calls, 2)
        quiet, quiet_script, _quiet_limiter = _client()
        self.assertEqual(list(quiet.daily_bars([], "2024-06-03", "2024-06-03", "raw")), [])
        self.assertEqual(list(quiet.daily_bars([" ", ""], "2024-06-03", "2024-06-03", "split")), [])
        self.assertEqual(quiet_script.urls, [])
        with self.assertRaises(ValueError):
            quiet.daily_bars("AAPL", "2024-06-03", "2024-06-03", "raw")
        with self.assertRaises(ValueError):
            quiet.daily_bars(["AAPL"], "2024-06-03", "2024-06-03", "adjusted")
        evening = datetime(2024, 6, 4, 3, 30, tzinfo=timezone.utc)
        dated, dated_script, _dated_limiter = _client(empty)
        self.assertEqual(list(dated.daily_bars(["EXMPL"], evening, "2024-06-03", "raw")), [])
        self.assertEqual(_query(dated_script.urls[0])["start"], ["2024-06-03"])

    def test_one_rejected_symbol_is_skipped_and_a_bad_window_is_not(self) -> None:
        def bars_for(symbols: list[str]) -> bytes:
            rows = {
                symbol: [{"t": "2016-01-04T05:00:00Z", "o": 1, "h": 2, "l": 1, "c": 1, "v": 3, "vw": 1}]
                for symbol in symbols
            }
            return json.dumps({"bars": rows}).encode()

        urls: list[str] = []

        def opener(request: urllib.request.Request, timeout: float) -> _Response:
            del timeout
            urls.append(request.full_url)
            symbols = _query(request.full_url)["symbols"][0].split(",")
            if "BAD" in symbols:
                raise _status(400, b'{"message":"invalid symbol: BAD"}')
            return _Response(bars_for(symbols))

        client = alpaca_data.AlpacaData(
            key_id="kid", secret_key="sek", opener=opener, limiter=_Limiter(), ingest_enabled=_allow  # nosec B106
        )
        names = ["AAA", "BAD", "SPY", "ZZZ"]
        found = [row["symbol"] for row in client.daily_bars(names, "2016-01-04", "2016-01-29", "raw")]
        self.assertEqual(found, ["AAA", "SPY", "ZZZ"])
        self.assertIn("SPY", _query(urls[1])["symbols"][0])

        def reject(request: urllib.request.Request, timeout: float) -> _Response:
            del request, timeout
            raise _status(400, b'{"message":"end is before start","url":"https://data.example/x?token=secret-query"}')

        broken = alpaca_data.AlpacaData(
            key_id="kid", secret_key="sek", opener=reject, limiter=_Limiter(), ingest_enabled=_allow  # nosec B106
        )
        with self.assertRaises(http_client.HttpStatusError) as raised:
            list(broken.daily_bars(["AAA", "SPY"], "2016-01-04", "2016-01-29", "raw"))
        self.assertEqual(str(raised.exception), "HTTP 400 end is before start")
        self.assertNotIn("secret-query", str(raised.exception))
        urls.clear()
        again = [row["symbol"] for row in client.daily_bars(names, "2016-02-01", "2016-02-27", "raw")]
        self.assertEqual(again, ["AAA", "SPY", "ZZZ"])
        self.assertTrue(urls)
        self.assertTrue(all("BAD" not in _query(url)["symbols"][0] for url in urls))

    def test_too_many_rejected_symbols_fail_the_request(self) -> None:
        bad = {f"B{index:02d}" for index in range(alpaca_bars._SKIP_LIMIT + 1)}

        def opener(request: urllib.request.Request, timeout: float) -> _Response:
            del timeout
            symbols = _query(request.full_url)["symbols"][0].split(",")
            if bad.intersection(symbols):
                raise _status(400, b'{"message":"invalid symbol"}')
            rows = {
                symbol: [{"t": "2016-01-04T05:00:00Z", "o": 1, "h": 2, "l": 1, "c": 1, "v": 3, "vw": 1}]
                for symbol in symbols
            }
            return _Response(json.dumps({"bars": rows}).encode())

        client = alpaca_data.AlpacaData(
            key_id="kid", secret_key="sek", opener=opener, limiter=_Limiter(), ingest_enabled=_allow  # nosec B106
        )
        with self.assertRaises(http_client.HttpStatusError) as raised:
            list(client.daily_bars(sorted(bad | {"SPY"}), "2016-01-04", "2016-01-29", "raw"))
        self.assertEqual(str(raised.exception), "HTTP 400 invalid symbol")

    def test_a_bad_bars_shape_and_a_repeated_token_stop(self) -> None:
        client, script, _limiter = _client(b'{"bars":[],"next_page_token":null}')
        with self.assertRaises(ValueError):
            list(client.daily_bars(["EXMPL"], "2024-06-03", "2024-06-03", "raw"))
        repeated = b'{"bars":{},"next_page_token":"same"}'
        again, again_script, _again_limiter = _client(repeated, repeated, repeated)
        with self.assertRaises(ValueError):
            list(again.daily_bars(["EXMPL"], "2024-06-03", "2024-06-03", "raw"))
        self.assertEqual(len(again_script.urls), 2)
        self.assertEqual(len(script.urls), 1)
        missing = (
            b'{"bars":{"EXMPL":[{"t":"2024-06-03T04:00:00Z","o":1,"h":1,"l":1,"v":1,"vw":1}]},"next_page_token":null}'
        )
        broken, _broken_script, _broken_limiter = _client(missing)
        with self.assertRaises(ValueError):
            list(broken.daily_bars(["EXMPL"], "2024-06-03", "2024-06-03", "raw"))

    def test_corporate_actions_map_cash_and_splits(self) -> None:
        client, script, limiter = _client(_load("alpaca_actions.json"), _load("alpaca_actions_next.json"))
        actions = client.corporate_actions("2023-01-01", "2024-06-30")
        self.assertEqual(
            actions,
            [
                {
                    "symbol": "EXMPL",
                    "type": "cash_dividend",
                    "exDate": "2024-05-10",
                    "processDate": "2024-05-16",
                    "payDate": "2024-05-16",
                    "cashPerShare": 0.25,
                    "splitFrom": None,
                    "splitTo": None,
                    "special": False,
                    "foreign": True,
                    "subType": "return_of_capital",
                    "newSymbol": None,
                },
                {
                    "symbol": "EXMPL",
                    "type": "forward_split",
                    "exDate": "2024-06-10",
                    "processDate": "2024-06-12",
                    "payDate": "2024-06-10",
                    "cashPerShare": None,
                    "splitFrom": 1,
                    "splitTo": 4,
                    "special": None,
                    "foreign": None,
                    "subType": None,
                    "newSymbol": None,
                },
                {
                    "symbol": "EXMPL",
                    "type": "reverse_split",
                    "exDate": "2023-03-01",
                    "processDate": "2023-03-08",
                    "payDate": "2023-03-01",
                    "cashPerShare": None,
                    "splitFrom": 10,
                    "splitTo": 1,
                    "special": None,
                    "foreign": None,
                    "subType": None,
                    "newSymbol": "EXM2",
                },
            ],
        )
        first = _query(script.urls[0])
        self.assertEqual(first["types"], ["cash_dividend,forward_split,reverse_split"])
        self.assertEqual(first["limit"], ["1000"])
        self.assertEqual(first["start"], ["2023-01-01"])
        self.assertEqual(first["end"], ["2024-06-30"])
        self.assertNotEqual(actions[0]["exDate"], "2023-01-01")
        self.assertEqual(_query(script.urls[1])["page_token"], ["actions-2"])
        self.assertEqual(limiter.calls, 2)
        self.assertNotIn("cusip", json.dumps(actions))

    def test_news_drops_the_body(self) -> None:
        client, script, limiter = _client(_load("alpaca_news.json"), _load("alpaca_news_next.json"))
        rows = client.news(["EXMPL"], "2024-06-03T00:00:00Z", "2024-06-04T00:00:00Z")
        self.assertEqual(rows[0]["id"], 42)
        self.assertEqual(rows[0]["symbols"], ["EXMPL", "SECND"])
        self.assertEqual(rows[0]["headline"], "Example rises")
        self.assertEqual(rows[0]["summary"], "Short summary")
        self.assertEqual(rows[0]["source"], "Example Wire")
        self.assertEqual(rows[0]["url"], "https://example.com/story")
        self.assertEqual(rows[0]["createdAt"], "2024-06-03T14:00:00Z")
        self.assertEqual(rows[1]["id"], 43)
        self.assertEqual(set(rows[0]), {"id", "symbols", "headline", "summary", "source", "url", "createdAt"})
        blob = json.dumps(rows)
        self.assertNotIn("FULL BODY", blob)
        self.assertNotIn("ALSO DROPPED", blob)
        self.assertNotIn("A Writer", blob)
        query = _query(script.urls[0])
        self.assertEqual(query["symbols"], ["EXMPL"])
        self.assertEqual(query["limit"], ["50"])
        self.assertEqual(query["start"], ["2024-06-03T00:00:00Z"])
        self.assertEqual(_query(script.urls[1])["page_token"], ["news-2"])
        self.assertEqual(limiter.calls, 2)
        quiet, quiet_script, _quiet_limiter = _client()
        self.assertEqual(quiet.news([], "2024-06-03", "2024-06-04"), [])
        self.assertEqual(quiet_script.urls, [])
        empty = b'{"news":[],"next_page_token":null}'
        batched, batched_script, _batched_limiter = _client(empty, empty)
        symbols = [f"S{index:03d}" for index in range(alpaca_data._BATCH + 1)]
        self.assertEqual(batched.news(symbols, "2024-06-03T00:00:00Z", "2024-06-04T00:00:00Z"), [])
        self.assertEqual(len(_query(batched_script.urls[0])["symbols"][0].split(",")), alpaca_data._BATCH)
        self.assertEqual(_query(batched_script.urls[1])["symbols"], ["S200"])
        moment = datetime(2024, 6, 3, 18, 0, tzinfo=ZoneInfo("America/New_York"))
        timed, timed_script, _timed_limiter = _client(empty)
        self.assertEqual(timed.news(["EXMPL"], moment, "2024-06-04T00:00:00Z"), [])
        self.assertEqual(_query(timed_script.urls[0])["start"], ["2024-06-03T22:00:00Z"])

    def test_secret_headers_stay_out_of_the_log(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("http_client")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        calls = {"n": 0}

        def opener(request: urllib.request.Request, timeout: float) -> _Response:
            del timeout
            calls["n"] += 1
            if calls["n"] == 1:
                headers = Message()
                headers["Retry-After"] = "0"
                raise urllib.error.HTTPError(request.full_url, 429, "slow", headers, io.BytesIO(b"slow"))
            self.assertEqual(request.get_header("Apca-api-key-id"), "kid")
            self.assertEqual(request.get_header("Apca-api-secret-key"), "sek")
            return _Response(_load("alpaca_assets.json"))

        try:
            secret = _SecretClient('{"key_id":"kid","secret_key":"sek"}')
            client = alpaca_data.client_from_secret(
                secret_client=secret, opener=opener, limiter=_Limiter(), ingest_enabled=lambda: True
            )
            self.assertEqual(secret.ids, ["findingalpha/alpaca-paper"])
            self.assertEqual(client.list_assets()[0]["symbol"], "EXMPL")
            self.assertEqual(repr(client), "AlpacaData()")
            self.assertNotIn("sek", repr(client))
        finally:
            logger.removeHandler(handler)
            logger.setLevel(logging.NOTSET)
        text = stream.getvalue()
        self.assertIn("http retry", text)
        self.assertNotIn("sek", text)
        self.assertNotIn("kid", text)

        def refuse(_request: object, timeout: float) -> _Response:
            del timeout
            raise AssertionError("requested")

        with self.assertRaises(secrets_read.NotConfigured):
            alpaca_data.AlpacaData(key_id="", secret_key="sek", opener=refuse)  # nosec B106
        with self.assertRaises(secrets_read.NotConfigured):
            alpaca_data.AlpacaData(key_id="kid", secret_key="se\nk", opener=refuse)  # nosec B106
        secrets_read.clear_cache()
        with self.assertRaises(secrets_read.NotConfigured):
            alpaca_data.client_from_secret(secret_client=_SecretClient('{"key_id":"kid"}'), opener=refuse)
        os.environ["ALPACA_SECRET_ID"] = "findingalpha/other"  # nosec B105
        secrets_read.clear_cache()
        other = _SecretClient('{"key_id":"kid","secret_key":"sek"}')
        alpaca_data.client_from_secret(secret_client=other, opener=opener, limiter=_Limiter())
        self.assertEqual(other.ids, ["findingalpha/other"])

    def test_module_functions_use_the_shared_client(self) -> None:
        client, _script, _limiter = _client(_load("alpaca_assets.json"))
        alpaca_data._CLIENT = client
        self.assertEqual(alpaca_data.list_assets()[0]["symbol"], "EXMPL")

    def test_a_rotated_secret_is_used_on_the_next_call(self) -> None:
        payloads = ['{"key_id":"kid","secret_key":"sek"}', '{"key_id":"next","secret_key":"sek-2"}']

        class _Flip:
            def __init__(self) -> None:
                self.n = 0

            def get_secret_value(self, SecretId: str) -> dict[str, str]:
                del SecretId
                payload = payloads[min(self.n, len(payloads) - 1)]
                self.n += 1
                return {"SecretString": payload}

        flip = _Flip()
        seen: list[str | None] = []

        def opener(request: urllib.request.Request, timeout: float) -> _Response:
            del timeout
            seen.append(request.get_header("Apca-api-key-id"))
            return _Response(_load("alpaca_assets.json"))

        alpaca_data._SECRET_CLIENT = flip
        alpaca_data._OPENER = opener
        alpaca_data._INGEST = lambda: True
        alpaca_data._LIMITER = _Limiter()
        alpaca_data._RESERVE = lambda: None
        alpaca_data.list_assets()
        alpaca_data.list_assets()
        self.assertEqual(flip.n, 1)
        secrets_read.clear_cache()
        alpaca_data.list_assets()
        self.assertEqual(seen, ["kid", "kid", "next"])
        self.assertEqual(flip.n, 2)

    def test_ingest_off_makes_no_request(self) -> None:
        client, script, limiter = _client(_load("alpaca_assets.json"), ingest_enabled=lambda: False)
        with self.assertRaises(alpaca_data.IngestDisabled):
            client.list_assets()
        self.assertEqual(script.urls, [])
        self.assertEqual(limiter.calls, 0)
        import kill_switch

        seen: dict[str, str] = {}

        def fake(name: str, settings: object = None) -> bool:
            del settings
            seen["name"] = name
            return True

        original = kill_switch.is_enabled
        kill_switch.is_enabled = fake
        try:
            checked, _checked_script, _checked_limiter = _client(_load("alpaca_assets.json"), ingest_enabled=None)
            self.assertEqual(checked.list_assets()[0]["symbol"], "EXMPL")
        finally:
            kill_switch.is_enabled = original
        self.assertEqual(seen["name"], "ingestEnabled")


class MinuteSlotTest(unittest.TestCase):
    def test_a_full_minute_waits_for_the_next_one(self) -> None:
        import store

        state = {"window": None, "count": 0}
        sleeps: list[float] = []
        clock = {"t": 120.0}

        def update(
            pk: str, sk: str, expression: str, values: dict[str, int], condition: str, names: dict[str, str]
        ) -> None:
            del pk, sk, condition, names
            minute = values[":minute"]
            if expression.startswith("ADD"):
                if state["window"] == minute and state["count"] < values[":cap"]:
                    state["count"] += 1
                    return
                raise store.ConditionNotMet("rate")
            if state["window"] is None or state["window"] != minute:
                state["window"] = minute
                state["count"] = 1
                return
            raise store.ConditionNotMet("rate")

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock["t"] += seconds

        def take() -> None:
            alpaca_data.take_minute_slot(update, clock=lambda: clock["t"], sleep=sleep, cap=2, attempts=4)

        take()
        take()
        self.assertEqual(state, {"window": 2, "count": 2})
        take()
        self.assertEqual(state, {"window": 3, "count": 1})
        self.assertEqual(sleeps, [60.0])

        def boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("down")

        with self.assertRaises(RuntimeError):
            alpaca_data.take_minute_slot(boom, clock=lambda: 0.0, sleep=lambda _seconds: None, attempts=2)

    def test_a_missing_table_does_not_reserve(self) -> None:
        saved = os.environ.pop("RECORDS_TABLE_NAME", None)
        alpaca_data._RESERVE = None
        try:
            alpaca_data._reserve_shared_slot()
        finally:
            if saved is None:
                os.environ.pop("RECORDS_TABLE_NAME", None)
            else:
                os.environ["RECORDS_TABLE_NAME"] = saved


if __name__ == "__main__":
    unittest.main()
