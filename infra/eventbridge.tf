# ─── EventBridge Custom Bus ───────────────────────────────────────────────────
# Used for custom application events in future phases.
# Note: CloudWatch Alarms always publish to the DEFAULT bus (not custom buses),
# so the alarm rule below targets event_bus_name = "default".
resource "aws_cloudwatch_event_bus" "aiops" {
  name = "${var.project_name}-event-bus"
}

# ─── Rule: CloudWatch Alarm state change → anomaly_detector Lambda ────────────
# Listens on the DEFAULT bus for our project's alarms entering ALARM state.
resource "aws_cloudwatch_event_rule" "cloudwatch_alarm_state_change" {
  name           = "${var.project_name}-alarm-state-change"
  description    = "Routes CloudWatch Alarm ALARM state changes to the anomaly detector Lambda"
  event_bus_name = "default" # CloudWatch Alarms publish here — cannot be changed

  event_pattern = jsonencode({
    source      = ["aws.cloudwatch"]
    detail-type = ["CloudWatch Alarm State Change"]
    detail = {
      state = {
        value = ["ALARM"]
      }
      alarmName = [{
        # Only capture alarms prefixed with our project name
        prefix = "${var.project_name}-"
      }]
    }
  })
}

resource "aws_cloudwatch_event_target" "anomaly_detector" {
  rule      = aws_cloudwatch_event_rule.cloudwatch_alarm_state_change.name
  target_id = "AnomalyDetectorLambda"
  arn       = aws_lambda_function.anomaly_detector.arn
}
