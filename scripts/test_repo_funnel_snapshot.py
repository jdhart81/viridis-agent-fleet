import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_funnel_snapshot import build


def fixture():
    w = {'eligible_payers': 1, 'repeat_payers': 1, 'pending_maturity': 0}
    return {'subscriptions': {'frontdoor_funnel': {'acquisition_source_views': {'github': 9}}},
        'payment_gate': {'x402': {'http_settlement_telemetry': {
        'total': {'distinct_external_payers': 2, 'external_paid_results_delivered': 3},
        'retention_cohorts': {'version': 'viridis-x402-retention-cohorts-v1', 'payer_count': 2,
        'by_acquisition_source': {'github': {'payer_count': 1, 'windows': {k: copy.deepcopy(w) for k in ('7d','14d','30d')}},
                                  'unknown': {'payer_count': 1}}}}}}}


class FunnelTests(unittest.TestCase):
    def test_no_false_delivery_attribution(self):
        s = build(fixture())
        self.assertEqual(s['github']['external_payers'], 1)
        self.assertIsNone(s['github']['paid_results_delivered'])
        self.assertIsNone(s['github']['service_selections'])
        self.assertEqual(s['github']['repeat_cohorts']['7d']['repeat_rate'], 1)
        self.assertEqual(s['historical_payers_unknown_source'], 1)

    def test_unavailable_is_not_zero(self):
        s = build({})['github']
        self.assertIsNone(s['external_payers'])
        self.assertIsNone(s['landing_page_views'])
        self.assertIsNone(s['repeat_cohorts']['7d']['repeat_payers'])

    def test_inconsistent_counts_fail_closed(self):
        h = fixture(); h['payment_gate']['x402']['http_settlement_telemetry']['total']['distinct_external_payers'] = 4
        self.assertIsNone(build(h)['github']['external_payers'])

    def test_immature_cohort_has_no_rate(self):
        h = fixture();w=h['payment_gate']['x402']['http_settlement_telemetry']['retention_cohorts']['by_acquisition_source']['github']['windows']['7d']
        w.update(eligible_payers=0, repeat_payers=0, pending_maturity=1)
        self.assertIsNone(build(h)['github']['repeat_cohorts']['7d']['repeat_rate'])

    def test_absent_github_in_complete_cohort_is_zero(self):
        h = fixture();r=h['payment_gate']['x402']['http_settlement_telemetry']['retention_cohorts']
        del r['by_acquisition_source']['github'];r['by_acquisition_source']['unknown']['payer_count']=2
        g=build(h)['github'];self.assertEqual(g['external_payers'],0)
        self.assertIsNone(g['repeat_cohorts']['7d']['repeat_rate'])

    def test_no_raw_identity_output(self):
        h=fixture();h['secret_wallet']='never-export'
        self.assertNotIn('never-export',str(build(h)))


if __name__ == '__main__': unittest.main()
