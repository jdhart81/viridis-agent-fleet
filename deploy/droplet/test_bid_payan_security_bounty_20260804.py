from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name("bid_payan_security_bounty_20260804.py")
SPEC = importlib.util.spec_from_file_location("bid_payan_security_bounty", MODULE_PATH)
assert SPEC and SPEC.loader
bidder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bidder)


def valid_detail(*, bids: list[dict] | None = None) -> dict:
    return {
        "request": {
            "_id": bidder.REQUEST_ID,
            "title": bidder.EXPECTED_TITLE,
            "status": "open",
            "escrow": True,
            "escrowDepositedCents": bidder.EXPECTED_PRICE_CENTS,
            "budgetMaxCents": bidder.EXPECTED_PRICE_CENTS,
        },
        "bids": bids or [],
    }


class PayanSecurityBidTests(unittest.TestCase):
    def test_exact_open_escrow_target_passes(self) -> None:
        self.assertIsNone(bidder.validate_target(valid_detail(), "agent-1"))

    def test_existing_agent_bid_is_returned_for_idempotency(self) -> None:
        existing = {"_id": "bid-1", "bidderId": "agent-1", "status": "pending"}
        self.assertEqual(
            bidder.validate_target(valid_detail(bids=[existing]), "agent-1"), existing
        )

    def test_changed_escrow_or_status_fails_closed(self) -> None:
        for field, value in (("status", "accepted"), ("escrowDepositedCents", 4)):
            detail = valid_detail()
            detail["request"][field] = value
            with self.assertRaises(RuntimeError):
                bidder.validate_target(detail, "agent-1")


if __name__ == "__main__":
    unittest.main()
