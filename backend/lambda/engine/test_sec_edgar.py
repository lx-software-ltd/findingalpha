"""SEC client against invented fixtures. No network."""

from __future__ import annotations

import json
import logging
import unittest
import urllib.request
from datetime import date
from pathlib import Path

import http_client
import sec_edgar

_FIXTURES = Path(__file__).resolve().parent / "test_fixtures"
_CONTACT = "sec-test@example.com"


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


class SecEdgarTest(unittest.TestCase):
    def setUp(self) -> None:
        sec_edgar._CLIENT = None
        self.limiter = _Limiter()
        self.seen: list[tuple[str, str]] = []

    def tearDown(self) -> None:
        sec_edgar._CLIENT = None

    def _client(self, routes: dict[str, bytes | int]) -> sec_edgar.SecEdgar:
        def opener(request: urllib.request.Request, timeout: float) -> _Response:
            del timeout
            url = request.full_url
            self.seen.append((url, request.get_header("User-agent")))
            body = routes.get(url)
            if body is None:
                raise AssertionError(url)
            if isinstance(body, int):
                raise http_client.HttpStatusError(body, "missing")
            return _Response(body)

        return sec_edgar.SecEdgar(contact=_CONTACT, opener=opener, limiter=self.limiter)

    def test_ticker_map_pads_the_cik_and_skips_a_blank_ticker(self) -> None:
        payload = (_FIXTURES / "sec_tickers.json").read_bytes()
        client = self._client({sec_edgar._TICKERS: payload})
        found = client.ticker_map()
        self.assertEqual(set(found), {"EXMPL", "SECND"})
        self.assertEqual(found["EXMPL"]["cik"], "0000000007")
        self.assertEqual(found["SECND"]["exchange"], "NASDAQ")
        self.assertEqual(self.seen[0][1], f"findingalpha {_CONTACT}")
        self.assertEqual(self.limiter.calls, 1)

    def test_submissions_and_facts_use_the_ten_digit_cik(self) -> None:
        routes = {
            "https://data.sec.gov/submissions/CIK0000000007.json": b'{"sic": "1000"}',
            "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000007.json": b'{"facts": {}}',
        }
        client = self._client(routes)
        self.assertEqual(client.submissions("7")["sic"], "1000")
        self.assertEqual(client.company_facts(7)["facts"], {})
        self.assertEqual(self.limiter.calls, 2)

    def test_daily_index_parses_rows_under_the_dashes(self) -> None:
        text = (_FIXTURES / "sec_master.idx").read_bytes()
        january = "https://www.sec.gov/Archives/edgar/daily-index/2024/QTR1/master.20240102.idx"
        april = "https://www.sec.gov/Archives/edgar/daily-index/2024/QTR2/master.20240401.idx"
        client = self._client({january: text, april: 404})
        rows = client.daily_index(date(2024, 1, 2))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["cik"], "0000000007")
        self.assertEqual(rows[0]["form"], "10-Q")
        self.assertEqual(rows[0]["filed"], "2024-01-02")
        self.assertTrue(rows[0]["path"].endswith(".txt"))
        self.assertEqual(client.daily_index("2024-04-01"), [])
        self.assertEqual(self.seen[-1][0], april)

    def test_a_missing_index_is_an_empty_list(self) -> None:
        url = "https://www.sec.gov/Archives/edgar/daily-index/2024/QTR1/master.20240101.idx"
        client = self._client({url: 404})
        self.assertEqual(client.daily_index("2024-01-01"), [])

    def test_a_server_error_is_not_an_empty_index(self) -> None:
        url = "https://www.sec.gov/Archives/edgar/daily-index/2024/QTR3/master.20240701.idx"

        def opener(request: object, timeout: float) -> _Response:
            del request, timeout
            raise http_client.HttpStatusError(503, "down")

        client = sec_edgar.SecEdgar(contact=_CONTACT, opener=opener, limiter=self.limiter)
        with self.assertRaises(http_client.HttpStatusError) as raised:
            client.daily_index("2024-07-01")
        self.assertEqual(raised.exception.status, 503)
        self.assertEqual(url.rsplit("/", 1)[-1], "master.20240701.idx")

    def test_a_missing_contact_makes_no_request(self) -> None:
        def opener(_request: object, timeout: float) -> _Response:
            del timeout
            raise AssertionError("requested")

        with self.assertRaises(sec_edgar.MissingSetting):
            sec_edgar.SecEdgar(contact="  ", opener=opener)
        with self.assertRaises(sec_edgar.MissingSetting):
            sec_edgar.SecEdgar(contact="bad\naddress", opener=opener)

    def test_module_functions_use_the_shared_client(self) -> None:
        payload = (_FIXTURES / "sec_tickers.json").read_bytes()
        sec_edgar._CLIENT = self._client({sec_edgar._TICKERS: payload})
        self.assertEqual(sec_edgar.ticker_map()["EXMPL"]["name"], "EXAMPLE INDUSTRIES INC")

    def test_the_contact_is_not_logged(self) -> None:
        records: list[logging.LogRecord] = []
        handler = logging.Handler()
        handler.emit = records.append  # type: ignore[method-assign]
        logger = logging.getLogger("http_client")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        def opener(_request: object, timeout: float) -> _Response:
            del timeout
            raise http_client.HttpStatusError(500, "down")

        client = sec_edgar.SecEdgar(contact=_CONTACT, opener=opener, limiter=self.limiter)
        try:
            with self.assertRaises(http_client.HttpStatusError):
                client.ticker_map()
        finally:
            logger.removeHandler(handler)
        dumped = json.dumps([record.getMessage() for record in records])
        self.assertNotIn(_CONTACT, dumped)
        self.assertNotIn("findingalpha", dumped)


if __name__ == "__main__":
    unittest.main()
