import pytest

from deploy.droplet import regulatory_radar_wedge_public_probe as public
from deploy.droplet import test_regulatory_radar_wedge_probe as fixtures


def patch_public(monkeypatch, *, health=None, quickstart=None):
    payloads = {
        "/healthz": health or fixtures.gateway_health(payment_enabled=True),
        "/agents": fixtures.agents_page(),
        "/quickstart": (
            quickstart
            if quickstart is not None
            else fixtures.quickstart_page()
        ),
        "/llms.txt": fixtures.llms_page(),
        "/.well-known/skills/viridis-paid-tools/SKILL.md": (
            fixtures.machine_repeat_surface()
        ),
    }
    monkeypatch.setattr(
        public.contract,
        "get_json",
        lambda base, path: payloads[path],
    )
    monkeypatch.setattr(
        public.contract,
        "get_text",
        lambda base, path: payloads[path],
    )


def test_public_probe_accepts_exact_live_contract(monkeypatch):
    patch_public(monkeypatch)

    result = public.probe_public_gateway(
        public.PUBLIC_GATEWAY_BASE,
        "enabled",
    )

    assert result["status"] == "ok"
    assert result["payment_enabled"] is True
    assert set(result["surface_sha256"]) == {
        "agents", "quickstart", "llms", "buyer_skill",
    }


@pytest.mark.parametrize(
    "base",
    [
        "http://mcp.viridisconservation.com",
        "https://mcp.viridisconservation.com.evil.example",
        "https://user@mcp.viridisconservation.com",
        "https://mcp.viridisconservation.com:443",
    ],
)
def test_public_probe_refuses_every_other_origin(monkeypatch, base):
    patch_public(monkeypatch)

    with pytest.raises(public.contract.ProbeFailure, match="exact Viridis"):
        public.probe_public_gateway(base, "enabled")


def test_public_probe_rejects_disabled_payment(monkeypatch):
    patch_public(
        monkeypatch,
        health=fixtures.gateway_health(payment_enabled=False),
    )

    with pytest.raises(public.contract.ProbeFailure, match="not enabled"):
        public.probe_public_gateway(
            public.PUBLIC_GATEWAY_BASE,
            "enabled",
        )


def test_public_probe_rejects_stale_public_quickstart(monkeypatch):
    patch_public(
        monkeypatch,
        quickstart=fixtures.quickstart_page().replace(
            "--route regulatory-radar --max-payment-usdc 0.25",
            "",
        ),
    )

    with pytest.raises(
        public.contract.ProbeFailure,
        match="returning-buyer",
    ):
        public.probe_public_gateway(
            public.PUBLIC_GATEWAY_BASE,
            "enabled",
        )
