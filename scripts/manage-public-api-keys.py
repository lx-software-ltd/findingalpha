#!/usr/bin/env python3
"""Mint, list, revoke, and toggle write or scopes on public API keys.

Keys authenticate ``/public/*`` with the ``x-api-key`` header. Only the
scrypt digest is stored (``pk = APIKEY#<digest>``, ``sk = META``). The
plaintext is printed once by ``create``, or written to ``--plaintext-out``
for the workflow to encrypt. The only tier that can be minted is ``admin``.

New keys expire in 90 days unless ``--expires-at`` is set. Scopes default
to ``system``. Writes need ``allowWrite`` on the row and the stack
parameter ``PublicApiWritesEnabled``.

Requires GetItem, PutItem, UpdateItem, and Query on the records table
and its ``gsi1`` index, plus kms Decrypt and GenerateDataKey on the
shared key.

Usage:
  python3 scripts/manage-public-api-keys.py create --label monitor [--tier admin]
  python3 scripts/manage-public-api-keys.py list
  python3 scripts/manage-public-api-keys.py revoke --key-id <keyId>
  python3 scripts/manage-public-api-keys.py set-write --key-id <keyId> --allow-write
  python3 scripts/manage-public-api-keys.py set-write --key-id <keyId> --read-only
  python3 scripts/manage-public-api-keys.py set-scopes --key-id <keyId> --scopes system,operate
"""

from __future__ import annotations

import argparse
import ipaddress
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

_AUTHORIZER_DIR = Path(__file__).resolve().parents[1] / "backend" / "lambda" / "public_api_authorizer"
sys.path.insert(0, str(_AUTHORIZER_DIR))
from api_key_hash import hash_api_key  # noqa: E402
from api_key_scopes import ALL_SCOPES, key_allows_write  # noqa: E402
from public_api_scopes_generated import SCOPE_SYSTEM  # noqa: E402

API_KEY_PK_PREFIX = "APIKEY#"
API_KEYS_GSI_PK = "APIKEYS"
KEY_PLAINTEXT_PREFIX = "fapk_"
DEFAULT_TABLE = "findingalpha-records"
DEFAULT_REGION = "ap-southeast-1"
DEFAULT_EXPIRY_DAYS = 90
BUILT_TIER = "admin"


def _table(args: argparse.Namespace):
    return boto3.resource("dynamodb", region_name=args.region).Table(args.table)


def require_tier(value: str) -> str:
    if value == "user":
        sys.exit("error: tier user is not built yet")
    if value != BUILT_TIER:
        sys.exit(f"error: unknown tier {value!r}")
    return value


def _validate_expires_at(raw: str | None) -> str:
    if raw is None:
        return (datetime.now(timezone.utc) + timedelta(days=DEFAULT_EXPIRY_DAYS)).date().isoformat()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        sys.exit(f"error: --expires-at {raw!r} is not an ISO date/datetime")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed <= datetime.now(timezone.utc):
        sys.exit(f"error: --expires-at {raw!r} is in the past")
    return raw


def _parse_scopes(raw: str | None) -> list[str]:
    text = (raw or SCOPE_SYSTEM).strip()
    scopes = sorted({part.strip() for part in text.split(",") if part.strip()})
    if not scopes:
        sys.exit("error: --scopes must list at least one scope")
    unknown = [scope for scope in scopes if scope not in ALL_SCOPES]
    if unknown:
        sys.exit(f"error: unknown scopes {unknown}; allowed: {', '.join(sorted(ALL_SCOPES))}")
    return scopes


