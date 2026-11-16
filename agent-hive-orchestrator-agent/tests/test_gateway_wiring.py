"""Production wiring, price integrity, and public cost-bound tests."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

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
    assert adapter.FREE_SOLVES_PER_DAY == 0
    assert adapter.MAX_SOLVER_SETTLEMENT_MINOR == 300
    assert adapter.MAX_API_COST_USD < 0.07
    assert adapter.MIN_CONTRIBUTION_MARGIN_MINOR >= 193
    assert adapter.CONTRIBUTION_MARGIN_BPS >= 3_500
    assert adapter.CONTRIBUTION_MARGIN_BPS >= \
        adapter.MIN_REQUIRED_CONTRIBUTION_MARGIN_BPS


def test_describe_and_manifest_advertise_the_enforced_zero_execution_free_tier():
    described = json.loads(asyncio.run(adapter.describe_agent()))
    pricing = described["pricing"]
    assert pricing["usd_per_solve"] == 5.0
    assert pricing["service_price_minor"] == 500
    assert pricing["free_per_day"] == 0
    assert pricing["provider_backed_free_solves_per_day"] == 0
    assert pricing["provider_service_tier"] == "default"
    assert "no free model-backed execution" in pricing["free_scope"]

    manifest = (
        Path(__file__).resolve().parents[1] / "agent.yaml").read_text()
    assert "$5.00 per model-backed solve" in manifest
    assert "no execution free tier" in manifest
    assert "$3.00 in solver settlements" in manifest
    assert "$0.07" in manifest
    assert "$1.93 / 38.6% contribution margin" in manifest
    assert "gpt-6-luna" in manifest
    assert "OpenAI Standard processing" in manifest


@pytest.mark.parametrize(("field", "value"), [
    ("budget_minor", 499),
    ("depth", 1),
    ("fee_bps", 1),
    ("subtasks", ["a", "b", "c", "d", "e"]),
    ("redundancy", 4),
])
def test_paid_preflight_rejects_every_public_cost_bound_before_job_mutation(
        monkeypatch, field, value):
    monkeypatch.setenv("OPENAI_API_KEY", "ready")
    rails = {name: Rail() for name in (
        "trust", "covenant", "escrow", "metering", "ledger")}
    core = adapter.configure_gateway(
        rails, transport_factory=fake_transport_factory)
    request = {
        "action": "solve", "problem": "p", "budget_minor": 500,
        "depth": 0, "redundancy": 2, "fee_bps": 0,
    }
    request[field] = value
    before = len(core.jobs)

    refused = core._paid_preflight(request)

    assert refused["status"] == "error"
    assert refused["field"] == field
    assert len(core.jobs) == before


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


def test_default_model_is_supported_and_clears_the_margin_floor():
    assert adapter.DEFAULT_MODEL == "gpt-6-luna"
    assert adapter.contribution_margin_bps("gpt-6-luna") == 3_860
    assert adapter.CONTRIBUTION_MARGIN_BPS == \
        adapter.contribution_margin_bps(adapter.DEFAULT_MODEL)
    adapter.require_margin_floor("gpt-6-luna")


def test_gateway_refuses_a_priced_model_that_breaches_the_floor():
    # gpt-6.1-terra is OpenAI's named successor to gpt-5-mini, but at
    # $5.00/solve its conservative ceiling ($0.62) leaves 27.6% margin.
    assert adapter.contribution_margin_bps("gpt-6.1-terra") == 2_760
    rails = {name: Rail() for name in (
        "trust", "covenant", "escrow", "metering", "ledger")}
    with pytest.raises(RuntimeError, match="minimum contribution margin"):
        adapter.configure_gateway(
            rails, transport_factory=fake_transport_factory,
            model="gpt-6.1-terra")


@pytest.mark.parametrize("model", [
    "gpt-5-mini", "gpt-5-mini-2025-08-07", "not-a-model"])
def test_gateway_refuses_retired_and_unknown_models_before_wiring(model):
    rails = {name: Rail() for name in (
        "trust", "covenant", "escrow", "metering", "ledger")}
    with pytest.raises(RuntimeError, match="HIVE_LLM_MODEL"):
        adapter.configure_gateway(
            rails, transport_factory=fake_transport_factory, model=model)


def _import_with_env(model):
    import os
    import subprocess
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "HIVE_LLM_MODEL": model}
    return subprocess.run(
        [sys.executable, "-c", "import adapters.mcp_server"],
        cwd=root, env=env, capture_output=True, text=True, timeout=60)


def test_stale_retired_env_pin_fails_boot_with_actionable_message():
    proc = _import_with_env("gpt-5-mini-2025-08-07")
    assert proc.returncode != 0
    assert "retired by OpenAI on 2026-12-11" in proc.stderr
    assert "gpt-6-luna" in proc.stderr


def test_explicit_supported_env_pin_boots():
    proc = _import_with_env("gpt-6-luna")
    assert proc.returncode == 0, proc.stderr
