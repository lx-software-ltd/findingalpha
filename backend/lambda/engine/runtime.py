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
    """Return the DynamoDB resource, creating it on the first call.

    Importing this module does not need an AWS region. Lambda sets
    ``AWS_REGION`` before a handler runs. Tests patch ``store`` and do
    not call this.
    """
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
    return _ddb
