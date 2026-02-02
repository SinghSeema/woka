# Cloudflare Tunnel Setup Guide

This guide shows you how to set up Cloudflare Tunnel to expose your bot backend publicly without opening ports on your router.

## Prerequisites

1. A Cloudflare account (free tier works)
2. A domain managed by Cloudflare (or you can use a free subdomain from Cloudflare)
3. Docker and Docker Compose installed

## Step 1: Create a Cloudflare Tunnel

1. **Log in to Cloudflare Dashboard**
   - Go to https://dash.cloudflare.com
   - Select your domain (or add one if you don't have one)

2. **Create a Tunnel**
   - Navigate to **Zero Trust** → **Networks** → **Tunnels**
   - Click **Create a tunnel**
   - Choose **Cloudflared** (not WARP)
   - Give it a name (e.g., `woka-bot-tunnel`)
   - Click **Save tunnel**

3. **Get the Tunnel Token**
   - After creating the tunnel, you'll see a **Token** field
   - Copy this token (it looks like a long string)
   - **Important**: This token is sensitive - keep it secret!

## Step 2: Configure the Tunnel Route

1. **In the Tunnel configuration page**, click **Configure** next to your tunnel
2. **Add Backend API Route**:
   - Click **Add a public hostname**
   - **Subdomain**: e.g., `api` or `woka-api`
   - **Domain**: Your Cloudflare domain
   - **Service**: `http://agent:8000` (this is the Docker service name)
   - Click **Save hostname**
   
   This routes `https://api.yourdomain.com` → your FastAPI backend on port 8000

3. **Add Frontend Route**:
   - Click **Add a public hostname** again
   - **Subdomain**: e.g., `app` or `woka` (or leave blank for root domain)
   - **Domain**: Your Cloudflare domain
   - **Service**: `http://frontend:80` (nginx serves on port 80 inside container)
   - Click **Save hostname**
   
   This routes `https://app.yourdomain.com` (or `https://yourdomain.com`) → your React frontend

## Step 3: Set Up Environment Variables

1. **Add the tunnel token to your `.env` file**:
   ```bash
   CLOUDFLARE_TUNNEL_TOKEN=your-tunnel-token-here
   ```

2. **Add frontend environment variables** (these are baked into the JS at build time):
   ```bash
   # Use your Cloudflare Tunnel URLs (replace with your actual subdomains)
   VITE_API_BASE_URL=https://api.yourdomain.com
   VITE_LIVEKIT_URL=wss://your-livekit-cloud-url
   ```

3. **Make sure all other required env vars are in `.env`**:
   - `LIVEKIT_URL`
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`
   - `GROQ_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - etc.

## Step 4: Start the Services

```bash
# Build and start both agent and tunnel
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Step 5: Verify It Works

1. **Check agent logs**:
   ```bash
   docker-compose logs agent
   ```
   You should see:
   - FastAPI starting on port 8000
   - Bot worker connecting to LiveKit
   - Supabase/Langfuse initialization

2. **Check tunnel logs**:
   ```bash
   docker-compose logs tunnel
   ```
   You should see:
   - Tunnel connecting to Cloudflare
   - Routes registered

3. **Test the public URLs**:
   - **Backend API**: Visit `https://api.yourdomain.com/docs`
     - You should see the FastAPI Swagger UI
   - **Frontend**: Visit `https://app.yourdomain.com` (or your configured subdomain)
     - You should see your React app
     - The app should be able to connect to the backend API

## Troubleshooting

### Tunnel won't connect
- Verify `CLOUDFLARE_TUNNEL_TOKEN` is correct in `.env`
- Check tunnel logs: `docker-compose logs tunnel`
- Ensure the tunnel is active in Cloudflare dashboard

### Agent not reachable via tunnel
- Verify the tunnel route points to `http://agent:8000` (not `localhost:8000`)
- Check agent logs: `docker-compose logs agent`
- Ensure agent container is healthy: `docker-compose ps`

### Frontend can't connect to backend
- Verify `VITE_API_BASE_URL` in your `.env` matches your Cloudflare Tunnel backend URL
- Rebuild the frontend container after changing env vars: `docker-compose build frontend && docker-compose up -d frontend`
- Make sure CORS is configured in your backend to allow your frontend domain
- Check browser console for CORS errors

## Security Notes

1. **Tunnel Token**: Never commit your `CLOUDFLARE_TUNNEL_TOKEN` to git
2. **Environment Variables**: Keep `.env` in `.gitignore`
3. **HTTPS**: Cloudflare Tunnel automatically provides HTTPS - no need to configure SSL certificates
4. **Access Control**: Consider adding Cloudflare Access rules if you want to restrict who can access your API

## Architecture Overview

Your `docker-compose.yml` now includes:

1. **`agent` service**: Backend (FastAPI + Bot Worker) on port 8000
2. **`frontend` service**: React frontend served by nginx on port 80 (mapped to host port 5173)
3. **`tunnel` service**: Cloudflare Tunnel that routes traffic to both services

Both services are accessible through Cloudflare Tunnel:
- Backend: `https://api.yourdomain.com`
- Frontend: `https://app.yourdomain.com`

