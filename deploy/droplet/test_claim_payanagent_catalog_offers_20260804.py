from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).with_name("claim_payanagent_catalog_offers_20260804.py")
SPEC = importlib.util.spec_from_file_location("claim_payan_catalog", MODULE_PATH)
assert SPEC and SPEC.loader
claimant = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = claimant
SPEC.loader.exec_module(claimant)


class PayanCatalogClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.claim = claimant.CLAIMS[0]
        self.terms = {
            "payTo": claimant.PAY_TO,
            "asset": claimant.USDC,
            "network": claimant.NETWORK,
            "amountRaw": "10000",
        }
        self.offer = {
            "_id": self.claim.offer_id,
            "isActive": True,
            "sellerId": None,
            "amountRaw": "10000",
        }

    def test_exact_unclaimed_offer_and_terms_pass(self) -> None:
        claimant.validate_existing_offer(self.claim, self.offer, self.terms)

    def test_idempotent_same_seller_offer_passes(self) -> None:
        self.offer["sellerId"] = claimant.SELLER_ID
        claimant.validate_existing_offer(self.claim, self.offer, self.terms)

    def test_offer_owned_by_other_seller_fails_closed(self) -> None:
        self.offer["sellerId"] = "other-seller"
        with self.assertRaisesRegex(RuntimeError, "another seller"):
            claimant.validate_existing_offer(self.claim, self.offer, self.terms)

    def test_price_change_fails_closed(self) -> None:
        self.terms["amountRaw"] = "250000"
        with self.assertRaisesRegex(RuntimeError, "unapproved catalog quote change"):
            claimant.validate_existing_offer(self.claim, self.offer, self.terms)

    def test_exact_manifest_intro_correction_passes(self) -> None:
        self.offer["amountRaw"] = "2000000"
        claimant.validate_existing_offer(
            self.claim,
            self.offer,
            self.terms,
            nominal_amount="2000000",
            intro_amount="10000",
        )

    def test_intro_correction_requires_stored_nominal_price(self) -> None:
        self.offer["amountRaw"] = "500000"
        with self.assertRaisesRegex(RuntimeError, "unapproved catalog quote change"):
            claimant.validate_existing_offer(
                self.claim,
                self.offer,
                self.terms,
                nominal_amount="2000000",
                intro_amount="10000",
            )

    def test_wallet_or_asset_change_fails_closed(self) -> None:
        for field, value in (
            ("payTo", "0x0000000000000000000000000000000000000001"),
            ("asset", "0x0000000000000000000000000000000000000002"),
        ):
            changed = dict(self.terms)
            changed[field] = value
            with self.assertRaises(RuntimeError):
                claimant.validate_existing_offer(self.claim, self.offer, changed)

    def test_claim_payload_uses_exact_url_and_post(self) -> None:
        payload = claimant.claim_payload(self.claim, "Live description.")
        self.assertEqual(payload["externalUrl"], self.claim.endpoint)
        self.assertEqual(payload["httpMethod"], "POST")
        self.assertEqual(payload["verificationBody"], self.claim.example_input)
        self.assertEqual(payload["title"], self.claim.title)
        self.assertNotIn("verification_query", payload)

    def test_exact_claim_state_is_idempotent(self) -> None:
        self.offer.update(
            {
                "sellerId": claimant.SELLER_ID,
                "title": self.claim.title,
                "httpMethod": "POST",
                "rankScore": 1000,
            }
        )
        self.assertTrue(
            claimant.is_exact_claimed(self.claim, self.offer, self.terms)
        )
        self.offer["httpMethod"] = "GET"
        self.assertFalse(
            claimant.is_exact_claimed(self.claim, self.offer, self.terms)
        )


if __name__ == "__main__":
    unittest.main()
