"""Request bodies. Responses are plain dicts shaped as documented in planning/API.md."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TradeRequest(BaseModel):
    ticker: str
    quantity: float = Field(allow_inf_nan=False)
    side: Literal["buy", "sell"]

    @field_validator("side", mode="before")
    @classmethod
    def _lower_side(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v


class WatchlistAddRequest(BaseModel):
    ticker: str
