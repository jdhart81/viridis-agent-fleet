#!/usr/bin/env python3
"""ORC v0.1 deterministic-replay validator (reference, dry-run only).

Given an Outcome Receipt, independently re-run the computation it claims and
produce UNSIGNED ERC-8004 Validation Registry `validationResponse` arguments.
It never holds keys and never touches a chain: submitting is the operator's
job, with their own signer, on the network they choose (Base Sepolia first).

Supported replay profiles:
  viridis.cliff-check/48E, viridis.cliff-check/45Y  -> taxcredit-engine replay
Any other profile is checked for integrity (L1) only and answered 0, because
a validator must not vouch for work it cannot reproduce.

--- INVARIANTS ---
V1  response is 100 only if the receipt is INTACT (L1) AND an independent
    replay reproduces digest.value exactly; otherwise 0.
V2  The output args equal fleet_utils.orc.erc8004_validation_response for the
    same inputs (one mapping, one implementation).
V3  No network, no keys, no chain writes; stdlib + fleet code only.
V4  Replay needs the original facts; without them the answer is 0 with the
    reason "facts_required" (a validator cannot replay from outputs alone).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

FLEET_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FLEET_ROOT))
from fleet_utils import orc  # noqa: E402

REPLAYABLE = {"viridis.cliff-check/48E": "48E", "viridis.cliff-check/45Y": "45Y"}


def _engine():
    src = FLEET_ROOT / "taxcredit-engine-agent" / "src"
    spec = importlib.util.spec_from_file_location(
        "orcv_taxcredit", src / "__init__.py", submodule_search_locations=[str(src)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["orcv_taxcredit"] = mod
    spec.loader.exec_module(mod)
    return mod.build()


def replay(receipt: dict, facts: dict | None) -> dict:
    level = orc.verify(receipt)
    out = {"intact": level["level"] >= 1, "replayed": False, "reason": ""}
    if not out["intact"]:
        out["reason"] = "not_intact"
        return out
    credit = REPLAYABLE.get(receipt.get("profile", ""))
    if credit is None:
        out["reason"] = "profile_not_replayable"
        return out
    if not isinstance(facts, dict):                                   # V4
        out["reason"] = "facts_required"
        return out
    res = asyncio.run(_engine().process({"action": "calculate", "credit": credit,
                                         "facts": facts}))
    if res.get("status") != "ok":
        out["reason"] = "engine_rejected_facts"
        return out
    out["replayed"] = res["data"].get("audit_sha256") == receipt["digest"]["value"]
    out["reason"] = "reproduced" if out["replayed"] else "replay_mismatch"
    return out


def validate(receipt: dict, facts: dict | None, *, request_hash: str,
             response_uri: str) -> dict:
    r = replay(receipt, facts)
    passed = r["intact"] and r["replayed"]                            # V1
    args = orc.erc8004_validation_response(receipt, request_hash=request_hash,
                                           response_uri=response_uri, passed=passed)
    return {"args": args, "replay": r, "signed": False,
            "submit": "Sign and send validationResponse(...) with YOUR signer on "
                      "Base Sepolia (chain 84532) first. This tool never does."}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ORC deterministic-replay validator (dry run)")
    ap.add_argument("receipt", help="ORC v0.1 JSON file")
    ap.add_argument("--facts", help="JSON file with the original facts (or a Cliff Check spec)")
    ap.add_argument("--request-hash", required=True, help="0x + 64 hex from validationRequest")
    ap.add_argument("--response-uri", required=True, help="https URL where the ORC is published")
    a = ap.parse_args(argv)
    receipt = json.loads(Path(a.receipt).read_text())
    facts = None
    if a.facts:
        f = json.loads(Path(a.facts).read_text())
        facts = f.get("facts", f)
    rh = a.request_hash[2:] if a.request_hash.startswith("0x") else a.request_hash
    print(json.dumps(validate(receipt, facts, request_hash=rh.lower(),
                              response_uri=a.response_uri), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
