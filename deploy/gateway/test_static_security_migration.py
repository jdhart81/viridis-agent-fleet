import asyncio
import base64
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from payment_gate import PaymentGate
from state_store import StateStore
import x402_http
import x402_rail
from value_decision import build_value_decision
from adoption_loop import build_adoption_plan


class Request:
    method = 'POST'
    query_params = {}
    def __init__(self, tool, args, headers=None):
        self.path_params = {'agent': 'security-preflight', 'tool': tool}
        self.headers = headers or {}
        self.args = args
    async def json(self):
        return self.args


def setup(monkeypatch, tmp_path):
    key = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    monkeypatch.setenv('SECURITY_PREFLIGHT_SIGNING_KEY_PKCS8_B64',base64.b64encode(key).decode())
    monkeypatch.setenv('X402_ENABLED','1')
    monkeypatch.setenv('X402_V2_ENABLED','0')
    monkeypatch.setenv('VIRIDIS_X402_ADDRESS','0xViridis')
    monkeypatch.setenv('X402_FACILITATOR_URL','https://fac.test')
    spec = importlib.util.spec_from_file_location('migrated_security',
            Path(__file__).resolve().parents[2]/'security-preflight-agent/src/core.py')
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    core = module.SecurityPreflightCore(str(tmp_path/'receipts.db'))
    store = StateStore(str(tmp_path/'state.db'));store.attach('security-preflight',core)
    gate = PaymentGate(store, None, free_calls_per_day=0);gate.attach('security-preflight',core)
    return x402_http.make_x402_http_route({'security-preflight':core},store,'https://mcp.test'),core,module


def test_both_quotes_have_fixed_price_without_worker_execution(monkeypatch,tmp_path):
    handler,core,module = setup(monkeypatch,tmp_path)
    with patch.object(module.subprocess,'run',side_effect=AssertionError('unpaid execution')):
        for tool in ['scan_source','screen_injection']:
            meta = x402_http.X402_HTTP_METADATA[('security-preflight',tool)]
            response = asyncio.run(handler(Request(tool,meta['input_example'])))
            assert response.status_code == 402
            body = json.loads(response.body)
            assert str(body['accepts'][0]['maxAmountRequired']) == '1000000'
    assert core._receipt_db.execute('select count(*) from security_preflight_receipts').fetchone()[0] == 0


def test_invalid_request_never_reaches_settlement(monkeypatch,tmp_path):
    handler,_,_ = setup(monkeypatch,tmp_path)
    with patch.object(x402_rail,'verify_and_settle',side_effect=AssertionError('invalid payment')):
        response = asyncio.run(handler(Request('scan_source',{'agent_id':'buyer-example','source':'https://example.com/repo'})))
        assert response.status_code == 400


def test_simulated_paid_call_delivers_once_with_redacted_receipt(monkeypatch,tmp_path):
    handler,core,_ = setup(monkeypatch,tmp_path)
    token = base64.b64encode(json.dumps({'x402Version':1,'scheme':'exact','network':'base',
                                        'payload':{'nonce':'static-security-test'}}).encode()).decode()
    args=json.loads(json.dumps(x402_http.X402_HTTP_METADATA[('security-preflight','screen_injection')]['input_example']))
    args['texts'][0] += ' PRIVATE-FIXTURE-5d881'
    with patch.object(x402_rail,'verify_and_settle',return_value={
            'settled':True,'tx_hash':'0xlocal-fixture-only','network':'base','amount_atomic':'1000000'}) as settle:
        response=asyncio.run(handler(Request('screen_injection',args,{'x-payment':token})))
        assert response.status_code == 200, response.body
        assert args['texts'][0] not in response.body.decode()
        assert core._receipt_db.execute('select count(*) from security_preflight_receipts').fetchone()[0] == 1
        repeated=asyncio.run(handler(Request('screen_injection',args,{'x-payment':token})))
        assert repeated.status_code == 402
        assert settle.call_count == 1
        assert core._receipt_db.execute('select count(*) from security_preflight_receipts').fetchone()[0] == 1


def test_adoption_selects_migrated_tools_without_old_manifest_watch():
    for tool, objective in [('scan_source','VulnCanon scan source code'),
                            ('screen_injection','screen injection text samples')]:
        inputs=x402_http.X402_HTTP_METADATA[('security-preflight',tool)]['input_example']
        plan=build_adoption_plan('https://mcp.test',objective,inputs=inputs,max_price_minor=100)
        assert plan['decision']=='READY_FOR_QUOTE',plan
        assert plan['integration']['route']=='security-preflight/'+tool
        assert 'change_check' not in plan['integration']
        assert plan['payment_authorized'] is False
