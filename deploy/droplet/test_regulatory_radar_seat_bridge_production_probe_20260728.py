import hashlib
import json

import pytest

from deploy.droplet import (
    regulatory_radar_seat_bridge_production_probe_20260728 as probe,
)


def exact_health():
    agents = {f"agent-{index}": {"status": "ok"} for index in range(27)}
    agents["security-preflight"] = {
        "status": "ok",
        "version": "1.1.0",
        "signer_required": True,
        "signer_ready": True,
        "receipt_store": "persistent-sqlite",
        "receipt_store_ready": True,
        "raw_inputs_stored": False,
        "runtime_fetches_enabled": False,
        "signer_public_key_sha256": probe.EXPECTED_SIGNER_PUBLIC_KEY_SHA256,
    }
    telemetry = {
        "settlements_total": 8,
        "self_settlements": 4,
        "external_settlements": 4,
        "distinct_external_payers": 4,
        "repeat_external_purchases": 0,
        "external_revenue_atomic": 280000,
        "first_external_settlement": {
            "tx_hash": "0xabc",
            "timestamp": "2026-07-20T00:00:00+00:00",
        },
    }
    return 200, {
        "status": "ok",
        "mount_errors": {},
        "persistence": {"available": True, "errors": {}},
        "agents": agents,
        "payment_gate": {
            "x402": {
                "enabled": True,
                "errors": {},
                "http_front_door": [
                    {
                        "agent": "regulatory-radar",
                        "tool": "scan_regulations",
                        "amount_atomic_usdc": "250000",
                        "v2_enabled": True,
                        "x402_version": 2,
                    },
                    {
                        "agent": "security-preflight",
                        "tool": "security_preflight",
                        "amount_atomic_usdc": "1000000",
                        "v2_enabled": True,
                        "x402_version": 2,
                    },
                ],
                "http_settlement_telemetry": {"total": telemetry},
            }
        },
        "subscriptions": {
            "status": "ok",
            "checks": {
                "stripe_provider_attached": True,
                "durable_activation_commit_attached": True,
                "plan_catalog_sha256": probe.EXPECTED_PLAN_CATALOG_SHA256,
                "plan_catalog_version": "0.3.0",
                "active_subscriptions": 0,
                "checkouts_started": 0,
                "mrr_minor": 0,
            },
        },
    }


def getter(payload=None):
    return lambda base: payload or exact_health()


class ExactHttpRuntime:
    @staticmethod
    def seat_option(agent, base):
        return dict(probe.EXPECTED_SEAT)

    @staticmethod
    def _with_commerce_metadata(payload, agent, tool, base):
        if payload.get("status") == "error":
            return payload
        commerce = {
            "auto_execute": False,
            "payment_required": True,
            "buyer_authorization_required": True,
        }
        if agent == "regulatory-radar":
            commerce["seat_option"] = dict(probe.EXPECTED_SEAT)
        return {**payload, "viridis_commerce": commerce}


class ExactRail:
    contacted = False

    @staticmethod
    def is_enabled():
        return True

    @staticmethod
    def build_accepts(agent, price, resource):
        return {"maxAmountRequired": "250000"}

    @classmethod
    def verify_and_settle(cls, payload, requirements, _transport=None):
        assert payload == {}
        assert requirements["maxAmountRequired"] == "250000"
        return {"settled": False, "reason": "missing_or_malformed_payment"}


@pytest.fixture
def runtime_files(tmp_path):
    paths = []
    hashes = []
    for name, raw in (
        ("x402_http.py", b"candidate x402"),
        ("x402_rail.py", b"preserved x402 rail"),
        ("payment_gate.py", b"preserved payment gate"),
        ("state_store.py", b"candidate state store"),
        ("viridis_mcp_gateway.py", b"preserved gateway"),
        ("security_core.py", b"preserved security core"),
    ):
        path = tmp_path / name
        path.write_bytes(raw)
        paths.append(path)
        hashes.append(hashlib.sha256(raw).hexdigest())
    return (*paths, *hashes)


def run_runtime(runtime_files, *, health=None):
    (
        x402_http,
        x402_rail,
        payment,
        state,
        gateway,
        security,
        x402_http_sha,
        _x402_rail_sha,
        payment_sha,
        state_sha,
        gateway_sha,
        security_sha,
    ) = runtime_files
    ExactRail.contacted = False
    return probe.verify_runtime(
        probe.LOOPBACK_BASE,
        x402_http_module=ExactHttpRuntime,
        x402_rail_module=ExactRail,
        health_getter=getter(health),
        x402_http_path=x402_http,
        x402_rail_path=x402_rail,
        payment_gate_path=payment,
        state_store_path=state,
        gateway_path=gateway,
        security_preflight_path=security,
        expected_x402_http_sha256=x402_http_sha,
        expected_payment_gate_sha256=payment_sha,
        expected_state_store_sha256=state_sha,
        expected_gateway_sha256=gateway_sha,
        expected_security_preflight_sha256=security_sha,
    )


