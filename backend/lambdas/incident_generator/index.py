"""
AIOps Incident Generator Lambda
Triggered daily by EventBridge. Generates 3-6 realistic incidents per run.
On first run (empty table), seeds 14 days of historical data.

Rules:
  - CRITICAL severity -> always OPEN or ESCALATED (requires human action)
  - WARNING severity  -> 80% auto-RESOLVED, 20% stays OPEN
"""
from __future__ import annotations
import json, logging, os, random, uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
_dynamo = boto3.resource("dynamodb")

INCIDENTS_TABLE    = os.environ["INCIDENTS_TABLE"]
REMEDIATIONS_TABLE = os.environ["REMEDIATIONS_TABLE"]

TEMPLATES = [
    {
        "type": "CPU", "alarmName": "aiops-high-cpu-utilization",
        "rootCause": "Runaway process consuming 100% CPU. Memory leak in the application worker pool causing infinite retry loops.",
        "topErrors": [
            "FATAL: Worker process exceeded CPU quota (100%) for 5 consecutive minutes",
            "ERROR: Request queue depth exceeded 10,000 — shedding load",
            "WARN:  GC overhead limit exceeded — heap at 98%",
        ],
        "actionType": "RESTART_SERVICE", "target": "aws:ec2:us-east-1/i-0abc123def456789",
        "metricRange": (75.0, 99.5), "ewmaRange": (60.0, 80.0), "zScoreRange": (3.2, 5.8),
        "baselineSeverity": "mixed",
    },
    {
        "type": "MEMORY", "alarmName": "aiops-high-memory-utilization",
        "rootCause": "Memory leak in Node.js service. Heap snapshots show retained DOM event listeners accumulating over time without garbage collection.",
        "topErrors": [
            "ERROR: JavaScript heap out of memory — allocation failed",
            "WARN:  Resident set size (RSS) exceeded 4 GB threshold",
            "ERROR: ENOMEM — cannot allocate memory for new buffer",
        ],
        "actionType": "CLEAR_CACHE", "target": "aws:ec2:us-east-1/i-0def456abc123789",
        "metricRange": (88.0, 97.0), "ewmaRange": (70.0, 85.0), "zScoreRange": (3.5, 6.2),
        "baselineSeverity": "mixed",
    },
    {
        "type": "DISK", "alarmName": "aiops-high-disk-utilization",
        "rootCause": "Application log rotation misconfigured. /var/log partition filled by uncompressed debug logs due to upstream service timeouts.",
        "topErrors": [
            "ERROR: No space left on device — write failed on /var/log/app",
            "CRITICAL: Disk usage at 95% on /dev/xvda1 (partition: root)",
            "WARN:  Log rotation failed — logrotate: error opening /var/log/app.log",
        ],
        "actionType": "ROTATE_LOGS", "target": "aws:ec2:us-east-1/i-0789abc123def456",
        "metricRange": (90.0, 98.0), "ewmaRange": (75.0, 88.0), "zScoreRange": (4.0, 7.1),
        "baselineSeverity": "critical",
    },
    {
        "type": "LATENCY", "alarmName": "aiops-high-api-latency",
        "rootCause": "Database connection pool exhaustion. All 100 connections held by long-running analytical queries blocking transactional traffic. N+1 query pattern in ORM layer.",
        "topErrors": [
            "ERROR: Connection pool timeout after 30s — pool size: 100/100 active",
            "WARN:  Query execution time exceeded 10s for 47 requests in the last minute",
            "ERROR: deadlock detected — process 12345 waits for ShareLock on transaction",
        ],
        "actionType": "SCALE_OUT", "target": "aws:rds:us-east-1/aiops-prod-db",
        "metricRange": (250.0, 850.0), "ewmaRange": (180.0, 400.0), "zScoreRange": (3.8, 6.5),
        "baselineSeverity": "mixed",
    },
    {
        "type": "CPU", "alarmName": "aiops-batch-cpu-spike",
        "rootCause": "Scheduled batch ETL job triggered at peak traffic hours. Processing 2M records simultaneously causing CPU saturation across all worker nodes.",
        "topErrors": [
            "WARN:  CPU steal time elevated (28%) — noisy neighbour on hypervisor",
            "ERROR: Batch job timeout after 3600s — partial results committed",
            "INFO:  Auto-scaling triggered — 3 new instances launching",
        ],
        "actionType": "SCALE_OUT", "target": "aws:autoscaling:us-east-1/aiops-asg-workers",
        "metricRange": (82.0, 96.0), "ewmaRange": (65.0, 78.0), "zScoreRange": (3.3, 5.1),
        "baselineSeverity": "warning",
    },
    {
        "type": "MEMORY", "alarmName": "aiops-oom-killer-triggered",
        "rootCause": "Linux OOM Killer invoked. Kernel terminated app process to reclaim memory. Unbounded in-memory cache with no eviction policy.",
        "topErrors": [
            "CRITICAL: OOM killer invoked — process app-worker (PID 4821) killed",
            "ERROR: Out of memory: Kill process 4821 — score 892",
            "WARN:  swap usage exceeded 80% — system under heavy memory pressure",
        ],
        "actionType": "RESTART_SERVICE", "target": "aws:ec2:us-east-1/i-0aabbcc112233445",
        "metricRange": (92.0, 99.9), "ewmaRange": (78.0, 92.0), "zScoreRange": (4.5, 8.0),
        "baselineSeverity": "critical",
    },
    {
        "type": "LATENCY", "alarmName": "aiops-cold-start-latency",
        "rootCause": "Lambda cold start cascade. Burst of concurrent invocations after 30-min idle period. Container initialisation taking 8-12s per cold start.",
        "topErrors": [
            "WARN:  Lambda cold start detected — init duration 9,241ms",
            "ERROR: API timeout (10s) exceeded — downstream Lambda cold start",
            "INFO:  Provisioned concurrency not configured for this function",
        ],
        "actionType": "SCALE_OUT", "target": "aws:lambda:us-east-1/aiops-api-handler",
        "metricRange": (2500.0, 12000.0), "ewmaRange": (1200.0, 4000.0), "zScoreRange": (3.1, 5.5),
        "baselineSeverity": "warning",
    },
]


