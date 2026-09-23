from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name(
    "post_payan_mcp_child_solver_request_20260804.py"
)
SPEC = importlib.util.spec_from_file_location("payan_solver_intake", MODULE_PATH)
assert SPEC and SPEC.loader
intake = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(intake)


def valid_feed() -> dict:
    return {
        "degraded": False,
        "network": "base-mainnet",
        "items": [
            {
                "source_id": intake.PARENT_CONTRACT,
                "source_status": "claimable",
                "source_url": intake.PARENT_ISSUE_URL,
                "work_state": "claimable",
                "payment_state": "escrowed",
                "payment_committed": True,
                "verification_ready": True,
                "standing_meta_bounty": True,
                "reward": {"amount": "2000000"},
                "cash_economics": {
                    "required_external_spend": {"amount": "1000000"},
                    "gross_cash_margin": {"amount": "1000000"},
                    "gross_cash_margin_positive": True,
                },
            }
        ],
    }


class PayanMcpChildSolverRequestTests(unittest.TestCase):
    def test_exact_parent_passes(self) -> None:
        parent = intake.validate_parent_feed(valid_feed())
        self.assertEqual(parent["source_id"], intake.PARENT_CONTRACT)

    def test_parent_state_or_economics_drift_fails_closed(self) -> None:
        for path, value in (
            (("items", 0, "work_state"), "claimed"),
            (("items", 0, "payment_committed"), False),
            (("items", 0, "cash_economics", "gross_cash_margin_positive"), False),
        ):
            feed = valid_feed()
            target = feed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.assertRaises(RuntimeError):
                intake.validate_parent_feed(feed)

    def test_only_exact_open_buyer_request_is_duplicate(self) -> None:
        exact = {
            "_id": "request-1",
            "buyerId": intake.SELLER_AGENT_ID,
            "title": intake.REQUEST_TITLE,
            "status": "open",
        }
        other = {**exact, "buyerId": "other-agent"}
        self.assertEqual(
            intake.find_existing_request([other, exact], intake.SELLER_AGENT_ID), exact
        )
        self.assertIsNone(
            intake.find_existing_request([other], intake.SELLER_AGENT_ID)
        )

    def test_created_request_must_match_every_approved_field(self) -> None:
        row = {
            "_id": "request-1",
            "buyerId": intake.SELLER_AGENT_ID,
            "title": intake.REQUEST_TITLE,
            "description": intake.REQUEST_DESCRIPTION,
            "budgetMaxCents": 1,
            "escrow": False,
            "status": "open",
        }
        self.assertEqual(
            intake.validate_created_request({"request": row}, "request-1"), row
        )
        for field, value in (("escrow", True), ("budgetMaxCents", 2)):
            changed = {**row, field: value}
            with self.assertRaises(RuntimeError):
                intake.validate_created_request({"request": changed}, "request-1")


if __name__ == "__main__":
    unittest.main()
