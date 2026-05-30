# Production Gap Analysis: Voice AI Pipeline (Woka)

---

## 1. Multilanguage Support (English + Hindi)

**What works:**
- STT (Deepgram Nova-2) supports Hindi — correctly passes `language="hi"` via `backend/bot/services/stt_service.py`
- Language detection is per-session from participant metadata in `backend/bot/main.py:108`
- A language block is injected into the system prompt for non-English sessions in `backend/bot/services/prompt_builder.py:83-92`

**Critical gaps:**

| Gap | Severity | File | Detail |
|-----|----------|------|--------|
| TTS is English-only (Deepgram Aura hardcoded) | 🔴 Critical | `tts_service.py` | User speaks Hindi → LLM is forced to reply in English → TTS speaks English. Hindi user hears English audio. |
| LLM prompt explicitly says "Always reply in English" | 🔴 Critical | `prompt_builder.py:87` | This is a workaround for TTS limitation, but it means no actual Hindi response is possible |
| Hardcoded disclaimers and safety guardrails in English | 🟠 High | `prompt_builder.py:72-73` | Medical disclaimers not translated |
| Filler responses while DB queries run are English-only | 🟠 High | `past_context_processor.py` | Hindi user hears English filler ("Let me think...") |
| Session summaries always written in English | 🟠 High | `summary_service.py` | Cross-session memory is in English even for Hindi sessions |
| No per-utterance language re-detection | 🟡 Medium | `main.py` | If user code-switches mid-call (Hinglish), STT stays locked to session language |
| Unknown language codes silently fall back to English | 🟡 Medium | `language_config.py:89` | No alerting when fallback triggers |

**Fix required:** Replace Deepgram Aura TTS with a bilingual provider (Google Cloud TTS supports Hindi via `hi-IN` voices, or ElevenLabs multilingual v2). Route TTS based on session language. Without this, Hindi support is STT-only — the bot literally cannot speak Hindi.

---

## 2. Context Engineering Flaws (30-min Call)

**Current strategy:** Rolling LLM-based compression triggered every ~25 messages. Compression merges the existing running summary with the new segment, asking the LLM to keep it under 4-5 sentences (`memory_compressor.py:84-99`).

**What is preserved:** Current focus/habit, goals, action steps, emotional state.

**What is silently lost after compression:**

