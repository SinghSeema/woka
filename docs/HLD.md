# High-Level Design (HLD)
## Woka Wellness Voice AI Assistant

**Version:** 1.0.0  
**Date:** 2024

---

## 1. System Overview

Woka Wellness is a real-time voice AI coaching application that enables users to have natural voice conversations with an AI wellness coach. The system uses WebRTC for real-time audio communication and integrates multiple AI services for speech processing and generation.

### 1.1 System Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        UI[React Frontend]
    end
    
    subgraph "API Layer"
        API[FastAPI Server]
    end
    
    subgraph "Real-time Layer"
        LK[LiveKit Server]
    end
    
    subgraph "Bot Layer"
        Bot[Pipecat Bot Worker]
    end
    
    subgraph "AI Services"
        STT[Deepgram STT]
        LLM[Groq LLM]
        TTS[Deepgram TTS]
    end
    
    UI -->|HTTPS| API
    UI -->|WebRTC| LK
    API -->|Token Generation| LK
    Bot -->|WebRTC| LK
    Bot -->|API Calls| STT
    Bot -->|API Calls| LLM
    Bot -->|API Calls| TTS
    
    style UI fill:#e1f5e1
    style API fill:#e1f5e1
    style LK fill:#fff4e1
    style Bot fill:#fff4e1
    style STT fill:#e1e5f5
    style LLM fill:#e1e5f5
    style TTS fill:#e1e5f5
```

---

## 2. Component Architecture

### 2.1 Frontend Components

```mermaid
graph LR
    App[App.jsx] --> VA[VoiceAssistant]
    VA -->|Not Connected| LP[LandingPage]
    VA -->|Connected| RV[RoomView]
    RV --> Stage[Stage Component]
    RV --> Controls[ControlBar]
    LP --> Button[Button UI]
    LP --> Card[Card UI]
    
    style App fill:#e1f5e1
    style VA fill:#e1f5e1
    style LP fill:#e1f5e1
    style RV fill:#e1f5e1
```

### 2.2 Backend Components

```mermaid
graph TB
    Main[main.py] --> Routes[API Routes]
    Main --> Config[Configuration]
    Main --> Security[Security Middleware]
    Routes --> Auth[Auth Routes]
    Config --> Settings[Pydantic Settings]
    Security --> CORS[CORS Middleware]
    Security --> RateLimit[Rate Limiting]
    
    style Main fill:#fff4e1
    style Routes fill:#fff4e1
    style Config fill:#fff4e1
    style Security fill:#fff4e1
```

### 2.3 Bot Components

```mermaid
graph TB
    Entry[Bot Entrypoint] --> Transport[LiveKit Transport]
    Entry --> Services[AI Services]
    Entry --> Pipeline[Processing Pipeline]
    Services --> STT[STT Service]
    Services --> LLM[LLM Service]
    Services --> TTS[TTS Service]
    Pipeline --> Handlers[Event Handlers]
    
    style Entry fill:#fff4e1
    style Transport fill:#fff4e1
    style Services fill:#fff4e1
    style Pipeline fill:#fff4e1
```

---

## 3. Data Flow

### 3.1 User Connection Flow

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant A as API Server
    participant L as LiveKit
    participant B as Bot
    
    U->>F: Enter name, click connect
    F->>A: GET /api/v1/auth/connect?user=name
    A->>A: Generate token
    A->>F: Return token, room_name, url
    F->>L: Connect with token
    L->>B: Notify participant joined
    B->>B: Initialize pipeline
    B->>L: Join room
    L->>F: Bot connected
    B->>U: Greeting message
```

### 3.2 Voice Interaction Flow

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant L as LiveKit
    participant B as Bot
    participant STT as Deepgram STT
    participant LLM as Groq LLM
    participant TTS as Deepgram TTS
    
    U->>F: Speaks
    F->>L: Audio stream
    L->>B: Audio frames
    B->>STT: Convert speech to text
    STT->>B: Text transcript
    B->>LLM: Process with context
    LLM->>B: Response text
    B->>TTS: Convert text to speech
    TTS->>B: Audio frames
    B->>L: Audio stream
    L->>F: Audio stream
    F->>U: Plays audio
