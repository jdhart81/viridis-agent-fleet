"""Action-surface parity pin (N68, SUPPORTED_ACTIONS spirit).

The process() handler table is the real public surface; describe() is the
advertised one; record_frontdoor_view / frontdoor_summary are deliberately
gateway-internal (not registered as MCP tools by the thin adapter). Nothing
previously pinned these three sets against drift: a handler added without a
describe() entry (or vice versa) would ship silently. These tests make the
split mechanical.
"""

import asyncio
import unittest

from src.core import SubscriptionsCore, AgentConfig


GATEWAY_INTERNAL = {
    "record_frontdoor_view",
    "record_snapshot_view",
    "record_snapshot_checkout_started",
    "record_snapshot_paid",
    "record_acquisition_view",
    "frontdoor_summary",
}


def _make_core():
    return SubscriptionsCore(AgentConfig())


def _registered_actions(core) -> set:
    """Recover the live handler table from the unknown-action envelope
    (constraint = 'one of: a, b, c') so the pin tracks the REAL table,
    not a hardcoded copy of it."""
    out = asyncio.run(core.process({"action": "definitely-not-an-action"}))
    assert out["status"] == "error" and out["error_type"] == "ValidationError"
    constraint = out["constraint"]
    prefix = "one of: "
    assert constraint.startswith(prefix), constraint
    return {a.strip() for a in constraint[len(prefix):].split(",")}


class TestActionSurfaceParity(unittest.TestCase):
    def setUp(self):
        self.core = _make_core()
        self.registered = _registered_actions(self.core)

    def test_every_advertised_capability_is_registered(self):
        capabilities = set(self.core.describe()["capabilities"])
        missing = capabilities - self.registered
        self.assertEqual(missing, set(),
                         f"describe() advertises unregistered actions: {missing}")

    def test_gateway_internal_actions_registered_but_not_advertised(self):
        capabilities = set(self.core.describe()["capabilities"])
        self.assertTrue(GATEWAY_INTERNAL <= self.registered,
                        "gateway-internal funnel actions must stay callable")
        leaked = GATEWAY_INTERNAL & capabilities
        self.assertEqual(leaked, set(),
                         f"gateway-internal actions leaked into describe(): {leaked}")

    def test_surface_split_is_exhaustive(self):
        """registered == advertised ∪ gateway-internal — any new handler
        must be explicitly classified on one side of the split."""
        capabilities = set(self.core.describe()["capabilities"])
        unclassified = self.registered - capabilities - GATEWAY_INTERNAL
        self.assertEqual(unclassified, set(),
                         f"new handler(s) not classified public/internal: {unclassified}")


if __name__ == "__main__":
    unittest.main()
