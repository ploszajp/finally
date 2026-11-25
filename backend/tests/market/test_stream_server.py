"""SSE over a real uvicorn process, including shutdown with a client connected."""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

BACKEND = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX SIGTERM")
def test_stream_and_shutdown_with_connected_client(tmp_path):
    port = free_port()
    log = tmp_path / "server.log"
    with log.open("w") as out:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.market.sse_app:app",
                "--port",
                str(port),
                "--timeout-graceful-shutdown",
                "1",
            ],
            cwd=BACKEND,
            stdout=out,
            stderr=subprocess.STDOUT,
        )
    try:
        url = f"http://127.0.0.1:{port}/api/stream/prices"
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            deadline = time.monotonic() + 10
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=1):
                        break
                except OSError:
                    assert time.monotonic() < deadline, log.read_text()
                    time.sleep(0.05)

            with client.stream("GET", url) as response:
                assert response.headers["content-type"].startswith("text/event-stream")
                events = []
                lines = response.iter_lines()
                while len(events) < 2:
                    line = next(lines)
                    if line.startswith("data: "):
                        events.append(json.loads(line.removeprefix("data: ")))
                assert "day_change_percent" in events[1]["AAPL"]

                server.terminate()  # the client is still connected
                server.wait(timeout=6)
        assert "LIFESPAN-SHUTDOWN-COMPLETE" in log.read_text()
    finally:
        if server.poll() is None:
            server.kill()
            server.wait()
