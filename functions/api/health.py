"""
Health Check Endpoint - GET /health

Returns API status and version information.
No authentication required.
"""

import json
from datetime import datetime, timezone


def handler(event, context):
    """
    Lambda handler for health check.

    Returns:
        200 with status information
    """
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        },
        "body": json.dumps({
            "status": "healthy",
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    }
