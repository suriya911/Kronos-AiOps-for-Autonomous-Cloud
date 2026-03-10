"""
AIOps — Remediate Lambda  (Phase 3)
=====================================
Called by Step Functions (AutoRemediate state) after GuardrailCheck passes.

Flow:
  1. Re-confirm guardrail (safety net — GuardrailCheck in ASL is the primary gate)
  2. Idempotency check — skip if this incidentId already has a remediation record
  3. Find SSM-managed instances tagged Project=aiops
     → If none found, record SIMULATED (no actual command run — safe for dev)
  4. Execute AWS-RunShellScript via SSM Send Command
  5. Poll SSM until SUCCESS / FAILED / TIMEOUT (max 90 s)
  6. Write audit record to aiops_remediations table
  7. Update incident status in aiops_incidents (RESOLVED or REMEDIATION_FAILED)

Input  (from Step Functions — full merged context including $.diagnosis):
  { incidentId, type, severity, alarmName, diagnosis, ... }

Output (stored at $.remediation):
  { incidentId, remediationId, actionType, remediationStatus, ssmCommandId, durationMs }
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

# ─── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ─── AWS clients ──────────────────────────────────────────────────────────────
_ssm    = boto3.client("ssm")
_dynamo = boto3.resource("dynamodb")

# ─── Environment ──────────────────────────────────────────────────────────────
INCIDENTS_TABLE      = os.environ["INCIDENTS_TABLE"]
REMEDIATIONS_TABLE   = os.environ["REMEDIATIONS_TABLE"]
SSM_GUARDRAILS_PARAM = os.environ["SSM_GUARDRAILS_PARAM"]
ENVIRONMENT          = os.environ.get("ENVIRONMENT", "dev")

# ─── Remediation action catalogue ─────────────────────────────────────────────
# Maps incident type → (actionType, shell commands)
_REMEDIATIONS: dict[str, tuple[str, list[str]]] = {
    "CPU": (
        "RESTART_SERVICE",
        [
            # Restart the SSM agent itself as a safe, always-present service
            "systemctl restart amazon-ssm-agent 2>/dev/null || service amazon-ssm-agent restart 2>/dev/null || true",
            "echo 'CPU remediation: service restart attempted'",
            "uptime",
        ],
    ),
    "MEMORY": (
        "CLEAR_MEMORY_CACHE",
        [
            "sync",
            "echo 3 | tee /proc/sys/vm/drop_caches 2>/dev/null || true",
            "free -m",
            "echo 'Memory remediation: page cache drop attempted'",
        ],
    ),
    "DISK": (
        "CLEAR_TMP_FILES",
        [
            "find /tmp -type f -mtime +1 -delete 2>/dev/null || true",
            "df -h /tmp",
            "echo 'Disk remediation: /tmp cleanup attempted'",
        ],
    ),
}

_SSM_POLL_TIMEOUT  = 90   # seconds to wait for SSM command
_GUARDRAIL_ALLOWED = {"CPU", "MEMORY", "DISK"}


# ═══════════════════════════════════════════════════════════════════════════════
# Handler
# ═══════════════════════════════════════════════════════════════════════════════

def handler(event: dict, context) -> dict:
    incident_id   = event.get("incidentId", "unknown")
    incident_type = event.get("type", "UNKNOWN")
    start_ms      = int(time.time() * 1000)

    logger.info(json.dumps({
        "message":    "remediate invoked",
        "incidentId": incident_id,
        "type":       incident_type,
    }))

    # ── 1. Guardrail safety net ────────────────────────────────────────────────
    guardrails    = _get_guardrails()
    allowed_types = set(guardrails.get("allowedTypes", list(_GUARDRAIL_ALLOWED)))

    if incident_type not in allowed_types:
        logger.warning(json.dumps({
            "message":      "guardrail_blocked",
            "incidentId":   incident_id,
            "type":         incident_type,
            "allowedTypes": list(allowed_types),
        }))
        raise ValueError(
            f"Guardrail: type '{incident_type}' not in allowedTypes {sorted(allowed_types)}"
        )

    # ── 2. Idempotency check ────────────────────────────────────────────────────
    if _already_remediated(incident_id):
        logger.info(json.dumps({
            "message":    "remediation_skipped_idempotent",
            "incidentId": incident_id,
        }))
        return {
            "incidentId":        incident_id,
            "remediationId":     "IDEMPOTENT",
            "actionType":        "SKIPPED",
            "remediationStatus": "SKIPPED",
            "ssmCommandId":      None,
            "durationMs":        0,
        }

    # ── 3. Execute remediation ─────────────────────────────────────────────────
    if incident_type not in _REMEDIATIONS:
        raise ValueError(f"No remediation defined for type '{incident_type}'")

    action_type, commands = _REMEDIATIONS[incident_type]
    remediation_id        = str(uuid4())

    ssm_command_id, ssm_status = _execute_remediation(incident_id, incident_type, commands)
    duration_ms                = int(time.time() * 1000) - start_ms

    # ── 4. Write audit record ──────────────────────────────────────────────────
    _write_remediation_record(
        remediation_id = remediation_id,
        incident_id    = incident_id,
        incident_type  = incident_type,
        action_type    = action_type,
        ssm_command_id = ssm_command_id,
        ssm_status     = ssm_status,
        duration_ms    = duration_ms,
    )

    # ── 5. Update incident ─────────────────────────────────────────────────────
    final_status = "RESOLVED" if ssm_status in ("SUCCESS", "SIMULATED") else "REMEDIATION_FAILED"
    _update_incident(incident_id, remediation_id, final_status, duration_ms)

    result = {
        "incidentId":        incident_id,
        "remediationId":     remediation_id,
        "actionType":        action_type,
        "remediationStatus": ssm_status,
        "ssmCommandId":      ssm_command_id,
        "durationMs":        duration_ms,
    }

    logger.info(json.dumps({
        "message":         "remediation_complete",
        "incidentId":      incident_id,
        "remediationId":   remediation_id,
        "status":          ssm_status,
        "finalStatus":     final_status,
        "durationMs":      duration_ms,
    }))

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SSM guardrails
# ═══════════════════════════════════════════════════════════════════════════════

def _get_guardrails() -> dict:
    """Read guardrail config from SSM Parameter Store."""
    try:
        resp = _ssm.get_parameter(Name=SSM_GUARDRAILS_PARAM, WithDecryption=False)
        return json.loads(resp["Parameter"]["Value"])
    except ClientError as exc:
        logger.warning(json.dumps({"message": "guardrails_fetch_failed", "error": str(exc)}))
        return {"allowedTypes": list(_GUARDRAIL_ALLOWED)}


# ═══════════════════════════════════════════════════════════════════════════════
# Idempotency
# ═══════════════════════════════════════════════════════════════════════════════

def _already_remediated(incident_id: str) -> bool:
    """
    Return True if a remediation record already exists for this incident.
    Queries the incidentId-index GSI on the remediations table.
    """
    try:
        table = _dynamo.Table(REMEDIATIONS_TABLE)
        resp  = table.query(
            IndexName="incidentId-index",
            KeyConditionExpression="incidentId = :iid",
            ExpressionAttributeValues={":iid": incident_id},
            Limit=1,
        )
        return len(resp.get("Items", [])) > 0
    except ClientError as exc:
        logger.warning(json.dumps({"message": "idempotency_check_failed", "error": str(exc)}))
        return False   # fail-open: attempt remediation if check errors


# ═══════════════════════════════════════════════════════════════════════════════
# SSM Run Command
# ═══════════════════════════════════════════════════════════════════════════════

def _execute_remediation(
    incident_id: str,
    incident_type: str,
    commands: list[str],
) -> tuple[str, str]:
    """
    Send an SSM Run Command to all Project=aiops managed instances.

    Returns (commandId, status).

    In dev environments with no managed instances, records SIMULATED
    without actually running any commands — safe and auditable.
    """
    try:
        # Discover SSM-managed instances with Project=aiops tag
        resp         = _ssm.describe_instance_information(
            Filters=[{"Key": "tag:Project", "Values": ["aiops"]}],
            MaxResults=5,
        )
        instance_ids = [i["InstanceId"] for i in resp.get("InstanceInformationList", [])]

    except ClientError as exc:
        logger.warning(json.dumps({"message": "ssm_describe_failed", "error": str(exc)}))
        instance_ids = []

    if not instance_ids:
        logger.info(json.dumps({
            "message":    "no_managed_instances_simulating",
            "incidentId": incident_id,
            "type":       incident_type,
            "note":       "No SSM-managed instances with tag Project=aiops. Logging SIMULATED remediation.",
        }))
        return f"SIMULATED-{str(uuid4())[:8]}", "SIMULATED"

    # Send command to all found instances
    try:
        send_resp  = _ssm.send_command(
            InstanceIds=instance_ids,
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": commands},
            Comment=f"AIOps auto-remediation — incident {incident_id} type {incident_type}",
            TimeoutSeconds=60,
        )
        command_id = send_resp["Command"]["CommandId"]
        logger.info(json.dumps({
            "message":     "ssm_command_sent",
            "commandId":   command_id,
            "instanceIds": instance_ids,
        }))
    except ClientError as exc:
        logger.error(json.dumps({"message": "ssm_send_command_failed", "error": str(exc)}))
        return f"FAILED-{str(uuid4())[:8]}", "FAILED"

    # Poll first instance for completion status
    status = _poll_ssm_command(command_id, instance_ids[0])
    return command_id, status


def _poll_ssm_command(command_id: str, instance_id: str) -> str:
    """Poll SSM command status until terminal state or timeout."""
    deadline = time.monotonic() + _SSM_POLL_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(3)
        try:
            resp   = _ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
            detail = resp.get("StatusDetails", "InProgress")
            if detail in ("Success", "Failed", "Cancelled", "TimedOut", "DeliveryTimedOut"):
                return detail.upper()
        except ClientError:
            break
    return "TIMEOUT"


# ═══════════════════════════════════════════════════════════════════════════════
# DynamoDB writes
# ═══════════════════════════════════════════════════════════════════════════════

def _write_remediation_record(
    remediation_id: str,
    incident_id: str,
    incident_type: str,
    action_type: str,
    ssm_command_id: str,
    ssm_status: str,
    duration_ms: int,
) -> None:
    """Write a full audit record to the aiops_remediations table."""
    table = _dynamo.Table(REMEDIATIONS_TABLE)
    table.put_item(Item={
        "remediationId": remediation_id,
        "incidentId":    incident_id,
        "type":          incident_type,
        "actionType":    action_type,
        "ssmCommandId":  ssm_command_id,
        "status":        ssm_status,
        "durationMs":    Decimal(str(duration_ms)),
        "createdAt":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment":   ENVIRONMENT,
    })


def _update_incident(
    incident_id: str,
    remediation_id: str,
    final_status: str,
    duration_ms: int,
) -> None:
    """Update incident record with resolution outcome."""
    try:
        now   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        table = _dynamo.Table(INCIDENTS_TABLE)
        table.update_item(
            Key={"incidentId": incident_id},
            UpdateExpression=(
                "SET #st = :st, remediationId = :rid, "
                "#m = :m, resolvedAt = :ra, mttr = :mt"
            ),
            ExpressionAttributeNames={"#st": "status", "#m": "method"},
            ExpressionAttributeValues={
                ":st":  final_status,
                ":rid": remediation_id,
                ":m":   "AUTO_REMEDIATED",
                ":ra":  now,
                ":mt":  Decimal(str(duration_ms)),
            },
        )
    except ClientError as exc:
        logger.warning(json.dumps({
            "message":    "update_incident_failed",
            "incidentId": incident_id,
            "error":      str(exc),
        }))
