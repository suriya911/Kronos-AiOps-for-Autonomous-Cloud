"""
AIOps — WebSocket Broadcast Lambda
Phase 1: Placeholder — logs DynamoDB stream records and returns success.
Phase 4: Iterates active connections and pushes JSON updates via API Gateway Management API.

Triggered by: DynamoDB Streams on aiops_incidents table
"""
import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict, context) -> dict:
    """
    Entry point.

    Event shape from DynamoDB Streams:
    {
      "Records": [
        {
          "eventName": "INSERT" | "MODIFY" | "REMOVE",
          "dynamodb": {
            "NewImage": {
              "incidentId": { "S": "inc_abc123" },
              "status": { "S": "RESOLVED" },
              ...
            },
            "OldImage": { ... }
          }
        }
      ]
    }
    """
    try:
        records = event.get("Records", [])

        logger.info(json.dumps({
            "message": "ws_broadcast invoked — Phase 1 placeholder",
            "recordCount": len(records),
            "phase": 1,
        }))

        for record in records:
            event_name = record.get("eventName", "unknown")
            new_image = record.get("dynamodb", {}).get("NewImage", {})
            incident_id = new_image.get("incidentId", {}).get("S", "unknown")

            logger.info(json.dumps({
                "message": "DynamoDB stream record received",
                "eventName": event_name,
                "incidentId": incident_id,
            }))

        # ── Phase 4 will add ────────────────────────────────────────────────
        # 1. Deserialize DynamoDB NewImage from DynamoDB JSON format
        # 2. Determine event type: INCIDENT_CREATED | INCIDENT_UPDATED | INCIDENT_RESOLVED
        # 3. Scan aiops_ws_connections for all active connectionIds
        # 4. For each connectionId, call API Gateway Management API:
        #    apigw.post_to_connection(ConnectionId=id, Data=json_payload)
        # 5. On GoneException (410): delete stale connectionId from table
        # ────────────────────────────────────────────────────────────────────

        return {
            "statusCode": 200,
            "body": json.dumps({
                "processed": len(records),
                "phase": 1,
            }),
        }

    except Exception as exc:
        logger.error(json.dumps({
            "message": "ws_broadcast error",
            "error": str(exc),
            "errorType": type(exc).__name__,
        }))
        raise
