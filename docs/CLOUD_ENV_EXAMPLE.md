## Cloud Environment Variables (Production Example)

Use this as a checklist when configuring secrets on Fly.io (or any app host).
Do **not** commit real values; set them in the provider’s secrets UI/CLI.

```bash
# General
ENVIRONMENT=production
DEBUG=false

# API Server
API_HOST=0.0.0.0
API_PORT=8000

# CORS
CORS_ORIGINS=https://your-frontend-domain.com

# LiveKit Cloud
LIVEKIT_URL=wss://your-livekit-cloud-url
LIVEKIT_API_KEY=lk_cloud_api_key
LIVEKIT_API_SECRET=lk_cloud_api_secret

# Groq
GROQ_API_KEY=your_groq_api_key

# Deepgram (if used)
DEEPGRAM_API_KEY=your_deepgram_api_key
DEEPGRAM_TTS_VOICE=aura-2-helena-en

# Supabase
SUPABASE_URL=https://your-supabase-url.supabase.co
SUPABASE_KEY=your_supabase_service_or_anon_key
SUPABASE_ENABLED=true

# Langfuse
ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com

# Bot config
BOT_NAME=Woka
VAD_THRESHOLD=0.5
NUM_IDLE_PROCESSES=1
```


