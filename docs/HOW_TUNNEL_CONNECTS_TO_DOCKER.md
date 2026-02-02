# How Cloudflare Tunnel Connects to Docker Containers

## The Connection Flow

```
Internet User
    ↓
Cloudflare Edge (your domain)
    ↓
Cloudflare Tunnel (cloudflared container)
    ↓
Docker Network (woka-bot-network)
    ↓
Your Services (agent:8000, frontend:80)
```

## Key Concepts

### 1. **Docker Network (Automatic)**

All services in `docker-compose.yml` are on the **same Docker network** (`woka-bot-network`). This means:

- Containers can talk to each other using **service names** as hostnames
- `agent` service is reachable at `http://agent:8000` from other containers
- `frontend` service is reachable at `http://frontend:80` from other containers
- **You don't need to expose ports to your host machine** - the tunnel container can reach them directly

### 2. **Tunnel Container**

The `tunnel` service runs `cloudflared` which:
- Connects to Cloudflare's servers using your **tunnel token**
- Receives configuration from Cloudflare dashboard (what routes to create)
- Forwards traffic from Cloudflare → your Docker services

### 3. **Cloudflare Dashboard Configuration**

In the Cloudflare dashboard, you tell the tunnel:
- "When someone visits `api.yourdomain.com`, forward to `http://agent:8000`"
- "When someone visits `app.yourdomain.com`, forward to `http://frontend:80`"

The tunnel container then routes traffic accordingly.

## Step-by-Step: What You Need to Configure

### Step 1: Docker Compose (Already Done ✅)

Your `docker-compose.yml` already sets this up:
- All services are on the same network
- Tunnel depends on agent and frontend
- Services can reach each other by name

**No changes needed here!**

### Step 2: Cloudflare Dashboard (You Need to Do This)

1. **Go to Cloudflare Dashboard** → Zero Trust → Networks → Tunnels
2. **Click on your tunnel** → **Configure**
3. **Add Public Hostname** for backend:
   - **Subdomain**: `api` (or whatever you want)
   - **Domain**: `yourdomain.com`
   - **Service**: `http://agent:8000` ← **This is the Docker service name!**
   - Click **Save hostname**

4. **Add Public Hostname** for frontend:
   - **Subdomain**: `app` (or whatever you want)
   - **Domain**: `yourdomain.com`
   - **Service**: `http://frontend:80` ← **This is the Docker service name!**
   - Click **Save hostname**

### Step 3: Tunnel Token (Already in docker-compose.yml ✅)

The tunnel container uses `CLOUDFLARE_TUNNEL_TOKEN` from your `.env` file to authenticate.

**Make sure your `.env` has:**
```bash
CLOUDFLARE_TUNNEL_TOKEN=your-token-from-cloudflare-dashboard
```

## Important: Service Names Must Match

In Cloudflare dashboard, when you set:
- **Service**: `http://agent:8000`

This `agent` must match the **service name** in your `docker-compose.yml`:

```yaml
services:
  agent:  # ← This name!
    ...
```

Same for frontend:
- Cloudflare: `http://frontend:80`
- docker-compose: `services: frontend:` ← Must match!

## How It Works When Running

1. **You run**: `docker-compose up -d`

2. **Docker creates**:
   - `agent` container on port 8000 (inside Docker network)
   - `frontend` container on port 80 (inside Docker network)
   - `tunnel` container that connects to Cloudflare

3. **Tunnel container**:
   - Reads your token from `.env`
   - Connects to Cloudflare servers
   - Downloads route configuration from Cloudflare dashboard
   - Sees: "route `api.yourdomain.com` → `http://agent:8000`"
   - Can reach `agent` because they're on the same Docker network

4. **When user visits `https://api.yourdomain.com`**:
   - Cloudflare receives the request
   - Forwards it through the tunnel to your `tunnel` container
   - Tunnel container forwards to `http://agent:8000` (Docker internal network)
   - Your FastAPI responds
   - Response goes back through tunnel → Cloudflare → user

## Troubleshooting

### Tunnel can't reach agent/frontend

**Check service names match:**
```bash
# List running containers
docker-compose ps

# Check if services are on same network
docker network inspect woka-bot-network
```

**Verify service names in Cloudflare dashboard match docker-compose.yml:**
- Cloudflare Service: `http://agent:8000` ✅
- docker-compose service: `agent:` ✅

### Tunnel connects but routes don't work

**Check Cloudflare dashboard:**
- Routes are configured correctly
- Service URLs use Docker service names (not `localhost` or `127.0.0.1`)
- Subdomains are correct

**Check tunnel logs:**
```bash
docker-compose logs tunnel
```

You should see routes being registered:
```
Registered tunnel connection connIndex=0
```

## Summary

**You only need to configure in Cloudflare Dashboard:**
- Create tunnel (get token)
- Add routes pointing to Docker service names (`http://agent:8000`, `http://frontend:80`)

**Docker Compose handles everything else automatically:**
- Network creation
- Service discovery
- Container communication

The tunnel container acts as a bridge between Cloudflare and your Docker services!

