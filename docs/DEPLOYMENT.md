# Deployment Guide
## Woka Wellness Voice AI Assistant

**Version:** 1.0.0

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Local Development](#local-development)
4. [Docker Deployment](#docker-deployment)
5. [Cloud Deployment](#cloud-deployment)
6. [On-Premise Deployment](#on-premise-deployment)
7. [Configuration](#configuration)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software
- **Python:** 3.10 or higher
- **Node.js:** 18 or higher
- **Docker:** 20.10 or higher (for Docker deployment)
- **Docker Compose:** 2.0 or higher (for Docker Compose)

### Required Services
- **LiveKit Server:** Running instance (local or cloud)
- **API Keys:**
  - Groq API key (for LLM)
  - Deepgram API key (for STT & TTS)
  - LiveKit API key and secret
  - Supabase URL and key (optional, for session history)

---

## Environment Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd pipecatBot
```

### 2. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Frontend Setup

```bash
cd frontend
npm install
```

### 4. Environment Variables

Create `.env` file in project root:

```bash
# Application
ENVIRONMENT=development
DEBUG=true

# API Server
API_HOST=0.0.0.0
API_PORT=8000

# CORS
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# LiveKit
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
LIVEKIT_URL=ws://127.0.0.1:7880

# AI Services
GROQ_API_KEY=your_groq_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
DEEPGRAM_TTS_VOICE=aura-2-helena-en

# Session History (Optional)
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_ENABLED=true

# Bot Configuration
BOT_NAME=Woka
VAD_THRESHOLD=0.5
NUM_IDLE_PROCESSES=3

# Security
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60
```

---

## Local Development

### 1. Start LiveKit Server

```bash
# Using Docker
docker run -d \
  --name livekit \
  -p 7880:7880 \
  -p 7881:7881 \
  -p 7882:7882/udp \
  -e LIVEKIT_KEYS="devkey: secret" \
  livekit/livekit-server:latest

# Or download and run locally
# See: https://docs.livekit.io/home/self-hosting/deployment/
```

### 2. Start Backend API

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Start Bot Worker

```bash
cd backend
source venv/bin/activate
python -m bot.main
```

### 4. Start Frontend

```bash
cd frontend
npm run dev
```

### 5. Access Application

- **Frontend:** http://localhost:5173
- **API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

---

## Docker Deployment

### 1. Build Images

```bash
# Build backend
docker build -t woka-backend -f backend/Dockerfile backend/

# Build frontend
docker build -t woka-frontend -f frontend/Dockerfile frontend/
```

### 2. Docker Compose

Use `docker-compose.yml` for local development:

```bash
docker-compose up -d
```

### 3. Production Docker Compose

For production, use environment-specific compose file:

```bash
docker-compose -f docker-compose.prod.yml up -d
```

---

## Cloud Deployment

### AWS Deployment

#### 1. EC2 Setup

```bash
# Install dependencies
sudo apt update
sudo apt install -y python3.10 python3-pip nodejs npm docker.io

# Clone repository
git clone <repository-url>
cd pipecatBot

# Setup environment
cp .env.example .env
# Edit .env with production values

# Start services
docker-compose -f docker-compose.prod.yml up -d
```

#### 2. Load Balancer Configuration

- Create Application Load Balancer
- Configure health check: `/health`
- Add SSL certificate
- Route traffic to EC2 instances

#### 3. Auto Scaling

- Configure Auto Scaling Group
- Set min/max instances
- Use health checks for scaling

### GCP Deployment

#### 1. Cloud Run

```bash
# Build and push images
gcloud builds submit --tag gcr.io/PROJECT_ID/woka-backend
gcloud builds submit --tag gcr.io/PROJECT_ID/woka-frontend

# Deploy
gcloud run deploy woka-backend --image gcr.io/PROJECT_ID/woka-backend
gcloud run deploy woka-frontend --image gcr.io/PROJECT_ID/woka-frontend
```

#### 2. Cloud Load Balancing

- Create load balancer
- Configure backend services
- Add SSL certificates
- Set up health checks

### Azure Deployment

#### 1. Container Instances

```bash
# Build and push to Azure Container Registry
az acr build --registry REGISTRY_NAME --image woka-backend backend/
az acr build --registry REGISTRY_NAME --image woka-frontend frontend/

# Deploy
az container create \
  --resource-group RESOURCE_GROUP \
  --name woka-backend \
  --image REGISTRY_NAME.azurecr.io/woka-backend
```

---

## On-Premise Deployment

### 1. Server Requirements

- **CPU:** 4+ cores
- **RAM:** 8GB+ (16GB recommended)
- **Storage:** 50GB+ SSD
- **Network:** Stable internet connection

### 2. Installation Steps

```bash
# 1. Install system dependencies
sudo apt update
sudo apt install -y python3.10 python3-pip nodejs npm nginx docker.io

# 2. Clone repository
git clone <repository-url>
cd pipecatBot

# 3. Setup backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Setup frontend
cd ../frontend
npm install
npm run build

# 5. Configure nginx
sudo cp nginx.conf /etc/nginx/sites-available/woka
sudo ln -s /etc/nginx/sites-available/woka /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# 6. Setup systemd services
sudo cp backend/woka-api.service /etc/systemd/system/
sudo cp backend/woka-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable woka-api woka-bot
sudo systemctl start woka-api woka-bot
```

### 3. Nginx Configuration

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Frontend
    location / {
        root /path/to/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket (if needed)
    location /ws {
        proxy_pass http://localhost:7880;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## Configuration

### Environment Variables

See `.env.example` for all available configuration options.

### Production Settings

For production, set:

```bash
ENVIRONMENT=production
DEBUG=false
CORS_ORIGINS=https://your-domain.com
```

### Scaling

**API Servers:**
- Run multiple instances behind load balancer
- Use process manager (PM2, Gunicorn with multiple workers)

**Bot Workers:**
- Scale based on concurrent sessions
- Each worker handles multiple sessions
- Monitor worker load

**LiveKit:**
- Supports clustering
- Configure for high availability

---

## Troubleshooting

### Common Issues

#### 1. Connection Failed

**Symptoms:** Frontend cannot connect to API

**Solutions:**
- Check API server is running
- Verify CORS configuration
- Check firewall rules
- Verify API_BASE_URL in frontend

#### 2. Bot Not Joining Room

**Symptoms:** User connects but bot doesn't appear

**Solutions:**
- Check bot worker is running
- Verify LiveKit connection
- Check API keys are correct
- Review bot logs

#### 3. Audio Issues

**Symptoms:** No audio or poor quality

**Solutions:**
- Check browser permissions
- Verify WebRTC connectivity
- Check network latency
- Review service API quotas

#### 4. High Latency

**Symptoms:** Slow response times

**Solutions:**
- Optimize pipeline
- Increase bot worker processes
- Check service API response times
- Monitor network latency

### Logs

**Backend API:**
```bash
# View logs
tail -f logs/api.log

# Or if using systemd
journalctl -u woka-api -f
```

**Bot Worker:**
```bash
# View logs
tail -f logs/bot.log

# Or if using systemd
journalctl -u woka-bot -f
```

**Frontend:**
- Check browser console
- Check network tab for API calls

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Expected response
{
  "status": "healthy",
  "app": "Woka Wellness Voice Assistant",
  "version": "1.0.0",
  "environment": "production"
}
```

---

## Monitoring

### Metrics to Monitor

- API request rate
- Response times
- Error rates
- Active sessions
- Bot worker load
- Service API quotas

### Tools

- **Application:** Built-in health checks
- **Infrastructure:** Prometheus, Grafana
- **Logs:** ELK Stack, CloudWatch
- **APM:** New Relic, Datadog

---

## Security Checklist

- [ ] Environment variables secured
- [ ] CORS configured correctly
- [ ] Rate limiting enabled
- [ ] HTTPS/TLS enabled
- [ ] API keys rotated regularly
- [ ] Logs don't contain sensitive data
- [ ] Firewall rules configured
- [ ] Regular security updates

---

## Support

For issues and questions:
- Check documentation
- Review logs
- Contact support team

