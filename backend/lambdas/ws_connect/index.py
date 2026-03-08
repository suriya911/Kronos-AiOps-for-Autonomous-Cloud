"""
AIOps — WebSocket Connect/Disconnect Handler
Phase 1: Placeholder — accepts all connections and returns 200.
Phase 4: Stores/removes connectionId in aiops_ws_connections DynamoDB table.

Handles: API Gateway WebSocket routes $connect and $disconnect
"""
import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict, context) -> dict:
    """
    Entry point.

    Event shape from API Gateway WebSocket:
    {
      "requestContext": {
        "routeKey": "$connect" | "$disconnect",
        "connectionId": "abc123==",
        "connectedAt": 1705312345000,
        "identity": { "sourceIp": "1.2.3.4" }
      }
    }

    Must return HTTP 200 within 29 seconds or API Gateway drops the connection.
    """
    try:
        request_context = event.get("requestContext", {})
        route_key = request_context.get("routeKey", "unknown")
        connection_id = request_context.get("connectionId", "unknown")

        logger.info(json.dumps({
            "message": "ws_connect invoked — Phase 1 placeholder",
            "routeKey": route_key,
            "connectionId": connection_id,
            "phase": 1,
        }))

        # ── Phase 4 will add ────────────────────────────────────────────────
        # $connect:    PutItem to aiops_ws_connections
        #              { connectionId, connectedAt, expiresAt (now + 7200) }
        # $disconnect: DeleteItem from aiops_ws_connections
        # ────────────────────────────────────────────────────────────────────

        return {
            "statusCode": 200,
            "body": json.dumps({"status": "OK", "routeKey": route_key}),
        }

    except Exception as exc:
        logger.error(json.dumps({
            "message": "ws_connect error",
            "error": str(exc),
            "errorType": type(exc).__name__,
        }))
        # Must return 500 — API Gateway will reject the connection
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal Server Error"}),
        }
