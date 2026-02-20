---
name: Voice Wellness Coach Test & Build Plan
overview: Create comprehensive test plan and test cases, then build the AI Voice Wellness Coach application with React frontend, Python Pipecat backend, Docker infrastructure, and full testing suite.
todos: []
---

# Voice Wellness Coach - Test Plan & Build Implementation

## Test Plan Overview

### Test Strategy

- **Unit Tests**: Backend services (pytest), Frontend components (Jest)
- **Integration Tests**: API endpoints, WebSocket connections, provider integrations (pytest)
- **E2E Tests**: Full conversation flows, audio streaming, exercises (Cypress)
- **Performance Tests**: Latency measurements (STT→LLM→TTS pipeline)
- **Security Tests**: Auth, TLS, input validation
- **Safety Tests**: Content moderation, crisis handling, disclaimers

### Test Cases by Category

#### 1. Unit Tests - Backend (pytest)

**SessionGateway Tests**
- Token validation (JWT/OAuth)
- WebSocket connection establishment
- TLS enforcement
- Session state initialization

**AudioPipeline Tests**
- STT node streaming partials handling
- DialogueManager prompt building with wellness persona
- Context management (20-turn window)
- Structured state updates (mood/stress/energy)
- TTS node streaming
- Exercise script selection

**ProviderRouter Tests**
- Provider selection based on credits
- Priority/fallback logic
- Provider health checks
- Cost tracking

**StateStore Tests**
- In-memory state operations
- Redis integration (if configured)
- Session state persistence
- State expiration/cleanup

**SessionSummaryService Tests**
- Summary generation from transcript
- Structured data extraction (mood scores, themes)
- Exercise usage tracking

**MetricsService Tests**
- Latency tracking per hop
- Token/audio usage counting
- Error rate calculation
- Prometheus export format

#### 2. Unit Tests - Frontend (Jest + React Testing Library)

**AudioCaptureModule Tests**
- MediaStream initialization
- Audio encoding (Opus/PCM)
- Streaming to WebSocket
- Error handling (mic permissions, connection loss)

**AudioPlayerModule Tests**
- Streaming audio playback
- Jitter buffer management
- Playback state management
- Audio format handling

**SessionUI Tests**
- Component rendering
- State indicators (Listening/Thinking/Speaking)
- Timer display
- Disclaimer visibility
- Exercise UI components
- Text recap display

#### 3. Integration Tests (pytest)

**WebSocket Connection Flow**
- Connection establishment
- Audio stream routing
- Message serialization/deserialization
- Connection cleanup on disconnect

**End-to-End Audio Pipeline**
- STT → DialogueManager → TTS flow
- Provider integration (OpenAI Realtime, etc.)
- State persistence across turns
- Error propagation and recovery

**Provider Integration**
- STT provider streaming
- LLM provider token streaming
- TTS provider audio streaming
- Fallback provider switching

#### 4. E2E Tests (Cypress)

**Happy Path - Daily Check-in**
1. User opens app
2. Sees disclaimer, accepts
3. Clicks "Start Session"
4. Speaks for 30-60 seconds
5. Receives empathetic response
6. System proposes exercise
7. User completes exercise
8. Session summary generated

**On-Demand Support Flow**
1. User starts session
2. Speaks stress/vent
3. System mirrors feelings
4. Offers micro-exercise (2-5 min)
5. User completes exercise

**Latency Verification**
- Measure time from user pause to first audio
- Verify median < 700ms
- Verify P95 < 1.2s
- Track per-hop latencies

**Exercise Flows**
- Guided breathing exercise
- Thought reframing exercise
- Body scan exercise
- Verify script progression, timed pauses

**Error Handling**
- Network disconnection
- Provider failure
- Mic permission denial
- Browser compatibility

**Safety & Disclaimers**
- Disclaimer visible and spoken
- Crisis keyword detection → resource routing
- Content moderation checks

#### 5. Performance Tests

**Latency Benchmarks**
- STT partial latency (80-150ms target)
- LLM first token latency (100-200ms target)
- TTS first chunk latency (80-150ms target)
- End-to-end latency (500-700ms median target)

**Concurrent Sessions**
- Load test with multiple simultaneous users
- State isolation verification
- Resource usage monitoring

#### 6. Security Tests

- JWT/OAuth token validation
- TLS/WSS enforcement
- Input sanitization
- XSS prevention
- CSRF protection (if applicable)
- Session hijacking prevention

---

## Build Plan

### Project Structure

