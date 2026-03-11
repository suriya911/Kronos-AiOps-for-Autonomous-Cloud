# ─── SNS Topic for Incident Alerts ───────────────────────────────────────────
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-incident-alerts"
}

# Email subscription — only created when sns_alert_email is set
# AWS will send a confirmation email on first apply — click the link to activate alerts
resource "aws_sns_topic_subscription" "email_alert" {
  count     = var.sns_alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.sns_alert_email
}
