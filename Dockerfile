# ── Stage 1: Dependency builder ──────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS builder

LABEL org.opencontainers.image.title="Senten Builder"
LABEL org.opencontainers.image.description="Build stage: installs Python dependencies"

WORKDIR /build

# Install build tools needed for some compiled extensions
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ── Stage 2: Production runtime ──────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="Senten"
LABEL org.opencontainers.image.description="Self-hosted DeepL translation frontend"

# dumb-init: correct signal handling (PID 1)
# Remove pip/setuptools/wheel from runtime image — not needed at runtime,
# and eliminates CVEs in those packages (e.g. CVE-2026-23949, CVE-2026-24049)
RUN apt-get update \
 && apt-get install -y --no-install-recommends dumb-init \
 && rm -rf /var/lib/apt/lists/* \
 && pip uninstall -y pip setuptools wheel 2>/dev/null || true

WORKDIR /app

# Create non-root user/group
RUN groupadd -g 1000 appgroup \
 && useradd -u 1000 -g appgroup -s /sbin/nologin -M appuser

# Copy installed Python packages from builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Copy application source (respects .dockerignore)
COPY --chown=appuser:appgroup . .

# Ensure the data directory exists (SQLite + logs)
RUN mkdir -p /app/data && chown appuser:appgroup /app/data

USER appuser

EXPOSE 8000

ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Log directory inside the writable /app/data volume
ENV LOG_DIR=/app/data

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

ENTRYPOINT ["dumb-init", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
