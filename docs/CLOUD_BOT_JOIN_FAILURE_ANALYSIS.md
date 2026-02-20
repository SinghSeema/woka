# Deep Analysis: Bot Failed to Join Room in Google Cloud

## Executive Summary

The bot worker **successfully registers** with LiveKit Cloud, but **fails to join rooms** due to **process initialization timeouts** when jobs are dispatched. The timeout occurs during worker process spawning, not during worker registration.

## Timeline of Events

### ✅ What Works

1. **Worker Registration**: ✅ SUCCESS
   ```
   2026-02-19 17:41:36 - Starting LiveKit worker process
   2026-02-19 17:41:39 - starting worker
   2026-02-19 17:42:02 - registered worker
   ```

2. **Token Generation**: ✅ SUCCESS
   ```
   2026-02-20 08:53:03 - Token generated successfully for user: wika, room: room_4056520894
   ```

3. **API Health**: ✅ SUCCESS
   - FastAPI backend is healthy and responding

### ❌ What Fails

**Process Initialization Timeout**: ❌ FAILURE
```
2026-02-20 08:52:42 - livekit.agents - ERROR - error initializing process
  File "/usr/local/lib/python3.11/site-packages/livekit/agents/ipc/proc_pool.py", line 205, in _proc_spawn_task
    await proc.initialize()
  File "/usr/local/lib/python3.11/site-packages/livekit/agents/ipc/supervised_proc.py", line 224, in initialize
    init_res = await asyncio.wait_for(...)
  raise TimeoutError() from exc
```

## Root Cause Analysis

### The Problem Flow

```
1. Cloud Run starts container
   └─> Runs: uvicorn app.main:app & python -m bot.main start
   
2. Worker process starts
   └─> cli.run_app(WorkerOptions(...))
   └─> Connects to LiveKit Cloud (wss://woka-qe4nlyjl.livekit.cloud)
   └─> ✅ Registers successfully
   
3. User connects via frontend
   └─> Frontend calls: GET /api/v1/auth/connect?user=wika
   └─> ✅ Token generated successfully
   └─> Frontend connects to LiveKit room
   
4. LiveKit dispatches job to worker
   └─> Worker needs to spawn a new process to handle the job
   └─> Process initialization starts
   └─> ❌ TIMEOUT during proc.initialize()
   └─> Job fails, bot never joins room
```

### Why Process Initialization Times Out

The timeout occurs in `supervised_proc.py` during `proc.initialize()`. This happens because:

1. **Heavy Imports**: Even with optimized imports, initial Python module loading is slow
   - `pipecat` framework initialization
   - `sentence-transformers` model loading
   - `onnxruntime` initialization
   - Other heavy dependencies

2. **Prewarm Function**: Even though `NUM_IDLE_PROCESSES=0`, when a job is dispatched:
   - LiveKit Agents framework spawns a new process
   - The `prewarm()` function is called (if configured)
   - `SileroVADAnalyzer()` loading takes time
   - Default timeout (likely 30-60s) is exceeded

3. **Cloud Run Constraints**:
   - **CPU throttling**: Cloud Run may throttle CPU during cold starts
   - **Memory pressure**: 2Gi memory might be tight during initialization
   - **Network latency**: Importing packages that download models
   - **Cold start penalty**: First process spawn is slower

4. **Default Timeout Too Short**: LiveKit Agents has a default `initialize_process_timeout` (likely 30-60s) that's too short for Cloud Run's constrained environment.

## Evidence from Logs

### Worker Registration (Success)
```
2026-02-19 17:41:36 - Starting LiveKit worker process
2026-02-19 17:41:39 - starting worker
2026-02-19 17:42:02 - registered worker  ← Worker is registered!
```

### Process Initialization (Failure)
```
2026-02-20 08:50:07 - error initializing process
  raise TimeoutError() from exc
2026-02-20 08:50:26 - error initializing process
  raise TimeoutError() from exc
... (repeats every ~18 seconds)
```

### Token Generation (Success)
```
2026-02-20 08:53:03 - Token generated successfully for user: wika, room: room_4056520894
```

**Key Insight**: Tokens are generated, but no bot joins because worker processes fail to initialize.

## Current Configuration

