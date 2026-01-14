"""
Graph Expander Dispatcher - Dispatches top packages for dependency discovery.

Triggered by EventBridge every Tuesday at 1:00 AM UTC (weekly).
Uses SQS fan-out pattern to avoid Lambda timeout issues.

This is Phase 1 of the sustainable package discovery system.
"""

import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")

PACKAGES_TABLE = os.environ.get("PACKAGES_TABLE", "pkgwatch-packages")
DISCOVERY_QUEUE_URL = os.environ.get("DISCOVERY_QUEUE_URL")
MAX_PACKAGES = 300  # Reduced from 500 for safety per opus review
BATCH_SIZE = 10  # Packages per SQS message


def handler(event, context):
    """Dispatch discovery jobs for top packages."""
    if not DISCOVERY_QUEUE_URL:
        logger.error("DISCOVERY_QUEUE_URL not configured")
        return {"statusCode": 500, "error": "DISCOVERY_QUEUE_URL not configured"}

    # Check circuit breaker first (prevents cascading failures)
    try:
        from shared.circuit_breaker import DEPSDEV_CIRCUIT

        if not DEPSDEV_CIRCUIT.can_execute():
            logger.warning("Skipping - deps.dev circuit open")
            return {
                "statusCode": 200,
                "body": json.dumps({"skipped": "circuit_open"}),
            }
    except ImportError:
        pass  # Circuit breaker not available in test environment

    table = dynamodb.Table(PACKAGES_TABLE)
    packages = []

    # Query tier 1 and tier 2 packages (most popular)
    # These are the packages whose dependencies we want to discover
    for tier in [1, 2]:
        try:
            response = table.query(
                IndexName="tier-index",
                KeyConditionExpression=Key("tier").eq(tier),
                Limit=MAX_PACKAGES // 2,
                ScanIndexForward=False,  # Most recently updated first
            )
            packages.extend(response.get("Items", []))
        except Exception as e:
            logger.error(f"Failed to query tier {tier} packages: {e}")

    logger.info(f"Found {len(packages)} tier 1-2 packages for discovery")

    if not packages:
        return {
            "statusCode": 200,
            "body": json.dumps({"dispatched": 0, "messages": 0}),
        }

    # Send to discovery queue in batches
    messages_sent = 0
    errors = 0

    for i in range(0, len(packages), BATCH_SIZE):
        batch = packages[i : i + BATCH_SIZE]
        package_names = []

        for pkg in batch:
            pk = pkg.get("pk", "")
            if "#" in pk:
                _, name = pk.split("#", 1)
                package_names.append(name)

        if not package_names:
            continue

        try:
            sqs.send_message(
                QueueUrl=DISCOVERY_QUEUE_URL,
                MessageBody=json.dumps(
                    {
                        "packages": package_names,
                        "ecosystem": "npm",
                    }
                ),
            )
            messages_sent += 1
        except Exception as e:
            logger.error(f"Failed to send batch {i // BATCH_SIZE}: {e}")
            errors += 1

    # Emit metrics
    try:
        from shared.metrics import emit_batch_metrics

        emit_batch_metrics(
            [
                {"metric_name": "GraphExpanderPackages", "value": len(packages)},
                {"metric_name": "GraphExpanderMessages", "value": messages_sent},
                {"metric_name": "GraphExpanderErrors", "value": errors},
            ]
        )
    except ImportError:
        pass  # Metrics not available in test environment

    logger.info(f"Dispatched {len(packages)} packages in {messages_sent} messages")

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "dispatched": len(packages),
                "messages": messages_sent,
                "errors": errors,
            }
        ),
    }
