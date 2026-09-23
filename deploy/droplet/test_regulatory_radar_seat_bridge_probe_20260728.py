import hashlib

import pytest

from deploy.droplet import regulatory_radar_seat_bridge_probe_20260728 as probe


def gateway_health(*, payment_enabled=False, degraded=None):
    agents = {
        f"agent-{index}": {"status": "ok"} for index in range(27)
    }
    agents["security-preflight"] = {
        "status": "ok",
        "version": "1.1.0",
        "signer_required": False,
        "signer_ready": False,
        "receipt_store": "memory",
        "receipt_store_ready": True,
        "raw_inputs_stored": False,
        "runtime_fetches_enabled": False,
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
                "http_front_door": [
                    {
                        "agent": "regulatory-radar",
                        "tool": "scan_regulations",
                        "amount_atomic_usdc": "250000",
                    },
                    {
                        "agent": "security-preflight",
                        "tool": "security_preflight",
                        "amount_atomic_usdc": "1000000",
                    },
                ],
            },
        },
    }


class ExactRuntime:
    seat = dict(probe.EXPECTED_SEAT)
    enrich_failed = False
    enrich_hive = False
    enrich_security = False

    @classmethod
    def seat_option(cls, agent, public_base):
        return dict(cls.seat)

    @classmethod
    def _with_commerce_metadata(cls, payload, agent, tool, public_base):
        if payload.get("status") == "error":
            if cls.enrich_failed:
                return {**payload, "viridis_commerce": {}}
            return payload
        commerce = {
            "auto_execute": False,
            "payment_required": True,
            "buyer_authorization_required": True,
        }
        if (
            agent == "regulatory-radar"
            or (agent == "hive" and cls.enrich_hive)
            or (agent == "security-preflight" and cls.enrich_security)
        ):
            commerce["seat_option"] = dict(cls.seat)
        return {**payload, "viridis_commerce": commerce}


@pytest.fixture
def files(tmp_path):
    paths = []
    hashes = []
    for name, raw in (
        ("x402_http.py", b"candidate x402"),
        ("payment_gate.py", b"production payment gate"),
        ("viridis_mcp_gateway.py", b"production gateway"),
        ("security_preflight_core.py", b"production security preflight"),
    ):
        path = tmp_path / name
        path.write_bytes(raw)
        paths.append(path)
        hashes.append(hashlib.sha256(raw).hexdigest())
    return (*paths, *hashes)


def run_probe(monkeypatch, files, *, health=None, runtime=ExactRuntime):
    x402, payment, gateway, security, x_sha, p_sha, g_sha, s_sha = files
    monkeypatch.setattr(
        probe, "get_health", lambda base: health or gateway_health()
    )
    if runtime is ExactRuntime:
        runtime.seat = dict(probe.EXPECTED_SEAT)
        runtime.enrich_failed = False
        runtime.enrich_hive = False
        runtime.enrich_security = False
    return probe.probe(
        "http://127.0.0.1:8402",
        module=runtime,
        x402_http_path=x402,
        payment_gate_path=payment,
        gateway_path=gateway,
        security_preflight_path=security,
        expected_x402_http_sha256=x_sha,
        expected_payment_gate_sha256=p_sha,
        expected_gateway_sha256=g_sha,
        expected_security_preflight_sha256=s_sha,
    )


def test_probe_accepts_healthy_payment_disabled_28_agent_candidate(
    monkeypatch, files
):
    result = run_probe(monkeypatch, files)
    assert result["status"] == "ok"
    assert result["agent_count"] == 28
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
    x402, payment, gateway, security, x_sha, p_sha, g_sha, s_sha = files
    with pytest.raises(probe.ProbeFailure, match="non-loopback"):
        probe.probe(
            "https://mcp.viridisconservation.com",
            module=ExactRuntime,
            x402_http_path=x402,
            payment_gate_path=payment,
            gateway_path=gateway,
            security_preflight_path=security,
            expected_x402_http_sha256=x_sha,
            expected_payment_gate_sha256=p_sha,
            expected_gateway_sha256=g_sha,
            expected_security_preflight_sha256=s_sha,
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
            monkeypatch, files, health=gateway_health(degraded="other")
        )


def test_probe_refuses_missing_security_preflight(monkeypatch, files):
    health = gateway_health()
    health[1]["agents"].pop("security-preflight")
    with pytest.raises(probe.ProbeFailure, match="expected 28 agents"):
        run_probe(monkeypatch, files, health=health)


def test_probe_refuses_security_preflight_signer(monkeypatch, files):
    health = gateway_health()
    security = health[1]["agents"]["security-preflight"]
    security["signer_ready"] = True
    with pytest.raises(probe.ProbeFailure, match="credential-free mode"):
        run_probe(monkeypatch, files, health=health)


def test_probe_refuses_changed_seat_contract(monkeypatch, files):
    class ChangedSeat(ExactRuntime):
        pass

    ChangedSeat.seat = {**probe.EXPECTED_SEAT, "price_monthly_minor": 1}
    monkeypatch.setattr(probe, "get_health", lambda base: gateway_health())
    x402, payment, gateway, security, x_sha, p_sha, g_sha, s_sha = files
    with pytest.raises(probe.ProbeFailure, match="seat object changed"):
        probe.probe(
            "http://127.0.0.1:8402",
            module=ChangedSeat,
            x402_http_path=x402,
            payment_gate_path=payment,
            gateway_path=gateway,
            security_preflight_path=security,
            expected_x402_http_sha256=x_sha,
            expected_payment_gate_sha256=p_sha,
            expected_gateway_sha256=g_sha,
            expected_security_preflight_sha256=s_sha,
        )


def test_probe_refuses_commerce_on_failed_result(monkeypatch, files):
    class FailedEnrichment(ExactRuntime):
        enrich_failed = True

    FailedEnrichment.enrich_failed = True
    with pytest.raises(probe.ProbeFailure, match="failed paid result"):
        run_probe(monkeypatch, files, runtime=FailedEnrichment)


def test_probe_refuses_seat_offer_on_uncovered_agent(monkeypatch, files):
    class HiveEnrichment(ExactRuntime):
        enrich_hive = True

    HiveEnrichment.enrich_hive = True
    with pytest.raises(probe.ProbeFailure, match="uncovered Hive"):
        run_probe(monkeypatch, files, runtime=HiveEnrichment)


def test_probe_refuses_seat_offer_on_security_preflight(monkeypatch, files):
    class SecurityEnrichment(ExactRuntime):
        enrich_security = True

    SecurityEnrichment.enrich_security = True
    with pytest.raises(probe.ProbeFailure, match="Security Preflight received"):
        run_probe(monkeypatch, files, runtime=SecurityEnrichment)


def test_probe_refuses_source_digest_mismatch(monkeypatch, files):
    x402, payment, gateway, security, _, p_sha, g_sha, s_sha = files
    monkeypatch.setattr(probe, "get_health", lambda base: gateway_health())
    with pytest.raises(probe.ProbeFailure, match="x402_http.py digest"):
        probe.probe(
            "http://127.0.0.1:8402",
            module=ExactRuntime,
            x402_http_path=x402,
            payment_gate_path=payment,
            gateway_path=gateway,
            security_preflight_path=security,
            expected_x402_http_sha256="0" * 64,
            expected_payment_gate_sha256=p_sha,
            expected_gateway_sha256=g_sha,
            expected_security_preflight_sha256=s_sha,
        )
