import unittest

import bid_payan_x402_examples_20260804 as target


class ExactPayanExampleBidTests(unittest.TestCase):
    def detail(self, request_id, *, bids=None, **overrides):
        expected = target.JOBS[request_id]
        row = {
            "_id": request_id,
            "title": expected["title"],
            "buyerId": target.EXPECTED_BUYER_ID,
            "status": "open",
            "escrow": True,
            "escrowDepositedCents": expected["budget_cents"],
            "budgetMaxCents": expected["budget_cents"],
        }
        row.update(overrides)
        return {"request": row, "bids": bids or []}

    def test_all_jobs_are_positive_margin_at_the_declared_purchase_cap(self):
        for expected in target.JOBS.values():
            self.assertEqual(expected["bid_cents"], 1)
            self.assertGreater(expected["bid_cents"] / 100, 0.001)

    def test_exact_open_escrowed_job_without_own_bid_is_eligible(self):
        request_id = next(iter(target.JOBS))
        self.assertIsNone(target.validate_target(request_id, self.detail(request_id), "viridis"))

    def test_wrong_escrow_amount_fails_closed(self):
        request_id = next(iter(target.JOBS))
        with self.assertRaisesRegex(RuntimeError, "exact open"):
            target.validate_target(
                request_id,
                self.detail(request_id, escrowDepositedCents=999),
                "viridis",
            )

    def test_duplicate_own_bids_fail_closed(self):
        request_id = next(iter(target.JOBS))
        bids = [{"bidderId": "viridis"}, {"bidderId": "viridis"}]
        with self.assertRaisesRegex(RuntimeError, "multiple Viridis"):
            target.validate_target(request_id, self.detail(request_id, bids=bids), "viridis")

    def test_existing_bid_must_match_every_reviewed_field(self):
        expected = next(iter(target.JOBS.values()))
        bid = {**target.exact_bid_payload(expected), "status": "pending"}
        target.verify_existing(bid, expected)
        bid["message"] = "different"
        with self.assertRaisesRegex(RuntimeError, "differs"):
            target.verify_existing(bid, expected)


if __name__ == "__main__":
    unittest.main()
