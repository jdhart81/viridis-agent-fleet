from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name(
    "monitor_payan_mcp_child_solver_request_20260804.py"
)
SPEC = importlib.util.spec_from_file_location("solver_monitor", MODULE_PATH)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


def valid_detail(*, bids: list[dict] | None = None) -> dict:
    return {
        "request": {
            "_id": monitor.REQUEST_ID,
            "buyerId": monitor.BUYER_ID,
            "title": monitor.REQUEST_TITLE,
            "status": "open",
            "escrow": False,
            "budgetMaxCents": 1,
        },
        "bids": bids or [],
    }


class SolverIntakeMonitorTests(unittest.TestCase):
    def test_empty_request_waits_without_action(self) -> None:
        snapshot = monitor.build_snapshot(
            valid_detail(), lambda _: (500, {}), "2026-08-04T00:00:00+00:00"
        )
        self.assertEqual(snapshot["bid_count"], 0)
        self.assertEqual(snapshot["next_action"], "wait_for_candidate")
        self.assertTrue(all(value is False for value in snapshot["boundaries"].values()))

    def test_valid_distinct_profile_becomes_review_candidate(self) -> None:
        bid = {
            "_id": "bid-1",
            "bidderId": "agent-1",
            "status": "pending",
            "priceCents": 1,
            "message": "available",
        }
        profile = {
            "_id": "agent-1",
            "name": "Independent",
            "status": "active",
            "chain": "base",
            "providerType": "agent",
            "walletAddress": "0x1111111111111111111111111111111111111111",
            "reputation": {"sales": 1},
        }
        snapshot = monitor.build_snapshot(
            valid_detail(bids=[bid]), lambda _: (200, profile), "now"
        )
        self.assertEqual(snapshot["public_profile_valid_pending_count"], 1)
        self.assertEqual(
            snapshot["next_action"], "review_candidate_independence_and_registration"
        )
        self.assertNotIn("message", snapshot["candidates"][0])
        self.assertFalse(snapshot["candidates"][0]["independence_verified"])

    def test_same_wallet_profile_fails_closed(self) -> None:
        bid = {
            "_id": "bid-1",
            "bidderId": "agent-1",
            "status": "pending",
            "message": "available",
        }
        profile = {
            "_id": "agent-1",
            "status": "active",
            "chain": "base",
            "providerType": "agent",
            "walletAddress": monitor.VIRIDIS_WALLET,
        }
        snapshot = monitor.build_snapshot(
            valid_detail(bids=[bid]), lambda _: (200, profile), "now"
        )
        self.assertEqual(snapshot["public_profile_valid_pending_count"], 0)
        self.assertEqual(
            snapshot["candidates"][0]["eligibility"], "public_profile_failed_closed"
        )

    def test_api_provider_is_not_promoted_as_independent_solver(self) -> None:
        bid = {
            "_id": "bid-1",
            "bidderId": "api-1",
            "status": "pending",
            "message": "wallet screening",
        }
        profile = {
            "_id": "api-1",
            "status": "active",
            "chain": "base",
            "providerType": "api",
            "walletAddress": "0x2222222222222222222222222222222222222222",
        }
        snapshot = monitor.build_snapshot(
            valid_detail(bids=[bid]), lambda _: (200, profile), "now"
        )
        self.assertEqual(snapshot["public_profile_valid_pending_count"], 0)
        self.assertEqual(snapshot["next_action"], "wait_for_candidate")
        self.assertEqual(
            snapshot["candidates"][0]["eligibility"],
            "provider_type_ineligible_for_solver",
        )

    def test_request_identity_or_escrow_drift_fails_closed(self) -> None:
        for field, value in (("buyerId", "other"), ("escrow", True)):
            detail = valid_detail()
            detail["request"][field] = value
            with self.assertRaises(RuntimeError):
                monitor.build_snapshot(detail, lambda _: (200, {}), "now")


if __name__ == "__main__":
    unittest.main()
