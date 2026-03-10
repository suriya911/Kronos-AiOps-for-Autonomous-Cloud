# ═══════════════════════════════════════════════════════════════════════════════
# HTTP API Gateway v2 — REST endpoints for the AIOps frontend  (Phase 5 + 6)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Protocol: HTTP (not WebSocket — that lives in api_gateway.tf)
# Stage:    $default  → URL has no stage prefix, e.g. /incidents not /prod/incidents
# Routes:   $default catch-all → api_handler Lambda dispatches internally
# Auth:     Cognito JWT Authorizer (Phase 6) — all routes require Bearer token
# CORS:     Managed by API GW (Phase 6: specific origins — no more wildcard)
#
# Note on CORS + JWT auth:
#   API GW v2 handles OPTIONS preflight BEFORE the JWT authorizer runs.
#   Preflight requests succeed without a token — no special OPTIONS route needed.
#
# URL format after deploy:
#   https://{api-id}.execute-api.{region}.amazonaws.com
# ═══════════════════════════════════════════════════════════════════════════════

resource "aws_apigatewayv2_api" "http" {
  name          = "${var.project_name}-http-api"
  protocol_type = "HTTP"
  description   = "HTTP REST API for AIOps frontend — incidents, metrics, KPI, settings"

  cors_configuration {
    # Phase 6: Tightened from "*" to specific origins.
    # API Gateway v2 does not support wildcard subdomains (*.vercel.app),
    # so we list each allowed origin explicitly.
    allow_origins  = [
      "http://localhost:8080",
      "http://localhost:8081",
      "https://kronos-aiops.vercel.app",
    ]
    allow_methods  = ["GET", "PATCH", "OPTIONS"]
    allow_headers  = ["Content-Type", "Authorization"]
    expose_headers = []
    max_age        = 86400
  }
}

# ─── Cognito JWT Authorizer ───────────────────────────────────────────────────
#
# Validates the "Authorization: Bearer <id_token>" header against the
# Cognito User Pool JWKS endpoint — no Lambda code changes needed.

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.http.id
  authorizer_type  = "JWT"
  name             = "cognito-jwt"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.spa.id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  }
}

# ─── Lambda integration ────────────────────────────────────────────────────────
# Payload format 2.0 gives the Lambda a simpler event shape:
#   event.rawPath      (not event.path)
#   event.requestContext.http.method  (not event.httpMethod)

resource "aws_apigatewayv2_integration" "api_handler" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api_handler.invoke_arn
  payload_format_version = "2.0"
}

# ─── Single $default route — protected by Cognito JWT ─────────────────────────

resource "aws_apigatewayv2_route" "http_default" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"

  # Phase 6: Require valid Cognito JWT on all routes
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
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
      # Phase 6: Log auth context for debugging
      authorizer      = "$context.authorizer.principalId"
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
