# Debug Plan: Bot Not Joining Rooms in Cloud Run

## Current Status
- ✅ Worker starts and registers with LiveKit Cloud
- ✅ Token generation works
- ✅ Frontend connects to LiveKit
- ❌ Bot never joins the room
- ❌ No entrypoint() logs when jobs are dispatched

## Debug Plan

### Phase 1: Verify Worker Registration & Connectivity

#### Step 1.1: Check Worker is Running
```bash
# Check if worker process is actually running
gcloud run services logs read woka-backend --region=asia-south1 --limit=100 | grep -E "Starting LiveKit|registered worker"
```

**Expected:** Should see "Starting LiveKit worker process" and "registered worker"

**If missing:** Worker process isn't starting (check Dockerfile CMD)

#### Step 1.2: Verify Worker Connection to LiveKit Cloud
```bash
# Check for connection errors
gcloud run services logs read woka-backend --region=asia-south1 --limit=200 | grep -E "Cannot connect|connection failed|WebSocket|livekit"
```

**Expected:** No connection errors

**If errors found:** Check LIVEKIT_URL and API keys

#### Step 1.3: Check Worker Registration Details
```bash
# Look for worker registration logs
gcloud run services logs read woka-backend --region=asia-south1 --limit=500 | grep -E "registered worker|worker.*registered|WorkerOptions"
```

**Expected:** "registered worker" log

**If missing:** Worker isn't registering (check LIVEKIT_API_KEY, LIVEKIT_API_SECRET)

---

### Phase 2: Verify Job Dispatch

#### Step 2.1: Monitor Real-Time Logs During Connection
```bash
# Run this in one terminal, then connect from frontend
gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=woka-backend"
```

**What to watch for:**
- When you connect from frontend, you should see:
  1. Token generation log
  2. `initializing process` (job dispatched)
  3. Either `Bot joined room` (success) or `error initializing process` (failure)

**If no `initializing process`:** LiveKit isn't dispatching jobs to worker

#### Step 2.2: Check LiveKit Cloud Dashboard
1. Go to LiveKit Cloud dashboard
2. Check "Agents" tab - should show registered worker
3. Check "Rooms" tab - when you connect, room should appear
4. Check if worker is assigned to the room

**Expected:** Worker visible in Agents tab, room created when connecting

**If worker not visible:** Registration issue
**If room created but no worker assigned:** Job dispatch issue

#### Step 2.3: Verify Token Permissions
```bash
# Check token generation code
grep -A 20 "def get_token" backend/app/api/routes/auth.py
```

**Check:**
- Token has `room_join=True` grant
- Token has correct `room` name
- Token has user metadata

**Expected:** Token should allow bot to join room

---

### Phase 3: Debug Process Initialization

#### Step 3.1: Check Process Initialization Timeout
```bash
# Check current timeout setting
grep "initialize_process_timeout" backend/bot/main.py
```

**Expected:** `initialize_process_timeout=120.0`

**If different:** Update to 120.0

#### Step 3.2: Add More Logging to Entrypoint
Add explicit logging at the very start of entrypoint:

```python
async def entrypoint(ctx: JobContext):
    """Bot entrypoint for handling a job."""
    logger.info(f"🚀 ENTRYPOINT CALLED - Room: {ctx.room.name}, Job: {ctx.job.id}")
    
    # Rest of code...
```

**Why:** Confirms entrypoint is being called

#### Step 3.3: Check for Silent Failures
```bash
# Look for any exceptions or errors
gcloud run services logs read woka-backend --region=asia-south1 --limit=500 | grep -E "Exception|Error|Traceback|Failed" | tail -n 30
```

**Expected:** No errors (or only expected errors)

**If errors found:** Investigate specific error

#### Step 3.4: Test Process Initialization Time
```bash
# Check how long process initialization takes
gcloud run services logs read woka-backend --region=asia-south1 --limit=1000 | grep -E "initializing process|error initializing" | tail -n 20
```

**Calculate:** Time between "initializing process" and "error initializing process"

**If < 120s:** Process is timing out (increase timeout or optimize)
**If > 120s:** Timeout setting not working

---

### Phase 4: Debug Lazy Imports

#### Step 4.1: Add Import Timing Logs
Add logging around lazy imports in entrypoint:

