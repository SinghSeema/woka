# Woka Wellness Voice AI Assistant

A voice AI wellness coaching application that provides personalized guidance through real-time voice interactions.

## 🌿 Features

- **Real-time Voice Interaction** - Natural conversations with AI wellness coach
- **Personalized Coaching** - Tailored advice on nutrition, exercise, sleep, and stress management
- **Agentic Memory** - Bot remembers past sessions and provides continuity across conversations
- **Session History** - Automatic session summaries stored in Supabase (optional)
- **Modern UI** - Beautiful, responsive interface built with React and Tailwind CSS
- **Production Ready** - Comprehensive error handling, logging, and security
- **Scalable Architecture** - Supports cloud and on-premise deployment

## 🏗️ Architecture

- **Frontend:** React 18 + Vite + Tailwind CSS
- **Backend:** FastAPI (Python)
- **Bot:** Pipecat AI + LiveKit Agents
- **AI Services:** Groq (LLM), Deepgram (STT & TTS)
- **Real-time:** LiveKit (WebRTC)

## 📋 Prerequisites

- Python 3.10+
- Node.js 18+
- Docker & Docker Compose (optional)
- LiveKit Server (local or cloud)
- API Keys:
  - Groq API key (for LLM)
  - Deepgram API key (for STT & TTS)
  - LiveKit API key and secret
  - Supabase URL and key (optional, for session history)

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone <repository-url>
cd pipecatBot
```

### 2. Setup Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your API keys
nano .env
```

### 3. Start LiveKit Server

```bash
# Using Docker
docker run -d \
  --name livekit \
  -p 7880:7880 \
  -p 7881:7881 \
  -p 7882:7882/udp \
  -e LIVEKIT_KEYS="devkey: secret" \
  livekit/livekit-server:latest
```
```bash
#try this if server is not reachable
    sudo docker run --rm \
    --network host \
    livekit/livekit-server \
    --dev
```

### 4. Start Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 5. Start Bot Worker

```bash
# In a separate terminal
cd backend
source venv/bin/activate
python -m bot.main dev
```

### 6. Start Frontend

```bash
# In another terminal
cd frontend
npm install
npm run dev
```

### 7. Access Application

- **Frontend:** http://localhost:5173
- **API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

## 🐳 Docker Deployment

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Manual Docker Build

```bash
# Build backend
docker build -t woka-backend -f backend/Dockerfile backend/

# Build frontend
docker build -t woka-frontend -f frontend/Dockerfile frontend/

# Run services
docker run -d --name woka-backend -p 8000:8000 --env-file .env woka-backend
docker run -d --name woka-frontend -p 80:80 woka-frontend
```

## 📁 Project Structure

```
pipecatBot/
├── backend/              # Backend API and bot
│   ├── app/             # FastAPI application
│   │   ├── api/         # API routes
│   │   ├── core/        # Core functionality
│   │   └── utils/       # Utilities
│   ├── bot/             # Bot worker
│   │   ├── services/    # AI service wrappers
│   │   └── handlers/    # Event handlers
│   └── tests/           # Tests
├── frontend/             # React frontend
│   ├── src/
│   │   ├── components/  # React components
│   │   ├── hooks/       # Custom hooks
│   │   ├── services/    # API clients
│   │   └── utils/       # Utilities
│   └── public/          # Static files
├── docs/                # Documentation
│   ├── PRD.md          # Product Requirements
│   ├── HLD.md          # High-Level Design
│   ├── LLD.md          # Low-Level Design
│   ├── API.md          # API Documentation
│   └── DEPLOYMENT.md    # Deployment Guide
└── docker-compose.yml   # Docker Compose config
```

## 🔧 Configuration

### Environment Variables

See `.env.example` for all available configuration options.

**Required:**
- `LIVEKIT_API_KEY` - LiveKit API key
- `LIVEKIT_API_SECRET` - LiveKit API secret
- `GROQ_API_KEY` - Groq API key (for LLM)
- `DEEPGRAM_API_KEY` - Deepgram API key (for STT & TTS)

**Optional:**
- `DEEPGRAM_TTS_VOICE` - Deepgram TTS voice (default: `aura-2-helena-en`)
- `SUPABASE_URL` - Supabase project URL (for session history)
- `SUPABASE_KEY` - Supabase API key (for session history)
- `SUPABASE_ENABLED` - Enable Supabase (default: `false`)

- `ENVIRONMENT` - Environment (development/staging/production)
- `DEBUG` - Debug mode
- `API_PORT` - API server port (default: 8000)
- `CORS_ORIGINS` - Allowed CORS origins
- `BOT_NAME` - Bot display name (default: `Woka`)
- `LLM_MODEL` - Groq LLM model (default: `llama-3.3-70b-versatile`)

## 📚 Documentation

- [Product Requirements Document (PRD)](docs/PRD.md)
- [High-Level Design (HLD)](docs/HLD.md)
- [Low-Level Design (LLD)](docs/LLD.md)
- [Context Management Rules](docs/CONTEXT_MANAGEMENT.md) - **Important**: Rules for managing LLM input context
- [Agentic Memory Guide](docs/AGENTIC_MEMORY.md)
- [API Documentation](docs/API.md)
- [Deployment Guide](docs/DEPLOYMENT.md)

## 🧪 Testing

### Backend Tests

```bash
cd backend
pytest tests/
```

### Frontend Tests

```bash
cd frontend
npm test
```

## 🔒 Security

- JWT token-based authentication
- CORS configuration
- Rate limiting
- Input validation
- Security headers
- No persistent storage of voice data

## 📊 Monitoring

### Health Checks

```bash
# API health
curl http://localhost:8000/health
```

### Logs

```bash
# Backend logs
tail -f logs/api.log

# Bot logs
tail -f logs/bot.log
```

## 🚀 Deployment

### Cloud Deployment

See [Deployment Guide](docs/DEPLOYMENT.md) for detailed instructions on:
- AWS deployment
- GCP deployment
- Azure deployment

### On-Premise Deployment

See [Deployment Guide](docs/DEPLOYMENT.md) for on-premise setup instructions.

## 🤝 Contributing

1. Follow the coding standards in `.cursorrules`
2. Write tests for new features
3. Update documentation
4. Submit pull requests

## 📝 License

[Add your license here]

## 📞 Support

For issues and questions:
- Check documentation in `docs/`
- Review logs
- Contact support team

## 🙏 Acknowledgments

- [LiveKit](https://livekit.io/) - Real-time communication
- [Pipecat AI](https://pipecat.ai/) - Voice AI framework
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [React](https://react.dev/) - UI framework
- [Tailwind CSS](https://tailwindcss.com/) - CSS framework

---

**Built with ❤️ for wellness and mindfulness**

