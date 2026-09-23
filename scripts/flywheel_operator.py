#!/usr/bin/env python3
"""Read public discovery and existing commercial probes; write local evidence only.

No payment, message, listing publication or production mutation is performed.
Detected network entries are review candidates, never fetch targets or authority.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from flywheel_work_receipts import apply_receipts, receipt_for, schedule_status
import compounding_controller

ROOT = Path(__file__).resolve().parents[1]


def stamp():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def read_json(path, default):
    # Corrupt evidence is an error, not a fresh empty baseline.
    return json.loads(path.read_text()) if path.exists() else default


def fetch(url):
    if urllib.parse.urlsplit(url).scheme != 'https':
        raise ValueError('Only configured public HTTPS sources are supported')
    request = urllib.request.Request(url, headers={'User-Agent': 'Viridis-flywheel-audit/1.0'})
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read(6_000_001)
        if len(body) > 6_000_000:
            raise ValueError('Response exceeds evidence limit')
        return {'status': response.status, 'url': response.url,
                'body': body.decode('utf-8'), 'observed_at': stamp()}


def project(channel, response):
    body = response['body']
    issues = []
    if response['status'] != 200:
        issues.append('http_status:' + str(response['status']))
    for value in channel.get('required', []):
        if value not in body:
            issues.append('missing:' + value)
    for value in channel.get('stale', []):
        if value.casefold() in body.casefold():
            issues.append('stale_copy:' + value)
    facts = {'final_url': response['url']}
    kind = channel.get('kind', 'text')
    if kind in ('routes', 'profiles'):
        data = json.loads(body)
        rows = data[kind]
        if not isinstance(rows, list):
            raise ValueError('Catalog inventory is not a list')
        inventory = {}
        fields = ('endpoint', 'mcp_endpoint', 'price_minor', 'description') if kind == 'routes' else (
            'endpoint', 'name', 'description', 'capabilities', 'version', 'status',
            'operator_entity_verified', 'expires_at')
        for row in rows:
            key = row['agent'] + '/' + row['tool'] if kind == 'routes' else row['agent_id']
            if not isinstance(key, str) or not key or key in inventory:
                raise ValueError('Invalid or duplicate inventory identifier')
            inventory[key] = {field: row.get(field) for field in fields}
        facts['inventory'] = inventory
    elif kind == 'registry':
        data = json.loads(body)
        if data.get('metadata', {}).get('nextCursor'):
            raise ValueError('Registry response incomplete; narrow query or add pagination')
        latest = [row['server'] for row in data['servers'] if
                  row.get('_meta', {}).get('io.modelcontextprotocol.registry/official', {}).get('isLatest')]
        if len(latest) != 1:
            raise ValueError('Expected exactly one latest Registry entry')
        facts['version'] = latest[0]['version']
        facts['remotes'] = latest[0].get('remotes', [])
        if facts['version'] != channel['version']:
            issues.append('registry_version_drift')
        if channel['endpoint'] not in [r.get('url') for r in facts['remotes']]:
            issues.append('registry_endpoint_drift')
    return {'status': 'drift' if issues else 'ok', 'issues': sorted(issues), 'facts': facts,
            'checked_at': response['observed_at'], 'body_sha256': hashlib.sha256(body.encode()).hexdigest()}


def check(channel):
    try:
        return project(channel, fetch(channel['url']))
    except Exception as exc:
        return {'status': 'unavailable', 'issues': ['source_unavailable'],
                'error': type(exc).__name__ + ': ' + str(exc), 'checked_at': stamp()}


def reconcile(previous, observed):
    """Failures preserve last good facts; noise in HTML never makes a change alert."""
    row = {**previous, **observed}
    changes = []
    if observed['status'] != 'unavailable':
        old = previous.get('facts', {}).get('inventory')
        new = observed.get('facts', {}).get('inventory')
        if old is not None and new is not None:
            for key in sorted(set(old) | set(new)):
                if old.get(key) != new.get(key):
                    changes.append({'id': key, 'change': 'added' if key not in old else
                                    'removed' if key not in new else 'changed'})
        row['last_successful_check'] = observed['checked_at']
        row.pop('error', None)
    if changes:
        row['last_inventory_changes'] = changes
        row['last_inventory_change_at'] = observed['checked_at']
    signal = {k: row.get(k) for k in ('status', 'issues', 'facts')}
    previous_signal = {k: previous.get(k) for k in ('status', 'issues', 'facts')}
    changed = signal != previous_signal
    event = None
    if changed and (previous or row['status'] != 'ok'):
        event = {'status': row['status'], 'issues': row['issues'], 'inventory_changes': changes}
    row['last_changed_at'] = observed['checked_at'] if changed else previous.get('last_changed_at')
    return row, event


def probe(script, args=()):
    try:
        result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *args],
                                capture_output=True, text=True, timeout=65, cwd=ROOT)
        data = json.loads(result.stdout)
        if result.returncode:
            return {'status': 'unavailable', 'detail': data}
        return {'status': 'ok', 'result': data}
    except Exception as exc:
        return {'status': 'unavailable', 'detail': type(exc).__name__ + ': ' + str(exc)}


def sales_actions(ledger, today):
    actions = []
    next_steps = {
        'QUALIFIED': 'Confirm buyer outcome, systems, budget and acceptance criteria; prepare bounded scope',
        'SCOPE_ACCEPTED': 'Provide existing verified funding instructions; work waits for independent funding verification',
        'FUNDING_PENDING': 'Reconcile exact independent funding receipt; do not infer funding from buyer or seller assertion',
        'FUNDED': 'Verify funding and access receipts, then execute agreed scope and acceptance tests',
        'DELIVERED': 'Obtain buyer acceptance of the exact delivered result; preserve delivery evidence',
        'ACCEPTED': 'Ask buyer what was useful and record their own response',
        'USEFUL': 'Qualify a real changed-input repeat or separately scoped Watch; no automatic enrollment',
        'REPEAT_REQUESTED': 'Confirm new scope and buyer budget; independently verify new payment before execution',
        'WATCH_ACTIVE': 'Reconcile active subscription and last delivered value using existing retention contract',
    }
    for offer in ledger.get('offers', []):
        if offer.get('suppress_email') or offer.get('state') in ('BOUNCED', 'DECLINED', 'OPTED_OUT'):
            continue
        if offer.get('state') == 'SENT':
            review_date = offer.get('next_review_on')
            actions.append({'id': 'buyer:' + offer['gmail_id'], 'priority': 2,
                            'action': 'Check authenticated inbox for reply/bounce/opt-out; qualify only a real reply',
                            'company': offer['company'], 'evidence': offer['gmail_id'],
                            'followup_not_before': review_date,
                            'followup_due_for_review': bool(review_date and today >= review_date),
                            'send_authorized_by_runner': False})
        elif offer.get('state') in next_steps:
            actions.append({'id': 'buyer:' + offer.get('id', offer.get('gmail_id', offer['company'])),
                            'priority': 0, 'action': next_steps[offer['state']],
                            'company': offer['company'], 'reported_stage': offer['state'],
                            'evidence': offer.get('evidence', []),
                            'stage_is_independent_revenue_evidence': False,
                            'send_authorized_by_runner': False})
    return actions


def execute(config, output, run_origin='manual'):
    now = stamp()
    state = read_json(output / 'state.json', {'channels': {}})
    ledger = dict(state['channels'])
    events, actions = [], []
    schedule = schedule_status(state, now, config.get('first_scheduled_due_at', now))
    if schedule['alert']:
        actions.append({'id': 'growth-schedule', 'priority': 1,
                        'action': ('Inspect the incomplete scheduled audit and its failed sources; manual recovery does not rewrite scheduled success'
                                   if schedule['status'] == 'attempted_incomplete' else
                                   'Investigate missing scheduled execution; manual refresh does not satisfy the schedule'),
                        'evidence': schedule})
    due = []
    for channel in config['channels']:
        last = ledger.get(channel['id'], {}).get('last_successful_check')
        if channel.get('weekly') and last and (
                datetime.fromisoformat(now).isocalendar()[:2] ==
                datetime.fromisoformat(last).isocalendar()[:2]):
            continue
        due.append(channel)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        observations = list(pool.map(check, due))
    for channel, observation in zip(due, observations):
        row, event = reconcile(ledger.get(channel['id'], {}), observation)
        row['source_url'] = channel['url']
        row['repair'] = channel.get('repair', 'Review against approved product contract')
        ledger[channel['id']] = row
        if event:
            events.append({'channel': channel['id'], **event})
    for key, row in ledger.items():
        if row.get('last_inventory_changes'):
            actions.append({'id': 'inventory:' + key, 'priority': 2,
                            'action': 'Review detected capability changes against approved manifests before distribution',
                            'changes': row['last_inventory_changes'],
                            'evidence': row['last_inventory_change_at']})
        if row['status'] != 'ok':
            actions.append({'id': key, 'priority': 1 if row['status'] == 'unavailable' else 3,
                            'action': row.get('repair'), 'issues': row['issues'],
                            'evidence': row.get('source_url')})
    # Watchdog precedes commercial snapshot; Nightkeeper owns alert-state mutation.
    watchdog = probe('fleet_nightkeeper_watchdog.py', ['check'])
    if watchdog['status'] != 'ok' or watchdog.get('result', {}).get('alert'):
        actions.append({'id': 'watchdog', 'priority': 1,
                        'action': 'Investigate missing or failed Nightkeeper execution; preserve watchdog evidence'})
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        pending = {
            'commercial': pool.submit(probe, 'commercial_truth_snapshot.py'),
            'bazaar': pool.submit(probe, 'bazaar_discoverability_snapshot.py',
                                  ['--query', 'viridis', '--query', 'MCP agent security preflight manifest policy']),
            'adoption': pool.submit(probe, 'viridis_adoption_client.py',
                                    ['Check an MCP manifest and tool policy']),
        }
    probes = {key: future.result() for key, future in pending.items()}
    if config.get('agent_search_audit'):
        search = probe('agent_search_audit.py')
        probes['agent_search'] = search
        result = search.get('result', {})
        atomic_json(output / 'AGENT_SEARCH.json', search)
        if search['status'] != 'ok' or result.get('status') != 'ok':
            actions.append({'id':'agent-search', 'priority':1,
                            'action':'Resolve intent, contract or external indexing gaps in AGENT_SEARCH.json; never self-pay to improve rank',
                            'evidence':'probes.agent_search'})
    for key, result in probes.items():
        if result['status'] != 'ok':
            actions.append({'id': 'probe:' + key, 'priority': 1,
                            'action': 'Restore evidence source; do not infer zero or healthy state'})
    bazaar = probes['bazaar'].get('result', {})
    if bazaar.get('classification') == 'SEMANTIC_DISCOVERABILITY_DEGRADED':
        actions.append({'id': 'bazaar-visibility', 'priority': 3,
                        'action': 'Review existing platform support and genuine buyer onboarding; no synthetic settlement',
                        'evidence': 'probes.bazaar'})
    probe_status = {key: result['status'] for key, result in probes.items()}
    probe_status['bazaar_visibility'] = bazaar.get('classification', 'unavailable')
    if config.get('agent_search_audit'):
        result = probes.get('agent_search', {}).get('result', {})
        probe_status['agent_search_quality'] = result.get('decision_sha256', 'unavailable')
    for key, value in probe_status.items():
        prior = state.get('probe_status', {}).get(key)
        if prior != value and (prior is not None or value != 'ok'):
            events.append({'channel': 'probe:' + key, 'status': value})
    commercial = probes['commercial'].get('result', {})
    if commercial:
        actions.append({'id': 'commercial-next', 'priority': 0,
                        'action': commercial.get('next_move'), 'evidence': 'probes.commercial'})
    sales_path = ROOT / config['sales_ledger']
    sales = read_json(sales_path, {})
    if not sales_path.exists():
        actions.append({'id': 'sales-source', 'priority': 1,
                        'action': 'Restore sales ledger; pipeline is unavailable, not empty'})
    actions.extend(sales_actions(sales, now[:10]))
    for gap in config.get('manual_checks', []):
        actions.append({'id': gap['id'], 'priority': 4, 'action': gap['action'],
                        'status': 'requires_authenticated_or_platform_review'})
    old_truth = state.get('commercial_truth')
    raw_truth = commercial.get('commercial_truth')
    # Ignore page views and free-call churn in material commercial events.
    keys = ('external_x402_revenue_atomic_usdc', 'distinct_external_x402_payers',
            'repeat_external_x402_purchases', 'external_x402_paid_results_delivered_exact',
            'external_x402_paid_results_receipted_exact', 'external_x402_paid_results_failed',
            'external_x402_paid_results_unknown', 'market_independently_useful_paid_deliveries',
            'market_would_buy_again_count', 'active_subscriptions', 'mrr_minor')
    truth = {key: raw_truth.get(key) for key in keys} if raw_truth is not None else None
    if old_truth is not None:
        old_truth = {key: old_truth.get(key) for key in keys}
    if truth is not None and old_truth is not None and truth != old_truth:
        events.append({'channel': 'commercial', 'status': 'changed',
                       'note': 'Inspect cash, attribution and delivery fields separately; not all changes are revenue'})
    compounding = None
    if config.get('compounding'):
        try:
            compounding = compounding_controller.run(commercial, ROOT, config['compounding'])
        except (ValueError, OSError, KeyError) as exc:
            compounding = {'status': 'HOLD', 'actions': [{'id': 'compound:configuration',
                'priority': 0, 'action': 'Restore compounding inputs: ' + str(exc)}]}
        actions.extend(compounding['actions'])
        prior = state.get('compounding_decision_sha256')
        if prior and prior != compounding.get('decision_sha256'):
            events.append({'channel': 'compounding', 'status': 'changed',
                           'note': 'Inspect evidence and proposals; no money moved'})
        atomic_json(output / 'COMPOUNDING.json', compounding)
    receipts = read_json(output / 'work-receipts.json', [])
    actions, reviewed = apply_receipts(actions, receipts, now, ROOT)
    run_id = now.replace(':', '').replace('.', '')
    report = {'run_id': run_id, 'checked_at': now, 'channels': ledger, 'events': events,
              'run_origin': run_origin, 'prior_schedule_status': schedule, 'reviewed_actions': reviewed,
              'probes': probes, 'watchdog': watchdog, 'compounding': compounding,
              'actions': sorted(actions, key=lambda item: (item['priority'], item['id'])),
              'boundaries': {'messages_sent': 0, 'payments_attempted': 0,
                             'listings_published': 0, 'network_profiles_are_customers': False},
              'status': 'attention' if actions else 'ok'}
    atomic_json(output / (run_id + '.json'), report)
    atomic_json(output / 'latest.json', report)
    atomic_json(output / 'state.json', {'channels': ledger, 'last_run': now,
                'last_scheduled_attempt': now if run_origin == 'scheduled' else state.get('last_scheduled_attempt'),
                'last_scheduled_run': now if run_origin == 'scheduled' and
                    all(p['status'] == 'ok' for p in probes.values()) and
                    all(c['status'] != 'unavailable' for c in ledger.values()) else state.get('last_scheduled_run'),
                'probe_status': probe_status,
                'commercial_truth': truth if truth is not None else old_truth,
                'compounding_decision_sha256': compounding.get('decision_sha256') if compounding else None})
    lines = ['# Viridis flywheel work queue', '', 'Checked: ' + now, '',
             'This is an evidence and action queue. It does not send messages or move money.', '']
    for action in report['actions']:
        lines.append('- **' + action['id'] + '**: ' + str(action['action']))
    (output / 'NEXT_ACTIONS.md').write_text('\n'.join(lines) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/flywheel_channels.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/business/evidence/discovery-upkeep')
    parser.add_argument('--run-origin', choices=['manual', 'scheduled'], default='manual')
    parser.add_argument('--record-action', help='Record a bounded review of an eligible current action')
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--note')
    parser.add_argument('--review-hours', type=int, default=24)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / '.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status': 'already_running'}))
            return 2
        if args.record_action:
            if args.evidence is None or not args.note:
                parser.error('--record-action requires --evidence and --note')
            latest = read_json(args.output / 'latest.json', {})
            action = next(a for a in latest.get('actions', []) if a['id'] == args.record_action)
            receipt = receipt_for(action, args.evidence, ROOT, args.note, stamp(), args.review_hours)
            receipts = read_json(args.output / 'work-receipts.json', [])
            atomic_json(args.output / 'work-receipts.json', receipts + [receipt])
            print(json.dumps({'status': 'review_recorded', 'receipt': receipt}))
            return 0
        report = execute(read_json(args.config, {}), args.output, args.run_origin)
    print(json.dumps({'status': report['status'], 'channels': len(report['channels']),
                      'new_events': len(report['events']), 'actions': len(report['actions']),
                      'report': str(args.output / 'latest.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
