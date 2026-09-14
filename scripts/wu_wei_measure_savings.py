#!/usr/bin/env python3
"""Compare supplied execution records. Offline; never executes tasks or pays."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def measure(data):
    if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError('schema_version must be 1')
    tasks = data.get('tasks', [])
    if not isinstance(tasks, list) or not tasks or any(not isinstance(t, str) or not t for t in tasks) or len(set(tasks)) != len(tasks):
        raise ValueError('tasks must be a nonempty list of unique task IDs fixed before comparison')
    for key in ('evaluation_id', 'cost_scope'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f'{key} is required')
    def money(value):
        if type(value) is not int or value < 0:
            raise ValueError('Costs must be nonnegative integer microdollars')
        return value
    def has_text(value):
        return isinstance(value, str) and bool(value.strip())

    arms = {}
    inputs = {}
    gaps = []
    for arm in ('baseline', 'routed'):
        source = data.get(arm, {})
        if not isinstance(source, dict):
            raise ValueError(f'{arm} must be an object')
        fee = money(source.get('overhead_microusd'))
        if not has_text(source.get('overhead_evidence_ref')):
            gaps.append(f'{arm}: overhead evidence missing (zero also requires explanation)')
        rows = source.get('results', [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) or not has_text(row.get('task_id')) for row in rows):
            raise ValueError('results must be a list of objects with task IDs')
        ids = [row['task_id'] for row in rows]
        if len(ids) != len(set(ids)) or set(ids) != set(tasks):
            raise ValueError(f'{arm}: exactly one final result required per manifest task; include failures')
        total = fee
        passed = 0
        inputs[arm] = {}
        for row in rows:
            task = row['task_id']
            sha = row.get('input_sha256', '')
            if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
                raise ValueError('input_sha256 must be a lowercase SHA-256 digest')
            inputs[arm][task] = sha
            if type(row.get('quality_pass')) is not bool:
                raise ValueError('quality_pass must be boolean; evaluate failures too')
            passed += row['quality_pass']
            if not has_text(row.get('quality_evidence_ref')):
                gaps.append(f'{arm}/{task}: quality evidence missing')
            attempts = row.get('attempts', [])
            if not isinstance(attempts, list) or not attempts or any(not isinstance(a, dict) for a in attempts):
                raise ValueError('Each task needs all attempts, including retries and fallbacks')
            for attempt in attempts:
                cost = attempt.get('actual_cost_microusd')
                if cost is None:
                    gaps.append(f'{arm}/{task}: actual attempt cost missing')
                else:
                    total += money(cost)
                if not has_text(attempt.get('cost_evidence_ref')):
                    gaps.append(f'{arm}/{task}: cost evidence missing')
                if not has_text(attempt.get('route_version')):
                    gaps.append(f'{arm}/{task}: route version missing')
        arms[arm] = {'task_count': len(tasks), 'quality_pass_count': passed,
                     'total_cost_microusd': total if not any(g.startswith(arm + '/') and 'actual attempt cost' in g for g in gaps) else None}
    if inputs['baseline'] != inputs['routed']:
        raise ValueError('Baseline and routed input hashes must match for every task')
    complete = not gaps
    equivalent = all(a['quality_pass_count'] == len(tasks) for a in arms.values())
    delta = arms['baseline']['total_cost_microusd'] - arms['routed']['total_cost_microusd'] if complete else None
    status = 'INCOMPLETE_EVIDENCE' if not complete else ('QUALITY_GATE_FAILED' if not equivalent else ('OBSERVED_SAVINGS' if delta > 0 else 'NO_OBSERVED_SAVINGS'))
    report = {'schema_version': 1, 'status': status, 'arms': arms, 'evidence_gaps': gaps,
              'observed_cost_difference_microusd': delta,
              'qualified_savings_microusd': delta if complete and equivalent else None,
              'currency': 'USD', 'input_sha256': digest(data),
              'basis': 'Caller-supplied actual costs and evidence references; references and completeness are not independently verified. Results apply only to this task set, not future traffic.',
              'energy_savings_wh': None}
    report['report_sha256'] = digest(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = measure(json.loads(args.input.read_text()))
    except (ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
