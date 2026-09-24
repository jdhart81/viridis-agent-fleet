"""Nightkeeper N70 action-surface parity pin."""

import asyncio
import unittest

from src.core import build


def _registered_actions(core) -> set:
    out = asyncio.run(core.process({"action": "definitely-not-an-action"}))
    assert out["status"] == "error", out
    constraint = out.get("constraint", "")
    prefix = "one of: "
    assert constraint.startswith(prefix), constraint
    return {item.strip() for item in constraint[len(prefix):].split(",")
            if item.strip()}


class TestActionSurfaceParity(unittest.TestCase):
    def setUp(self):
        self.core = build()
        self.registered = _registered_actions(self.core)

    def test_advertised_equals_registered(self):
        advertised = set(self.core.describe()["capabilities"])
        self.assertEqual(advertised, self.registered)

    def test_every_registered_action_reaches_a_handler(self):
        for action in sorted(self.registered):
            out = asyncio.run(build().process({"action": action}))
            error = str(out.get("error", "")) + str(out.get("message", ""))
            self.assertNotIn("unknown action", error)


if __name__ == "__main__":
    unittest.main()
