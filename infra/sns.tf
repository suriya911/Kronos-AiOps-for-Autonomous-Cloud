# ─── SNS Topic for Incident Alerts ───────────────────────────────────────────
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-incident-alerts"
}

# Email subscription — AWS will send a confirmation email on first apply
# You MUST click the confirmation link before alerts will be delivered
resource "aws_sns_topic_subscription" "email_alert" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.sns_alert_email
}
