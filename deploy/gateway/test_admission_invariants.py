#!/usr/bin/env python3
"""
AA1–AA7 — agent admission invariants, machine-checked (ratified 2026-07-18).

Every mount in the gateway MUST be discoverable (AA1), economically decided
(AA2), revenue-modeled (AA3), and present on every shipping surface (AA5,
AA7). This suite FAILS the fleet gate when someone mounts an agent without
its distribution/pricing wiring — admission doctrine as code, not memory.

Run:  pytest deploy/gateway/test_admission_invariants.py -q
"""
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import viridis_mcp_gateway as gateway                      # noqa: E402
from payment_gate import FREE_CALLS_BY_AGENT, PRICE_MINOR  # noqa: E402

MOUNTS = gateway.MOUNTS
AGENT_SEO = gateway.AGENT_SEO

# AA2: the ratified free rails — settlement/trust infrastructure that is
# free FOREVER by doctrine (tax transactions, never rails). Adding a mount
# to neither this set nor PRICE_MINOR fails the gate.
FREE_RAILS = {
    "identity":       "the passport: paid identity would tax every entry",
    "trust":          "reputation reads must be free to price risk",
    "escrow":         "settlement rail: taxing it taxes the tax",
    "metering":       "the fleet's own books must be free to audit",
    "arbitration":    "justice priced per filing (PB6 fee), not per read",
    "compute-ledger": "physics ledger: public by thesis",
    "covenant":       "safety leases must never be priced out",
    "provenance":     "genesis/lineage checks are trust infrastructure",
    "offsets":        "clearinghouse monetizes retirement, not lookup",
    "erc8004":        "interop bridge: adoption funnel",
    "surety":         "quotes free (price_bond); premiums are the revenue",
    "notary":         "delivery proofs underpin escrow: rails",
    "wavefunction":   "discovery funnel for the whole fleet",
    "viridisos":      "staging preview: verification and identity are free network rails",
}


def test_AA2_free_rails_and_priced_agents_partition_the_mounts():
    """Every mount is exactly one of: priced (gated) or declared free rail."""
    for mount in MOUNTS:
        priced = mount in PRICE_MINOR
        free = mount in FREE_RAILS
        assert priced != free, (
            f"AA2 violated: '{mount}' is "
            + ("BOTH priced and declared free"
               if priced and free else
               "NEITHER in PRICE_MINOR (gated) nor in FREE_RAILS "
               "(declared free) — make the economic decision explicit"))


def test_AA2_no_orphan_prices():
    """PRICE_MINOR names only real mounts (no ghost pricing)."""
    for name in PRICE_MINOR:
        assert name in MOUNTS or name == "signed-cliff-check", (
            f"AA2: PRICE_MINOR entry '{name}' has no mount or declared product surface")


def test_hive_price_and_no_loss_leader_match_owned_description():
    assert PRICE_MINOR["hive"] == 500
    assert FREE_CALLS_BY_AGENT["hive"] == 0


def test_AA1_every_mount_has_seo_entry():
    for mount in MOUNTS:
        assert mount in AGENT_SEO, (
            f"AA1 violated: '{mount}' missing AGENT_SEO — it is invisible "
            "to the ARD catalog and every registry that indexes it")


def test_AA1_seo_entries_are_complete_and_bounded():
    for mount, seo in AGENT_SEO.items():
        assert seo.get("desc") and len(seo["desc"]) <= 280, (
            f"AA1: '{mount}' desc missing or > 280 chars")
        queries = seo.get("queries") or []
        assert 2 <= len(queries) <= 5, (
            f"AA1: '{mount}' needs 2-5 intent queries, has {len(queries)}")


def test_AA3_every_root_agent_has_revenue_model_on_record():
    for mount, agent_dir in MOUNTS.items():
        yaml_path = ROOT / agent_dir / "agent.yaml"
        assert yaml_path.exists(), f"AA3: {agent_dir}/agent.yaml missing"
        text = yaml_path.read_text()
        assert "revenue_model" in text, (
            f"AA3: '{mount}' agent.yaml lacks revenue_model")
        assert "thesis_connection" in text, (
            f"AA3: '{mount}' agent.yaml lacks thesis_connection")


def test_AA5_deck_role_map_covers_every_mount():
    deck = (HERE / "deck.html").read_text()
    role_block = re.search(r"const ROLE = \{(.*?)\};", deck, re.S)
    assert role_block, "deck.html ROLE map not found"
    for mount in MOUNTS:
        assert (f'"{mount}"' in role_block.group(1)
                or f"{mount}:" in role_block.group(1)), (
            f"AA5: deck.html ROLE map missing '{mount}'")


def test_AA5_glama_bridge_role_map_covers_every_mount():
    bridge = (ROOT / "deploy" / "glama" / "fleet_bridge.py").read_text()
    for mount in MOUNTS:
        assert f'"{mount}"' in bridge, (
            f"AA5: glama fleet_bridge.py ROLE missing '{mount}'")


def test_AA5_glama_manifest_includes_every_mount():
    import json
    manifest = json.loads(
        (ROOT / "deploy" / "glama" / "fleet_manifest.json").read_text())
    for mount in MOUNTS:
        assert mount in manifest and manifest[mount], (
            f"AA5: fleet_manifest.json missing tools for '{mount}' — "
            "regenerate via scripts/generate_live_glama_manifest.py")


def test_AA5_dockerfile_copies_every_agent_dir():
    dockerfile = (HERE / "Dockerfile").read_text()
    for mount, agent_dir in MOUNTS.items():
        assert f"COPY {agent_dir}/" in dockerfile, (
            f"AA5: Dockerfile missing COPY for '{agent_dir}' — the gateway "
            "will crash-loop on deploy")


def test_AA7_quickstart_mentions_every_priced_agent_family():
    """Every PRICED mount is reachable from the quickstart (by name)."""
    quickstart = (ROOT / "docs" / "QUICKSTART_FIRST_CALL.md").read_text()
    for mount in PRICE_MINOR:
        assert mount in quickstart, (
            f"AA7: docs/QUICKSTART_FIRST_CALL.md never mentions priced "
            f"mount '{mount}' — the front porch doesn't know it exists")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
