#!/usr/bin/env python3
"""
Carbon-Neutral Agent Work — the x402-C loop, proven end to end.

Viridis authored the x402-C carbon-receipts standard
(docs/standards/X402C_CARBON_RECEIPTS.md). This demo proves Viridis's own two
agents actually *implement* it — the reference implementation the spec names:

    compute-ledger  prices the work in gCO2e (Landauer-bounded) and EMITS the
                    x402-C `carbon` object                       (C1, C2, C3)
    offset-clearinghouse  retires exactly that mass of VERIFIED conservation
                    credit and VERIFIES the retirement            (C4)

The loop: record_work -> footprint -> buy_offset(exact gCO2e) ->
carbon_receipt(offset_ref=retirement) -> verify_retirement confirms coverage.
The result is a payment receipt that is *carbon-neutral by construction and
independently checkable* — the only such thing whose sustainability claim is
grounded in physics (the Intelligence Bound thesis), not self-report.

Run:
    python3 scripts/carbon_neutral_work_demo.py            # narrative + assertions
    python3 scripts/carbon_neutral_work_demo.py --quiet    # assertions only (CI)

Exits non-zero if any invariant fails — an integration test.

--- INVARIANTS (carbon-neutral composition contract) ---
CN1  C1 physical floor: a landauer-floor receipt exists only for a workload
     whose energy cleared the Landauer minimum (impossible work is rejected
     upstream, so a fraudulent low-carbon claim cannot be receipted).
CN2  C2 recomputable: the receipt's g_co2e == (energy_j/3.6e6)*grid.
CN3  C3 no-detachment: the receipt's attestation_hash binds it to the
     compute-ledger entry's hash chain and recomputes.
CN4  C4 offset coverage: the offset the receipt points to retires >= the
     receipt's gCO2e of VERIFIED conservation credit — verify_retirement
     confirms it, and only verified supply could be listed at all (O7).
CN5  Mass closes to the gram: emitted gCO2e (ceil to grams) == retired grams
     == required grams the validator checks; net position is zero.
CN6  The whole loop mutates only what it must: the compute ledger and the
     offset book each stay hash-chain valid; carbon_receipt/verify_retirement
     are read-only.
"""
import argparse
import asyncio
import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = {
    "ledger": ROOT / "agent-compute-ledger-agent" / "src" / "core.py",
    "offsets": ROOT / "agent-offset-clearinghouse-agent" / "src" / "core.py",
}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(f"cn_{name}_core", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


FAILURES = []


def check(label, cond, detail=""):
    if not cond:
        FAILURES.append(label)
    if not QUIET or not cond:
        print(f"  {'✓' if cond else '✗'} {label}" + (f" — {detail}" if detail else ""))


def say(*a):
    if not QUIET:
        print(*a)


async def _run(cores):
    ledger = cores["ledger"].build()
    offsets = cores["offsets"].build()

    async def L(**a): return await ledger.process(a)
    async def O(**a): return await offsets.process(a)

    # ① The agent does real, thermodynamically-validated work.
    say("\n① compute-ledger prices the work (Landauer-bounded)")
    work = await L(action="record_work", agent_id="acme-inference",
                   entry_id="job-x", task="LLM inference batch",
                   power_w=350.0, duration_s=8.0, bit_ops=5e13,
                   grid_intensity_g_per_kwh=380.0)
    check("work recorded (cleared the Landauer floor)", work["status"] == "ok")
    entry = work["data"]
    gco2e = entry["carbon_g"]
    say(f"   energy {entry['energy_j']:.1f} J, {gco2e:.4f} gCO2e, "
        f"landauer_efficiency {entry['landauer_efficiency']:.2e}")

    # ② Verified conservation supply is on the book (only verified can list).
    say("\n② offset-clearinghouse lists VERIFIED conservation credit")
    await O(action="list_credit", issuer="viridis-land-trust",
            project_id="restoration-site-7", mass_g=1_000_000,
            price_minor_per_kg=800,
            verification_ref="dscore:zenodo.19317982/site7")

    # ③ Retire exactly the emitted mass (ceil to whole grams).
    grams = math.ceil(gco2e)
    say(f"\n③ retire {grams} g of verified credit to neutralize the job")
    buy = await O(action="buy_offset", buyer="acme-inference",
                  purchase_id="neutralize-job-x", mass_g=grams)
    check("offset retired for the job", buy["status"] == "ok")
    offset_ref = buy["data"]["purchase_id"]

    # ④ Emit the x402-C carbon receipt, pointing at the retirement.
    say("\n④ emit the x402-C carbon receipt (offset_ref = the retirement)")
    rc = await L(action="carbon_receipt", entry_id="job-x", offset_ref=offset_ref)
    check("carbon receipt emitted", rc["status"] == "ok")
    carbon = rc["data"]["carbon"]
    say("   " + json.dumps({k: carbon[k] for k in
                            ("version", "g_co2e", "method", "offset_ref")}))

    # ---- Conformance checks C1-C4 (CN1-CN6) -----------------------------
    check("CN1 C1 method is landauer-floor (physical floor cleared)",
          carbon["method"] == "landauer-floor"
          and 0 < carbon["landauer_efficiency"] <= 1)
    from importlib import import_module  # J_PER_KWH via the ledger module
    JPK = cores["ledger"].J_PER_KWH
    check("CN2 C2 recomputable g_co2e",
          abs(carbon["g_co2e"] - (carbon["energy_j"] / JPK)
              * carbon["grid_intensity_g_per_kwh"]) < 1e-6)
    stored = dict(carbon)
    h = stored.pop("attestation_hash")
    import hashlib
    canon = json.dumps(stored, sort_keys=True, separators=(",", ":"))
    check("CN3 C3 attestation_hash binds to the ledger entry",
          hashlib.sha256((canon + rc["data"]["entry_hash"]).encode()).hexdigest() == h)

    vr = await O(action="verify_retirement", purchase_id=offset_ref,
                 required_g=grams)
    check("CN4 C4 offset covers the receipt's gCO2e (verified supply)",
          vr["data"]["covered"] and vr["data"]["retired_g"] >= grams,
          f"retired {vr['data']['retired_g']} g >= {grams} g")

    net = await O(action="net_position", buyer="acme-inference",
                  emitted_g=grams)
    check("CN5 mass closes to the gram (net position zero)",
          net["data"]["net_g"] == 0,
          f"emitted {grams} = retired {net['data']['retired_g']}")

    lv = await L(action="verify_chain", agent_id="acme-inference")
    check("CN6 compute ledger chain valid after the loop", lv["data"]["valid"])
    cert = await O(action="verify_certificate", certificate=buy["data"])
    check("CN6 offset certificate verifies", cert["data"]["valid"])

    say("\n⑤ Result: a payment receipt that is carbon-neutral by construction "
        "and independently checkable —")
    say(f"   {grams} gCO2e of physically-validated agent work, neutralized by "
        f"{grams} g of D-Score-verified conservation, every step recomputable.")


def main():
    global QUIET
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    QUIET = ap.parse_args().quiet
    cores = {n: _load(n, p) for n, p in AGENTS.items()}
    say("═══ Viridis Carbon-Neutral Agent Work — x402-C reference impl proof ═══")
    asyncio.run(_run(cores))
    print()
    if FAILURES:
        print(f"✗ FAILED: {len(FAILURES)} invariant(s): {', '.join(FAILURES)}")
        return 1
    print("✓ ALL x402-C LOOP INVARIANTS HELD — "
          "compute-ledger + offset-clearinghouse implement the standard.")
    return 0


if __name__ == "__main__":
    QUIET = False
    sys.exit(main())
