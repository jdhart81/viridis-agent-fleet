#!/usr/bin/env python3
"""Offline tests for the unpaid-only Regulatory Radar preflight."""

import base64
import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import radar_preflight as preflight  # noqa: E402


ENDPOINT = "https://mcp.test" + preflight.ROUTE


def _encoded_required(**overrides):
    required = {
        "x402Version": 2,
        "resource": {"url": ENDPOINT},
        "accepts": [
            {
                "scheme": "exact",
                "network": preflight.BASE_NETWORK,
                "asset": preflight.BASE_USDC,
                "amount": "10000",
                "payTo": "0xViridis",
            }
        ],
    }
    required.update(overrides)
    return base64.urlsafe_b64encode(
        json.dumps(required).encode("utf-8")
    ).decode("ascii").rstrip("=")


class RadarPreflightTests(unittest.TestCase):
    def _run(self, header=None, **kwargs):
        captured = {}

        def fake_fetch(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            headers = {} if header is None else {"PAYMENT-REQUIRED": header}
            return 402, headers, b'{"error":"PAYMENT-SIGNATURE required"}'

        result = preflight.preflight(
            "US",
            "energy",
            query="45V emissions",
            base_url="https://mcp.test",
            fetch=fake_fetch,
            **kwargs,
        )
        return result, captured

    def test_valid_v2_quote_passes_without_payment(self):
        result, captured = self._run(_encoded_required())

        self.assertEqual(result["status"], "verified_unpaid")
        self.assertEqual(result["amount_atomic_usdc"], 10_000)
        self.assertFalse(result["payment_attempted"])
        self.assertEqual(captured["request"].full_url, ENDPOINT)

    def test_missing_header_fails_closed(self):
        with self.assertRaisesRegex(
            preflight.PreflightError, "omitted PAYMENT-REQUIRED"
        ):
            self._run()

    def test_v1_fails_closed(self):
        with self.assertRaisesRegex(preflight.PreflightError, "x402Version 2"):
            self._run(_encoded_required(x402Version=1))

    def test_wrong_network_asset_or_resource_fails_closed(self):
        invalid_accepts = [
            ("network", "eip155:1"),
            ("asset", "0xWrong"),
        ]
        for key, value in invalid_accepts:
            accepted = {
                "scheme": "exact",
                "network": preflight.BASE_NETWORK,
                "asset": preflight.BASE_USDC,
                "amount": "10000",
                "payTo": "0xViridis",
            }
            accepted[key] = value
            with self.subTest(key=key), self.assertRaises(
                preflight.PreflightError
            ):
                self._run(_encoded_required(accepts=[accepted]))

        with self.assertRaisesRegex(preflight.PreflightError, "resource"):
            self._run(
                _encoded_required(resource={"url": ENDPOINT + "-wrong"})
            )

    def test_quote_above_ceiling_fails_before_payment(self):
        accepted = {
            "scheme": "exact",
            "network": preflight.BASE_NETWORK,
            "asset": preflight.BASE_USDC,
            "amount": "250001",
            "payTo": "0xViridis",
        }
        with self.assertRaisesRegex(preflight.PreflightError, "exceeds ceiling"):
            self._run(
                _encoded_required(accepts=[accepted]),
                max_atomic=250_000,
            )

    def test_payer_is_only_public_hint_and_no_payment_header_is_sent(self):
        _, captured = self._run(
            _encoded_required(), payer="0xPublicPayer"
        )
        headers = {
            key.lower(): value
            for key, value in captured["request"].header_items()
        }
        self.assertEqual(headers["x402-payer-address"], "0xPublicPayer")
        self.assertNotIn("payment-signature", headers)
        self.assertNotIn("x-payment", headers)
        self.assertNotIn("authorization", headers)
        payload = json.loads(captured["request"].data)
        self.assertEqual(
            payload,
            {
                "jurisdiction": "US",
                "sector": "energy",
                "query": "45V emissions",
            },
        )
        self.assertNotIn("private", json.dumps(payload).lower())


if __name__ == "__main__":
    unittest.main()
