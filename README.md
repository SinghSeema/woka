# Woka Wellness Voice AI Assistant

Voice-first wellness coaching app with real-time conversation, session memory, and Cloud Run deployment.

## Current Architecture

Production deployment is split into **three Cloud Run services**:

- `woka-frontend`: React app (Vite build, Nginx runtime)
- `woka-backend`: FastAPI API service
- `woka-agent`: LiveKit agent worker process

This separation avoids API/worker contention and makes worker tuning independent from API scaling.

## Core Stack

- Frontend: React + Vite + Tailwind
- Backend: FastAPI (Python)
- Agent: Pipecat + LiveKit Agents
- AI: Groq (LLM), Deepgram (STT/TTS)
- Realtime: LiveKit Cloud
- Optional persistence: Supabase

## Local Development

### Prerequisites

- Python 3.10+
- Node.js 18+
- LiveKit (local or cloud)
- Docker (optional for local container runs)

### 1) Install dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cd ../frontend
npm install
```

### 2) Configure environment

Create a `.env` file at repo root. At minimum:

```bash
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
GROQ_API_KEY=...
DEEPGRAM_API_KEY=...
```

Optional for session save:

```bash
SUPABASE_ENABLED=true
SUPABASE_URL=...
SUPABASE_KEY=...
```

### 3) Start services (3 terminals)

```bash
# Terminal 1: backend API
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
# Terminal 2: agent worker
cd backend
source venv/bin/activate
python -m bot.main dev
```

```bash
# Terminal 3: frontend
cd frontend
npm run dev
```

Local URLs:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

## GCP Deployment

### Backend + Frontend

```bash
chmod +x scripts/gcp/deploy.sh
PROJECT_ID=<your-project-id> REGION=asia-south1 REPO=woka-repo ./scripts/gcp/deploy.sh
```

### Agent only

```bash
gcloud builds submit --config=cloudbuild.agent.yaml \
  --substitutions=_REGION=asia-south1,_REPO=woka-repo,_TAG=latest

PROJECT_ID=<your-project-id> REGION=asia-south1 REPO=woka-repo TAG=latest \
  ./scripts/gcp/deploy-agent.sh
```

## Secret Manager Policy (Important)

Deployment scripts follow this policy:

- **Never create or modify secrets during deploy**
- **Only reference existing Secret Manager secrets**
- Use `--update-env-vars` and `--update-secrets` to avoid replacing all runtime config

Required secrets in GCP:

- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `GROQ_API_KEY`
- `DEEPGRAM_API_KEY`
- `SUPABASE_KEY` (if Supabase enabled)

Optional secrets:

- `OPENAI_API_KEY`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

## How `.env` Is Used in Cloud

- Cloud Run does **not** read `.env` files directly.
- `scripts/gcp/deploy-agent.sh` reads root `.env`, extracts non-secret config, and pushes those as Cloud Run env vars.
- Sensitive keys are excluded from `.env` export and sourced from Secret Manager.
- `LIVEKIT_URL` is forced to the production LiveKit Cloud URL for agent deployments.

## Key Files

- `Dockerfile`: backend API image
- `Dockerfile.agent`: dedicated agent worker image
- `cloudbuild.backend.yaml`: backend image build
- `cloudbuild.frontend.yaml`: frontend image build
- `cloudbuild.agent.yaml`: agent image build
- `scripts/gcp/deploy.sh`: backend + frontend deploy
- `scripts/gcp/deploy-agent.sh`: agent-only deploy

## Documentation

- `docs/GCP_DEPLOYMENT.md` - current GCP deployment flow
- `docs/DEPLOYMENT.md` - local + cloud deployment guide
- `docs/DEBUG_BOT_JOIN_ISSUE.md` - LiveKit/worker troubleshooting notes
- `docs/DEBUG_SESSION_SAVING.md` - session persistence debugging notes

