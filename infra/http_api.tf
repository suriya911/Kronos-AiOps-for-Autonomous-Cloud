# ═══════════════════════════════════════════════════════════════════════════════
# HTTP API Gateway v2 — REST endpoints for the AIOps frontend  (Phase 5)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Protocol: HTTP (not WebSocket — that lives in api_gateway.tf)
# Stage:    $default  → URL has no stage prefix, e.g. /incidents not /prod/incidents
# Routes:   $default catch-all → api_handler Lambda dispatches internally
# Auth:     NONE — open API (no Cognito)
# CORS:     Managed by API GW — all origins allowed for simplicity
#
# URL format after deploy:
#   https://{api-id}.execute-api.{region}.amazonaws.com
# ═══════════════════════════════════════════════════════════════════════════════

resource "aws_apigatewayv2_api" "http" {
  name          = "${var.project_name}-http-api"
  protocol_type = "HTTP"
  description   = "HTTP REST API for AIOps frontend — incidents, metrics, KPI, settings"

  cors_configuration {
    allow_origins  = ["*"]
    allow_methods  = ["GET", "PATCH", "POST", "OPTIONS"]
    allow_headers  = ["Content-Type", "Authorization"]
    expose_headers = []
    max_age        = 86400
  }
}

# ─── Lambda integration ────────────────────────────────────────────────────────

resource "aws_apigatewayv2_integration" "api_handler" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api_handler.invoke_arn
  payload_format_version = "2.0"
}

# ─── Single $default route — no auth ──────────────────────────────────────────

resource "aws_apigatewayv2_route" "http_default" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"

  authorization_type = "NONE"
}

# ─── Stage ($default = no stage prefix in URL) ────────────────────────────────

resource "aws_apigatewayv2_stage" "http" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.http_api_access.arn
    format = jsonencode({
      requestId       = "$context.requestId"
      ip              = "$context.identity.sourceIp"
      httpMethod      = "$context.httpMethod"
      routeKey        = "$context.routeKey"
      status          = "$context.status"
      responseLength  = "$context.responseLength"
      responseLatency = "$context.responseLatency"
    })
  }

  default_route_settings {
    throttling_rate_limit  = 100
    throttling_burst_limit = 200
  }
}

# ─── CloudWatch log group for API access logs ─────────────────────────────────

resource "aws_cloudwatch_log_group" "http_api_access" {
  name              = "/aws/apigateway/${var.project_name}-http-api"
  retention_in_days = var.log_retention_days
}

# ─── Lambda invoke permission ─────────────────────────────────────────────────

resource "aws_lambda_permission" "apigateway_http" {
  statement_id  = "AllowHTTPAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
