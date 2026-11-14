"""Shared boto clients and engine constants."""

from __future__ import annotations

import logging

import boto3

ADMIN_GROUP = "admin"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_ddb = boto3.resource("dynamodb")
