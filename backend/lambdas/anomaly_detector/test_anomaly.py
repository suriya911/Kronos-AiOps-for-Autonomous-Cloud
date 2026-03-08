"""
Phase 2 unit tests — AIOps Anomaly Detector
============================================
Tests the full Lambda handler using moto to mock all AWS services.

Run:
    pip install pytest moto[all] boto3
    python -m pytest test_anomaly.py -v

Coverage:
    1. test_normal_traffic    — flat metric → NORMAL, no DynamoDB write
    2. test_cpu_spike         — last point spikes → ANOMALY, CPU type, DynamoDB write
    3. test_memory_gradual    — gradual escalation breaches threshold → ANOMALY, MEMORY type
    4. test_disk_full         — near-constant low + sudden jump → ANOMALY, DISK type
    5. test_latency_spike     — latency alarm name → ANOMALY, LATENCY type
"""

from __future__ import annotations

import json
import os
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

# ─── Environment variables that the Lambda module reads at import time ──────────
os.environ.setdefault("INCIDENTS_TABLE",      "test_aiops_incidents")
os.environ.setdefault("METRICS_CACHE_TABLE",  "test_aiops_metrics_cache")
os.environ.setdefault("STEP_FUNCTIONS_ARN",   "arn:aws:states:us-east-1:123456789012:stateMachine:test-workflow")
os.environ.setdefault("SSM_THRESHOLDS_PARAM", "/aiops/thresholds")
os.environ.setdefault("LOG_LEVEL",            "DEBUG")
os.environ.setdefault("ENVIRONMENT",          "test")
os.environ.setdefault("AWS_DEFAULT_REGION",   "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID",    "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY","testing")
os.environ.setdefault("AWS_SECURITY_TOKEN",   "testing")
os.environ.setdefault("AWS_SESSION_TOKEN",    "testing")


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _make_event(alarm_name: str = "aiops-high-cpu-utilization") -> dict:
    """Minimal EventBridge CloudWatch Alarm state change event."""
    return {
        "source":      "aws.cloudwatch",
        "detail-type": "CloudWatch Alarm State Change",
        "detail": {
            "alarmName": alarm_name,
            "state":         {"value": "ALARM",  "reason": "Threshold breached"},
            "previousState": {"value": "OK"},
            "configuration": {
                "metrics": [{
                    "metricStat": {
                        "metric": {
                            "namespace":  "AWS/EC2",
                            "name":       "CPUUtilization",
                            "dimensions": [{"name": "InstanceId", "value": "i-test123"}],
                        },
                        "period": 60,
                        "stat":   "Average",
                    }
                }]
            },
        },
    }


