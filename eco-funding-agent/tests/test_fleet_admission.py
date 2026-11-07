"""Viridis fleet Agent Admission Invariants (AA1-AA7, ratified 2026-07-18), checked for
this agent. The gateway-side wiring (MOUNTS, Dockerfile, deck/Glama ROLE maps) lives in
the gateway repository and is specified in deploy/fleet/MOUNT.md."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import shutil
import subprocess
import sys

import pytest
from conftest import ROOT, clone

from viridis_eco_funding import make_receipt
from viridis_eco_funding.fleet import (
    ACTIONS,
    FREE_RAIL_REASON,
    MOUNT,
    SEO,
    EcoFundingAgentCore,
    build,
)

PAID_OR_MONEY_MOUNTS = {"escrow", "settlement", "payments", "surety", "subscriptions", "x402",
                        "metering", "erc8004"}
KNOWN_FLEET_MOUNTS = {"identity", "trust", "escrow", "metering", "arbitration", "compute-ledger",
                      "covenant", "hive", "provenance", "offsets", "erc8004", "surety", "notary",
                      "wavefunction", "smartscale", "protogen", "regulatory-radar",
                      "narrative-engine", "taxcredit-engine", "ghg-ledger", "quantity-takeoff",
                      "disclosure-compiler", "verified", "verdigraph", "neurogenesis",
                      "green-router", "viridisos", "security-preflight", MOUNT}


def yaml_text() -> str:
    return (ROOT / "agent.yaml").read_text(encoding="utf-8")


def test_AA1_seo_entry_bounded_and_consistent():
    assert SEO["desc"] and len(SEO["desc"]) <= 280
    assert 2 <= len(SEO["queries"]) <= 5
    text = yaml_text()
    assert SEO["desc"] in text, "agent.yaml seo.desc must match fleet.SEO"
    for query in SEO["queries"]:
        assert query in text


def test_AA2_declared_free_rail_never_priced():
    text = yaml_text()
    assert re.search(r'model:\s*"free_rail"', text)
    assert FREE_RAIL_REASON in text
    assert re.search(r"^money_credentials:\s*\[\]\s*$", text, re.M)
    assert re.search(r"^credentials:\s*\[\]\s*$", text, re.M)
    assert build().describe()["economics"] == {"model": "free_rail", "reason": FREE_RAIL_REASON}
    mount_doc = (ROOT / "deploy" / "fleet" / "MOUNT.md").read_text()
    assert "Do **not** add it to `PRICE_MINOR`" in mount_doc


def test_AA3_revenue_model_and_thesis_on_record():
    text = yaml_text()
    for key in ("revenue_model:", "thesis_connection:"):
        assert key in text
        block = text.split(key, 1)[1].split("\n", 1)[1]
        assert len(block.strip()) > 80, f"{key} is empty"


@pytest.mark.parametrize("action", ACTIONS)
def test_AA4_every_success_envelope_teaches_edges(action, woodland_site, example_pool):
    core = EcoFundingAgentCore()
    receipt = make_receipt(woodland_site)
    payloads = {
        "value_site": {"site": woodland_site},
        "explain_valuation": {"valuation_or_site": woodland_site},
        "verify_receipt": {"receipt": receipt},
        "simulate_pool": {"pool": example_pool, "observations": [{"period": 0, "receipt": receipt}]},
        "describe_method": {},
    }
    out = asyncio.run(core.process({"action": action, **payloads[action]}))
    assert out["status"] == "ok", out
    steps = out["next_steps"]
    assert steps, f"{action} teaches no edges"
    for step in steps:
        assert step["mount"] in KNOWN_FLEET_MOUNTS
        assert step["mount"] not in PAID_OR_MONEY_MOUNTS, "no edges to money rails"
        assert step["endpoint"] == f"https://mcp.viridisconservation.com/{step['mount']}/mcp"
        assert step["why"]
    if action == "value_site":
        assert {"notary", "regulatory-radar", "ghg-ledger"} <= {s["mount"] for s in steps}
    assert "legal review before money moves" in out["notice"]


def test_gateway_contract_describe_health_errors():
    core = build()
    described = core.describe()
    assert {"name", "version", "capabilities"} <= set(described)
    assert described["capabilities"] == list(ACTIONS)
    assert described["read_only"] is True and described["money_movement"] is False
    assert core.health()["status"] == "ok"
    for payload, kind in (({"action": "transfer"}, "unknown_action"), ("nope", "invalid_input"),
                          ({"action": "value_site", "site": {"site_id": "x"}}, "invalid_input"),
                          ({"action": "verify_receipt", "receipt": {}, "refetch_source": True},
                           "invalid_input")):
        out = core.process_sync(payload)
        assert out["status"] == "error" and out["error_type"] == kind, out


def test_value_site_binding_uses_injected_read_only_client(woodland_site, synthetic_record):
    from viridis_eco_funding.vergecommon import ReadOnlyVergeCommonClient

    def opener(request, timeout):
        assert request.get_method() == "GET"
        import io

        class R(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *e):
                return False
        return R(json.dumps(synthetic_record).encode())

    core = EcoFundingAgentCore(client_factory=lambda: ReadOnlyVergeCommonClient(opener=opener))
    out = core.process_sync({"action": "value_site", "site": woodland_site, "bind_vergecommon": True})
    assert out["result"]["receipt"]["source"]["project_kind"] == "woodland"
    receipt = out["result"]["receipt"]
    verified = core.process_sync({"action": "verify_receipt", "receipt": receipt, "refetch_source": True})
    assert verified["result"]["valid"] is True


def test_adapter_loads_like_the_gateway_and_lists_five_read_only_tools():
    pytest.importorskip("mcp")
    for name in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location("gateway_adapter_eco_funding",
                                                  ROOT / "adapters" / "mcp_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert isinstance(module.agent, EcoFundingAgentCore)
    tools = asyncio.run(module.mcp.list_tools())
    assert sorted(t.name for t in tools) == sorted(ACTIONS)
    assert module.agent.READ_ACTIONS == module.agent.KNOWN_ACTIONS == frozenset(ACTIONS)
    for tool in tools:
        ann = tool.annotations
        read_only = getattr(ann, "read_only_hint", getattr(ann, "readOnlyHint", None))
        destructive = getattr(ann, "destructive_hint", getattr(ann, "destructiveHint", None))
        assert read_only is True and destructive is False


def test_gateway_emulation_over_http():
    """deploy/fleet/gateway_check.py mounts the adapter at /eco-funding/mcp and calls every
    tool over JSON-RPC (loopback). Set VEF_GATEWAY_PYTHON to an mcp==1.28.1 interpreter to
    also run it under the gateway's pinned SDK."""
    pytest.importorskip("mcp")
    pytest.importorskip("uvicorn")
    import os
    pythons = [sys.executable] + [p for p in [os.environ.get("VEF_GATEWAY_PYTHON")] if p]
    for python in pythons:
        env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
        out = subprocess.run([python, "-W", "ignore", str(ROOT / "deploy" / "fleet" / "gateway_check.py")],
                             capture_output=True, text=True, timeout=180, env=env)
        assert out.returncode == 0, out.stderr[-3000:]
        report = json.loads(out.stdout.strip().splitlines()[-1])
        assert report["ok"] is True and report["endpoint"] == "/eco-funding/mcp"


