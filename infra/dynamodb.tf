# ─── Table 1: incidents ───────────────────────────────────────────────────────
# Main table — stores full incident lifecycle records
resource "aws_dynamodb_table" "incidents" {
  name         = "${var.project_name}_incidents"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "incidentId"

  attribute {
    name = "incidentId"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "detectedAt"
    type = "S"
  }

  # GSI: query by status + time — used by dashboard filters
  global_secondary_index {
    name            = "status-detectedAt-index"
    hash_key        = "status"
    range_key       = "detectedAt"
    projection_type = "ALL"
  }

  # DynamoDB Streams: required for WebSocket real-time push (wired in Phase 4)
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "${var.project_name}_incidents"
  }
}

# ─── Table 2: metrics_cache ───────────────────────────────────────────────────
# Caches recent CloudWatch metric data to avoid API throttling
resource "aws_dynamodb_table" "metrics_cache" {
  name         = "${var.project_name}_metrics_cache"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "metricName"
  range_key    = "timestamp"

  attribute {
    name = "metricName"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  # TTL: auto-expire cached entries after 24 hours (set expiresAt = epoch+86400)
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  tags = {
    Name = "${var.project_name}_metrics_cache"
  }
}

# ─── Table 3: remediations ────────────────────────────────────────────────────
# Audit log for every remediation action taken
resource "aws_dynamodb_table" "remediations" {
  name         = "${var.project_name}_remediations"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "remediationId"

  attribute {
    name = "remediationId"
    type = "S"
  }

  attribute {
    name = "incidentId"
    type = "S"
  }

  # GSI: look up all remediations for a given incident
  global_secondary_index {
    name            = "incidentId-index"
    hash_key        = "incidentId"
    projection_type = "ALL"
  }

  tags = {
    Name = "${var.project_name}_remediations"
  }
}

# ─── Table 4: ws_connections ──────────────────────────────────────────────────
# Tracks active WebSocket connection IDs for broadcasting
resource "aws_dynamodb_table" "ws_connections" {
  name         = "${var.project_name}_ws_connections"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "connectionId"

  attribute {
    name = "connectionId"
    type = "S"
  }

  # TTL: auto-expire stale connections after 2 hours
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  tags = {
    Name = "${var.project_name}_ws_connections"
  }
}