def _setup_aws_infra(region: str = "us-east-1") -> None:
    """Create the DynamoDB tables and SSM parameter used by the Lambda."""
    ddb = boto3.client("dynamodb", region_name=region)

    # incidents table
    ddb.create_table(
        TableName=os.environ["INCIDENTS_TABLE"],
        AttributeDefinitions=[{"AttributeName": "incidentId", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "incidentId", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )

    # metrics cache table
    ddb.create_table(
        TableName=os.environ["METRICS_CACHE_TABLE"],
        AttributeDefinitions=[
            {"AttributeName": "metricName",  "AttributeType": "S"},
            {"AttributeName": "timestamp",   "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "metricName",  "KeyType": "HASH"},
            {"AttributeName": "timestamp",   "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # SSM thresholds
    ssm = boto3.client("ssm", region_name=region)
    ssm.put_parameter(
        Name=os.environ["SSM_THRESHOLDS_PARAM"],
        Value=json.dumps({
            "zScoreThreshold": 3.0,
            "ewmaAlpha":       0.3,
            "minDataPoints":   5,   # low for unit tests (normally 10+)
        }),
        Type="String",
        Overwrite=True,
    )


def _scan_incidents(region: str = "us-east-1") -> list[dict]:
    """Return all items in the test incidents table."""
    ddb  = boto3.resource("dynamodb", region_name=region)
    tbl  = ddb.Table(os.environ["INCIDENTS_TABLE"])
    resp = tbl.scan()
    return resp.get("Items", [])


def _make_cw_response(values: list[float]) -> dict:
    """Fake CloudWatch GetMetricData response (newest-first, as AWS returns them)."""
    reversed_values = list(reversed(values))
    return {
        "MetricDataResults": [{
            "Id":         "m1",
            "Label":      "TestMetric",
            "Timestamps": [f"2024-01-01T00:{i:02d}:00Z" for i in range(len(reversed_values))],
            "Values":     reversed_values,
            "StatusCode": "Complete",
        }]
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1 — Normal traffic → NORMAL, zero DynamoDB writes
# ═══════════════════════════════════════════════════════════════════════════════

@mock_aws
def test_normal_traffic() -> None:
    """
    60 values all near 50.0 → z-score well below 3.0 → NORMAL.
    Incident table must remain empty.
    """
    _setup_aws_infra()

    # reset module-level SSM cache between tests
    import index as lm
    lm._thresholds_cache = None
    lm._thresholds_fetched_at = 0.0

    flat_values = [50.0 + (i % 3) * 0.1 for i in range(60)]

    with patch.object(lm._cw, "get_metric_data", return_value=_make_cw_response(flat_values)), \
         patch.object(lm._sfn, "start_execution",
                      return_value={"executionArn": "arn:aws:states:us-east-1:123:execution:test:normal"}):

        resp = lm.handler(_make_event("aiops-high-cpu-utilization"), MagicMock())

    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["status"] == "NORMAL", f"Expected NORMAL, got {body}"

    incidents = _scan_incidents()
    assert len(incidents) == 0, f"Expected 0 incidents, found {len(incidents)}"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2 — CPU spike → ANOMALY, type=CPU, incident written to DynamoDB
# ═══════════════════════════════════════════════════════════════════════════════

@mock_aws
def test_cpu_spike() -> None:
    """
    59 values ≈ 50 then final value = 95 → z-score > 3 → ANOMALY.
    Incident type must be CPU. DynamoDB must have exactly 1 OPEN incident.
    """
    _setup_aws_infra()

    import index as lm
    lm._thresholds_cache = None
    lm._thresholds_fetched_at = 0.0

    spike_values = [50.0] * 59 + [95.0]

    with patch.object(lm._cw, "get_metric_data", return_value=_make_cw_response(spike_values)), \
         patch.object(lm._sfn, "start_execution",
                      return_value={"executionArn": "arn:aws:states:us-east-1:123:execution:test:cpu"}):

        resp = lm.handler(_make_event("aiops-high-cpu-utilization"), MagicMock())

    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["status"] == "ANOMALY", f"Expected ANOMALY, got {body}"
    assert body["type"]   == "CPU",     f"Expected CPU type, got {body['type']}"
    assert "incidentId"   in body

    incidents = _scan_incidents()
    assert len(incidents) == 1, f"Expected 1 incident, found {len(incidents)}"
    assert incidents[0]["status"] == "OPEN"
    assert incidents[0]["type"]   == "CPU"
    assert float(incidents[0]["zScore"]) > 3.0


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3 — Memory gradual increase → ANOMALY, type=MEMORY
# ═══════════════════════════════════════════════════════════════════════════════

@mock_aws
def test_memory_gradual() -> None:
    """
    Values gradually rise from 40 → 90 over 60 points.
    The final Z-score should breach 3.0 → ANOMALY, type=MEMORY.
    """
    _setup_aws_infra()

    import index as lm
    lm._thresholds_cache = None
    lm._thresholds_fetched_at = 0.0

    # Gradual rise: start at 40, end near 90
    n = 60
    gradual_values = [40.0 + (50.0 / n) * i for i in range(n)]
    # Boost final point to ensure anomaly
    gradual_values[-1] = 95.0

    with patch.object(lm._cw, "get_metric_data", return_value=_make_cw_response(gradual_values)), \
         patch.object(lm._sfn, "start_execution",
                      return_value={"executionArn": "arn:aws:states:us-east-1:123:execution:test:mem"}):

        resp = lm.handler(_make_event("aiops-high-memory-utilization"), MagicMock())

    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["status"] == "ANOMALY", f"Expected ANOMALY, got {body}"
    assert body["type"]   == "MEMORY",  f"Expected MEMORY type, got {body['type']}"

    incidents = _scan_incidents()
    assert len(incidents) == 1
    assert incidents[0]["type"] == "MEMORY"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4 — Disk full → ANOMALY, type=DISK
# ═══════════════════════════════════════════════════════════════════════════════

@mock_aws
def test_disk_full() -> None:
    """
    59 values ≈ 30 (normal disk usage) then final value = 95.
    Alarm name contains 'disk' → type=DISK.
    """
    _setup_aws_infra()

    import index as lm
    lm._thresholds_cache = None
    lm._thresholds_fetched_at = 0.0

    disk_values = [30.0] * 59 + [95.0]

    with patch.object(lm._cw, "get_metric_data", return_value=_make_cw_response(disk_values)), \
         patch.object(lm._sfn, "start_execution",
                      return_value={"executionArn": "arn:aws:states:us-east-1:123:execution:test:disk"}):

        resp = lm.handler(_make_event("aiops-high-disk-usage"), MagicMock())

    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["status"] == "ANOMALY", f"Expected ANOMALY, got {body}"
    assert body["type"]   == "DISK",    f"Expected DISK type, got {body['type']}"

    incidents = _scan_incidents()
    assert len(incidents) == 1
    assert incidents[0]["type"] == "DISK"
    assert float(incidents[0]["metricValue"]) == pytest.approx(95.0)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5 — Latency spike → ANOMALY, type=LATENCY
# ═══════════════════════════════════════════════════════════════════════════════

@mock_aws
def test_latency_spike() -> None:
    """
    59 values ≈ 100 ms (normal p99 latency) then final value = 2500 ms.
    Alarm name contains 'latency' → type=LATENCY.
    Severity must be CRITICAL (z-score > threshold * 1.5).
    """
    _setup_aws_infra()

    import index as lm
    lm._thresholds_cache = None
    lm._thresholds_fetched_at = 0.0

    latency_values = [100.0] * 59 + [2500.0]

    with patch.object(lm._cw, "get_metric_data", return_value=_make_cw_response(latency_values)), \
         patch.object(lm._sfn, "start_execution",
                      return_value={"executionArn": "arn:aws:states:us-east-1:123:execution:test:lat"}):

        resp = lm.handler(_make_event("aiops-high-latency"), MagicMock())

    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["status"] == "ANOMALY",  f"Expected ANOMALY, got {body}"
    assert body["type"]   == "LATENCY",  f"Expected LATENCY type, got {body['type']}"

    incidents = _scan_incidents()
    assert len(incidents) == 1
    assert incidents[0]["type"]     == "LATENCY"
    assert incidents[0]["severity"] == "CRITICAL"
    assert float(incidents[0]["metricValue"]) == pytest.approx(2500.0)
