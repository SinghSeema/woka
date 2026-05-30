#!/bin/bash
# run-demo.sh — start Woka locally for a demo.
#
# This script does NOT touch .env. It starts LiveKit via Docker and then
# launches all three services with local-specific env overrides applied
# in-shell only (no files are modified).
#
# Usage:
#   chmod +x run-demo.sh
#   ./run-demo.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Woka — Local Demo Startup${NC}"
echo -e "${BLUE}========================================${NC}\n"

# ── Prerequisites ─────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  echo -e "${RED}ERROR: .env file not found.${NC}"
  exit 1
fi

if [ ! -d ".pipebot" ]; then
  echo -e "${RED}ERROR: .pipebot venv not found. Run:  python3 -m venv .pipebot && source .pipebot/bin/activate && pip install -r backend/requirements.txt${NC}"
  exit 1
fi

if ! command -v docker &>/dev/null; then
  echo -e "${RED}ERROR: Docker not found. Install Docker to run LiveKit locally.${NC}"
  exit 1
fi

# ── Local env overrides (applied in-shell, .env is never touched) ─────────────
# These values override whatever is in .env for this shell session only.
export LIVEKIT_URL="ws://127.0.0.1:7880"
export LIVEKIT_PUBLIC_URL="ws://127.0.0.1:7880"
export LIVEKIT_API_KEY="devkey"
export LIVEKIT_API_SECRET="secret"
# frontend/.env.local already overrides VITE_API_BASE_URL=http://localhost:8000

# ── Step 1: Start LiveKit ──────────────────────────────────────────────────────
echo -e "${BLUE}[1/4] Starting LiveKit server (Docker)...${NC}"

if docker ps --format '{{.Names}}' | grep -q "^woka-livekit$"; then
  echo -e "${GREEN}  LiveKit already running.${NC}"
else
  docker run -d \
    --name woka-livekit \
    --network host \
    livekit/livekit-server:latest \
    --dev \
    --bind 0.0.0.0 \
    2>/dev/null || \
  docker start woka-livekit 2>/dev/null || true

  echo -e "${YELLOW}  Waiting for LiveKit to be ready...${NC}"
  sleep 3

  if docker ps --format '{{.Names}}' | grep -q "^woka-livekit$"; then
    echo -e "${GREEN}  LiveKit started on ws://127.0.0.1:7880${NC}"
  else
    echo -e "${RED}  LiveKit failed to start. Check: docker logs woka-livekit${NC}"
    exit 1
  fi
fi

# ── Cleanup on exit ────────────────────────────────────────────────────────────
cleanup() {
  echo -e "\n${YELLOW}Stopping services...${NC}"
  kill $BACKEND_PID $BOT_PID $FRONTEND_PID 2>/dev/null || true
  echo -e "${YELLOW}Stopping LiveKit...${NC}"
  docker stop woka-livekit 2>/dev/null || true
  echo -e "${GREEN}All stopped.${NC}"
  exit
}
trap cleanup SIGINT SIGTERM

# ── Load .env into shell (without overwriting the local overrides above) ───────
set -a
while IFS= read -r line; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  line=$(echo "$line" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//' | \
         sed 's/[[:space:]]*=[[:space:]]*/=/' | sed 's/#.*$//' | sed 's/[[:space:]]*$//')
  if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
    key="${line%%=*}"
    # Only export keys that haven't been set by our local overrides above
    if [[ -z "${!key}" ]]; then
      export "$line" 2>/dev/null || true
    fi
  fi
done < .env
set +a

# Re-apply local overrides (in case .env clobbered them)
export LIVEKIT_URL="ws://127.0.0.1:7880"
export LIVEKIT_PUBLIC_URL="ws://127.0.0.1:7880"
export LIVEKIT_API_KEY="devkey"
export LIVEKIT_API_SECRET="secret"

PYTHON="$SCRIPT_DIR/.pipebot/bin/python3"

# ── Step 2: Backend API ────────────────────────────────────────────────────────
echo -e "\n${BLUE}[2/4] Starting Backend API on http://localhost:8000 ...${NC}"
cd "$SCRIPT_DIR/backend"
"$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > "$SCRIPT_DIR/logs/backend.log" 2>&1 &
BACKEND_PID=$!
cd "$SCRIPT_DIR"
sleep 3

if kill -0 $BACKEND_PID 2>/dev/null; then
  echo -e "${GREEN}  Backend running (PID $BACKEND_PID)${NC}"
else
  echo -e "${RED}  Backend failed. Check logs/backend.log${NC}"
  tail -15 logs/backend.log
  exit 1
fi

# ── Step 3: Bot agent worker ───────────────────────────────────────────────────
echo -e "\n${BLUE}[3/4] Starting Bot agent worker...${NC}"
cd "$SCRIPT_DIR/backend"
"$PYTHON" -m bot.main dev > "$SCRIPT_DIR/logs/bot.log" 2>&1 &
BOT_PID=$!
cd "$SCRIPT_DIR"
sleep 3

if kill -0 $BOT_PID 2>/dev/null; then
  echo -e "${GREEN}  Bot agent running (PID $BOT_PID)${NC}"
else
  echo -e "${RED}  Bot agent failed. Check logs/bot.log${NC}"
  cat logs/bot.log | tail -15
  exit 1
fi

# ── Step 4: Frontend ───────────────────────────────────────────────────────────
echo -e "\n${BLUE}[4/4] Starting Frontend on http://localhost:5173 ...${NC}"
# Kill anything on port 5173
lsof -ti tcp:5173 | xargs kill -9 2>/dev/null || true
cd frontend
npm run dev -- --port 5173 > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..
sleep 3

if kill -0 $FRONTEND_PID 2>/dev/null; then
  echo -e "${GREEN}  Frontend running (PID $FRONTEND_PID)${NC}"
else
  echo -e "${RED}  Frontend failed. Check logs/frontend.log${NC}"
  cat logs/frontend.log | tail -15
  exit 1
fi

# ── Ready ──────────────────────────────────────────────────────────────────────
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  All services running!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "  ${GREEN}Frontend:${NC}  http://localhost:5173"
echo -e "  ${GREEN}API:${NC}       http://localhost:8000"
echo -e "  ${GREEN}API Docs:${NC}  http://localhost:8000/docs"
echo -e "  ${GREEN}LiveKit:${NC}   ws://127.0.0.1:7880\n"
echo -e "${YELLOW}Logs:  logs/backend.log | logs/bot.log | logs/frontend.log${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop everything.\n${NC}"

wait
