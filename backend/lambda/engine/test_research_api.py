"""Screen and backtest reads."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import api_handler


def _event(path: str) -> dict:
    return {
        "requestContext": {
            "http": {"method": "GET", "path": path},
            "authorizer": {"jwt": {"claims": {"sub": "user-1", "cognito:groups": "[admin]"}}},
        }
    }


class ResearchApiTest(unittest.TestCase):
    def test_the_latest_screen_returns_the_shortlist(self) -> None:
        meta = {
            "asOf": "2017-02-28",
            "gsi1sk": "2017-02-28",
            "registerHash": "abc",
            "shortlistSize": 1,
            "counts": {"universe": 2, "passed": 1, "shortlisted": 1},
        }
        rows = [
            {"rank": 2, "symbol": "BBB", "composite": 0.1, "groups": {}, "factors": {}, "z": {}},
            {
                "rank": 1,
                "symbol": "AAA",
                "name": "Aaa",
                "sector": "tech",
                "composite": 0.4,
                "groups": {"quality": 0.2},
                "factors": {"roic": 0.1},
                "z": {"roic": 0.3},
            },
        ]
        with (
            patch("store.query_gsi1_latest", return_value=[meta]),
            patch("store.get", return_value=meta),
            patch("research_api.config.data_bucket_name", return_value="data"),
            patch("research_api.s3io.exists", return_value=True),
            patch("research_api.s3io.get_jsonl_gz", return_value=iter(rows)),
        ):
            response = api_handler.lambda_handler(_event("/screens/latest"), None)
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual([row["symbol"] for row in body["rows"]], ["AAA"])
        self.assertEqual(body["counts"]["universe"], 2)

    def test_a_missing_backtest_is_not_found(self) -> None:
        with patch("store.get", return_value=None):
            response = api_handler.lambda_handler(_event("/backtests/missing"), None)
        self.assertEqual(response["statusCode"], 404)


if __name__ == "__main__":
    unittest.main()
