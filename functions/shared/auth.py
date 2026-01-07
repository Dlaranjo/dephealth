"""
Authentication and API Key Management.

Handles:
- API key generation
- API key validation (using GSI for O(1) lookup)
- Usage tracking
- Tier limits
"""

import hashlib
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
API_KEYS_TABLE = os.environ.get("API_KEYS_TABLE", "dephealth-api-keys")

# Monthly request limits by tier
TIER_LIMITS = {
    "free": 5000,
    "starter": 25000,
    "pro": 100000,
    "business": 500000,
}


def generate_api_key(user_id: str, tier: str = "free", email: str = None) -> str:
    """
    Generate a new API key for a user.

    Args:
        user_id: Unique user identifier
        tier: Subscription tier (free, starter, pro, business)
        email: Optional user email for reference

    Returns:
        The generated API key (only returned once, store securely!)
    """
    # Generate secure random key with prefix
    api_key = f"dh_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    table = dynamodb.Table(API_KEYS_TABLE)

    table.put_item(
        Item={
            "pk": user_id,
            "sk": key_hash,
            "key_hash": key_hash,  # Duplicated for GSI
            "tier": tier,
            "requests_this_month": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "email": email,
        }
    )

    return api_key


def validate_api_key(api_key: str) -> Optional[dict]:
    """
    Validate API key and return user info.

    Uses key-hash-index GSI for O(1) lookup.

    Args:
        api_key: The API key to validate (e.g., "dh_abc123...")

    Returns:
        User info dict or None if invalid
    """
    if not api_key:
        return None

    # Check prefix
    if not api_key.startswith("dh_"):
        return None

    # Hash the key for lookup
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    table = dynamodb.Table(API_KEYS_TABLE)

    try:
        # Query using GSI for O(1) lookup by key hash
        response = table.query(
            IndexName="key-hash-index",
            KeyConditionExpression=Key("key_hash").eq(key_hash),
        )

        items = response.get("Items", [])
        if not items:
            return None

        item = items[0]
        tier = item.get("tier", "free")

        return {
            "user_id": item["pk"],
            "key_hash": item["sk"],  # Return for use in increment_usage
            "tier": tier,
            "monthly_limit": TIER_LIMITS.get(tier, TIER_LIMITS["free"]),
            "requests_this_month": item.get("requests_this_month", 0),
            "created_at": item.get("created_at"),
            "email": item.get("email"),
        }

    except Exception as e:
        # Log error but don't expose details
        print(f"Error validating API key: {e}")
        return None


def increment_usage(user_id: str, key_hash: str, count: int = 1) -> int:
    """
    Increment monthly usage counter.

    Uses atomic counter in DynamoDB for concurrency safety.

    Args:
        user_id: User's partition key (pk)
        key_hash: Key hash (sort key / sk)
        count: Number to increment by (default 1, use higher for batch operations)

    Returns:
        New usage count
    """
    table = dynamodb.Table(API_KEYS_TABLE)

    response = table.update_item(
        Key={"pk": user_id, "sk": key_hash},
        UpdateExpression="ADD requests_this_month :inc",
        ExpressionAttributeValues={":inc": count},
        ReturnValues="UPDATED_NEW",
    )

    return response.get("Attributes", {}).get("requests_this_month", 0)


def reset_monthly_usage(user_id: str, key_hash: str) -> None:
    """
    Reset monthly usage counter (called at start of each month).

    Args:
        user_id: User's partition key
        key_hash: Key hash (sort key)
    """
    table = dynamodb.Table(API_KEYS_TABLE)

    table.update_item(
        Key={"pk": user_id, "sk": key_hash},
        UpdateExpression="SET requests_this_month = :zero, last_reset = :now",
        ExpressionAttributeValues={
            ":zero": 0,
            ":now": datetime.now(timezone.utc).isoformat(),
        },
    )


def update_tier(user_id: str, key_hash: str, new_tier: str) -> None:
    """
    Update user's subscription tier.

    Args:
        user_id: User's partition key
        key_hash: Key hash (sort key)
        new_tier: New tier (free, starter, pro, business)
    """
    if new_tier not in TIER_LIMITS:
        raise ValueError(f"Invalid tier: {new_tier}")

    table = dynamodb.Table(API_KEYS_TABLE)

    table.update_item(
        Key={"pk": user_id, "sk": key_hash},
        UpdateExpression="SET tier = :tier, tier_updated_at = :now",
        ExpressionAttributeValues={
            ":tier": new_tier,
            ":now": datetime.now(timezone.utc).isoformat(),
        },
    )


def revoke_api_key(user_id: str, key_hash: str) -> None:
    """
    Revoke (delete) an API key.

    Args:
        user_id: User's partition key
        key_hash: Key hash (sort key)
    """
    table = dynamodb.Table(API_KEYS_TABLE)
    table.delete_item(Key={"pk": user_id, "sk": key_hash})


def get_user_keys(user_id: str) -> list[dict]:
    """
    Get all API keys for a user.

    Args:
        user_id: User's partition key

    Returns:
        List of key metadata (not the actual keys!)
    """
    table = dynamodb.Table(API_KEYS_TABLE)

    response = table.query(
        KeyConditionExpression=Key("pk").eq(user_id),
    )

    return [
        {
            "key_hash_prefix": item["sk"][:8] + "...",
            "tier": item.get("tier"),
            "created_at": item.get("created_at"),
            "requests_this_month": item.get("requests_this_month", 0),
        }
        for item in response.get("Items", [])
    ]
