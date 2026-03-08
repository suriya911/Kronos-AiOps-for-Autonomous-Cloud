# ═══════════════════════════════════════════════════════════════════════════════
# CloudWatch Alarms
# These publish state-change events to the default EventBridge bus.
# The EventBridge rule in eventbridge.tf routes ALARM events to anomaly_detector.
# ═══════════════════════════════════════════════════════════════════════════════

# ─── CPU High ─────────────────────────────────────────────────────────────────
# Will be in INSUFFICIENT_DATA until an EC2 instance reports metrics.
# To target a specific instance, uncomment the dimensions block below.
resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "${var.project_name}-high-cpu-utilization"
  alarm_description   = "[AIOps] CPU utilization exceeded ${var.cloudwatch_alarm_cpu_threshold}% — triggers anomaly detector"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Average"
  threshold           = var.cloudwatch_alarm_cpu_threshold
  treat_missing_data  = "notBreaching"

  # actions handled via EventBridge rule — no direct alarm action needed
  alarm_actions = []

  # Uncomment to target a specific EC2 instance:
  # dimensions = {
  #   InstanceId = "i-REPLACE_WITH_YOUR_INSTANCE_ID"
  # }

  tags = { Name = "${var.project_name}-high-cpu" }
}

# ─── Memory High (requires CloudWatch Agent on EC2) ───────────────────────────
resource "aws_cloudwatch_metric_alarm" "high_memory" {
  alarm_name          = "${var.project_name}-high-memory-utilization"
  alarm_description   = "[AIOps] Memory usage exceeded 85% — triggers anomaly detector"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "mem_used_percent"
  namespace           = "CWAgent"
  period              = 60
  statistic           = "Average"
  threshold           = 85
  treat_missing_data  = "notBreaching"
  alarm_actions       = []

  tags = { Name = "${var.project_name}-high-memory" }
}

# ─── Disk High (requires CloudWatch Agent on EC2) ─────────────────────────────
resource "aws_cloudwatch_metric_alarm" "high_disk" {
  alarm_name          = "${var.project_name}-high-disk-utilization"
  alarm_description   = "[AIOps] Disk usage exceeded 90% — triggers anomaly detector"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "disk_used_percent"
  namespace           = "CWAgent"
  period              = 300
  statistic           = "Average"
  threshold           = 90
  treat_missing_data  = "notBreaching"
  alarm_actions       = []

  tags = { Name = "${var.project_name}-high-disk" }
}

# ─── API Latency High (p99 > 2s) ─────────────────────────────────────────────
resource "aws_cloudwatch_metric_alarm" "high_latency" {
  alarm_name          = "${var.project_name}-high-api-latency"
  alarm_description   = "[AIOps] API Gateway p99 latency exceeded 2s — triggers anomaly detector"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "Latency"
  namespace           = "AWS/ApiGateway"
  period              = 60
  extended_statistic  = "p99"
  threshold           = 2000 # ms
  treat_missing_data  = "notBreaching"
  alarm_actions       = []

  tags = { Name = "${var.project_name}-high-latency" }
}
