"""Local, expiring work receipts; never monetary or buyer acceptance evidence."""
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path


def fingerprint(action):
    return hashlib.sha256(json.dumps(action, sort_keys=True).encode()).hexdigest()


def receipt_for(action, evidence, root, note, now, hours=24):
    if not (action['id'].startswith(('buyer:', 'inventory:')) or
            action.get('status') == 'requires_authenticated_or_platform_review'):
        raise ValueError('Live drift and commercial gates close only through fresh source verification')
    if not note.strip() or not 1 <= hours <= 168:
        raise ValueError('A substantive note and 1–168 hour review interval are required')
    path = Path(evidence).resolve()
    path.relative_to(root.resolve())
    if not path.is_file() or not path.stat().st_size:
        raise ValueError('Evidence must be a nonempty existing workspace file')
    return {'action_id': action['id'], 'fingerprint': fingerprint(action),
            'recorded_at': now, 'review_after': (datetime.fromisoformat(now) +
                timedelta(hours=hours)).isoformat(),
            'evidence': str(path.relative_to(root.resolve())),
            'evidence_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'note': note, 'classification': 'operator_review_not_buyer_or_revenue_proof'}


def apply_receipts(actions, receipts, now, root):
    open_actions, reviewed = [], []
    latest = {r['action_id']: r for r in receipts}
    for action in actions:
        receipt = latest.get(action['id'])
        valid = False
        eligible = (action['id'].startswith(('buyer:', 'inventory:')) or
                    action.get('status') == 'requires_authenticated_or_platform_review')
        if eligible and receipt and receipt['fingerprint'] == fingerprint(action):
            path = (root / receipt['evidence']).resolve()
            try:
                path.relative_to(root.resolve())
                valid = (datetime.fromisoformat(receipt['recorded_at']) <= datetime.fromisoformat(now) <
                         datetime.fromisoformat(receipt['review_after']) and path.is_file() and
                         hashlib.sha256(path.read_bytes()).hexdigest() == receipt['evidence_sha256'])
            except ValueError:
                pass
        if valid:
            reviewed.append({'action': action, 'receipt': receipt})
        else:
            open_actions.append(action)
    return open_actions, reviewed


def schedule_status(state, now, first_due):
    last = state.get('last_scheduled_run')
    attempt = state.get('last_scheduled_attempt')
    due = datetime.fromisoformat(last) + timedelta(hours=26) if last else datetime.fromisoformat(first_due)
    late = datetime.fromisoformat(now) > due
    return {'status': ('attempted_incomplete' if attempt and (not last or attempt > last) else
                      ('missed' if last else 'never_succeeded')) if late else
            ('within_interval' if last else 'not_due'),
            'alert': late, 'last_scheduled_run': last, 'last_scheduled_attempt': attempt, 'due_at': due.isoformat(),
            'manual_runs_satisfy_schedule': False}
