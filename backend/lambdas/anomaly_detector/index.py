"""
AIOps — Anomaly Detector Lambda
Phase 1: Placeholder — logs event and returns success.
Phase 2: EWMA + Z-score anomaly detection with scipy, DynamoDB write, Step Functions trigger.

Triggered by: EventBridge (CloudWatch Alarm state change → ALARM)
"""
import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict, context) -> dict:
    """
    Entry point.

    EventBridge event shape (CloudWatch Alarm state change):
    {
      "source": "aws.cloudwatch",
      "detail-type": "CloudWatch Alarm State Change",
      "detail": {
        "alarmName": "aiops-high-cpu-utilization",
        "state": { "value": "ALARM" },
        "previousState": { "value": "OK" },
        "configuration": { "metrics": [...] }
      }
    }
    """
    try:
        alarm_name = event.get("detail", {}).get("alarmName", "unknown")
        new_state = event.get("detail", {}).get("state", {}).get("value", "unknown")

        logger.info(json.dumps({
            "message": "anomaly_detector invoked — Phase 1 placeholder",
            "alarmName": alarm_name,
            "newState": new_state,
            "phase": 1,
        }))

        # ── Phase 2 will add ────────────────────────────────────────────────
        # 1. Pull last 60 metric data points via cloudwatch.get_metric_data()
        # 2. Check metrics cache in DynamoDB (avoid throttling)
        # 3. Run EWMA (alpha=0.3) + Z-score (threshold=3.0) classification
        # 4. Write incident record to aiops_incidents DynamoDB table
        # 5. Start Step Functions execution with incident context
        # ────────────────────────────────────────────────────────────────────

        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "PLACEHOLDER",
                "phase": 1,
                "alarmName": alarm_name,
            }),
        }

    except Exception as exc:
        logger.error(json.dumps({
            "message": "anomaly_detector error",
            "error": str(exc),
            "errorType": type(exc).__name__,
        }))
        raise