def _parse_cidrs(raw: str | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for part in raw.split(","):
        cidr = part.strip()
        if not cidr:
            continue
        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            sys.exit(f"error: --allowed-cidrs entry {cidr!r} is not a CIDR")
        out.append(cidr)
    return out


def cmd_create(args: argparse.Namespace) -> None:
    tier = require_tier(args.tier)
    expires_at = _validate_expires_at(args.expires_at)
    scopes = _parse_scopes(args.scopes)
    cidrs = _parse_cidrs(args.allowed_cidrs)
    plaintext = KEY_PLAINTEXT_PREFIX + secrets.token_urlsafe(36)
    digest = hash_api_key(plaintext)
    key_id = uuid.uuid4().hex[:12]
    created_at = datetime.now(timezone.utc).isoformat()
    item = {
        "pk": f"{API_KEY_PK_PREFIX}{digest}",
        "sk": "META",
        "gsi1pk": API_KEYS_GSI_PK,
        "gsi1sk": f"{created_at}#{key_id}",
        "keyId": key_id,
        "label": args.label,
        "tier": tier,
        "scopes": scopes,
        "allowWrite": bool(args.allow_write),
        "revoked": False,
        "createdAt": created_at,
        "expiresAt": expires_at,
    }
    if cidrs:
        item["allowedCidrs"] = cidrs
    try:
        _table(args).put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code == "ConditionalCheckFailedException":
            sys.exit("error: hash collision (retry)")
        raise
    print(f"keyId:  {key_id}")
    print(f"label:  {args.label}")
    print(f"tier:   {tier}")
    print(f"scopes: {','.join(scopes)}")
    print(f"write:  {'yes' if item['allowWrite'] else 'no'}")
    print(f"expires: {expires_at}")
    if cidrs:
        print(f"cidrs:  {','.join(cidrs)}")
    if args.plaintext_out:
        out_path = Path(args.plaintext_out)
        out_path.touch(mode=0o600, exist_ok=False)
        out_path.write_text(plaintext + "\n", encoding="utf-8")
        print(f"API key written to {out_path} (shown nowhere else)")
        return
    print()
    print("API key (shown once, store it now):")
    print(f"  {plaintext}")
    print()
    print("Example:")
    print(f'  curl -H "x-api-key: {plaintext}" https://api.<domain>/public/system/status')


def _query_keys(args: argparse.Namespace) -> list[dict]:
    table = _table(args)
    items: list[dict] = []
    kwargs: dict = {
        "IndexName": "gsi1",
        "KeyConditionExpression": "gsi1pk = :pk",
        "ExpressionAttributeValues": {":pk": API_KEYS_GSI_PK},
    }
    while True:
        res = table.query(**kwargs)
        items.extend(res.get("Items", []))
        last = res.get("LastEvaluatedKey")
        if not last:
            return items
        kwargs["ExclusiveStartKey"] = last


def cmd_list(args: argparse.Namespace) -> None:
    items = _query_keys(args)
    if not items:
        print("no API keys found")
        return
    for item in sorted(items, key=lambda row: str(row.get("createdAt", ""))):
        state = "revoked" if item.get("revoked") else "active"
        expires = item.get("expiresAt") or "never"
        scopes = item.get("scopes") or []
        scopes_text = ",".join(str(scope) for scope in scopes) if isinstance(scopes, list) else str(scopes)
        write = "yes" if key_allows_write(item) else "no"
        print(
            f"{item.get('keyId')}  {state:8}  label={item.get('label')!r}  "
            f"tier={item.get('tier')}  scopes={scopes_text}  write={write}  "
            f"created={item.get('createdAt')}  expires={expires}"
        )


def _matches(args: argparse.Namespace) -> list[dict]:
    matches = [item for item in _query_keys(args) if item.get("keyId") == args.key_id]
    if not matches:
        sys.exit(f"error: no API key with keyId {args.key_id!r}")
    return matches


def cmd_revoke(args: argparse.Namespace) -> None:
    table = _table(args)
    for item in _matches(args):
        table.update_item(
            Key={"pk": item["pk"], "sk": item["sk"]},
            UpdateExpression="SET revoked = :t",
            ExpressionAttributeValues={":t": True},
        )
        print(f"revoked keyId {args.key_id} (label={item.get('label')!r})")
    print("note: API Gateway caches authorizer verdicts for up to 60 seconds")


def cmd_set_scopes(args: argparse.Namespace) -> None:
    """Replace the scope list. The caller must repeat every scope the key should keep."""
    scopes = _parse_scopes(args.scopes)
    matches = _matches(args)
    table = _table(args)
    for item in matches:
        previous = item.get("scopes") or []
        if isinstance(previous, list):
            previous_text = ",".join(str(scope) for scope in previous)
        else:
            previous_text = str(previous)
        table.update_item(
            Key={"pk": item["pk"], "sk": item["sk"]},
            UpdateExpression="SET scopes = :s",
            ExpressionAttributeValues={":s": scopes},
        )
        print(f"keyId {args.key_id} scopes {previous_text} -> {','.join(scopes)} (label={item.get('label')!r})")
    print("note: API Gateway caches authorizer verdicts for up to 60 seconds")
    print("note: a scope the deployed authorizer does not know is ignored until that deploy")


def cmd_set_write(args: argparse.Namespace) -> None:
    if args.allow_write == args.read_only:
        sys.exit("error: pass exactly one of --allow-write or --read-only")
    allow = bool(args.allow_write)
    table = _table(args)
    for item in _matches(args):
        table.update_item(
            Key={"pk": item["pk"], "sk": item["sk"]},
            UpdateExpression="SET allowWrite = :w",
            ExpressionAttributeValues={":w": allow},
        )
        print(f"{'enabled' if allow else 'disabled'} write on keyId {args.key_id} (label={item.get('label')!r})")
    print("note: API Gateway caches authorizer verdicts for up to 60 seconds")
    print("note: stack PublicApiWritesEnabled must be true for writes to succeed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--table", default=DEFAULT_TABLE)
    common.add_argument("--region", default=DEFAULT_REGION)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", parents=[common], help="mint a new API key")
    create.add_argument("--label", required=True)
    create.add_argument("--tier", default=BUILT_TIER, help="only admin is built")
    create.add_argument(
        "--scopes",
        default=SCOPE_SYSTEM,
        help=f"comma-separated scopes (default: system). Allowed: {', '.join(sorted(ALL_SCOPES))}",
    )
    create.add_argument("--allow-write", action="store_true")
    create.add_argument("--expires-at", default=None)
    create.add_argument("--allowed-cidrs", default=None)
    create.add_argument("--plaintext-out", default=None)
    create.set_defaults(func=cmd_create)

    listing = sub.add_parser("list", parents=[common], help="list keys (digests are never shown)")
    listing.set_defaults(func=cmd_list)

    revoke = sub.add_parser("revoke", parents=[common], help="revoke a key by keyId")
    revoke.add_argument("--key-id", required=True)
    revoke.set_defaults(func=cmd_revoke)

    set_write = sub.add_parser("set-write", parents=[common], help="enable or disable writes on a key")
    set_write.add_argument("--key-id", required=True)
    set_write.add_argument("--allow-write", action="store_true")
    set_write.add_argument("--read-only", action="store_true")
    set_write.set_defaults(func=cmd_set_write)

    set_scopes = sub.add_parser(
        "set-scopes",
        parents=[common],
        help="replace the scope list on a key",
    )
    set_scopes.add_argument("--key-id", required=True)
    set_scopes.add_argument(
        "--scopes",
        required=True,
        help="comma-separated scopes that replace the current list; repeat every scope to keep. "
        f"Allowed: {', '.join(sorted(ALL_SCOPES))}",
    )
    set_scopes.set_defaults(func=cmd_set_scopes)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
