#!/usr/bin/env python3
"""
A2A Economy Composition Demo — identity -> trust -> escrow, end to end.

Proves the three novel Viridis A2A primitives COMPOSE into a working market:
one agent discovers, vets, hires, and pays another agent — safely — with no
human in the loop and no trusted intermediary holding the relationship.

Run:
    python3 scripts/a2a_economy_demo.py            # narrative + assertions
    python3 scripts/a2a_economy_demo.py --quiet    # assertions only (CI mode)

Exits non-zero if any invariant fails, so this doubles as an integration test.

Design note: each agent core is self-contained and stdlib-only, so we load the
three `src/core.py` modules directly (under unique names to avoid the shared
`src.core` collision) and drive them through their real `process()` contract —
exactly how an MCP orchestrator would call them.
"""
import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = {
    "identity": ROOT / "agent-identity-registry-agent" / "src" / "core.py",
    "trust":    ROOT / "agent-trust-oracle-agent" / "src" / "core.py",
    "escrow":   ROOT / "agent-escrow-agent" / "src" / "core.py",
}


def _load(name: str, path: Path):
    """Load an agent core under a unique module name (avoids src.core collision)."""
    spec = importlib.util.spec_from_file_location(f"a2a_{name}_core", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


QUIET = False


def say(*a):
    if not QUIET:
        print(*a)


def check(cond, msg):
    if not cond:
        print(f"  ✗ INVARIANT FAILED: {msg}", file=sys.stderr)
        raise SystemExit(1)
    say(f"  ✓ {msg}")


async def main() -> int:
    identity = _load("identity", AGENTS["identity"]).build()
    trust = _load("trust", AGENTS["trust"]).build()
    escrow = _load("escrow", AGENTS["escrow"]).build()

    say("=" * 68)
    say("  VIRIDIS A2A ECONOMY — identity -> trust -> escrow, end to end")
    say("=" * 68)

    # ---------------------------------------------------------------- #
    # 0. Two agents exist: a buyer (orchestrator) and a CAD provider.
    # ---------------------------------------------------------------- #
    say("\n[1] IDENTITY — provider registers and advertises capabilities")
    reg = await identity.process({
        "action": "register", "agent_id": "cad-bot-7",
        "name": "ProtoGen CAD Bot", "pubkey": "pk_cadbot7",
        "capabilities": ["cad", "parametric", "step-export"],
        "pricing": {"per_brief_usd": 149}, "reputation_hint": 0.5,
    })
    check(reg["status"] == "ok", "provider registered")
    did = reg["data"]["did"]
    check(did.startswith("did:viridis:"), f"provider minted a DID: {did}")

    # a competitor with fewer capabilities, so discovery must discriminate
    await identity.process({
        "action": "register", "agent_id": "cad-bot-lite", "pubkey": "pk_lite",
        "capabilities": ["cad"], "reputation_hint": 0.9,
    })

    say("\n[2] DISCOVERY — buyer needs cad + step-export; registry AND-matches")
    disc = await identity.process({
        "action": "discover", "capabilities": ["cad", "step-export"]})
    ids = [r["agent_id"] for r in disc["data"]["results"]]
    check(ids == ["cad-bot-7"],
          f"only the fully-capable provider is returned (got {ids})")

    # ---------------------------------------------------------------- #
    # 1. Vet the provider BEFORE committing money.
    # ---------------------------------------------------------------- #
    say("\n[3] TRUST — buyer checks the provider's reputation (first contact)")
    t0 = await trust.process({"action": "score", "agent_id": "cad-bot-7"})
    check(t0["data"]["score"] == 0.5 and t0["data"]["tier"] == "NEUTRAL",
          "unknown provider gets a neutral 0.5 prior (no blind trust, no unfair 0)")

    # ---------------------------------------------------------------- #
    # 2. Hire safely via escrow: open -> fund -> deliver -> release.
    # ---------------------------------------------------------------- #
    say("\n[4] ESCROW — buyer opens escrow for a $149 CAD brief (1% fee)")
    op = await escrow.process({
        "action": "open", "payer": "buyer-orchestrator", "payee": "cad-bot-7",
        "amount_minor": 14900, "currency": "USD", "fee_bps": 100,
        "terms": "STEP file of bracket, tolerances per spec"})
    check(op["status"] == "ok", "escrow opened")
    eid = op["data"]["escrow_id"]
    check(op["data"]["fee_minor"] == 149 and op["data"]["net_to_payee_minor"] == 14751,
          "fee frozen at open: $1.49 platform, $147.51 net to provider")

    await escrow.process({"action": "fund", "escrow_id": eid, "payment_ref": "x402_tok_abc"})
    say("      ... provider delivers the STEP file, buyer verifies ...")
    rel = await escrow.process({
        "action": "release", "escrow_id": eid, "delivery_proof": "sha256:deadbeef"})
    check(rel["data"]["state"] == "RELEASED", "funds released to provider on delivery")

    aud = await escrow.process({"action": "verify_audit", "escrow_id": eid})
    check(aud["data"]["valid"] is True,
          f"escrow audit chain is intact ({aud['data']['entries']} tamper-evident entries)")

    # ---------------------------------------------------------------- #
    # 3. Outcome feeds back into reputation — the flywheel.
    # ---------------------------------------------------------------- #
    say("\n[5] TRUST FEEDBACK — successful settlement raises provider reputation")
    await trust.process({"action": "record_outcome", "agent_id": "cad-bot-7",
                         "kind": "delivered", "counterparty": "buyer-orchestrator"})
    t1 = await trust.process({"action": "score", "agent_id": "cad-bot-7"})
    check(t1["data"]["score"] > t0["data"]["score"],
          f"reputation rose {t0['data']['score']} -> {round(t1['data']['score'],3)} after a clean job")

    att = await trust.process({"action": "attest", "agent_id": "cad-bot-7", "claim": "settled-job"})
    ver = await trust.process({"action": "verify_attestation", "agent_id": "cad-bot-7",
                               "attestation_id": att["data"]["attestation_id"]})
    check(ver["data"]["valid"] is True, "buyer issues a verifiable trust attestation for the provider")

    # ---------------------------------------------------------------- #
    # 4. The unhappy path: a bad job disputes, refunds, and is punished.
    # ---------------------------------------------------------------- #
    say("\n[6] DISPUTE PATH — a second job fails: dispute -> refund -> reputation drops")
    op2 = await escrow.process({"action": "open", "payer": "buyer-orchestrator",
                                "payee": "cad-bot-7", "amount_minor": 14900})
    eid2 = op2["data"]["escrow_id"]
    await escrow.process({"action": "fund", "escrow_id": eid2})
    await escrow.process({"action": "dispute", "escrow_id": eid2, "reason": "wrong tolerances"})
    ref = await escrow.process({"action": "refund", "escrow_id": eid2, "reason": "arbiter: buyer"})
    check(ref["data"]["state"] == "REFUNDED", "disputed job refunds the buyer (no funds lost)")
    # exactly-once: cannot now release the refunded escrow
    bad = await escrow.process({"action": "release", "escrow_id": eid2})
    check(bad["status"] == "error", "double-spend blocked: cannot release a refunded escrow")

    await trust.process({"action": "record_outcome", "agent_id": "cad-bot-7", "kind": "dispute_lost"})
    t2 = await trust.process({"action": "score", "agent_id": "cad-bot-7"})
    check(t2["data"]["score"] < t1["data"]["score"],
          f"reputation fell {round(t1['data']['score'],3)} -> {round(t2['data']['score'],3)} after a lost dispute")

    say("\n" + "=" * 68)
    say("  RESULT: identity -> trust -> escrow composed end to end.")
    say("  An agent discovered, vetted, hired, paid, and re-rated another")
    say("  agent — safely, autonomously, with a full audit trail.")
    say("=" * 68)
    if QUIET:
        print("A2A composition demo: ALL INVARIANTS PASSED")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="assertions only (CI mode)")
    args = ap.parse_args()
    QUIET = args.quiet
    raise SystemExit(asyncio.run(main()))
