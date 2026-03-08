"""
AIOps — Anomaly Detector Lambda  (Phase 2)
==========================================
Triggered by: EventBridge rule on CloudWatch Alarm state change → ALARM

Flow:
  1. Parse alarm name + metric metadata from EventBridge event
  2. Read EWMA / Z-score thresholds from SSM Parameter Store
  3. Check DynamoDB metrics cache (< 60 s old) — skip CloudWatch call if fresh
  4. Cache miss → call CloudWatch GetMetricData for last 60 data points
  5. Run EWMA + rolling-window Z-score anomaly detection (stdlib only, no scipy)
  6. ANOMALY → classify type, write incident to DynamoDB, start Step Functions
  7. NORMAL  → structured log only, no DynamoDB write
  8. Any exception → write ERROR incident to DynamoDB, re-raise (DLQ captures it)
"""

from __future__ import annotations

import json
import logging
import os
import statistics
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

# ─── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ─── AWS clients (module-level = reused across warm invocations) ───────────────
_cw      = boto3.client("cloudwatch")
_dynamo  = boto3.resource("dynamodb")
_ssm     = boto3.client("ssm")
_sfn     = boto3.client("stepfunctions")

# ─── Environment variables ─────────────────────────────────────────────────────
INCIDENTS_TABLE      = os.environ["INCIDENTS_TABLE"]
METRICS_CACHE_TABLE  = os.environ["METRICS_CACHE_TABLE"]
STEP_FUNCTIONS_ARN   = os.environ["STEP_FUNCTIONS_ARN"]
SSM_THRESHOLDS_PARAM = os.environ["SSM_THRESHOLDS_PARAM"]
ENVIRONMENT          = os.environ.get("ENVIRONMENT", "dev")

# ─── Module-level caches (warm Lambda reuse) ──────────────────────────────────
_thresholds_cache: dict | None = None
_thresholds_fetched_at: float  = 0.0
_THRESHOLDS_TTL_SECONDS        = 300   # re-read SSM every 5 minutes


# ═══════════════════════════════════════════════════════════════════════════════
# Public handler
# ═══════════════════════════════════════════════════════════════════════════════

def handler(event: dict, context) -> dict:
    """
    Lambda entry point.

    EventBridge payload (CloudWatch Alarm state change):
    {
      "source": "aws.cloudwatch",
      "detail-type": "CloudWatch Alarm State Change",
      "detail": {
        "alarmName": "aiops-high-cpu-utilization",
        "state": { "value": "ALARM", "reason": "..." },
        "previousState": { "value": "OK" },
        "configuration": {
          "metrics": [
            { "metricStat": {
                "metric": { "namespace": "AWS/EC2", "name": "CPUUtilization",
                            "dimensions": [{"name":"InstanceId","value":"i-xxx"}] },
                "period": 60, "stat": "Average" } }
          ]
        }
      }
    }
    """
    alarm_name = "unknown"
    try:
        detail     = event.get("detail", {})
        alarm_name = detail.get("alarmName", "unknown")
        new_state  = detail.get("state", {}).get("value", "UNKNOWN")

        logger.info(json.dumps({
            "message": "anomaly_detector invoked",
            "alarmName": alarm_name,
            "newState": new_state,
            "environment": ENVIRONMENT,
        }))

        # 1. Thresholds from SSM (cached)
        thresholds      = _get_thresholds()
        z_threshold     = float(thresholds.get("zScoreThreshold", 3.0))
        ewma_alpha      = float(thresholds.get("ewmaAlpha", 0.3))
        min_data_points = int(thresholds.get("minDataPoints", 10))

        # 2. Extract metric metadata from event
        metric_info = _extract_metric_info(detail)

        # 3. Fetch metric values (cache-first)
        values = _get_metric_values(alarm_name, metric_info)

        if len(values) < min_data_points:
            logger.warning(json.dumps({
                "message": "insufficient data points — skipping detection",
                "alarmName": alarm_name,
                "pointsAvailable": len(values),
                "minRequired": min_data_points,
            }))
            return {"statusCode": 200, "body": json.dumps({"status": "INSUFFICIENT_DATA"})}

        # 4. Run EWMA + Z-score detection
        is_anomaly, z_score, ewma_value = _detect_anomaly(values, ewma_alpha, z_threshold)

        logger.info(json.dumps({
            "message": "detection_result",
            "alarmName": alarm_name,
            "isAnomaly": is_anomaly,
            "zScore": z_score,
            "ewmaValue": ewma_value,
            "latestValue": round(values[-1], 4),
            "dataPoints": len(values),
        }))

        if not is_anomaly:
            return {"statusCode": 200, "body": json.dumps({"status": "NORMAL", "zScore": z_score})}

        # 5. Write incident + start Step Functions
        incident_id  = str(uuid4())
        incident_type = _classify_type(alarm_name)
        severity      = "CRITICAL" if abs(z_score) > z_threshold * 1.5 else "WARNING"

        incident = _write_incident(
            incident_id   = incident_id,
            alarm_name    = alarm_name,
            incident_type = incident_type,
            severity      = severity,
            values        = values,
            z_score       = z_score,
            ewma_value    = ewma_value,
        )

        execution_arn = _start_step_functions(incident_id, incident)
        _update_incident_execution_arn(incident_id, execution_arn)

        logger.info(json.dumps({
            "message": "incident_created",
            "incidentId": incident_id,
            "type": incident_type,
            "severity": severity,
            "executionArn": execution_arn,
        }))

        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "ANOMALY",
                "incidentId": incident_id,
                "type": incident_type,
                "severity": severity,
                "zScore": z_score,
            }),
        }

    except Exception as exc:
        logger.error(json.dumps({
            "message": "anomaly_detector_error",
            "alarmName": alarm_name,
            "error": str(exc),
            "errorType": type(exc).__name__,
        }))
        # Write ERROR sentinel to DynamoDB so the incident is traceable
        try:
            _write_error_incident(alarm_name, exc)
        except Exception as inner:
            logger.error(json.dumps({"message": "failed_to_write_error_incident", "error": str(inner)}))
        raise   # re-raise → DLQ captures the raw event


