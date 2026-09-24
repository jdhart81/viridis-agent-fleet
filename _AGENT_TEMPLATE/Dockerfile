# Multi-stage Dockerfile for Viridis Agents
#
# Usage:
#   docker build -t my-agent .
#   docker run -e AGENT_NAME=my-agent -e LOG_LEVEL=INFO -p 8080:8080 my-agent
#

# ============================================================================
# Stage 1: Builder
# ============================================================================

FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ============================================================================
# Stage 2: Runtime
# ============================================================================

FROM python:3.11-slim

# Set metadata
LABEL maintainer="justin@viridis.earth"
LABEL org.opencontainers.image.source="https://github.com/viridis-earth/agents"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/root/.local/bin:$PATH \
    AGENT_NAME=agent \
    LOG_LEVEL=INFO \
    HOST=0.0.0.0 \
    PORT=8080

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 agent && chown -R agent:agent /app
USER agent

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose port
EXPOSE ${PORT}

# Run FastAPI adapter
CMD ["python", "-m", "uvicorn", "adapters.fastapi_server:app", \
     "--host", "0.0.0.0", "--port", "8080"]
