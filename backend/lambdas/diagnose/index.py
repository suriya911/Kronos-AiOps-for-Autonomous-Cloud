"""
AIOps — Diagnose Lambda  (Phase 3)
===================================
Called by Step Functions (Diagnose state) after an anomaly is detected.

Flow:
  1. Discover all Lambda log groups with the project prefix
  2. Run CloudWatch Logs Insights query for last hour of ERROR/EXCEPTION lines
  3. Poll until complete (max 28 s — Lambda timeout is 60 s)
  4. Parse top 5 error patterns → build a one-line root cause string
  5. Patch aiops_incidents DynamoDB record with diagnosis
  6. Return structured diagnosis to Step Functions (stored in $.diagnosis)

Input  (from Step Functions — full incident context):
  { incidentId, type, severity, alarmName, metricValue, zScore, detectedAt, ... }

Output (stored at $.diagnosis):
  { incidentId, rootCause, topErrors, queryId, logGroupsQueried }
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
_logs   = boto3.client("logs")
_dynamo = boto3.resource("dynamodb")

# ─── Environment ──────────────────────────────────────────────────────────────
INCIDENTS_TABLE = os.environ["INCIDENTS_TABLE"]
ENVIRONMENT     = os.environ.get("ENVIRONMENT", "dev")

# Derive project prefix from table name: "aiops_incidents" → "aiops"
_PROJECT_PREFIX = INCIDENTS_TABLE.split("_")[0]

QUERY_TIMEOUT_SECONDS = 28   # Logs Insights can take ~30 s; Lambda timeout is 60 s
LOG_WINDOW_SECONDS    = 3600 # Query the last 60 minutes


# ═══════════════════════════════════════════════════════════════════════════════
# Handler
# ═══════════════════════════════════════════════════════════════════════════════

def handler(event: dict, context) -> dict:
    incident_id   = event.get("incidentId", "unknown")
    incident_type = event.get("type", "UNKNOWN")
    alarm_name    = event.get("alarmName", "")

    logger.info(json.dumps({
        "message":    "diagnose invoked",
        "incidentId": incident_id,
        "type":       incident_type,
        "alarmName":  alarm_name,
    }))

    # 1. Discover project Lambda log groups
    log_groups = _discover_log_groups(f"/aws/lambda/{_PROJECT_PREFIX}")
    if not log_groups:
        # Fallback to the anomaly detector log group (always exists)
        log_groups = [f"/aws/lambda/{_PROJECT_PREFIX}-anomaly-detector"]

    # 2. Run Logs Insights query
    top_errors, query_id = _run_insights_query(log_groups, incident_type)

    # 3. Summarise root cause
    root_cause = _summarise_root_cause(top_errors, incident_type, alarm_name)

    # 4. Patch DynamoDB incident record
    _update_incident_diagnosis(incident_id, root_cause, top_errors)

    result = {
        "incidentId":       incident_id,
        "rootCause":        root_cause,
        "topErrors":        top_errors,
        "queryId":          query_id,
        "logGroupsQueried": log_groups,
    }

    logger.info(json.dumps({
        "message":    "diagnosis_complete",
        "incidentId": incident_id,
        "rootCause":  root_cause,
        "errorCount": len(top_errors),
        "queryId":    query_id,
    }))

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Log group discovery
# ═══════════════════════════════════════════════════════════════════════════════

def _discover_log_groups(prefix: str) -> list[str]:
    """Return up to 10 log group names starting with the given prefix."""
    try:
        resp = _logs.describe_log_groups(logGroupNamePrefix=prefix, limit=10)
        groups = [g["logGroupName"] for g in resp.get("logGroups", [])]
        logger.info(json.dumps({"message": "log_groups_discovered", "count": len(groups), "groups": groups}))
        return groups
    except ClientError as exc:
        logger.warning(json.dumps({"message": "log_groups_discovery_failed", "error": str(exc)}))
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# CloudWatch Logs Insights query
# ═══════════════════════════════════════════════════════════════════════════════

def _run_insights_query(log_groups: list[str], incident_type: str) -> tuple[list[dict], str]:
    """
    Start a Logs Insights query and poll until done.
    Returns (top_errors_list, query_id).
    """
    end_time   = int(time.time())
    start_time = end_time - LOG_WINDOW_SECONDS

    # Pattern matches ERROR, Exception, CRITICAL, Traceback, Failed, fatal
    query_string = (
        "fields @timestamp, @message, @logStream "
        "| filter @message like /(?i)(error|exception|critical|traceback|failed|fatal)/ "
        "| sort @timestamp desc "
        "| limit 20"
    )

    try:
        start_resp = _logs.start_query(
            logGroupNames=log_groups,
            startTime=start_time,
            endTime=end_time,
            queryString=query_string,
        )
        query_id = start_resp["queryId"]
        logger.info(json.dumps({"message": "logs_insights_started", "queryId": query_id}))
    except ClientError as exc:
        logger.warning(json.dumps({"message": "logs_insights_start_failed", "error": str(exc)}))
        return [], "none"

    # Poll until complete or timeout
    deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS
    status   = "Running"
    raw      = []

    while time.monotonic() < deadline and status in ("Running", "Scheduled"):
        time.sleep(2)
        try:
            poll = _logs.get_query_results(queryId=query_id)
            status = poll.get("status", "Running")
            raw    = poll.get("results", [])
        except ClientError as exc:
            logger.warning(json.dumps({"message": "logs_insights_poll_failed", "error": str(exc)}))
            break

    logger.info(json.dumps({
        "message":  "logs_insights_complete",
        "queryId":  query_id,
        "status":   status,
        "rowCount": len(raw),
    }))

    # Parse raw rows into structured dicts
    top_errors: list[dict] = []
    for row in raw[:5]:
        row_dict = {field["field"]: field["value"] for field in row}
        top_errors.append({
            "timestamp": row_dict.get("@timestamp", ""),
            "message":   row_dict.get("@message", "")[:300],   # truncate long stack traces
            "logStream": row_dict.get("@logStream", ""),
        })

    return top_errors, query_id


# ═══════════════════════════════════════════════════════════════════════════════
# Root cause summarisation
# ═══════════════════════════════════════════════════════════════════════════════

_PATTERN_MAP: list[tuple[str, str]] = [
    ("out of memory",        "Memory exhaustion in Lambda logs — likely cause of MEMORY anomaly."),
    ("memoryerror",          "Python MemoryError raised — Lambda is running out of heap space."),
    ("timeout",              "Timeout errors — service is under heavy load or a downstream dependency is slow."),
    ("timed out",            "Timeout errors — service is under heavy load or a downstream dependency is slow."),
    ("connection refused",   "Connection refused — downstream service or database may be unavailable."),
    ("connectionerror",      "Network connectivity error — downstream service or database may be unreachable."),
    ("throttl",              "AWS API throttling — Lambda function is hitting service rate limits."),
    ("no space",             "Disk space exhaustion — /tmp or attached volume may be full."),
    ("disk",                 "Disk-related error — check /tmp usage or EBS volume."),
    ("cpu",                  "CPU-related error — process may be compute-bound or in a tight loop."),
    ("traceback",            "Unhandled exception (Traceback) detected in Lambda logs."),
    ("exception",            "Exception detected in Lambda logs — check stack trace."),
]


def _summarise_root_cause(
    top_errors: list[dict],
    incident_type: str,
    alarm_name: str,
) -> str:
    """Return a one-line root cause string based on log patterns."""
    if not top_errors:
        return (
            f"No recent errors found in CloudWatch Logs for the last hour. "
            f"Incident type: {incident_type} (alarm: {alarm_name}). "
            f"Possible infrastructure-level event outside Lambda logs."
        )

    first_msg = top_errors[0].get("message", "").lower()

    for pattern, explanation in _PATTERN_MAP:
        if pattern in first_msg:
            return explanation

    # Generic fallback
    snippet = top_errors[0].get("message", "")[:120]
    return f"{len(top_errors)} recent error(s) found. Top: {snippet}"


# ═══════════════════════════════════════════════════════════════════════════════
# DynamoDB update
# ═══════════════════════════════════════════════════════════════════════════════

def _update_incident_diagnosis(
    incident_id: str,
    root_cause: str,
    top_errors: list[dict],
) -> None:
    """Patch rootCause and topErrors onto the DynamoDB incident record."""
    try:
        table = _dynamo.Table(INCIDENTS_TABLE)
        table.update_item(
            Key={"incidentId": incident_id},
            UpdateExpression=(
                "SET rootCause = :rc, topErrors = :te, diagnosedAt = :da"
            ),
            ExpressionAttributeValues={
                ":rc": root_cause,
                ":te": top_errors,
                ":da": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
    except ClientError as exc:
        logger.warning(json.dumps({
            "message":    "update_diagnosis_failed",
            "incidentId": incident_id,
            "error":      str(exc),
        }))
