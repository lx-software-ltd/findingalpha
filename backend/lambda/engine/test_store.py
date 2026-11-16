"""DynamoDB queries never send an empty key value."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

import store


class _Table:
    def __init__(self) -> None:
        self.queries: list[dict[str, Any]] = []
        self.paginate = False

    def query(self, **kwargs: Any) -> dict[str, Any]:
        for value in kwargs.get("ExpressionAttributeValues", {}).values():
            if value == "":
                raise RuntimeError("empty string key")
        self.queries.append(kwargs)
        if self.paginate and "ExclusiveStartKey" not in kwargs and kwargs.get("Limit") != 1:
            return {"Items": [{"n": 1}], "LastEvaluatedKey": {"pk": "more"}}
        return {"Items": [{"n": 2}]}


class StoreQueryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.table = _Table()
        self.bound = patch("store._table", return_value=self.table)
        self.bound.start()

    def tearDown(self) -> None:
        self.bound.stop()

    def test_an_empty_prefix_is_not_sent(self) -> None:
        self.table.paginate = True
        self.assertEqual(store.query_gsi1("JOBSTATE"), [{"n": 1}, {"n": 2}])
        self.assertEqual(store.query_pk("JOB#prices"), [{"n": 1}, {"n": 2}])
        for query in self.table.queries:
            self.assertNotIn(":sk", query["ExpressionAttributeValues"])
            self.assertNotIn("begins_with", query["KeyConditionExpression"])
        self.assertEqual(self.table.queries[0]["IndexName"], "gsi1")
        self.assertEqual(self.table.queries[1]["IndexName"], "gsi1")
        self.assertEqual(self.table.queries[1].get("ExclusiveStartKey"), {"pk": "more"})
        self.assertNotIn("IndexName", self.table.queries[2])

    def test_a_real_prefix_is_a_begins_with(self) -> None:
        store.query_gsi1("UNIVERSE", "2024")
        store.query_pk("JOB#tick", "RUN#")
        store.query_latest("JOB#tick", "RUN#", 1)
        gsi, pk, latest = self.table.queries
        self.assertEqual(gsi["ExpressionAttributeValues"][":sk"], "2024")
        self.assertIn("begins_with(gsi1sk, :sk)", gsi["KeyConditionExpression"])
        self.assertEqual(pk["ExpressionAttributeValues"][":sk"], "RUN#")
        self.assertIn("begins_with(sk, :sk)", pk["KeyConditionExpression"])
        self.assertEqual(latest["ExpressionAttributeValues"][":sk"], "RUN#")
        self.assertEqual(store.query_gsi1_latest("JOBRUNS", 5), [{"n": 2}])
        self.assertNotIn(":sk", self.table.queries[-1]["ExpressionAttributeValues"])


if __name__ == "__main__":
    unittest.main()
