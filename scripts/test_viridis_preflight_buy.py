"""Buyer payment boundaries. Every transport is synthetic; no money moves."""
import argparse
import base64
import copy
import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import viridis_preflight_buy as buyer
from viridis_preflight_watch import _digest, baseline_from_paid_result

INPUTS = {"agent_id": "test-agent", "manifest": {"tools": []}}


def required():
    return {"x402Version": 2, "resource": {"url": buyer.URL}, "accepts": [{
        "scheme": "exact", "network": buyer.NETWORK, "asset": buyer.ASSET,
        "payTo": buyer.RECIPIENT, "amount": "10000", "maxTimeoutSeconds": 60,
        "extra": {"name": "USD Coin", "version": "2"}}]}


def challenge(value=None):
    value = required() if value is None else value
    return 402, {"PAYMENT-REQUIRED": base64.b64encode(json.dumps(value).encode()).decode()}, {}


def result():
    value = {"status": "ok", "receipt": {"receipt_id": "vsr_" + "a" * 24},
             "findings": [], "buyer_feedback_token": "private-test-token"}
    delivery = {"version": "viridis-paid-delivery-v1", "route": "security-preflight/security_preflight",
                "settlement": {"transaction": "synthetic-only"}, "result_sha256": _digest(value)}
    delivery["receipt_sha256"] = _digest(delivery)
    return {**value, "viridis_delivery": delivery}


class FakeSigner:
    address = "synthetic-buyer"
    def sign(self, value):
        self.signed = value
        return "synthetic-signature"


class BuyerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "paid.json"

    def paid(self, **kwargs):
        return buyer.run(INPUTS, pay=True, cap=10000, output=self.output,
                         signer_factory=FakeSigner, **kwargs)

    def test_default_does_not_load_wallet_or_sign(self):
        calls = []
        def transport(*args):
            calls.append(args)
            return challenge()
        with patch.dict('os.environ', {'X402_BUYER_PRIVATE_KEY': 'must-not-read'}):
            value = buyer.run(INPUTS, transport=transport,
                              signer_factory=lambda: self.fail('wallet loaded'))
        self.assertFalse(value['payment_attempted'])
        self.assertEqual(len(calls), 1)
        self.assertNotIn('PAYMENT-SIGNATURE', calls[0][1])

    def test_modified_terms_and_over_cap_cannot_sign(self):
        changes = [('payTo', '0x'+'a'*40), ('asset', '0x'+'b'*40),
                   ('network', 'eip155:1'), ('scheme', 'upto'), ('amount', '10001'),
                   ('maxTimeoutSeconds', 3600)]
        for key, value in changes:
            with self.subTest(key=key):
                q = required(); q['accepts'][0][key] = value
                with self.assertRaises(buyer.BuyerError):
                    self.paid(transport=lambda *args: challenge(q))
                self.assertFalse(self.output.exists())

    def test_resource_redirect_and_multiple_options_refused(self):
        q = required();q['resource']['url'] = 'https://other.invalid/paid'
        options = required();options['accepts'].append(copy.deepcopy(options['accepts'][0]))
        for response in [challenge(q), challenge(options), (308, {'Location': buyer.URL}, {})]:
            with self.assertRaises(buyer.BuyerError):buyer.quote(response)
        self.assertIsNone(buyer.NoRedirect().redirect_request(None,None,307,'',{},'https://other.invalid'))

    def test_paid_requires_explicit_cap_and_storage(self):
        for kwargs in [{}, {'cap':10000}, {'output':self.output}]:
            with self.assertRaises(buyer.BuyerError):
                buyer.run(INPUTS, pay=True, signer_factory=lambda: self.fail('wallet loaded'), **kwargs)

    def test_success_saves_private_complete_result_with_repeat_baseline(self):
        calls = []
        def transport(*args):
            calls.append(args)
            return challenge() if len(calls)==1 else (200, {}, result())
        summary = self.paid(transport=transport)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], calls[1][0])
        self.assertEqual(calls[1][1]['PAYMENT-SIGNATURE'], 'synthetic-signature')
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        saved = json.loads(self.output.read_text())
        self.assertEqual(saved, result())
        self.assertEqual(baseline_from_paid_result(saved), summary['receipt_id'])
        self.assertNotIn('private-test-token', json.dumps(summary))

    def test_existing_result_is_never_overwritten_or_paid_again(self):
        self.output.write_text('prior receipt')
        calls = []
        def transport(*args):calls.append(args);return challenge()
        with self.assertRaises(buyer.BuyerError):self.paid(transport=transport)
        self.assertEqual(self.output.read_text(), 'prior receipt')
        self.assertEqual(len(calls), 1)

    def test_uncertain_network_outcome_is_saved_without_retry(self):
        calls=[]
        def transport(*args):
            calls.append(args)
            if len(calls)==1:return challenge()
            raise TimeoutError('may already have settled')
        with self.assertRaisesRegex(buyer.BuyerError, 'outcome unknown'):
            self.paid(transport=transport)
        self.assertEqual(len(calls), 2)
        self.assertEqual(json.loads(self.output.read_text())['status'], 'PAYMENT_OUTCOME_UNKNOWN')

    def test_bad_response_and_paid_redirect_saved_without_retry(self):
        for status, body in [(200, {'status':'ok'}), (500, {'error':'failed'}), (307, {})]:
            with self.subTest(status=status):
                self.output.unlink(missing_ok=True)
                responses=iter([challenge(), (status, {}, body)])
                with self.assertRaises(buyer.BuyerError):
                    self.paid(transport=lambda *args: next(responses))
                self.assertEqual(json.loads(self.output.read_text()), body)

    def test_invalid_amounts_refused(self):
        for value in ['NaN','Infinity','-1','0','0.0000001']:
            with self.assertRaises(argparse.ArgumentTypeError):buyer.atomic(value)
        self.assertEqual(buyer.atomic('0.01'),10000)

    @unittest.skipUnless(importlib.util.find_spec('x402'), 'optional paid SDK not installed')
    def test_real_sdk_signs_only_validated_quote_locally(self):
        from eth_account import Account
        key = Account.create().key.hex()  # unfunded ephemeral test account
        with patch.dict('os.environ', {'X402_BUYER_PRIVATE_KEY': key}):
            signer = buyer.Signer()
            payload = json.loads(base64.b64decode(signer.sign(buyer.quote(challenge(),10000))))
        self.assertEqual(payload['accepted']['amount'], '10000')
        self.assertEqual(payload['accepted']['payTo'].lower(), buyer.RECIPIENT.lower())
        self.assertEqual(payload['resource']['url'], buyer.URL)
        self.assertEqual(payload['payload']['authorization']['from'].lower(), signer.address.lower())


if __name__ == '__main__':unittest.main()
