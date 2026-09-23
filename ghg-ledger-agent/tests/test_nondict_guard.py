"""Pin the non-dict input guard; stdlib unittest so the agent tests anywhere.

process() must never raise on non-dict input; it must return the structured
ValidationError envelope (field="input", constraint="object"). Added Night 60 —
the guard existed in core.py but no test pinned it.
"""
import asyncio
import unittest

from src.core import build


def run(payload):
    return asyncio.run(build().process(payload))


class TestNonDictGuard(unittest.TestCase):
    def test_nondict_input_returns_validation_envelope(self):
        for bad_input in (None, [], "not-a-dict", 5):
            with self.subTest(bad_input=bad_input):
                r = run(bad_input)
                self.assertIsInstance(r, dict)
                self.assertEqual(r["status"], "error")
                self.assertEqual(r["error_type"], "ValidationError")
                self.assertEqual(r["field"], "input")
                self.assertEqual(r["constraint"], "object")
                self.assertIn("must be an object", r["message"])


if __name__ == "__main__":
    unittest.main()
