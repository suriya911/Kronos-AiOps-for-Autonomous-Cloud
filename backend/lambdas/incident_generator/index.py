"""
AIOps — Incident Generator Lambda
===================================
Triggered by EventBridge on a rate(3 days) schedule.
Writes 2–4 realistic synthetic incidents to DynamoDB so the dashboard
always has fresh data to demonstrate the platform's capabilities.

Each incident includes:
  - Full incident fields (type, severity, status, MTTR, etc.)
  - rootCause, topErrors, metricHistory, timeline timestamps
  - Associated remediation record (for RESOLVED incidents)
"""

from __future__ import annotations

import json
import logging
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3

# ─── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ─── AWS clients ──────────────────────────────────────────────────────────────
_dynamo = boto3.resource("dynamodb")

# ─── Environment ──────────────────────────────────────────────────────────────
INCIDENTS_TABLE    = os.environ["INCIDENTS_TABLE"]
REMEDIATIONS_TABLE = os.environ["REMEDIATIONS_TABLE"]
ENVIRONMENT        = os.environ.get("ENVIRONMENT", "dev")

# ─── Incident templates ────────────────────────────────────────────────────────

TEMPLATES = [
    {
        "type":      "CPU",
        "alarmName": "aiops-high-cpu-utilization",
        "rootCause": "Runaway process consuming 100% CPU — likely a memory leak in the application worker pool causing infinite retry loops.",
        "topErrors": [
            "FATAL: Worker process exceeded CPU quota (100%) for 5 consecutive minutes",
            "ERROR: Request queue depth exceeded 10,000 — shedding load",
            "WARN:  GC overhead limit exceeded — heap at 98%",
        ],
        "actionType":  "RESTART_SERVICE",
        "target":      "aws:ec2:us-east-1/i-0abc123def456789",
        "metricRange": (75.0, 99.5),
        "ewmaRange":   (60.0, 80.0),
        "zScoreRange": (3.2, 5.8),
    },
    {
        "type":      "MEMORY",
        "alarmName": "aiops-high-memory-utilization",
        "rootCause": "Memory leak in Node.js service — heap snapshots show retained DOM event listeners accumulating over time without being garbage-collected.",
        "topErrors": [
            "ERROR: JavaScript heap out of memory — allocation failed",
            "WARN:  Resident set size (RSS) exceeded 4 GB threshold",
            "ERROR: ENOMEM — cannot allocate memory for new buffer",
        ],
        "actionType":  "CLEAR_CACHE",
        "target":      "aws:ec2:us-east-1/i-0def456abc123789",
        "metricRange": (88.0, 97.0),
        "ewmaRange":   (70.0, 85.0),
        "zScoreRange": (3.5, 6.2),
    },
    {
        "type":      "DISK",
        "alarmName": "aiops-high-disk-utilization",
        "rootCause": "Application log rotation misconfigured — /var/log partition filled by uncompressed debug logs written at ERROR level due to upstream service timeouts.",
        "topErrors": [
            "ERROR: No space left on device — write failed on /var/log/app",
            "CRITICAL: Disk usage at 95% on /dev/xvda1 (partition: root)",
            "WARN:  Log rotation failed — logrotate: error opening /var/log/app.log",
        ],
        "actionType":  "ROTATE_LOGS",
        "target":      "aws:ec2:us-east-1/i-0789abc123def456",
        "metricRange": (90.0, 98.0),
        "ewmaRange":   (75.0, 88.0),
        "zScoreRange": (4.0, 7.1),
    },
    {
        "type":      "LATENCY",
        "alarmName": "aiops-high-api-latency",
        "rootCause": "Database connection pool exhaustion — all 100 connections held by long-running analytical queries blocking transactional traffic. N+1 query pattern detected in ORM layer.",
        "topErrors": [
            "ERROR: Connection pool timeout after 30s — pool size: 100/100 active",
            "WARN:  Query execution time exceeded 10s for 47 requests in the last minute",
            "ERROR: deadlock detected — process 12345 waits for ShareLock on transaction",
        ],
        "actionType":  "SCALE_OUT",
        "target":      "aws:rds:us-east-1/aiops-prod-db",
        "metricRange": (250.0, 850.0),
        "ewmaRange":   (180.0, 400.0),
        "zScoreRange": (3.8, 6.5),
    },
    {
        "type":      "CPU",
        "alarmName": "aiops-batch-cpu-spike",
        "rootCause": "Scheduled batch ETL job triggered at peak traffic hours — data pipeline processing 2M records simultaneously causing CPU saturation across all worker nodes.",
        "topErrors": [
            "WARN:  CPU steal time elevated (28%) — noisy neighbour detected on hypervisor",
            "ERROR: Batch job timeout after 3600s — partial results committed",
            "INFO:  Auto-scaling triggered — 3 new instances launching",
        ],
        "actionType":  "SCALE_OUT",
        "target":      "aws:autoscaling:us-east-1/aiops-asg-workers",
        "metricRange": (82.0, 96.0),
        "ewmaRange":   (65.0, 78.0),
        "zScoreRange": (3.3, 5.1),
    },
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _float_range(lo: float, hi: float) -> float:
    return round(random.uniform(lo, hi), 2)


def _metric_history(peak: float, length: int = 20) -> list[float]:
    """Generate a realistic metric history that builds up to the peak."""
    baseline = peak * 0.4
    history = []
    for i in range(length):
        frac = i / (length - 1)
        noise = random.uniform(-3.0, 3.0)
        val = round(baseline + (peak - baseline) * (frac ** 1.5) + noise, 2)
        history.append(max(0.0, min(val, 100.0 if peak <= 100 else val)))
    return history


def _generate_incident(template: dict, base_time: datetime) -> tuple[dict, dict | None]:
    """
    Build one incident dict + optional remediation dict.
    Returns (incident, remediation_or_None).
    """
    incident_id    = str(uuid.uuid4())
    remediation_id = str(uuid.uuid4())

    detected_at   = base_time
    diagnosed_at  = detected_at + timedelta(seconds=random.randint(8, 25))
    remediated_at = diagnosed_at + timedelta(seconds=random.randint(15, 90))
    resolved_at   = remediated_at + timedelta(seconds=random.randint(5, 30))

    metric_val = _float_range(*template["metricRange"])
    ewma_val   = _float_range(*template["ewmaRange"])
    z_score    = _float_range(*template["zScoreRange"])

    # Randomly decide: RESOLVED (auto), ESCALATED, or OPEN
    outcome_roll = random.random()
    if outcome_roll < 0.65:
        status   = "RESOLVED"
        method   = "AUTO_REMEDIATED"
        mttr_ms  = int((resolved_at - detected_at).total_seconds() * 1000)
        severity = "WARNING" if z_score < 4.5 else "CRITICAL"
        resolved_ts = _iso(resolved_at)
    elif outcome_roll < 0.85:
        status   = "ESCALATED"
        method   = "HUMAN_REQUIRED"
        mttr_ms  = None
        severity = "CRITICAL"
        resolved_ts = None
    else:
        status   = "OPEN"
        method   = None
        mttr_ms  = None
        severity = "CRITICAL" if z_score > 4.0 else "WARNING"
        resolved_ts = None

    incident: dict = {
        "incidentId":    incident_id,
        "type":          template["type"],
        "status":        status,
        "severity":      severity,
        "detectedAt":    _iso(detected_at),
        "diagnosedAt":   _iso(diagnosed_at),
        "resolvedAt":    resolved_ts,
        "alarmName":     template["alarmName"],
        "metricValue":   Decimal(str(metric_val)),
        "ewmaValue":     Decimal(str(ewma_val)),
        "zScore":        Decimal(str(z_score)),
        "rootCause":     template["rootCause"],
        "topErrors":     template["topErrors"],
        "metricHistory": [Decimal(str(v)) for v in _metric_history(metric_val)],
        "method":        method,
        "remediationId": remediation_id if status == "RESOLVED" else None,
        "executionArn":  (
            f"arn:aws:states:us-east-1:807430513014:execution:"
            f"aiops-incident-workflow:{incident_id[:8]}"
        ),
    }
    if mttr_ms:
        incident["mttr"] = Decimal(str(mttr_ms))

    # Build remediation record for RESOLVED incidents
    remediation: dict | None = None
    if status == "RESOLVED":
        duration_ms = int((resolved_at - diagnosed_at).total_seconds() * 1000)
        remediation = {
            "remediationId": remediation_id,
            "incidentId":    incident_id,
            "actionType":    template["actionType"],
            "target":        template["target"],
            "ssmCommandId":  f"cmd-{uuid.uuid4().hex[:16]}",
            "status":        "SUCCESS",
            "durationMs":    Decimal(str(duration_ms)),
            "createdAt":     _iso(diagnosed_at),
        }

    return incident, remediation


def handler(event: dict, context) -> dict:
    """
    EventBridge scheduled trigger — generate and write 2–4 synthetic incidents.
    """
    logger.info(json.dumps({"message": "incident_generator_triggered", "event": str(event)}))

    incidents_table    = _dynamo.Table(INCIDENTS_TABLE)
    remediations_table = _dynamo.Table(REMEDIATIONS_TABLE)

    now        = _utcnow()
    n_to_gen   = random.randint(2, 4)
    selected   = random.sample(TEMPLATES, k=min(n_to_gen, len(TEMPLATES)))

    # Space incidents across the last 72 hours so they look organic
    written = 0
    for i, tmpl in enumerate(selected):
        hours_ago = random.uniform(i * 5, i * 5 + 48)
        base_time = now - timedelta(hours=hours_ago)

        incident, remediation = _generate_incident(tmpl, base_time)

        # Write incident
        incidents_table.put_item(Item=incident)

        # Write remediation (if any)
        if remediation:
            remediations_table.put_item(Item=remediation)

        logger.info(json.dumps({
            "message":    "incident_written",
            "incidentId": incident["incidentId"],
            "type":       incident["type"],
            "status":     incident["status"],
            "severity":   incident["severity"],
        }))
        written += 1

    logger.info(json.dumps({"message": "generation_complete", "written": written}))
    return {"statusCode": 200, "body": json.dumps({"generated": written})}
