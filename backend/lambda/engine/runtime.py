"""Shared boto clients and engine constants."""

from __future__ import annotations

import logging
import os

import boto3

ADMIN_GROUP = "admin"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Lambda always sets AWS_REGION. Tests and CI do not, and a recent botocore
# refuses to build a client until a region exists. Do not override a real one.
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-1")

_ddb = boto3.resource("dynamodb")
