"""Thin MCP adapter for the Viridis hive orchestrator."""

import asyncio
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # stdlib smoke shim
    class FastMCP:
        def __init__(self, name, **kwargs):
            self.name, self.tools = name, {}

        def tool(self, *args, **kwargs):
            def decorator(fn):
                self.tools[fn.__name__] = fn
                return fn
            return decorator

        def run(self):
            raise RuntimeError("mcp SDK is required to serve")

from adapters.llm_solver import (
    DEFAULT_MODEL,
    MAX_PROMPT_CHARS,
    MAX_REVIEW_OUTPUT_TOKENS,
    MAX_SOLVE_OUTPUT_TOKENS,
    LLMSolverAdapter,
    conservative_request_cost_usd,
    openai_transport,
)
from src.core import build

SERVICE_PRICE_MINOR = 500
FREE_SOLVES_PER_DAY = 3
SOLVER_PRICE_MINOR = 25
SOLVER_IDS = ("hive-reasoner-a", "hive-reasoner-b", "hive-reasoner-c")
MAX_PUBLIC_SUBTASKS = 4
MAX_PUBLIC_REDUNDANCY = 3
MAX_PUBLIC_PROBLEM_CHARS = 12_000
MAX_PUBLIC_SUBTASK_CHARS = 4_000
MAX_MODEL_CALLS_PER_SOLVE = (
    MAX_PUBLIC_SUBTASKS * MAX_PUBLIC_REDUNDANCY * 2)
MAX_API_COST_USD = round(
    MAX_PUBLIC_SUBTASKS * MAX_PUBLIC_REDUNDANCY * (
        conservative_request_cost_usd(MAX_SOLVE_OUTPUT_TOKENS)
        + conservative_request_cost_usd(MAX_REVIEW_OUTPUT_TOKENS)),
    6,
)
MAX_SOLVER_SETTLEMENT_MINOR = (
    MAX_PUBLIC_SUBTASKS * MAX_PUBLIC_REDUNDANCY * SOLVER_PRICE_MINOR)
MIN_CONTRIBUTION_MARGIN_MINOR = (
    SERVICE_PRICE_MINOR
    - MAX_SOLVER_SETTLEMENT_MINOR
    - int(MAX_API_COST_USD * 100 + 0.999999)
)


def _server(name: str, description: str):
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)


mcp = _server(
    "agent-hive-orchestrator-agent",
    "Deterministic nested hive-mind orchestration over the A2A rails: "
    "hire N solvers, adversarial cross-review, honest synthesis, "
    "exactly-once settlement, carbon accounting, content-addressed audit.",
)
# Bare adapter imports remain standalone-honest for package tooling and local
# inspection. The production gateway must call configure_gateway() with the
# already-mounted shared rail instances before it exposes this server.
agent = build()


def configure_gateway(rails: Dict[str, Any], *,
                      transport_factory=openai_transport,
                      model: str = DEFAULT_MODEL):
    """Bind the hive to the gateway's shared rails and three paid workers."""
    required = {"trust", "covenant", "escrow", "metering", "ledger"}
    missing = sorted(required - set(rails))
    if missing:
        raise RuntimeError(
            "hive gateway wiring missing rails: " + ", ".join(missing))
    solvers = {
        solver_id: {
            "adapter": LLMSolverAdapter(transport_factory(model=model)),
            "price_minor": SOLVER_PRICE_MINOR,
            "capabilities": ["reasoning", "analysis", "adversarial-review"],
        }
        for solver_id in SOLVER_IDS
    }
    global agent
    agent = build(solvers=solvers, rails={
        "trust": rails["trust"],
        "covenant": rails["covenant"],
        "escrow": rails["escrow"],
        "metering": rails["metering"],
        "ledger": rails["ledger"],
    })
    agent._solver_provider_ready = lambda: bool(
        os.getenv("OPENAI_API_KEY", "").strip())
    agent._paid_preflight = _paid_preflight
    return agent


