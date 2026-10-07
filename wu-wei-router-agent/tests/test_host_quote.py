"""Read-only host quote: no new MCP tool or bypass for core execution."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('quote_fixtures',Path(__file__).with_name('test_router_v2.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


def test_quote_discloses_fee_without_audit_mutation(monkeypatch):
    agent=f.core(monkeypatch);data=f.payload()
    zero=agent.quote_route(data,fee_microusd=0)
    dollar=agent.quote_route(data,fee_microusd=1000000)
    for key in ('decision','chosen_profile','decision_sha256','thermo'):
        assert zero[key]==dollar[key]
    assert agent._router_state()['events']==[]
    assert agent._router_state()['seq']==0
    assert 'quote_route' not in agent.KNOWN_ACTIONS
    assert dollar['service_fee']==1000000 and dollar['preview_only'] is True
    with pytest.raises(ValueError):agent.quote_route(data,fee_microusd=-1)
    monkeypatch.setenv('WU_WEI_V2_ENABLED','0')
    with pytest.raises(ValueError):agent.quote_route(data)


@pytest.mark.parametrize('gross, expected', [(500000, True), (1000000, False), (1500000, False)])
def test_fee_exceeds_modeled_savings_below_equal_above(monkeypatch, gross, expected):
    agent=f.core(monkeypatch);data=f.payload()
    data['profiles'][0]['cost_microusd']=2000
    data['profiles'][1]['cost_microusd']=2000-gross//data['task']['count']
    quote=agent.quote_route(data,fee_microusd=1000000)
    assert quote['modeled_gross_savings']==gross
    assert quote['fee_exceeds_modeled_savings'] is expected
    assert quote['modeled_net_savings_after_fee']==gross-1000000
    assert agent._router_state()['events']==[]
