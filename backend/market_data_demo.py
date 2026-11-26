"""Live terminal demo of the market data subsystem.

    uv run market_data_demo.py                 # run until Ctrl+C
    uv run market_data_demo.py --duration 30   # stop after 30 seconds

Uses the same factory as the app: the simulator by default, or Massive if
MASSIVE_API_KEY is set in the environment.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections import deque
from collections.abc import Sequence

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.market import PriceCache, PriceUpdate, create_market_data_source
from app.market.seed_prices import SEED_PRICES

SPARK_CHARS = "▁▂▃▄▅▆▇█"
HISTORY_LENGTH = 40
# A single-update move this large (percent) is listed under "Notable moves".
NOTABLE_MOVE_PERCENT = 1.0
STYLES = {"up": "green", "down": "red", "flat": "dim"}
ARROWS = {"up": "▲", "down": "▼", "flat": "•"}


def sparkline(values: Sequence[float]) -> str:
    """Render values as block characters scaled between their min and max."""
    if not values:
        return ""
    low, high = min(values), max(values)
    if high == low:
        return SPARK_CHARS[0] * len(values)
    scale = (len(SPARK_CHARS) - 1) / (high - low)
    return "".join(SPARK_CHARS[round((v - low) * scale)] for v in values)


class DemoState:
    """Price history and notable moves, built up from cache snapshots."""

    def __init__(self) -> None:
        self.history: dict[str, deque[float]] = {}
        self.moves: deque[PriceUpdate] = deque(maxlen=5)
        self._seen: dict[str, PriceUpdate] = {}

    def record(self, prices: dict[str, PriceUpdate]) -> None:
        for ticker, update in prices.items():
            if self._seen.get(ticker) is update:
                continue
            self._seen[ticker] = update
            self.history.setdefault(ticker, deque(maxlen=HISTORY_LENGTH)).append(update.price)
            if abs(update.change_percent) >= NOTABLE_MOVE_PERCENT:
                self.moves.appendleft(update)


def render(prices: dict[str, PriceUpdate], state: DemoState, title: str) -> Group:
    table = Table(title=title, expand=False)
    table.add_column("Ticker", style="bold")
    table.add_column("Price", justify="right")
    table.add_column("Tick %", justify="right")
    table.add_column("Day %", justify="right")
    table.add_column("History", width=HISTORY_LENGTH, no_wrap=True)

    for ticker, update in prices.items():
        style = STYLES[update.direction]
        day = update.day_change_percent
        day_style = "green" if day > 0 else "red" if day < 0 else "dim"
        table.add_row(
            ticker,
            Text(f"{ARROWS[update.direction]} {update.price:,.2f}", style=style),
            Text(f"{update.change_percent:+.2f}%", style=style),
            Text(f"{day:+.2f}%", style=day_style),
            Text(sparkline(state.history.get(ticker, ())), style=day_style),
        )

    lines = Text()
    for move in state.moves:
        clock = time.strftime("%H:%M:%S", time.localtime(move.timestamp))
        lines.append(
            f"{clock}  {move.ticker:<6} {move.change_percent:+.2f}% to {move.price:,.2f}\n",
            style=STYLES[move.direction],
        )
    if not state.moves:
        lines.append("None yet", style="dim")

    return Group(table, Panel(lines, title="Notable moves", expand=False))


async def run(duration: float | None, console: Console | None = None) -> None:
    cache = PriceCache()
    source = create_market_data_source(cache)
    await source.start(list(SEED_PRICES))
    title = f"FinAlly market data ({type(source).__name__}), Ctrl+C to quit"
    state = DemoState()
    deadline = None if duration is None else time.monotonic() + duration

    try:
        with Live(console=console, auto_refresh=False) as live:
            while deadline is None or time.monotonic() < deadline:
                prices = cache.get_all()
                state.record(prices)
                live.update(render(prices, state, title), refresh=True)
                await asyncio.sleep(0.25)
    finally:
        await source.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Live market data terminal demo")
    parser.add_argument("--duration", type=float, help="seconds to run (default: until Ctrl+C)")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.duration))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
