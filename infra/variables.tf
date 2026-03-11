variable "aws_region" {
  description = "AWS region to deploy all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name prefix for all resource names"
  type        = string
  default     = "aiops"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "sns_alert_email" {
  description = "Email address to receive incident escalation alerts (you'll get a confirmation email)"
  type        = string
  default     = ""
}

variable "lambda_timeout" {
  description = "Default Lambda function timeout in seconds"
  type        = number
  default     = 30
}

variable "lambda_memory_mb" {
  description = "Default Lambda function memory allocation in MB"
  type        = number
  default     = 256
}

variable "anomaly_lambda_memory_mb" {
  description = "Memory for anomaly detector Lambda (higher for scipy layer)"
  type        = number
  default     = 512
}

variable "dynamodb_billing_mode" {
  description = "DynamoDB billing mode — PAY_PER_REQUEST stays within free tier"
  type        = string
  default     = "PAY_PER_REQUEST"
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days"
  type        = number
  default     = 7
}

variable "cloudwatch_alarm_cpu_threshold" {
  description = "CPU utilization % threshold to trigger anomaly detection alarm"
  type        = number
  default     = 80
}
