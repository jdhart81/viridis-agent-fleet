import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
import x402_demo_client as c

@pytest.mark.parametrize('route',['wu-wei-router','maxwell-defense'])
def test_new_routes_require_input_before_any_network(route):
    with patch.object(c,'DryRunBuyer',side_effect=AssertionError('network initialized')),contextlib.redirect_stderr(io.StringIO()),pytest.raises(SystemExit):
        c.main(['--route',route,'--dry-run'])

@pytest.mark.parametrize('route',['wu-wei-router','maxwell-defense'])
def test_owned_inputs_and_quote_only(route):
    payload={'owned':'example'}
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'inputs.json';p.write_text(json.dumps(payload))
        with patch.object(c,'run_workflow') as run,contextlib.redirect_stdout(io.StringIO()):
            assert c.main(['--route',route,'--input-file',str(p),'--dry-run'])==0
            assert run.call_args.args[2] is True
            assert run.call_args.kwargs['steps'][0].build_input({})==payload

@pytest.mark.parametrize('route',['wu-wei-router','maxwell-defense'])
def test_no_paid_mode_without_explicit_limit(route):
    with contextlib.redirect_stderr(io.StringIO()),pytest.raises(SystemExit):c.main(['--route',route,'--input-file','unused.json'])

def test_canonical_origin_and_explicit_override():
    assert c.MAXWELL_STEP.url(c.DEFAULT_BASE_URL).startswith('https://mcp.viridis-security.com/')
    assert c.MAXWELL_STEP.url('https://fixture.invalid')=='https://fixture.invalid/x402/maxwell-defense/rehearse_defense'
    assert c.WU_WEI_STEP.url(c.DEFAULT_BASE_URL)==c.DEFAULT_BASE_URL+'/x402/wu-wei-router/plan_workload'

@pytest.mark.parametrize('step',[c.MAXWELL_STEP,c.WU_WEI_STEP])
def test_quote_above_ceiling_never_pays(step):
    from dataclasses import replace
    from unittest.mock import Mock
    buyer=Mock();buyer.challenge.return_value={'status':402,'headers':{},'body':{'accepts':[{'amount':'1000001'}]}}
    with contextlib.redirect_stdout(io.StringIO()),pytest.raises(RuntimeError,match='exceeds'):
        c.run_workflow(c.DEFAULT_BASE_URL,buyer,steps=(replace(step,build_input=lambda _:{}),),max_payment_atomic=1000000)
    buyer.pay.assert_not_called()
