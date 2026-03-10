"""
AIOps — WebSocket Broadcast Lambda  (Phase 4)
===============================================
Triggered by DynamoDB Streams on the aiops_incidents table.

Flow for each stream record:
  1. Deserialize DynamoDB NewImage → plain Python dict
  2. Classify event type:
       INSERT → INCIDENT_CREATED
       MODIFY → INCIDENT_UPDATED  (with special labels for RESOLVED / ESCALATED)
  3. Scan aiops_ws_connections for all active connection IDs
  4. POST the JSON payload to every active connection via APIGW Management API
  5. Remove stale connections (410 GoneException)

Payload pushed to each client:
  {
    "event":      "INCIDENT_CREATED" | "INCIDENT_UPDATED" | "INCIDENT_RESOLVED" | "INCIDENT_ESCALATED",
    "incidentId": "<uuid>",
    "type":       "CPU" | "MEMORY" | "DISK" | "LATENCY" | "UNKNOWN",
    "severity":   "CRITICAL" | "WARNING",
    "status":     "OPEN" | "RESOLVED" | "ESCALATED" | "REMEDIATION_FAILED",
    "method":     "AUTO_REMEDIATED" | "HUMAN_REQUIRED" | null,
    "mttr":       297 | null,          # milliseconds
    "zScore":     391.81,
    "detectedAt": "2026-03-08T11:19:00Z",
    "resolvedAt": "2026-03-08T11:19:50Z" | null,
    "alarmName":  "aiops-high-cpu-utilization",
    "timestamp":  "2026-03-08T11:19:51Z"  # broadcast time
  }
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

# ─── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ─── AWS clients ──────────────────────────────────────────────────────────────
_dynamo = boto3.resource("dynamodb")

# API Gateway Management client — instantiated lazily after env var is read
_apigw: boto3.client = None   # type: ignore

# ─── Environment ──────────────────────────────────────────────────────────────
WS_CONNECTIONS_TABLE    = os.environ["WS_CONNECTIONS_TABLE"]
WEBSOCKET_API_ENDPOINT  = os.environ["WEBSOCKET_API_ENDPOINT"]   # https://id.execute-api.region.amazonaws.com/stage
ENVIRONMENT             = os.environ.get("ENVIRONMENT", "dev")

# ─── DynamoDB type deserialiser ────────────────────────────────────────────────
_deserializer = TypeDeserializer()


# ═══════════════════════════════════════════════════════════════════════════════
# Handler
# ═══════════════════════════════════════════════════════════════════════════════

def handler(event: dict, context) -> dict:
    """
    Entry point — processes a batch of DynamoDB stream records.

    Returns { statusCode, processed, skipped } so Lambda can log progress.
    Raising an exception causes Lambda to retry the batch (use only for
    transient errors — stale connection cleanup is idempotent).
    """
    global _apigw
    if _apigw is None:
        _apigw = boto3.client(
            "apigatewaymanagementapi",
            endpoint_url=WEBSOCKET_API_ENDPOINT,
        )

    records   = event.get("Records", [])
    processed = 0
    skipped   = 0

    logger.info(json.dumps({
        "message":     "ws_broadcast invoked",
        "recordCount": len(records),
    }))

    for record in records:
        event_name = record.get("eventName", "")
        if event_name not in ("INSERT", "MODIFY"):
            skipped += 1
            continue   # ignore REMOVE events

        raw_new = record.get("dynamodb", {}).get("NewImage", {})
        if not raw_new:
            skipped += 1
            continue

        try:
            incident = _deserialize_image(raw_new)
            payload  = _build_payload(event_name, incident)
            _broadcast(payload)
            processed += 1
        except Exception as exc:
            logger.error(json.dumps({
                "message":     "record_processing_error",
                "eventName":   event_name,
                "error":       str(exc),
                "errorType":   type(exc).__name__,
            }))
            skipped += 1

    logger.info(json.dumps({
        "message":   "ws_broadcast_complete",
        "processed": processed,
        "skipped":   skipped,
    }))

    return {"statusCode": 200, "processed": processed, "skipped": skipped}


# ═══════════════════════════════════════════════════════════════════════════════
# DynamoDB image deserialisation
# ═══════════════════════════════════════════════════════════════════════════════

def _deserialize_image(raw: dict) -> dict:
    """Convert DynamoDB JSON format to plain Python dict."""
    return {k: _deserializer.deserialize(v) for k, v in raw.items()}


# ═══════════════════════════════════════════════════════════════════════════════
# Payload builder
# ═══════════════════════════════════════════════════════════════════════════════

def _build_payload(event_name: str, incident: dict) -> dict:
    """
    Construct the WebSocket push payload.

    Event type mapping:
      INSERT              → INCIDENT_CREATED
      MODIFY + RESOLVED   → INCIDENT_RESOLVED
      MODIFY + ESCALATED  → INCIDENT_ESCALATED
      MODIFY (other)      → INCIDENT_UPDATED
    """
    status = incident.get("status", "OPEN")

    if event_name == "INSERT":
        ws_event = "INCIDENT_CREATED"
    elif status == "RESOLVED":
        ws_event = "INCIDENT_RESOLVED"
    elif status == "ESCALATED":
        ws_event = "INCIDENT_ESCALATED"
    else:
        ws_event = "INCIDENT_UPDATED"

    # Coerce Decimal → float for JSON serialisation
    def _to_num(v):
        if isinstance(v, Decimal):
            f = float(v)
            return int(f) if f.is_integer() else f
        return v

    return {
        "event":       ws_event,
        "incidentId":  incident.get("incidentId", ""),
        "type":        incident.get("type", "UNKNOWN"),
        "severity":    incident.get("severity", "WARNING"),
        "status":      status,
        "method":      incident.get("method"),
        "alarmName":   incident.get("alarmName", ""),
        "zScore":      _to_num(incident.get("zScore", 0)),
        "metricValue": _to_num(incident.get("metricValue", 0)),
        "mttr":        _to_num(incident.get("mttr")) if incident.get("mttr") is not None else None,
        "detectedAt":  incident.get("detectedAt", ""),
        "resolvedAt":  incident.get("resolvedAt"),
        "rootCause":   incident.get("rootCause"),
        "timestamp":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": ENVIRONMENT,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Broadcast to all connections
# ═══════════════════════════════════════════════════════════════════════════════

def _broadcast(payload: dict) -> None:
    """
    Scan the ws_connections table and POST payload to every active client.
    Stale connections (410 Gone) are deleted automatically.
    """
    table        = _dynamo.Table(WS_CONNECTIONS_TABLE)
    data_bytes   = json.dumps(payload).encode("utf-8")

    # Paginated scan — low volume expected (< 100 concurrent connections in dev)
    paginator_kwargs: dict = {}
    sent     = 0
    removed  = 0
    failed   = 0

    while True:
        resp          = table.scan(**paginator_kwargs)
        connections   = resp.get("Items", [])

        for conn in connections:
            cid = conn.get("connectionId", "")
            if not cid:
                continue

            try:
                _apigw.post_to_connection(
                    ConnectionId=cid,
                    Data=data_bytes,
                )
                sent += 1

            except ClientError as exc:
                error_code = exc.response["Error"]["Code"]

                if error_code == "GoneException":
                    # Client disconnected without proper $disconnect — clean up
                    try:
                        table.delete_item(Key={"connectionId": cid})
                        removed += 1
                        logger.info(json.dumps({
                            "message":      "stale_connection_removed",
                            "connectionId": cid,
                        }))
                    except ClientError:
                        pass   # best-effort cleanup

                else:
                    failed += 1
                    logger.warning(json.dumps({
                        "message":      "post_to_connection_failed",
                        "connectionId": cid,
                        "error":        str(exc),
                    }))

        # Continue pagination if there are more pages
        last_key = resp.get("LastEvaluatedKey")
        if last_key:
            paginator_kwargs = {"ExclusiveStartKey": last_key}
        else:
            break

    logger.info(json.dumps({
        "message":  "broadcast_complete",
        "event":    payload.get("event"),
        "sent":     sent,
        "removed":  removed,
        "failed":   failed,
        "incidentId": payload.get("incidentId"),
    }))
