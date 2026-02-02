# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
# Use npm install instead of npm ci since package-lock.json might not exist
RUN npm install

# Copy source code
COPY . .

# Build args for Vite environment variables (baked into JS at build time)
ARG VITE_API_BASE_URL
ARG VITE_LIVEKIT_URL

# Set as environment variables for Vite to pick up during build
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_LIVEKIT_URL=${VITE_LIVEKIT_URL}

# Build the app
RUN npm run build

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

