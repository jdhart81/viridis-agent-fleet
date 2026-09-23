import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from flywheel_work_receipts import apply_receipts, receipt_for, schedule_status

NOW = '2026-09-09T13:00:00+00:00'


class ReceiptTests(unittest.TestCase):
    def test_recorded_attempt_is_not_reported_as_missing_execution(self):
        result = schedule_status({'last_scheduled_attempt': '2026-09-09T12:30:00+00:00'}, NOW, '2026-09-09T12:00:00+00:00')
        self.assertEqual(result['status'], 'attempted_incomplete')
        self.assertTrue(result['alert'])
        self.assertIsNone(result['last_scheduled_run'])

    def test_manual_run_does_not_hide_missed_schedule(self):
        result = schedule_status({'last_run': NOW}, NOW, '2026-09-09T12:00:00+00:00')
        self.assertEqual(result['status'], 'never_succeeded')
        self.assertTrue(result['alert'])

    def test_future_scheduled_time_is_not_missed(self):
        self.assertEqual(schedule_status({}, NOW, '2026-09-09T14:00:46+00:00')['status'], 'not_due')

    def test_old_scheduled_success_is_missed(self):
        result = schedule_status({'last_scheduled_run': '2026-09-07T14:00:00+00:00'}, NOW, NOW)
        self.assertEqual(result['status'], 'missed')

    def test_review_requires_evidence_and_reopens_when_changed_or_expired(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            proof = root / 'evidence.txt'
            proof.write_text('Authenticated inbox check: no new reply')
            action = {'id': 'buyer:1', 'action': 'Review inbox'}
            r = receipt_for(action, proof, root, 'Checked inbox', NOW)
            opened, reviewed = apply_receipts([action], [r], NOW, root)
            self.assertFalse(opened)
            self.assertEqual(len(reviewed), 1)
            self.assertTrue(apply_receipts([action], [r], '2026-09-11T13:00:00+00:00', root)[0])
            changed = {**action, 'action': 'Buyer replied; qualify scope'}
            self.assertTrue(apply_receipts([changed], [r], NOW, root)[0])
            proof.write_text('modified evidence')
            self.assertTrue(apply_receipts([action], [r], NOW, root)[0])

    def test_live_drift_cannot_be_hidden_by_manual_receipt(self):
        with self.assertRaises(ValueError):
            receipt_for({'id': 'fleet-guide'}, 'unused', Path('/tmp'), 'done', NOW)

    def test_missing_evidence_rejected(self):
        with TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                receipt_for({'id': 'buyer:1'}, Path(folder)/'missing', Path(folder), 'done', NOW)


if __name__ == '__main__':
    unittest.main()