# ═══════════════════════════════════════════════════════════════════════════════
# SSM — thresholds
# ═══════════════════════════════════════════════════════════════════════════════

def _get_thresholds() -> dict:
    """Read EWMA/Z-score thresholds from SSM. Cached in module memory for 5 min."""
    global _thresholds_cache, _thresholds_fetched_at
    now = time.monotonic()
    if _thresholds_cache and (now - _thresholds_fetched_at) < _THRESHOLDS_TTL_SECONDS:
        return _thresholds_cache

    try:
        resp = _ssm.get_parameter(Name=SSM_THRESHOLDS_PARAM, WithDecryption=False)
        _thresholds_cache    = json.loads(resp["Parameter"]["Value"])
        _thresholds_fetched_at = now
        logger.info(json.dumps({"message": "thresholds_refreshed", "thresholds": _thresholds_cache}))
    except ClientError as exc:
        logger.warning(json.dumps({
            "message": "ssm_fetch_failed_using_defaults",
            "error": str(exc),
        }))
        _thresholds_cache = {"zScoreThreshold": 3.0, "ewmaAlpha": 0.3, "minDataPoints": 10}

    return _thresholds_cache


# ═══════════════════════════════════════════════════════════════════════════════
# Event parsing
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_metric_info(detail: dict) -> dict:
    """Pull namespace, metric name, dimensions from the EventBridge detail."""
    try:
        metrics_config = detail.get("configuration", {}).get("metrics", [])
        if metrics_config:
            metric_stat = metrics_config[0].get("metricStat", {})
            metric      = metric_stat.get("metric", {})
            return {
                "namespace":   metric.get("namespace", "AWS/EC2"),
                "metricName":  metric.get("name", "CPUUtilization"),
                "dimensions":  metric.get("dimensions", []),
                "period":      metric_stat.get("period", 60),
                "stat":        metric_stat.get("stat", "Average"),
            }
    except (KeyError, IndexError, TypeError):
        pass

    # Fallback: derive from alarm name
    alarm_name = detail.get("alarmName", "")
    return {
        "namespace":  "AWS/EC2",
        "metricName": "CPUUtilization",
        "dimensions": [],
        "period":     60,
        "stat":       "Average",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Metrics — cache + CloudWatch fetch
# ═══════════════════════════════════════════════════════════════════════════════

def _get_metric_values(alarm_name: str, metric_info: dict) -> list[float]:
    """Return the last 60 metric data points. Checks DynamoDB cache first."""
    cache_key = f"{alarm_name}#{metric_info['metricName']}"

    # Check cache
    cached = _check_metrics_cache(cache_key)
    if cached is not None:
        logger.info(json.dumps({"message": "metrics_cache_hit", "cacheKey": cache_key}))
        return cached

    # Cache miss → fetch from CloudWatch
    values = _fetch_cloudwatch_metrics(metric_info)
    if values:
        _write_metrics_cache(cache_key, values)

    return values


def _check_metrics_cache(cache_key: str) -> list[float] | None:
    """Return cached values if record exists and is < 60 seconds old."""
    try:
        table = _dynamo.Table(METRICS_CACHE_TABLE)
        # Use alarm_name as metricName and epoch minute as timestamp
        now_epoch = int(time.time())
        resp = table.get_item(Key={"metricName": cache_key, "timestamp": str(now_epoch // 60)})
        item = resp.get("Item")
        if item and int(item.get("expiresAt", 0)) > now_epoch:
            raw = item.get("values", [])
            return [float(v) for v in raw]
    except ClientError as exc:
        logger.warning(json.dumps({"message": "cache_read_error", "error": str(exc)}))
    return None


def _write_metrics_cache(cache_key: str, values: list[float]) -> None:
    """Write metric values to DynamoDB cache with 24-hour TTL."""
    try:
        table     = _dynamo.Table(METRICS_CACHE_TABLE)
        now_epoch = int(time.time())
        table.put_item(Item={
            "metricName": cache_key,
            "timestamp":  str(now_epoch // 60),
            "values":     [Decimal(str(round(v, 6))) for v in values],
            "cachedAt":   now_epoch,
            "expiresAt":  now_epoch + 86400,   # 24-hour DynamoDB TTL
        })
    except ClientError as exc:
        logger.warning(json.dumps({"message": "cache_write_error", "error": str(exc)}))


def _fetch_cloudwatch_metrics(metric_info: dict) -> list[float]:
    """Call CloudWatch GetMetricData for the last 60 data points."""
    import datetime as dt

    end_time   = datetime.now(timezone.utc)
    period     = metric_info.get("period", 60)
    # Fetch enough history for 60 data points
    start_time = end_time - dt.timedelta(seconds=period * 60)

    dimensions = [
        {"Name": d["name"], "Value": d["value"]}
        for d in metric_info.get("dimensions", [])
    ]

    metric_query: dict[str, Any] = {
        "Id":         "m1",
        "MetricStat": {
            "Metric": {
                "Namespace":  metric_info["namespace"],
                "MetricName": metric_info["metricName"],
                "Dimensions": dimensions,
            },
            "Period": period,
            "Stat":   metric_info.get("stat", "Average"),
        },
        "ReturnData": True,
    }

    try:
        resp   = _cw.get_metric_data(
            MetricDataQueries=[metric_query],
            StartTime=start_time,
            EndTime=end_time,
        )
        result = resp.get("MetricDataResults", [{}])[0]
        values = result.get("Values", [])
        # Values are newest-first — reverse so chronological order
        values.reverse()
        logger.info(json.dumps({
            "message": "cloudwatch_fetch",
            "metricName": metric_info["metricName"],
            "pointsFetched": len(values),
        }))
        return [float(v) for v in values]
    except ClientError as exc:
        logger.error(json.dumps({"message": "cloudwatch_fetch_error", "error": str(exc)}))
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# Core detection algorithm
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_anomaly(
    values: list[float],
    alpha: float = 0.3,
    threshold: float = 3.0,
) -> tuple[bool, float, float]:
    """
    EWMA + residual Z-score anomaly detection.

    Args:
        values:    Time-ordered metric data points (oldest → newest).
        alpha:     EWMA smoothing factor (0 < alpha < 1).
        threshold: Z-score magnitude above which we call an anomaly.

    Returns:
        (is_anomaly, z_score, ewma_value)

    Algorithm:
        1. Compute EWMA over all points.
        2. Build residuals = [actual[i] - ewma[i]] for the BASELINE
           (every point except the latest). This captures how much values
           normally deviate from the trend — without the spike contaminating
           either the centre or the spread.
        3. Z-score = (latest - ewma_before_latest) / std(residuals).
           "ewma_before_latest" (ewma[-2]) is the prediction the EWMA made
           BEFORE seeing the current value — the cleanest anomaly signal.
        4. When the baseline is perfectly flat (residual_std → 0), the epsilon
           makes any real spike produce an astronomically large Z-score.
    """
    if len(values) < 2:
        return False, 0.0, values[0] if values else 0.0

    # 1. EWMA over all values
    ewma = [values[0]]
    for v in values[1:]:
        ewma.append(alpha * v + (1.0 - alpha) * ewma[-1])

    # 2. Residuals on the baseline (all points EXCEPT the latest)
    #    residual[i] = how far actual[i] was from ewma[i] — normal noise
    residuals = [values[i] - ewma[i] for i in range(len(values) - 1)]

    if len(residuals) >= 2:
        residual_std = statistics.stdev(residuals)
    else:
        residual_std = 1.0

    # 3. Z-score: latest value vs the EWMA *before* the latest update
    #    ewma[-2] is the "prediction" the model had before seeing the spike
    latest_val      = values[-1]
    ewma_prediction = ewma[-2]   # EWMA state before the current data point

    z_score = (latest_val - ewma_prediction) / (residual_std + 1e-8)

    is_anomaly = abs(z_score) > threshold

    return is_anomaly, round(z_score, 4), round(ewma[-1], 4)


# ═══════════════════════════════════════════════════════════════════════════════
# Classification
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_type(alarm_name: str) -> str:
    """Map alarm name keywords → incident type string."""
    name_lower = alarm_name.lower()
    if "cpu" in name_lower:
        return "CPU"
    if "memory" in name_lower or "mem" in name_lower:
        return "MEMORY"
    if "disk" in name_lower or "storage" in name_lower:
        return "DISK"
    if "latency" in name_lower or "lag" in name_lower or "duration" in name_lower:
        return "LATENCY"
    return "UNKNOWN"


# ═══════════════════════════════════════════════════════════════════════════════
# DynamoDB — incident writes
# ═══════════════════════════════════════════════════════════════════════════════

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_incident(
    incident_id: str,
    alarm_name: str,
    incident_type: str,
    severity: str,
    values: list[float],
    z_score: float,
    ewma_value: float,
) -> dict:
    """Write a new OPEN incident record to the DynamoDB incidents table."""
    table = _dynamo.Table(INCIDENTS_TABLE)

    # Keep only last 20 data points in the record (space-saving)
    metric_history = [Decimal(str(round(v, 6))) for v in values[-20:]]

    item = {
        "incidentId":    incident_id,
        "status":        "OPEN",
        "type":          incident_type,
        "severity":      severity,
        "alarmName":     alarm_name,
        "metricValue":   Decimal(str(round(values[-1], 6))),
        "zScore":        Decimal(str(z_score)),
        "ewmaValue":     Decimal(str(ewma_value)),
        "metricHistory": metric_history,
        "detectedAt":    _utcnow_iso(),
        "resolvedAt":    None,
        "mttr":          None,
        "method":        None,
        "executionArn":  None,   # filled in after Step Functions start
        "environment":   ENVIRONMENT,
    }

    table.put_item(Item=item)
    logger.info(json.dumps({
        "message": "incident_written",
        "incidentId": incident_id,
        "table": INCIDENTS_TABLE,
    }))
    return item


def _update_incident_execution_arn(incident_id: str, execution_arn: str) -> None:
    """Patch executionArn onto an existing incident record."""
    try:
        table = _dynamo.Table(INCIDENTS_TABLE)
        table.update_item(
            Key={"incidentId": incident_id},
            UpdateExpression="SET executionArn = :arn",
            ExpressionAttributeValues={":arn": execution_arn},
        )
    except ClientError as exc:
        logger.warning(json.dumps({
            "message": "update_execution_arn_failed",
            "incidentId": incident_id,
            "error": str(exc),
        }))


def _write_error_incident(alarm_name: str, exc: Exception) -> None:
    """Write a sentinel ERROR incident so failures are traceable in DynamoDB."""
    table = _dynamo.Table(INCIDENTS_TABLE)
    table.put_item(Item={
        "incidentId":  str(uuid4()),
        "status":      "ERROR",
        "type":        "UNKNOWN",
        "severity":    "WARNING",
        "alarmName":   alarm_name,
        "error":       str(exc),
        "errorType":   type(exc).__name__,
        "detectedAt":  _utcnow_iso(),
        "environment": ENVIRONMENT,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Step Functions
# ═══════════════════════════════════════════════════════════════════════════════

def _start_step_functions(incident_id: str, incident: dict) -> str:
    """Start the Step Functions incident workflow. Returns the execution ARN."""
    # Build a JSON-serialisable copy (Decimal → float for Step Functions input)
    sfn_input = {
        "incidentId":  incident_id,
        "type":        incident["type"],
        "severity":    incident["severity"],
        "alarmName":   incident["alarmName"],
        "metricValue": float(incident["metricValue"]),
        "zScore":      float(incident["zScore"]),
        "ewmaValue":   float(incident["ewmaValue"]),
        "detectedAt":  incident["detectedAt"],
        "environment": ENVIRONMENT,
    }

    resp = _sfn.start_execution(
        stateMachineArn=STEP_FUNCTIONS_ARN,
        name=f"incident-{incident_id}",   # unique per execution
        input=json.dumps(sfn_input),
    )
    return resp["executionArn"]
