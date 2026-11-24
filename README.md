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

```bash
cp .env.example .env        # add your OPENROUTER_API_KEY
./scripts/start_mac.sh      # Windows: .\scripts\start_windows.ps1
```

Then open http://localhost:8000.

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
