# ═══════════════════════════════════════════════════════════════════════════════
# IAM — Lambda Execution Role (shared by all 6 Lambda functions)
# ═══════════════════════════════════════════════════════════════════════════════

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "lambda_execution" {
  name               = "${var.project_name}-lambda-execution-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  description        = "Shared execution role for all AIOps Lambda functions"
}

# AWS managed policy: CloudWatch Logs write access (included for free)
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ─── Custom permissions policy ────────────────────────────────────────────────
# Uses ARN patterns (not direct resource references) to avoid circular deps
# between lambda.tf, api_gateway.tf, and stepfunctions.tf
data "aws_iam_policy_document" "lambda_permissions" {

  # CloudWatch Metrics — anomaly_detector reads 60 data points per alarm
  statement {
    sid    = "CloudWatchMetrics"
    effect = "Allow"
    actions = [
      "cloudwatch:GetMetricData",
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:ListMetrics",
    ]
    resources = ["*"]
  }

  # CloudWatch Logs Insights — diagnose Lambda runs root-cause queries
  statement {
    sid    = "CloudWatchLogsInsights"
    effect = "Allow"
    actions = [
      "logs:StartQuery",
      "logs:GetQueryResults",
      "logs:StopQuery",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = ["*"]
  }

  # DynamoDB — all 4 project tables
  statement {
    sid    = "DynamoDBTableAccess"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Scan",
      "dynamodb:Query",
    ]
    resources = [
      aws_dynamodb_table.incidents.arn,
      "${aws_dynamodb_table.incidents.arn}/index/*",
      aws_dynamodb_table.metrics_cache.arn,
      aws_dynamodb_table.remediations.arn,
      "${aws_dynamodb_table.remediations.arn}/index/*",
      aws_dynamodb_table.ws_connections.arn,
    ]
  }

  # DynamoDB Streams — ws_broadcast reads from the incidents stream
  statement {
    sid    = "DynamoDBStreams"
    effect = "Allow"
    actions = [
      "dynamodb:GetRecords",
      "dynamodb:GetShardIterator",
      "dynamodb:DescribeStream",
      "dynamodb:ListStreams",
    ]
    resources = [
      "${aws_dynamodb_table.incidents.arn}/stream/*",
    ]
  }

  # Step Functions — anomaly_detector starts state machine execution
  # Using ARN pattern to avoid circular dependency with stepfunctions.tf
  statement {
    sid     = "StepFunctionsStart"
    effect  = "Allow"
    actions = ["states:StartExecution"]
    resources = [
      "arn:aws:states:${var.aws_region}:${data.aws_caller_identity.current.account_id}:stateMachine:${var.project_name}-*",
    ]
  }

  # SNS — escalate Lambda publishes incident alerts
  statement {
    sid     = "SNSPublish"
    effect  = "Allow"
    actions = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }

  # SSM — remediate Lambda runs commands; settings API reads/writes parameters
  statement {
    sid    = "SSMAccess"
    effect = "Allow"
    actions = [
      "ssm:SendCommand",
      "ssm:GetCommandInvocation",
      "ssm:ListCommands",
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:PutParameter",
    ]
    resources = ["*"]
  }

  # API Gateway WebSocket Management — ws_broadcast pushes to connections
  # Using wildcard to avoid circular dependency with api_gateway.tf
  statement {
    sid     = "APIGatewayWebSocketManagement"
    effect  = "Allow"
    actions = ["execute-api:ManageConnections"]
    resources = [
      "arn:aws:execute-api:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*",
    ]
  }

  # SQS Dead-Letter Queue — Lambda sends failed async payloads here
  statement {
    sid     = "SQSDLQWrite"
    effect  = "Allow"
    actions = ["sqs:SendMessage"]
    resources = [
      "arn:aws:sqs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${var.project_name}-lambda-dlq",
    ]
  }

  # Lambda invoke — api_handler triggers anomaly_detector for live demo
  statement {
    sid     = "InvokeAnomalyDetector"
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-anomaly-detector",
    ]
  }
}

resource "aws_iam_policy" "lambda_permissions" {
  name        = "${var.project_name}-lambda-permissions"
  description = "All project-specific permissions for AIOps Lambda functions"
  policy      = data.aws_iam_policy_document.lambda_permissions.json
}

resource "aws_iam_role_policy_attachment" "lambda_permissions" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = aws_iam_policy.lambda_permissions.arn
}

# ═══════════════════════════════════════════════════════════════════════════════
# IAM — Step Functions Execution Role
# ═══════════════════════════════════════════════════════════════════════════════

data "aws_iam_policy_document" "stepfunctions_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "stepfunctions_execution" {
  name               = "${var.project_name}-stepfunctions-execution-role"
  assume_role_policy = data.aws_iam_policy_document.stepfunctions_assume_role.json
  description        = "Execution role for AIOps Step Functions state machine"
}

data "aws_iam_policy_document" "stepfunctions_permissions" {
  # Invoke all Lambda functions called from state machine states
  statement {
    sid    = "InvokeLambdaFunctions"
    effect = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [
      aws_lambda_function.anomaly_detector.arn,
      aws_lambda_function.diagnose.arn,
      aws_lambda_function.remediate.arn,
      aws_lambda_function.escalate.arn,
      "${aws_lambda_function.diagnose.arn}:*",
      "${aws_lambda_function.remediate.arn}:*",
      "${aws_lambda_function.escalate.arn}:*",
    ]
  }

  # Write execution logs to CloudWatch
  statement {
    sid    = "CloudWatchLogsDelivery"
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }

  # X-Ray tracing
  statement {
    sid    = "XRayAccess"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
      "xray:GetSamplingRules",
      "xray:GetSamplingTargets",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "stepfunctions_permissions" {
  name        = "${var.project_name}-stepfunctions-permissions"
  description = "Permissions for AIOps Step Functions to invoke Lambda and write logs"
  policy      = data.aws_iam_policy_document.stepfunctions_permissions.json
}

resource "aws_iam_role_policy_attachment" "stepfunctions_permissions" {
  role       = aws_iam_role.stepfunctions_execution.name
  policy_arn = aws_iam_policy.stepfunctions_permissions.arn
}

# ─── EventBridge permission to invoke anomaly_detector Lambda ─────────────────
resource "aws_lambda_permission" "eventbridge_invoke_anomaly_detector" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.anomaly_detector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cloudwatch_alarm_state_change.arn
}
