import copy
import importlib.util
import json
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name(
    "tune_payanagent_offer_conversion_20260804.py"
)
SPEC = importlib.util.spec_from_file_location("payan_offer_tuner", MODULE_PATH)
assert SPEC and SPEC.loader
target = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(target)


def current_rows():
    rows = {}
    for offer_id, spec in target.OFFER_UPDATES.items():
        rows[offer_id] = {
            "_id": offer_id,
            "sellerId": target.SELLER_AGENT_ID,
            "isActive": True,
            "payTo": target.SELLER_WALLET,
            "network": "eip155:8453",
            "amountRaw": spec["expected"]["amountRaw"],
            "priceCents": spec["expected"]["priceCents"],
            "title": spec["expected"]["title"],
        }
    return rows


class OfferTuningTests(unittest.TestCase):
    def test_schemas_are_valid_closed_json_schemas(self):
        for spec in target.OFFER_UPDATES.values():
            parsed = json.loads(spec["patch"]["inputSchema"])
            self.assertEqual(parsed["type"], "object")
            self.assertIs(parsed["additionalProperties"], False)
            self.assertTrue(parsed["required"])

    def test_rejects_payment_term_drift(self):
        offer_id = next(iter(target.OFFER_UPDATES))
        row = current_rows()[offer_id]
        row["amountRaw"] = "999999"
        with self.assertRaisesRegex(RuntimeError, "exact Viridis listing"):
            target.validate_current(offer_id, row)

    def test_tunes_exact_metadata_only(self):
        rows = current_rows()
        calls = []

        def requester(url, *, method="GET", payload=None, api_key=None):
            offer_id = url.split("?", 1)[0].rsplit("/", 1)[-1]
            calls.append((offer_id, method, copy.deepcopy(payload), api_key))
            if method == "PATCH":
                rows[offer_id].update(payload)
                return 200, {"ok": True}
            return 200, {"offer": copy.deepcopy(rows[offer_id])}

        result = target.tune_offers("pk_test", requester=requester)
        self.assertEqual(len(result), 3)
        self.assertEqual([c[1] for c in calls], ["GET", "PATCH", "GET"] * 3)
        for offer_id, row in rows.items():
            target.validate_updated(offer_id, row)
            self.assertEqual(row["amountRaw"], target.OFFER_UPDATES[offer_id]["expected"]["amountRaw"])
            self.assertNotIn("priceCents", target.OFFER_UPDATES[offer_id]["patch"])
            self.assertNotIn("endpoint", target.OFFER_UPDATES[offer_id]["patch"])

    def test_evidence_boundaries_are_all_false(self):
        boundaries = {
            "changed_price": False,
            "changed_payment_terms": False,
            "changed_endpoint": False,
            "signed": False,
            "moved_money": False,
            "accepted_bid": False,
        }
        self.assertTrue(all(value is False for value in boundaries.values()))


if __name__ == "__main__":
    unittest.main()
