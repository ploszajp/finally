"""Parsing of structured LLM replies."""

from __future__ import annotations

import json

import pytest

from app.llm.schema import InvalidLLMResponseError, LLMResponse, parse_llm_response


def test_full_reply():
    r = parse_llm_response(
        json.dumps(
            {
                "message": "Done",
                "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 2.5}],
                "watchlist_changes": [{"ticker": "PYPL", "action": "add"}],
            }
        )
    )
    assert r.message == "Done"
    assert r.trades[0].ticker == "AAPL" and r.trades[0].quantity == 2.5
    assert r.watchlist_changes[0].action == "add"


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "hi", "trades": [], "watchlist_changes": []},
        {"message": "hi"},
        {"message": "hi", "trades": None, "watchlist_changes": None},
    ],
)
def test_empty_missing_or_null_arrays_become_empty(payload):
    r = parse_llm_response(json.dumps(payload))
    assert r == LLMResponse(message="hi", trades=[], watchlist_changes=[])


def test_code_fence_is_tolerated():
    r = parse_llm_response('```json\n{"message": "x", "trades": [], "watchlist_changes": []}\n```')
    assert r.message == "x"


@pytest.mark.parametrize(
    "content",
    [
        None,
        "",
        "   ",
        "not json",
        "[1, 2]",
        '{"trades": []}',
        '{"message": "x", "trades": [{"ticker": "AAPL", "side": "hold", "quantity": 1}]}',
        '{"message": "x", "trades": [{"ticker": "AAPL", "side": "buy"}]}',
        '{"message": "x", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": "lots"}]}',
        '{"message": "x", "watchlist_changes": [{"ticker": "A", "action": "watch"}]}',
        '{"message": "x", "extra": 1}',
        '{"message": "x", "trades": {"ticker": "AAPL"}}',
    ],
)
def test_malformed_replies_raise(content):
    with pytest.raises(InvalidLLMResponseError):
        parse_llm_response(content)


def test_json_schema_is_strict():
    schema = LLMResponse.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"message", "trades", "watchlist_changes"}
