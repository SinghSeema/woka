FROM python:3.11-slim AS backend

WORKDIR /app

# System deps for building some Python wheels (httpx, uvicorn extras, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only PyTorch first to avoid downloading CUDA libraries (~2GB+)
# This must be done before installing sentence-transformers
# Increased timeout (300s) and retries (3) for large package downloads
RUN pip install --no-cache-dir --timeout=300 --retries=3 --index-url https://download.pytorch.org/whl/cpu torch

# Copy backend requirements and install
# Increased timeout (300s) and retries (3) for network reliability
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --timeout=300 --retries=3 -r /app/backend/requirements.txt

# Copy backend source
COPY backend /app/backend

# Default envs (can be overridden by host)
ENV PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    PYTHONPATH=/app/backend

# Expose API port
EXPOSE 8000

# Start both the FastAPI backend and the bot worker in one process supervisor.
# For simplicity we use a small shell script; in production you can switch to
# something like supervisord or run separate services.
CMD ["bash", "-lc", "cd /app/backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 & python -m bot.main dev"]

