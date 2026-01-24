#!/bin/bash
# Run script for Woka Wellness Voice AI Assistant

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Woka Wellness Voice AI Assistant ===${NC}\n"

# Check if venv exists
if [ ! -d ".pipebot" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv .pipebot
fi

# Activate venv
source .pipebot/bin/activate

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Warning: .env file not found. Creating from .env.example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}Please edit .env with your API keys before running!${NC}"
    exit 1
fi

# Install backend dependencies if needed
echo -e "${BLUE}Checking backend dependencies...${NC}"
cd backend
pip install -q -r requirements.txt
cd ..

# Install frontend dependencies if needed
echo -e "${BLUE}Checking frontend dependencies...${NC}"
cd frontend
if [ ! -d "node_modules" ]; then
    npm install
fi
cd ..

echo -e "\n${GREEN}Starting services...${NC}\n"
echo -e "${YELLOW}Note: Make sure LiveKit server is running!${NC}\n"

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Stopping services...${NC}"
    kill $BACKEND_PID $BOT_PID $FRONTEND_PID 2>/dev/null || true
    exit
}

trap cleanup SIGINT SIGTERM

# Start backend API
echo -e "${BLUE}Starting Backend API on http://localhost:8000${NC}"
cd backend
source ../.pipebot/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

sleep 2

# Start bot worker
echo -e "${BLUE}Starting Bot Worker...${NC}"
cd backend
source ../.pipebot/bin/activate
# Load environment variables from .env file (handle spaces around =)
set -a
source <(grep -v '^#' ../.env | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*=[[:space:]]*/=/' | sed 's/[[:space:]]*$//')
set +a
python -m bot.main dev &
BOT_PID=$!
cd ..

sleep 2

# Start frontend
echo -e "${BLUE}Starting Frontend on http://localhost:5173${NC}"
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo -e "\n${GREEN}All services started!${NC}\n"
echo -e "${GREEN}Frontend:${NC} http://localhost:5173"
echo -e "${GREEN}API:${NC} http://localhost:8000"
echo -e "${GREEN}API Docs:${NC} http://localhost:8000/docs\n"
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}\n"

# Wait for all processes
wait

