#!/usr/bin/env bash
# Stop and remove the FinAlly container (macOS/Linux). The finally-data
# volume is kept, so the portfolio persists. Idempotent.
set -euo pipefail

CONTAINER="finally"

if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
  docker stop "$CONTAINER" >/dev/null
  docker rm "$CONTAINER" >/dev/null
  echo "FinAlly stopped. Data volume 'finally-data' kept."
else
  echo "FinAlly is not running."
fi
