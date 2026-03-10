#!/usr/bin/env bash
# ─── AIOps Bootstrap Script ───────────────────────────────────────────────────
# Run ONCE before: terraform init
# What it does:
#   1. Creates S3 bucket for Terraform remote state
#   2. Creates DynamoDB table for Terraform state locking
#   3. Auto-patches infra/main.tf with your account ID
#   4. Creates local .archives/ directory for Lambda zips
#
# Usage:
#   chmod +x scripts/bootstrap.sh
#   ./scripts/bootstrap.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
BUCKET_NAME="aiops-terraform-state-${ACCOUNT_ID}"
LOCK_TABLE="aiops-tf-lock"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "${SCRIPT_DIR}")"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     AIOps Bootstrap                  ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "  Account  : ${ACCOUNT_ID}"
echo "  Region   : ${REGION}"
echo "  S3 Bucket: ${BUCKET_NAME}"
echo "  DDB Lock : ${LOCK_TABLE}"
echo ""

# ── Step 1: Create S3 state bucket ───────────────────────────────────────────
echo "[1/4] S3 state bucket..."

if aws s3api head-bucket --bucket "${BUCKET_NAME}" 2>/dev/null; then
  echo "  ✓ Already exists: ${BUCKET_NAME}"
else
  aws s3api create-bucket \
    --bucket "${BUCKET_NAME}" \
    --region "${REGION}" > /dev/null
  echo "  ✓ Created: ${BUCKET_NAME}"
fi

# Versioning: protects against accidental state deletion
aws s3api put-bucket-versioning \
  --bucket "${BUCKET_NAME}" \
  --versioning-configuration Status=Enabled
echo "  ✓ Versioning enabled"

# Encryption at rest
aws s3api put-bucket-encryption \
  --bucket "${BUCKET_NAME}" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
echo "  ✓ AES-256 encryption enabled"

# Block all public access
aws s3api put-public-access-block \
  --bucket "${BUCKET_NAME}" \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
echo "  ✓ Public access blocked"

# ── Step 2: Create DynamoDB lock table ───────────────────────────────────────
echo ""
echo "[2/4] DynamoDB lock table..."

if aws dynamodb describe-table \
  --table-name "${LOCK_TABLE}" \
  --region "${REGION}" > /dev/null 2>&1; then
  echo "  ✓ Already exists: ${LOCK_TABLE}"
else
  aws dynamodb create-table \
    --table-name "${LOCK_TABLE}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "${REGION}" > /dev/null
  echo "  ✓ Created: ${LOCK_TABLE}"
fi

# ── Step 3: Patch infra/main.tf with bucket name ─────────────────────────────
echo ""
echo "[3/4] Patching infra/main.tf..."

MAIN_TF="${ROOT_DIR}/infra/main.tf"
if grep -q "YOUR_ACCOUNT_ID" "${MAIN_TF}"; then
  # Cross-platform sed: GNU sed (Linux/WSL/Git Bash) uses -i, BSD sed (macOS) needs -i ''
  if sed --version 2>/dev/null | grep -q GNU; then
    sed -i "s/aiops-terraform-state-YOUR_ACCOUNT_ID/${BUCKET_NAME}/" "${MAIN_TF}"
  else
    sed -i '' "s/aiops-terraform-state-YOUR_ACCOUNT_ID/${BUCKET_NAME}/" "${MAIN_TF}"
  fi
  echo "  ✓ Updated bucket name in main.tf → ${BUCKET_NAME}"
else
  echo "  ✓ main.tf already patched (bucket name found)"
fi

# ── Step 4: Create .archives directory ───────────────────────────────────────
echo ""
echo "[4/4] Creating .archives/ directory..."
mkdir -p "${ROOT_DIR}/.archives"
echo "  ✓ .archives/ ready (Lambda zips go here)"

# ─── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════╗"
echo "║  Bootstrap complete!                 ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo ""
echo "  1.  cd infra"
echo "  2.  cp terraform.tfvars.example terraform.tfvars"
echo "  3.  Edit terraform.tfvars — set sns_alert_email"
echo "  4.  terraform init"
echo "  5.  terraform plan"
echo "  6.  terraform apply"
echo ""
echo "  After apply, check Stop Check 1 criteria in the README."
echo ""
