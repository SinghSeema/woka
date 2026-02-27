---
name: Production-ready Voice AI Bot
overview: Transform the working pipecatBot into a production-ready application with proper structure, documentation, modern UI, and comprehensive improvements for both cloud and on-premise deployment.
todos:
  - id: restructure
    content: "Restructure project: create backend/, frontend/, and docs/ directories with proper file organization"
    status: completed
  - id: fix-imports
    content: Fix missing LLMMessagesFrame import and update all import paths after restructuring
    status: completed
    dependencies:
      - restructure
  - id: config-management
    content: Create configuration management system with Pydantic Settings and environment-based configs
    status: completed
    dependencies:
      - restructure
  - id: security
    content: "Implement security improvements: CORS configuration, rate limiting, error handling"
    status: completed
    dependencies:
      - restructure
      - config-management
  - id: logging
    content: Add structured logging and monitoring setup for backend and bot
    status: completed
    dependencies:
      - restructure
  - id: backend-refactor
    content: Refactor backend API with proper error handling, validation, and health checks
    status: completed
    dependencies:
      - restructure
      - config-management
      - logging
  - id: bot-refactor
    content: Refactor bot code with better error handling, service wrappers, and event handlers
    status: completed
    dependencies:
      - restructure
      - config-management
  - id: tailwind-setup
    content: Install and configure Tailwind CSS in frontend with design system
    status: completed
    dependencies:
      - restructure
  - id: ui-components
    content: "Create modern UI components with Tailwind: LandingPage, RoomView, and reusable components"
    status: completed
    dependencies:
      - tailwind-setup
  - id: frontend-refactor
    content: Refactor frontend with error boundaries, loading states, and improved UX
    status: completed
    dependencies:
      - ui-components
  - id: prd
    content: Create Product Requirements Document (PRD) with user personas, features, and requirements
    status: completed
  - id: hld
    content: Create High-Level Design document with system architecture and deployment diagrams
    status: completed
  - id: lld
    content: Create Low-Level Design document with component details and sequence diagrams
    status: completed
  - id: api-docs
    content: Create API documentation with OpenAPI/Swagger specifications
    status: completed
    dependencies:
      - backend-refactor
  - id: docker-setup
    content: Create Dockerfiles and docker-compose.yml for development and production
    status: completed
    dependencies:
      - restructure
  - id: cursor-rules
    content: Create comprehensive .cursorrules file with coding standards and architecture patterns
    status: completed
  - id: gitignore-env
    content: Create .gitignore and .env.example files
    status: completed
  - id: readme
    content: Create comprehensive README with setup instructions and project overview
    status: completed
    dependencies:
      - docker-setup
---

# Production-Ready Voice AI Bot Transformation Plan

## Current State Analysis

The application is a working voice AI wellness coaching bot with:

- **Backend**: FastAPI server (`server.py`) for LiveKit token generation
- **Bot**: Pipecat-based voice agent (`bot.py`) using Groq LLM, Deepgram STT, Cartesia TTS
- **Frontend**: React app (`App.jsx`) with LiveKit components
- **Issues Found**:
  - Missing import (`LLMMessagesFrame` in `bot.py`)
  - Flat file structure (all files in root)
  - No error handling, logging, or monitoring
  - CORS wide open (`allow_origins=["*"]`)
  - Hardcoded URLs and configuration
  - Basic UI needs modernization
  - No documentation or tests
  - Missing `.gitignore`, environment variable management

## Proposed Structure

```javascript
pipecatBot/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app entry
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── routes/
│   │   │       ├── __init__.py
│   │   │       └── auth.py      # Token generation endpoints
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py        # Configuration management
│   │   │   ├── logging.py        # Logging setup
│   │   │   └── security.py       # Security middleware
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── exceptions.py    # Custom exceptions
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── main.py              # Bot entrypoint (refactored bot.py)
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── llm_service.py   # LLM service wrapper
│   │   │   ├── stt_service.py   # STT service wrapper
│   │   │   └── tts_service.py   # TTS service wrapper
│   │   └── handlers/
│   │       ├── __init__.py
│   │       └── events.py        # Event handlers
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_api.py
│   │   └── test_bot.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── VoiceAssistant.jsx
│   │   │   ├── LandingPage.jsx
│   │   │   ├── RoomView.jsx
│   │   │   └── ui/              # Reusable UI components
│   │   ├── hooks/
│   │   │   ├── useLiveKit.js
│   │   │   └── useErrorBoundary.js
│   │   ├── services/
│   │   │   └── api.js           # API client
│   │   ├── utils/
│   │   │   ├── constants.js
│   │   │   └── errorHandler.js
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css            # Tailwind imports
│   ├── public/
│   │   └── index.html
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
├── docs/
│   ├── PRD.md                   # Product Requirements Document
│   ├── HLD.md                   # High-Level Design
│   ├── LLD.md                   # Low-Level Design
│   ├── diagrams/                # Architecture diagrams
│   ├── API.md                   # API documentation
│   └── DEPLOYMENT.md            # Deployment guide
├── .cursorrules                 # Cursor AI rules
├── .gitignore
├── .env.example                 # Environment variable template
├── docker-compose.yml           # Local development setup
├── README.md
└── Makefile                     # Common commands
```

## Implementation Plan

### Phase 1: Project Restructuring & Foundation

1. **Restructure project directories**
   - Move backend files to `backend/` with proper Python package structure
   - Move frontend files to `frontend/src/` with component organization
   - Create `docs/` directory for documentation

2. **Fix immediate issues**
   - Add missing `LLMMessagesFrame` import in bot code
   - Fix import paths after restructuring
   - Add proper error handling

