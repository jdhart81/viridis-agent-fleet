#!/usr/bin/env python3
"""Calculate aggregate retention cohorts from an offline gateway state copy.

Payer addresses are used transiently for grouping and never printed or
written. The input database is opened immutable/read-only.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import json
import pickle
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "deploy/gateway"
sys.path.insert(0, str(GATEWAY))

from retention_cohorts import build_retention_cohorts  # noqa: E402
from x402_http import (  # noqa: E402
    SETTLEMENT_CLASSIFICATION_VERSION,
    X402_HTTP_TOOLS,
)

PAID_AGENTS = frozenset(agent for agent, _tool in X402_HTTP_TOOLS)


def rows(path: Path) -> dict[str, bytes]:
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True
    )
    try:
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("state database integrity check failed")
        result = {}
        for agent, snapshot, stored_sha in connection.execute(
            "SELECT agent, snapshot, sha256 FROM agent_state ORDER BY agent"
        ):
            if hashlib.sha256(snapshot).hexdigest() != stored_sha:
                raise RuntimeError(f"{agent}: stored snapshot digest mismatch")
            result[str(agent)] = snapshot
        return result
    finally:
        connection.close()


def module_context(agent: str) -> dict[str, Any]:
    gateway = importlib.import_module("viridis_mcp_gateway")
    mount = gateway.MOUNTS.get(agent)
    if mount is None:
        return {}
    gateway._load_adapter(agent, mount)
    return {
        name: sys.modules[name]
        for name in list(sys.modules)
        if name == "src" or name.startswith("src.")
    }


@contextlib.contextmanager
def installed(modules: dict[str, Any]):
    sentinel = object()
    prior = {name: sys.modules.get(name, sentinel) for name in modules}
    sys.modules.update(modules)
    try:
        yield
    finally:
        for name, value in prior.items():
            if value is sentinel:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def decode(agent: str, raw: bytes) -> dict[str, Any]:
    modules = module_context(agent)
    with installed(modules):
        value = pickle.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError(f"{agent}: snapshot root is not an object")
    return value


def probe(path: Path, *, as_of: datetime) -> dict[str, Any]:
    state_rows = rows(path)
    records = []
    decoded_rows = 0
    missing = sorted(PAID_AGENTS - state_rows.keys())
    if missing:
        raise RuntimeError(f"state database is missing paid agents: {missing}")
    for agent in sorted(PAID_AGENTS):
        state = decode(agent, state_rows[agent])
        decoded_rows += 1
        gate = state.get("_payment_gate_state")
        if not isinstance(gate, dict):
            continue
        consumed = gate.get("consumed_x402")
        if not isinstance(consumed, dict):
            continue
        for record in consumed.values():
            if (
                isinstance(record, dict)
                and record.get("surface") in {"http-402-v2", "a2a-x402-v2"}
                and record.get("classification_version")
                == SETTLEMENT_CLASSIFICATION_VERSION
            ):
                records.append(record)
    cohorts = build_retention_cohorts(records, as_of=as_of)
    return {
        "status": "ok",
        "classification": "offline_aggregate_retention_probe",
        "database_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "state_rows": len(state_rows),
        "decoded_rows": decoded_rows,
        "versioned_records_considered": len(records),
        "retention_cohorts": cohorts,
        "payer_identifiers_returned": False,
        "production_mutated": False,
    }


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("as-of timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--as-of", default=datetime.now(timezone.utc).isoformat())
    args = parser.parse_args()
    try:
        result = probe(args.database, as_of=parse_time(args.as_of))
    except Exception as exc:
        print(json.dumps({
            "status": "failed",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
