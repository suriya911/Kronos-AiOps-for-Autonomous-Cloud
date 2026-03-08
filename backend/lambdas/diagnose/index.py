"""
AIOps — Diagnose Lambda
Phase 1: Placeholder — logs event and returns stub diagnosis.
Phase 3: Queries CloudWatch Logs Insights for root cause analysis.

Called by: Step Functions (Diagnose state)
"""
import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict, context) -> dict:
    """
    Entry point.

    Input from Step Functions (passed from anomaly_detector):
    {
      "incidentId": "inc_abc123",
      "type": "CPU",
      "alarmName": "aiops-high-cpu-utilization",
      "metricValue": 94.7,
      "zScore": 4.23
    }

    Output (passed to next state):
    {
      "incidentId": "inc_abc123",
      "rootCause": "...",
      "diagnosis": { "topErrors": [...] }
    }
    """
    try:
        incident_id = event.get("incidentId", "unknown")
        incident_type = event.get("type", "unknown")

        logger.info(json.dumps({
            "message": "diagnose invoked — Phase 1 placeholder",
            "incidentId": incident_id,
            "type": incident_type,
            "phase": 1,
        }))

        # ── Phase 3 will add ────────────────────────────────────────────────
        # 1. Start CloudWatch Logs Insights query on relevant log groups
        # 2. Poll until query completes (with timeout)
        # 3. Parse top 5 error patterns from results
        # 4. Update aiops_incidents record with diagnosis
        # ────────────────────────────────────────────────────────────────────

        return {
            "incidentId": incident_id,
            "type": incident_type,
            "rootCause": "PLACEHOLDER — real diagnosis added in Phase 3",
            "diagnosis": {
                "topErrors": [],
                "logInsightsQuery": None,
            },
            "phase": 1,
        }

    except Exception as exc:
        logger.error(json.dumps({
            "message": "diagnose error",
            "error": str(exc),
            "errorType": type(exc).__name__,
        }))
        raise
