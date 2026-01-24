# Troubleshooting Guide

## Common Errors

### 404 Error: Failed to load resource

**Symptom:** Browser console shows "Failed to load resource: the server responded with a status of 404"

**Cause:** The backend API server is not running or not accessible.

**Solution:**
1. Check if backend is running:
   ```bash
   curl http://localhost:8000/health
   ```

2. If backend is not running, start it:
   ```bash
   cd backend
   source ../.pipebot/bin/activate
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. Or use the run script:
   ```bash
   ./run.sh
   ```

4. Check backend logs:
   ```bash
   tail -f backend.log
   ```

### Connection Refused

**Symptom:** "Connection refused" error when frontend tries to connect to backend.

**Causes:**
- Backend API is not running
- Wrong port number
- Firewall blocking connection

**Solution:**
1. Verify backend is running on port 8000:
   ```bash
   lsof -i :8000
   # or
   netstat -tlnp | grep 8000
   ```

2. Check backend logs for errors
3. Verify CORS settings in `.env` file

### Bot Worker Not Starting

**Symptom:** Bot worker fails with "LIVEKIT_URL is required" error.

**Solution:**
1. Ensure `.env` file has `LIVEKIT_URL` set
2. Make sure environment variables are exported:
   ```bash
   source .env  # or use the run.sh script
   ```

### Config Validation Errors

**Symptom:** "Field required" errors when starting backend or bot.

**Solution:**
1. Check `.env` file has all required variables:
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`
   - `GROQ_API_KEY`
   - `DEEPGRAM_API_KEY` (for both STT and TTS)
   - `DEEPGRAM_TTS_VOICE` (optional, defaults to `aura-2-helena-en`)

2. Verify `.env` file is in project root (not in backend/)

### Port Already in Use

**Symptom:** "Address already in use" error.

**Solution:**
1. Find and kill the process using the port:
   ```bash
   lsof -ti:8000 | xargs kill -9
   ```

2. Or change the port in `.env`:
   ```
   API_PORT=8001
   ```

## Debugging Steps

1. **Check all services are running:**
   ```bash
   ps aux | grep -E "(uvicorn|bot|vite)"
   ```

2. **Check ports are listening:**
   ```bash
   netstat -tlnp | grep -E ":(8000|5173|7880)"
   ```

3. **Test API endpoints:**
   ```bash
   curl http://localhost:8000/health
   curl "http://localhost:8000/api/v1/auth/connect?user=Test"
   ```

4. **Check browser console** for detailed error messages

5. **Check backend logs:**
   ```bash
   tail -f backend.log
   ```

6. **Check bot logs** (if running in terminal, check output)

## Quick Health Check

Run this to verify everything is working:

```bash
# Check backend
curl http://localhost:8000/health

# Check frontend
curl http://localhost:5173

# Check LiveKit
curl http://localhost:7880
```

## Getting Help

If issues persist:
1. Check all logs (backend.log, terminal output)
2. Verify `.env` file has correct values
3. Ensure all dependencies are installed
4. Check that LiveKit server is running

