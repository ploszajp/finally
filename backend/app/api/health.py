from __future__ import annotations

from fastapi import APIRouter

from app.services.state import get_state

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health() -> dict:
    source = get_state().source
    name = "massive" if "massive" in type(source).__name__.lower() else "simulator"
    return {
        "status": "ok",
        "market_data_source": name,
        "tracked_tickers": len(source.get_tickers()),
        "last_success_at": source.last_success_at,
        "last_error": source.last_error,
    }
