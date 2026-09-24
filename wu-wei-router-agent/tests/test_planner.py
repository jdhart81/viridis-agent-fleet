import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import pytest
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('wwr',root/'src/core.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def run(p,monkeypatch):
    monkeypatch.setenv('WU_WEI_FLEET_ENABLED','1')
    return asyncio.run(m.WuWeiRouterCore().process({'action':'plan_workload',**p}))

def example(): return json.loads((root/'example.json').read_text())

def test_cost_fee_and_determinism(monkeypatch):
    p=example();r=run(p,monkeypatch)
    assert r['routes'][0]['profile_id']=='small'
    assert r['economics']['modeled_net_savings_after_fee']==7000000
    assert r==run(p,monkeypatch)
    assert r['execution_authorized'] is False

@pytest.mark.parametrize('field,value',[('approved',False),('successes',90),('p95_latency_ms',2000),('task_class','other')])
def test_cheaper_ineligible_route_never_selected(monkeypatch,field,value):
    p=example();p['profiles'][1][field]=value
    r=run(p,monkeypatch);assert r['routes'][0]['profile_id']=='baseline'
    assert r['decision']=='NO_NET_SAVINGS_AT_THIS_VOLUME'

@pytest.mark.parametrize('mutation',[lambda p:p['profiles'][0].update(cost_microusd=True),lambda p:p['profiles'][0].update(successes=101),lambda p:p['profiles'][0].update(evidence_age_seconds=604801),lambda p:p['tasks'][0].update(requires_local=True),lambda p:p['profiles'].append(copy.deepcopy(p['profiles'][0])),lambda p:p.update(extra='x'),lambda p:p['tasks'][0].update(count=0)])
def test_reject_before_paid_execution(monkeypatch,mutation):
    p=example();mutation(p);assert run(p,monkeypatch)['error_type']=='ValidationError'

def test_small_workload_does_not_hide_fee(monkeypatch):
    p=example();p['tasks'][0]['count']=1;r=run(p,monkeypatch)
    assert r['economics']['modeled_net_savings_after_fee']==-992000
    assert r['decision']=='NO_NET_SAVINGS_AT_THIS_VOLUME'
