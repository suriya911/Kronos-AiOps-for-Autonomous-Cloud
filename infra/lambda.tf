# ═══════════════════════════════════════════════════════════════════════════════
# Lambda — Archive data sources (Terraform auto-zips the Python source files)
# Output path: ../.archives/  (gitignored, recreated on each terraform plan)
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# Lambda Layer — scipy + numpy for EWMA anomaly detection
# Built by Docker BEFORE terraform apply (see Phase 2 instructions)
# Command: docker run --rm -v "$(pwd)/backend/layers/anomaly":/out \
#            public.ecr.aws/lambda/python:3.11 pip install scipy numpy -t /out/python
# ═══════════════════════════════════════════════════════════════════════════════

resource "aws_lambda_layer_version" "anomaly" {
  layer_name          = "${var.project_name}-anomaly-detection"
  description         = "scipy + numpy for EWMA + Z-score anomaly detection (Phase 2)"

  # Layer zip is 61 MB — too large for Lambda direct-upload limit (50 MB).
  # Upload to S3 first (see Phase 2 instructions), then reference via S3.
  # Command: aws s3 cp .archives/anomaly_layer.zip s3://aiops-terraform-state-{ACCOUNT}/layers/anomaly_layer.zip
  s3_bucket           = "aiops-terraform-state-${data.aws_caller_identity.current.account_id}"
  s3_key              = "layers/anomaly_layer.zip"

  compatible_runtimes = ["python3.11"]
}

data "archive_file" "anomaly_detector" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/lambdas/anomaly_detector"
  output_path = "${path.module}/../.archives/anomaly_detector.zip"
}

data "archive_file" "diagnose" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/lambdas/diagnose"
  output_path = "${path.module}/../.archives/diagnose.zip"
}

data "archive_file" "remediate" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/lambdas/remediate"
  output_path = "${path.module}/../.archives/remediate.zip"
}

data "archive_file" "escalate" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/lambdas/escalate"
  output_path = "${path.module}/../.archives/escalate.zip"
}

data "archive_file" "ws_connect" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/lambdas/ws_connect"
  output_path = "${path.module}/../.archives/ws_connect.zip"
}

data "archive_file" "ws_broadcast" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/lambdas/ws_broadcast"
  output_path = "${path.module}/../.archives/ws_broadcast.zip"
}

# ═══════════════════════════════════════════════════════════════════════════════
# CloudWatch Log Groups (pre-created so retention is controlled by Terraform)
# ═══════════════════════════════════════════════════════════════════════════════