def test_public_snapshot_accepts_exact_28_agent_production():
    result = probe.commercial_snapshot(probe.PUBLIC_BASE, health_getter=getter())
    assert result["status"] == "ok"
    assert result["agent_count"] == 28
    assert result["x402"]["telemetry_total"]["external_revenue_atomic"] == 280000
    assert result["probe_effects"]["paid_route_called"] is False
    assert result["probe_effects"]["subscription_mutated"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda health: health[1]["agents"]["security-preflight"].__setitem__(
                "signer_ready", False
            ),
            "Security Preflight",
        ),
        (
            lambda health: health[1]["payment_gate"]["x402"].__setitem__(
                "enabled", False
            ),
            "not enabled",
        ),
        (
            lambda health: health[1]["subscriptions"]["checks"].__setitem__(
                "plan_catalog_sha256", "0" * 64
            ),
            "catalog changed",
        ),
        (
            lambda health: health[1]["agents"]["agent-0"].__setitem__(
                "status", "degraded"
            ),
            "not healthy",
        ),
    ),
)
def test_public_snapshot_fails_closed_on_production_drift(mutation, message):
    health = exact_health()
    mutation(health)
    with pytest.raises(probe.ProbeFailure, match=message):
        probe.commercial_snapshot(
            probe.PUBLIC_BASE,
            health_getter=getter(health),
        )


def test_public_verify_accepts_equal_or_external_growth():
    baseline = probe.commercial_snapshot(probe.PUBLIC_BASE, health_getter=getter())
    current = exact_health()
    telemetry = current[1]["payment_gate"]["x402"][
        "http_settlement_telemetry"
    ]["total"]
    telemetry["settlements_total"] += 1
    telemetry["external_settlements"] += 1
    telemetry["distinct_external_payers"] += 1
    telemetry["external_revenue_atomic"] += 250000
    result = probe.verify_public(
        probe.PUBLIC_BASE,
        baseline,
        health_getter=getter(current),
    )
    assert result["commercial_deltas"]["external_settlements"] == 1
    assert result["operator_caused_commercial_mutation"] is False


def test_public_verify_refuses_counter_regression():
    baseline = probe.commercial_snapshot(probe.PUBLIC_BASE, health_getter=getter())
    current = exact_health()
    current[1]["payment_gate"]["x402"]["http_settlement_telemetry"]["total"][
        "external_revenue_atomic"
    ] -= 1
    with pytest.raises(probe.ProbeFailure, match="regressed"):
        probe.verify_public(
            probe.PUBLIC_BASE,
            baseline,
            health_getter=getter(current),
        )


def test_public_verify_refuses_self_settlement_change():
    baseline = probe.commercial_snapshot(probe.PUBLIC_BASE, health_getter=getter())
    current = exact_health()
    telemetry = current[1]["payment_gate"]["x402"][
        "http_settlement_telemetry"
    ]["total"]
    telemetry["self_settlements"] += 1
    telemetry["settlements_total"] += 1
    with pytest.raises(probe.ProbeFailure, match="self-settlement"):
        probe.verify_public(
            probe.PUBLIC_BASE,
            baseline,
            health_getter=getter(current),
        )


def test_runtime_probe_checks_exact_sources_seat_and_empty_payment(runtime_files):
    result = run_runtime(runtime_files)
    assert result["status"] == "ok"
    assert result["empty_payment_refusal"] == {
        "settled": False,
        "reason": "missing_or_malformed_payment",
    }
    assert result["facilitator_contacted"] is False
    assert result["paid_route_called"] is False
    assert result["payment_settled"] is False
    assert result["checkout_opened"] is False


def test_runtime_probe_refuses_non_loopback(runtime_files):
    with pytest.raises(probe.ProbeFailure, match="non-loopback"):
        probe.verify_runtime(
            probe.PUBLIC_BASE,
            x402_http_module=ExactHttpRuntime,
            x402_rail_module=ExactRail,
        )


def test_runtime_probe_refuses_source_drift(runtime_files):
    values = list(runtime_files)
    values[6] = "0" * 64
    with pytest.raises(probe.ProbeFailure, match="x402_http.py digest"):
        run_runtime(tuple(values))


def test_runtime_probe_refuses_changed_seat(runtime_files, monkeypatch):
    monkeypatch.setattr(
        ExactHttpRuntime,
        "seat_option",
        staticmethod(
            lambda agent, base: {
                **probe.EXPECTED_SEAT,
                "price_monthly_minor": 1,
            }
        ),
    )
    with pytest.raises(probe.ProbeFailure, match="seat object changed"):
        run_runtime(runtime_files)


def test_cli_writes_machine_readable_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        probe,
        "commercial_snapshot",
        lambda base: (_ for _ in ()).throw(probe.ProbeFailure("drift")),
    )
    assert probe.main(["public-capture", "--base", probe.PUBLIC_BASE]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "failed"
    assert output["message"] == "drift"
