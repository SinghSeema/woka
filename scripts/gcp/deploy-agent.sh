#!/usr/bin/env bash
set -euo pipefail

# Deploy agent service - ALWAYS uses existing Secret Manager secrets
# Never creates or modifies secrets - only references them
# Usage: PROJECT_ID=wellness-coach-1985 REGION=asia-south1 REPO=woka-repo TAG=latest ./scripts/gcp/deploy-agent.sh

PROJECT_ID="${PROJECT_ID:-wellness-coach-1985}"
REGION="${REGION:-asia-south1}"
REPO="${REPO:-woka-repo}"
TAG="${TAG:-latest}"
SERVICE_NAME="woka-agent"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "PROJECT_ID is required"
  exit 1
fi

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/woka-agent:${TAG}"

echo "🚀 Deploying agent service..."
echo "   Image: ${IMAGE}"
echo "   Service: ${SERVICE_NAME}"
echo "   Region: ${REGION}"
echo "   Using existing Secret Manager secrets (never creates new ones)"
echo ""

# Verify required secrets exist in Secret Manager (don't create them)
echo "Verifying secrets exist in Secret Manager..."
REQUIRED_SECRETS=("LIVEKIT_API_KEY" "LIVEKIT_API_SECRET" "GROQ_API_KEY" "DEEPGRAM_API_KEY" "SUPABASE_KEY")
OPTIONAL_SECRETS=("OPENAI_API_KEY" "LANGFUSE_PUBLIC_KEY" "LANGFUSE_SECRET_KEY")

for secret in "${REQUIRED_SECRETS[@]}"; do
  if ! gcloud secrets describe "${secret}" >/dev/null 2>&1; then
    echo "❌ ERROR: Secret '${secret}' not found in Secret Manager"
    echo "   Please create it first: gcloud secrets create ${secret} --replication-policy=automatic"
    exit 1
  fi
  echo "   ✅ ${secret} exists"
done

# Build secrets list for deployment (required + optional if they exist)
SECRETS_LIST=(
  "LIVEKIT_API_KEY=LIVEKIT_API_KEY:latest"
  "LIVEKIT_API_SECRET=LIVEKIT_API_SECRET:latest"
  "GROQ_API_KEY=GROQ_API_KEY:latest"
  "DEEPGRAM_API_KEY=DEEPGRAM_API_KEY:latest"
  "SUPABASE_KEY=SUPABASE_KEY:latest"
)

for secret in "${OPTIONAL_SECRETS[@]}"; do
  if gcloud secrets describe "${secret}" >/dev/null 2>&1; then
    echo "   ✅ ${secret} exists (optional, will be included)"
    SECRETS_LIST+=("${secret}=${secret}:latest")
  else
    echo "   ⚠️  ${secret} not found (optional, skipping)"
  fi
done

echo ""
echo "Loading configuration from .env file..."

# Extract non-sensitive configuration variables from .env file
# Excludes API keys and secrets that should be in Secret Manager
ENV_VARS_ARRAY=()

if [ -f .env ]; then
  # List of variables that should be in Secret Manager (exclude these)
  SECRET_VARS=(
    "LIVEKIT_API_KEY"
    "LIVEKIT_API_SECRET"
    "GROQ_API_KEY"
    "DEEPGRAM_API_KEY"
    "SUPABASE_KEY"
    "OPENAI_API_KEY"
    "LANGFUSE_PUBLIC_KEY"
    "LANGFUSE_SECRET_KEY"
    "DAILY_API_KEY"
    "CARTESIA_API_KEY"
    "CLOUDFLARE_TUNNEL_TOKEN"
    "VITE_API_BASE_URL"
    "VITE_LIVEKIT_URL"
  )

  # Read .env and extract configuration variables
  while IFS='=' read -r key value || [ -n "$key" ]; do
    # Trim whitespace from key
    key=$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    
    # Skip empty lines and comments
    [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
    
    # Skip if it's a secret variable
    is_secret=0
    for secret in "${SECRET_VARS[@]}"; do
      if [ "$key" = "$secret" ]; then
        is_secret=1
        break
      fi
    done
    
    if [ $is_secret -eq 0 ]; then
      # Remove quotes and comments from value, trim whitespace
      value=$(echo "$value" | sed -e 's/^[[:space:]]*"//' -e 's/"[[:space:]]*$//' -e "s/^[[:space:]]*'//" -e "s/'[[:space:]]*$//" -e 's/[[:space:]]*#.*$//' -e 's/[[:space:]]*$//')
      # Only add if both key and value are non-empty
      if [[ -n "$key" && -n "$value" ]]; then
        ENV_VARS_ARRAY+=("${key}=${value}")
      fi
    fi
  done < <(grep -E "^[A-Z_]+=" .env || true)
fi

# Override LIVEKIT_URL with production URL (not localhost)
# Remove any existing LIVEKIT_URL from array and add production one
NEW_ENV_VARS_ARRAY=()
for var in "${ENV_VARS_ARRAY[@]}"; do
  if [[ ! "$var" =~ ^LIVEKIT_URL= ]]; then
    NEW_ENV_VARS_ARRAY+=("$var")
  fi
done
NEW_ENV_VARS_ARRAY+=("LIVEKIT_URL=wss://woka-qe4nlyjl.livekit.cloud")
ENV_VARS_ARRAY=("${NEW_ENV_VARS_ARRAY[@]}")

# Join array into comma-separated string (only non-empty entries)
ENV_VARS_STRING=$(IFS=','; echo "${ENV_VARS_ARRAY[*]}")

echo "   Loaded ${#ENV_VARS_ARRAY[@]} configuration variables from .env"
echo ""
echo "Deploying with existing secrets from Secret Manager..."

# Deploy with update flags to preserve existing configuration
# Uses --update-secrets to reference existing secrets (never creates new ones)
# Uses --update-env-vars to add/update env vars without removing existing ones
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --platform=managed \
  --no-cpu-throttling \
  --min-instances=0 \
  --memory=1Gi \
  --cpu=1 \
  --update-env-vars="${ENV_VARS_STRING}" \
  --update-secrets="$(IFS=','; echo "${SECRETS_LIST[*]}")" \
  --quiet

echo ""
echo "✅ Agent service deployed successfully!"
echo "   URL: $(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format='value(status.url)')"
echo ""
echo "📝 Note: All secrets are referenced from Secret Manager (not created or modified)"

