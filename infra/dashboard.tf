# ═══════════════════════════════════════════════════════════════════════════════
# CloudWatch Operations Dashboard — Kronos AIOps  (Phase 6)
# ═══════════════════════════════════════════════════════════════════════════════
#
# 8 widgets across 4 rows:
#   Row 1: Lambda Errors (all 6 fns) | Lambda Duration p99 (all 6 fns)
#   Row 2: HTTP API 5xx count        | HTTP API IntegrationLatency p99
#   Row 3: DynamoDB Throttles        | Step Functions executions
#   Row 4: WebSocket connections     | Operational links
#
# Open at:
#   terraform output cloudwatch_dashboard_url
# ═══════════════════════════════════════════════════════════════════════════════

locals {
  # All Lambda function names for the dashboard widgets
  lambda_names = [
    "${var.project_name}-anomaly-detector",
    "${var.project_name}-diagnose",
    "${var.project_name}-remediate",
    "${var.project_name}-escalate",
    "${var.project_name}-ws-connect",
    "${var.project_name}-ws-broadcast",
    "${var.project_name}-api-handler",
  ]

  region = var.aws_region

  # Helper: generate a metric entry for a Lambda function
  # Used inside the widget metric arrays
  lambda_error_metrics = [
    for fn in local.lambda_names : ["AWS/Lambda", "Errors", "FunctionName", fn, { "stat" : "Sum", "label" : fn }]
  ]

  lambda_duration_metrics = [
    for fn in local.lambda_names : ["AWS/Lambda", "Duration", "FunctionName", fn, { "stat" : "p99", "label" : fn }]
  ]
}

resource "aws_cloudwatch_dashboard" "ops" {
  dashboard_name = "${var.project_name}-ops"

  dashboard_body = jsonencode({
    widgets = [

      # ── Row 1: Lambda Errors ─────────────────────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Errors (Sum / 5m)"
          region = local.region
          view   = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Sum"
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", "${var.project_name}-anomaly-detector"],
            ["AWS/Lambda", "Errors", "FunctionName", "${var.project_name}-diagnose"],
            ["AWS/Lambda", "Errors", "FunctionName", "${var.project_name}-remediate"],
            ["AWS/Lambda", "Errors", "FunctionName", "${var.project_name}-escalate"],
            ["AWS/Lambda", "Errors", "FunctionName", "${var.project_name}-ws-connect"],
            ["AWS/Lambda", "Errors", "FunctionName", "${var.project_name}-ws-broadcast"],
            ["AWS/Lambda", "Errors", "FunctionName", "${var.project_name}-api-handler"],
          ]
        }
      },

      # ── Row 1: Lambda Duration p99 ───────────────────────────────────────────
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Duration p99 (ms / 5m)"
          region = local.region
          view   = "timeSeries"
          stacked = false
          period  = 300
          stat    = "p99"
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", "${var.project_name}-anomaly-detector"],
            ["AWS/Lambda", "Duration", "FunctionName", "${var.project_name}-diagnose"],
            ["AWS/Lambda", "Duration", "FunctionName", "${var.project_name}-remediate"],
            ["AWS/Lambda", "Duration", "FunctionName", "${var.project_name}-escalate"],
            ["AWS/Lambda", "Duration", "FunctionName", "${var.project_name}-api-handler"],
          ]
        }
      },

      # ── Row 2: HTTP API 5xx ───────────────────────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "HTTP API 5xx Errors (Count / 5m)"
          region = local.region
          view   = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Sum"
          metrics = [
            ["AWS/ApiGateway", "5XXError", "ApiId", aws_apigatewayv2_api.http.id, "Stage", "$default"]
          ]
        }
      },

      # ── Row 2: HTTP API Latency p99 ───────────────────────────────────────────
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "HTTP API Integration Latency p99 (ms / 5m)"
          region = local.region
          view   = "timeSeries"
          stacked = false
          period  = 300
          stat    = "p99"
          metrics = [
            ["AWS/ApiGateway", "IntegrationLatency", "ApiId", aws_apigatewayv2_api.http.id, "Stage", "$default"]
          ]
        }
      },

      # ── Row 3: DynamoDB Throttles ─────────────────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "DynamoDB Throttled Requests (Incidents Table)"
          region = local.region
          view   = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Sum"
          metrics = [
            ["AWS/DynamoDB", "ReadThrottleEvents",  "TableName", aws_dynamodb_table.incidents.name],
            ["AWS/DynamoDB", "WriteThrottleEvents", "TableName", aws_dynamodb_table.incidents.name],
          ]
        }
      },

      # ── Row 3: Step Functions ─────────────────────────────────────────────────
      {
        type   = "metric"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "Step Functions — Executions Started vs Failed"
          region = local.region
          view   = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Sum"
          metrics = [
            ["AWS/States", "ExecutionsStarted", "StateMachineArn", aws_sfn_state_machine.incident_workflow.arn],
            ["AWS/States", "ExecutionsFailed",  "StateMachineArn", aws_sfn_state_machine.incident_workflow.arn],
            ["AWS/States", "ExecutionsSucceeded","StateMachineArn", aws_sfn_state_machine.incident_workflow.arn],
          ]
        }
      },

      # ── Row 4: WebSocket Connections ──────────────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 18
        width  = 12
        height = 6
        properties = {
          title  = "WebSocket Active Connections"
          region = local.region
          view   = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Average"
          metrics = [
            ["AWS/ApiGateway", "ConnectCount",    "ApiId", aws_apigatewayv2_api.websocket.id, "Stage", "prod"],
            ["AWS/ApiGateway", "MessageCount",    "ApiId", aws_apigatewayv2_api.websocket.id, "Stage", "prod"],
            ["AWS/ApiGateway", "DisconnectCount", "ApiId", aws_apigatewayv2_api.websocket.id, "Stage", "prod"],
          ]
        }
      },

      # ── Row 4: Operational text widget ────────────────────────────────────────
      {
        type   = "text"
        x      = 12
        y      = 18
        width  = 12
        height = 6
        properties = {
          markdown = <<-MD
            ## Kronos AIOps — Quick Links

            **API**
            - HTTP API: `${aws_apigatewayv2_stage.http.invoke_url}`
            - WebSocket: `${aws_apigatewayv2_stage.websocket.invoke_url}`

            **Log Groups**
            - [anomaly-detector](/cloudwatch/home#logsV2:log-groups/log-group/$252Faws$252Flambda$252F${var.project_name}-anomaly-detector)
            - [api-handler](/cloudwatch/home#logsV2:log-groups/log-group/$252Faws$252Flambda$252F${var.project_name}-api-handler)
            - [HTTP API Access](/cloudwatch/home#logsV2:log-groups/log-group/$252Faws$252Fapigateway$252F${var.project_name}-http-api)

            **Resources**
            - DynamoDB: `${aws_dynamodb_table.incidents.name}`
            - Cognito Pool: `${aws_cognito_user_pool.main.id}`
          MD
        }
      },

    ]
  })
}