resource "aws_cloudwatch_log_group" "lambda_anomaly_detector" {
  name              = "/aws/lambda/${var.project_name}-anomaly-detector"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "lambda_diagnose" {
  name              = "/aws/lambda/${var.project_name}-diagnose"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "lambda_remediate" {
  name              = "/aws/lambda/${var.project_name}-remediate"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "lambda_escalate" {
  name              = "/aws/lambda/${var.project_name}-escalate"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "lambda_ws_connect" {
  name              = "/aws/lambda/${var.project_name}-ws-connect"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "lambda_ws_broadcast" {
  name              = "/aws/lambda/${var.project_name}-ws-broadcast"
  retention_in_days = var.log_retention_days
}

# ═══════════════════════════════════════════════════════════════════════════════
# SQS Dead-Letter Queue — captures payloads from failed async Lambda invocations
# ═══════════════════════════════════════════════════════════════════════════════

resource "aws_sqs_queue" "lambda_dlq" {
  name                      = "${var.project_name}-lambda-dlq"
  message_retention_seconds = 86400 # 1 day — then auto-deleted
}

# ═══════════════════════════════════════════════════════════════════════════════
# Lambda Functions
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 1. anomaly_detector ──────────────────────────────────────────────────────
# Triggered by EventBridge on CloudWatch Alarm state change.
# Phase 2: adds EWMA + Z-score detection logic, DynamoDB write, SFN trigger.
resource "aws_lambda_function" "anomaly_detector" {
  function_name    = "${var.project_name}-anomaly-detector"
  description      = "Receives CloudWatch alarms via EventBridge, runs EWMA+Z-score anomaly detection, writes incident to DynamoDB, starts Step Functions workflow"
  filename         = data.archive_file.anomaly_detector.output_path
  source_code_hash = data.archive_file.anomaly_detector.output_base64sha256
  handler          = "index.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_execution.arn
  timeout          = var.lambda_timeout
  memory_size      = var.anomaly_lambda_memory_mb # 512 MB for scipy layer

  # scipy + numpy layer (built via Docker before terraform apply)
  layers = [aws_lambda_layer_version.anomaly.arn]

  # reserved_concurrent_executions omitted — free-tier accounts require
  # at least 10 unreserved executions to remain. Re-add in production.

  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }

  environment {
    variables = {
      INCIDENTS_TABLE     = aws_dynamodb_table.incidents.name
      METRICS_CACHE_TABLE = aws_dynamodb_table.metrics_cache.name
      # ARN constructed manually to avoid circular dep with stepfunctions.tf
      STEP_FUNCTIONS_ARN  = "arn:aws:states:${var.aws_region}:${data.aws_caller_identity.current.account_id}:stateMachine:${var.project_name}-incident-workflow"
      SSM_THRESHOLDS_PARAM = aws_ssm_parameter.thresholds.name
      AWS_ACCOUNT_ID_VAR  = data.aws_caller_identity.current.account_id
      LOG_LEVEL           = "INFO"
      ENVIRONMENT         = var.environment
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_anomaly_detector,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.lambda_permissions,
  ]
}

# ─── 2. diagnose ──────────────────────────────────────────────────────────────
# Called by Step Functions Triage state.
# Phase 3: queries CloudWatch Logs Insights for root cause analysis.
resource "aws_lambda_function" "diagnose" {
  function_name    = "${var.project_name}-diagnose"
  description      = "Queries CloudWatch Logs Insights to determine incident root cause. Called by Step Functions."
  filename         = data.archive_file.diagnose.output_path
  source_code_hash = data.archive_file.diagnose.output_base64sha256
  handler          = "index.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_execution.arn
  timeout          = 60 # Logs Insights queries can take up to 30s
  memory_size      = var.lambda_memory_mb

  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }

  environment {
    variables = {
      INCIDENTS_TABLE = aws_dynamodb_table.incidents.name
      LOG_LEVEL       = "INFO"
      ENVIRONMENT     = var.environment
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_diagnose,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.lambda_permissions,
  ]
}

# ─── 3. remediate ─────────────────────────────────────────────────────────────
# Called by Step Functions AutoRemediate state.
# Phase 3: executes SSM Run Command with idempotency check.
resource "aws_lambda_function" "remediate" {
  function_name    = "${var.project_name}-remediate"
  description      = "Executes auto-remediation actions via SSM Run Command with idempotency checks. Called by Step Functions."
  filename         = data.archive_file.remediate.output_path
  source_code_hash = data.archive_file.remediate.output_base64sha256
  handler          = "index.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_execution.arn
  timeout          = 120 # SSM commands may take up to 2 minutes
  memory_size      = var.lambda_memory_mb

  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }

  environment {
    variables = {
      INCIDENTS_TABLE      = aws_dynamodb_table.incidents.name
      REMEDIATIONS_TABLE   = aws_dynamodb_table.remediations.name
      SSM_GUARDRAILS_PARAM = aws_ssm_parameter.guardrails.name
      LOG_LEVEL            = "INFO"
      ENVIRONMENT          = var.environment
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_remediate,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.lambda_permissions,
  ]
}

# ─── 4. escalate ──────────────────────────────────────────────────────────────
# Called by Step Functions Escalate state.
# Phase 3: publishes to SNS when guardrail blocks auto-remediation.
resource "aws_lambda_function" "escalate" {
  function_name    = "${var.project_name}-escalate"
  description      = "Publishes incident escalation notifications via SNS. Called by Step Functions when guardrail blocks auto-remediation."
  filename         = data.archive_file.escalate.output_path
  source_code_hash = data.archive_file.escalate.output_base64sha256
  handler          = "index.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_execution.arn
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_mb

  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }

  environment {
    variables = {
      INCIDENTS_TABLE = aws_dynamodb_table.incidents.name
      SNS_TOPIC_ARN   = aws_sns_topic.alerts.arn
      LOG_LEVEL       = "INFO"
      ENVIRONMENT     = var.environment
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_escalate,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.lambda_permissions,
  ]
}

# ─── 5. ws_connect ────────────────────────────────────────────────────────────
# Handles WebSocket $connect and $disconnect routes.
# Phase 4: stores/removes connectionId in DynamoDB.
resource "aws_lambda_function" "ws_connect" {
  function_name    = "${var.project_name}-ws-connect"
  description      = "Handles WebSocket $connect/$disconnect — manages active connection IDs in DynamoDB"
  filename         = data.archive_file.ws_connect.output_path
  source_code_hash = data.archive_file.ws_connect.output_base64sha256
  handler          = "index.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_execution.arn
  timeout          = 10 # Connection events must respond fast (API GW 29s limit)
  memory_size      = var.lambda_memory_mb

  environment {
    variables = {
      WS_CONNECTIONS_TABLE = aws_dynamodb_table.ws_connections.name
      LOG_LEVEL            = "INFO"
      ENVIRONMENT          = var.environment
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_ws_connect,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.lambda_permissions,
  ]
}

# ─── 6. ws_broadcast ──────────────────────────────────────────────────────────
# Triggered by DynamoDB Streams on the incidents table.
# Phase 4: pushes incident updates to all active WebSocket connections.
resource "aws_lambda_function" "ws_broadcast" {
  function_name    = "${var.project_name}-ws-broadcast"
  description      = "Triggered by DynamoDB Streams on incidents table — broadcasts updates to all connected WebSocket clients"
  filename         = data.archive_file.ws_broadcast.output_path
  source_code_hash = data.archive_file.ws_broadcast.output_base64sha256
  handler          = "index.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_execution.arn
  timeout          = 30
  memory_size      = var.lambda_memory_mb

  environment {
    variables = {
      WS_CONNECTIONS_TABLE    = aws_dynamodb_table.ws_connections.name
      WEBSOCKET_API_ENDPOINT  = "https://${aws_apigatewayv2_api.websocket.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_apigatewayv2_stage.websocket.name}"
      LOG_LEVEL               = "INFO"
      ENVIRONMENT             = var.environment
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_ws_broadcast,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.lambda_permissions,
    aws_apigatewayv2_stage.websocket,
  ]
}

# ─── API Gateway permissions to invoke Lambda ─────────────────────────────────
resource "aws_lambda_permission" "apigateway_ws_connect" {
  statement_id  = "AllowAPIGatewayConnect"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ws_connect.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigateway_ws_broadcast" {
  statement_id  = "AllowAPIGatewayBroadcast"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ws_broadcast.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket.execution_arn}/*/*"
}

# ─── 7. api_handler ───────────────────────────────────────────────────────────
# HTTP REST API for the frontend — incidents, KPI, metrics, settings.
# Deployed in Phase 5; sits behind aws_apigatewayv2_api.http (http_api.tf).

data "archive_file" "api_handler" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/lambdas/api_handler"
  output_path = "${path.module}/../.archives/api_handler.zip"
}

resource "aws_cloudwatch_log_group" "lambda_api_handler" {
  name              = "/aws/lambda/${var.project_name}-api-handler"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api_handler" {
  function_name    = "${var.project_name}-api-handler"
  description      = "HTTP API for AIOps frontend — incidents, KPI, metrics, remediations, settings"
  filename         = data.archive_file.api_handler.output_path
  source_code_hash = data.archive_file.api_handler.output_base64sha256
  handler          = "index.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_execution.arn   # existing role has all needed perms
  timeout          = 30
  memory_size      = var.lambda_memory_mb

  environment {
    variables = {
      INCIDENTS_TABLE      = aws_dynamodb_table.incidents.name
      REMEDIATIONS_TABLE   = aws_dynamodb_table.remediations.name
      METRICS_CACHE_TABLE  = aws_dynamodb_table.metrics_cache.name
      SSM_GUARDRAILS_PARAM = aws_ssm_parameter.guardrails.name
      SSM_THRESHOLDS_PARAM = aws_ssm_parameter.thresholds.name
      ANOMALY_DETECTOR_ARN = aws_lambda_function.anomaly_detector.arn
      ENVIRONMENT          = var.environment
      LOG_LEVEL            = "INFO"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_api_handler,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.lambda_permissions,
  ]
}

# ─── 8. incident_generator ────────────────────────────────────────────────────
# EventBridge scheduled trigger (rate 3 days).
# Writes 2–4 synthetic incidents to DynamoDB to keep the dashboard populated.

data "archive_file" "incident_generator" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/lambdas/incident_generator"
  output_path = "${path.module}/../.archives/incident_generator.zip"
}

resource "aws_cloudwatch_log_group" "lambda_incident_generator" {
  name              = "/aws/lambda/${var.project_name}-incident-generator"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "incident_generator" {
  function_name    = "${var.project_name}-incident-generator"
  description      = "Generates realistic synthetic incidents every 3 days to keep the AIOps dashboard populated for demos"
  filename         = data.archive_file.incident_generator.output_path
  source_code_hash = data.archive_file.incident_generator.output_base64sha256
  handler          = "index.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_execution.arn
  timeout          = 30
  memory_size      = var.lambda_memory_mb

  environment {
    variables = {
      INCIDENTS_TABLE    = aws_dynamodb_table.incidents.name
      REMEDIATIONS_TABLE = aws_dynamodb_table.remediations.name
      ENVIRONMENT        = var.environment
      LOG_LEVEL          = "INFO"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_incident_generator,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.lambda_permissions,
  ]
}

# EventBridge rule — fires every 3 days
resource "aws_cloudwatch_event_rule" "incident_generator" {
  name                = "${var.project_name}-incident-generator"
  description         = "Triggers incident_generator Lambda every 3 days"
  schedule_expression = "rate(3 days)"
}

resource "aws_cloudwatch_event_target" "incident_generator" {
  rule      = aws_cloudwatch_event_rule.incident_generator.name
  target_id = "incident-generator-lambda"
  arn       = aws_lambda_function.incident_generator.arn
}

resource "aws_lambda_permission" "incident_generator_eventbridge" {
  statement_id  = "AllowEventBridgeIncidentGenerator"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.incident_generator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.incident_generator.arn
}

# ─── DynamoDB Stream → ws_broadcast (Phase 4 trigger) ────────────────────────
# Wires the DynamoDB incidents stream to the ws_broadcast Lambda.
# In Phase 4, this is what drives real-time WebSocket pushes.
resource "aws_lambda_event_source_mapping" "incidents_stream" {
  event_source_arn  = aws_dynamodb_table.incidents.stream_arn
  function_name     = aws_lambda_function.ws_broadcast.arn
  starting_position = "LATEST"
  batch_size        = 1 # Process each incident update immediately

  depends_on = [
    aws_iam_role_policy_attachment.lambda_permissions,
  ]
}
