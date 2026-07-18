#!/usr/bin/env python3
"""Certify the fleet's own cognition: a notarized brain_id for every mount.

For each agent in the gateway MOUNTS:
  1. Build a deterministic CONSTITUTIONAL GENOME (viridis-fleet-genome.v1)
     from its agent.yaml — name, purpose, role, governance nodes. The schema
     is fixed and stated below, so ANYONE can regenerate the genome and
     verify the brain_id (verifiable cognition, VB1/VB3).
  2. Compile it with the verdigraph brain engine (same vendored engine the
     /verdigraph mount serves — sandbox==prod determinism was verified at
     mount time).
  3. Notarize content_hash on the LIVE fleet notary (commit + immediate
     reveal -> permanent REVEALED proof, N1/N2).
  4. Emit docs/FLEET_BRAIN_REGISTRY.md — the fleet's auditable constitution.

Run from the fleet root:
  VIRIDIS_INTERNAL_SECRET=<48-char secret> python3 scripts/certify_fleet_brains.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets as pysecrets
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "verdigraph-brain-agent"))
from src.vg.brain import extract, report_to_dict, verify_brain  # noqa: E402

BASE = "https://mcp.viridisconservation.com"
GENOME_SCHEMA = "viridis-fleet-genome.v1"


def mounts() -> dict:
    text = (ROOT / "deploy" / "gateway" / "viridis_mcp_gateway.py").read_text()
    block = text.split("MOUNTS = {")[1].split("}")[0]
    return dict(re.findall(r'"([a-z0-9-]+)":\s+"([a-z0-9- ]+agent)"', block))


def yaml_field(text: str, key: str) -> str:
    m = re.search(rf'^{key}:\s*"?(.+?)"?\s*$', text, re.M)
    return (m.group(1) if m else "").strip()


def genome_for(mount: str, agent_dir: str) -> dict:
    y = (ROOT / agent_dir / "agent.yaml").read_text()
    role = yaml_field(y, "a2a_role") or yaml_field(y, "pillar") or "service"
    return {
        "agent_name": yaml_field(y, "name") or agent_dir,
        "purpose": yaml_field(y, "description")[:500],
        "initial_nodes": ["mission_keeper", "invariant_enforcer",
                          "service_endpoint", role.replace(" ", "_")],
        "fitness_metrics": ["invariant_compliance", "fleet_test_pass_rate"],
        "metadata": {"fleet_mount": mount, "version": yaml_field(y, "version"),
                     "constitution": GENOME_SCHEMA},
    }


def mcp_call(path: str, tool: str, args: dict, secret: str) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": args}}).encode()
    req = urllib.request.Request(
        f"{BASE}/{path}/mcp", data=body,
        headers={"content-type": "application/json",
                 "accept": "application/json, text/event-stream",
                 "X-Viridis-Internal": f"{secret}:fleet-constitution"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode()
    data = [ln[5:] for ln in raw.splitlines() if ln.startswith("data:")]
    payload = json.loads(data[-1] if data else raw)
    return json.loads(payload["result"]["content"][0]["text"])


def main() -> int:
    secret = os.environ.get("VIRIDIS_INTERNAL_SECRET", "").strip()
    if not secret:
        print("VIRIDIS_INTERNAL_SECRET required (env/viridis internal "
              "secret.md — the 48-char token)")
        return 1
    deadline = (datetime.now(timezone.utc)
                + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows, failures = [], []
    for mount, agent_dir in sorted(mounts().items()):
        genome = genome_for(mount, agent_dir)
        content = json.dumps(genome, sort_keys=True)
        brain = extract("verdigraph_genome", content.encode())
        report = report_to_dict(verify_brain(brain))
        checks = report.get("checks") or []
        passed = sum(1 for c in checks if c.get("passed"))
        salt = pysecrets.token_hex(16)
        digest = brain.content_hash
        commit_hash = hashlib.sha256((salt + digest).encode()).hexdigest()
        try:
            committed = mcp_call("notary", "commit", {
                "committer": "viridis:fleet-constitution",
                "nonce": f"brain-{mount}", "commit_hash": commit_hash,
                "deadline": deadline,
                "context": f"fleet-brain {mount} {brain.brain_id}"}, secret)
            cid = (committed.get("data") or {}).get("commitment_id")
            revealed = mcp_call("notary", "reveal", {
                "commitment_id": cid, "salt": salt,
                "content_digest": digest}, secret)
            state = (revealed.get("data") or {}).get("state") \
                or revealed.get("status")
        except Exception as exc:  # noqa: BLE001
            cid, state = None, f"ERROR {type(exc).__name__}"
            failures.append(mount)
        rows.append((mount, brain.brain_id, digest, passed, len(checks),
                     cid, state))
        print(f"{mount:22s} {brain.brain_id} inv {passed}/{len(checks)} "
              f"notary {cid} {state}")

    out = ROOT / "docs" / "FLEET_BRAIN_REGISTRY.md"
    lines = [
        "# Viridis Fleet Brain Registry — Notarized Cognition",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()} · genome schema "
        f"`{GENOME_SCHEMA}` · engine: verdigraph-neurogenesis (vendored, "
        "DOI 10.5281/zenodo.20400274)",
        "",
        "Every mounted agent's constitutional genome (name, purpose, role, "
        "governance nodes — regenerate it with "
        "`scripts/certify_fleet_brains.py`) compiled to a deterministic, "
        "content-addressed brain_id and NOTARIZED on the fleet's own "
        "commit-reveal notary (state REVEALED = permanent, machine-checkable "
        "proof, N1/N2). Verify any row: rebuild the genome, `build_brain` it "
        "on /verdigraph/mcp (or locally), compare ids; check the commitment "
        "with `verify` on /notary/mcp.",
        "",
        "| mount | brain_id | content_hash | invariants | notary commitment | state |",
        "|---|---|---|---|---|---|",
    ]
    for mount, bid, digest, passed, total, cid, state in rows:
        lines.append(f"| {mount} | `{bid}` | `{digest[:16]}…` | "
                     f"{passed}/{total} | `{cid}` | {state} |")
    out.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {out} — {len(rows)} agents, {len(failures)} failures"
          + (f" ({', '.join(failures)})" if failures else ""))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
