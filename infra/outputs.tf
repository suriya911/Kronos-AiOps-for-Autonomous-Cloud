# ─── DynamoDB ─────────────────────────────────────────────────────────────────
output "dynamodb_incidents_table_name" {
  description = "Name of the incidents DynamoDB table"
  value       = aws_dynamodb_table.incidents.name
}

output "dynamodb_incidents_stream_arn" {
  description = "DynamoDB Stream ARN — used to wire ws_broadcast Lambda in Phase 4"
  value       = aws_dynamodb_table.incidents.stream_arn
}

# ─── SNS ──────────────────────────────────────────────────────────────────────
output "sns_topic_arn" {
  description = "SNS topic ARN for incident escalation alerts"
  value       = aws_sns_topic.alerts.arn
}

# ─── Step Functions ───────────────────────────────────────────────────────────
output "step_functions_arn" {
  description = "Step Functions state machine ARN — set as STEP_FUNCTIONS_ARN env var"
  value       = aws_sfn_state_machine.incident_workflow.arn
}

# ─── WebSocket API ────────────────────────────────────────────────────────────
output "websocket_url" {
  description = "WebSocket endpoint — set as NEXT_PUBLIC_WS_URL in Vercel"
  value       = aws_apigatewayv2_stage.websocket.invoke_url
}

output "websocket_api_id" {
  description = "API Gateway WebSocket API ID"
  value       = aws_apigatewayv2_api.websocket.id
}

output "websocket_management_endpoint" {
  description = "API Gateway management endpoint for ws_broadcast Lambda"
  value       = "https://${aws_apigatewayv2_api.websocket.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_apigatewayv2_stage.websocket.name}"
}

# ─── Lambda ───────────────────────────────────────────────────────────────────
output "anomaly_detector_arn" {
  description = "Anomaly detector Lambda ARN"
  value       = aws_lambda_function.anomaly_detector.arn
}

# ─── IAM ──────────────────────────────────────────────────────────────────────
output "lambda_execution_role_arn" {
  description = "IAM role ARN shared by all Lambda functions"
  value       = aws_iam_role.lambda_execution.arn
}

# ─── SSM ──────────────────────────────────────────────────────────────────────
output "ssm_guardrails_param" {
  description = "SSM Parameter Store path for guardrail config"
  value       = aws_ssm_parameter.guardrails.name
}

output "ssm_thresholds_param" {
  description = "SSM Parameter Store path for anomaly detection thresholds"
  value       = aws_ssm_parameter.thresholds.name
}

# ─── EventBridge ──────────────────────────────────────────────────────────────
output "eventbridge_rule_arn" {
  description = "EventBridge rule ARN that routes CloudWatch alarms to anomaly detector"
  value       = aws_cloudwatch_event_rule.cloudwatch_alarm_state_change.arn
}

# ─── HTTP API (Phase 5) ───────────────────────────────────────────────────────
output "http_api_url" {
  description = "HTTP API base URL — set as VITE_API_BASE_URL in frontend/.env.local"
  value       = aws_apigatewayv2_stage.http.invoke_url
}

# ─── Account Info ─────────────────────────────────────────────────────────────
output "aws_account_id" {
  description = "AWS Account ID (useful for constructing ARNs)"
  value       = data.aws_caller_identity.current.account_id
}

# ─── CloudWatch Dashboard ─────────────────────────────────────────────────────
output "cloudwatch_dashboard_url" {
  description = "Direct link to the Kronos ops dashboard in CloudWatch console"
  value       = "https://console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${var.project_name}-ops"
}