def test_AA6_registry_manifest_and_tools_json():
    server = json.loads((ROOT / "deploy" / "fleet" / "server.json").read_text())
    assert server["name"] == "io.github.jdhart81/eco-funding"  # fleet convention: agent folder / mount name
    assert len(server["description"]) <= 100
    assert server["remotes"] == [{"type": "streamable-http",
                                  "url": "https://mcp.viridisconservation.com/eco-funding/mcp"}]
    from viridis_eco_funding import __version__
    assert server["version"] == __version__
    assert f'version: "{__version__}"' in yaml_text(), "agent.yaml and core version in lockstep"
    tools = json.loads((ROOT / "deploy" / "fleet" / "tools.json").read_text())
    assert sorted(t["name"] for t in tools["tools"]) == sorted(ACTIONS)


def test_AA7_quickstart_worked_example_is_valid(woodland_site):
    snippet = (ROOT / "deploy" / "fleet" / "QUICKSTART_SNIPPET.md").read_text()
    assert "https://mcp.viridisconservation.com/eco-funding/mcp" in snippet
    body = snippet.split("-d '", 1)[1].split("'\n", 1)[0]
    request = json.loads(body)
    site = request["params"]["arguments"]["site"]
    out = build().process_sync({"action": "value_site", "site": clone(site)})
    assert out["status"] == "ok" and out["result"]["headline"]["complexity_score"] > 0


def test_fleet_contract_C4_error_flagging_is_wired_inside_a_fleet_tree(tmp_path):
    """Fleet C4: in a fleet tree the adapter wraps its tools with fleet_utils'
    flag_error_results (isError on error envelopes); standalone it is a no-op."""
    pytest.importorskip("mcp")
    fleet = tmp_path / "fleet"
    (fleet / "fleet_utils").mkdir(parents=True)
    (fleet / "fleet_utils" / "__init__.py").write_text("")
    (fleet / "fleet_utils" / "mcp_errors.py").write_text(
        "CALLS = []\n"
        "def flag_error_results(server):\n"
        "    CALLS.append(server)\n"
        "    return 5\n")
    agent_dir = fleet / "eco-funding-agent"
    shutil.copytree(ROOT / "adapters", agent_dir / "adapters")
    shutil.copytree(ROOT / "src", agent_dir / "src", ignore=shutil.ignore_patterns("__pycache__"))
    probe = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('ad', r'{agent_dir / 'adapters' / 'mcp_server.py'}')\n"
        "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)\n"
        "import fleet_utils.mcp_errors as m\n"
        "assert m.CALLS == [mod.mcp], m.CALLS\n"
        "print('wired')\n")
    # -I: ignore an inherited PYTHONPATH (the fleet test runner puts the real fleet root on it)
    out = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0 and out.stdout.strip() == "wired", out.stderr


def test_open_core_layout_shim():
    """The open-core split requires src/core.py + adapters/mcp_server.py + tests/ per agent."""
    import importlib.util as iu
    spec = iu.spec_from_file_location("eco_core_shim", ROOT / "src" / "core.py")
    module = iu.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.build().describe()["name"] == "viridis-eco-funding"
    assert (ROOT / "adapters" / "mcp_server.py").is_file() and (ROOT / "tests").is_dir()


def test_core_is_stateless_for_the_gateway_state_store():
    """StateStore pickles instance state and restores it at boot; a default core must carry
    none, so a stale snapshot can never override the running version."""
    import pickle
    core = build()
    assert core.__dict__ == {}
    restored = build()
    restored.__dict__.update(pickle.loads(pickle.dumps({"version": "0.0.0-stale"})))
    assert restored.describe()["version"] == restored.health()["version"] == build().describe()["version"]
    assert restored.describe()["version"] != "0.0.0-stale"
