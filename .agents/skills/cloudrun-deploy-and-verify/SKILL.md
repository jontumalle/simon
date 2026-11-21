---
name: cloudrun-deploy-and-verify
description: >-
  Runbook for deploying Simon's platform to Cloud Run (simon-staging / simon-prod), triaging GitHub
  Actions workflows (deploy-platform.yml, deploy-agents.yml, eval-discovery-vertex.yml), and
  verifying live staging endpoints, Firestore access, and Managed Agent fleet health. Activate
  whenever deploying the app, debugging failed CI runs, or checking staging health.
---

# Cloud Run Deploy, CI Triage & Staging Verification

## Canonical Staging Target
- **GCP Project**: `gemini4nyc26nyc-2203` · **Region**: `us-east1`
- **Staging Service**: `simon-staging` → `https://simon-staging-139550420825.us-east1.run.app`
- **Prod Service**: `simon-prod` (from `prod` branch)
- **CLI Path**: Always prepend `export PATH="$HOME/google-cloud-sdk/bin:$PATH"` (or call `~/google-cloud-sdk/bin/gcloud`).

---

## 1. Preferred Path: Trigger & Monitor GitHub Actions CI
Platform and Managed Agent deploys run automatically on `main` pushes via `.github/workflows/deploy-platform.yml` and `.github/workflows/deploy-agents.yml`.

```bash
# Check recent workflow runs
gh run list --limit 10

# Inspect a failed run's logs
gh run view <run-id> --log-failed

# Manually trigger staging platform deploy
gh workflow run deploy-platform.yml --ref main -f service_name=simon-staging

# Manually trigger Managed Agents deploy (all or single agent)
gh workflow run deploy-agents.yml --ref main -f prefix=staging-
gh workflow run deploy-agents.yml --ref main -f prefix=staging- -f agent=<slug>
```

---

## 2. Direct Local Cloud Run Deploy (When Needed)
If you need to deploy directly without waiting on Actions:

```bash
export PATH="$HOME/google-cloud-sdk/bin:$PATH"
PROJECT="gemini4nyc26nyc-2203"
REGION="us-east1"
SERVICE="simon-staging"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/simon/simon-platform:$(git rev-parse --short HEAD)"

gcloud builds submit --project="$PROJECT" --tag="$IMAGE" .
gcloud run deploy "$SERVICE" \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080
```
*(Preserve existing env vars / secrets on the service — do not overwrite `GEMINI_API_KEY` with a blank value.)*

---

## 3. Live Staging Verification Checklist
Run after every deploy and report exact HTTP status codes and counts:

```bash
BASE="https://simon-staging-139550420825.us-east1.run.app"

# 1. Home UI + health check
curl -sS -o /dev/null -w "GET / -> %{http_code}\n" "$BASE/"
curl -sS "$BASE/api/agents" | head -c 300 && echo ""

# 2. Firestore-backed endpoints
curl -sS "$BASE/api/sources" | head -c 300 && echo ""
curl -sS "$BASE/api/agent-runs" | head -c 300 && echo ""

# 3. Cloud Run logs if a 5xx appears
~/google-cloud-sdk/bin/gcloud run services logs read simon-staging \
  --region=us-east1 --project=gemini4nyc26nyc-2203 --limit=40
```
