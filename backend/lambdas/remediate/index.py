"""
AIOps — Remediate Lambda
Phase 1: Placeholder — logs event and returns stub result.
Phase 3: Executes SSM Run Command with idempotency check.

Called by: Step Functions (AutoRemediate state)
"""
import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict, context) -> dict:
    """
    Entry point.

    Input from Step Functions:
    {
      "incidentId": "inc_abc123",
      "type": "CPU",
      "rootCause": "...",
      "resourceId": "i-0abc123"
    }

    Output:
    {
      "incidentId": "inc_abc123",
      "remediationId": "rem_xyz789",
      "actionType": "RESTART_SERVICE",
      "remediationStatus": "SUCCESS",
      "ssmCommandId": "cmd-0abc123",
      "durationMs": 3240
    }
    """
    try:
        incident_id = event.get("incidentId", "unknown")
        incident_type = event.get("type", "unknown")

        logger.info(json.dumps({
            "message": "remediate invoked — Phase 1 placeholder",
            "incidentId": incident_id,
            "type": incident_type,
            "phase": 1,
        }))

        # ── Phase 3 will add ────────────────────────────────────────────────
        # 1. Check SSM guardrails parameter — is this type allowed?
        # 2. IDEMPOTENCY: check current service state before acting
        #    (e.g., is the service already running? disk already cleared?)
        # 3. Execute appropriate SSM Run Command based on incident type:
        #    CPU/MEMORY → restart service
        #    DISK       → clear /tmp files
        #    LATENCY    → escalate (blocked by guardrail)
        # 4. Poll SSM command status until SUCCESS or FAILED
        # 5. Write remediation record to aiops_remediations table
        # 6. Update incident record with remediationId and status
        # ────────────────────────────────────────────────────────────────────

        return {
            "incidentId": incident_id,
            "remediationId": "PLACEHOLDER",
            "actionType": "NONE",
            "remediationStatus": "PLACEHOLDER",
            "ssmCommandId": None,
            "durationMs": 0,
            "phase": 1,
        }

    except Exception as exc:
        logger.error(json.dumps({
            "message": "remediate error",
            "error": str(exc),
            "errorType": type(exc).__name__,
        }))
        raise
