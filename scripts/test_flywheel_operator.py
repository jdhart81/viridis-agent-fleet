import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import flywheel_operator as op


def response(body):
    return {'status': 200, 'url': 'https://example.com', 'body': body,
            'observed_at': '2026-09-08T20:00:00+00:00'}


class FlywheelTests(unittest.TestCase):
    def test_failed_source_preserves_inventory_and_last_success(self):
        old = {'facts': {'inventory': {'a': {}}}, 'last_successful_check': 'yesterday'}
        row, event = op.reconcile(old, {'status': 'unavailable', 'issues': ['source_unavailable'],
                                     'checked_at': 'today'})
        self.assertEqual(row['facts'], old['facts'])
        self.assertEqual(row['last_successful_check'], 'yesterday')
        self.assertEqual(event['inventory_changes'], [])

    def test_baseline_not_fabricated_growth(self):
        row = op.project({'kind': 'profiles'}, response(json.dumps({'profiles': [{'agent_id': 'a'}]})))
        _, event = op.reconcile({}, row)
        self.assertIsNone(event)

    def test_detect_add_remove_and_change_without_fetching_profile(self):
        old = {'status': 'ok', 'issues': [], 'facts': {'inventory': {'a': {}, 'b': {}}}}
        now = {'status': 'ok', 'issues': [], 'facts': {'inventory': {'b': {'version': 2}, 'c': {}}},
               'checked_at': 'today'}
        _, event = op.reconcile(old, now)
        self.assertEqual([x['change'] for x in event['inventory_changes']], ['removed', 'changed', 'added'])

    def test_html_timestamp_noise_is_quiet(self):
        old, _ = op.reconcile({}, op.project({}, response('clock 12:00')))
        _, event = op.reconcile(old, op.project({}, response('clock 12:01')))
        self.assertIsNone(event)

    def test_duplicate_profile_ids_fail(self):
        with self.assertRaises(ValueError):
            op.project({'kind': 'profiles'}, response('{"profiles":[{"agent_id":"a"},{"agent_id":"a"}]}'))

    def test_missing_inventory_does_not_become_zero(self):
        with self.assertRaises(KeyError):
            op.project({'kind': 'routes'}, response('{}'))

    def test_registry_incomplete_response_not_success(self):
        with self.assertRaises(ValueError):
            op.project({'kind': 'registry'}, response('{"metadata":{"nextCursor":"more"},"servers":[]}'))

    def test_bounces_optouts_never_become_followups(self):
        rows = [{'state': s} for s in ['BOUNCED', 'OPTED_OUT', 'DECLINED']]
        rows.append({'state': 'SENT', 'suppress_email': True})
        self.assertEqual(op.sales_actions({'offers': rows}, '2026-09-12'), [])

    def test_sent_email_is_inbox_review_not_buyer_or_send(self):
        action = op.sales_actions({'offers': [{'state': 'SENT', 'gmail_id': 'x', 'company': 'Example',
                                              'next_review_on': '2026-09-11'}]}, '2026-09-08')[0]
        self.assertFalse(action['send_authorized_by_runner'])
        self.assertFalse(action['followup_due_for_review'])

    def test_reported_funding_is_a_verification_task_not_revenue(self):
        action = op.sales_actions({'offers': [{'state': 'FUNDED', 'id': 'buyer-1',
                                              'company': 'Example'}]}, '2026-09-08')[0]
        self.assertIn('Verify funding', action['action'])
        self.assertFalse(action['stage_is_independent_revenue_evidence'])

    def test_useful_delivery_leads_to_separately_authorized_repeat(self):
        action = op.sales_actions({'offers': [{'state': 'USEFUL', 'id': 'buyer-1',
                                              'company': 'Example'}]}, '2026-09-08')[0]
        self.assertIn('no automatic enrollment', action['action'])

    def test_corrupt_evidence_is_not_reset(self):
        with TemporaryDirectory() as folder:
            p = Path(folder) / 'state.json'
            p.write_text('{broken')
            with self.assertRaises(json.JSONDecodeError):
                op.read_json(p, {})

    def test_probe_failure_is_unavailable_not_empty_success(self):
        with patch.object(op.subprocess, 'run', side_effect=TimeoutError('timeout')):
            self.assertEqual(op.probe('unused.py')['status'], 'unavailable')

    def test_recovery_emits_event_once(self):
        failed = {'status': 'unavailable', 'issues': ['source_unavailable'], 'error': 'timeout'}
        recovered, event = op.reconcile(failed, op.project({}, response('ok')))
        self.assertEqual(event['status'], 'ok')
        self.assertNotIn('error', recovered)
        _, again = op.reconcile(recovered, op.project({}, response('ok')))
        self.assertIsNone(again)

    def test_full_runs_are_durable_quiet_and_keep_open_work(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'sales.json').write_text('{"offers":[]}')
            config = {'channels': [{'id': 'example', 'url': 'https://example.com',
                                    'required': ['new endpoint'], 'repair': 'Correct owned link'}],
                      'sales_ledger': 'sales.json'}
            def fake_probe(script, args=()):
                if script == 'commercial_truth_snapshot.py':
                    return {'status': 'ok', 'result': {'commercial_truth': {'mrr_minor': 0},
                            'next_move': {'action': 'establish_one_verified_paid_result_delivery'}}}
                return {'status': 'ok', 'result': {}}
            with patch.object(op, 'ROOT', root), patch.object(op, 'fetch', return_value=response('old endpoint')), \
                    patch.object(op, 'probe', side_effect=fake_probe):
                first = op.execute(config, root)
                second = op.execute(config, root)
            self.assertTrue(first['events'])
            self.assertEqual(second['events'], [])
            self.assertTrue(any(x['id'] == 'example' for x in second['actions']))
            self.assertEqual(second['boundaries']['payments_attempted'], 0)
            self.assertTrue((root / (first['run_id'] + '.json')).exists())
            self.assertTrue((root / (second['run_id'] + '.json')).exists())
            self.assertEqual(json.loads((root / 'latest.json').read_text())['run_id'], second['run_id'])


if __name__ == '__main__':
    unittest.main()
