"""DynamoDB access for the records table."""

from __future__ import annotations

from typing import Any

import runtime
from config import records_table_name


def _table() -> Any:
    return runtime._ddb.Table(records_table_name())


def get(pk: str, sk: str) -> dict[str, Any] | None:
    item = _table().get_item(Key={"pk": pk, "sk": sk}).get("Item")
    return item if isinstance(item, dict) else None


def put(item: dict[str, Any]) -> None:
    _table().put_item(Item=item)


def query_pk(pk: str, prefix: str = "") -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :sk)",
        "ExpressionAttributeValues": {":pk": pk, ":sk": prefix},
    }
    items: list[dict[str, Any]] = []
    while True:
        page = _table().query(**kwargs)
        items.extend(page.get("Items") or [])
        token = page.get("LastEvaluatedKey")
        if not token:
            return items
        kwargs["ExclusiveStartKey"] = token


def query_gsi1(gsi1pk: str, prefix: str = "") -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {
        "IndexName": "gsi1",
        "KeyConditionExpression": "gsi1pk = :pk AND begins_with(gsi1sk, :sk)",
        "ExpressionAttributeValues": {":pk": gsi1pk, ":sk": prefix},
    }
    items: list[dict[str, Any]] = []
    while True:
        page = _table().query(**kwargs)
        items.extend(page.get("Items") or [])
        token = page.get("LastEvaluatedKey")
        if not token:
            return items
        kwargs["ExclusiveStartKey"] = token


def scan_pk_prefix(prefix: str) -> list[dict[str, Any]]:
    page = _table().scan(
        FilterExpression="begins_with(pk, :pk)",
        ExpressionAttributeValues={":pk": prefix},
    )
    return list(page.get("Items") or [])


def delete(pk: str, sk: str) -> None:
    _table().delete_item(Key={"pk": pk, "sk": sk})


def query_latest(pk: str, prefix: str, limit: int = 1) -> list[dict[str, Any]]:
    page = _table().query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :sk)",
        ExpressionAttributeValues={":pk": pk, ":sk": prefix},
        ScanIndexForward=False,
        Limit=limit,
    )
    return list(page.get("Items") or [])


def query_gsi1_latest(gsi1pk: str, limit: int) -> list[dict[str, Any]]:
    page = _table().query(
        IndexName="gsi1",
        KeyConditionExpression="gsi1pk = :pk",
        ExpressionAttributeValues={":pk": gsi1pk},
        ScanIndexForward=False,
        Limit=limit,
    )
    return list(page.get("Items") or [])


def update(pk: str, sk: str, expression: str, values: dict[str, Any], names: dict[str, str] | None = None) -> None:
    kwargs: dict[str, Any] = {
        "Key": {"pk": pk, "sk": sk},
        "UpdateExpression": expression,
        "ExpressionAttributeValues": values,
    }
    if names:
        kwargs["ExpressionAttributeNames"] = names
    _table().update_item(**kwargs)
