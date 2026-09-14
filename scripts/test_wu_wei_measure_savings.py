import copy
import pytest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("wu_wei_measure_savings", Path(__file__).with_name("wu_wei_measure_savings.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
measure = module.measure


def sample():
    row = {'task_id': 'a', 'input_sha256': 'a'*64, 'quality_pass': True,
           'quality_evidence_ref': 'test-only-eval', 'attempts': [
               {'actual_cost_microusd': 100, 'cost_evidence_ref': 'test-only-cost', 'route_version': 'fixture-v1'}]}
    arm = {'overhead_microusd': 0, 'overhead_evidence_ref': 'test-only-no-overhead', 'results': [row]}
    d = {'schema_version': 1, 'tasks': ['a'], 'evaluation_id': 'fixture', 'cost_scope': 'test fixture',
         'baseline': copy.deepcopy(arm), 'routed': copy.deepcopy(arm)}
    d['routed']['results'][0]['attempts'][0]['actual_cost_microusd'] = 20
    return d


def test_retries_and_fees_can_erase_savings():
    d = sample()
    d['routed']['results'][0]['attempts'].append(copy.deepcopy(d['baseline']['results'][0]['attempts'][0]))
    d['routed']['overhead_microusd'] = 10
    r = measure(d)
    assert r['status'] == 'NO_OBSERVED_SAVINGS'
    assert r['qualified_savings_microusd'] == -30


def test_missing_cost_is_not_zero():
    d = sample(); d['routed']['results'][0]['attempts'][0]['actual_cost_microusd'] = None
    r = measure(d)
    assert r['status'] == 'INCOMPLETE_EVIDENCE'
    assert r['qualified_savings_microusd'] is None
    assert r['arms']['routed']['total_cost_microusd'] is None


def test_quality_failure_blocks_claim():
    d = sample(); d['routed']['results'][0]['quality_pass'] = False
    r = measure(d)
    assert r['status'] == 'QUALITY_GATE_FAILED'
    assert r['observed_cost_difference_microusd'] == 80
    assert r['qualified_savings_microusd'] is None


def test_different_inputs_rejected():
    d = sample(); d['routed']['results'][0]['input_sha256'] = 'b'*64
    with pytest.raises(ValueError, match='must match'): measure(d)


def test_dropped_failure_rejected():
    d = sample(); d['tasks'].append('failed-task')
    with pytest.raises(ValueError, match='manifest task'): measure(d)


def test_missing_receipt_blocks_claim():
    d = sample(); d['baseline']['results'][0]['attempts'][0]['cost_evidence_ref'] = ''
    assert measure(d)['status'] == 'INCOMPLETE_EVIDENCE'


def test_negative_and_boolean_costs_rejected():
    for cost in (-1, True):
        d = sample(); d['baseline']['overhead_microusd'] = cost
        with pytest.raises(ValueError): measure(d)


def test_comparable_records_and_reproducible_digest():
    d = sample(); r = measure(d)
    assert r['status'] == 'OBSERVED_SAVINGS'
    assert r['qualified_savings_microusd'] == 80
    assert r == measure(copy.deepcopy(d))


@pytest.mark.parametrize('bad', [None, [], {'schema_version': True}, {'schema_version': 1, 'tasks': 'a'}])
def test_malformed_manifest_rejected(bad):
    with pytest.raises(ValueError): measure(bad)


def test_whitespace_is_not_evidence():
    d = sample(); d['routed']['overhead_evidence_ref'] = '   '
    assert measure(d)['status'] == 'INCOMPLETE_EVIDENCE'


@pytest.mark.parametrize('field,value', [('results', None), ('results', [None])])
def test_malformed_results_rejected(field, value):
    d = sample(); d['routed'][field] = value
    with pytest.raises(ValueError): measure(d)
