# ── Build Stage ───────────────────────────────────────────────────────────────
FROM python:3.14-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml .

# Install dependencies into a virtual environment (no dev extras)
RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python -e "."

# ── Production Stage ──────────────────────────────────────────────────────────
FROM python:3.14-slim AS production

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create log directory
RUN mkdir -p logs

# Use virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# Run database migrations then start the app
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 2"]
