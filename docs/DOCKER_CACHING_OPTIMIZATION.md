# Docker Build Caching Optimization

## Problem

Every Docker build was re-downloading all dependencies (Python packages, npm packages) even when dependencies hadn't changed. This made builds slow and wasted bandwidth.

## Root Cause

1. **Docker layer caching works**, but only if the layer inputs (like `requirements.txt` or `package.json`) are unchanged
2. **Even small changes** to dependency files invalidate the entire cache
3. **Cloud Build** wasn't using BuildKit cache mounts, which persist across builds

## Solution: BuildKit Cache Mounts

We've optimized both Dockerfiles to use **BuildKit cache mounts**, which persist package caches between builds even when dependency files change.

### Backend Dockerfile (`Dockerfile`)

**Before:**
```dockerfile
RUN pip install --no-cache-dir ... torch
RUN pip install --no-cache-dir ... -r requirements.txt
```

**After:**
```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ... torch
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ... -r requirements.txt
```

**Benefits:**
- Pip downloads are cached in `/root/.cache/pip`
- Cache persists even when `requirements.txt` changes
- Only new/updated packages are downloaded

### Frontend Dockerfile (`frontend/Dockerfile`)

**Before:**
```dockerfile
RUN npm install
RUN npm run build
```

**After:**
```dockerfile
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit || npm install --prefer-offline --no-audit
RUN --mount=type=cache,target=/app/node_modules/.cache \
    npm run build
```

**Benefits:**
- NPM packages cached in `/root/.npm`
- Vite build cache cached in `/app/node_modules/.cache`
- Uses `npm ci` for faster, reproducible builds (falls back to `npm install` if no lock file)

### Cloud Build Configuration

**Updated `cloudbuild.backend.yaml` and `cloudbuild.frontend.yaml`:**

```yaml
steps:
  - name: gcr.io/cloud-builders/docker
    env:
      - DOCKER_BUILDKIT=1  # Enable BuildKit
    args:
      - build
      - --build-arg
      - BUILDKIT_INLINE_CACHE=1  # Enable inline cache
      - ...
```

## Performance Impact

### Before Optimization
- **Every build**: Downloads all dependencies (~2-5 minutes)
- **Total build time**: ~5-10 minutes

### After Optimization
- **First build**: Downloads all dependencies (~2-5 minutes) - same as before
- **Subsequent builds**: Reuses cached packages (~30 seconds - 2 minutes)
- **When dependencies change**: Only downloads new/updated packages

### Expected Speedup
- **No dependency changes**: ~80-90% faster builds
- **Minor dependency changes**: ~50-70% faster builds
- **Major dependency changes**: ~20-40% faster builds

## How It Works

1. **BuildKit cache mounts** create persistent cache volumes
2. **Pip/npm** store downloaded packages in these cache volumes
3. **Next build** reuses packages from cache
4. **Only new packages** are downloaded

## Testing Locally

To test with BuildKit locally:

```bash
# Enable BuildKit
export DOCKER_BUILDKIT=1

# Build backend
docker build -t woka-backend -f Dockerfile .

# Build frontend
docker build -t woka-frontend -f frontend/Dockerfile frontend/
```

## Notes

- Cache mounts are **separate from layer caching**
- Cache persists **even when Docker images are removed**
- Cache is **shared across all builds** on the same machine/Cloud Build worker
- Cache can be cleared with: `docker builder prune`

## Troubleshooting

If builds are still slow:

1. **Check BuildKit is enabled**: `docker buildx version`
2. **Clear old cache**: `docker builder prune`
3. **Check cache usage**: `docker system df`
4. **Verify Cloud Build logs** show `DOCKER_BUILDKIT=1`

