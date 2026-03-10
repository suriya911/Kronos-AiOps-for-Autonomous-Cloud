# Phase 6 — GitHub Setup Guide

## 1. Create a Pull Request

**Via GitHub.com:**

1. Go to: https://github.com/suriya911/Kronos-AiOps-for-Autonomous-Cloud
2. Click **"Compare & pull request"** (Brave will show this banner since you just pushed)
3. Base branch: **main**
4. Compare branch: **phase-2-anomaly-detection**
5. Title: `Phase 6: Full Production Hardening (Auth, CI/CD, CloudWatch)`
6. Description:
```
## Summary

Adds Cognito authentication, GitHub Actions CI/CD, and CloudWatch operations dashboard.

### What's included

**Authentication (OAuth2 PKCE)**
- Cognito User Pool + Hosted UI domain
- JWT Authorizer on HTTP API Gateway
- Frontend AuthGuard + auth.ts helper (no library)

**CI/CD (GitHub Actions + Vercel)**
- PR check workflow: TypeScript check + Vite build
- Deploy workflow: terraform apply + Vercel deploy

**CloudWatch Dashboard**
- 8-widget operations dashboard with Lambda, API, DynamoDB, StepFunctions, WebSocket metrics

### Tests will validate

✅ TypeScript compilation (zero errors)
✅ Vite build succeeds
✅ Frontend loads auth flow correctly
```
7. Click **"Create pull request"**

---

## 2. Add GitHub Secrets

**Via GitHub.com:**

Go to: https://github.com/suriya911/Kronos-AiOps-for-Autonomous-Cloud/settings/secrets/actions

Add these secrets **exactly as shown**:

### AWS Credentials (for terraform apply in Deploy workflow)

| Secret Name | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | *Your IAM user access key* |
| `AWS_SECRET_ACCESS_KEY` | *Your IAM user secret key* |

### Frontend Environment Variables (for Vite build)

| Secret Name | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://tozg3pwytc.execute-api.us-east-1.amazonaws.com` |
| `VITE_WS_URL` | `wss://r0o037d2gc.execute-api.us-east-1.amazonaws.com/prod` |
| `VITE_COGNITO_USER_POOL_ID` | `us-east-1_b7LI08o2i` |
| `VITE_COGNITO_CLIENT_ID` | `7de4o5p8lp0u4tgvp4sscm2e02` |
| `VITE_COGNITO_DOMAIN` | `https://aiops-auth-807430513014.auth.us-east-1.amazoncognito.com` |

### Vercel Deployment (for vercel CLI in Deploy workflow)

| Secret Name | Value |
|---|---|
| `VERCEL_TOKEN` | *Your Vercel personal access token* |
| `VERCEL_ORG_ID` | *Your Vercel organization/team ID* |
| `VERCEL_PROJECT_ID` | *Your Vercel project ID* |

**How to get Vercel secrets:**
- Token: https://vercel.com/account/tokens → Create token
- Org ID: https://vercel.com/account → Organization ID (or Team settings)
- Project ID: Deploy your project to Vercel first, then grab ID from `.vercel/project.json` or project settings

---

## 3. Monitor PR Check Workflow

After creating the PR:

1. GitHub will automatically run `.github/workflows/pr-check.yml`
2. Wait for the check to complete (should pass in ~2 min)
3. You'll see a green ✅ next to the commit if successful
4. If it fails, click "Details" to view the error

**Expected output:**
```
✓ tsc --noEmit (0 errors)
✓ bun run build (2787 modules transformed)
```

---

## 4. Merge to Main & Deploy

When PR check passes:

1. Click **"Merge pull request"** on the PR page
2. Confirm merge
3. GitHub will automatically run `.github/workflows/deploy.yml`:
   - **Job 1 (terraform):** Applies any infra changes (Cognito was already applied, so this is fast)
   - **Job 2 (vercel):** Builds frontend + deploys to Vercel production
4. Visit your Vercel production URL → AuthGuard redirects to Cognito login
5. Sign in with `test@example.com` / `TestPass123!`

---

## 5. Verify Everything Works

**Backend API now requires auth:**
```bash
curl https://tozg3pwytc.execute-api.us-east-1.amazonaws.com/kpi
# Returns: {"message":"Unauthorized"}

# With token:
curl -H "Authorization: Bearer <token>" \
  https://tozg3pwytc.execute-api.us-east-1.amazonaws.com/kpi
# Returns: KPI data
```

**Frontend:**
- http://localhost:8081 → redirects to Cognito login
- After sign-in → all 5 pages load real AWS data
- WebSocket auto-reconnects with exponential backoff

**CloudWatch Dashboard:**
- https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=aiops-ops
- Shows Lambda errors, API latency, DynamoDB throttles, etc.

---

## Summary

| Step | Status | What Happens |
|---|---|---|
| Create PR | ➡️ TODO | Push phase-2-anomaly-detection → main on GitHub |
| PR Check | Auto | TypeScript + build validation |
| Add Secrets | ➡️ TODO | GitHub Settings → Actions secrets |
| Merge PR | ➡️ TODO | Triggers Deploy workflow |
| Deploy | Auto | terraform + Vercel deploy |
| Test | ➡️ TODO | Sign in + verify all pages |

**Everything is ready. Just need the PR + secrets + merge!**
