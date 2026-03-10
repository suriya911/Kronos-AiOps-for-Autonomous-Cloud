# ─── CloudWatch Log Group for Step Functions execution logs ───────────────────
resource "aws_cloudwatch_log_group" "stepfunctions" {
  name              = "/aws/states/${var.project_name}-incident-workflow"
  retention_in_days = var.log_retention_days
}

# ─── State Machine ────────────────────────────────────────────────────────────
# Phase 1: simple Pass state (placeholder). ASL is replaced in Phase 3.
resource "aws_sfn_state_machine" "incident_workflow" {
  name     = "${var.project_name}-incident-workflow"
  role_arn = aws_iam_role.stepfunctions_execution.arn

  # Phase 3: templatefile() injects Lambda ARNs into the ASL so we avoid
  # hard-coding account IDs or region strings inside the JSON file.
  definition = templatefile("${path.module}/../backend/state_machines/incident_workflow.asl.json", {
    diagnose_arn  = aws_lambda_function.diagnose.arn
    remediate_arn = aws_lambda_function.remediate.arn
    escalate_arn  = aws_lambda_function.escalate.arn
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.stepfunctions.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  depends_on = [
    aws_cloudwatch_log_group.stepfunctions,
    aws_iam_role_policy_attachment.stepfunctions_permissions,
  ]
}
