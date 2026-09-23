#!/usr/bin/env python3

from __future__ import annotations

import copy
import unittest

import monitor_payan_x402_example_bids_20260804 as watcher
from bid_payan_x402_examples_20260804 import EXPECTED_BUYER_ID, JOBS, exact_bid_payload


def detail_for(request_id: str) -> dict:
    expected = JOBS[request_id]
    bid = {
        "_id": watcher.EXPECTED_BID_IDS[request_id],
        "bidderId": watcher.SELLER_ID,
        "requestId": request_id,
        "status": "pending",
        **exact_bid_payload(expected),
    }
    return {
        "request": {
            "_id": request_id,
            "title": expected["title"],
            "buyerId": EXPECTED_BUYER_ID,
            "budgetMaxCents": expected["budget_cents"],
            "escrow": True,
            "escrowDepositedCents": expected["budget_cents"],
            "status": "open",
        },
        "bids": [bid],
    }


class ClassifyTests(unittest.TestCase):
    def test_pending_bid_waits_for_buyer(self) -> None:
        request_id = next(iter(JOBS))
        result = watcher.classify(request_id, detail_for(request_id))
        self.assertEqual(result["state"], "pending_buyer_acceptance")
        self.assertFalse(result["purchase_authorized"])

    def test_exact_acceptance_holds_for_purchase_authorization(self) -> None:
        request_id = next(iter(JOBS))
        detail = detail_for(request_id)
        detail["request"].update(
            {
                "status": "accepted",
                "providerId": watcher.SELLER_ID,
                "agreedPriceCents": JOBS[request_id]["bid_cents"],
            }
        )
        detail["bids"][0]["status"] = "accepted"
        result = watcher.classify(request_id, detail)
        self.assertEqual(result["state"], "accepted_purchase_authorization_required")
        self.assertFalse(result["funds_moved"])

    def test_acceptance_price_drift_fails_closed(self) -> None:
        request_id = next(iter(JOBS))
        detail = detail_for(request_id)
        detail["request"].update(
            {
                "status": "accepted",
                "providerId": watcher.SELLER_ID,
                "agreedPriceCents": 2,
            }
        )
        detail["bids"][0]["status"] = "accepted"
        with self.assertRaisesRegex(RuntimeError, "price drifted"):
            watcher.classify(request_id, detail)

    def test_duplicate_own_bid_fails_closed(self) -> None:
        request_id = next(iter(JOBS))
        detail = detail_for(request_id)
        detail["bids"].append(copy.deepcopy(detail["bids"][0]))
        with self.assertRaisesRegex(RuntimeError, "not unique"):
            watcher.classify(request_id, detail)

    def test_other_provider_is_loss_not_revenue(self) -> None:
        request_id = next(iter(JOBS))
        detail = detail_for(request_id)
        detail["request"].update(
            {
                "status": "completed",
                "providerId": "j57other",
                "agreedPriceCents": JOBS[request_id]["bid_cents"],
            }
        )
        detail["bids"][0]["status"] = "rejected"
        result = watcher.classify(request_id, detail)
        self.assertEqual(result["state"], "lost_to_other_provider")

    def test_snapshot_counts_acceptances(self) -> None:
        details = {request_id: detail_for(request_id) for request_id in JOBS}
        accepted_id = next(iter(JOBS))
        details[accepted_id]["request"].update(
            {
                "status": "accepted",
                "providerId": watcher.SELLER_ID,
                "agreedPriceCents": JOBS[accepted_id]["bid_cents"],
            }
        )
        details[accepted_id]["bids"][0]["status"] = "accepted"

        def fetch(request_id: str) -> tuple[int, dict]:
            return 200, details[request_id]

        snapshot = watcher.build_snapshot(fetch, "2026-08-04T00:00:00+00:00")
        self.assertEqual(snapshot["accepted_authorization_required_count"], 1)
        self.assertEqual(snapshot["next_action"], "hold_for_exact_purchase_authorization")
        self.assertFalse(snapshot["boundaries"]["signs"])


if __name__ == "__main__":
    unittest.main()
