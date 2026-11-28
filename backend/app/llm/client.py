"""LiteLLM -> OpenRouter -> Cerebras call with structured outputs."""

from __future__ import annotations

import asyncio
import logging
import os

import litellm
from litellm import acompletion

from .errors import LLM_INVALID_RESPONSE, LLM_NOT_CONFIGURED, LLM_TIMEOUT, LLM_UNAVAILABLE, LLMError
from .schema import InvalidLLMResponseError, LLMResponse, parse_llm_response

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
TIMEOUT_SECONDS = 30.0
MAX_ATTEMPTS = 2  # one retry, only for replies that do not match the schema

litellm.suppress_debug_info = True


def _api_key() -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    return key or None


async def _complete(messages: list[dict], api_key: str) -> str | None:
    response = await asyncio.wait_for(
        acompletion(
            model=MODEL,
            messages=messages,
            response_format=LLMResponse,
            reasoning_effort="low",
            extra_body=EXTRA_BODY,
            api_key=api_key,
            timeout=TIMEOUT_SECONDS,
        ),
        timeout=TIMEOUT_SECONDS + 5,
    )
    return response.choices[0].message.content


async def call_llm(messages: list[dict]) -> LLMResponse:
    """Return the parsed structured reply or raise LLMError with a failure code."""
    api_key = _api_key()
    if api_key is None:
        raise LLMError(LLM_NOT_CONFIGURED)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            content = await _complete(messages, api_key)
        except (TimeoutError, litellm.Timeout):
            logger.warning("LLM call timed out after %ss", TIMEOUT_SECONDS)
            raise LLMError(LLM_TIMEOUT) from None
        except Exception as e:  # noqa: BLE001 - network, auth, rate limit, provider errors
            # Type only: provider messages can echo request details.
            logger.warning("LLM call failed: %s", type(e).__name__)
            raise LLMError(LLM_UNAVAILABLE) from None
        try:
            return parse_llm_response(content)
        except InvalidLLMResponseError as e:
            logger.warning("LLM reply invalid (attempt %d/%d): %s", attempt, MAX_ATTEMPTS, e)
    raise LLMError(LLM_INVALID_RESPONSE)
