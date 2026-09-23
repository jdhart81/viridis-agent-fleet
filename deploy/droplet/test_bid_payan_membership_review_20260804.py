import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name("bid_payan_membership_review_20260804.py")
SPEC = importlib.util.spec_from_file_location("bid_payan_membership_review", MODULE_PATH)
bidder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bidder)


def valid_detail(*, bids=None):
    return {
        "request": {
            "_id": bidder.REQUEST_ID,
            "title": bidder.EXPECTED_TITLE,
            "buyerId": bidder.EXPECTED_BUYER_ID,
            "status": "open",
            "escrow": False,
            "budgetMaxCents": bidder.EXPECTED_PRICE_CENTS,
        },
        "bids": bids or [],
    }


class BidValidationTests(unittest.TestCase):
    def test_exact_open_request_without_own_bid(self):
        self.assertIsNone(bidder.validate_target(valid_detail(), "agent-1"))

    def test_existing_own_bid_is_idempotent(self):
        own = {"_id": "bid-1", "bidderId": "agent-1", "status": "pending"}
        self.assertEqual(bidder.validate_target(valid_detail(bids=[own]), "agent-1"), own)

    def test_different_buyer_fails_closed(self):
        detail = valid_detail()
        detail["request"]["buyerId"] = "someone-else"
        with self.assertRaisesRegex(RuntimeError, "exact open one-cent"):
            bidder.validate_target(detail, "agent-1")

    def test_escrowed_variant_fails_closed(self):
        detail = valid_detail()
        detail["request"]["escrow"] = True
        with self.assertRaisesRegex(RuntimeError, "exact open one-cent"):
            bidder.validate_target(detail, "agent-1")

    def test_duplicate_own_bids_fail_closed(self):
        bids = [
            {"_id": "bid-1", "bidderId": "agent-1"},
            {"_id": "bid-2", "bidderId": "agent-1"},
        ]
        with self.assertRaisesRegex(RuntimeError, "multiple Viridis bids"):
            bidder.validate_target(valid_detail(bids=bids), "agent-1")


if __name__ == "__main__":
    unittest.main()
