#!/usr/bin/env python3
"""Verify the only allowed first-boot copied-state normalization.

Run inside the exact candidate image after its first clean stop. Both database
arguments must be offline copies mounted read-only. The verifier never opens a
live production database and never writes either input.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import pickle
import sqlite3
import sys
from pathlib import Path
from typing import Any


EXPECTED_ROWS = 35
EXPECTED_CHANGED = frozenset({"metering", "security-preflight"})
EXPECTED_METERING_ATTRS = frozenset({"_meters", "_seq"})
EXPECTED_SECURITY_BEFORE_ATTRS = frozenset(
    {"_payment_gate_state", "_receipt_db_path", "_receipts"}
)
EXPECTED_SECURITY_AFTER_ATTRS = frozenset(
    {"_payment_gate_state", "_receipts"}
)
EXPECTED_PRODUCTION_RECEIPT_DB = (
    "/data/security_preflight_receipts.sqlite3"
)


class NormalizationFailure(RuntimeError):
    """Copied-state normalization exceeded its exact allowed boundary."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise NormalizationFailure(message)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_rows(path: Path) -> dict[str, dict[str, Any]]:
    require(path.is_file(), f"database is missing: {path}")
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        require(integrity == ("ok",), f"SQLite integrity failed: {path}")
        rows = connection.execute(
            "SELECT agent, seq, snapshot, sha256, updated_at "
            "FROM agent_state ORDER BY agent"
        ).fetchall()
    finally:
        connection.close()
    result = {}
    for agent, seq, snapshot, stored_sha, updated_at in rows:
        actual_sha = _sha256_bytes(snapshot)
        require(
            stored_sha == actual_sha,
            f"{agent}: stored snapshot SHA-256 does not match its bytes",
        )
        result[agent] = {
            "seq": int(seq),
            "snapshot": snapshot,
            "sha256": stored_sha,
            "updated_at": updated_at,
        }
    return result


def _load_runtime_module_contexts() -> dict[str, dict[str, Any]]:
    gateway_dir = Path("/fleet/deploy/gateway")
    require(gateway_dir.is_dir(), "exact candidate gateway is unavailable")
    sys.path.insert(0, str(gateway_dir))
    import viridis_mcp_gateway as gateway

    contexts = {}
    for agent in ("metering", "security-preflight"):
        agent_dir = gateway.MOUNTS.get(agent)
        require(agent_dir is not None, f"{agent}: current mount is missing")
        gateway._load_adapter(agent, agent_dir)
        contexts[agent] = {
            name: sys.modules[name]
            for name in list(sys.modules)
            if name == "src" or name.startswith("src.")
        }
    return contexts


@contextlib.contextmanager
def _module_context(modules: dict[str, Any] | None):
    if not modules:
        yield
        return
    sentinel = object()
    saved = {}
    for name, module in modules.items():
        saved[name] = sys.modules.get(name, sentinel)
        sys.modules[name] = module
    try:
        yield
    finally:
        for name, previous in saved.items():
            if previous is sentinel:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def _unpickle(raw: bytes, modules: dict[str, Any] | None) -> dict[str, Any]:
    with _module_context(modules):
        state = pickle.loads(raw)
    require(isinstance(state, dict), "snapshot root is not a dictionary")
    return state


def verify_normalization(
    before: Path,
    after: Path,
    *,
    module_contexts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    require(before.resolve() != after.resolve(), "before and after are the same")
    require(
        not Path(str(after) + "-wal").exists(),
        "normalized database still has a WAL sidecar",
    )
    require(
        not Path(str(after) + "-shm").exists(),
        "normalized database still has an SHM sidecar",
    )
    require(
        not (after.parent / "security_preflight_receipts.sqlite3").exists(),
        "candidate created a persistent Security Preflight receipt database",
    )

    before_rows = _read_rows(before)
    after_rows = _read_rows(after)
    require(
        len(before_rows) == EXPECTED_ROWS,
        f"expected {EXPECTED_ROWS} before rows, found {len(before_rows)}",
    )
    require(
        len(after_rows) == EXPECTED_ROWS,
        f"expected {EXPECTED_ROWS} after rows, found {len(after_rows)}",
    )
    require(
        before_rows.keys() == after_rows.keys(),
        "agent_state row identities changed",
    )
    changed = {
        agent
        for agent in before_rows
        if before_rows[agent] != after_rows[agent]
    }
    require(
        changed == EXPECTED_CHANGED,
        "unexpected changed rows: "
        f"expected {sorted(EXPECTED_CHANGED)}, found {sorted(changed)}",
    )

    contexts = module_contexts or _load_runtime_module_contexts()
    semantic = {}
    for agent in sorted(EXPECTED_CHANGED):
        old = before_rows[agent]
        new = after_rows[agent]
        require(
            new["seq"] == old["seq"] + 1,
            f"{agent}: first normalization did not advance exactly one seq",
        )
        require(
            new["updated_at"] != old["updated_at"],
            f"{agent}: changed row retained its old timestamp",
        )
        old_state = _unpickle(old["snapshot"], contexts.get(agent))
        new_state = _unpickle(new["snapshot"], contexts.get(agent))
        if agent == "metering":
            require(
                frozenset(old_state) == EXPECTED_METERING_ATTRS,
                "metering: unexpected pre-normalization attributes",
            )
            require(
                frozenset(new_state) == EXPECTED_METERING_ATTRS,
                "metering: unexpected post-normalization attributes",
            )
            require(
                old_state == new_state,
                "metering: logical state changed during normalization",
            )
            semantic[agent] = {
                "logical_state_equal": True,
                "attributes": sorted(new_state),
            }
        else:
            require(
                frozenset(old_state) == EXPECTED_SECURITY_BEFORE_ATTRS,
                "security-preflight: unexpected legacy attributes",
            )
            require(
                old_state["_receipt_db_path"]
                == EXPECTED_PRODUCTION_RECEIPT_DB,
                "security-preflight: legacy receipt path is unexpected",
            )
            require(
                frozenset(new_state) == EXPECTED_SECURITY_AFTER_ATTRS,
                "security-preflight: runtime path was not excluded",
            )
            durable_old = {
                key: value
                for key, value in old_state.items()
                if key != "_receipt_db_path"
            }
            require(
                durable_old == new_state,
                "security-preflight: durable state changed",
            )
            semantic[agent] = {
                "durable_state_equal": True,
                "removed_runtime_attribute": "_receipt_db_path",
                "attributes": sorted(new_state),
            }

    return {
        "status": "ok",
        "before_sha256": _sha256_file(before),
        "after_sha256": _sha256_file(after),
        "agent_state_rows": len(after_rows),
        "changed_rows": sorted(changed),
        "semantic": semantic,
        "receipt_database_created": False,
        "wal_present": False,
        "shm_present": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_normalization(args.before, args.after)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
