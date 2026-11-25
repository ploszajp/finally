import asyncio
import time


async def wait_for(condition, timeout=2.0):
    """Poll until condition() is true. Avoids tests that rely on a fixed sleep."""
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        await asyncio.sleep(0.005)