```

---

## 4. Technology Stack

### 4.1 Frontend
- **Framework:** React 18
- **Build Tool:** Vite
- **Styling:** Tailwind CSS
- **Real-time:** LiveKit React Components
- **Language:** JavaScript (ES6+)

### 4.2 Backend
- **Framework:** FastAPI
- **Language:** Python 3.10+
- **Configuration:** Pydantic Settings
- **Logging:** Python logging
- **Server:** Uvicorn

### 4.3 Bot
- **Framework:** Pipecat AI
- **Transport:** LiveKit Agents
- **VAD:** Silero VAD
- **Language:** Python 3.10+

### 4.4 Infrastructure
- **Real-time:** LiveKit Server
- **STT:** Deepgram API
- **LLM:** Groq API
- **TTS:** Deepgram API (Aura voices)

---

## 5. Deployment Architecture

### 5.1 Cloud Deployment

```mermaid
graph TB
    subgraph "Load Balancer"
        LB[Cloud Load Balancer]
    end
    
    subgraph "Frontend"
        CDN[CDN/Static Hosting]
    end
    
    subgraph "API Cluster"
        API1[API Server 1]
        API2[API Server 2]
        APIN[API Server N]
    end
    
    subgraph "LiveKit Cluster"
        LK1[LiveKit Server 1]
        LK2[LiveKit Server 2]
    end
    
    subgraph "Bot Workers"
        BOT1[Bot Worker 1]
        BOT2[Bot Worker 2]
        BOTN[Bot Worker N]
    end
    
    subgraph "External Services"
        STT[Deepgram]
        LLM[Groq]
        TTS[Deepgram]
    end
    
    Users --> LB
    LB --> CDN
    LB --> API1
    LB --> API2
    LB --> APIN
    API1 --> LK1
    API2 --> LK2
    LK1 --> BOT1
    LK2 --> BOT2
    BOT1 --> STT
    BOT1 --> LLM
    BOT1 --> TTS
    
    style LB fill:#e1f5e1
    style CDN fill:#e1f5e1
    style API1 fill:#fff4e1
    style API2 fill:#fff4e1
    style LK1 fill:#fff4e1
    style BOT1 fill:#fff4e1
```

### 5.2 On-Premise Deployment

```mermaid
graph TB
    subgraph "On-Premise Server"
        NGINX[Nginx Reverse Proxy]
        API[API Server]
        LK[LiveKit Server]
        BOT[Bot Workers]
    end
    
    subgraph "External Services"
        STT[Deepgram]
        LLM[Groq]
        TTS[Deepgram]
    end
    
    Users --> NGINX
    NGINX --> API
    NGINX --> LK
    API --> LK
    LK --> BOT
    BOT --> STT
    BOT --> LLM
    BOT --> TTS
    
    style NGINX fill:#e1f5e1
    style API fill:#fff4e1
    style LK fill:#fff4e1
    style BOT fill:#fff4e1
```

---

## 6. Security Architecture

### 6.1 Security Layers

1. **Network Security**
   - HTTPS/TLS for all communications
   - CORS configuration
   - Rate limiting

2. **Authentication**
   - JWT tokens for LiveKit access
   - Token expiration
   - Secure token generation

3. **Data Security**
   - No persistent storage of voice data
   - Environment variable management
   - Secrets management

4. **Application Security**
   - Input validation
   - Error handling without exposing internals
   - Security headers

---

## 7. Scalability Considerations

### 7.1 Horizontal Scaling
- API servers can be scaled independently
- Bot workers can be scaled based on load
- LiveKit supports clustering

### 7.2 Performance Optimization
- Pre-warmed bot processes
- Connection pooling
- Efficient pipeline processing

### 7.3 Resource Management
- Process limits per worker
- Memory management
- CPU usage monitoring

---

## 8. Monitoring and Observability

### 8.1 Metrics
- Request rate
- Response times
- Error rates
- Active sessions
- Bot worker load

### 8.2 Logging
- Structured logging
- Log levels (DEBUG, INFO, WARNING, ERROR)
- Request/response logging

### 8.3 Health Checks
- API health endpoint
- Bot worker health
- Service availability

---

## 9. Error Handling Strategy

### 9.1 Error Types
- **Client Errors:** Validation, authentication
- **Server Errors:** Internal errors, service unavailability
- **Network Errors:** Connection failures, timeouts

### 9.2 Error Handling Flow
1. Error occurs
2. Log error with context
3. Return appropriate HTTP status
4. Provide user-friendly message
5. Monitor and alert

---

## 10. Session History and Agentic Memory

### 10.1 Session Storage
- **Database:** Supabase (PostgreSQL) for session summaries
- **Storage:** In-memory transcript storage during sessions
- **Persistence:** Summaries saved on session end (disconnect or call end)
- **Normalization:** User names normalized (lowercase) for consistent lookups

### 10.2 Summary Generation
- **Method:** LLM-based summarization using Groq
- **Content:** Main topics, user goals, key advice, progress/plans
- **Timing:** Generated when session ends (≥30 seconds, ≥2 messages)
- **Fallback:** Basic summary if LLM fails

### 10.3 Agentic Memory
- **Retrieval:** Fetches last 10 past sessions on user join
- **Integration:** Past session summaries included in LLM system prompt
- **Continuity:** Bot references past conversations naturally
- **Privacy:** User name normalization ensures consistent history

### 10.4 Data Flow
```
User Session → Transcript (RAM) → Summary (LLM) → Supabase → Next Session Context
```

---

## 11. Future Enhancements

### 11.1 Architecture Improvements
- Message queue for async processing
- Caching layer for session summaries
- CDN for static assets
- Real-time analytics

### 11.2 Feature Additions
- User accounts and authentication
- Analytics dashboard
- Admin panel
- Session export/download
- Multi-language support

