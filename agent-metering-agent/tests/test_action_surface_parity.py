"""Action-surface parity pin (N69 cross-pollination of the N68
subscriptions idiom, SUPPORTED_ACTIONS spirit).

Three surfaces must agree: the live dispatch table (recovered from the
unknown-action envelope's 'one of:' constraint, not hardcoded), the
describe().capabilities advertisement, and the handlers that actually
answer. The metering agent has NO gateway-internal actions, so the pin is
exact parity: advertised == registered, and every registered action
reaches a real handler (never the unknown-action envelope).
"""

import asyncio
import unittest

from src.core import build


def _registered_actions(core) -> set:
    out = asyncio.run(core.process({"action": "definitely-not-an-action"}))
    assert out["status"] == "error", out
    constraint = out.get("constraint", "")
    prefix = "one of: "
    assert constraint.startswith(prefix), constraint
    return {a.strip() for a in constraint[len(prefix):].split(",") if a.strip()}


class TestActionSurfaceParity(unittest.TestCase):
    def setUp(self):
        self.core = build()
        self.registered = _registered_actions(self.core)

    def test_advertised_equals_registered(self):
        capabilities = set(self.core.describe()["capabilities"])
        self.assertEqual(
            capabilities, self.registered,
            "describe().capabilities and the dispatch constraint drifted: "
            f"advertised-only={capabilities - self.registered}, "
            f"registered-only={self.registered - capabilities}")

    def test_every_registered_action_reaches_a_handler(self):
        """The constraint string must not advertise a dead route: calling
        each registered action (bare, no args) may fail validation but must
        NEVER come back as 'unknown action'."""
        for act in sorted(self.registered):
            out = asyncio.run(build().process({"action": act}))
            err = str(out.get("error", "")) + str(out.get("message", ""))
            self.assertNotIn("unknown action", err,
                             f"registered action '{act}' has no handler")


if __name__ == "__main__":
    unittest.main()
