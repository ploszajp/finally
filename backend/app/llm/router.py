"""Chat endpoints: POST /api/chat, GET /api/chat/history (planning/API_CHAT.md)."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, StringConstraints

from . import service

router = APIRouter(prefix="/api/chat", tags=["chat"])

MessageText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=service.MAX_MESSAGE_LENGTH),
]


class ChatRequest(BaseModel):
    message: MessageText


@router.post("")
async def post_chat(body: ChatRequest) -> dict:
    return await service.process_chat(body.message)


@router.get("/history")
async def get_history(
    limit: Annotated[
        int, Query(ge=1, le=service.MAX_HISTORY_LIMIT)
    ] = service.DEFAULT_HISTORY_LIMIT,
) -> dict:
    return await asyncio.to_thread(service.get_history, limit)
