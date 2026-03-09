"""
AIOps — WebSocket Connect/Disconnect Handler  (Phase 4)
=========================================================
Handles API Gateway WebSocket lifecycle routes:
  $connect    → store connectionId in aiops_ws_connections (with TTL)
  $disconnect → remove connectionId from aiops_ws_connections

DynamoDB item schema (aiops_ws_connections):
  PK: connectionId  (String)
  connectedAt       (String — ISO-8601)
  expiresAt         (Number — epoch seconds, DynamoDB TTL attribute)
  sourceIp          (String)

API Gateway requires this Lambda to return HTTP 200 within 29 s;
any non-2xx rejects the connection / triggers disconnect.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

# ─── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ─── AWS clients ──────────────────────────────────────────────────────────────
_dynamo = boto3.resource("dynamodb")

# ─── Environment ──────────────────────────────────────────────────────────────
WS_CONNECTIONS_TABLE = os.environ["WS_CONNECTIONS_TABLE"]
_CONNECTION_TTL_SECONDS = 7_200   # 2 hours — API Gateway max WebSocket duration


# ═══════════════════════════════════════════════════════════════════════════════
# Handler
# ═══════════════════════════════════════════════════════════════════════════════

def handler(event: dict, context) -> dict:
    """
    Dispatches to _connect or _disconnect based on routeKey.

    Event shape from API Gateway WebSocket:
      { "requestContext": { "routeKey": "$connect"|"$disconnect",
                             "connectionId": "Abc123==",
                             "connectedAt": 1705312345000,
                             "identity": { "sourceIp": "1.2.3.4" } } }
    """
    request_context = event.get("requestContext", {})
    route_key       = request_context.get("routeKey", "unknown")
    connection_id   = request_context.get("connectionId", "unknown")
    source_ip       = request_context.get("identity", {}).get("sourceIp", "unknown")

    logger.info(json.dumps({
        "message":      "ws_connect handler invoked",
        "routeKey":     route_key,
        "connectionId": connection_id,
        "sourceIp":     source_ip,
    }))

    try:
        if route_key == "$connect":
            return _connect(connection_id, source_ip)
        elif route_key == "$disconnect":
            return _disconnect(connection_id)
        else:
            logger.warning(json.dumps({
                "message":  "unexpected_route_key",
                "routeKey": route_key,
            }))
            return {"statusCode": 200, "body": "OK"}

    except Exception as exc:
        logger.error(json.dumps({
            "message":   "ws_connect_handler_error",
            "routeKey":  route_key,
            "error":     str(exc),
            "errorType": type(exc).__name__,
        }))
        # Return 500 — API Gateway will drop the connection on $connect failure
        return {"statusCode": 500, "body": json.dumps({"error": "Internal Server Error"})}


# ═══════════════════════════════════════════════════════════════════════════════
# Connect
# ═══════════════════════════════════════════════════════════════════════════════

def _connect(connection_id: str, source_ip: str) -> dict:
    """Store the new connectionId in DynamoDB with a 2-hour TTL."""
    now       = datetime.now(timezone.utc)
    now_epoch = int(now.timestamp())

    try:
        table = _dynamo.Table(WS_CONNECTIONS_TABLE)
        table.put_item(Item={
            "connectionId": connection_id,
            "connectedAt":  now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expiresAt":    now_epoch + _CONNECTION_TTL_SECONDS,   # DynamoDB TTL
            "sourceIp":     source_ip,
        })
        logger.info(json.dumps({
            "message":      "connection_stored",
            "connectionId": connection_id,
            "expiresAt":    now_epoch + _CONNECTION_TTL_SECONDS,
        }))
    except ClientError as exc:
        logger.error(json.dumps({
            "message":      "store_connection_failed",
            "connectionId": connection_id,
            "error":        str(exc),
        }))
        return {"statusCode": 500, "body": "Failed to store connection"}

    return {"statusCode": 200, "body": json.dumps({"connected": True, "connectionId": connection_id})}


# ═══════════════════════════════════════════════════════════════════════════════
# Disconnect
# ═══════════════════════════════════════════════════════════════════════════════

def _disconnect(connection_id: str) -> dict:
    """Remove the connectionId from DynamoDB on WebSocket close."""
    try:
        table = _dynamo.Table(WS_CONNECTIONS_TABLE)
        table.delete_item(Key={"connectionId": connection_id})
        logger.info(json.dumps({
            "message":      "connection_removed",
            "connectionId": connection_id,
        }))
    except ClientError as exc:
        # Log but don't fail — the client is already gone
        logger.warning(json.dumps({
            "message":      "remove_connection_failed",
            "connectionId": connection_id,
            "error":        str(exc),
        }))

    return {"statusCode": 200, "body": json.dumps({"disconnected": True})}
