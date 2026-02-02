# Cloudflare Quick Tunnel Setup

This setup uses Cloudflare's quick tunnel feature (no custom domain required).

## Current Tunnel URLs

Get the current URLs by running:
```bash
# Frontend URL
docker-compose logs tunnel-frontend | grep "https://" | tail -1

# Backend API URL  
docker-compose logs tunnel-backend | grep "https://" | tail -1

# LiveKit URL
docker-compose logs tunnel-livekit | grep "https://" | tail -1
```

## After Restarting Tunnels

If you restart the tunnels, the URLs will change. Update these:

1. **Update Frontend** (rebuild with new backend URL):
   ```bash
   # Get new backend URL
   BACKEND_URL=$(docker-compose logs tunnel-backend | grep "https://" | tail -1 | awk '{print $NF}')
   
   # Rebuild frontend
   docker-compose build --build-arg VITE_API_BASE_URL=$BACKEND_URL frontend
   docker-compose up -d frontend
   ```

2. **Update Backend** (set new LiveKit URL):
   ```bash
   # Get new LiveKit URL (convert http to wss)
   LIVEKIT_URL=$(docker-compose logs tunnel-livekit | grep "https://" | tail -1 | awk '{print $NF}' | sed 's|https://|wss://|')
   
   # Update .env or docker-compose.yml with LIVEKIT_PUBLIC_URL
   # Then restart agent
   docker-compose restart agent
   ```

## Quick Access

- **Frontend**: Check logs for current URL
- **Backend API Docs**: `{BACKEND_URL}/docs`
- **Health Check**: `{BACKEND_URL}/health`

## Notes

- Quick tunnels are temporary and URLs change on restart
- For production, use a named tunnel with a custom domain
- These tunnels work without a Cloudflare account (free tier)
