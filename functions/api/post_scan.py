"""
Scan Endpoint - POST /scan

Scans a package.json file and returns health scores for all dependencies.
Requires API key authentication.
"""

import asyncio
import json
import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Import from shared module (bundled with Lambda)
from shared.auth import validate_api_key, check_and_increment_usage_batch
from shared.response_utils import error_response, decimal_default

PACKAGES_TABLE = os.environ.get("PACKAGES_TABLE", "dephealth-packages")

# Lazy initialization of boto3 clients
_dynamodb = None
_packages_table = None


def get_packages_table():
    """Lazy initialize DynamoDB packages table."""
    global _dynamodb, _packages_table
    if _packages_table is None:
        _dynamodb = boto3.resource("dynamodb")
        _packages_table = _dynamodb.Table(PACKAGES_TABLE)
    return _packages_table


def _batch_get_sync(batch_keys: list) -> dict:
    """Synchronous batch get for thread pool."""
    dynamodb = boto3.resource("dynamodb")
    response = dynamodb.batch_get_item(
        RequestItems={PACKAGES_TABLE: {"Keys": batch_keys}}
    )
    return response


async def _batch_get_all(all_keys: list) -> list:
    """Fetch all batches concurrently using thread pool."""
    loop = asyncio.get_event_loop()

    # Split into batches of 25 (DynamoDB limit)
    batches = [all_keys[i:i + 25] for i in range(0, len(all_keys), 25)]

    # Use thread pool for concurrent boto3 calls (boto3 is not async-native)
    with ThreadPoolExecutor(max_workers=10) as executor:
        tasks = [
            loop.run_in_executor(executor, _batch_get_sync, batch)
            for batch in batches
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    return results


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
        return error_response(401, "invalid_api_key", "Invalid or missing API key")

    # Parse request body
    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return error_response(400, "invalid_json", "Request body must be valid JSON")

    # Extract dependencies
    dependencies = _extract_dependencies(body)

    if not dependencies:
        return error_response(
            400,
            "no_dependencies",
            "No dependencies found. Provide 'content' (package.json string) or 'dependencies' object.",
        )

    # Atomically check rate limit and reserve quota for this scan
    # This prevents race conditions where concurrent scans can exceed the limit
    allowed, new_count = check_and_increment_usage_batch(
        user["user_id"],
        user["key_hash"],
        user["monthly_limit"],
        len(dependencies),
    )
    if not allowed:
        remaining = user["monthly_limit"] - new_count
        return error_response(
            429,
            "rate_limit_exceeded",
            f"Scanning {len(dependencies)} packages would exceed your remaining {remaining} requests.",
        )
    remaining = user["monthly_limit"] - new_count

    # Fetch scores for all dependencies using concurrent batch reads
    results = []
    not_found = []

    # Build all keys
    dep_list = list(dependencies)
    all_keys = [{"pk": f"npm#{name}", "sk": "LATEST"} for name in dep_list]
    dep_set = set(dep_list)  # Track which packages we've processed

    # Run concurrent batches using asyncio
    loop = asyncio.new_event_loop()
    try:
        batch_results = loop.run_until_complete(_batch_get_all(all_keys))
    finally:
        loop.close()

    # Process results from all batches
    for batch_response in batch_results:
        if isinstance(batch_response, Exception):
            logger.error(f"Batch request failed: {batch_response}")
            continue

        # Process found items
        for item in batch_response.get("Responses", {}).get(PACKAGES_TABLE, []):
            package_name = item["pk"].split("#", 1)[1]
            if package_name in dep_set:
                dep_set.discard(package_name)
                results.append({
                    "package": package_name,
                    "health_score": item.get("health_score"),
                    "risk_level": item.get("risk_level"),
                    "abandonment_risk": item.get("abandonment_risk", {}),
                    "is_deprecated": item.get("is_deprecated", False),
                    "archived": item.get("archived", False),
                    "last_updated": item.get("last_updated"),
                })

    # Any remaining items in dep_set were not found
    not_found.extend(dep_set)

    # Usage was already atomically reserved at the start of the request
    # based on len(dependencies) - this prevents race conditions

    # Calculate counts by risk level
    critical_count = sum(1 for r in results if r["risk_level"] == "CRITICAL")
    high_count = sum(1 for r in results if r["risk_level"] == "HIGH")
    medium_count = sum(1 for r in results if r["risk_level"] == "MEDIUM")
    low_count = sum(1 for r in results if r["risk_level"] == "LOW")

    # Sort results by risk (CRITICAL first, LOW last)
    risk_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, None: 4}
    results.sort(key=lambda x: (risk_order.get(x["risk_level"], 4), x["package"]))

    # Response format matches CLI/Action ScanResult interface:
    # { total, critical, high, medium, low, packages }
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "X-RateLimit-Limit": str(user["monthly_limit"]),
            "X-RateLimit-Remaining": str(remaining),  # Already reflects reserved quota
        },
        "body": json.dumps({
            "total": len(dependencies),
            "critical": critical_count,
            "high": high_count,
            "medium": medium_count,
            "low": low_count,
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
        content = body["content"]
        # Security: Ensure content is a string before parsing
        if isinstance(content, str):
            try:
                package_json = json.loads(content)
                deps = package_json.get("dependencies", {})
                dev_deps = package_json.get("devDependencies", {})
                if isinstance(deps, dict):
                    dependencies.update(deps.keys())
                if isinstance(dev_deps, dict):
                    dependencies.update(dev_deps.keys())
            except (json.JSONDecodeError, AttributeError):
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
