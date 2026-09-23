from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name(
    "auto_claim_payanagent_catalog_offers_20260804.py"
)
SPEC = importlib.util.spec_from_file_location("auto_payan_claim", MODULE_PATH)
assert SPEC and SPEC.loader
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)


class AutoCatalogClaimTests(unittest.TestCase):
    def test_requires_both_exact_production_markers(self) -> None:
        self.assertTrue(
            watch.deployment_ready(
                "verificationBody is used only during the unpaid ownership probe"
            )
        )
        self.assertFalse(watch.deployment_ready("verificationBody"))
        self.assertFalse(
            watch.deployment_ready("only during the unpaid ownership probe")
        )


if __name__ == "__main__":
    unittest.main()
