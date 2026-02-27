# Deployment Guide

Current design separates runtime into three services:

- `woka-frontend` (UI)
- `woka-backend` (FastAPI)
- `woka-agent` (LiveKit worker)

Use this document for local setup and high-level deployment flow.
For detailed GCP commands, use `docs/GCP_DEPLOYMENT.md`.

## Prerequisites

- Python 3.10+
- Node.js 18+
- Docker (optional for local images)
- LiveKit (cloud or local)
- GCP project (for cloud deployment)

## Local Development

### Install

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cd ../frontend
npm install
```

### Configure `.env`

Create root `.env` with at least:

```bash
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
GROQ_API_KEY=...
DEEPGRAM_API_KEY=...
```

Optional for session persistence:

```bash
SUPABASE_ENABLED=true
SUPABASE_URL=...
SUPABASE_KEY=...
```

### Run locally

```bash
# terminal 1
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
# terminal 2
cd backend
source venv/bin/activate
python -m bot.main dev
```

```bash
# terminal 3
cd frontend
npm run dev
```

## Docker Images

Local/manual image builds:

```bash
docker build -t woka-backend -f Dockerfile .
docker build -t woka-agent -f Dockerfile.agent .
docker build -t woka-frontend -f frontend/Dockerfile frontend
```

## GCP Deployment

### Backend + Frontend

```bash
PROJECT_ID=<your-project-id> REGION=asia-south1 REPO=woka-repo ./scripts/gcp/deploy.sh
```

### Agent only

```bash
gcloud builds submit --config=cloudbuild.agent.yaml \
  --substitutions=_REGION=asia-south1,_REPO=woka-repo,_TAG=latest

PROJECT_ID=<your-project-id> REGION=asia-south1 REPO=woka-repo TAG=latest \
  ./scripts/gcp/deploy-agent.sh
```

## Secret Handling Policy

- Deploy scripts do not create or mutate secrets.
- Secrets must already exist in Secret Manager.
- Deploy uses `--update-secrets` and `--update-env-vars` to preserve existing service config.

## Troubleshooting Quick Checks

```bash
gcloud run services list --region=asia-south1
gcloud run services logs read woka-agent --region=asia-south1 --limit=100
gcloud run services logs read woka-backend --region=asia-south1 --limit=100
```

If session summaries are not saving, verify:

- `SUPABASE_ENABLED=true`
- `SUPABASE_URL` env var exists on `woka-agent`
- `SUPABASE_KEY` secret is attached to `woka-agent`

