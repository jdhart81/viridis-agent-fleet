"""Standard-library, offline validation of one proposed synthetic fixture."""
import hashlib
import json
from pathlib import Path

ORDERING = {
    'key': 'sequence',
    'direction': 'ascending',
    'unique_fields': ['sequence', 'event_id'],
    'noncanonical_input': 'reject; never sort or repair',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical_bytes(value):
    """Project-specific Python JSON encoding; not a broader canonicalization standard."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
        allow_nan=False,
    ).encode('utf-8')


def content_hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'Duplicate JSON object key')
        out[key] = value
    return out


def load(path):
    def bad_constant(value):
        raise ValueError('Non-finite JSON constant')

    return json.loads(
        Path(path).read_text(encoding='utf-8'),
        object_pairs_hook=unique_object,
        parse_constant=bad_constant,
    )


def ordered(rows):
    require(isinstance(rows, list), 'Events must be an array')
    sequences = [row['sequence'] for row in rows]
    require(
        all(type(s) is int and s > 0 for s in sequences),
        'Sequences must be positive integers',
    )
    require(
        sequences == sorted(set(sequences)),
        'Unsorted or duplicate event sequence',
    )
    ids = [row['event_id'] for row in rows]
    require(len(ids) == len(set(ids)), 'Duplicate event ID')
    return sequences


def verdict(fixture, case):
    require(fixture['canonical_event_ordering'] == ORDERING, 'Ordering rule differs')
    stored = fixture['stored_events']
    sequence = ordered(stored)
    require(
        sequence == list(range(1, len(stored) + 1)),
        'Stored history must be contiguous from 1',
    )
    require(
        len(fixture['run_ids']) == len(set(fixture['run_ids'])),
        'Duplicate declared run ID',
    )
    require(
        all(e['run_id'] in fixture['run_ids'] for e in stored),
        'Unknown stored run ID',
    )
    anchor = fixture['coverage_anchor']
    require(
        anchor == {
            'expected_earliest_sequence': 1,
            'event_id': stored[0]['event_id'],
        },
        'Supplied anchor mismatch',
    )
    first = next((e for e in stored if e['outcome'] == 'blocked'), None)
    require(
        first is not None
        and first['event_id'] == fixture['first_blocker_event']
        and first['step'] == 'pre_registration',
        'First blocker mismatch',
    )
    basis = case['coverage_basis']
    require(
        basis['method'] == 'exact_sequence_set'
        and basis['supplied_anchor'] == anchor,
        'Coverage basis mismatch',
    )
    require(
        basis['evidence'] == 'caller_supplied_synthetic_readback'
        and basis['timestamps_establish_coverage'] is False
        and basis['collection_completeness_proven'] is False,
        'Unsupported evidence claim',
    )
    interval = basis['required_interval']
    require(
        isinstance(interval, list)
        and len(interval) == 2
        and all(type(x) is int for x in interval),
        'Invalid required interval',
    )
    start, end = interval
    require(
        start == anchor['expected_earliest_sequence']
        and start <= end <= len(stored),
        'Required interval outside anchor/history',
    )
    visible = case['returned_events']
    selected = ordered(visible)
    require(
        all(1 <= s <= len(stored) for s in selected),
        'Unknown returned sequence',
    )
    require(
        all(e == stored[e['sequence'] - 1] for e in visible),
        'Readback event content changed',
    )
    bounds = [selected[0], selected[-1]] if selected else None
    require(
        case['returned_range'] == bounds,
        'Reported returned bounds inconsistent with actual rows',
    )
    require(
        list(dict.fromkeys(e['run_id'] for e in visible)) == case['run_ids'],
        'Case run IDs inconsistent with actual rows',
    )
    # A supplied anchor or complete oracle cannot fill missing visible rows.
    if selected != list(range(start, end + 1)):
        return 'INSUFFICIENT_COVERAGE'
    blocker = next((e for e in visible if e['outcome'] == 'blocked'), None)
    if blocker is None:
        return 'UNRESOLVED'
    final = visible[-1]
    if final['step'] == 'synthetic_probe_completed' and final['outcome'] == 'succeeded':
        require(
            final['run_id'] != blocker['run_id'],
            'Retry must use a distinct run ID',
        )
        require(
            any(
                e['step'] == 'retry_started' and e['run_id'] == final['run_id']
                for e in visible
            ),
            'Retry start missing',
        )
        return 'RECOVERED_WITH_PRIOR_BLOCKER'
    return 'BLOCKED' if final['outcome'] == 'blocked' else 'UNRESOLVED'


def validate(fixture):
    require(
        fixture['version'] == '0.1.1'
        and fixture['status'] == 'PROPOSED_SYNTHETIC_CONTRACT',
        'Wrong fixture version/status',
    )
    require(
        fixture['verdict_vocabulary'] == {
            'fixture_local': ['BLOCKED', 'RECOVERED_WITH_PRIOR_BLOCKER', 'UNRESOLVED'],
            'required_conformance_outcome': 'INSUFFICIENT_COVERAGE',
        },
        'Verdict vocabulary changed',
    )
    cases = fixture['cases']
    require(
        len({c['case_id'] for c in cases}) == len(cases),
        'Duplicate case ID',
    )
    results = {c['case_id']: verdict(fixture, c) for c in cases}
    for c in cases:
        require(results[c['case_id']] == c['expected_verdict'], 'Expected verdict mismatch')
    initial = next(
        c for c in cases if c['case_id'] == 'complete_history'
    )['returned_events']
    retry = next(
        c for c in cases if c['case_id'] == 'retry_after_fix'
    )['returned_events']
    require(
        canonical_bytes(retry[:len(initial)]) == canonical_bytes(initial),
        'Retry changes first-run history',
    )
    return results


if __name__ == '__main__':
    fixture = load(Path(__file__).with_name('fixture.json'))
    print(json.dumps(
        {
            'results': validate(fixture),
            'fixture_content_sha256': content_hash(fixture),
        },
        sort_keys=True,
    ))
