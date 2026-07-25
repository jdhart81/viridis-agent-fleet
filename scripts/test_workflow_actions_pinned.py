#!/usr/bin/env python3
"""Regression guard for immutable third-party GitHub Action references."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
USES_LINE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^#\s]+)")
FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class WorkflowActionPinTests(unittest.TestCase):
    def test_third_party_actions_use_full_commit_sha(self) -> None:
        failures: list[str] = []
        workflow_files = sorted(
            [*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]
        )
        self.assertTrue(workflow_files, "no workflow files found")

        for workflow in workflow_files:
            for line_number, line in enumerate(
                workflow.read_text(encoding="utf-8").splitlines(), start=1
            ):
                match = USES_LINE.match(line)
                if not match:
                    continue
                reference = match.group(1)
                if reference.startswith("./"):
                    continue
                if "@" not in reference:
                    failures.append(
                        f"{workflow.relative_to(ROOT)}:{line_number}: "
                        f"missing @commit in {reference}"
                    )
                    continue
                action, revision = reference.rsplit("@", 1)
                if not FULL_COMMIT.fullmatch(revision):
                    failures.append(
                        f"{workflow.relative_to(ROOT)}:{line_number}: "
                        f"{action} must use a 40-character commit SHA"
                    )

        self.assertEqual([], failures, "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
