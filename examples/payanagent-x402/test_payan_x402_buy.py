import base64
from decimal import Decimal
import json
import unittest

from payan_x402_buy import BASE_USDC, decode_payment_required, parse_input, validate_terms


def encode(payload):
    return base64.b64encode(json.dumps(payload).encode()).decode()


class PaymentTermsTests(unittest.TestCase):
    def valid_terms(self):
        return {
            "x402Version": 2,
            "accepts": [
                {
                    "scheme": "exact",
                    "network": "eip155:8453",
                    "amount": "1000",
                    "payTo": "0x1111111111111111111111111111111111111111",
                    "asset": BASE_USDC,
                }
            ],
        }

    def test_decodes_and_accepts_capped_base_usdc(self):
        decoded = decode_payment_required(encode(self.valid_terms()))
        row = validate_terms(decoded, Decimal("0.01"))
        self.assertEqual(row["amount"], "1000")

    def test_rejects_wrong_asset(self):
        terms = self.valid_terms()
        terms["accepts"][0]["asset"] = "0x2222222222222222222222222222222222222222"
        with self.assertRaisesRegex(ValueError, "exactly one"):
            validate_terms(terms, Decimal("0.01"))

    def test_rejects_over_cap(self):
        terms = self.valid_terms()
        terms["accepts"][0]["amount"] = "10001"
        with self.assertRaisesRegex(ValueError, "exceeds cap"):
            validate_terms(terms, Decimal("0.01"))

    def test_input_must_be_object(self):
        self.assertEqual(parse_input('{"message":"ok"}'), {"message": "ok"})
        with self.assertRaisesRegex(ValueError, "JSON object"):
            parse_input("[]")


if __name__ == "__main__":
    unittest.main()
