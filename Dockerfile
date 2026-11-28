# syntax=docker/dockerfile:1

# ---------- Stage 1: build the Next.js static export ----------
FROM node:22-slim AS frontend
WORKDIR /frontend

# Install dependencies first so they are cached between source changes.
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build && test -f out/index.html


# ---------- Stage 2: Python runtime ----------
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    STATIC_DIR=/app/static \
    DB_PATH=/app/db/finally.db

WORKDIR /app

# Dependencies only (cached layer), then the project itself. The uv cache
# lives in a BuildKit cache mount so it is not baked into the image (~350 MB).
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY --from=frontend /frontend/out ./static

# Non-root user; /app/db is the volume mount point (a fresh named volume
# inherits this ownership).
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/db \
    && chown -R app:app /app/db
USER app

EXPOSE 8000
VOLUME ["/app/db"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "2"]
