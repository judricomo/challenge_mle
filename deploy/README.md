# Cloud Run Deployment Guide

Complete guide for deploying the Flight Delay Prediction API to Google Cloud Run with structured branching strategy, automated CI/CD, traffic routing, stress testing, and A/B testing.

## 📋 Table of Contents

- [Architecture Overview](#architecture-overview)
- [Branching Strategy](#branching-strategy)
- [CI/CD Workflows](#cicd-workflows)
- [Prerequisites](#prerequisites)
- [Initial Setup](#initial-setup)
- [Development Workflow](#development-workflow)
- [Deployment Process](#deployment-process)
- [A/B Testing](#ab-testing)
- [Monitoring & Rollback](#monitoring--rollback)
- [Troubleshooting](#troubleshooting)

---

## 🏗️ Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                      Cloud Run Service                          │
│                   flight-delay-api                              │
├────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │ Staging Rev    │  │ Production Rev │  │  Model A/B     │  │
│  │ (0% traffic)   │  │ (canary/100%)  │  │  (split)       │  │
│  │ Test only      │  │ Live traffic   │  │  Experiments   │  │
│  └────────────────┘  └────────────────┘  └────────────────┘  │
│                                                                  │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │  Vertex AI Model     │
                │  Registry            │
                │                      │
                │  gs://delay_models   │
                └──────────────────────┘
```

### Key Features

- **Zero-downtime deployments** with traffic routing
- **Canary releases** for gradual rollouts (10% → 50% → 100%)
- **A/B testing** for comparing model versions
- **Automated stress testing** on every deployment
- **Environment isolation** (staging vs production)
- **Model versioning** via Vertex AI Registry

---

## 🌳 Branching Strategy

```
feature/xxx ──PR──▶ develop ──PR──▶ release/vX.X.X ──Merge──▶ main
    │                  │                 │                        │
    │                  │                 │                        │
    ▼                  ▼                 ▼                        ▼
  Tests           Tests            Staging Deploy         Production Deploy
   only            only            (0% traffic)           (canary/100%)
```

### Branch Types

| Branch | Purpose | Triggers | Deployment |
|--------|---------|----------|------------|
| `feature/**` | Development work | Tests only | None |
| `develop` | Integration | Tests only | None |
| `release/**` | Pre-production | Tests + Stress + Staging | Staging (0% traffic) |
| `main` | Production | Tests + Stress + Production | Production (canary) |

### Naming Conventions

- **Feature branches**: `feature/add-new-model`, `feature/fix-preprocessing`
- **Release branches**: `release/v1.0.0`, `release/v1.1.0`

---

## ⚙️ CI/CD Workflows

### 1. **CI - Feature Tests** (`.github/workflows/ci-feature.yml`)

**Triggers**: Push to `feature/**` or PR to `develop`

**Actions**:
- ✅ Run unit tests (model + API)
- ✅ Upload coverage reports
- ✅ Upload test results

**No deployment** - fast feedback loop for developers.

---

### 2. **CI - Staging Deployment** (`.github/workflows/ci-staging.yml`)

**Triggers**: PR from `develop` to `release/**`

**Actions**:
1. Run all tests (model + API)
2. Build Docker image
3. Push to GCR: `gcr.io/PROJECT_ID/flight-delay-api:staging-SHA`
4. Deploy to Cloud Run with **0% traffic** (staging revision)
5. Run stress tests (100 users, 60 seconds)
6. Comment PR with staging URL

**Result**: Isolated staging environment for testing before production.

---

### 3. **CD - Production Deployment** (`.github/workflows/cd-prod.yml`)

**Triggers**: Merge from `release/**` to `main`

**Actions**:
1. Run all tests
2. Build and push Docker image: `gcr.io/PROJECT_ID/flight-delay-api:prod-SHA`
3. Deploy to Cloud Run with **canary strategy** (default 10% traffic)
4. Run production stress tests
5. Create deployment summary with traffic management commands

**Deployment Strategies**:
- **Canary** (default): 10% → monitor → 50% → monitor → 100%
- **Direct**: 100% traffic immediately (manual trigger only)

---

### 4. **A/B Test Deployment** (`.github/workflows/ab-test.yml`)

**Triggers**: Manual workflow dispatch

**Actions**:
1. Deploy Model A (baseline) with 0% traffic
2. Deploy Model B (variant) with 0% traffic
3. Split traffic between models (e.g., 50/50)
4. Provide tagged URLs for direct testing

**Use case**: Compare two different models in production.

---

### 5. **A/B Test Analysis** (`.github/workflows/ab-test-analysis.yml`)

**Triggers**: Manual workflow dispatch

**Actions**:
1. Query Cloud Logging for request counts
2. Analyze error rates per revision
3. Provide latency metrics links
4. Generate recommendations for winner promotion

---

## 🔧 Prerequisites

### 1. GCP Project Setup

```bash
# Set your project
export GCP_PROJECT_ID="norse-botany-479603-v0"
export GCP_REGION="us-central1"

gcloud config set project $GCP_PROJECT_ID
```

### 2. Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  containerregistry.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  storage.googleapis.com
```

### 3. Create Service Account

```bash
# Create service account for GitHub Actions
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions Service Account"

# Grant necessary roles
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:github-actions@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:github-actions@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:github-actions@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:github-actions@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

### 4. Setup Workload Identity Federation (Recommended)

Instead of service account keys, use Workload Identity Federation:

```bash
# Create workload identity pool
gcloud iam workload-identity-pools create "github-pool" \
  --location="global" \
  --display-name="GitHub Actions Pool"

# Create workload identity provider
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Get the provider resource name
gcloud iam workload-identity-pools providers describe "github-provider" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --format="value(name)"

# Allow GitHub repo to impersonate service account
gcloud iam service-accounts add-iam-policy-binding \
  "github-actions@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/judricomo/challenge_mle"
```

### 5. Configure GitHub Secrets

Go to **GitHub Repository → Settings → Secrets and variables → Actions** and add:

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider` | Workload Identity Provider |
| `GCP_SERVICE_ACCOUNT` | `github-actions@PROJECT_ID.iam.gserviceaccount.com` | Service Account Email |
| `VERTEX_MODEL_NAME_STAGING` | `flight-delay-model` | Model name for staging |
| `VERTEX_MODEL_NAME_PROD` | `flight-delay-model` | Model name for production |

---

## 🚀 Initial Setup

### 1. Clone Repository

```bash
git clone https://github.com/judricomo/challenge_mle.git
cd challenge_mle
```

### 2. Create Branch Structure

```bash
# Create develop branch
git checkout -b develop
git push -u origin develop

# Set up branch protection rules on GitHub
# Settings → Branches → Add rule
# - Branch name pattern: main, develop, release/*
# - Require pull request reviews
# - Require status checks to pass
```

### 3. Upload Initial Model

```bash
# Train and upload model
python scripts/train_model.py
python scripts/upload_to_vertex.py
```

### 4. Test Local Docker Build

```bash
make docker-build
make docker-run
```

---

## 💻 Development Workflow

### Creating a New Feature

```bash
# 1. Create feature branch from develop
git checkout develop
git pull origin develop
git checkout -b feature/improve-model

# 2. Make changes
# Edit code, add features, etc.

# 3. Test locally
make model-test
make api-test
make docker-build

# 4. Commit and push
git add .
git commit -m "Improve model accuracy with feature engineering"
git push origin feature/improve-model

# 5. Create PR to develop on GitHub
# GitHub → Pull Requests → New Pull Request
# Base: develop ← Compare: feature/improve-model

# 6. CI workflow runs automatically:
#    - Runs all tests
#    - No deployment

# 7. After review, merge to develop
```

### Deploying to Staging

```bash
# 1. Create release branch from develop
git checkout develop
git pull origin develop
git checkout -b release/v1.1.0

# 2. Push release branch
git push -u origin release/v1.1.0

# 3. Create PR from develop to release/v1.1.0
# GitHub → Pull Requests → New Pull Request
# Base: release/v1.1.0 ← Compare: develop

# 4. CI-Staging workflow runs automatically:
#    - Runs all tests
#    - Builds Docker image
#    - Deploys to Cloud Run (0% traffic)
#    - Runs stress tests
#    - Comments PR with staging URL

# 5. Test staging environment
curl https://staging-revision-url/health
curl -X POST https://staging-revision-url/predict \
  -H "Content-Type: application/json" \
  -d '{"flights":[{"OPERA":"Grupo LATAM","TIPOVUELO":"N","MES":3}]}'

# 6. After testing, merge PR
```

### Deploying to Production

```bash
# 1. Create PR from release/v1.1.0 to main
# GitHub → Pull Requests → New Pull Request
# Base: main ← Compare: release/v1.1.0

# 2. Review changes carefully

# 3. Merge PR to main

# 4. CD-Production workflow runs automatically:
#    - Runs all tests
#    - Builds Docker image
#    - Deploys to Cloud Run with canary (10% traffic)
#    - Runs stress tests
#    - Creates deployment summary

# 5. Monitor canary deployment (see next section)
```

---

## 📊 Deployment Process

### Canary Deployment Flow

```
Deploy (10%) → Monitor 15-30 min → Increase (50%) → Monitor 15-30 min → Full (100%)
     │              │                    │                  │                  │
     │              │                    │                  │                  │
     ▼              ▼                    ▼                  ▼                  ▼
 New revision   Check metrics      Adjust traffic     Check metrics      Promote
 with 10%       - Errors           to 50%             - Errors           to 100%
 traffic        - Latency                             - Latency
                - Success rate                        - Success rate
```

### 1. Initial Deployment (10% canary)

Automatically triggered by merging to `main`:

```bash
# Check deployment status
gcloud run services describe flight-delay-api \
  --region=us-central1 \
  --format='table(status.traffic.revisionName,status.traffic.percent)'

# Output:
# REVISION                              PERCENT
# flight-delay-api-prod-20251128-120000  10      ← New
# flight-delay-api-prod-20251127-110000  90      ← Old
```

### 2. Monitor Metrics

```bash
# View logs
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=flight-delay-api" \
  --limit 50

# Check error rate
gcloud logging read \
  "resource.type=cloud_run_revision AND severity>=ERROR" \
  --limit 50

# View in Cloud Console
open https://console.cloud.google.com/run/detail/us-central1/flight-delay-api/metrics
```

**Key metrics to watch**:
- ✅ Error rate < 1%
- ✅ Latency p95 similar to previous version
- ✅ Success rate > 99%

### 3. Increase Traffic (50%)

If metrics look good after 15-30 minutes:

```bash
# Get revision names
gcloud run services describe flight-delay-api \
  --region=us-central1 \
  --format='value(status.traffic.revisionName)'

# Increase to 50%
gcloud run services update-traffic flight-delay-api \
  --region=us-central1 \
  --to-revisions=flight-delay-api-prod-20251128-120000=50,flight-delay-api-prod-20251127-110000=50
```

**Or use GitHub Actions**:
- Go to: **Actions → CD - Production Deployment**
- Click **Run workflow**
- Select **Deployment strategy**: canary
- Set **Canary percent**: 50

### 4. Full Promotion (100%)

After monitoring 50% split for 15-30 minutes:

```bash
# Promote to 100%
gcloud run services update-traffic flight-delay-api \
  --region=us-central1 \
  --to-revisions=flight-delay-api-prod-20251128-120000=100
```

✅ **Done!** New version is now serving 100% of production traffic.

---

## 🧪 A/B Testing

### Use Case

Compare two different models (e.g., different algorithms or feature sets) in production to determine which performs better.

### Prerequisites

1. Train two models locally
2. Upload both to Vertex AI with different names:
   - Model A: `flight-delay-model`
   - Model B: `flight-delay-model-v2`

### Running A/B Test

1. **Go to GitHub Actions**:
   - Navigate to: **Actions → A/B Test Deployment**
   - Click **Run workflow**

2. **Configure test**:
   - **Model A name**: `flight-delay-model`
   - **Model B name**: `flight-delay-model-v2`
   - **Traffic split**: `50` (50% each)
   - Click **Run workflow**

3. **Test both models**:

```bash
# Main URL (traffic split)
SERVICE_URL="https://flight-delay-api-XXX.a.run.app"

# Model A only (tagged URL)
MODEL_A_URL="https://model-a---flight-delay-api-XXX.a.run.app"

# Model B only (tagged URL)
MODEL_B_URL="https://model-b---flight-delay-api-XXX.a.run.app"

# Test Model A
curl -X POST $MODEL_A_URL/predict \
  -H "Content-Type: application/json" \
  -d '{"flights":[{"OPERA":"Grupo LATAM","TIPOVUELO":"N","MES":3}]}'

# Test Model B
curl -X POST $MODEL_B_URL/predict \
  -H "Content-Type: application/json" \
  -d '{"flights":[{"OPERA":"Grupo LATAM","TIPOVUELO":"N","MES":3}]}'
```

### Analyzing Results

After 24-48 hours, run analysis:

1. **Go to GitHub Actions**:
   - Navigate to: **Actions → A/B Test Analysis**
   - Click **Run workflow**
   - Select **Hours to analyze**: 24
   - Click **Run workflow**

2. **Review metrics**:
   - Request counts per model
   - Error rates
   - Latency (link to Cloud Monitoring)

3. **Compare**:
   - Which model has lower error rate?
   - Which model has better latency?
   - Which model serves requests more successfully?

### Promoting Winner

```bash
# If Model B wins
gcloud run services update-traffic flight-delay-api \
  --region=us-central1 \
  --to-revisions=flight-delay-api-model-b-20251128-120000=100
```

---

## 📈 Monitoring & Rollback

### Monitoring

**Cloud Console Dashboard**:
```
https://console.cloud.google.com/run/detail/us-central1/flight-delay-api/metrics
```

**Key Metrics**:
- Request count
- Request latency (p50, p95, p99)
- Error rate (4xx, 5xx)
- Container instance count
- Memory/CPU utilization

**Logs**:
```bash
# View recent logs
gcloud logging read \
  "resource.type=cloud_run_revision" \
  --limit 100 \
  --format json

# Follow logs in real-time
gcloud logging tail \
  "resource.type=cloud_run_revision AND resource.labels.service_name=flight-delay-api"
```

### Instant Rollback

If issues are detected:

```bash
# List revisions
gcloud run revisions list \
  --service=flight-delay-api \
  --region=us-central1

# Rollback to previous revision
gcloud run services update-traffic flight-delay-api \
  --region=us-central1 \
  --to-revisions=flight-delay-api-prod-20251127-110000=100
```

**Rollback takes ~5 seconds** with zero downtime.

---

## 🔍 Troubleshooting

### Issue: Workflow fails with "Context access might be invalid"

**Cause**: GitHub Secrets not configured.

**Solution**: Add all required secrets in GitHub → Settings → Secrets → Actions:
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`
- `VERTEX_MODEL_NAME_STAGING`
- `VERTEX_MODEL_NAME_PROD`

### Issue: Service won't start - "Could not load model"

**Cause**: Model not found in Vertex AI or incorrect permissions.

**Solution**:
```bash
# Check model exists
gcloud ai models list --region=us-central1

# Check service account permissions
gcloud projects get-iam-policy norse-botany-479603-v0 \
  --flatten="bindings[].members" \
  --filter="bindings.members:github-actions@"
```

### Issue: 502/503 errors

**Cause**: Container startup timeout or memory issues.

**Solution**: Increase timeout and memory:
```bash
gcloud run services update flight-delay-api \
  --timeout=600 \
  --memory=4Gi \
  --region=us-central1
```

### Issue: Staging deployment has 0% traffic but can't access URL

**Cause**: This is expected - staging revisions have unique URLs.

**Solution**: Use the revision-specific URL from the PR comment, not the main service URL.

---

## 📚 Additional Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Traffic Management Guide](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
- [Vertex AI Model Registry](https://cloud.google.com/vertex-ai/docs/model-registry/introduction)
- [GitHub Actions + GCP](https://github.com/google-github-actions/auth)

---

## 🎯 Quick Reference

### Common Commands

```bash
# Build locally
make docker-build

# Run locally
make docker-run

# Run tests
make model-test
make api-test

# Run stress tests (local)
make stress-test

# Run stress tests (deployed)
STRESS_URL=https://your-api.run.app make stress-test

# Check traffic split
gcloud run services describe flight-delay-api --region=us-central1

# View logs
gcloud logging tail "resource.type=cloud_run_revision"

# Rollback
gcloud run services update-traffic flight-delay-api \
  --to-revisions=<previous-revision>=100 --region=us-central1
```

### Workflow Triggers

| Workflow | Trigger | Purpose |
|----------|---------|---------|------|
| CI - Feature | Push to `feature/**` or PR to `develop` | Run tests only |
| CI - Staging | PR to `release/**` | Deploy to staging (0% traffic) |
| CD - Production | Merge to `main` | Deploy to production (canary) |
| A/B Test | Manual | Deploy two models with traffic split |
| A/B Analysis | Manual | Analyze A/B test metrics |

---

**Need help?** Check the troubleshooting section or review the workflow files in `.github/workflows/`.
