import json
import os
import sys
from pathlib import Path
from starlette.testclient import TestClient

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import viridis_mcp_gateway as gateway


def test_all_buyer_intents_select_bounded_service_without_execution(monkeypatch,tmp_path):
    monkeypatch.setenv('STATE_DB',str(tmp_path/'state.sqlite3'))
    cases=json.loads((HERE.parents[1]/'config/agent_search_cases.json').read_text())['cases']
    with TestClient(gateway.build_app()) as client:
        for case in cases:
            r=client.post('/adopt',json={'objective':case['query']})
            assert r.status_code==200
            d=r.json();selected=d.get('route_decision',{}).get('selected') or {}
            expected=case['expected_route']
            if case.get('enabled_if') and os.environ.get(case['enabled_if']) != '1':
                expected=None
            assert selected.get('route')==expected,case
            assert all(d[k] is False for k in ('money_moved','payment_authorized','tool_executed','state_persisted'))
            if case['expected_route'] is None:assert d['decision']=='NO_MATCH'
