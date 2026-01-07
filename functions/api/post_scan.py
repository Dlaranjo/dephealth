"""
Scan Endpoint - POST /scan

Scans a package.json file and returns health scores for all dependencies.
Requires API key authentication.
"""

import json
import logging
import os
from decimal import Decimal
from typing import Optional

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
    Lambda handler for POST /scan.

    Request body:
    {
        "content": "<package.json content as string>"
    }
    or
    {
        "dependencies": {"lodash": "^4.17.21", "express": "^4.18.0"}
    }

    Returns health scores for all dependencies.
    """
    # Extract API key
    headers = event.get("headers", {})
    api_key = headers.get("x-api-key") or headers.get("X-API-Key")

    # Validate API key
    user = validate_api_key(api_key)

    if not user:
        return _error_response(401, "invalid_api_key", "Invalid or missing API key")

    # Parse request body
    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return _error_response(400, "invalid_json", "Request body must be valid JSON")

    # Extract dependencies
    dependencies = _extract_dependencies(body)

    if not dependencies:
        return _error_response(
            400,
            "no_dependencies",
            "No dependencies found. Provide 'content' (package.json string) or 'dependencies' object.",
        )

    # Check rate limit (each package counts as one request)
    remaining = user["monthly_limit"] - user["requests_this_month"]
    if remaining < len(dependencies):
        return _error_response(
            429,
            "rate_limit_exceeded",
            f"Scanning {len(dependencies)} packages would exceed your remaining {remaining} requests.",
        )

    # Fetch scores for all dependencies
    table = dynamodb.Table(PACKAGES_TABLE)
    results = []
    not_found = []

    for package_name in dependencies:
        try:
            response = table.get_item(
                Key={"pk": f"npm#{package_name}", "sk": "LATEST"}
            )
            item = response.get("Item")

            if item:
                results.append({
                    "package": package_name,
                    "health_score": item.get("health_score"),
                    "risk_level": item.get("risk_level"),
                    "abandonment_risk": item.get("abandonment_risk", {}).get(
                        "probability"
                    ),
                    "is_deprecated": item.get("is_deprecated", False),
                    "archived": item.get("archived", False),
                    "last_updated": item.get("last_updated"),
                })
            else:
                not_found.append(package_name)

        except Exception as e:
            logger.error(f"Error fetching {package_name}: {e}")
            not_found.append(package_name)

    # Increment usage by the number of packages we looked up (not found + found)
    # This prevents rate limit bypass by scanning many packages for 1 request
    packages_looked_up = len(results) + len(not_found)
    try:
        increment_usage(user["user_id"], user["key_hash"], count=packages_looked_up)
    except Exception as e:
        logger.warning(f"Failed to increment usage: {e}")

    # Calculate summary statistics
    scores = [r["health_score"] for r in results if r["health_score"] is not None]
    summary = {
        "total_dependencies": len(dependencies),
        "scored": len(results),
        "not_found": len(not_found),
        "risk_breakdown": {
            "critical": sum(1 for r in results if r["risk_level"] == "CRITICAL"),
            "high": sum(1 for r in results if r["risk_level"] == "HIGH"),
            "medium": sum(1 for r in results if r["risk_level"] == "MEDIUM"),
            "low": sum(1 for r in results if r["risk_level"] == "LOW"),
        },
        "average_health_score": round(sum(scores) / len(scores), 1) if scores else None,
        "deprecated_count": sum(1 for r in results if r.get("is_deprecated")),
        "archived_count": sum(1 for r in results if r.get("archived")),
    }

    # Sort results by risk (CRITICAL first, LOW last)
    risk_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, None: 4}
    results.sort(key=lambda x: (risk_order.get(x["risk_level"], 4), x["package"]))

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "X-RateLimit-Limit": str(user["monthly_limit"]),
            "X-RateLimit-Remaining": str(remaining - 1),
        },
        "body": json.dumps({
            "summary": summary,
            "packages": results,
            "not_found": not_found,
        }, default=decimal_default),
    }


def _extract_dependencies(body: dict) -> list[str]:
    """
    Extract dependency names from request body.

    Supports:
    - {"content": "<package.json string>"}
    - {"dependencies": {...}}
    - {"devDependencies": {...}}
    """
    dependencies = set()

    # Option 1: Parse package.json content string
    if "content" in body:
        try:
            package_json = json.loads(body["content"])
            deps = package_json.get("dependencies", {})
            dev_deps = package_json.get("devDependencies", {})
            dependencies.update(deps.keys())
            dependencies.update(dev_deps.keys())
        except json.JSONDecodeError:
            pass

    # Option 2: Direct dependencies object
    if "dependencies" in body:
        deps = body["dependencies"]
        if isinstance(deps, dict):
            dependencies.update(deps.keys())
        elif isinstance(deps, list):
            dependencies.update(deps)

    if "devDependencies" in body:
        dev_deps = body["devDependencies"]
        if isinstance(dev_deps, dict):
            dependencies.update(dev_deps.keys())
        elif isinstance(dev_deps, list):
            dependencies.update(dev_deps)

    # Filter out invalid entries
    return [d for d in dependencies if d and isinstance(d, str)]


def _error_response(status_code: int, code: str, message: str) -> dict:
    """Generate error response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": {"code": code, "message": message}}),
    }
