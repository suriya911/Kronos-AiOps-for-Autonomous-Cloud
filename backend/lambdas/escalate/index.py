"""
AIOps — Escalate Lambda  (Phase 3)
=====================================
Called by Step Functions (Escalate state) when:
  - GuardrailCheck routes LATENCY / UNKNOWN incidents here, OR
  - Diagnose or AutoRemediate state raises an unhandled exception

Flow:
  1. Build a rich SNS email with incident context + diagnosis + console URL
  2. Publish to the project SNS topic (subscribed email receives it)
  3. Mark incident status = ESCALATED in DynamoDB

Input  (from Step Functions — full merged context):
  { incidentId, type, severity, alarmName, metricValue, zScore,
    detectedAt, diagnosis (optional), error (optional), ... }

Output (stored at $.escalation):
  { incidentId, escalationStatus, snsMessageId }
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

# ─── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ─── AWS clients ──────────────────────────────────────────────────────────────
_sns    = boto3.client("sns")
_dynamo = boto3.resource("dynamodb")

# ─── Environment ──────────────────────────────────────────────────────────────
INCIDENTS_TABLE = os.environ["INCIDENTS_TABLE"]
SNS_TOPIC_ARN   = os.environ["SNS_TOPIC_ARN"]
ENVIRONMENT     = os.environ.get("ENVIRONMENT", "dev")

_SFN_CONSOLE_BASE = (
    "https://console.aws.amazon.com/states/home"
    "#/executions/details"
)


# ═══════════════════════════════════════════════════════════════════════════════
# Handler
# ═══════════════════════════════════════════════════════════════════════════════

def handler(event: dict, context) -> dict:
    incident_id   = event.get("incidentId", "unknown")
    incident_type = event.get("type",       "UNKNOWN")
    severity      = event.get("severity",   "WARNING")
    alarm_name    = event.get("alarmName",  "")
    metric_value  = event.get("metricValue", 0)
    z_score       = event.get("zScore",      0)
    detected_at   = event.get("detectedAt",  "")
    execution_arn = event.get("executionArn", "")

    # Diagnosis from previous state (may be absent if Diagnose itself failed)
    diagnosis  = event.get("diagnosis", {}) or {}
    root_cause = diagnosis.get("rootCause", "Diagnosis step did not complete.")

    # Step Functions error payload (present when Diagnose or Remediate failed)
    error_info = event.get("error", {}) or {}

    logger.info(json.dumps({
        "message":    "escalate invoked",
        "incidentId": incident_id,
        "type":       incident_type,
        "severity":   severity,
        "hasError":   bool(error_info),
    }))

    # ── Build + publish SNS message ────────────────────────────────────────────
    subject = _build_subject(severity, incident_type, alarm_name)
    body    = _build_body(
        incident_id   = incident_id,
        incident_type = incident_type,
        severity      = severity,
        alarm_name    = alarm_name,
        metric_value  = metric_value,
        z_score       = z_score,
        detected_at   = detected_at,
        root_cause    = root_cause,
        execution_arn = execution_arn,
        error_info    = error_info,
    )

    sns_message_id    = _publish(subject, body)
    escalation_status = "SENT" if sns_message_id else "FAILED"

    # ── Update DynamoDB ────────────────────────────────────────────────────────
    _update_incident_escalated(incident_id, sns_message_id, escalation_status)

    result = {
        "incidentId":       incident_id,
        "escalationStatus": escalation_status,
        "snsMessageId":     sns_message_id,
    }

    logger.info(json.dumps({
        "message":          "escalation_complete",
        "incidentId":       incident_id,
        "escalationStatus": escalation_status,
        "snsMessageId":     sns_message_id,
    }))

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Message building
# ═══════════════════════════════════════════════════════════════════════════════

def _build_subject(severity: str, incident_type: str, alarm_name: str) -> str:
    """Build a concise SNS email subject (max 100 chars)."""
    raw = f"[AIOps {severity}] {incident_type} Incident — {alarm_name}"
    return raw[:100]


def _build_body(
    incident_id: str,
    incident_type: str,
    severity: str,
    alarm_name: str,
    metric_value: float,
    z_score: float,
    detected_at: str,
    root_cause: str,
    execution_arn: str,
    error_info: dict,
) -> str:
    """Build the plain-text body of the SNS escalation email."""

    # Step Functions execution console link
    if execution_arn:
        console_url = f"{_SFN_CONSOLE_BASE}/{execution_arn}"
    else:
        console_url = "Not available"

    # Reason for escalation
    if error_info:
        error_name  = error_info.get("Error", error_info.get("errorType", "UnknownError"))
        error_cause = str(error_info.get("Cause", error_info.get("error", "No cause provided")))[:300]
        escalation_reason = (
            f"An automated step failed during incident processing.\n"
            f"  Error Type  : {error_name}\n"
            f"  Error Cause : {error_cause}"
        )
    else:
        escalation_reason = (
            f"Incident type '{incident_type}' is blocked by the auto-remediation "
            f"guardrail (LATENCY / UNKNOWN types require human review)."
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "AIOps Incident Escalation — Human Intervention Required",
        "=" * 60,
        "",
        f"Incident ID   : {incident_id}",
        f"Type          : {incident_type}",
        f"Severity      : {severity}",
        f"Alarm         : {alarm_name}",
        f"Metric Value  : {metric_value}",
        f"Z-Score       : {z_score}",
        f"Detected At   : {detected_at}",
        f"Environment   : {ENVIRONMENT}",
        "",
        "Root Cause Analysis:",
        f"  {root_cause}",
        "",
        "Reason for Escalation:",
        f"  {escalation_reason}",
        "",
        "Step Functions Execution:",
        f"  {console_url}",
        "",
        "Required Actions:",
        "  1. Review the Step Functions execution trace at the URL above.",
        "  2. Check CloudWatch Logs for the affected Lambda functions.",
        "  3. If safe to remediate, perform the fix manually.",
        "  4. Update incident status in DynamoDB (set status=RESOLVED).",
        "  5. Optionally update guardrail settings via the AIOps settings page.",
        "",
        f"Generated : {now}",
        f"Platform  : AIOps Incident Response Platform ({ENVIRONMENT})",
    ]

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# SNS publish
# ═══════════════════════════════════════════════════════════════════════════════

def _publish(subject: str, message: str) -> str | None:
    """Publish to the project SNS topic. Returns message ID or None on failure."""
    try:
        resp = _sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message,
        )
        return resp["MessageId"]
    except ClientError as exc:
        logger.error(json.dumps({
            "message": "sns_publish_failed",
            "error":   str(exc),
        }))
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# DynamoDB update
# ═══════════════════════════════════════════════════════════════════════════════

def _update_incident_escalated(
    incident_id: str,
    sns_message_id: str | None,
    escalation_status: str,
) -> None:
    """Mark the incident as ESCALATED in DynamoDB."""
    try:
        now   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        table = _dynamo.Table(INCIDENTS_TABLE)
        table.update_item(
            Key={"incidentId": incident_id},
            UpdateExpression=(
                "SET #st = :st, #m = :m, escalatedAt = :ea, snsMessageId = :sns"
            ),
            ExpressionAttributeNames={"#st": "status", "#m": "method"},
            ExpressionAttributeValues={
                ":st":  "ESCALATED",
                ":m":   "HUMAN_REQUIRED",
                ":ea":  now,
                ":sns": sns_message_id or "FAILED",
            },
        )
    except ClientError as exc:
        logger.warning(json.dumps({
            "message":    "update_escalated_failed",
            "incidentId": incident_id,
            "error":      str(exc),
        }))
