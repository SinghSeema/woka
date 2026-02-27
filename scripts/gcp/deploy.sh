#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   PROJECT_ID=your-project REGION=asia-south1 REPO=woka-repo ./scripts/gcp/deploy.sh
#
# Required in .env for backend runtime:
# LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL, LIVEKIT_PUBLIC_URL,
# GROQ_API_KEY, DEEPGRAM_API_KEY

PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-asia-south1}"
REPO="${REPO:-woka-repo}"
BACKEND_SERVICE="${BACKEND_SERVICE:-woka-backend}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-woka-frontend}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d-%H%M%S)}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "PROJECT_ID is required"
  exit 1
fi

if [[ ! -f ".env" ]]; then
  echo ".env not found at repo root"
  exit 1
fi

gcloud config set project "${PROJECT_ID}"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com

if ! gcloud artifacts repositories describe "${REPO}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Woka container images"
fi

# Check if secret exists (don't create new ones during deployment)
check_secret() {
  local secret_name="$1"
  if ! gcloud secrets describe "${secret_name}" >/dev/null 2>&1; then
    echo "❌ ERROR: Secret '${secret_name}' not found in Secret Manager"
    echo "   Please create it first: gcloud secrets create ${secret_name} --replication-policy=automatic"
    echo "   Then add a version: echo 'your-value' | gcloud secrets versions add ${secret_name} --data-file=-"
    return 1
  fi
  return 0
}

# Update secret value only if secret already exists (for maintenance)
update_secret_if_exists() {
  local key="$1"
  local secret_name="$2"
  local value
  value="$(grep -E "^${key}=" .env | head -n1 | cut -d= -f2- || true)"
  if [[ -z "${value}" ]]; then
    echo "Skipping ${secret_name}: ${key} not found in .env"
    return
  fi

  if gcloud secrets describe "${secret_name}" >/dev/null 2>&1; then
    echo "Updating existing secret: ${secret_name}"
    printf "%s" "${value}" | gcloud secrets versions add "${secret_name}" --data-file=-
  else
    echo "⚠️  Secret '${secret_name}' does not exist. Skipping (use check_secret to verify)."
  fi
}

# Verify all required secrets exist (don't create during deployment)
echo "Verifying required secrets exist in Secret Manager..."
REQUIRED_SECRETS=("LIVEKIT_API_KEY" "LIVEKIT_API_SECRET" "GROQ_API_KEY" "DEEPGRAM_API_KEY" "SUPABASE_KEY")
for secret in "${REQUIRED_SECRETS[@]}"; do
  if ! check_secret "${secret}"; then
    exit 1
  fi
done
echo "✅ All required secrets exist"
echo ""

gcloud builds submit \
  --config=cloudbuild.backend.yaml \
  --substitutions=_REGION="${REGION}",_REPO="${REPO}",_TAG="${IMAGE_TAG}"

BACKEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/woka-backend:${IMAGE_TAG}"

# Deploy backend using --update flags to preserve existing configuration
gcloud run deploy "${BACKEND_SERVICE}" \
  --image="${BACKEND_IMAGE}" \
  --region="${REGION}" \
  --allow-unauthenticated \
  --port=8000 \
  --memory=2Gi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --update-env-vars=ENVIRONMENT=production,DEBUG=false,API_PORT=8000 \
  --update-env-vars=LIVEKIT_URL="$(grep -E '^LIVEKIT_URL=' .env | cut -d= -f2-)",LIVEKIT_PUBLIC_URL="$(grep -E '^LIVEKIT_PUBLIC_URL=' .env | cut -d= -f2-)" \
  --update-secrets=LIVEKIT_API_KEY=LIVEKIT_API_KEY:latest,LIVEKIT_API_SECRET=LIVEKIT_API_SECRET:latest,GROQ_API_KEY=GROQ_API_KEY:latest,DEEPGRAM_API_KEY=DEEPGRAM_API_KEY:latest

BACKEND_URL="$(gcloud run services describe "${BACKEND_SERVICE}" --region "${REGION}" --format='value(status.url)')"
echo "Backend URL: ${BACKEND_URL}"

gcloud builds submit \
  --config=cloudbuild.frontend.yaml \
  --substitutions=_REGION="${REGION}",_REPO="${REPO}",_API_BASE_URL="${BACKEND_URL}",_TAG="${IMAGE_TAG}"

FRONTEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/woka-frontend:${IMAGE_TAG}"

gcloud run deploy "${FRONTEND_SERVICE}" \
  --image="${FRONTEND_IMAGE}" \
  --region="${REGION}" \
  --allow-unauthenticated \
  --port=80 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=5

FRONTEND_URL="$(gcloud run services describe "${FRONTEND_SERVICE}" --region "${REGION}" --format='value(status.url)')"
echo "Frontend URL: ${FRONTEND_URL}"


