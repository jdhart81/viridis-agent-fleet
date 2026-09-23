import hashlib
import json

import pytest

from deploy.droplet import regulatory_radar_wedge_probe as probe


def gateway_health(*, payment_enabled=False):
    return {
        "status": "ok",
        "mount_errors": {},
        "persistence": {"available": True, "errors": {}},
        "agents": {
            f"agent-{index}": {"status": "ok"} for index in range(27)
        },
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


def agents_page():
    return (
        probe.INTRO_ENABLED
        + "\nStart here · Regulatory Radar\n"
        + "The live unpaid 402 is authoritative\n"
        + "A repeat is never automatic\n"
        + 'href="/quickstart#radar-first-call"\n'
        + 'href="/quickstart#radar-repeat-call"\n'
        + "The live merchant inventory is authoritative for which routes "
        + "CDP currently indexes.\n"
        + "Hive can become Bazaar-indexed only after its first successful "
        + "buyer settlement.\n"
        + probe.BAZAAR_MERCHANT_URL
    )


def quickstart_page():
    return (
        probe.INTRO_ENABLED
        + "\nRecommended first purchase\n"
        + "fresh unsigned quote\n"
        + "Viridis never treats a prior purchase as permission to spend "
        + "again.\n"
        + 'id="official-client"\n'
        + 'id="radar-repeat-call"\n'
        + "--route regulatory-radar --max-payment-usdc 0.25\n"
        + "This is exactly one new paid attempt.\n"
        + "It does not authorize any later purchase.\n"
        + "\n.card code{display:block;overflow-wrap:anywhere;"
        + "word-break:break-word}\n"
        + "CDP's live merchant inventory is the authoritative current list "
        + "of settlement-indexed routes.\n"
        + "Hive can become Bazaar-indexed only after its first successful "
        + "buyer settlement.\n"
        + probe.BAZAAR_MERCHANT_URL
    )


def machine_repeat_surface():
    return (
        "--route regulatory-radar --max-payment-usdc 0.25\n"
        "exactly one new paid attempt\n"
        "authorize any later purchase"
    )


def llms_page():
    return probe.INTRO_ENABLED + "\n" + machine_repeat_surface()


def patch_gateway(
    monkeypatch,
    *,
    health=None,
    agents=None,
    quickstart=None,
    llms=None,
    buyer_skill=None,
):
    payloads = {
        "/healthz": health or gateway_health(),
        "/agents": agents if agents is not None else agents_page(),
        "/quickstart": (
            quickstart if quickstart is not None else quickstart_page()
        ),
        "/llms.txt": llms if llms is not None else llms_page(),
        "/.well-known/skills/viridis-paid-tools/SKILL.md": (
            buyer_skill
            if buyer_skill is not None
            else machine_repeat_surface()
        ),
    }
    monkeypatch.setattr(
        probe,
        "get_json",
        lambda base, path: payloads[path],
    )
    monkeypatch.setattr(
        probe,
        "get_text",
        lambda base, path: payloads[path],
    )


def growth_content():
    routes = "\n".join(
        f"• {route} — {price}"
        for route, price in probe.EXPECTED_ROUTE_PRICES.items()
    )
    return (
        "Start here: Regulatory Radar — one bounded x402 compliance scan "
        "on Base.\n"
        "List price: $0.25. Inspect the live unpaid quote before signing; "
        "the quote is authoritative for this buyer.\n\n"
        f"{routes}\n"
        f"{probe.GROWTH_INTRO_ENABLED}\n"
        "Live external proof: 3 settlement(s) from 3 distinct payer(s).\n"
        f"{probe.REPEAT_BUYER_CTA}\n"
        "https://mcp.viridisconservation.com/quickstart\n"
        "https://mcp.viridisconservation.com/agents"
    )


def growth_result(**updates):
    result = {
        "status": "dry_run",
        "enabled": True,
        "send_attempted": False,
        "model": {"mode": "deterministic", "reason": "dry_run_no_api"},
        "target": {"id": "owned-channel", "policy_cleared": True},
        "content": growth_content(),
    }
    result.update(updates)
    return result


def write_growth(tmp_path, result=None):
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(result or growth_result()),
        encoding="utf-8",
    )
    state = tmp_path / "growth.sqlite3"
    state.write_bytes(b"copied growth state")
    digest = hashlib.sha256(state.read_bytes()).hexdigest()
    return result_path, state, digest


