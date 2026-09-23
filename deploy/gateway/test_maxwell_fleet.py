"""Local payment fixtures only. No network, charges or production activation."""
import asyncio
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from payment_gate import PaymentGate
from state_store import StateStore
import x402_http
import x402_rail

ROOT = Path(__file__).resolve().parents[2]
ROUTE = ("maxwell-defense", "rehearse_defense")


class Request:
    method = "POST"
    query_params = {}
    path_params = {"agent": ROUTE[0], "tool": ROUTE[1]}
    def __init__(self, args, headers=None):
        self.args, self.headers = args, headers or {}
    async def json(self):
        return self.args


def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("MAXWELL_FLEET_ENABLED", "1")
    monkeypatch.setenv("X402_ENABLED", "1")
    monkeypatch.setenv("X402_V2_ENABLED", "0")
    monkeypatch.setenv("VIRIDIS_X402_ADDRESS", "0xViridis")
    monkeypatch.setenv("X402_FACILITATOR_URL", "https://fixture.invalid")
    spec = importlib.util.spec_from_file_location("maxwell_paid_fixture", ROOT / "maxwell-defense-agent/src/core.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    core = module.MaxwellDefenseCore()
    store = StateStore(str(tmp_path / "state.db")); store.attach(ROUTE[0], core)
    gate = PaymentGate(store, None, free_calls_per_day=0); gate.attach(ROUTE[0], core)
    handler = x402_http.make_x402_http_route({ROUTE[0]: core}, store, "https://fixture.invalid", tools={ROUTE: ROUTE[1]})
    return handler, core


def test_startup_discovery_is_opt_in():
    code = """
import viridis_mcp_gateway as g
import x402_http as x
import os
enabled = os.environ.get('MAXWELL_FLEET_ENABLED') == '1'
assert ('maxwell-defense' in g.MOUNTS) == enabled
assert (('maxwell-defense','rehearse_defense') in x.X402_HTTP_TOOLS) == enabled
assert not any(m.get('category') == 'security-plane' for m in g.EXTERNAL_MEMBERS)
if enabled:
    entries = g._x402_service_manifest_entries('https://fixture.invalid')
    assert 'maxwell-defense' in str(entries)
    module = g._load_adapter('maxwell-defense', 'maxwell-defense-agent')
    assert module.agent.describe()['enabled'] is True
    assert module.agent.health()['status'] == 'ok'
    import asyncio, json
    from unittest.mock import patch
    with patch.object(module.agent, 'process', side_effect=AssertionError('invalid input reached payment gate')):
        refusal = json.loads(asyncio.run(module.rehearse_defense(0, 250, 2000, 100)))
        assert refusal['error_type'] == 'ValidationError'
"""
    for flag in ("0", "1"):
        result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).parent,
                                env=os.environ | {"MAXWELL_FLEET_ENABLED": flag}, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_unpaid_invalid_disabled_never_execute_or_settle(monkeypatch, tmp_path):
    handler, core = setup(monkeypatch, tmp_path)
    args = x402_http.X402_HTTP_METADATA[ROUTE]["input_example"]
    with patch.object(core, "_gate_inner", side_effect=AssertionError("unpaid work")), \
         patch.object(x402_rail, "verify_and_settle", side_effect=AssertionError("unauthorized settlement")):
        response = asyncio.run(handler(Request(args)))
        assert response.status_code == 402, response.body
        assert json.loads(response.body)["accepts"][0]["maxAmountRequired"] == "1000000"
        assert asyncio.run(handler(Request(args | {"client_hashes_per_second": 0}))).status_code == 400
        monkeypatch.setenv("MAXWELL_FLEET_ENABLED", "0")
        assert asyncio.run(handler(Request(args))).status_code == 503


def test_simulated_payment_delivers_report_and_replay_cannot_charge_again(monkeypatch, tmp_path):
    handler, core = setup(monkeypatch, tmp_path)
    args = x402_http.X402_HTTP_METADATA[ROUTE]["input_example"]
    token = base64.b64encode(json.dumps({"x402Version": 1, "scheme": "exact", "network": "base",
        "payload": {"nonce": "maxwell-local-fixture"}}).encode()).decode()
    with patch.object(x402_rail, "verify_and_settle", return_value={
        "settled": True, "tx_hash": "0xlocal-fixture-only", "network": "base", "amount_atomic": "1000000"}) as settle:
        response = asyncio.run(handler(Request(args, {"x-payment": token})))
        assert response.status_code == 200, response.body
        assert '"protection_activated":false' in response.body.decode()
        repeated = asyncio.run(handler(Request(args, {"x-payment": token})))
        assert repeated.status_code == 402
        assert settle.call_count == 1


def test_mcp_gate_does_not_grant_free_execution(monkeypatch, tmp_path):
    _, core = setup(monkeypatch, tmp_path)
    args = x402_http.X402_HTTP_METADATA[ROUTE]["input_example"]
    result = asyncio.run(core.process({"action": ROUTE[1], **args}))
    assert result["error_type"] == "payment_required"
