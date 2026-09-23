#!/usr/bin/env python3
"""Keep deployment-local Security Preflight storage out of restored state."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


INPUT_SHA256 = (
    "6272581daa541f74f97e75f1f5cb663ff625ebdcc101e1a03518401783d89b9c"
)
OUTPUT_SHA256 = (
    "e34b2c1bd9a0618e59e8864bacae2e1fd10404ddc41e60b4beb61bceaf7ccc73"
)

EXCLUSION_ANCHOR = """\
EXCLUDED_ATTRS = frozenset({"config", "logger", "process"})
"""

EXCLUSION_REPLACEMENT = EXCLUSION_ANCHOR + """\

# Runtime-bound values are chosen from the current process environment and
# must never move between production, recovery drills, or isolated candidates.
# Their durable state still restores normally; only the deployment-local
# transport/storage selector is rebuilt on each boot.
RUNTIME_BOUND_ATTRS = {
    "security-preflight": frozenset({"_receipt_db_path"}),
}
"""

SNAPSHOT_ANCHOR = """\
        skipped = self._skipped_attrs.setdefault(name, set())
        for attr, value in vars(core).items():
            if attr in EXCLUDED_ATTRS:
                continue
"""

SNAPSHOT_REPLACEMENT = """\
        skipped = self._skipped_attrs.setdefault(name, set())
        runtime_bound = RUNTIME_BOUND_ATTRS.get(name, frozenset())
        for attr, value in vars(core).items():
            if attr in EXCLUDED_ATTRS or attr in runtime_bound:
                continue
"""

RESTORE_ANCHOR = """\
            with self._module_context(name):    # PS8
                state = pickle.loads(row[0])
            for attr, value in state.items():
                setattr(core, attr, value)
"""

RESTORE_REPLACEMENT = """\
            with self._module_context(name):    # PS8
                state = pickle.loads(row[0])
            runtime_bound = RUNTIME_BOUND_ATTRS.get(name, frozenset())
            for attr, value in state.items():
                if attr in runtime_bound:
                    continue
                setattr(core, attr, value)
"""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def transformed_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    observed = _sha256(raw)
    if observed != INPUT_SHA256:
        raise RuntimeError(
            f"input digest mismatch: expected {INPUT_SHA256}, found {observed}"
        )
    text = raw.decode("utf-8")
    if "RUNTIME_BOUND_ATTRS" in text:
        raise RuntimeError("runtime-bound restore boundary is already present")
    text = _replace_once(
        text,
        EXCLUSION_ANCHOR,
        EXCLUSION_REPLACEMENT,
        "runtime-bound declaration",
    )
    text = _replace_once(
        text,
        SNAPSHOT_ANCHOR,
        SNAPSHOT_REPLACEMENT,
        "runtime-bound snapshot exclusion",
    )
    text = _replace_once(
        text,
        RESTORE_ANCHOR,
        RESTORE_REPLACEMENT,
        "runtime-bound restore exclusion",
    )
    return text.encode("utf-8")


def apply_overlay(path: Path) -> str:
    output = transformed_bytes(path)
    output_digest = _sha256(output)
    if not OUTPUT_SHA256:
        raise RuntimeError(
            "OUTPUT_SHA256 is not pinned; observed transform "
            f"{output_digest}"
        )
    if output_digest != OUTPUT_SHA256:
        raise RuntimeError(
            "output digest mismatch: "
            f"expected {OUTPUT_SHA256}, found {output_digest}"
        )
    path.write_bytes(output)
    return output_digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("/fleet/deploy/gateway/state_store.py"),
    )
    args = parser.parse_args()
    print(apply_overlay(args.path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
