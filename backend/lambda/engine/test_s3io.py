"""JSON and gzipped JSONL against a fake bucket."""

from __future__ import annotations

import io
import unittest

import s3io
from botocore.exceptions import ClientError


class _Body:
    def __init__(self, payload: bytes) -> None:
        self._buffer = io.BytesIO(payload)

    def read(self, n: int = -1) -> bytes:
        return self._buffer.read(n)

    def close(self) -> None:
        self._buffer.close()


class _Bucket:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        del ContentType
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
        return {"Body": _Body(self.objects[(Bucket, Key)])}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, str]:
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str = "") -> dict[str, object]:
        keys = sorted(key for bucket, key in self.objects if bucket == Bucket and key.startswith(Prefix))
        start = int(ContinuationToken or "0")
        page = keys[start : start + 1]
        truncated = start + 1 < len(keys)
        result: dict[str, object] = {
            "Contents": [{"Key": key} for key in page],
            "IsTruncated": truncated,
        }
        if truncated:
            result["NextContinuationToken"] = str(start + 1)
        return result


class S3IoTest(unittest.TestCase):
    def test_gzip_json_round_trip(self) -> None:
        bucket = _Bucket()
        s3io.put_gzip_json("data", "facts.json.gz", {"cik": 1}, client=bucket)
        self.assertEqual(s3io.get_gzip_json("data", "facts.json.gz", client=bucket), {"cik": 1})
        self.assertTrue(bucket.objects[("data", "facts.json.gz")].startswith(b"\x1f\x8b"))

    def test_json_round_trip(self) -> None:
        bucket = _Bucket()
        s3io.put_json("data", "reference/a.json", {"n": 1}, client=bucket)
        self.assertEqual(s3io.get_json("data", "reference/a.json", client=bucket), {"n": 1})
        self.assertTrue(s3io.exists("data", "reference/a.json", client=bucket))
        self.assertFalse(s3io.exists("data", "missing.json", client=bucket))
        s3io.delete("data", "reference/a.json", client=bucket)
        self.assertFalse(s3io.exists("data", "reference/a.json", client=bucket))

    def test_jsonl_gz_round_trip(self) -> None:
        bucket = _Bucket()
        s3io.put_jsonl_gz("data", "prices/part.jsonl.gz", [{"s": "AAA"}, {"s": "BBB"}], client=bucket)
        rows = list(s3io.get_jsonl_gz("data", "prices/part.jsonl.gz", client=bucket))
        self.assertEqual(rows, [{"s": "AAA"}, {"s": "BBB"}])

    def test_list_keys_follows_pages(self) -> None:
        bucket = _Bucket()
        s3io.put_json("data", "prices/a.json", {}, client=bucket)
        s3io.put_json("data", "prices/b.json", {}, client=bucket)
        s3io.put_json("data", "other/c.json", {}, client=bucket)
        self.assertEqual(s3io.list_keys("data", "prices/", client=bucket), ["prices/a.json", "prices/b.json"])


if __name__ == "__main__":
    unittest.main()
