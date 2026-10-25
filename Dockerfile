# Stage 1: Build & Dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir build && \
    python -m build --wheel --no-isolation

# Stage 2: Hardened Runtime Container
FROM python:3.12-slim AS runner

# Security: Dedicated Non-Root User & Group
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /bin/bash -m appuser

WORKDIR /app

# Install runtime dependencies
COPY pyproject.toml .
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /tmp/*.whl && \
    rm -rf /tmp/*.whl

# Copy application source & config
COPY src/ /app/src/
COPY data/ /app/data/
COPY .env.example /app/.env.example

# Create storage directories and set ownership to non-root appuser
RUN mkdir -p /app/storage /app/storage/chroma_db /app/storage/documents && \
    chown -R appuser:appuser /app

# Switch to unprivileged non-root user
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    AEGIS_HOST=0.0.0.0 \
    AEGIS_PORT=8000 \
    AEGIS_ENVIRONMENT=production \
    AEGIS_DATABASE_URL=sqlite:////app/storage/aegis.db \
    AEGIS_CHROMA_PERSIST_DIR=/app/storage/chroma_db \
    AEGIS_STORAGE_DIR=/app/storage/documents

EXPOSE 8000

# Container Orchestration Health Check
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

ENTRYPOINT ["python", "-m", "uvicorn", "aegis.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