def _public_validation(problem: Any, subtasks: Any,
                       redundancy: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(problem, str) or not problem.strip():
        return {
            "status": "error", "error_type": "ValidationError",
            "field": "problem", "constraint": "non-empty string",
            "message": "problem must be a non-empty string",
        }
    if len(problem) > MAX_PUBLIC_PROBLEM_CHARS:
        return {
            "status": "error", "error_type": "ValidationError",
            "field": "problem",
            "constraint": f"<= {MAX_PUBLIC_PROBLEM_CHARS} characters",
            "message": "problem exceeds the public cost-bounded limit",
        }
    if subtasks is not None and (
            not isinstance(subtasks, list) or not subtasks
            or not all(isinstance(item, str) and item.strip()
                       for item in subtasks)):
        return {
            "status": "error", "error_type": "ValidationError",
            "field": "subtasks",
            "constraint": f"1..{MAX_PUBLIC_SUBTASKS} non-empty strings",
            "message": "subtasks must be non-empty strings",
        }
    effective = subtasks or [problem]
    if len(effective) > MAX_PUBLIC_SUBTASKS:
        return {
            "status": "error", "error_type": "ValidationError",
            "field": "subtasks",
            "constraint": f"1..{MAX_PUBLIC_SUBTASKS} items",
            "message": "too many subtasks for one cost-bounded solve",
        }
    if any(len(item) > MAX_PUBLIC_SUBTASK_CHARS for item in effective):
        return {
            "status": "error", "error_type": "ValidationError",
            "field": "subtasks",
            "constraint": (
                f"each item <= {MAX_PUBLIC_SUBTASK_CHARS} characters"),
            "message": "subtask exceeds the public cost-bounded limit",
        }
    if (isinstance(redundancy, bool) or not isinstance(redundancy, int)
            or not 1 <= redundancy <= MAX_PUBLIC_REDUNDANCY):
        return {
            "status": "error", "error_type": "ValidationError",
            "field": "redundancy",
            "constraint": f"1..{MAX_PUBLIC_REDUNDANCY}",
            "message": "redundancy exceeds the public cost-bounded limit",
        }
    if len(problem) + max(map(len, effective), default=0) + 64 \
            > MAX_PROMPT_CHARS:
        return {
            "status": "error", "error_type": "ValidationError",
            "field": "problem",
            "constraint": f"composed prompt <= {MAX_PROMPT_CHARS} characters",
            "message": "problem and subtask exceed the solver prompt cap",
        }
    return None


def _paid_preflight(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fail closed before an x402/A2A quote can become a settlement.

    The public paid lane is one fixed, margin-bounded product.  Keeping this
    hook on the core lets every gateway commerce surface enforce the same
    provider-readiness and cost policy before it accepts money.
    """
    validation = _public_validation(
        payload.get("problem"), payload.get("subtasks"),
        payload.get("redundancy", 2))
    if validation is not None:
        return validation
    if payload.get("budget_minor") != SERVICE_PRICE_MINOR:
        return {
            "status": "error", "error_type": "ValidationError",
            "field": "budget_minor",
            "constraint": f"exactly {SERVICE_PRICE_MINOR}",
            "message": "paid Hive solves use the fixed public budget profile",
        }
    depth = payload.get("depth", 0)
    if isinstance(depth, bool) or depth != 0:
        return {
            "status": "error", "error_type": "ValidationError",
            "field": "depth", "constraint": "exactly 0",
            "message": "public paid Hive solves cannot delegate to child hives",
        }
    fee_bps = payload.get("fee_bps", 0)
    if isinstance(fee_bps, bool) or fee_bps != 0:
        return {
            "status": "error", "error_type": "ValidationError",
            "field": "fee_bps", "constraint": "exactly 0",
            "message": "public paid Hive solver fees are fixed",
        }
    threshold = payload.get("accept_threshold", 0.6)
    if (isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(float(threshold))
            or not 0.0 < float(threshold) <= 1.0):
        return {
            "status": "error", "error_type": "ValidationError",
            "field": "accept_threshold", "constraint": "number in (0,1]",
            "message": "accept_threshold must be a finite number in (0,1]",
        }
    seed = payload.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int):
        return {
            "status": "error", "error_type": "ValidationError",
            "field": "seed", "constraint": "integer",
            "message": "seed must be an integer",
        }
    provider_probe = getattr(agent, "_solver_provider_ready", None)
    if not callable(provider_probe) or not provider_probe():
        return {
            "status": "error",
            "error_type": "ServiceUnavailable",
            "message": "hive solver provider is not configured",
        }
    return None


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), indent=2, default=str)


@mcp.tool()
async def solve(problem: str, budget_minor: int,
                subtasks: Optional[List[str]] = None,
                depth: int = 0, redundancy: int = 2,
                accept_threshold: float = 0.6, seed: int = 0,
                fee_bps: int = 0, covenant_id: Optional[str] = None,
                payment_ref: Optional[str] = None,
                request_id: Optional[str] = None) -> str:
    """Open and run a hive job in one call: hire solvers through the rails
    (covenant -> escrow -> meter), force reviewer!=author cross-review,
    synthesize only what survives review, settle every escrow exactly-once,
    and return a content-addressed audit hash plus bits-per-joule telemetry.
    Price: $5.00 per solve after 3 free/day; sub-hires settle via escrow at
    each solver's list price."""
    validation = _public_validation(problem, subtasks, redundancy)
    if validation is not None:
        return json.dumps(validation, indent=2)
    provider_probe = getattr(agent, "_solver_provider_ready", None)
    if callable(provider_probe) and not provider_probe():
        return json.dumps({
            "status": "error",
            "error_type": "ServiceUnavailable",
            "message": "hive solver provider is not configured",
        }, indent=2)
    req: Dict[str, Any] = {"action": "solve", "problem": problem,
                           "budget_minor": budget_minor, "depth": depth,
                           "redundancy": redundancy,
                           "accept_threshold": accept_threshold,
                           "seed": seed, "fee_bps": fee_bps}
    if subtasks is not None:
        req["subtasks"] = subtasks
    if covenant_id is not None:
        req["covenant_id"] = covenant_id
    if payment_ref is not None:
        req["payment_ref"] = payment_ref
    if request_id is not None:
        req["request_id"] = request_id
    return await _run(req)


@mcp.tool()
async def job_status(job_id: str) -> str:
    """Return job state, plan hash, and live budget conservation books."""
    return await _run({"action": "job_status", "job_id": job_id})


@mcp.tool()
async def audit_job(job_id: str) -> str:
    """Return the full content-addressed lineage of a completed job: plan,
    hires (including refused ones with reasons), contributions, reviews,
    settlements, rail calls (with simulated flags), and synthesis."""
    return await _run({"action": "audit_job", "job_id": job_id})


@mcp.tool()
async def verify_audit(audit_json: str) -> str:
    """Recompute the audit digest from a presented lineage (never trusts the
    embedded hash) and report whether it matches a job this hive ran."""
    try:
        audit = json.loads(audit_json)
    except (TypeError, json.JSONDecodeError) as exc:
        return json.dumps({"status": "error",
                           "error_type": "ValidationError",
                           "message": f"audit_json is not valid JSON: {exc}"})
    return await _run({"action": "verify_audit", "audit": audit})


@mcp.tool()
async def list_solvers() -> str:
    """List the registered solver pool: id, kind (worker|hive), price,
    capabilities."""
    return await _run({"action": "list_solvers"})


@mcp.tool()
async def describe_agent() -> str:
    """Return fleet-standard capabilities, actions, invariants, and pricing."""
    described = agent.describe()
    described["pricing"].update({
        "service_price_minor": SERVICE_PRICE_MINOR,
        "currency": "USD",
        "max_solver_settlement_minor": MAX_SOLVER_SETTLEMENT_MINOR,
        "max_provider_api_cost_usd": MAX_API_COST_USD,
        "minimum_contribution_margin_minor": MIN_CONTRIBUTION_MARGIN_MINOR,
    })
    described["public_limits"] = {
        "max_subtasks": MAX_PUBLIC_SUBTASKS,
        "max_redundancy": MAX_PUBLIC_REDUNDANCY,
        "max_model_calls": MAX_MODEL_CALLS_PER_SOLVE,
        "max_problem_chars": MAX_PUBLIC_PROBLEM_CHARS,
        "max_subtask_chars": MAX_PUBLIC_SUBTASK_CHARS,
    }
    return json.dumps(described, indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(asyncio.run(agent.health()), indent=2))
