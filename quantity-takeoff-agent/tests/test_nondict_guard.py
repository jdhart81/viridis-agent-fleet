"""Pin the fleet-standard non-dict input guard — Night 61.

process() must never raise on non-dict input; the internal ValidationError
must surface as the canonical structured envelope (field="input",
constraint="object" dialect). The guard existed in core.py but no test
pinned it, so a regression would have gone undetected.
"""
import asyncio
import unittest

from src.core import build


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestNonDictGuard(unittest.TestCase):
    def test_nondict_input_returns_canonical_envelope(self):
        a = build()
        for bad in (None, [], "not-a-dict", 5):
            with self.subTest(bad_input=type(bad).__name__):
                r = run(a.process(bad))
                self.assertIsInstance(r, dict)
                self.assertEqual(r["status"], "error")
                self.assertEqual(r["error_type"], "ValidationError")
                self.assertEqual(r["field"], "input")
                self.assertEqual(r["value"], type(bad).__name__)
                self.assertEqual(r["constraint"], "object")
                self.assertEqual(r["message"], "input must be an object")
                self.assertIn("timestamp", r)


if __name__ == "__main__":
    unittest.main()
