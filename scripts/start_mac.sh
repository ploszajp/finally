#!/usr/bin/env bash
# Start FinAlly in Docker (macOS/Linux). Idempotent: safe to run repeatedly.
# Usage: ./scripts/start_mac.sh [--build] [--no-open]
set -euo pipefail

IMAGE="finally:latest"
CONTAINER="finally"
VOLUME="finally-data"
PORT="${PORT:-8000}"
URL="http://localhost:${PORT}"

BUILD=0
OPEN=1
for arg in "$@"; do
  case "$arg" in
    --build) BUILD=1 ;;
    --no-open) OPEN=0 ;;
    -h|--help) echo "Usage: $0 [--build] [--no-open]"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker and try again." >&2
  exit 1
fi

if [ "$BUILD" -eq 1 ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building $IMAGE..."
  docker build -t "$IMAGE" .
fi

ENV_ARGS=()
if [ -f .env ]; then
  ENV_ARGS=(--env-file .env)
else
  echo "Warning: .env not found; AI chat needs OPENROUTER_API_KEY (see .env.example)." >&2
fi

# Replace any existing container (running or stopped); the volume is kept.
docker stop "$CONTAINER" >/dev/null 2>&1 || true
docker rm "$CONTAINER" >/dev/null 2>&1 || true

docker run -d \
  --name "$CONTAINER" \
  -p "${PORT}:8000" \
  -v "${VOLUME}:/app/db" \
  ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} \
  "$IMAGE" >/dev/null

echo "Waiting for FinAlly to become healthy..."
HEALTHY=0
for _ in $(seq 1 30); do
  if curl -fsS "${URL}/api/health" >/dev/null 2>&1; then
    HEALTHY=1
    break
  fi
  sleep 1
done

if [ "$HEALTHY" -ne 1 ]; then
  echo "FinAlly did not become healthy within 30s. Check: docker logs $CONTAINER" >&2
  exit 1
fi

echo "FinAlly is running at ${URL}"

if [ "$OPEN" -eq 1 ]; then
  if command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  fi
fi