```javascript
voice-wellness-coach/
├── backend/
│   ├── src/
│   │   ├── gateway/
│   │   │   └── session_gateway.py
│   │   ├── pipeline/
│   │   │   ├── audio_pipeline.py
│   │   │   ├── stt_node.py
│   │   │   ├── dialogue_manager.py
│   │   │   └── tts_node.py
│   │   ├── providers/
│   │   │   ├── router.py
│   │   │   ├── llm_provider.py
│   │   │   ├── stt_provider.py
│   │   │   └── tts_provider.py
│   │   ├── services/
│   │   │   ├── state_store.py
│   │   │   ├── session_summary_service.py
│   │   │   ├── metrics_service.py
│   │   │   └── user_service.py
│   │   ├── exercises/
│   │   │   ├── breathing.py
│   │   │   ├── reframing.py
│   │   │   └── body_scan.py
│   │   └── main.py
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── SessionUI.tsx
│   │   │   ├── AudioCapture.tsx
│   │   │   ├── AudioPlayer.tsx
│   │   │   └── ExerciseView.tsx
│   │   ├── modules/
│   │   │   ├── audioCapture.ts
│   │   │   ├── audioPlayer.ts
│   │   │   └── sessionClient.ts
│   │   ├── hooks/
│   │   │   └── useVoiceSession.ts
│   │   ├── types/
│   │   │   └── session.ts
│   │   └── App.tsx
│   ├── tests/
│   │   ├── unit/
│   │   └── e2e/
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .github/workflows/
│   └── ci.yml
├── README.md
└── .env.example
```

### Implementation Steps

#### Phase 1: Backend Foundation

1. **Project Setup**
   - Initialize Python project with requirements.txt
   - Add Pipecat, FastAPI/websockets, pytest dependencies
   - Create project structure

2. **Core Services**
   - Implement StateStore (in-memory + Redis optional)
   - Implement MetricsService with Prometheus export
   - Implement UserService (basic auth/preferences)

3. **Provider Abstraction**
   - Create provider interfaces (LLMProvider, STTProvider, TTSProvider)
   - Implement ProviderRouter with priority/fallback
   - Add OpenAI Realtime provider implementation

4. **Audio Pipeline**
   - Implement STT node with streaming
   - Implement DialogueManager with wellness persona
   - Implement TTS node with streaming
   - Wire together in AudioPipeline

5. **Session Gateway**
   - WebSocket server setup
   - Auth middleware (JWT)
   - Route audio streams to pipeline
   - Handle session lifecycle

6. **Exercises**
   - Implement 2-3 exercises (breathing, reframing, body scan)
   - Exercise script structure
   - Integration with DialogueManager

7. **Session Summary Service**
   - Transcript summarization
   - Structured data extraction
   - Storage layer

#### Phase 2: Frontend Foundation

1. **Project Setup**
   - Create React + TypeScript project
   - Setup build tooling (Vite/Webpack)
   - Add Jest, React Testing Library, Cypress

2. **Audio Modules**
   - AudioCaptureModule (MediaStream, encoding, WebSocket)
   - AudioPlayerModule (streaming playback, jitter buffer)
   - SessionClient (WebSocket wrapper)

3. **UI Components**
   - SessionUI (main container)
   - State indicators
   - Disclaimer component
   - Exercise components
   - Timer display

4. **Integration**
   - Connect audio modules to backend
   - Session state management (React hooks)
   - Error handling UI

#### Phase 3: Testing Infrastructure

1. **Backend Tests**
   - Unit tests for all services
   - Integration tests for pipeline
   - Provider mock fixtures

2. **Frontend Tests**
   - Component unit tests
   - Audio module tests (with mocked MediaStream)
   - Cypress E2E setup

3. **Performance Tests**
   - Latency measurement utilities
   - Load testing scripts

#### Phase 4: DevOps & Deployment

1. **Docker Setup**
   - Backend Dockerfile
   - Frontend Dockerfile
   - Docker Compose for local development
   - Health checks

2. **CI/CD**
   - GitHub Actions workflow
   - Test execution
   - Docker image building

3. **Cloud Deployment Configs**
   - Kubernetes manifests (optional)
   - Cloud provider configs
   - Environment variable management

### Key Implementation Details

**Backend (Python)**
- Framework: FastAPI with WebSocket support or native asyncio
- Pipecat integration for audio pipeline
- Redis optional for StateStore
- Prometheus metrics endpoint

**Frontend (React + TypeScript)**
- Audio encoding: Web Audio API or Opus.js
- WebSocket client with reconnection logic
- State management: React Context or Zustand
- Audio playback: Howler.js or native AudioContext

**Latency Optimization**
- Streaming at all stages
- Prompt optimization (compact, ~20 turns)
- Client-side VAD for pause detection
- Small jitter buffers (60-80ms)

**Safety Implementation**
- Safety prompts in DialogueManager
- Crisis keyword detection → resource routing
- Content filtering (optional external service)
- Visible disclaimer + spoken onboarding

### Configuration

**Environment Variables**
- Provider API keys (OpenAI, Anthropic, etc.)
- Redis connection (optional)
- Auth secrets (JWT)
- Metrics endpoint config

**Provider Priority Order**
- Configured in ProviderRouter
- Based on free credits remaining
- Fallback chain: OpenAI → Anthropic → Google

---

## Deliverables

1. Complete test plan document with all test cases
2. Working backend with Pipecat pipeline
3. Working frontend React app
4. Full test suite (unit, integration, E2E)
5. Docker Compose setup









