"""LLM-backed SolverAdapter - OpenAI default, provider-swappable.

Vendor policy (standing, 2026-07-20): agent-economy-facing work is
OpenAI-backed by default and always provider-swappable. This adapter takes
an injected async ``transport(payload) -> str`` so the provider is a
constructor argument, not a hard dependency - and tests run with a fake
transport, no network.

The adapter never touches the network at import time and raises loudly if
constructed without a transport or API key (FS5: a bad adapter must not
brick boot - construct lazily at wiring time, not module import).
"""

from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable, Dict, Optional

Transport = Callable[[Dict[str, Any]], Awaitable[str]]

DEFAULT_MODEL = os.getenv("HIVE_LLM_MODEL", "gpt-5-mini-2025-08-07")
DEFAULT_PROVIDER = os.getenv("HIVE_LLM_PROVIDER", "openai")
MAX_PROMPT_CHARS = 20_000
MAX_SOLVE_OUTPUT_TOKENS = 2_048
MAX_REVIEW_OUTPUT_TOKENS = 256

# Pinned 2026-07-25 from the official GPT-5 mini model page. The gateway
# accepts only this priced profile so its $5 service margin cannot silently
# disappear when somebody changes HIVE_LLM_MODEL.
OPENAI_PRICE_USD_PER_MILLION = {
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-5-mini-2025-08-07": {"input": 0.25, "output": 2.00},
}

SOLVE_INSTRUCTIONS = (
    "You are one solver inside a hive of independent solvers. Attack the "
    "subtask directly and completely. Return ONLY your best answer text."
)
REVIEW_INSTRUCTIONS = (
    "You are an adversarial reviewer inside a hive. You did NOT write this "
    "contribution. Try to refute it. Return ONLY a JSON object "
    '{"score": <float 0..1>, "critique": "<one paragraph>"} where score '
    "reflects correctness and completeness for the stated subtask."
)


def openai_transport(api_key: Optional[str] = None,
                     model: str = DEFAULT_MODEL,
                     base_url: str = "https://api.openai.com/v1") -> Transport:
    """Build the default OpenAI transport.

    The key and httpx are both required only when a solver actually calls the
    provider. Gateway boot therefore stays side-effect free and testable.
    """
    if model not in OPENAI_PRICE_USD_PER_MILLION:
        raise RuntimeError(
            f"unsupported HIVE_LLM_MODEL cost profile: {model!r}")

    async def _call(payload: Dict[str, Any]) -> str:
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY required for OpenAI solver call")
        prompt = str(payload.get("prompt", ""))
        if len(prompt) > MAX_PROMPT_CHARS:
            raise RuntimeError(
                f"solver prompt exceeds {MAX_PROMPT_CHARS} character cap")
        requested = payload.get("max_output_tokens",
                                MAX_SOLVE_OUTPUT_TOKENS)
        if isinstance(requested, bool) or not isinstance(requested, int):
            raise RuntimeError("max_output_tokens must be an integer")
        max_output_tokens = min(
            max(1, requested), MAX_SOLVE_OUTPUT_TOKENS)
        import httpx  # imported lazily: no boot-time dependency (FS5)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": [
                    {"role": "system", "content": payload["instructions"]},
                    {"role": "user", "content": prompt}],
                    "max_completion_tokens": max_output_tokens},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    return _call


def conservative_request_cost_usd(max_output_tokens: int,
                                  model: str = DEFAULT_MODEL) -> float:
    """Upper bound for one capped request under the pinned cost profile.

    Treat every input character as a token. This is intentionally more
    conservative than ordinary text tokenization.
    """
    rates = OPENAI_PRICE_USD_PER_MILLION[model]
    return (
        MAX_PROMPT_CHARS * rates["input"]
        + max_output_tokens * rates["output"]
    ) / 1_000_000


class LLMSolverAdapter:
    """SolverAdapter protocol (solve/review) over any injected transport."""

    def __init__(self, transport: Transport, *,
                 power_w: float = 350.0, seconds_per_call: float = 20.0,
                 bit_ops_per_call: float = 1e15,
                 grid_g_per_kwh: float = 400.0) -> None:
        if not callable(transport):
            raise TypeError("transport must be an async callable")
        self._transport = transport
        self._physics = {"power_w": power_w,
                         "duration_s": seconds_per_call,
                         "bit_ops": bit_ops_per_call,
                         "grid_g_per_kwh": grid_g_per_kwh}

    async def solve(self, task: Dict[str, Any]) -> Dict[str, Any]:
        content = await self._transport({
            "instructions": SOLVE_INSTRUCTIONS,
            "prompt": (f"Problem: {task.get('problem', '')}\n"
                       f"Subtask: {task.get('subtask', '')}"),
            "max_output_tokens": MAX_SOLVE_OUTPUT_TOKENS,
        })
        return {"content": str(content), **self._physics}

    async def review(self, req: Dict[str, Any]) -> Dict[str, Any]:
        raw = await self._transport({
            "instructions": REVIEW_INSTRUCTIONS,
            "prompt": (f"Subtask: {req.get('subtask', '')}\n"
                       f"Contribution:\n{req.get('content', '')}"),
            "max_output_tokens": MAX_REVIEW_OUTPUT_TOKENS,
        })
        try:
            parsed = json.loads(raw)
            score = float(parsed.get("score"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"score": 0.0, "critique": "unparseable review output"}
        if not 0.0 <= score <= 1.0 or score != score:
            return {"score": 0.0, "critique": "score out of bounds"}
        return {"score": score, "critique": str(parsed.get("critique", ""))}