3. **Configuration management**
   - Create `backend/app/core/config.py` using Pydantic Settings
   - Environment-based configuration (dev/staging/prod)
   - Create `.env.example` with all required variables
   - Add validation for required environment variables

4. **Security improvements**
   - Replace wildcard CORS with configurable allowed origins
   - Add rate limiting middleware
   - Implement proper error responses (no stack traces in production)
   - Add request validation and sanitization

### Phase 2: Backend Production Readiness

1. **Logging & Monitoring**
   - Structured logging with Python `logging` module
   - Log levels configuration
   - Request/response logging middleware
   - Error tracking setup (optional: Sentry integration)

2. **Error handling**
   - Custom exception classes
   - Global exception handlers
   - Proper HTTP status codes
   - Error response formatting

3. **API improvements**
   - Input validation with Pydantic models
   - Response models
   - API versioning structure
   - Health check endpoint (`/health`)

4. **Bot improvements**
   - Better error handling in pipeline
   - Connection retry logic
   - Graceful shutdown handling
   - Resource cleanup

### Phase 3: Frontend Modernization

1. **Tailwind CSS integration**
   - Install and configure Tailwind CSS
   - Remove old CSS, migrate to Tailwind utility classes
   - Create design system with Tailwind config
   - Responsive design implementation

2. **Component refactoring**
   - Split `App.jsx` into smaller components
   - Create reusable UI components (Button, Card, Modal, etc.)
   - Implement loading states
   - Add error boundaries

3. **UX improvements**
   - Modern landing page with animations
   - Better room view with participant cards
   - Connection status indicators
   - Toast notifications for errors/success
   - Loading skeletons
   - Smooth transitions

4. **State management**
   - Add React Context for global state (if needed)
   - API client with error handling
   - Retry logic for failed requests

### Phase 4: Documentation

1. **PRD (Product Requirements Document)**
   - Product overview and goals
   - User personas and use cases
   - Feature requirements
   - Non-functional requirements
   - Success metrics

2. **HLD (High-Level Design)**
   - System architecture diagram
   - Component interactions
   - Technology stack
   - Deployment architecture
   - Data flow diagrams

3. **LLD (Low-Level Design)**
   - Detailed component designs
   - API specifications
   - Database schema (if applicable)
   - Sequence diagrams for key flows
   - Class/module diagrams

4. **Additional documentation**
   - API documentation (OpenAPI/Swagger)
   - Deployment guide
   - Development setup guide
   - Environment variables reference

### Phase 5: DevOps & Infrastructure

1. **Docker setup**
   - Multi-stage Dockerfiles for backend and frontend
   - Docker Compose for local development
   - Production-optimized images

2. **CI/CD preparation**
   - GitHub Actions workflow structure (or GitLab CI)
   - Linting and formatting checks
   - Test execution
   - Build and deployment scripts

3. **Environment management**
   - `.env.example` template
   - Environment-specific configs
   - Secrets management documentation

### Phase 6: Testing & Quality

1. **Backend tests**
   - Unit tests for API endpoints
   - Integration tests for bot pipeline
   - Mock external services

2. **Frontend tests**
   - Component tests (optional, can be added later)
   - E2E test structure (optional)

3. **Code quality**
   - Add linting (ruff for Python, ESLint for JS)
   - Code formatting (black, prettier)
   - Pre-commit hooks

### Phase 7: Cursor Rules

Create comprehensive `.cursorrules` file covering:

- Code style and conventions
- Architecture patterns
- File organization rules
- Testing requirements
- Documentation standards
- Security best practices

## Key Files to Create/Modify

### Backend

- `backend/app/main.py` - Refactored FastAPI app
- `backend/app/core/config.py` - Configuration management
- `backend/app/core/logging.py` - Logging setup
- `backend/app/api/routes/auth.py` - Token endpoint
- `backend/bot/main.py` - Refactored bot with proper structure
- `backend/bot/services/` - Service wrappers

### Frontend

- `frontend/src/components/VoiceAssistant.jsx` - Main component
- `frontend/src/components/LandingPage.jsx` - Modern landing page
- `frontend/src/components/RoomView.jsx` - Room interface
- `frontend/tailwind.config.js` - Tailwind configuration
- `frontend/src/index.css` - Tailwind imports

### Documentation

- `docs/PRD.md` - Product requirements
- `docs/HLD.md` - High-level design with diagrams
- `docs/LLD.md` - Low-level design with diagrams
- `docs/API.md` - API documentation
- `docs/DEPLOYMENT.md` - Deployment instructions

### Configuration

- `.cursorrules` - Cursor AI rules
- `.gitignore` - Git ignore patterns
- `.env.example` - Environment template
- `docker-compose.yml` - Local development
- `README.md` - Project overview

## Diagrams to Include

1. **System Architecture Diagram** (HLD)
   - Shows frontend, backend, bot, LiveKit, and external services
   - Data flow between components

2. **Sequence Diagram** (LLD)
   - User connection flow
   - Voice interaction flow
   - Error handling flow

3. **Deployment Architecture** (HLD)
   - Cloud deployment structure
   - On-premise deployment structure

4. **Component Diagram** (LLD)
   - Backend module structure
   - Frontend component hierarchy

## Success Criteria

- ✅ All files properly organized in production-ready structure
- ✅ Modern, responsive UI with Tailwind CSS
- ✅ Comprehensive error handling and logging
- ✅ Security best practices implemented
- ✅ Complete documentation (PRD, HLD, LLD)
- ✅ Docker setup for easy deployment
- ✅ CI/CD pipeline ready
- ✅ Code quality tools configured










