"""WW-O1..O5, O7: modeled energy within baseline cost; unchanged Wilson eligibility."""
import copy
import pytest
import importlib.util
from pathlib import Path
# Explicit fixture-module registration also works with pytest importlib mode.
spec=importlib.util.spec_from_file_location('ww_objective_fixtures',Path(__file__).with_name('test_router_v2.py'))
fixtures=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
module, core, payload, admitted = fixtures.module, fixtures.core, fixtures.payload, fixtures.admitted


def alternatives():
    data=payload()
    third=copy.deepcopy(data['profiles'][1])
    third.update(id='efficient',cost_microusd=8000,power_w=1)
    data['profiles'].append(third)
    return data


def test_ww_o1_lower_energy_beats_cheapest(monkeypatch):
    data=alternatives();r=admitted(core(monkeypatch),data)
    assert r['chosen_profile']=='efficient'
    assert r['decision_record']['selection_objective']=='least_energy_within_baseline_cost'
    # Input order cannot change the tie-breaking or normalized digest.
    data['profiles'].reverse()
    assert admitted(core(monkeypatch),data)['decision_sha256']==r['decision_sha256']


def test_ww_o2_over_baseline_never_chosen(monkeypatch):
    data=alternatives();data['profiles'][-1]['cost_microusd']=10001
    assert admitted(core(monkeypatch),data)['chosen_profile']=='small'


def test_ww_o3_any_capped_missing_power_cost_fallback(monkeypatch):
    data=alternatives();data['profiles'][-1].pop('power_w')
    r=admitted(core(monkeypatch),data)
    assert r['chosen_profile']=='small'
    assert r['decision_record']['selection_objective']=='cost_fallback_missing_power'
    # Missing baseline power must never create a modeled savings delta.
    data['profiles'][0].pop('power_w')
    t=admitted(core(monkeypatch),data)['thermo']
    assert t['status']=='insufficient data for savings' and 'modeled_savings_uj' not in t


def test_ww_o4_baseline_least_energy_no_change(monkeypatch):
    data=alternatives();data['profiles'][0]['power_w']=0
    r=admitted(core(monkeypatch),data)
    assert r['chosen_profile']=='baseline' and r['decision']=='BASELINE_OPTIMAL_NO_CHANGE'
    assert r['thermo']['modeled_savings_uj']==0
    assert r['decision_record']['selection_objective']=='least_energy_within_baseline_cost'


def test_ww_o5_fee_neutrality(monkeypatch):
    data=alternatives();results=[]
    for fee in (0,1000000):
        monkeypatch.setattr(module,'FEE',fee)
        results.append(admitted(core(monkeypatch),data))
    a,b=results
    assert a['decision_record']==b['decision_record']
    assert a['decision_sha256']==b['decision_sha256']
    assert a['chosen_profile']==b['chosen_profile']=='efficient'
    assert a['thermo']==b['thermo']
    assert a['economics']['service_fee']==0 and b['economics']['service_fee']==1000000


def test_ww_o7_ineligible_baseline_still_rejected(monkeypatch):
    data=alternatives();data['profiles'][0]['approved']=False
    agent=core(monkeypatch)
    r=admitted(agent,data)
    assert r['error_type']=='ValidationError'
    assert r['message']=='Baseline must meet the same eligibility constraints; use representative evaluation data'
    assert agent._router_state()['events']==[]


def test_budget_cap_defensive_check():
    data=alternatives();data['profiles'][0]['approved']=False
    with pytest.raises(AssertionError,match='Budget cap must contain eligible baseline'):
        module._decision_record(data['profiles'],data['task'])
