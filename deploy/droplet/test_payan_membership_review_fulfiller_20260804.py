import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_DIR = Path(__file__).parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))
MODULE_PATH = MODULE_DIR / "payan_membership_review_fulfiller_20260804.py"
SPEC = importlib.util.spec_from_file_location("membership_review_fulfiller", MODULE_PATH)
worker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(worker)


def valid_detail(*, request_status="open", bid_status="pending", provider_id=None):
    request = {
        "_id": worker.REQUEST_ID,
        "title": worker.EXPECTED_TITLE,
        "buyerId": worker.EXPECTED_BUYER_ID,
        "status": request_status,
        "escrow": False,
        "budgetMaxCents": worker.EXPECTED_PRICE_CENTS,
    }
    if provider_id is not None:
        request["providerId"] = provider_id
    if request_status == "accepted":
        request["agreedPriceCents"] = worker.EXPECTED_PRICE_CENTS
    bid = {
        "_id": "bid-1",
        "bidderId": "agent-1",
        "status": bid_status,
        "priceCents": worker.EXPECTED_PRICE_CENTS,
        "estimatedDurationSeconds": worker.EXPECTED_DURATION_SECONDS,
        "message": worker.BID_MESSAGE,
    }
    return {"request": request, "bids": [bid]}, bid


class FulfillerValidationTests(unittest.TestCase):
    def test_pending_bid_waits(self):
        detail, bid = valid_detail()
        self.assertEqual(
            worker.fulfillment_action(detail, "agent-1", bid),
            "pending_buyer_acceptance",
        )

    def test_exact_accepted_bid_fulfills(self):
        detail, bid = valid_detail(
            request_status="accepted", bid_status="accepted", provider_id="agent-1"
        )
        self.assertEqual(worker.fulfillment_action(detail, "agent-1", bid), "fulfill")

    def test_wrong_accepted_provider_fails_closed(self):
        detail, bid = valid_detail(
            request_status="accepted", bid_status="accepted", provider_id="agent-2"
        )
        with self.assertRaisesRegex(RuntimeError, "not assigned"):
            worker.fulfillment_action(detail, "agent-1", bid)

    def test_fulfilled_own_request_is_idempotent(self):
        detail, bid = valid_detail(
            request_status="fulfilled", bid_status="accepted", provider_id="agent-1"
        )
        self.assertEqual(
            worker.fulfillment_action(detail, "agent-1", bid), "already_fulfilled"
        )

    def test_bid_message_drift_is_rejected(self):
        detail, _ = valid_detail()
        detail["bids"][0]["message"] = "drift"
        with self.assertRaisesRegex(RuntimeError, "not uniquely verifiable"):
            worker.exact_bid(detail, "agent-1")

    def test_output_contains_digest_and_boundaries(self):
        output = worker.build_output("review body", "bid-1")
        self.assertIn(worker.DELIVERABLE_SHA256, output)
        self.assertIn("no wallet connection", output.lower())
        self.assertIn("review body", output)


if __name__ == "__main__":
    unittest.main()
