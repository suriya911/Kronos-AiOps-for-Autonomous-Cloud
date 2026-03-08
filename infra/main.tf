terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }

  # ─── Remote State ────────────────────────────────────────────────────────────
  # BEFORE running terraform init:
  #   1. Run: ./scripts/bootstrap.sh   (auto-fills YOUR_ACCOUNT_ID below)
  #   2. Or manually: replace YOUR_ACCOUNT_ID with your 12-digit AWS account ID
  # ─────────────────────────────────────────────────────────────────────────────
  backend "s3" {
    bucket         = "aiops-terraform-state-YOUR_ACCOUNT_ID"
    key            = "aiops/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "aiops-tf-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# ─── Data Sources ─────────────────────────────────────────────────────────────
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
