"""Native Wilson routing invariants; local admission fixtures, no billing rail."""
import asyncio
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ww_v2_core', ROOT / 'src/core.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def core(monkeypatch):
    monkeypatch.setenv('WU_WEI_FLEET_ENABLED', '1')
    monkeypatch.setenv('WU_WEI_V2_ENABLED', '1')
    return module.WuWeiRouterCore()


def payload():
    data = json.loads((ROOT / 'example.json').read_text())
    data['profiles'][0]['power_w'] = 100
    data['profiles'][1]['power_w'] = 10.125
    return {'action': 'route_task', 'profiles': data['profiles'], 'task': data['tasks'][0]}


def admitted(agent, data):
    with agent.admitted_request():
        return asyncio.run(agent.process(data))


def test_ww_v3_stable_decision_separate_audit_identity(monkeypatch):
    agent = core(monkeypatch)
    data = payload()
    first = admitted(agent, data)
    data['profiles'].reverse()
    second = admitted(agent, data)
    assert first['status'] == second['status'] == 'ok'
    assert first['decision_record'] == second['decision_record']
    assert first['decision_sha256'] == second['decision_sha256']
    assert first['decision_id'] != second['decision_id']
    record = first['decision_record']
    assert 'at' not in record and 'decision_id' not in record
    assert first['decision_sha256'] == hashlib.sha256(module.canonical_decision(record)).hexdigest()
    assert record['thermo']['chosen_energy_uj'] == 5062500000
    assert record['thermo']['baseline_energy_uj'] == 100000000000
    module.canonical_decision(record)  # recursive no-float check
    assert first['execution_authorized'] is False
    assert first['energy_savings_measured'] is False


def test_ww_v4_baseline_optimal_is_full_success(monkeypatch):
    agent = core(monkeypatch)
    data = payload()
    data['profiles'][1]['approved'] = False
    result = admitted(agent, data)
    assert result['status'] == 'ok'
    assert result['decision'] == 'BASELINE_OPTIMAL_NO_CHANGE'
    assert result['chosen_profile'] == result['baseline_profile'] == 'baseline'
    assert result['reason'] == 'baseline optimal / no change'
    assert result['thermo']['modeled_savings_uj'] == 0
    assert result['economics']['modeled_net_savings_after_fee'] == -1000000


def test_ww_v6_standalone_refuses_mutations(monkeypatch):
    agent = core(monkeypatch)
    assert asyncio.run(agent.process(payload()))['error_type'] == 'payment_required'
    assert agent._router_state()['events'] == []
    assert asyncio.run(agent.process({'action': 'export_state'}))['status'] == 'ok'


@pytest.mark.parametrize('mutation', [
    lambda d: d['profiles'][0].update(power_w=True),
    lambda d: d['profiles'][0].update(power_w=float('nan')),
    lambda d: d['profiles'][0].update(trials=True),
    lambda d: d['task'].update(count=0),
    lambda d: d['task'].update(baseline_profile='missing'),
    lambda d: d['profiles'].append(copy.deepcopy(d['profiles'][0])),
    lambda d: d.update(_authorized=True),
])
def test_invalid_before_admission(monkeypatch, mutation):
    agent = core(monkeypatch)
    data = payload()
    mutation(data)
    result = asyncio.run(agent.process(data))
    assert result['error_type'] == 'ValidationError'
    assert agent._router_state()['events'] == []


def test_registration_outcome_export_import_round_trip(monkeypatch):
    agent = core(monkeypatch)
    data = payload()
    for profile in data['profiles']:
        assert admitted(agent, {'action': 'register_compute_profile', 'profile': profile})['status'] == 'ok'
    route = admitted(agent, {'action': 'route_task', 'task': data['task']})
    outcome = {'action': 'record_route_outcome', 'decision_id': route['decision_id'], 'successes': 9, 'trials': 10}
    assert admitted(agent, outcome)['outcome']['source'] == 'caller-reported'
    assert admitted(agent, outcome)['error_type'] == 'ValidationError'
    state = asyncio.run(agent.process({'action': 'export_state'}))['state']
    restored = core(monkeypatch)
    assert admitted(restored, {'action': 'import_state', 'state': state})['status'] == 'ok'
    assert asyncio.run(restored.process({'action': 'export_state'}))['state'] == state
    again = admitted(restored, {'action': 'route_task', 'task': data['task']})
    assert again['decision_sha256'] == route['decision_sha256']
    assert again['decision_id'] > route['decision_id']
    state['events'][0]['decision_record']['chosen_profile'] = 'baseline'
    before = copy.deepcopy(restored._router_state())
    assert admitted(restored, {'action': 'import_state', 'state': state})['error_type'] == 'ValidationError'
    assert restored._router_state() == before


def test_missing_power_and_energy_shortfall_are_explicit(monkeypatch):
    agent = core(monkeypatch)
    data = payload()
    del data['profiles'][1]['power_w']
    result = admitted(agent, data)
    assert result['thermo']['status'] == 'insufficient data for savings'
    assert 'modeled_savings_uj' not in result['thermo']
    data['profiles'][1]['power_w'] = 1000
    result = admitted(agent, data)
    assert result['thermo']['modeled_savings_uj'] == 0
    assert result['thermo']['chosen_energy_exceeds_baseline'] is False


def test_fee_neutrality_and_honest_shortfall(monkeypatch):
    agent = core(monkeypatch)
    data = payload()
    data['task']['count'] = 1
    monkeypatch.setattr(module, 'FEE', 0)
    free = admitted(agent, data)
    monkeypatch.setattr(module, 'FEE', 1000000)
    paid = admitted(agent, data)
    assert paid['decision_record'] == free['decision_record']
    assert paid['decision_sha256'] == free['decision_sha256']
    assert paid['decision'] == 'SHADOW_TRIAL_RECOMMENDED'
    assert paid['economics']['modeled_net_savings_after_fee'] < 0


def test_admission_is_scoped_per_core_and_task(monkeypatch):
    a, b = core(monkeypatch), core(monkeypatch)
    async def calls():
        async def allowed():
            with a.admitted_request():
                return await a.process(payload())
        async def refused():
            return await a.process(payload())
        return await asyncio.gather(allowed(), refused())
    results = asyncio.run(calls())
    assert results[0]['status'] == 'ok'
    assert results[1]['error_type'] == 'payment_required'
    with a.admitted_request():
        assert asyncio.run(b.process(payload()))['error_type'] == 'payment_required'
    assert asyncio.run(a.process(payload()))['error_type'] == 'payment_required'
