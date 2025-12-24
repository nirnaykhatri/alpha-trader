# ==============================================================================
# Trading Bot Dockerfile for Azure Container Apps
# ==============================================================================
#
# Multi-stage build for optimized production image:
#   - Stage 1: Build stage with dev dependencies
#   - Stage 2: Production stage with minimal footprint
#
# Build:
#   docker build -t trading-bot:latest .
#
# Run locally:
#   docker run -p 8080:8080 \
#     -e AZURE_CLIENT_ID=<managed-identity-client-id> \
#     -e AZURE_KEYVAULT_URL=https://<keyvault>.vault.azure.net \
#     trading-bot:latest
#
# ==============================================================================

# ==============================================================================
# Stage 1: Build Stage
# ==============================================================================
FROM python:3.11-slim AS builder

# Build arguments for metadata
ARG BUILD_DATE
ARG VCS_REF

# Labels for container registry
LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.title="Alpha Trader Bot" \
      org.opencontainers.image.description="Production trading bot for Azure Container Apps" \
      org.opencontainers.image.vendor="Alpha Trader"

# Set build environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies with optimizations
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# ==============================================================================
# Stage 2: Production Stage
# ==============================================================================
FROM python:3.11-slim AS production

# Security: Run as non-root user
RUN groupadd -r botuser && useradd -r -g botuser botuser

# Set production environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    # Azure Container Apps uses port 8080 by default
    PORT=8080 \
    # Python optimization
    PYTHONOPTIMIZE=2

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Required for healthcheck
    curl \
    # Required for timezone data
    tzdata \
    # CA certificates for HTTPS
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=botuser:botuser src/ ./src/
COPY --chown=botuser:botuser config/ ./config/
COPY --chown=botuser:botuser run_bot.py ./

# Create directories for logs and data with proper permissions
RUN mkdir -p /app/logs /app/data && \
    chown -R botuser:botuser /app/logs /app/data

# Switch to non-root user
USER botuser

# Expose webhook port
EXPOSE 8080

# Health check for Container Apps liveness probe
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default command - run the trading bot
# Container Apps will set environment variables for Azure services
CMD ["python", "run_bot.py"]
