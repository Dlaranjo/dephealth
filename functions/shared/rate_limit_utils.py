"""
Rate Limiting Utilities

Shared functions for rate limit calculations, usage alerts, and reset timestamps.
Used by API endpoints (get_package, post_scan) to provide consistent rate limit
information to users.
"""

from datetime import datetime, timezone
from typing import Optional


def get_reset_timestamp() -> int:
    """Get Unix timestamp for start of next month (when usage resets).

    Returns:
        Unix timestamp (seconds since epoch) for 00:00:00 UTC on the first day
        of next month.
    """
    now = datetime.now(timezone.utc)

    # First day of next month
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

    return int(next_month.timestamp())


def check_usage_alerts(user: dict, current_usage: int) -> Optional[dict]:
    """Check if user is approaching rate limit and return alert info.

    Provides tiered alerts at 80%, 95%, and 100% thresholds to help users
    monitor their API usage.

    Args:
        user: User dict with monthly_limit key
        current_usage: Current number of requests this month

    Returns:
        Alert dict with level, percent, and message if alert needed, None otherwise.

    Example:
        >>> user = {"monthly_limit": 5000}
        >>> check_usage_alerts(user, 4800)
        {
            "level": "critical",
            "percent": 96.0,
            "message": "Only 200 requests remaining this month"
        }
    """
    limit = user.get("monthly_limit", 5000)
    usage_percent = (current_usage / limit) * 100 if limit > 0 else 100

    if usage_percent >= 100:
        return {
            "level": "exceeded",
            "percent": 100,
            "message": f"Monthly limit exceeded. Upgrade at https://dephealth.laranjo.dev/pricing",
        }
    elif usage_percent >= 95:
        return {
            "level": "critical",
            "percent": round(usage_percent, 1),
            "message": f"Only {limit - current_usage} requests remaining this month",
        }
    elif usage_percent >= 80:
        return {
            "level": "warning",
            "percent": round(usage_percent, 1),
            "message": f"{round(100 - usage_percent, 1)}% of monthly quota remaining",
        }

    return None
