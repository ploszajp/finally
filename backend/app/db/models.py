"""Plain records returned by the repository."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Position:
    ticker: str
    quantity: float
    avg_cost: float
    updated_at: str


@dataclass(frozen=True, slots=True)
class Trade:
    id: str
    ticker: str
    side: str
    quantity: float
    price: float
    executed_at: str


@dataclass(frozen=True, slots=True)
class WatchlistEntry:
    ticker: str
    added_at: str


@dataclass(frozen=True, slots=True)
class Snapshot:
    id: str
    total_value: float
    recorded_at: str


@dataclass(frozen=True, slots=True)
class ChatMessage:
    id: str
    role: str
    content: str
    actions: Any | None
    created_at: str
