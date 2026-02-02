## Deploying the Bot Backend on Fly.io

This assumes you have a working Dockerfile at the repo root and a LiveKit
Cloud project configured.

### 1. Install Fly CLI and log in

```bash
curl -L https://fly.io/install.sh | sh
fly auth login
```

### 2. Launch the app (one-time)

From the repo root:

```bash
fly launch --no-deploy
```

- When prompted:
  - App name: choose something like `woka-bot-backend`.
  - Select a close region.
  - Answer **yes** to using the existing Dockerfile.
  - Skip Postgres/Redis add-ons for now.

This will create a `fly.toml` file; commit it to your repo.

### 3. Configure secrets (production env)

Use `docs/CLOUD_ENV_EXAMPLE.md` as a checklist.

Example:

```bash
fly secrets set \
  ENVIRONMENT=production \
  LIVEKIT_URL=wss://your-livekit-url \
  LIVEKIT_API_KEY=lk_cloud_api_key \
  LIVEKIT_API_SECRET=lk_cloud_api_secret \
  GROQ_API_KEY=your_groq_api_key \
  SUPABASE_URL=https://your-project.supabase.co \
  SUPABASE_KEY=your_supabase_key \
  SUPABASE_ENABLED=true \
  ENABLE_LANGFUSE=true \
  LANGFUSE_PUBLIC_KEY=your_langfuse_public_key \
  LANGFUSE_SECRET_KEY=your_langfuse_secret_key \
  LANGFUSE_HOST=https://cloud.langfuse.com
```

Add any other keys you use locally (`DEEPGRAM_API_KEY`, etc.).

### 4. Deploy

```bash
fly deploy
```

Watch logs:

```bash
fly logs
```

- Confirm:
  - FastAPI is listening on `0.0.0.0:8000`.
  - `bot.main` has connected to LiveKit Cloud.
  - Supabase and Langfuse initialization messages look healthy.

### 5. Frontend configuration

- Point your React/Vite frontend (deployed via Netlify/Vercel/etc.) at:
  - API base URL: `https://<your-fly-app>.fly.dev`
  - LiveKit URL: the same `LIVEKIT_URL` you set in secrets.
- Ensure CORS in your backend `.env`/secrets (`CORS_ORIGINS`) includes the
  final frontend domain.


