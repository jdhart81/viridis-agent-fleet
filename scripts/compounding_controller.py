#!/usr/bin/env python3
"""Deterministic financial/mission decisions. Local evidence only; never pays or sends."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

COSTS = {'compute', 'payment', 'support', 'refunds', 'hosting', 'other'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError('Amounts and counters must be nonnegative integers')
    return value


def fresh(value, now, hours):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or not 0 <= (now - parsed).total_seconds() <= hours * 3600:
        raise ValueError('Evidence is stale, future-dated or lacks a timezone')


def evidence(ref, root):
    """Integrity of a locally reconciled source, NOT independent truth verification."""
    path = (root / ref['path']).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Evidence must be a file inside the workspace')
    if path.stat().st_size > 10_000_000:
        raise ValueError('Evidence exceeds size limit')
    if hashlib.sha256(path.read_bytes()).hexdigest() != ref['sha256']:
        raise ValueError('Evidence digest mismatch')


def evaluate(snapshot, ledger, policy, root, now=None):
    now = now or datetime.now(timezone.utc)
    report = {'version': 1, 'checked_at': now.isoformat(), 'status': 'HOLD',
              'financial': {'net_surplus_atomic_usdc': None}, 'repeat_quotes': [],
              'mission': {'proposal_atomic_usdc': 0, 'impact_claimed': False},
              'expansion_allowed': False, 'actions': [],
              'boundaries': {'payments_attempted': 0, 'messages_sent': 0,
                             'model_calls': 0, 'independent_evidence_verification': False,
                             'allocation_is_transfer_authority': False}}
    def action(key, message):
        report['actions'].append({'id': 'compound:' + key, 'priority': 0, 'action': message})
    try:
        for key in ('snapshot_max_age_hours', 'ledger_max_age_hours', 'request_max_age_hours',
                    'minimum_useful_buyers', 'minimum_repeat_buyers'):
            if integer(policy[key]) == 0:
                raise ValueError('Freshness windows and expansion thresholds must be positive')
        fresh(snapshot['generated_at'], now, policy['snapshot_max_age_hours'])
        truth = snapshot['commercial_truth']
        cash = integer(truth['external_x402_revenue_atomic_usdc'])
        count = integer(truth['external_x402_settlements'])
        delivered = integer(truth['external_x402_paid_results_delivered_exact'])
        unknown = integer(truth['external_x402_paid_results_unknown'])
        report['financial'].update(external_settled_atomic_usdc=cash, external_settlements=count)
        if unknown:
            action('delivery', f'Reconcile {unknown} historical paid outcomes; preserve unknown delivery status until evidence resolves it.')
        if not delivered:
            action('buyer', 'Complete one real buyer delivery and obtain attributable usefulness feedback before expanding the catalog.')
        if ledger.get('status') != 'reconciled':
            raise ValueError('Cost and settlement ledger is not reconciled; profit is unavailable')
        fresh(ledger['reconciled_at'], now, policy['ledger_max_age_hours'])
        evidence(ledger['reconciliation_evidence'], root)
        transactions = ledger['transactions']
        ids, payers, total, variable = set(), set(), 0, 0
        useful, repeat_payers, routes = set(), set(), {}
        by_id = {}
        for row in transactions:
            key = row['settlement_id']
            if not isinstance(key, str) or not key or key in ids or row['origin'] != 'external':
                raise ValueError('Duplicate, invalid or non-external settlement')
            ids.add(key); by_id[key] = row
            payer = row['payer_id']
            if not isinstance(payer, str) or not payer:
                raise ValueError('Missing pseudonymous payer ID')
            payers.add(payer)
            evidence(row['evidence'], root)
            amount = integer(row['amount_atomic_usdc']); total += amount
            if set(row['costs_atomic_usdc']) != COSTS:
                raise ValueError('Every cost category must be explicitly reconciled, including zero costs')
            cost = sum(integer(x) for x in row['costs_atomic_usdc'].values()); variable += cost
            if row['delivery'] not in ('delivered', 'failed', 'unknown'):
                raise ValueError('Invalid delivery state')
            if type(row.get('useful')) is not bool:
                raise ValueError('Usefulness must be explicitly true or false')
            if row.get('useful'):
                if row['delivery'] != 'delivered':
                    raise ValueError('Useful feedback requires delivery')
                evidence(row['acceptance_evidence'], root)
                if payer in useful: repeat_payers.add(payer)
                useful.add(payer)
            route = routes.setdefault(row['route'], {'revenue_atomic_usdc': 0, 'cost_atomic_usdc': 0})
            route['revenue_atomic_usdc'] += amount; route['cost_atomic_usdc'] += cost
        if total != cash or len(ids) != count or len(payers) != truth['distinct_external_x402_payers']:
            raise ValueError('Ledger does not reconcile to external settlement totals and payers')
        if sum(r['delivery'] == 'delivered' for r in transactions) != delivered:
            raise ValueError('Ledger delivery count disagrees with the commercial source')
        if sum(r['delivery'] == 'unknown' for r in transactions) != unknown:
            raise ValueError('Ledger unknown outcomes disagree with the commercial source')
        shared = integer(ledger['shared_cost_atomic_usdc'])
        treasury = ledger['treasury']; evidence(treasury['evidence'], root)
        available = integer(treasury['available_atomic_usdc'])
        liabilities = integer(treasury['liabilities_atomic_usdc'])
        reserve = integer(policy['minimum_reserve_atomic_usdc'])
        transfers, allocated = set(), 0
        for row in ledger['mission_transfers']:
            if not row['id'] or row['id'] in transfers:
                raise ValueError('Duplicate mission transfer')
            transfers.add(row['id']); evidence(row['evidence'], root)
            allocated += integer(row['amount_atomic_usdc'])
        net = total - variable - shared
        report['financial'].update(net_surplus_atomic_usdc=net, routes=routes,
                                  shared_cost_atomic_usdc=shared, reconciled=True)
        bps = integer(policy['mission_proposal_bps'])
        if bps > 10000: raise ValueError('Mission proposal exceeds 100 percent')
        candidate = min(max(0, net * bps // 10000 - allocated), max(0, available - liabilities - reserve))
        # Unknown outcomes retain a hold even when costs were supplied.
        if unknown: candidate = 0
        report['mission'].update(proposal_atomic_usdc=candidate, already_transferred_atomic_usdc=allocated,
                                 proposed_share_bps=bps, reserve_atomic_usdc=reserve)
        outcomes, outcome_ids = [], set()
        for row in ledger.get('mission_outcomes', []):
            if row['id'] in outcome_ids or row['transfer_id'] not in transfers:
                raise ValueError('Duplicate mission outcome or missing funding reference')
            outcome_ids.add(row['id']); evidence(row['evidence'], root)
            if not all(isinstance(row[k], str) and row[k] for k in ('id', 'metric', 'unit', 'observed_value', 'baseline_value')):
                raise ValueError('Mission observations require metric, unit, baseline and observed value')
            outcomes.append({k: row[k] for k in ('id', 'transfer_id', 'metric', 'unit', 'baseline_value', 'observed_value', 'evidence')})
        report['mission']['reported_outcomes'] = outcomes
        report['mission']['outcome_boundary'] = 'Linked project observations; no automatic causal, independent-verification or certification claim'
        if candidate:
            report['mission']['proposal_id'] = digest({'settlements': sorted(ids), 'amount': candidate,
                                                       'transfers': sorted(transfers), 'policy': policy})
            action('mission', 'Review the surplus allocation proposal and select an evidenced mission project; no transfer is authorized by this report.')
        request_ids = set()
        for request in ledger['repeat_requests']:
            if not request['id'] or request['id'] in request_ids:
                raise ValueError('Duplicate repeat request')
            request_ids.add(request['id'])
            previous = by_id[request['settlement_id']]
            evidence(request['buyer_request_evidence'], root)
            fresh(request['requested_at'], now, policy['request_max_age_hours'])
            fresh(request['authorization_recorded_at'], now, policy['request_max_age_hours'])
            if datetime.fromisoformat(request['expires_at'].replace('Z', '+00:00')) <= now:
                continue
            if request['payer_id'] != previous['payer_id'] or request['route'] != previous['route']:
                raise ValueError('Repeat request does not match the prior buyer and service')
            # A prior purchase never authorizes another one. This only prepares an unpaid quote.
            if type(request['quote_requested']) is not bool:
                raise ValueError('Quote request must be explicitly true or false')
            if not request['quote_requested'] or not previous.get('useful') or previous['delivery'] != 'delivered':
                continue
            for h in (request['input_sha256'], request['rules_sha256'], previous['input_sha256'], previous['rules_sha256']):
                if not isinstance(h, str) or len(h) != 64 or any(c not in '0123456789abcdef' for c in h):
                    raise ValueError('Invalid source or rules digest')
            if (request['input_sha256'], request['rules_sha256']) == (previous['input_sha256'], previous['rules_sha256']):
                continue
            if request['route'] not in policy['repeat_routes'] or integer(request['max_price_atomic_usdc']) == 0:
                continue
            if unknown or net <= 0:
                continue
            route = routes[request['route']]
            if route['revenue_atomic_usdc'] <= route['cost_atomic_usdc']:
                continue
            report['repeat_quotes'].append({'id': digest(request), 'route': request['route'],
                'buyer_request_id': request['id'], 'maximum_atomic_usdc': request['max_price_atomic_usdc'],
                'next_action': 'obtain_fresh_unpaid_quote', 'payment_authorized': False})
        report['expansion_allowed'] = (not unknown and net > 0 and
            len(useful) >= policy['minimum_useful_buyers'] and len(repeat_payers) >= policy['minimum_repeat_buyers'])
        report['status'] = 'REVIEW_READY' if candidate or report['repeat_quotes'] else 'HOLD'
        if net <= 0: action('margin', 'Resolve negative or zero net surplus before funding expansion or mission allocations.')
        if not report['expansion_allowed']:
            action('retention', 'Earn useful outcomes from three independent buyers and real repeat use from two before expansion; these are management thresholds, not established traction.')
    except (KeyError, ValueError, TypeError, OSError, AttributeError) as exc:
        # Never retain partially computed spend proposals after any validation failure.
        report.update(status='HOLD', repeat_quotes=[], expansion_allowed=False)
        report['financial']['net_surplus_atomic_usdc'] = None
        report['financial']['reconciled'] = False
        report['mission']['proposal_atomic_usdc'] = 0
        report['mission'].pop('proposal_id', None)
        action('reconciliation', str(exc))
    report['decision_sha256'] = digest({k:v for k,v in report.items() if k != 'checked_at'})
    return report


def run(snapshot, root, settings):
    policy = json.loads((root / settings['policy']).read_text())
    ledger = json.loads((root / settings['ledger']).read_text())
    return evaluate(snapshot, ledger, policy, root)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--snapshot', type=Path, default=root/'docs/business/evidence/discovery-upkeep/latest.json')
    parser.add_argument('--ledger', type=Path, default=root/'config/compounding_ledger.json')
    parser.add_argument('--policy', type=Path, default=root/'config/compounding_policy.json')
    args = parser.parse_args()
    data = json.loads(args.snapshot.read_text())
    snapshot = data.get('probes', {}).get('commercial', {}).get('result', data)
    result = evaluate(snapshot, json.loads(args.ledger.read_text()), json.loads(args.policy.read_text()), root)
    print(json.dumps(result, indent=2, sort_keys=True))
