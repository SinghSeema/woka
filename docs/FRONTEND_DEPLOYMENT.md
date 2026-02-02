## Frontend Deployment (Browser Client)

Your `frontend/` app is a Vite/React SPA that connects to LiveKit and your API.

### 1. Configure environment variables

For Netlify/Vercel, set build-time env vars:

- `VITE_API_BASE_URL=https://your-backend.fly.dev`
- `VITE_LIVEKIT_URL=wss://your-livekit-cloud-url`

Update `frontend/src/utils/constants.js` or your config layer to read from
`import.meta.env.VITE_API_BASE_URL` and `VITE_LIVEKIT_URL`.

### 2. Build locally (optional sanity check)

```bash
cd frontend
npm run build
```

Ensure the build succeeds and `dist/` is created.

### 3. Deploy to Netlify or Vercel

- Connect your GitHub repository.
- Set the build command: `npm run build`
- Set the publish directory: `frontend/dist`
- Configure the env vars above in the provider UI.

After deployment, you should be able to open:

- `https://your-frontend-domain.com`

and have it talk to:

- `https://your-backend.fly.dev` (API)
- `wss://your-livekit-cloud-url` (LiveKit Cloud)


