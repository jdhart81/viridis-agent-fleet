import copy
import json
import tempfile
import unittest
from pathlib import Path

from validate import load, validate, verdict, canonical_bytes, content_hash


class Tests(unittest.TestCase):
    def setUp(self):
        self.f = load(Path(__file__).with_name('fixture.json'))
        self.c = self.f['cases'][2]

    def rejected(self):
        with self.assertRaises(ValueError):
            verdict(self.f, self.c)

    def test_expected_verdicts(self):
        self.assertEqual(validate(self.f), {
            'complete_history': 'BLOCKED',
            'truncated_history': 'INSUFFICIENT_COVERAGE',
            'retry_after_fix': 'RECOVERED_WITH_PRIOR_BLOCKER',
        })

    def test_unsorted_rows_rejected(self):
        self.c['returned_events'][0:2] = list(reversed(self.c['returned_events'][0:2]))
        self.rejected()

    def test_duplicate_sequence_rejected(self):
        self.c['returned_events'].insert(1, copy.deepcopy(self.c['returned_events'][0]))
        self.rejected()

    def test_duplicate_id_rejected(self):
        self.c['returned_events'][1]['event_id'] = 'e1'
        self.rejected()

    def test_interior_gap_is_insufficient_even_with_matching_endpoints(self):
        self.c['returned_events'].pop(1)
        self.assertEqual(verdict(self.f, self.c), 'INSUFFICIENT_COVERAGE')

    def test_reported_bounds_cannot_hide_truncation(self):
        self.c = self.f['cases'][1]
        self.c['returned_range'] = [1, 6]
        self.rejected()

    def test_empty_readback_is_insufficient(self):
        self.c.update(returned_events=[], returned_range=None, run_ids=[])
        self.assertEqual(verdict(self.f, self.c), 'INSUFFICIENT_COVERAGE')

    def test_changed_blocker_content_rejected(self):
        self.c['returned_events'][1]['error_class'] = 'OTHER'
        self.rejected()

    def test_changed_blocker_timestamp_rejected(self):
        self.c['returned_events'][1]['server_timestamp'] = '2000-01-01T00:00:09Z'
        self.rejected()

    def test_same_run_retry_rejected(self):
        for rows in (self.f['stored_events'], self.c['returned_events']):
            for e in rows[3:]:
                e['run_id'] = 'synthetic-run-a'
        self.c['run_ids'] = ['synthetic-run-a']
        self.rejected()

    def test_case_run_identity_mismatch_rejected(self):
        self.c['run_ids'] = ['synthetic-run-a']
        self.rejected()

    def test_first_blocker_declaration_rewrite_rejected(self):
        self.f['first_blocker_event'] = 'e6'
        self.rejected()

    def test_timestamp_order_does_not_establish_sequence_coverage(self):
        for rows in (self.f['stored_events'], self.c['returned_events']):
            for e in rows:
                e['server_timestamp'] = '2000-01-01T00:00:00Z'
        self.assertEqual(verdict(self.f, self.c), 'RECOVERED_WITH_PRIOR_BLOCKER')
        self.c['returned_events'].pop(1)
        self.assertEqual(verdict(self.f, self.c), 'INSUFFICIENT_COVERAGE')

    def test_anchor_alone_does_not_upgrade_truncation(self):
        self.assertEqual(verdict(self.f, self.f['cases'][1]), 'INSUFFICIENT_COVERAGE')

    def test_extra_visible_row_outside_required_interval_is_insufficient(self):
        self.c = self.f['cases'][0]
        self.c['returned_events'].append(copy.deepcopy(self.f['stored_events'][2]))
        self.c['returned_range'] = [1, 3]
        self.assertEqual(verdict(self.f, self.c), 'INSUFFICIENT_COVERAGE')

    def test_hash_ignores_object_key_order_and_whitespace(self):
        shuffled = json.loads(json.dumps(self.f, sort_keys=True))
        self.assertEqual(content_hash(self.f), content_hash(shuffled))
        self.assertFalse(canonical_bytes(self.f).endswith(b'\n'))

    def test_hash_retains_array_order_and_content(self):
        changed = copy.deepcopy(self.f)
        changed['stored_events'].reverse()
        self.assertNotEqual(content_hash(self.f), content_hash(changed))

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'duplicate.json'
            p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):
                load(p)

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):
            canonical_bytes({'a': float('nan')})


if __name__ == '__main__':
    unittest.main()
