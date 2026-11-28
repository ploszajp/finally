"""Shutdown with an SSE client connected must end streams cleanly (no CancelledError)."""

from __future__ import annotations

import logging
import signal
import socket
import threading
import time

import httpx
import pytest
import uvicorn

import app.main as main_module


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_chain_shutdown_signals_sets_event_and_restores():
    calls = []

    def original(signum, frame):
        calls.append(signum)

    before = signal.signal(signal.SIGTERM, original)
    try:
        stop = threading.Event()
        restore = main_module._chain_shutdown_signals(stop)
        handler = signal.getsignal(signal.SIGTERM)
        assert handler is not original
        handler(signal.SIGTERM, None)
        assert stop.is_set()
        assert calls == [signal.SIGTERM]  # the wrapped handler still runs
        restore()
        assert signal.getsignal(signal.SIGTERM) is original
    finally:
        signal.signal(signal.SIGTERM, before)


def test_chain_shutdown_signals_is_noop_off_main_thread():
    result = []
    t = threading.Thread(target=lambda: result.append(main_module._chain_shutdown_signals(None)))
    t.start()
    t.join()
    result[0]()  # restore is a harmless no-op


def test_sigint_with_open_sse_stream_shuts_down_cleanly(tmp_path, make_app, caplog):
    make_app(tmp_path / "unused.db", tmp_path)  # installs the deterministic FakeSource
    app = main_module.create_app(db_path=tmp_path / "x.db", static_dir=tmp_path)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, port=port, timeout_graceful_shutdown=3, log_config=None)
    )
    outcome: dict = {}

    def client() -> None:
        while not server.started:
            time.sleep(0.02)
        url = f"http://127.0.0.1:{port}/api/stream/prices"
        try:
            with httpx.stream("GET", url, timeout=10, trust_env=False) as r:
                for line in r.iter_lines():
                    if line.startswith("data:") and "sent_at" not in outcome:
                        outcome["sent_at"] = time.monotonic()
                        signal.raise_signal(signal.SIGINT)
            outcome["clean"] = True
        except Exception as e:  # noqa: BLE001 - reported by the assertion below
            outcome["error"] = repr(e)

    caplog.set_level(logging.INFO)
    thread = threading.Thread(target=client, daemon=True)
    thread.start()
    # uvicorn installs signal handlers only on the main thread, which pytest runs on.
    with pytest.raises(KeyboardInterrupt):  # uvicorn re-raises the captured SIGINT at exit
        server.run()
    elapsed = time.monotonic() - outcome["sent_at"]
    thread.join(5)

    assert outcome.get("clean"), outcome
    assert elapsed < 2, f"shutdown waited for the graceful timeout ({elapsed:.2f}s)"
    assert "Exception in ASGI application" not in caplog.text
    assert "timeout graceful shutdown exceeded" not in caplog.text
