# ═══════════════════════════════════════════════════════════════════════════════
# Cognito Authentication — User Pool + Hosted UI + SPA App Client (Phase 6)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Auth flow: Hosted UI (OAuth2 Authorization Code + PKCE)
#   1. Frontend redirects unauthenticated users to the Cognito Hosted UI URL
#   2. User signs in (email + password)
#   3. Cognito redirects back with ?code= query param
#   4. Frontend exchanges code for ID/Access tokens (PKCE — no client secret)
#   5. Access token is sent as "Authorization: Bearer <token>" on every API call
#   6. API Gateway JWT Authorizer validates the token against the User Pool JWKS
#
# No Lambda code changes needed — the JWT authorizer validates at the gateway.
# ═══════════════════════════════════════════════════════════════════════════════

# ─── User Pool ────────────────────────────────────────────────────────────────

resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-users"

  # Auto-verify email addresses so users can log in immediately after signup
  auto_verified_attributes = ["email"]

  # Username is the email address
  username_attributes = ["email"]

  username_configuration {
    case_sensitive = false
  }

  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_numbers                  = true
    require_uppercase                = false
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  # Self-service account recovery via email
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = {
    Name = "${var.project_name}-user-pool"
  }
}

# ─── Hosted UI domain ─────────────────────────────────────────────────────────
#
# Creates a free Cognito-managed domain:
#   https://<domain>.auth.<region>.amazoncognito.com
#
# Using account ID as suffix ensures global uniqueness.

resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project_name}-auth-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.main.id
}

# ─── SPA App Client ───────────────────────────────────────────────────────────
#
# No client secret → safe for public SPAs.
# Authorization Code + PKCE is the secure flow for browser apps.

resource "aws_cognito_user_pool_client" "spa" {
  name         = "${var.project_name}-spa"
  user_pool_id = aws_cognito_user_pool.main.id

  # No secret — the client is a public SPA (secret can't be kept safe in JS)
  generate_secret = false

  # OAuth2 Authorization Code flow (PKCE enforced by the frontend)
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]

  # Token validity
  access_token_validity  = 60    # minutes
  id_token_validity      = 60    # minutes
  refresh_token_validity = 30    # days

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  # Allowed redirect URLs (add Vercel URL here once deployed)
  callback_urls = [
    "http://localhost:8080",
    "http://localhost:8081",
    "https://kronos-aiops.vercel.app",
  ]

  logout_urls = [
    "http://localhost:8080",
    "http://localhost:8081",
    "https://kronos-aiops.vercel.app",
  ]

  # Prevent implicit flow — PKCE code flow only
  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]
}