```python
async def entrypoint(ctx: JobContext):
    """Bot entrypoint for handling a job."""
    logger.info(f"🚀 ENTRYPOINT CALLED - Room: {ctx.room.name}")
    
    import_start = time.time()
    logger.info("📦 Starting lazy imports...")
    
    from livekit import api
    logger.info(f"✅ Imported livekit.api ({time.time() - import_start:.2f}s)")
    
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    logger.info(f"✅ Imported SileroVADAnalyzer ({time.time() - import_start:.2f}s)")
    
    # Continue with other imports...
```

**Why:** Identifies which import is slow/failing

#### Step 4.2: Test Imports Locally
```bash
# Test if imports work in container
docker compose exec agent python3 -c "
import time
start = time.time()
from pipecat.audio.vad.silero import SileroVADAnalyzer
print(f'Import took: {time.time() - start:.2f}s')
"
```

**Expected:** Imports complete in < 10s

**If slow:** Optimize imports or pre-cache models

---

### Phase 5: Verify Configuration

#### Step 5.1: Check Environment Variables
```bash
# Verify all required env vars are set
gcloud run services describe woka-backend --region=asia-south1 --format="value(spec.template.spec.containers[0].env)" | grep -E "LIVEKIT|NUM_IDLE"
```

**Check:**
- `LIVEKIT_URL` = `wss://woka-qe4nlyjl.livekit.cloud`
- `LIVEKIT_API_KEY` = set (from secret)
- `LIVEKIT_API_SECRET` = set (from secret)
- `NUM_IDLE_PROCESSES` = `0`

#### Step 5.2: Verify Secrets
```bash
# Check secrets exist and have values
gcloud secrets list | grep LIVEKIT
gcloud secrets versions access latest --secret=LIVEKIT_API_KEY | head -c 20
gcloud secrets versions access latest --secret=LIVEKIT_API_SECRET | head -c 20
```

**Expected:** Both secrets exist and have values

**If missing:** Create/update secrets

#### Step 5.3: Check Cloud Run Resources
```bash
# Verify resources are sufficient
gcloud run services describe woka-backend --region=asia-south1 --format="value(spec.template.spec.containers[0].resources)"
```

**Check:**
- CPU: At least 1
- Memory: At least 2Gi
- Min instances: 1 (to keep worker warm)

**If insufficient:** Increase resources

---

### Phase 6: Test Job Dispatch Manually

#### Step 6.1: Create Test Room via API
```bash
# Generate token and create room
curl "https://woka-backend-2881969360.asia-south1.run.app/api/v1/auth/connect?user=testuser"
```

**Check response:** Should return token, room_name, url

#### Step 6.2: Monitor Logs During Test
```bash
# In another terminal, watch logs
gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=woka-backend"
```

**Then:** Connect from frontend and watch for:
- Token generation
- `initializing process`
- `Bot joined room` or error

---

### Phase 7: Check LiveKit Cloud Configuration

#### Step 7.1: Verify LiveKit Cloud Project
- Check LiveKit Cloud dashboard
- Verify project is active
- Check API keys match

#### Step 7.2: Check Worker Type
```python
# In bot/main.py, check WorkerOptions
WorkerOptions(
    worker_type=WorkerType.ROOM,  # Should be ROOM, not AGENT
    ...
)
```

**Expected:** `worker_type=WorkerType.ROOM`

**If different:** Update to ROOM

#### Step 7.3: Verify Room Name Format
```bash
# Check room name format in token generation
grep -A 10 "room_name" backend/app/api/routes/auth.py
```

**Expected:** Room name format matches what LiveKit expects

---

### Phase 8: Add Comprehensive Logging

#### Step 8.1: Add Logging to Worker Startup
```python
# In bot/main.py, add logging before cli.run_app
if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("Starting LiveKit worker process")
    logger.info(f"LIVEKIT_URL: {settings.LIVEKIT_URL}")
    logger.info(f"NUM_IDLE_PROCESSES: {settings.NUM_IDLE_PROCESSES}")
    logger.info(f"initialize_process_timeout: 120.0")
    logger.info("=" * 50)
    
    try:
        cli.run_app(...)
```

#### Step 8.2: Add Logging to Prewarm
```python
def prewarm(proc: JobProcess):
    """Pre-warm bot processes with heavy models."""
    logger.info("🔥 PREWARM STARTED")
    start_time = time.time()
    
    try:
        logger.info("Pre-warming bot process (VAD Silero model)...")
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        logger.info("✅ SileroVADAnalyzer imported")
        
        proc.userdata["vad"] = SileroVADAnalyzer()
        logger.info(f"✅ Bot engine warmed up ({time.time() - start_time:.2f}s)")
    except Exception as e:
        logger.error(f"❌ Pre-warm failed: {e}", exc_info=True)
```

