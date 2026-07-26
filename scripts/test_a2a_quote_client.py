#!/usr/bin/env python3
"""Offline contract tests for the official-SDK A2A quote probe."""
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import a2a_quote_client as client  # noqa: E402


class Obj:
    def __init__(self, **values):
        self.__dict__.update(values)


class A2AQuoteClientTests(unittest.TestCase):
    def test_card_selectors_require_exact_interface_and_extension(self):
        interface = Obj(
            protocol_binding="HTTP+JSON",
            protocol_version="1.0",
            url="https://mcp.test/a2a",
        )
        extension = Obj(uri=client.EXTENSION_URI, required=True)
        card = Obj(
            supported_interfaces=[
                Obj(protocol_binding="JSONRPC", url="https://mcp.test/rpc"),
                interface,
            ],
            capabilities=Obj(extensions=[extension]),
        )

        self.assertIs(client._interface(card), interface)
        self.assertIs(client._extension(card), extension)

    def test_required_skill_set_includes_hive_and_all_paid_routes(self):
        self.assertEqual(
            client.REQUIRED_SKILL_IDS,
            {
                "quantity-takeoff.calculate_takeoff",
                "ghg-ledger.calculate_inventory",
                "disclosure-compiler.compile_disclosure",
                "taxcredit-engine.calculate_tax_credit",
                "regulatory-radar.scan_regulations",
                "hive.solve",
            },
        )

    def test_skill_discovery_tolerates_future_additions(self):
        card = Obj(skills=[
            *(Obj(id=skill_id) for skill_id in client.REQUIRED_SKILL_IDS),
            Obj(id="future-agent.future_tool"),
            Obj(id=""),
        ])

        skill_ids = client._skill_ids(card)

        self.assertFalse(client.REQUIRED_SKILL_IDS - skill_ids)
        self.assertIn("future-agent.future_tool", skill_ids)
        self.assertNotIn("", skill_ids)

    def test_quote_summary_extracts_official_protobuf_json_shape(self):
        event = {
            "task": {
                "id": "task-1",
                "status": {
                    "state": "TASK_STATE_INPUT_REQUIRED",
                    "message": {
                        "metadata": {
                            "x402.payment.status": "payment-required",
                            "x402.payment.required": {
                                "x402Version": 2.0,
                                "resource": {
                                    "url": "https://mcp.test/x402/radar/scan"
                                },
                                "accepts": [{
                                    "scheme": "exact",
                                    "network": "eip155:8453",
                                    "asset": "0xUSDC",
                                    "amount": "10000",
                                    "payTo": "0xSeller",
                                }],
                            },
                        }
                    },
                },
            }
        }

        self.assertEqual(
            client._quote_summary(event),
            {
                "task_id": "task-1",
                "state": "TASK_STATE_INPUT_REQUIRED",
                "payment_status": "payment-required",
                "x402_version": 2.0,
                "scheme": "exact",
                "network": "eip155:8453",
                "asset": "0xUSDC",
                "amount_atomic_usdc": "10000",
                "pay_to": "0xSeller",
                "resource": "https://mcp.test/x402/radar/scan",
            },
        )

    def test_default_mode_is_read_only_discovery(self):
        args = client._parser().parse_args([])
        self.assertFalse(args.request_quote)
        self.assertEqual(args.base_url, client.DEFAULT_BASE_URL)
        self.assertEqual(args.skill, client.DEFAULT_SKILL)


if __name__ == "__main__":
    unittest.main()
