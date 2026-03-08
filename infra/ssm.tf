# ─── Guardrail Configuration ──────────────────────────────────────────────────
# Controls which incident types are eligible for auto-remediation.
# The settings page in the frontend writes to this parameter via PATCH /api/guardrails.
resource "aws_ssm_parameter" "guardrails" {
  name        = "/${var.project_name}/guardrails"
  description = "JSON: which incident types are allowed for auto-remediation"
  type        = "String"

  value = jsonencode({
    allowedTypes = ["CPU", "MEMORY", "DISK"]
    blockedTypes = ["LATENCY", "UNKNOWN"]
    version      = 1
  })

  tags = {
    Name = "${var.project_name}-guardrails"
  }
}

# ─── Anomaly Detection Thresholds ─────────────────────────────────────────────
# EWMA alpha and Z-score threshold used by the anomaly_detector Lambda.
# The settings page in the frontend writes to this parameter via PATCH /api/thresholds.
resource "aws_ssm_parameter" "thresholds" {
  name        = "/${var.project_name}/thresholds"
  description = "JSON: anomaly detection algorithm parameters (EWMA + Z-score)"
  type        = "String"

  value = jsonencode({
    zScoreThreshold = 3.0
    ewmaAlpha       = 0.3
    minDataPoints   = 60
    version         = 1
  })

  tags = {
    Name = "${var.project_name}-thresholds"
  }
}
