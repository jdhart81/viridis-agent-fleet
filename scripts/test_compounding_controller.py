import copy
import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import compounding_controller as c
from flywheel_work_receipts import apply_receipts, fingerprint

NOW = datetime(2026, 9, 9, 15, tzinfo=timezone.utc)


class CompoundingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'receipt.txt').write_text('synthetic evidence, never a customer receipt')
        ref = {'path': 'receipt.txt', 'sha256': hashlib.sha256((self.root/'receipt.txt').read_bytes()).hexdigest()}
        self.policy = {'snapshot_max_age_hours': 1, 'ledger_max_age_hours': 24,
                       'request_max_age_hours': 168, 'minimum_reserve_atomic_usdc': 25_000_000,
                       'mission_proposal_bps': 1000, 'minimum_useful_buyers': 3,
                       'minimum_repeat_buyers': 2, 'repeat_routes': ['security-preflight/scan_source']}
        self.snapshot = {'generated_at': NOW.isoformat(), 'commercial_truth': {
            'external_x402_revenue_atomic_usdc': 100_000_000, 'external_x402_settlements': 1,
            'distinct_external_x402_payers': 1, 'external_x402_paid_results_delivered_exact': 1,
            'external_x402_paid_results_unknown': 0}}
        row = {'settlement_id': 'external-1', 'payer_id': 'buyer-1', 'origin': 'external',
               'amount_atomic_usdc': 100_000_000, 'costs_atomic_usdc': dict.fromkeys(c.COSTS, 0),
               'evidence': ref, 'delivery': 'delivered', 'useful': True, 'acceptance_evidence': ref,
               'route': 'security-preflight/scan_source', 'input_sha256': 'a'*64, 'rules_sha256': 'b'*64}
        row['costs_atomic_usdc']['compute'] = 10_000_000
        self.ledger = {'status': 'reconciled', 'reconciled_at': NOW.isoformat(),
                       'reconciliation_evidence': ref, 'transactions': [row],
                       'shared_cost_atomic_usdc': 10_000_000,
                       'treasury': {'available_atomic_usdc': 80_000_000, 'liabilities_atomic_usdc': 0, 'evidence': ref},
                       'mission_transfers': [], 'repeat_requests': []}
        self.request = {'id': 'request-1', 'settlement_id': 'external-1', 'payer_id': 'buyer-1',
                        'route': row['route'], 'input_sha256': 'c'*64, 'rules_sha256': 'b'*64,
                        'max_price_atomic_usdc': 1_000_000, 'quote_requested': True,
                        'requested_at': NOW.isoformat(), 'authorization_recorded_at': NOW.isoformat(),
                        'expires_at': '2026-09-10T15:00:00+00:00', 'buyer_request_evidence': ref}

    def run_gate(self):
        return c.evaluate(self.snapshot, self.ledger, self.policy, self.root, NOW)

    def test_costs_and_reserve_bound_nonexecuting_proposal(self):
        r = self.run_gate()
        self.assertEqual(r['financial']['net_surplus_atomic_usdc'], 80_000_000)
        self.assertEqual(r['mission']['proposal_atomic_usdc'], 8_000_000)
        self.assertFalse(r['expansion_allowed'])
        self.assertFalse(r['boundaries']['allocation_is_transfer_authority'])
        self.ledger['treasury']['available_atomic_usdc'] = 26_000_000
        self.assertEqual(self.run_gate()['mission']['proposal_atomic_usdc'], 1_000_000)

    def test_missing_costs_never_become_zero(self):
        del self.ledger['transactions'][0]['costs_atomic_usdc']['support']
        r = self.run_gate()
        self.assertIsNone(r['financial']['net_surplus_atomic_usdc'])
        self.assertEqual(r['mission']['proposal_atomic_usdc'], 0)

    def test_stale_and_future_snapshots_hold(self):
        for stamp in ['2026-09-08T15:00:00+00:00', '2026-09-10T15:00:00+00:00']:
            self.snapshot['generated_at'] = stamp
            self.assertEqual(self.run_gate()['status'], 'HOLD')

    def test_duplicate_or_self_settlement_cannot_fund_mission(self):
        self.ledger['transactions'].append(copy.deepcopy(self.ledger['transactions'][0]))
        self.assertEqual(self.run_gate()['mission']['proposal_atomic_usdc'], 0)
        self.ledger['transactions'].pop(); self.ledger['transactions'][0]['origin'] = 'self'
        self.assertEqual(self.run_gate()['mission']['proposal_atomic_usdc'], 0)

    def test_aggregate_mismatch_holds(self):
        self.snapshot['commercial_truth']['external_x402_revenue_atomic_usdc'] += 1
        self.assertIsNone(self.run_gate()['financial']['net_surplus_atomic_usdc'])

    def test_changed_input_prepares_quote_only_and_same_input_does_nothing(self):
        self.ledger['repeat_requests'] = [self.request]
        r = self.run_gate(); self.assertEqual(len(r['repeat_quotes']), 1)
        self.assertFalse(r['repeat_quotes'][0]['payment_authorized'])
        self.request['input_sha256'] = 'a'*64
        self.assertEqual(self.run_gate()['repeat_quotes'], [])

    def test_repeat_requires_current_matching_buyer_request(self):
        self.ledger['repeat_requests'] = [self.request]
        for field, bad in [('payer_id','other'), ('expires_at','2026-09-08T15:00:00+00:00'), ('quote_requested',False)]:
            old = self.request[field]; self.request[field] = bad
            self.assertEqual(self.run_gate()['repeat_quotes'], [])
            self.request[field] = old

    def test_transfer_deduction_prevents_proposing_same_allocation_twice(self):
        self.ledger['mission_transfers'] = [{'id':'transfer-1','amount_atomic_usdc':8_000_000,
                                            'evidence':self.ledger['reconciliation_evidence']}]
        self.assertEqual(self.run_gate()['mission']['proposal_atomic_usdc'], 0)
        self.assertFalse(self.run_gate()['mission']['impact_claimed'])

    def test_tampering_and_path_escape_fail_closed(self):
        self.ledger['reconciliation_evidence']['path'] = '../outside.txt'
        self.assertEqual(self.run_gate()['status'], 'HOLD')
        self.ledger['reconciliation_evidence']['path'] = 'receipt.txt'
        (self.root/'receipt.txt').write_text('changed')
        self.assertEqual(self.run_gate()['status'], 'HOLD')

    def test_invalid_repeat_rolls_back_already_computed_mission_proposal(self):
        self.ledger['repeat_requests'] = [self.request, self.request]
        r = self.run_gate()
        self.assertEqual(r['mission']['proposal_atomic_usdc'], 0)
        self.assertEqual(r['repeat_quotes'], [])

    def test_unchanged_evidence_produces_stable_decision(self):
        self.assertEqual(self.run_gate()['decision_sha256'], self.run_gate()['decision_sha256'])

    def test_expansion_requires_multiple_useful_buyers_and_real_repeats(self):
        rows = []
        for i, payer in enumerate(['one', 'two', 'three', 'one', 'two']):
            row = copy.deepcopy(self.ledger['transactions'][0])
            row.update(settlement_id=str(i), payer_id=payer); rows.append(row)
        self.ledger['transactions'] = rows
        self.snapshot['commercial_truth'].update(external_x402_revenue_atomic_usdc=500_000_000,
            external_x402_settlements=5, distinct_external_x402_payers=3,
            external_x402_paid_results_delivered_exact=5)
        self.assertTrue(self.run_gate()['expansion_allowed'])
        rows[-1]['useful'] = False
        self.assertFalse(self.run_gate()['expansion_allowed'])

    def test_mission_observations_require_referenced_funding_and_do_not_certify(self):
        self.ledger['mission_outcomes'] = [{'id':'outcome-1','transfer_id':'missing',
            'metric':'sampled_sites','unit':'sites','baseline_value':'0','observed_value':'2',
            'evidence':self.ledger['reconciliation_evidence']}]
        self.assertEqual(self.run_gate()['status'], 'HOLD')
        self.ledger['mission_transfers'] = [{'id':'missing','amount_atomic_usdc':8_000_000,
                                           'evidence':self.ledger['reconciliation_evidence']}]
        r = self.run_gate()
        self.assertEqual(len(r['mission']['reported_outcomes']), 1)
        self.assertFalse(r['mission']['impact_claimed'])

    def test_operator_review_cannot_hide_compounding_hold(self):
        action = {'id':'compound:reconciliation','priority':0,'action':'reconcile'}
        receipt = {'action_id':action['id'], 'fingerprint':fingerprint(action)}
        opened, reviewed = apply_receipts([action],[receipt],NOW.isoformat(),self.root)
        self.assertEqual(opened,[action]); self.assertEqual(reviewed,[])


if __name__ == '__main__': unittest.main()
