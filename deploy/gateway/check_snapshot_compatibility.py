#!/usr/bin/env python3
"""Release gate for a copied production gateway-state database.

Loads every current adapter with the same module isolation as the gateway,
then verifies that every snapshot row can be unpickled and re-serialized under
the current code. The database argument must be a backup/copy, never the live
production file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import viridis_mcp_gateway as gateway
from state_store import StateStore


def load_current_cores(store: StateStore) -> tuple[dict, dict]:
    cores = {}
    errors = {}
    for path, agent_dir in {
        **gateway.MOUNTS,
        "subscriptions": "subscriptions-agent",
    }.items():
        try:
            adapter = gateway._load_adapter(path, agent_dir)
            modules = {
                name: sys.modules[name] for name in list(sys.modules)
                if name == "src" or name.startswith("src.")
            }
            cores[path] = adapter.agent
            store.register_modules(path, modules)
        except Exception as exc:
            errors[path] = f"{type(exc).__name__}: {exc}"
    return cores, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db", type=Path, required=True,
        help="path to an offline backup/copy of viridis_state.db")
    args = parser.parse_args()
    if not args.db.is_file():
        print(json.dumps({
            "status": "error",
            "errors": {"__db__": f"database not found: {args.db}"},
        }, indent=2))
        return 1

    store = StateStore(str(args.db))
    cores, load_errors = load_current_cores(store)
    report = store.compatibility_report(cores)
    report["adapter_load_errors"] = load_errors
    if load_errors:
        report["status"] = "error"
    print(json.dumps(report, indent=2, sort_keys=True))
    store.close()
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