#### Step 8.3: Add Logging to Entrypoint Start
```python
async def entrypoint(ctx: JobContext):
    """Bot entrypoint for handling a job."""
    logger.info("=" * 50)
    logger.info(f"🚀 ENTRYPOINT CALLED")
    logger.info(f"   Room: {ctx.room.name}")
    logger.info(f"   Job ID: {ctx.job.id if hasattr(ctx, 'job') else 'N/A'}")
    logger.info(f"   Process ID: {ctx.proc.id if hasattr(ctx.proc, 'id') else 'N/A'}")
    logger.info("=" * 50)
    
    # Rest of code...
```

---

### Phase 9: Test Incrementally

#### Step 9.1: Test Without Prewarm
Temporarily disable prewarm:
```python
def prewarm(proc: JobProcess):
    logger.info("Skipping prewarm for testing")
    pass
```

**Test:** See if bot joins (faster initialization)

#### Step 9.2: Test With Minimal Entrypoint
Create minimal entrypoint:
```python
async def entrypoint(ctx: JobContext):
    logger.info(f"🚀 MINIMAL ENTRYPOINT - Room: {ctx.room.name}")
    await ctx.connect(auto_subscribe=True)
    logger.info(f"✅ Bot joined room: {ctx.room.name}")
    # That's it - no pipeline, no services
```

**Test:** See if bot can at least join room

#### Step 9.3: Gradually Add Complexity
1. Add VAD
2. Add services (STT, LLM, TTS)
3. Add pipeline
4. Add handlers

**Identify:** At which step it fails

---

### Phase 10: Check LiveKit Cloud Agent Configuration

#### Step 10.1: Verify Agent Name
```python
# Check if agent_name is set correctly
WorkerOptions(
    agent_name=settings.BOT_NAME,  # Should match LiveKit Cloud config
    ...
)
```

#### Step 10.2: Check Worker Permissions
- Verify worker has permission to join rooms
- Check LiveKit Cloud agent policies
- Verify token grants match worker permissions

---

## Quick Diagnostic Commands

### Check Everything at Once
```bash
# Run all checks
echo "=== Worker Status ==="
gcloud run services logs read woka-backend --region=asia-south1 --limit=100 | grep -E "Starting LiveKit|registered worker" | tail -n 5

echo "=== Recent Errors ==="
gcloud run services logs read woka-backend --region=asia-south1 --limit=200 | grep -E "error|Error|ERROR|Exception" | tail -n 10

echo "=== Process Initialization ==="
gcloud run services logs read woka-backend --region=asia-south1 --limit=500 | grep -E "initializing process|error initializing" | tail -n 10

echo "=== Token Generation ==="
gcloud run services logs read woka-backend --region=asia-south1 --limit=100 | grep -E "Token generated|room_" | tail -n 5

echo "=== Bot Join Attempts ==="
gcloud run services logs read woka-backend --region=asia-south1 --limit=500 | grep -E "Bot joined|entrypoint|ENTRYPOINT" | tail -n 10
```

---

## Expected Flow (Success Case)

```
1. Container starts
   └─> "Starting LiveKit worker process"
   
2. Worker connects to LiveKit Cloud
   └─> "registered worker"
   
3. User connects from frontend
   └─> "Token generated successfully"
   
4. LiveKit dispatches job
   └─> "initializing process"
   
5. Process initializes
   └─> (within 120s) Process ready
   
6. Entrypoint called
   └─> "🚀 ENTRYPOINT CALLED"
   
7. Bot connects to room
   └─> "Bot joined room: room_XXX"
   
8. Pipeline starts
   └─> "🚀 Starting pipeline runner"
```

---

## Most Likely Issues (Based on Current Evidence)

1. **Process initialization timing out** (even with 120s)
   - **Fix:** Increase timeout further or optimize imports

2. **Entrypoint not being called**
   - **Fix:** Check LiveKit Cloud agent configuration

3. **Silent failure in entrypoint**
   - **Fix:** Add more logging to entrypoint

4. **Job not being dispatched**
   - **Fix:** Check LiveKit Cloud dashboard, verify worker is assigned to rooms

---

## Next Steps

1. ✅ Run Phase 1 checks (verify worker registration)
2. ⏳ Run Phase 2 checks (monitor real-time during connection)
3. ⏳ Add logging from Phase 8
4. ⏳ Test incrementally from Phase 9
5. ⏳ Check LiveKit Cloud dashboard

Start with Phase 1 and 2 - they'll tell us if the issue is with registration or job dispatch.

