"""Integration test harness: the real FastAPI app (app.main:app) in a uvicorn subprocess.

Each server gets its own temporary SQLite file (DB_PATH), the GBM simulator
(MASSIVE_API_KEY empty) and the deterministic mock LLM (LLM_MOCK=true). Tests talk
to it over HTTP with httpx, exactly like the frontend does, so db + services + api +
market data + LLM mock are exercised together.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

BACKEND = Path(__file__).resolve().parents[2]
DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class Server:
    """A running app process bound to one database file."""

    db_path: Path
    port: int
    process: subprocess.Popen
    log_path: Path

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def log(self) -> str:
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


def start_server(db_path: Path, log_path: Path, extra_env: dict[str, str] | None = None) -> Server:
    port = _free_port()
    env = os.environ.copy()
    # Explicit values win over the project-root .env (python-dotenv never overrides).
    env.update(
        {
            "DB_PATH": str(db_path),
            "LLM_MOCK": "true",
            "MASSIVE_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            # API-only: these tests do not need the static frontend.
            "STATIC_DIR": str(db_path.parent / "no-static"),
        }
    )
    env.update(extra_env or {})
    out = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--timeout-graceful-shutdown",
            "1",
        ],
        cwd=BACKEND,
        env=env,
        stdout=out,
        stderr=subprocess.STDOUT,
    )
    out.close()
    server = Server(db_path=db_path, port=port, process=process, log_path=log_path)

    deadline = time.monotonic() + 20
    with httpx.Client(timeout=2.0, trust_env=False) as client:
        while True:
            if process.poll() is not None:
                pytest.fail(f"server exited with {process.returncode}:\n{server.log()}")
            try:
                if client.get(f"{server.base_url}/api/health").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if time.monotonic() > deadline:
                server.stop()
                pytest.fail(f"server did not become healthy:\n{server.log()}")
            time.sleep(0.1)
    return server


@pytest.fixture
def server_factory(tmp_path) -> Iterator:
    """Start servers on demand (e.g. twice on one DB to test persistence); all are stopped."""
    servers: list[Server] = []

    def factory(db_path: Path | None = None, **extra_env: str) -> Server:
        path = db_path or tmp_path / "finally.db"
        s = start_server(path, tmp_path / f"server-{len(servers)}.log", extra_env)
        servers.append(s)
        return s

    yield factory
    for s in servers:
        s.stop()


@pytest.fixture
def server(server_factory) -> Server:
    """A fresh app with a brand-new database."""
    return server_factory()


@pytest.fixture
def client(server) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=server.base_url, timeout=10.0, trust_env=False) as c:
        yield c


def read_sse_events(base_url: str, count: int, timeout: float = 10.0) -> list[dict]:
    """Open the SSE stream, collect `count` data events, then disconnect."""
    events: list[dict] = []
    with httpx.Client(timeout=timeout, trust_env=False) as c:
        with c.stream("GET", f"{base_url}/api/stream/prices") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            deadline = time.monotonic() + timeout
            for line in response.iter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line.removeprefix("data:").strip()))
                    if len(events) >= count:
                        break
                assert time.monotonic() < deadline, f"only {len(events)} SSE events"
    return events


def wait_for(predicate, timeout: float = 5.0, interval: float = 0.1, message: str = ""):
    """Poll `predicate` until it returns a truthy value; return that value."""
    deadline = time.monotonic() + timeout
    while True:
        result = predicate()
        if result:
            return result
        if time.monotonic() > deadline:
            raise AssertionError(message or "condition not met in time")
        time.sleep(interval)
