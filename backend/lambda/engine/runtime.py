"""Shared boto clients and engine constants."""

from __future__ import annotations

import logging
from typing import Any

import boto3

ADMIN_GROUP = "admin"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_ddb: Any = None


def ddb() -> Any:
    """Return the DynamoDB resource, creating it on first use.

    Importing this module must not need an AWS region. Lambda sets
    ``AWS_REGION`` before any call. Tests stub the table instead.
    """
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
    return _ddb
