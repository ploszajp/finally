"""FastAPI application: `uvicorn app.main:app --timeout-graceful-shutdown 2`."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.api import health, portfolio, watchlist
from app.api.errors import register_error_handlers
from app.api.static import register_static
from app.db import init_db
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.services import portfolio as portfolio_service
from app.services import watchlist as watchlist_service
from app.services.state import AppState, set_state

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
SNAPSHOT_INTERVAL_SECONDS = 30.0


def _load_local_env() -> None:
    """Local development only: load <project root>/.env if present, never overriding
    variables already set. In Docker the variables come from --env-file."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_file, override=False)


async def _snapshot_loop(interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(portfolio_service.record_snapshot)
        except Exception:
            logger.exception("Periodic portfolio snapshot failed")


def _chain_shutdown_signals(stop: threading.Event) -> Callable[[], None]:
    """Set `stop` as soon as uvicorn receives a shutdown signal.

    Uvicorn waits for open connections (SSE streams never end on their own) before the
    lifespan shutdown runs, then cancels them after --timeout-graceful-shutdown and logs
    a CancelledError traceback. Wrapping its signal handlers lets the streams end first.
    Returns a function that restores the wrapped handlers.
    """
    if threading.current_thread() is not threading.main_thread():
        return lambda: None  # e.g. TestClient: no signals, nothing to chain
    installed: dict[int, tuple[Any, Any]] = {}
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        previous = signal.getsignal(sig)
        if not callable(previous):
            continue

        def handler(signum: int, frame: Any, previous: Any = previous) -> None:
            stop.set()
            previous(signum, frame)

        signal.signal(sig, handler)
        installed[sig] = (handler, previous)

    def restore() -> None:
        for sig, (handler, previous) in installed.items():
            if signal.getsignal(sig) is handler:
                signal.signal(sig, previous)

    return restore


def _include_chat_router(app: FastAPI) -> None:
    try:
        from app.llm.router import router as chat_router
    except ModuleNotFoundError as e:
        if e.name not in ("app.llm", "app.llm.router"):
            raise
        logger.warning("Chat router not available (app.llm.router missing); /api/chat disabled")
        return
    app.include_router(chat_router)


def create_app(
    db_path: str | Path | None = None,
    static_dir: str | Path | None = None,
    snapshot_interval: float = SNAPSHOT_INTERVAL_SECONDS,
) -> FastAPI:
    _load_local_env()
    cache = PriceCache()
    stop_streams = threading.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        stop_streams.clear()
        restore_signals = _chain_shutdown_signals(stop_streams)
        db = init_db(db_path)
        source = create_market_data_source(cache)
        set_state(AppState(db=db, cache=cache, source=source))
        snapshot_task: asyncio.Task | None = None
        try:
            await source.start(watchlist_service.tracked_tickers())
            # First snapshot after prices exist, so the P&L chart is never empty.
            await asyncio.to_thread(portfolio_service.record_snapshot)
            snapshot_task = asyncio.create_task(_snapshot_loop(snapshot_interval))
            logger.info("FinAlly started (db=%s)", db.path)
            yield
        finally:
            stop_streams.set()
            restore_signals()
            if snapshot_task is not None:
                snapshot_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await snapshot_task
            await source.stop()
            set_state(None)

    app = FastAPI(title="FinAlly", version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(portfolio.router)
    app.include_router(watchlist.router)
    app.include_router(create_stream_router(cache, stop_event=stop_streams))
    _include_chat_router(app)

    # Must stay last: the catch-all route would otherwise shadow API routes.
    if static_dir is None:
        static_dir = os.environ.get("STATIC_DIR", "").strip() or BACKEND_DIR / "static"
    register_static(app, Path(static_dir))
    return app


app = create_app()
