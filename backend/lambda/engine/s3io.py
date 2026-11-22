"""JSON and gzipped JSONL objects in one bucket."""

from __future__ import annotations

import gzip
import io
import json
from typing import Any, Iterable, Iterator

from botocore.exceptions import ClientError


def _client(client: Any) -> Any:
    if client is not None:
        return client
    import boto3

    return boto3.client("s3")


def put_json(bucket: str, key: str, payload: Any, *, client: Any = None) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    _client(client).put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")


def put_gzip_json(bucket: str, key: str, payload: Any, *, client: Any = None) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    _client(client).put_object(Bucket=bucket, Key=key, Body=gzip.compress(raw), ContentType="application/gzip")


def get_gzip_json(bucket: str, key: str, *, client: Any = None) -> Any:
    body = _client(client).get_object(Bucket=bucket, Key=key)["Body"]
    try:
        return json.loads(gzip.decompress(body.read()).decode("utf-8"))
    finally:
        body.close()


def get_json(bucket: str, key: str, *, client: Any = None) -> Any:
    body = _client(client).get_object(Bucket=bucket, Key=key)["Body"]
    try:
        return json.loads(body.read().decode("utf-8"))
    finally:
        body.close()


def put_jsonl_gz(bucket: str, key: str, rows: Iterable[dict[str, Any]], *, client: Any = None) -> None:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n")
    _client(client).put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType="application/gzip",
    )


def get_jsonl_gz(bucket: str, key: str, *, client: Any = None) -> Iterator[dict[str, Any]]:
    body = _client(client).get_object(Bucket=bucket, Key=key)["Body"]
    try:
        with gzip.GzipFile(fileobj=body) as handle:
            for line in handle:
                text = line.strip()
                if text:
                    yield json.loads(text)
    finally:
        body.close()


def delete(bucket: str, key: str, *, client: Any = None) -> None:
    _client(client).delete_object(Bucket=bucket, Key=key)


def exists(bucket: str, key: str, *, client: Any = None) -> bool:
    try:
        _client(client).head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise
    return True


def list_keys(bucket: str, prefix: str, *, client: Any = None) -> list[str]:
    s3 = _client(client)
    keys: list[str] = []
    # Empty pagination cursor, not a password.
    token = ""  # nosec B105
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = s3.list_objects_v2(**kwargs)
        keys.extend(item["Key"] for item in page.get("Contents") or [])
        if not page.get("IsTruncated"):
            return keys
        token = page["NextContinuationToken"]
