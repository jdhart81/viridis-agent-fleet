import hashlib
from pathlib import Path

import pytest

from deploy.droplet import regulatory_radar_seat_bridge_probe as probe


def gateway_health(*, payment_enabled=False, degraded=None):
    agents = {
        f"agent-{index}": {"status": "ok"} for index in range(27)
    }
    status = "ok"
    http_status = 200
    if degraded == "hive":
        agents.pop("agent-0")
        agents["hive"] = {
            "status": "degraded",
            "checks": {
                "solver_provider_ready": False,
                "wired_dependencies_ready": True,
            },
        }
        status = "degraded"
        http_status = 503
    elif degraded == "other":
        agents["agent-0"] = {"status": "degraded"}
        status = "degraded"
        http_status = 503
    return http_status, {
        "status": status,
        "mount_errors": {},
        "persistence": {"available": True, "errors": {}},
        "agents": agents,
        "payment_gate": {
            "x402": {
                "enabled": payment_enabled,
                "errors": {},
                "http_front_door": [{
                    "agent": "regulatory-radar",
                    "tool": "scan_regulations",
                    "amount_atomic_usdc": "250000",
                }],
            },
        },
    }


class ExactRuntime:
    seat = dict(probe.EXPECTED_SEAT)
    enrich_failed = False
    enrich_hive = False

    @classmethod
    def seat_option(cls, agent, public_base):
        return dict(cls.seat)

    @classmethod
    def _with_commerce_metadata(
        cls, payload, agent, tool, public_base
    ):
        if payload.get("status") == "error":
            if cls.enrich_failed:
                return {**payload, "viridis_commerce": {}}
            return payload
        commerce = {
            "auto_execute": False,
            "payment_required": True,
            "buyer_authorization_required": True,
        }
        if agent == "regulatory-radar" or cls.enrich_hive:
            commerce["seat_option"] = dict(cls.seat)
        return {**payload, "viridis_commerce": commerce}


@pytest.fixture
def files(tmp_path):
    x402 = tmp_path / "x402_http.py"
    payment = tmp_path / "payment_gate.py"
    x402.write_bytes(b"candidate x402")
    payment.write_bytes(b"production payment gate")
    return (
        x402,
        payment,
        hashlib.sha256(x402.read_bytes()).hexdigest(),
        hashlib.sha256(payment.read_bytes()).hexdigest(),
    )


def run_probe(monkeypatch, files, *, health=None, runtime=ExactRuntime):
    x402, payment, x402_sha, payment_sha = files
    monkeypatch.setattr(
        probe, "get_health", lambda base: health or gateway_health()
    )
    runtime.seat = dict(probe.EXPECTED_SEAT)
    runtime.enrich_failed = False
    runtime.enrich_hive = False
    return probe.probe(
        "http://127.0.0.1:8402",
        module=runtime,
        x402_http_path=x402,
        payment_gate_path=payment,
        expected_x402_http_sha256=x402_sha,
        expected_payment_gate_sha256=payment_sha,
    )


def test_probe_accepts_healthy_payment_disabled_candidate(monkeypatch, files):
    result = run_probe(monkeypatch, files)

    assert result["status"] == "ok"
    assert result["health_mode"] == "fully_healthy"
    assert result["paid_route_called"] is False
    assert result["payment_signed"] is False
    assert result["subscription_mutated"] is False


def test_probe_accepts_only_exact_missing_hive_provider(monkeypatch, files):
    result = run_probe(
        monkeypatch, files, health=gateway_health(degraded="hive")
    )

    assert result["health_mode"] == "expected_missing_hive_provider"


def test_probe_refuses_non_loopback(monkeypatch, files):
    monkeypatch.setattr(probe, "get_health", lambda base: gateway_health())
    x402, payment, x402_sha, payment_sha = files

    with pytest.raises(probe.ProbeFailure, match="non-loopback"):
        probe.probe(
            "https://mcp.viridisconservation.com",
            module=ExactRuntime,
            x402_http_path=x402,
            payment_gate_path=payment,
            expected_x402_http_sha256=x402_sha,
            expected_payment_gate_sha256=payment_sha,
        )


def test_probe_refuses_enabled_payment(monkeypatch, files):
    with pytest.raises(probe.ProbeFailure, match="payment rail is enabled"):
        run_probe(
            monkeypatch,
            files,
            health=gateway_health(payment_enabled=True),
        )


def test_probe_refuses_unexpected_degraded_agent(monkeypatch, files):
    with pytest.raises(probe.ProbeFailure, match="unexpected degraded"):
        run_probe(
            monkeypatch,
            files,
            health=gateway_health(degraded="other"),
        )


def test_probe_refuses_changed_seat_contract(monkeypatch, files):
    class ChangedSeat(ExactRuntime):
        pass

    ChangedSeat.seat = {**probe.EXPECTED_SEAT, "price_monthly_minor": 1}
    monkeypatch.setattr(
        probe, "get_health", lambda base: gateway_health()
    )
    x402, payment, x402_sha, payment_sha = files

    with pytest.raises(probe.ProbeFailure, match="seat object changed"):
        probe.probe(
            "http://127.0.0.1:8402",
            module=ChangedSeat,
            x402_http_path=x402,
            payment_gate_path=payment,
            expected_x402_http_sha256=x402_sha,
            expected_payment_gate_sha256=payment_sha,
        )


def test_probe_refuses_commerce_on_failed_result(monkeypatch, files):
    class FailedEnrichment(ExactRuntime):
        enrich_failed = True

    monkeypatch.setattr(
        probe, "get_health", lambda base: gateway_health()
    )
    x402, payment, x402_sha, payment_sha = files

    with pytest.raises(probe.ProbeFailure, match="failed paid result"):
        probe.probe(
            "http://127.0.0.1:8402",
            module=FailedEnrichment,
            x402_http_path=x402,
            payment_gate_path=payment,
            expected_x402_http_sha256=x402_sha,
            expected_payment_gate_sha256=payment_sha,
        )


def test_probe_refuses_seat_offer_on_uncovered_agent(monkeypatch, files):
    class HiveEnrichment(ExactRuntime):
        enrich_hive = True

    monkeypatch.setattr(
        probe, "get_health", lambda base: gateway_health()
    )
    x402, payment, x402_sha, payment_sha = files

    with pytest.raises(probe.ProbeFailure, match="uncovered Hive"):
        probe.probe(
            "http://127.0.0.1:8402",
            module=HiveEnrichment,
            x402_http_path=x402,
            payment_gate_path=payment,
            expected_x402_http_sha256=x402_sha,
            expected_payment_gate_sha256=payment_sha,
        )


def test_probe_refuses_source_digest_mismatch(monkeypatch, files):
    x402, payment, _, payment_sha = files
    monkeypatch.setattr(probe, "get_health", lambda base: gateway_health())

    with pytest.raises(probe.ProbeFailure, match="x402_http.py digest"):
        probe.probe(
            "http://127.0.0.1:8402",
            module=ExactRuntime,
            x402_http_path=x402,
            payment_gate_path=payment,
            expected_x402_http_sha256="0" * 64,
            expected_payment_gate_sha256=payment_sha,
        )
