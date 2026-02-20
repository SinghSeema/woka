# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
# Using BuildKit cache mount to cache npm packages between builds
# This cache persists even when package.json changes
# Use npm ci for faster, reproducible builds if package-lock.json exists
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit || npm install --prefer-offline --no-audit

# Copy source code
COPY . .

# Build args for Vite environment variables (baked into JS at build time)
ARG VITE_API_BASE_URL
ARG VITE_LIVEKIT_URL

# Set as environment variables for Vite to pick up during build
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_LIVEKIT_URL=${VITE_LIVEKIT_URL}

# Build the app
# Cache node_modules/.cache for Vite build cache
RUN --mount=type=cache,target=/app/node_modules/.cache \
    npm run build

# Production stage - serve static files
FROM nginx:alpine

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config (optional - for SPA routing)
RUN echo 'server { \
    listen 80; \
    server_name _; \
    root /usr/share/nginx/html; \
    index index.html; \
    location / { \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

