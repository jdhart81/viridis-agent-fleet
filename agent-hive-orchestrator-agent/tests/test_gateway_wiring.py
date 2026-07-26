"""Production wiring, price integrity, and public cost-bound tests."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters import mcp_server as adapter  # noqa: E402


class Rail:
    async def process(self, request):
        return {"status": "ok", "data": {}}


def fake_transport_factory(*, model):
    async def transport(payload):
        if payload["max_output_tokens"] == adapter.MAX_REVIEW_OUTPUT_TOKENS:
            return json.dumps({"score": 0.9, "critique": "ok"})
        return "bounded answer"

    return transport


def test_gateway_wires_exact_shared_rails_and_three_solvers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "present-for-readiness-only")
    rails = {name: Rail() for name in (
        "trust", "covenant", "escrow", "metering", "ledger")}
    core = adapter.configure_gateway(
        rails, transport_factory=fake_transport_factory)
    assert core.rails_mode == "wired"
    assert len(core.solvers) == 3
    assert set(core.solvers) == set(adapter.SOLVER_IDS)
    for name, rail in rails.items():
        assert core._rails[name] is rail
    health = asyncio.run(core.health())
    assert health["status"] == "ok"
    assert health["checks"]["solver_provider_ready"] is True


def test_gateway_wiring_fails_closed_when_a_rail_is_missing():
    rails = {name: Rail() for name in (
        "trust", "covenant", "escrow", "metering")}
    try:
        adapter.configure_gateway(
            rails, transport_factory=fake_transport_factory)
        assert False
    except RuntimeError as exc:
        assert "ledger" in str(exc)


def test_public_economics_leave_healthy_contribution_margin():
    assert adapter.SERVICE_PRICE_MINOR == 500
    assert adapter.FREE_SOLVES_PER_DAY == 3
    assert adapter.MAX_SOLVER_SETTLEMENT_MINOR == 300
    assert adapter.MAX_API_COST_USD < 0.18
    assert adapter.MIN_CONTRIBUTION_MARGIN_MINOR >= 182


def test_public_limits_refuse_before_provider_or_job_mutation(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    before = len(adapter.agent.jobs)
    result = json.loads(asyncio.run(adapter.solve(
        problem="p", budget_minor=500,
        subtasks=["a", "b", "c", "d", "e"],
    )))
    assert result["status"] == "error"
    assert result["field"] == "subtasks"
    assert len(adapter.agent.jobs) == before


def test_paid_preflight_enforces_fixed_margin_profile_before_job_mutation(
        monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ready")
    rails = {name: Rail() for name in (
        "trust", "covenant", "escrow", "metering", "ledger")}
    core = adapter.configure_gateway(
        rails, transport_factory=fake_transport_factory)
    before = len(core.jobs)
    refused = core._paid_preflight({
        "action": "solve", "problem": "p", "budget_minor": 499,
        "depth": 0, "redundancy": 2, "fee_bps": 0})
    assert refused["status"] == "error"
    assert refused["field"] == "budget_minor"
    accepted = core._paid_preflight({
        "action": "solve", "problem": "p", "budget_minor": 500,
        "depth": 0, "redundancy": 3, "fee_bps": 0})
    assert accepted is None
    assert len(core.jobs) == before