### Cloud Run Service
- **Service**: `woka-backend`
- **Region**: `asia-south1`
- **Min Instances**: `1` (keeps worker warm)
- **CPU**: `1`
- **Memory**: `2Gi`
- **Image**: `asia-south1-docker.pkg.dev/wellness-coach-1985/woka-repo/woka-backend:20260220-141438`

### Environment Variables
- `NUM_IDLE_PROCESSES=0` ✅ (No prewarm)
- `LIVEKIT_URL=wss://woka-qe4nlyjl.livekit.cloud` ✅
- `LIVEKIT_PUBLIC_URL=wss://woka-qe4nlyjl.livekit.cloud` ✅

### Worker Configuration
```python
WorkerOptions(
    entrypoint_fnc=entrypoint,
    prewarm_fnc=prewarm,  # Still configured, even if num_idle_processes=0
    num_idle_processes=0,
)
```

## Solutions

### Solution 1: Increase Process Initialization Timeout ⭐ RECOMMENDED

Add `initialize_process_timeout` to `WorkerOptions`:

```python
from livekit.agents import WorkerOptions

cli.run_app(
    WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm,
        num_idle_processes=0,
        initialize_process_timeout=120,  # Increase from default (likely 30-60s) to 120s
    )
)
```

**Pros**:
- Simple fix
- Gives more time for heavy imports
- Doesn't change architecture

**Cons**:
- Still slow, but at least works
- User waits longer for bot to join

### Solution 2: Disable Prewarm for Job Processes

Modify `prewarm()` to be a no-op or remove it:

```python
def prewarm(proc: JobProcess):
    """Pre-warm bot processes with heavy models."""
    # Skip prewarm in Cloud Run to avoid timeouts
    # VAD will be created on-demand in entrypoint
    logger.info("Skipping prewarm in Cloud Run environment")
    pass
```

**Pros**:
- Faster process initialization
- VAD is created on-demand (slower first response, but works)

**Cons**:
- First bot response is slower
- Still need to increase timeout for heavy imports

### Solution 3: Lazy Import Heavy Dependencies ⭐ BEST

Move heavy imports inside `entrypoint()` instead of at module level:

```python
async def entrypoint(ctx: JobContext):
    """Bot entrypoint for handling a job."""
    # Lazy import heavy dependencies
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from bot.services.stt_service import create_stt_service
    # ... etc
    
    # Rest of entrypoint...
```

**Pros**:
- Fastest process initialization
- Only loads what's needed when needed
- Better resource usage

**Cons**:
- Requires refactoring imports
- First job in a process is slower (but subsequent jobs are fast)

### Solution 4: Increase Cloud Run Resources

- **CPU**: Increase from `1` to `2`
- **Memory**: Increase from `2Gi` to `4Gi`

**Pros**:
- More resources = faster initialization
- Better for production

**Cons**:
- Higher cost
- Doesn't solve root cause (just makes it faster)

### Solution 5: Use Separate Services (Advanced)

Split into two services:
1. **API Service**: FastAPI only (lightweight)
2. **Worker Service**: Bot worker only (can have more resources)

**Pros**:
- Better resource allocation
- Can scale independently

**Cons**:
- More complex architecture
- More services to manage

## Recommended Fix (Combination)

1. **Increase timeout** (Solution 1): `initialize_process_timeout=120`
2. **Disable prewarm** (Solution 2): Make `prewarm()` a no-op
3. **Lazy imports** (Solution 3): Move heavy imports to `entrypoint()`

This combination ensures:
- ✅ Process initialization completes within timeout
- ✅ No unnecessary prewarm overhead
- ✅ Fast startup for worker processes

## Testing Plan

After applying fixes:

1. **Deploy to Cloud Run**
2. **Monitor logs** for:
   - "Starting LiveKit worker process"
   - "registered worker"
   - "Bot joined room" ← Should see this!
   - No more "error initializing process"
3. **Test end-to-end**:
   - Frontend connects
   - Bot joins within 10-20 seconds
   - Bot responds to user

## Monitoring

Key metrics to watch:
- **Process initialization time**: Should be < 120s
- **Bot join time**: Should be < 20s after user connects
- **Error rate**: Should drop to 0%
- **Worker registration**: Should remain stable

## Next Steps

1. ✅ Identify root cause (this document)
2. ⏳ Implement fixes (Solutions 1, 2, 3)
3. ⏳ Deploy and test
4. ⏳ Monitor and validate

