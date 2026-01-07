"""
Get Package Endpoint - GET /packages/{ecosystem}/{name}

Returns health score and details for a single package.
Requires API key authentication.
"""

import calendar
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Import from shared module (bundled with Lambda)
from shared.auth import validate_api_key, increment_usage


def decimal_default(obj):
    """JSON encoder for Decimal types from DynamoDB."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

dynamodb = boto3.resource("dynamodb")
PACKAGES_TABLE = os.environ.get("PACKAGES_TABLE", "dephealth-packages")


def handler(event, context):
    """
    Lambda handler for GET /packages/{ecosystem}/{name}.

    Returns package health score and related data.
    """
    # Extract API key from headers
    headers = event.get("headers", {})
    api_key = headers.get("x-api-key") or headers.get("X-API-Key")

    # Validate API key
    user = validate_api_key(api_key)

    if not user:
        return _error_response(401, "invalid_api_key", "Invalid or missing API key")

    # Check rate limit
    if user["requests_this_month"] >= user["monthly_limit"]:
        return _rate_limit_response(user)

    # Extract path parameters
    path_params = event.get("pathParameters", {})
    ecosystem = path_params.get("ecosystem", "npm")
    name = path_params.get("name")

    if not name:
        return _error_response(400, "missing_parameter", "Package name is required")

    # Handle URL-encoded package names (e.g., %40babel%2Fcore -> @babel/core)
    from urllib.parse import unquote
    name = unquote(name)

    # Validate ecosystem
    if ecosystem not in ["npm"]:  # Can expand later: "pypi", "maven", etc.
        return _error_response(
            400,
            "invalid_ecosystem",
            f"Unsupported ecosystem: {ecosystem}. Supported: npm",
        )

    # Fetch package from DynamoDB
    table = dynamodb.Table(PACKAGES_TABLE)

    try:
        response = table.get_item(Key={"pk": f"{ecosystem}#{name}", "sk": "LATEST"})
        item = response.get("Item")
    except Exception as e:
        logger.error(f"DynamoDB error: {e}")
        return _error_response(500, "internal_error", "Failed to fetch package data")

    if not item:
        return _error_response(
            404,
            "package_not_found",
            f"Package '{name}' not found in {ecosystem}",
        )

    # Increment usage counter
    try:
        increment_usage(user["user_id"], user["key_hash"])
    except Exception as e:
        logger.warning(f"Failed to increment usage: {e}")

    # Format response
    response_data = {
        "package": name,
        "ecosystem": ecosystem,
        "health_score": item.get("health_score"),
        "risk_level": item.get("risk_level"),
        "abandonment_risk": item.get("abandonment_risk"),
        "components": item.get("score_components"),
        "confidence": item.get("confidence"),
        "signals": {
            "weekly_downloads": item.get("weekly_downloads"),
            "dependents_count": item.get("dependents_count"),
            "stars": item.get("stars"),
            "days_since_last_commit": item.get("days_since_last_commit"),
            "commits_90d": item.get("commits_90d"),
            "active_contributors_90d": item.get("active_contributors_90d"),
            "maintainer_count": item.get("maintainer_count"),
            "is_deprecated": item.get("is_deprecated"),
            "archived": item.get("archived"),
            "openssf_score": item.get("openssf_score"),
        },
        "advisories": item.get("advisories", []),
        "latest_version": item.get("latest_version"),
        "last_published": item.get("last_published"),
        "repository_url": item.get("repository_url"),
        "last_updated": item.get("last_updated"),
    }

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "X-RateLimit-Limit": str(user["monthly_limit"]),
            "X-RateLimit-Remaining": str(
                user["monthly_limit"] - user["requests_this_month"] - 1
            ),
        },
        "body": json.dumps(response_data, default=decimal_default),
    }


def _error_response(status_code: int, code: str, message: str) -> dict:
    """Generate error response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": {"code": code, "message": message}}),
    }


def _rate_limit_response(user: dict) -> dict:
    """Generate rate limit exceeded response with Retry-After header."""
    now = datetime.now(timezone.utc)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    seconds_until_reset = (days_in_month - now.day) * 86400 + (24 - now.hour) * 3600

    return {
        "statusCode": 429,
        "headers": {
            "Content-Type": "application/json",
            "Retry-After": str(seconds_until_reset),
            "X-RateLimit-Limit": str(user["monthly_limit"]),
            "X-RateLimit-Remaining": "0",
        },
        "body": json.dumps({
            "error": {
                "code": "rate_limit_exceeded",
                "message": f"Monthly limit of {user['monthly_limit']} requests exceeded",
                "retry_after_seconds": seconds_until_reset,
                "upgrade_url": "https://dephealth.laranjo.dev/pricing",
            }
        }),
    }