def _utcnow():
    return datetime.now(timezone.utc)

def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def _float_range(lo, hi):
    return round(random.uniform(lo, hi), 2)

def _metric_history(peak, length=20):
    baseline = peak * 0.35
    history = []
    for i in range(length):
        frac = i / (length - 1)
        noise = random.uniform(-3.0, 3.0)
        val = round(baseline + (peak - baseline) * (frac ** 1.5) + noise, 2)
        history.append(max(0.0, val))
    return history


def _generate_incident(template, base_time, force_status=None):
    incident_id    = str(uuid.uuid4())
    remediation_id = str(uuid.uuid4())

    detected_at   = base_time
    diagnosed_at  = detected_at  + timedelta(seconds=random.randint(8, 30))
    remediated_at = diagnosed_at + timedelta(seconds=random.randint(20, 120))
    resolved_at   = remediated_at + timedelta(seconds=random.randint(5, 45))

    metric_val = _float_range(*template["metricRange"])
    ewma_val   = _float_range(*template["ewmaRange"])
    z_score    = _float_range(*template["zScoreRange"])

    baseline = template.get("baselineSeverity", "mixed")
    if baseline == "critical":
        severity = "CRITICAL"
    elif baseline == "warning":
        severity = "WARNING"
    else:
        severity = "CRITICAL" if z_score >= 4.5 else "WARNING"

    if force_status:
        status = force_status
    elif severity == "CRITICAL":
        status = "OPEN" if random.random() < 0.5 else "ESCALATED"
    else:
        status = "RESOLVED" if random.random() < 0.80 else "OPEN"

    if status == "RESOLVED":
        method      = "AUTO_REMEDIATED"
        mttr_ms     = int((resolved_at - detected_at).total_seconds() * 1000)
        resolved_ts = _iso(resolved_at)
    elif status == "ESCALATED":
        method      = "HUMAN_REQUIRED"
        mttr_ms     = None
        resolved_ts = None
    else:
        method      = None
        mttr_ms     = None
        resolved_ts = None

    timeline = [
        {"ts": _iso(detected_at),  "event": severity + " alarm triggered: " + template["alarmName"], "actor": "CloudWatch"},
        {"ts": _iso(diagnosed_at), "event": "Root cause identified by KRONOS anomaly detector", "actor": "KRONOS AI"},
    ]
    if status in ("RESOLVED", "ESCALATED"):
        timeline.append({"ts": _iso(remediated_at), "event": "Remediation executed: " + template["actionType"], "actor": "KRONOS AI"})
    if status == "RESOLVED":
        timeline.append({"ts": _iso(resolved_at), "event": "Incident resolved automatically — system nominal", "actor": "KRONOS AI"})
    elif status == "ESCALATED":
        timeline.append({"ts": _iso(remediated_at + timedelta(seconds=30)), "event": "Escalated to on-call engineer — manual intervention required", "actor": "PagerDuty"})

    incident = {
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
        "executionArn":  "arn:aws:states:us-east-1:807430513014:execution:aiops-incident-workflow:" + incident_id[:8],
        "timeline":      timeline,
        "diagnosis":     {
            "topErrors":        template["topErrors"],
            "logInsightsQuery": "fields @message | filter @message like /ERROR/ | limit 20",
        },
        "resourceId":    template["target"],
    }
    if mttr_ms:
        incident["mttr"] = Decimal(str(mttr_ms))

    remediation = None
    if status == "RESOLVED":
        duration_ms = int((resolved_at - diagnosed_at).total_seconds() * 1000)
        remediation = {
            "remediationId": remediation_id,
            "incidentId":    incident_id,
            "actionType":    template["actionType"],
            "target":        template["target"],
            "ssmCommandId":  "cmd-" + uuid.uuid4().hex[:16],
            "status":        "SUCCESS",
            "durationMs":    Decimal(str(duration_ms)),
            "createdAt":     _iso(diagnosed_at),
        }

    return incident, remediation


