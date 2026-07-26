"""LLMSolverAdapter tests - fake transport, no network, provider-swappable."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.llm_solver import (  # noqa: E402
    MAX_REVIEW_OUTPUT_TOKENS,
    MAX_SOLVE_OUTPUT_TOKENS,
    LLMSolverAdapter,
    conservative_request_cost_usd,
    openai_transport,
)
from src.core import build  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def fake_transport(responses):
    calls = []

    async def _call(payload):
        calls.append(payload)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    _call.calls = calls
    return _call


def test_solve_returns_content_and_physics():
    t = fake_transport(["the answer"])
    adapter = LLMSolverAdapter(t)
    out = run(adapter.solve({"problem": "p", "subtask": "s"}))
    assert out["content"] == "the answer"
    assert out["power_w"] > 0 and out["duration_s"] > 0
    assert "Subtask: s" in t.calls[0]["prompt"]
    assert t.calls[0]["max_output_tokens"] == MAX_SOLVE_OUTPUT_TOKENS


def test_review_parses_json_and_bounds_score():
    adapter = LLMSolverAdapter(fake_transport(
        [json.dumps({"score": 0.8, "critique": "fine"})]))
    out = run(adapter.review({"subtask": "s", "content": "c"}))
    assert out["score"] == 0.8
    assert adapter._transport.calls[0]["max_output_tokens"] == \
        MAX_REVIEW_OUTPUT_TOKENS

    for bad in ["not json", json.dumps({"score": 7}),
                json.dumps({"score": "high"}), json.dumps({})]:
        adapter = LLMSolverAdapter(fake_transport([bad]))
        out = run(adapter.review({"subtask": "s", "content": "c"}))
        assert out["score"] == 0.0


def test_adapter_composes_with_hive_core():
    def mk(answer, score):
        # solve returns answer; review returns a JSON score
        return fake_transport([answer, json.dumps({"score": score}),
                               json.dumps({"score": score})])

    solvers = {
        "llm-a": {"adapter": LLMSolverAdapter(mk("alpha analysis", 0.9)),
                  "price_minor": 100},
        "llm-b": {"adapter": LLMSolverAdapter(mk("beta analysis", 0.9)),
                  "price_minor": 100},
    }
    core = build(solvers=solvers)
    res = run(core.process({"action": "solve", "problem": "compare",
                            "budget_minor": 500, "seed": 1}))
    assert res["status"] == "ok"
    assert res["data"]["synthesis"]["sections"]


def test_transport_must_be_callable():
    try:
        LLMSolverAdapter("not-callable")
        assert False
    except TypeError:
        pass


def test_openai_key_is_checked_only_at_call_time(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    transport = openai_transport()
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY required"):
        run(transport({
            "instructions": "i", "prompt": "p",
            "max_output_tokens": 1,
        }))


def test_cost_bound_is_conservative_and_small():
    solve = conservative_request_cost_usd(MAX_SOLVE_OUTPUT_TOKENS)
    review = conservative_request_cost_usd(MAX_REVIEW_OUTPUT_TOKENS)
    assert 0 < review < solve < 0.01
