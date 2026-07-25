from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("publish_mcp_registry_idempotent.sh")


class PublishMcpRegistryIdempotentTests(unittest.TestCase):
    def run_wrapper(self, publisher_body: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            publisher = root / "fake publisher"
            manifest = root / "server manifest.json"
            publisher.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n" + publisher_body,
                encoding="utf-8",
            )
            publisher.chmod(0o755)
            manifest.write_text("{}\n", encoding="utf-8")
            return subprocess.run(
                ["bash", str(SCRIPT), str(publisher), str(manifest)],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "LC_ALL": "C"},
            )

    def test_successful_publish_is_reported(self) -> None:
        result = self.run_wrapper('printf "published\\n"\n')

        self.assertEqual(result.returncode, 0)
        self.assertIn("published", result.stdout)
        self.assertIn("registry_publish_outcome=published", result.stdout)

    def test_duplicate_version_is_an_idempotent_success(self) -> None:
        result = self.run_wrapper(
            'printf "%s\\n" '
            '\'{"errors":[{"message":"invalid version: cannot publish duplicate version"}]}\' '
            ">&2\n"
            "exit 1\n"
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("already published", result.stdout)
        self.assertIn("registry_publish_outcome=already_published", result.stdout)

    def test_unrelated_failure_remains_a_failure(self) -> None:
        result = self.run_wrapper('printf "authentication failed\\n" >&2\nexit 17\n')

        self.assertEqual(result.returncode, 17)
        self.assertIn("authentication failed", result.stdout)
        self.assertNotIn("registry_publish_outcome=", result.stdout)


if __name__ == "__main__":
    unittest.main()