def _count_existing(table):
    resp = table.scan(Select="COUNT", Limit=10)
    return resp.get("Count", 0)


def _seed_history(incidents_table, remediations_table, days=14):
    now = _utcnow()
    written = 0
    for day_offset in range(days, 0, -1):
        day_base = now - timedelta(days=day_offset)
        n = random.randint(2, 5)
        templates = random.choices(TEMPLATES, k=n)
        for tmpl in templates:
            hour_offset = random.uniform(0, 22)
            base_time = day_base.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=hour_offset)
            roll = random.random()
            if roll < 0.75:
                force = "RESOLVED"
            elif roll < 0.88:
                force = "ESCALATED"
            else:
                force = "OPEN"
            incident, remediation = _generate_incident(tmpl, base_time, force_status=force)
            incidents_table.put_item(Item=incident)
            if remediation:
                remediations_table.put_item(Item=remediation)
            written += 1
    logger.info(json.dumps({"message": "history_seeded", "written": written, "days": days}))
    return written


def handler(event, context):
    logger.info(json.dumps({"message": "incident_generator_triggered"}))

    incidents_table    = _dynamo.Table(INCIDENTS_TABLE)
    remediations_table = _dynamo.Table(REMEDIATIONS_TABLE)

    existing = _count_existing(incidents_table)
    seeded = 0
    if existing < 5:
        logger.info(json.dumps({"message": "seeding_14_day_history", "existing": existing}))
        seeded = _seed_history(incidents_table, remediations_table, days=14)

    now      = _utcnow()
    n        = random.randint(3, 6)
    selected = random.choices(TEMPLATES, k=n)

    written = 0
    for tmpl in selected:
        minutes_ago = random.randint(5, 360)
        base_time   = now - timedelta(minutes=minutes_ago)
        incident, remediation = _generate_incident(tmpl, base_time)
        incidents_table.put_item(Item=incident)
        if remediation:
            remediations_table.put_item(Item=remediation)
        logger.info(json.dumps({"incidentId": incident["incidentId"], "status": incident["status"], "severity": incident["severity"]}))
        written += 1

    return {"statusCode": 200, "body": json.dumps({"generated": written, "seeded": seeded})}
