"""
Usage Endpoint - GET /usage

Returns API usage statistics for the current API key.
Requires API key authentication.
"""

import calendar
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Import from shared module (bundled with Lambda)
from shared.auth import validate_api_key, TIER_LIMITS


def decimal_default(obj):
    """JSON encoder for Decimal types from DynamoDB."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def handler(event, context):
    """
    Lambda handler for GET /usage.

    Returns current usage statistics and limits.
    """
    # Extract API key
    headers = event.get("headers", {})
    api_key = headers.get("x-api-key") or headers.get("X-API-Key")

    # Validate API key
    user = validate_api_key(api_key)

    if not user:
        return {
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "error": {
                    "code": "invalid_api_key",
                    "message": "Invalid or missing API key",
                }
            }),
        }

    # Calculate reset date (first of next month)
    now = datetime.now(timezone.utc)
    if now.month == 12:
        reset_date = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        reset_date = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

    seconds_until_reset = (reset_date - now).total_seconds()

    # Calculate usage percentage
    usage_percentage = (
        user["requests_this_month"] / user["monthly_limit"] * 100
        if user["monthly_limit"] > 0
        else 0
    )

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "X-RateLimit-Limit": str(user["monthly_limit"]),
            "X-RateLimit-Remaining": str(
                max(0, user["monthly_limit"] - user["requests_this_month"])
            ),
        },
        "body": json.dumps({
            "tier": user["tier"],
            "usage": {
                "requests_this_month": user["requests_this_month"],
                "monthly_limit": user["monthly_limit"],
                "remaining": max(0, user["monthly_limit"] - user["requests_this_month"]),
                "usage_percentage": round(usage_percentage, 1),
            },
            "reset": {
                "date": reset_date.isoformat(),
                "seconds_until_reset": int(seconds_until_reset),
            },
            "limits_by_tier": {
                tier: limit for tier, limit in TIER_LIMITS.items()
            },
        }, default=decimal_default),
    }
