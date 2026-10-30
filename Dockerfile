# ============================================================================
# Stage 1: Build Frontend SPA
# ============================================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ============================================================================
# Stage 2: Production Runtime
# ============================================================================
FROM python:3.12-slim

# Install system dependencies: ffprobe (via ffmpeg), mediainfo, tzdata, gosu
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    mediainfo \
    tzdata \
    ca-certificates \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

ENV PUID=1000 \
    PGID=1000 \
    TZ=Etc/UTC \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

# Install Python requirements
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source code
COPY backend/ ./backend/

# Copy built frontend assets from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Persist data directory and volume mount targets
RUN mkdir -p /app/data /media /downloads

EXPOSE 9494

VOLUME ["/app/data", "/media", "/downloads"]

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9494"]
