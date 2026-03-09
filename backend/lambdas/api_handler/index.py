"""
AIOps — HTTP API Handler Lambda  (Phase 5)
==========================================
Single Lambda behind an API Gateway v2 HTTP API ($default route).
Dispatches internally by HTTP method + rawPath.

Routes:
  GET  /incidents              → list incidents (optional ?status=, ?limit=)
  GET  /incidents/{id}         → incident detail + remediation record
  GET  /kpi                    → computed KPI metrics
  GET  /metrics                → CloudWatch datapoints (?range=1h|6h|24h|7d|30d)
  GET  /remediations           → remediation audit log
  GET  /settings               → guardrails + thresholds from SSM
  PATCH /settings/guardrails   → save guardrail allowlist to SSM
  PATCH /settings/thresholds   → save detection thresholds to SSM

All responses include CORS headers (allow_origins is also enforced by API GW).
DynamoDB Decimal values are coerced to int/float before JSON serialisation.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

# ─── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ─── AWS clients ──────────────────────────────────────────────────────────────
_dynamo = boto3.resource("dynamodb")
_cw     = boto3.client("cloudwatch")
_ssm    = boto3.client("ssm")

# ─── Environment ──────────────────────────────────────────────────────────────
INCIDENTS_TABLE      = os.environ["INCIDENTS_TABLE"]
REMEDIATIONS_TABLE   = os.environ["REMEDIATIONS_TABLE"]
METRICS_CACHE_TABLE  = os.environ["METRICS_CACHE_TABLE"]
SSM_GUARDRAILS_PARAM = os.environ["SSM_GUARDRAILS_PARAM"]
SSM_THRESHOLDS_PARAM = os.environ["SSM_THRESHOLDS_PARAM"]
ENVIRONMENT          = os.environ.get("ENVIRONMENT", "dev")

# ─── CORS headers returned on every response ──────────────────────────────────
CORS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,PATCH,OPTIONS",
    "Content-Type":                 "application/json",
}

# ─── Enum mapping: backend → frontend ─────────────────────────────────────────
METHOD_MAP: dict[str | None, str] = {
    "AUTO_REMEDIATED": "AUTO",
    "HUMAN_REQUIRED":  "ESCALATED",
    None:              "MANUAL",
}

STATUS_MAP: dict[str, str] = {
    "OPEN":               "OPEN",
    "RESOLVED":           "RESOLVED",
    "ESCALATED":          "ESCALATED",
    "REMEDIATION_FAILED": "ERROR",
    "ERROR":              "ERROR",
}

ALL_INCIDENT_TYPES = ["CPU", "MEMORY", "DISK", "LATENCY", "UNKNOWN"]


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def handler(event: dict, context) -> dict:
    """Dispatch on HTTP method + rawPath."""
    rc     = event.get("requestContext", {}).get("http", {})
    method = rc.get("method", "GET")
    path   = event.get("rawPath", "/")
    qs     = event.get("queryStringParameters") or {}

    logger.info(json.dumps({
        "message": "api_handler invoked",
        "method":  method,
        "path":    path,
        "qs":      qs,
    }))

    try:
        # OPTIONS preflight — API GW handles it but Lambda catches $default
        if method == "OPTIONS":
            return _ok({})

        if method == "GET":
            # /incidents/{id}
            m = re.match(r"^/incidents/([^/]+)$", path)
            if m:
                return _get_incident(m.group(1))

            if path == "/incidents":
                return _list_incidents(qs)

            if path == "/kpi":
                return _get_kpi()

            if path == "/metrics":
                return _get_metrics(qs)

            if path == "/remediations":
                return _list_remediations(qs)

            if path == "/settings":
                return _get_settings()

            return _err(f"Unknown path: {path}", 404)

        if method == "PATCH":
            body = json.loads(event.get("body") or "{}")

            if path == "/settings/guardrails":
                return _save_guardrails(body)

            if path == "/settings/thresholds":
                return _save_thresholds(body)

            return _err(f"Unknown path: {path}", 404)

        return _err(f"Method not allowed: {method}", 405)

    except ClientError as exc:
        logger.error(json.dumps({"message": "aws_client_error", "error": str(exc)}))
        return _err(str(exc), 502)
    except Exception as exc:
        logger.error(json.dumps({"message": "unhandled_error", "error": str(exc),
                                  "errorType": type(exc).__name__}))
        return _err("Internal server error", 500)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _ok(body: dict | list, status: int = 200) -> dict:
    return {"statusCode": status, "headers": CORS, "body": json.dumps(body)}


def _err(message: str, status: int = 500) -> dict:
    return {"statusCode": status, "headers": CORS, "body": json.dumps({"error": message})}


def _coerce(obj: Any) -> Any:
    """Recursively convert DynamoDB Decimal → int/float for JSON serialisation."""
    if isinstance(obj, Decimal):
        f = float(obj)
        if math.isnan(f) or math.isinf(f):
            return None
        return int(f) if obj == obj.to_integral_value() else f
    if isinstance(obj, (list, tuple)):
        return [_coerce(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _coerce(v) for k, v in obj.items()}
    return obj


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _ms_between(ts1: str | None, ts2: str | None) -> int | None:
    t1, t2 = _parse_iso(ts1), _parse_iso(ts2)
    if t1 and t2:
        return int((t2 - t1).total_seconds() * 1000)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Incident transform
# ═══════════════════════════════════════════════════════════════════════════════

def _transform_incident(item: dict) -> dict:
    """Map DynamoDB incident item → frontend Incident shape."""
    return {
        "incidentId":    item.get("incidentId", ""),
        "type":          item.get("type", "UNKNOWN"),
        "status":        STATUS_MAP.get(item.get("status", "OPEN"), "ERROR"),
        "severity":      item.get("severity", "WARNING"),
        "detectedAt":    item.get("detectedAt", ""),
        "resolvedAt":    item.get("resolvedAt") or None,
        "mttr":          _coerce(item.get("mttr")),
        "method":        METHOD_MAP.get(item.get("method")),  # type: ignore[arg-type]
        "alarmName":     item.get("alarmName", ""),
        "metricValue":   _coerce(item.get("metricValue", 0)),
        "zScore":        _coerce(item.get("zScore", 0)),
        "executionArn":  item.get("executionArn"),
        "remediationId": item.get("remediationId"),
    }


def _derive_resource_id(item: dict) -> str:
    """
    Derive a human-readable resourceId from the alarm name.
    Example: 'aiops-high-cpu-utilization' → 'aws:ec2:us-east-1'
    The actual EC2 instance ID isn't persisted in DynamoDB.
    """
    alarm = item.get("alarmName", "")
    if "cpu" in alarm.lower() or "memory" in alarm.lower() or "disk" in alarm.lower():
        return "aws:ec2:us-east-1"
    if "latency" in alarm.lower() or "alb" in alarm.lower():
        return "aws:alb:us-east-1"
    return "aws:unknown:us-east-1"


def _reconstruct_timeline(item: dict) -> list[dict]:
    """
    Build a timeline array from individual timestamp fields stored in DynamoDB.
    DynamoDB stores each phase's timestamp separately; the frontend expects an array.
    """
    detected  = item.get("detectedAt")
    diagnosed = item.get("diagnosedAt")
    resolved  = item.get("resolvedAt")
    escalated = item.get("escalatedAt")

    timeline: list[dict] = []

    if detected:
        timeline.append({"state": "ALARM_TRIGGERED", "ts": detected})

    if diagnosed and detected:
        timeline.append({
            "state":      "DIAGNOSIS_DONE",
            "ts":         diagnosed,
            "durationMs": _ms_between(detected, diagnosed),
        })

    if resolved:
        prev = diagnosed or detected
        timeline.append({
            "state":      "INCIDENT_CLOSED",
            "ts":         resolved,
            "durationMs": _ms_between(prev, resolved),
        })
    elif escalated:
        prev = diagnosed or detected
        timeline.append({
            "state":      "ESCALATED",
            "ts":         escalated,
            "durationMs": _ms_between(prev, escalated),
        })

    return timeline


def _flatten_top_errors(raw: list) -> list[str]:
    """Convert DynamoDB topErrors (List[str] or List[Map]) → string[]."""
    result = []
    for e in raw:
        if isinstance(e, str):
            result.append(e)
        elif isinstance(e, dict):
            msg = e.get("message") or e.get("msg") or str(e)
            result.append(str(msg)[:300])
    return result


def _build_remediation_detail(rem: dict | None) -> dict | None:
    if not rem:
        return None
    return {
        "remediationId": rem.get("remediationId", ""),
        "actionType":    rem.get("actionType", ""),
        "target":        rem.get("target", ""),
        "ssmCommandId":  rem.get("ssmCommandId", ""),
        "status":        rem.get("status", ""),
        "durationMs":    _coerce(rem.get("durationMs", 0)),
        "log":           [],  # SSM command output not stored in DynamoDB
    }


# ═══════════════════════════════════════════════════════════════════════════════
# GET /incidents
# ═══════════════════════════════════════════════════════════════════════════════

def _list_incidents(qs: dict) -> dict:
    """
    Scan aiops_incidents. If ?status= provided, query the GSI instead.
    Returns { incidents: Incident[], count: number }.
    """
    table  = _dynamo.Table(INCIDENTS_TABLE)
    limit  = min(int(qs.get("limit", 200)), 500)
    status = qs.get("status")

    items: list[dict] = []

    if status:
        # Use status-detectedAt-index GSI for efficient filtered query
        resp = table.query(
            IndexName="status-detectedAt-index",
            KeyConditionExpression="#st = :st",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":st": status.upper()},
            Limit=limit,
            ScanIndexForward=False,   # newest first
        )
        items = resp.get("Items", [])
    else:
        # Full scan — low volume in dev, acceptable
        resp = table.scan(Limit=limit)
        items = resp.get("Items", [])

        # Sort newest first
        def _sort_key(i: dict) -> str:
            return i.get("detectedAt", "")
        items.sort(key=_sort_key, reverse=True)

    incidents = [_transform_incident(_coerce(i)) for i in items]

    logger.info(json.dumps({
        "message": "list_incidents",
        "status":  status,
        "count":   len(incidents),
    }))

    return _ok({"incidents": incidents, "count": len(incidents)})


# ═══════════════════════════════════════════════════════════════════════════════
# GET /incidents/{id}
# ═══════════════════════════════════════════════════════════════════════════════

def _get_incident(incident_id: str) -> dict:
    """
    Fetch full IncidentDetail: incident record + associated remediation (if any).
    """
    # Fetch incident
    table = _dynamo.Table(INCIDENTS_TABLE)
    resp  = table.get_item(Key={"incidentId": incident_id})
    item  = resp.get("Item")
    if not item:
        return _err("Incident not found", 404)

    item = _coerce(item)

    # Fetch associated remediation via incidentId-index GSI
    remediation: dict | None = None
    if item.get("remediationId"):
        rem_table = _dynamo.Table(REMEDIATIONS_TABLE)
        rem_resp  = rem_table.query(
            IndexName="incidentId-index",
            KeyConditionExpression="incidentId = :iid",
            ExpressionAttributeValues={":iid": incident_id},
            Limit=1,
        )
        rem_items = rem_resp.get("Items", [])
        if rem_items:
            remediation = _coerce(rem_items[0])

    # Build IncidentDetail
    base = _transform_incident(item)
    top_errors_raw = item.get("topErrors", [])

    base.update({
        "resourceId":    _derive_resource_id(item),
        "ewmaValue":     item.get("ewmaValue", 0),
        "metricHistory": item.get("metricHistory", []),    # List[float], up to 20 pts
        "rootCause":     item.get("rootCause") or "",
        "diagnosis": {
            "topErrors":        _flatten_top_errors(top_errors_raw),
            "logInsightsQuery": (
                "fields @timestamp, @message | filter @message like /(?i)(error|exception)/ "
                "| sort @timestamp desc | limit 20"
            ),
        },
        "remediation":          _build_remediation_detail(remediation),
        "timeline":             _reconstruct_timeline(item),
        "diagnosedAt":          item.get("diagnosedAt"),
        "triageAt":             item.get("triageAt"),
        "guardrailCheckedAt":   item.get("guardrailCheckedAt"),
        "remediationStartedAt": item.get("remediationStartedAt"),
    })

    return _ok(base)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /kpi
# ═══════════════════════════════════════════════════════════════════════════════

def _get_kpi() -> dict:
    """
    Compute KPI metrics on the fly from the incidents table.
    No caching — volume is low and React Query caches client-side.
    """
    table = _dynamo.Table(INCIDENTS_TABLE)
    now   = _utcnow()
    cutoff = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Scan all incidents (dev has < 100; production should use a date-range GSI)
    resp  = table.scan()
    items = [_coerce(i) for i in resp.get("Items", [])]

    # Filter last 30 days
    recent = [
        i for i in items
        if i.get("detectedAt", "") >= cutoff
    ]

    # MTTR — average of RESOLVED incidents with mttr set (ms → seconds)
    resolved_with_mttr = [
        float(i["mttr"]) for i in recent
        if i.get("status") == "RESOLVED" and i.get("mttr") is not None
    ]
    mttr_s = round(statistics.mean(resolved_with_mttr) / 1000, 1) if resolved_with_mttr else 0.0

    # Auto-resolution rate — RESOLVED / (RESOLVED + ESCALATED)
    n_resolved  = sum(1 for i in recent if i.get("status") == "RESOLVED")
    n_escalated = sum(1 for i in recent if i.get("status") == "ESCALATED")
    total_closed = n_resolved + n_escalated
    auto_rate = round(n_resolved / total_closed * 100, 1) if total_closed > 0 else 0.0

    # Open incidents by severity
    open_items    = [i for i in items if i.get("status") in ("OPEN", "ERROR")]
    n_open        = len(open_items)
    n_critical    = sum(1 for i in open_items if i.get("severity") == "CRITICAL")
    n_warning     = n_open - n_critical

    # Detection latency — ms from detectedAt to diagnosedAt
    latencies = []
    for i in recent:
        ms = _ms_between(i.get("detectedAt"), i.get("diagnosedAt"))
        if ms and ms > 0:
            latencies.append(ms)
    avg_latency_s = round(statistics.mean(latencies) / 1000, 1) if latencies else 0.0

    kpi = {
        "mttr": {
            "value":             mttr_s,
            "unit":              "seconds",
            "changeVsBaseline":  0,
            "trend":             "down" if mttr_s < 60 else "up",
        },
        "autoResolutionRate": {
            "value":  auto_rate,
            "unit":   "%",
            "period": "last 30 days",
        },
        "openIncidents": {
            "total":    n_open,
            "critical": n_critical,
            "warning":  n_warning,
        },
        "detectionLatency": {
            "value": avg_latency_s,
            "unit":  "seconds",
        },
    }

    logger.info(json.dumps({
        "message":   "kpi_computed",
        "mttr_s":    mttr_s,
        "auto_rate": auto_rate,
        "open":      n_open,
    }))

    return _ok(kpi)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /metrics
# ═══════════════════════════════════════════════════════════════════════════════

def _get_metrics(qs: dict) -> dict:
    """
    Fetch CloudWatch metric datapoints for CPU, memory, disk, latency.
    ?range=1h|6h|24h|7d|30d  (default: 1h)

    Falls back to empty datapoints if no CloudWatch data exists (dev environment
    without real EC2 instances). Frontend Metrics page guards against empty arrays.
    """
    range_param = qs.get("range", "1h")
    hours_map   = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}
    hours       = hours_map.get(range_param, 1)
    period      = 300 if hours <= 6 else 3600   # 5-min or 1-hour resolution

    end_time   = _utcnow()
    start_time = end_time - timedelta(hours=hours)

    metric_queries = [
        {
            "Id":         "cpu",
            "MetricStat": {
                "Metric": {
                    "Namespace":  "AWS/EC2",
                    "MetricName": "CPUUtilization",
                    "Dimensions": [],
                },
                "Period": period,
                "Stat":   "Average",
            },
            "ReturnData": True,
        },
        {
            "Id":         "memory",
            "MetricStat": {
                "Metric": {
                    "Namespace":  "CWAgent",
                    "MetricName": "mem_used_percent",
                    "Dimensions": [],
                },
                "Period": period,
                "Stat":   "Average",
            },
            "ReturnData": True,
        },
        {
            "Id":         "disk",
            "MetricStat": {
                "Metric": {
                    "Namespace":  "CWAgent",
                    "MetricName": "disk_used_percent",
                    "Dimensions": [],
                },
                "Period": period,
                "Stat":   "Maximum",
            },
            "ReturnData": True,
        },
        {
            "Id":         "latency",
            "MetricStat": {
                "Metric": {
                    "Namespace":  "AWS/ApplicationELB",
                    "MetricName": "TargetResponseTime",
                    "Dimensions": [],
                },
                "Period": period,
                "Stat":   "p95",
            },
            "ReturnData": True,
        },
    ]

    # Attempt CloudWatch batch call
    cw_data: dict[str, list[dict]] = {
        "cpu": [], "memory": [], "disk": [], "latency": []
    }

    try:
        resp    = _cw.get_metric_data(
            MetricDataQueries=metric_queries,
            StartTime=start_time,
            EndTime=end_time,
        )
        for result in resp.get("MetricDataResults", []):
            mid        = result["Id"]
            timestamps = result.get("Timestamps", [])
            values     = result.get("Values", [])
            pairs = sorted(
                [{"ts": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "value": round(v, 2)}
                 for t, v in zip(timestamps, values)],
                key=lambda x: x["ts"],
            )
            cw_data[mid] = pairs
    except ClientError as exc:
        logger.warning(json.dumps({"message": "cloudwatch_fetch_failed", "error": str(exc)}))

    def _metric_shape(key: str, unit: str, threshold: float | None) -> dict:
        pts = cw_data.get(key, [])
        vals = [p["value"] for p in pts]
        return {
            "current":       vals[-1] if vals else 0.0,
            "min":           min(vals) if vals else 0.0,
            "max":           max(vals) if vals else 0.0,
            "avg":           round(sum(vals) / len(vals), 2) if vals else 0.0,
            "unit":          unit,
            "threshold":     threshold,
            "dataPoints":    pts,
            "dataAvailable": bool(pts),
        }

    result = {
        "range":   range_param,
        "cpu":     _metric_shape("cpu",     "%",   80.0),
        "memory":  _metric_shape("memory",  "%",   85.0),
        "disk":    _metric_shape("disk",    "%",   90.0),
        "latency": _metric_shape("latency", "ms",  200.0),
    }

    return _ok(result)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /remediations
# ═══════════════════════════════════════════════════════════════════════════════

def _list_remediations(qs: dict) -> dict:
    """Scan aiops_remediations, sorted newest first."""
    table = _dynamo.Table(REMEDIATIONS_TABLE)
    limit = min(int(qs.get("limit", 200)), 500)

    resp  = table.scan(Limit=limit)
    items = [_coerce(i) for i in resp.get("Items", [])]
    items.sort(key=lambda i: i.get("createdAt", ""), reverse=True)

    remediations = [
        {
            "remediationId": i.get("remediationId", ""),
            "incidentId":    i.get("incidentId", ""),
            "actionType":    i.get("actionType", ""),
            "target":        i.get("target", ""),
            "ssmCommandId":  i.get("ssmCommandId", ""),
            "status":        i.get("status", ""),
            "durationMs":    i.get("durationMs", 0),
            "executedAt":    i.get("createdAt", ""),
        }
        for i in items
    ]

    return _ok({"remediations": remediations, "count": len(remediations)})


# ═══════════════════════════════════════════════════════════════════════════════
# GET /settings
# ═══════════════════════════════════════════════════════════════════════════════

def _get_settings() -> dict:
    """
    Read both SSM parameters and return combined settings.

    SSM guardrails format: {"allowedTypes": ["CPU","MEMORY","DISK"], "version": N}
    SSM thresholds format: {"zScoreThreshold": 3.0, "ewmaAlpha": 0.3, "minDataPoints": 60}

    Frontend expects:
      guardrails: Array<{type: string, autoRemediate: boolean}>
      thresholds: {zScoreThreshold, ewmaAlpha, minDataPoints}
    """
    try:
        resp = _ssm.get_parameters(
            Names=[SSM_GUARDRAILS_PARAM, SSM_THRESHOLDS_PARAM],
            WithDecryption=False,
        )
    except ClientError as exc:
        return _err(f"SSM read failed: {exc}", 502)

    params_by_name = {p["Name"]: p["Value"] for p in resp.get("Parameters", [])}

    # Guardrails
    raw_guardrails = json.loads(params_by_name.get(SSM_GUARDRAILS_PARAM, "{}"))
    allowed        = set(raw_guardrails.get("allowedTypes", ["CPU", "MEMORY", "DISK"]))
    guardrails     = [
        {"type": t, "autoRemediate": t in allowed}
        for t in ALL_INCIDENT_TYPES
    ]

    # Thresholds
    raw_thresholds = json.loads(params_by_name.get(SSM_THRESHOLDS_PARAM, "{}"))
    thresholds     = {
        "zScoreThreshold": float(raw_thresholds.get("zScoreThreshold", 3.0)),
        "ewmaAlpha":       float(raw_thresholds.get("ewmaAlpha", 0.3)),
        "minDataPoints":   int(raw_thresholds.get("minDataPoints", 60)),
        "version":         int(raw_thresholds.get("version", 1)),
    }

    return _ok({
        "guardrails": guardrails,
        "thresholds": thresholds,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH /settings/guardrails
# ═══════════════════════════════════════════════════════════════════════════════

def _save_guardrails(body: dict) -> dict:
    """
    Accept {guardrails: [{type, autoRemediate}, ...]} and write to SSM.
    Increments version for cache busting in the anomaly_detector Lambda.
    """
    guardrails = body.get("guardrails", [])
    if not isinstance(guardrails, list):
        return _err("guardrails must be an array", 400)

    allowed = [g["type"] for g in guardrails if g.get("autoRemediate")]
    blocked = [g["type"] for g in guardrails if not g.get("autoRemediate")]

    # Read current to increment version
    try:
        resp    = _ssm.get_parameter(Name=SSM_GUARDRAILS_PARAM)
        current = json.loads(resp["Parameter"]["Value"])
        version = int(current.get("version", 1)) + 1
    except (ClientError, json.JSONDecodeError):
        version = 1

    new_value = json.dumps({
        "allowedTypes": allowed,
        "blockedTypes": blocked,
        "version":      version,
    })

    _ssm.put_parameter(
        Name=SSM_GUARDRAILS_PARAM,
        Value=new_value,
        Type="String",
        Overwrite=True,
    )

    logger.info(json.dumps({
        "message": "guardrails_saved",
        "allowed": allowed,
        "version": version,
    }))

    return _ok({"saved": True, "version": version, "allowedTypes": allowed})


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH /settings/thresholds
# ═══════════════════════════════════════════════════════════════════════════════

def _save_thresholds(body: dict) -> dict:
    """
    Accept {zScoreThreshold, ewmaAlpha, minDataPoints} and write to SSM.
    Anomaly detector reads this on its 5-minute cache refresh cycle.
    """
    thresholds = body.get("thresholds", body)   # accept top-level or nested

    z_score     = float(thresholds.get("zScoreThreshold", 3.0))
    ewma_alpha  = float(thresholds.get("ewmaAlpha", 0.3))
    min_pts     = int(thresholds.get("minDataPoints", 60))

    # Validation
    if not (1.0 <= z_score <= 10.0):
        return _err("zScoreThreshold must be between 1.0 and 10.0", 400)
    if not (0.05 <= ewma_alpha <= 0.95):
        return _err("ewmaAlpha must be between 0.05 and 0.95", 400)
    if not (5 <= min_pts <= 200):
        return _err("minDataPoints must be between 5 and 200", 400)

    try:
        resp    = _ssm.get_parameter(Name=SSM_THRESHOLDS_PARAM)
        current = json.loads(resp["Parameter"]["Value"])
        version = int(current.get("version", 1)) + 1
    except (ClientError, json.JSONDecodeError):
        version = 1

    new_value = json.dumps({
        "zScoreThreshold": z_score,
        "ewmaAlpha":       ewma_alpha,
        "minDataPoints":   min_pts,
        "version":         version,
    })

    _ssm.put_parameter(
        Name=SSM_THRESHOLDS_PARAM,
        Value=new_value,
        Type="String",
        Overwrite=True,
    )

    logger.info(json.dumps({
        "message":         "thresholds_saved",
        "zScoreThreshold": z_score,
        "ewmaAlpha":       ewma_alpha,
        "minDataPoints":   min_pts,
    }))

    return _ok({"saved": True, "zScoreThreshold": z_score, "ewmaAlpha": ewma_alpha,
                "minDataPoints": min_pts, "version": version})