| Lost Information | Impact on Woka Coaching |
|-----------------|------------------------|
| User constraints/dislikes ("I hate running", "I'm busy at 7am") | Bot re-suggests exercises user already rejected |
| Exact quantities ("30 min walk, 2L water") → fuzzy over compressions | Goals become vague after 2–3 compressions |
| Unresolved issues (mid-call struggles that weren't solved) | Not flagged as open — disappear from context |
| Specific commitments made ("I'll try yoga this week") | No cross-session validation ("Did you do it?") |
| Reasoning behind goals | Bot can't motivate with the user's own "why" |
| Tone/personality details | Generic responses for a personalised coaching app |

**Hallucination risk:** When `_merge_summaries()` (`memory_compressor.py:66-129`) is called 3+ times, LLM is summarizing a summary of a summary. The instruction to "REMOVE outdated info" can cause the model to silently drop still-relevant details. No audit trail exists to detect this.

**Concrete improvements:**

1. **Structured summary schema** — instead of free-text, compress into a fixed JSON/YAML structure:
   ```
   CURRENT_GOAL: [specific goal + metric]
   UNRESOLVED: [open challenges or questions]
   CONSTRAINTS: [dislikes, time restrictions, equipment limits]
   COMMITMENTS: [specific actions promised this session]
   FOLLOW_UP: [topics to revisit next call]
   ```
2. **Compression depth limit** — after 2 incremental merges, trigger a full re-summary from the raw transcript (not from a summary-of-summary)
3. **Commitment validation** — at session start, inject last session's `COMMITMENTS` into the prompt and instruct the bot to ask about completion
4. **Keep a quantitative anchor** — extract and freeze specific numbers (minutes, counts, dates) separately from the prose summary so they survive compression

---

## 3. Memory Management Gaps

**Current memory stack:**

| Layer | Implementation | Persistence |
|-------|---------------|-------------|
| Short-term (in-call) | `ConversationMemory` + OpenAI LLM context | Lost on disconnect |
| Mid-term (call cache) | `ShadowMemory` with in-memory embeddings | Lost on bot restart |
| Query cache | `ContextCache` with 5-min TTL | Lost on bot restart |
| Long-term | Supabase (session summaries + vector chunks) | Persisted ✅ |

**Gaps:**

| Gap | Severity | Detail |
|-----|----------|--------|
| ContextCache is pure in-memory — lost on any crash/restart | 🔴 Critical | `context_cache.py:36` — First query after restart always hits DB cold |
| No circuit breaker for Supabase | 🔴 Critical | If Supabase is slow, every user's context fetch hangs. No "skip memory if >Xms" rule |
| Session only written at end — crash = lost session | 🔴 Critical | If bot crashes at 28 min of a 30-min call, nothing is saved |
| No deduplication on session saves | 🟠 High | Same session could be written twice (e.g., on reconnect); no unique constraint visible |
| No explicit latency SLO for memory retrieval | 🟠 High | No timeout wrapper around DB calls; slow query blocks the pipeline turn |
| ContextCache has no size limit — unbounded growth per user | 🟠 High | `context_cache.py` — TTL only, no LRU eviction |
| ShadowMemory embeddings not cleaned up on shutdown | 🟡 Medium | `shadow_memory.py:75` — Memory leak risk in long-running processes |
| No cross-user isolation enforcement at retrieval | 🟡 Medium | Relies purely on DB query filters; no explicit user_id assertion before injection |

**Concrete improvements:**

1. **Incremental session saves** — write a checkpoint to Supabase every 5 minutes during the call, not just at end
2. **Circuit breaker** — if Supabase returns >500ms or fails, skip memory injection and proceed with the call (log it)
3. **Redis for ContextCache** — persist the query cache across restarts; even a 5-min Redis TTL is better than pure in-memory
4. **DB timeout budget** — wrap every Supabase call with `asyncio.wait_for(..., timeout=0.4)` and fall back gracefully

---

## 4. LiveKit Concurrency — How Many Simultaneous Users?

**Current infrastructure:**
- LiveKit: **Cloud-hosted** (`wss://woka-qe4nlyjl.livekit.cloud`) — not self-hosted
- Bot runtime: **Google Cloud Run** — `--max-instances=3`, `--memory=2Gi` per instance (`scripts/gcp/deploy.sh`)
- `NUM_IDLE_PROCESSES=0` — no pre-warmed bot processes; every user waits for cold start

**Resource per bot session:**
- Memory: ~120–200 MB (Python runtime + LLM context + embeddings)
- Threads: 2–5 (STT + TTS + main loop)
- Connections: 3–4 (LiveKit WS + Deepgram + Groq + Supabase)

**Bottleneck stack (in order):**

| Bottleneck | Limit | Configured? |
|-----------|-------|-------------|
| Cloud Run max instances | 3 instances × ~13 bot processes = ~30 theoretical | ✅ (but too low) |
| Per-instance RAM at 150MB/bot | ~13 bots per 2GB instance | ✅ |
| Supabase connection pool | ~10–20 connections total | ❌ Not configured |
| Groq API rate limits | ~100 req/min (free), 1000/min (paid) | ❌ No rate limiter in code |
| Deepgram concurrent streams | Depends on plan; no limit set | ❌ Not configured |

**Realistic concurrent user count:**

| Scenario | Simultaneous Users |
|---------|-------------------|
| No past-context queries, short turns | ~10–15 |
| Normal use (50% use past context) | **3–5** |
| Heavy use (all querying Supabase simultaneously) | **1–2** (pool exhaustion) |

The binding constraint today is `--max-instances=3` combined with no pre-warming and Supabase pool limits. With 3 Cloud Run instances and 150MB/bot, you have theoretical headroom for ~15 bots, but Supabase becomes the real bottleneck before that.

**To support 50 concurrent users you need:**
1. Raise `--max-instances` to 10–15
2. Set `NUM_IDLE_PROCESSES=2` to eliminate cold start latency
3. Add Supabase connection pooling (PgBouncer or Supabase Pooler mode, set pool size ≥50)
4. Add client-side retry/backoff on Groq and Deepgram with rate limit headers
5. Move ContextCache to Redis so warm cache survives across restarts

---

## Priority Fix Order

| Priority | Fix | Impact |
|----------|-----|--------|
| P0 | Replace TTS with multilingual provider (Google Cloud TTS) | Hindi users can't hear Hindi responses at all currently |
| P0 | Add incremental session saves every 5 min | Crash = lost 30-min conversation |
| P1 | Circuit breaker on Supabase memory fetch | One slow DB call shouldn't block all users |
| P1 | Structured summary schema with UNRESOLVED/COMMITMENTS fields | Core coaching quality gap |
| P1 | Raise Cloud Run max-instances + tune Supabase pool | Hard ceiling at 3–5 concurrent users |
| P2 | Redis-backed ContextCache | Eliminates cold-start DB flood after restarts |
| P2 | Per-utterance language re-detection (or Hinglish mode) | Real Hindi callers naturally code-switch |
| P2 | Compression depth limit + full re-summary after 2 merges | Prevents hallucination drift on long calls |
