# FinAlly — AI Trading Workstation

An AI-powered trading workstation: live-streaming market data, a simulated $10,000 portfolio, and an LLM chat assistant that can analyze your positions and execute trades in natural language. Think Bloomberg terminal with an AI copilot.

Built entirely by coding agents as the capstone project for an agentic AI coding course.

## Features

- Live price streaming (SSE) with green/red flash animations and sparklines
- Market orders with instant fills, no fees
- Portfolio heatmap, P&L chart, and positions table
- AI chat assistant that can trade and manage your watchlist
- Built-in market simulator, so no market data API key is needed

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js + TypeScript (static export), Tailwind CSS |
| Backend | FastAPI (Python, managed with `uv`) |
| Database | SQLite (`db/finally.db`, created on startup) |
| AI | LiteLLM → OpenRouter (`gpt-oss-120b` on Cerebras) |
| Deployment | One Docker container on port 8000 |

## Quick Start

Requires Docker (Docker Desktop on macOS/Windows).

```bash
cp .env.example .env              # add your OPENROUTER_API_KEY
./scripts/start_mac.sh            # macOS/Linux
```

```powershell
Copy-Item .env.example .env       # add your OPENROUTER_API_KEY
.\scripts\start_windows.ps1       # Windows PowerShell
```

The script builds the image on first run, starts the container and opens http://localhost:8000.

| Action | macOS/Linux | Windows |
|---|---|---|
| Start | `./scripts/start_mac.sh` | `.\scripts\start_windows.ps1` |
| Rebuild after code changes | `./scripts/start_mac.sh --build` | `.\scripts\start_windows.ps1 -Build` |
| Start without opening a browser | `--no-open` | `-NoOpen` |
| Stop (data kept) | `./scripts/stop_mac.sh` | `.\scripts\stop_windows.ps1` |

If PowerShell blocks the script, run it with `powershell -ExecutionPolicy Bypass -File .\scripts\start_windows.ps1`.

Your portfolio lives in the Docker volume `finally-data` and survives restarts and rebuilds. To start over: stop the app, then `docker volume rm finally-data`.

### Docker Compose (alternative)

```bash
docker compose up -d --build      # start
docker compose down               # stop, keeps the volume (down -v deletes it)
```

### Plain Docker

```bash
docker build -t finally .
docker run -d --name finally -p 8000:8000 -v finally-data:/app/db --env-file .env finally
```

### Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes (for chat) | LLM access via OpenRouter |
| `MASSIVE_API_KEY` | No | Real market data (Polygon.io); the simulator is used if unset |
| `LLM_MOCK` | No | `true` returns deterministic mock LLM responses for tests |

## Project Layout

```
frontend/   Next.js app
backend/    FastAPI app, DB schema and seed data
planning/   Specs and docs that agents share
scripts/    Docker start/stop scripts
test/       Playwright E2E tests
db/         SQLite volume mount
```

## Documentation

The full specification is in [`planning/PLAN.md`](planning/PLAN.md).

## License

See [LICENSE](LICENSE).
