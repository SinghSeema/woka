# GCP Deployment (Cloud Run + Secret Manager)

This project is deployed as **three Cloud Run services**:

- `woka-frontend` (React static app)
- `woka-backend` (FastAPI API)
- `woka-agent` (LiveKit worker)

## Design Principles

- Backend API and agent worker are deployed separately.
- Secrets are always read from Secret Manager.
- Deployment scripts must not create or modify secrets.
- Runtime updates use `--update-env-vars` and `--update-secrets` (not `--set-*`).

## Prerequisites

- `gcloud` installed and authenticated
- Cloud Build, Cloud Run, Artifact Registry, and Secret Manager APIs enabled
- Existing Artifact Registry repo (default `woka-repo`)
- Required Secret Manager secrets already created

Required secrets:

- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `GROQ_API_KEY`
- `DEEPGRAM_API_KEY`
- `SUPABASE_KEY`

Optional secrets:

- `OPENAI_API_KEY`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

## Deploy Backend + Frontend

From repo root:

```bash
chmod +x scripts/gcp/deploy.sh
PROJECT_ID=<your-project-id> REGION=asia-south1 REPO=woka-repo ./scripts/gcp/deploy.sh
```

What it does:

1. Validates required secrets exist
2. Builds backend image (`cloudbuild.backend.yaml`)
3. Deploys `woka-backend`
4. Resolves backend URL
5. Builds frontend image with backend URL (`cloudbuild.frontend.yaml`)
6. Deploys `woka-frontend`

## Deploy Agent Only

Use this when only agent code changed:

```bash
gcloud builds submit --config=cloudbuild.agent.yaml \
  --substitutions=_REGION=asia-south1,_REPO=woka-repo,_TAG=latest

PROJECT_ID=<your-project-id> REGION=asia-south1 REPO=woka-repo TAG=latest \
  ./scripts/gcp/deploy-agent.sh
```

Agent deploy behavior:

- verifies required secrets exist
- includes optional secrets only if present
- reads non-secret config from root `.env`
- pushes non-secret config via `--update-env-vars`
- forces `LIVEKIT_URL` to production LiveKit Cloud URL
- deploys with cost profile:
  - `--min-instances=0`
  - `--memory=1Gi`
  - `--cpu=1`
  - `--no-cpu-throttling`

## Verify Deployment

```bash
gcloud run services list --region=asia-south1
gcloud run services describe woka-agent --region=asia-south1
gcloud run services logs read woka-agent --region=asia-south1 --limit=100
```

## Common Pitfalls

- Using `--set-env-vars` or `--set-secrets` replaces existing config.
- Localhost values in `.env` can break cloud runtime if not overridden.
- Missing `SUPABASE_*` env/secrets disables session summary persistence.


