# Woka — Voice Wellness Coach

A voice-first AI wellness coaching assistant. Users speak naturally; Woka listens, remembers past sessions, and coaches them on nutrition, sleep, exercise, and mindset — all in real time.

---

## Architecture

Production runs as **three independent Cloud Run services**:

| Service | Role | Image |
|---|---|---|
| `woka-frontend` | React UI (Vite + Nginx) | `cloudbuild.frontend.yaml` |
| `woka-backend` | FastAPI REST API | `cloudbuild.backend.yaml` |
| `woka-agent` | LiveKit agent worker (bot brain) | `cloudbuild.agent.yaml` |

Separating the agent from the API means worker crashes don't affect the API, and each service scales independently.

```
User browser
    │  WebRTC audio
    ▼
LiveKit Cloud ──────────────────────► woka-agent (Cloud Run)
    │                                      │
    │  REST (token, room)                  │ STT → LLM → TTS
    ▼                                      │
woka-backend (Cloud Run)             Deepgram / Groq
    │
    ▼
woka-frontend (Cloud Run)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, Tailwind CSS |
| Backend API | FastAPI (Python 3.10) |
| Agent framework | Pipecat + LiveKit Agents SDK |
| LLM | Groq (llama-3.1-8b-instant) |
| Speech-to-Text | Deepgram Nova-2 |
| Text-to-Speech | Deepgram Aura |
| Real-time transport | LiveKit Cloud |
| Session memory | Supabase (Postgres + pgvector) |
| Observability | Langfuse |

---

## Key Bot Features

- **Backchannel filtering** — short acknowledgments like "ok" and "yeah" are silently dropped so they don't start a new LLM turn or cause awkward silence-then-restart
- **Noise-resistant VAD** — tuned Silero Voice Activity Detection ignores background conversations and brief audio bursts
- **Session memory** — past sessions are embedded and retrieved semantically; the bot recalls commitments from previous conversations
- **Voice-clean responses** — LLM is instructed to use plain speech (no markdown, no asterisks, natural numbered lists)
- **Memory compression** — long conversations are summarised incrementally so the context window stays within token limits
- **Multi-language input** — Deepgram supports Hindi, Tamil, Telugu and others; the bot always responds in English

---

## Local Development

### Prerequisites

- Python 3.10+
- Node.js 18+
- A LiveKit server (local Docker or LiveKit Cloud)

### 1. Install dependencies

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 2. Configure environment

Copy the example and fill in your keys. **Never commit `.env`.**

```bash
cp .env.example .env   # or create from scratch
```

Minimum required variables:

```env
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=your_livekit_key
LIVEKIT_API_SECRET=your_livekit_secret
GROQ_API_KEY=your_groq_key
DEEPGRAM_API_KEY=your_deepgram_key
```

Optional — enables session memory:

```env
SUPABASE_ENABLED=true
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_service_key
```

Optional — enables observability:

```env
ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

### 3. Start LiveKit locally

```bash
docker run --rm --network host livekit/livekit-server --dev
```

### 4. Start all three services (three terminals)

```bash
# Terminal 1 — Backend API
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Agent worker
cd backend
source .venv/bin/activate
python -m bot.main dev

# Terminal 3 — Frontend
cd frontend
npm run dev
```

Open `http://localhost:5173`.  API docs at `http://localhost:8000/docs`.

---

## GCP Deployment

All secrets are stored in **GCP Secret Manager** — they are never written into environment variables or image layers.

### First-time setup (secrets)

Create each secret once before deploying:

```bash
echo "your-value" | gcloud secrets create LIVEKIT_API_KEY --data-file=-
echo "your-value" | gcloud secrets create LIVEKIT_API_SECRET --data-file=-
echo "your-value" | gcloud secrets create GROQ_API_KEY --data-file=-
echo "your-value" | gcloud secrets create DEEPGRAM_API_KEY --data-file=-
echo "your-value" | gcloud secrets create SUPABASE_KEY --data-file=-
# Optional
echo "your-value" | gcloud secrets create LANGFUSE_PUBLIC_KEY --data-file=-
echo "your-value" | gcloud secrets create LANGFUSE_SECRET_KEY --data-file=-
```

### Deploy backend + frontend

```bash
chmod +x scripts/gcp/deploy.sh
PROJECT_ID=your-project REGION=asia-south1 REPO=woka-repo ./scripts/gcp/deploy.sh
```

### Deploy agent only (most common)

```bash
# Build image
gcloud builds submit \
  --config=cloudbuild.agent.yaml \
  --substitutions=_REGION=asia-south1,_REPO=woka-repo,_TAG=$(date +%Y%m%d-%H%M%S)

# Deploy to Cloud Run (replace TAG with the value printed above)
gcloud run deploy woka-agent \
  --image=asia-south1-docker.pkg.dev/YOUR_PROJECT/woka-repo/woka-agent:TAG \
  --region=asia-south1
```

### Tuning VAD without rebuilding

VAD settings can be updated instantly via env vars — no image rebuild needed:

```bash
gcloud run services update woka-agent \
  --region=asia-south1 \
  --update-env-vars="VAD_CONFIDENCE=0.88,VAD_START_SECS=0.6,VAD_MIN_WORDS_INTERRUPT=2"
```

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `BOT_NAME` | `Woka` | Bot display name |
| `VAD_CONFIDENCE` | `0.88` | Silero VAD speech confidence threshold (0–1) |
| `VAD_START_SECS` | `0.6` | Seconds of sustained speech before triggering |
| `VAD_STOP_SECS` | `0.8` | Seconds of silence before speech ends |
| `VAD_MIN_WORDS_INTERRUPT` | `2` | Minimum words to interrupt the bot mid-speech |
| `SUPABASE_ENABLED` | `false` | Enable session memory persistence |
| `MAX_PAST_SESSIONS` | `1` | Past sessions injected into context at startup |
| `ENABLE_SEMANTIC_SEARCH` | `true` | Use embeddings for past context retrieval |
| `ENABLE_LANGFUSE` | `false` | Send metrics to Langfuse |
| `SESSION_LANGUAGE` | `en` | Default session language (BCP-47) |
| `DEEPGRAM_STT_MODEL` | `nova-2` | Deepgram STT model |

---

## Repository Structure

```
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routes (auth, rooms)
│   │   └── core/         # Config, logging, observability
│   └── bot/
│       ├── main.py       # Agent entrypoint + pipeline assembly
│       ├── handlers/     # LiveKit event handlers (session save, memory)
│       └── services/     # STT, TTS, LLM, memory, VAD, filters
├── frontend/
│   └── src/
│       ├── components/   # React UI components
│       └── services/     # API client
├── scripts/
│   └── gcp/              # Deploy scripts
├── docs/                 # Architecture and debugging notes
├── Dockerfile            # Backend API image
├── Dockerfile.agent      # Agent worker image
├── cloudbuild.agent.yaml # Agent CI/CD config
└── cloudbuild.backend.yaml
```

---

## Security Notes

- `.env` is listed in `.gitignore` and must never be committed
- GCP Secret Manager is the only place API keys are stored in production
- Deploy scripts read secrets by reference (`--update-secrets`), never by value
- No API keys or credentials appear anywhere in the codebase