def test_gateway_probe_accepts_exact_loopback_candidate(monkeypatch):
    patch_gateway(monkeypatch)

    result = probe.probe_gateway(
        "http://127.0.0.1:18402", "enabled")

    assert result["status"] == "ok"
    assert result["agent_count"] == 27
    assert result["payment_enabled"] is False


def test_gateway_probe_refuses_non_loopback(monkeypatch):
    patch_gateway(monkeypatch)

    with pytest.raises(probe.ProbeFailure, match="non-loopback"):
        probe.probe_gateway("https://mcp.viridisconservation.com", "enabled")


def test_gateway_probe_rejects_enabled_payment(monkeypatch):
    patch_gateway(monkeypatch, health=gateway_health(payment_enabled=True))

    with pytest.raises(probe.ProbeFailure, match="payment rail is enabled"):
        probe.probe_gateway("http://127.0.0.1:18402", "enabled")


def test_gateway_probe_rejects_missing_repeat_boundary(monkeypatch):
    patch_gateway(
        monkeypatch,
        agents=agents_page().replace("A repeat is never automatic", ""),
    )

    with pytest.raises(probe.ProbeFailure, match="repeat authorization"):
        probe.probe_gateway("http://127.0.0.1:18402", "enabled")


def test_gateway_probe_rejects_raw_intro_placeholder(monkeypatch):
    patch_gateway(
        monkeypatch,
        quickstart=quickstart_page() + "\n{{INTRO_STATUS}}",
    )

    with pytest.raises(probe.ProbeFailure, match="raw placeholder"):
        probe.probe_gateway("http://127.0.0.1:18402", "enabled")


def test_gateway_probe_rejects_endpoint_overflow_regression(monkeypatch):
    patch_gateway(
        monkeypatch,
        quickstart=quickstart_page().replace(
            "overflow-wrap:anywhere;", ""),
    )

    with pytest.raises(probe.ProbeFailure, match="overflow-safe"):
        probe.probe_gateway("http://127.0.0.1:18402", "enabled")


def test_gateway_probe_rejects_stale_bazaar_count_claim(monkeypatch):
    patch_gateway(
        monkeypatch,
        agents=agents_page() + "\nEvery live route was indexed",
    )

    with pytest.raises(probe.ProbeFailure, match="stale Bazaar claim"):
        probe.probe_gateway("http://127.0.0.1:18402", "enabled")


def test_gateway_probe_rejects_unbounded_repeat_path(monkeypatch):
    patch_gateway(
        monkeypatch,
        quickstart=quickstart_page().replace(
            "--route regulatory-radar --max-payment-usdc 0.25", ""),
    )

    with pytest.raises(probe.ProbeFailure, match="returning-buyer"):
        probe.probe_gateway("http://127.0.0.1:18402", "enabled")


def test_gateway_probe_rejects_stale_machine_repeat_surface(monkeypatch):
    patch_gateway(
        monkeypatch,
        llms=llms_page().replace(
            "--route regulatory-radar --max-payment-usdc 0.25", ""),
    )

    with pytest.raises(probe.ProbeFailure, match="llms omits"):
        probe.probe_gateway("http://127.0.0.1:18402", "enabled")


def test_growth_probe_accepts_no_send_no_model_result(tmp_path):
    result_path, state, digest = write_growth(tmp_path)

    result = probe.probe_growth(result_path, state, digest, 3, 3)

    assert result["status"] == "ok"
    assert result["send_attempted"] is False
    assert result["model_called"] is False


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"send_attempted": True}, "outbound send"),
        (
            {"model": {"mode": "openai", "reason": "generated"}},
            "dry-run/no-model",
        ),
    ],
)
def test_growth_probe_rejects_send_or_model(tmp_path, updates, message):
    result_path, state, digest = write_growth(
        tmp_path, growth_result(**updates))

    with pytest.raises(probe.ProbeFailure, match=message):
        probe.probe_growth(result_path, state, digest, 3, 3)


def test_growth_probe_rejects_unexpected_price(tmp_path):
    bad = growth_result()
    bad["content"] = bad["content"].replace("$5.00", "$4.00", 1)
    result_path, state, digest = write_growth(tmp_path, bad)

    with pytest.raises(probe.ProbeFailure, match="hive at"):
        probe.probe_growth(result_path, state, digest, 3, 3)


def test_growth_probe_rejects_state_change(tmp_path):
    result_path, state, digest = write_growth(tmp_path)
    state.write_bytes(b"mutated")

    with pytest.raises(probe.ProbeFailure, match="database changed"):
        probe.probe_growth(result_path, state, digest, 3, 3)
