"""LiteLLM call wrapper: error mapping and retry. acompletion is replaced; no network."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import litellm
import pytest

from app.llm import client as llm_client
from app.llm.errors import (
    LLM_INVALID_RESPONSE,
    LLM_NOT_CONFIGURED,
    LLM_TIMEOUT,
    LLM_UNAVAILABLE,
    LLMError,
)
from app.llm.schema import LLMResponse

VALID = json.dumps({"message": "ok", "trades": [], "watchlist_changes": []})
MESSAGES = [{"role": "user", "content": "hi"}]


def _response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def fake(monkeypatch):
    """Install a fake acompletion that yields queued results (content string or exception)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    calls: list[dict] = []
    queue: list = []

    async def acompletion(**kwargs):
        calls.append(kwargs)
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _response(item)

    monkeypatch.setattr(llm_client, "acompletion", acompletion)
    return SimpleNamespace(calls=calls, queue=queue)


async def test_success_uses_cerebras_structured_output(fake):
    fake.queue.append(VALID)
    r = await llm_client.call_llm(MESSAGES)
    assert r.message == "ok"
    [kw] = fake.calls
    assert kw["model"] == "openrouter/openai/gpt-oss-120b"
    assert kw["extra_body"] == {"provider": {"order": ["cerebras"]}}
    assert kw["response_format"] is LLMResponse
    assert kw["reasoning_effort"] == "low"
    assert kw["api_key"] == "test-key"
    assert kw["timeout"] == 30.0
    assert kw["messages"] == MESSAGES


async def test_missing_key_is_not_configured(fake, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "   ")
    with pytest.raises(LLMError) as exc:
        await llm_client.call_llm(MESSAGES)
    assert exc.value.code == LLM_NOT_CONFIGURED
    assert fake.calls == []


async def test_invalid_then_valid_retries_once(fake):
    fake.queue.extend(["garbage", VALID])
    assert (await llm_client.call_llm(MESSAGES)).message == "ok"
    assert len(fake.calls) == 2


async def test_invalid_twice_is_invalid_response(fake):
    fake.queue.extend(["garbage", json.dumps({"message": 1}), VALID])
    with pytest.raises(LLMError) as exc:
        await llm_client.call_llm(MESSAGES)
    assert exc.value.code == LLM_INVALID_RESPONSE
    assert len(fake.calls) == 2


@pytest.mark.parametrize(
    "error",
    [TimeoutError(), litellm.Timeout(message="t", model="m", llm_provider="openrouter")],
)
async def test_timeout(fake, error):
    fake.queue.append(error)
    with pytest.raises(LLMError) as exc:
        await llm_client.call_llm(MESSAGES)
    assert exc.value.code == LLM_TIMEOUT


async def test_hanging_call_times_out(fake, monkeypatch):
    monkeypatch.setattr(llm_client, "TIMEOUT_SECONDS", -4.95)  # wait_for gets 0.05 s

    async def hang(**kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr(llm_client, "acompletion", hang)
    with pytest.raises(LLMError) as exc:
        await llm_client.call_llm(MESSAGES)
    assert exc.value.code == LLM_TIMEOUT


@pytest.mark.parametrize(
    "error",
    [
        litellm.AuthenticationError(message="bad key sk-secret", llm_provider="x", model="m"),
        litellm.RateLimitError(message="slow down", llm_provider="x", model="m"),
        litellm.APIConnectionError(message="down", llm_provider="x", model="m"),
        httpx.ConnectError("refused"),
        RuntimeError("anything"),
    ],
)
async def test_provider_errors_are_unavailable_and_not_logged(fake, caplog, error):
    fake.queue.append(error)
    with pytest.raises(LLMError) as exc:
        await llm_client.call_llm(MESSAGES)
    assert exc.value.code == LLM_UNAVAILABLE
    assert "sk-secret" not in caplog.text
    assert "test-key" not in caplog.text
    assert exc.value.__cause__ is None
