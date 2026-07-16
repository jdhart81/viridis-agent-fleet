#!/usr/bin/env python3
"""
Viridis Agent Stable — MCP Gateway (deployment round 1).

One process, twenty-two hosted MCP servers. Each agent's existing
adapters/mcp_server.py is loaded unmodified and mounted at the path its
registry manifest already declares:

    https://<host>/identity/mcp        agent-identity-registry-agent
    https://<host>/trust/mcp           agent-trust-oracle-agent
    https://<host>/escrow/mcp          agent-escrow-agent
    https://<host>/metering/mcp        agent-metering-agent
    https://<host>/arbitration/mcp     agent-arbitration-agent
    https://<host>/compute-ledger/mcp  agent-compute-ledger-agent
    https://<host>/covenant/mcp        agent-covenant-agent
    https://<host>/provenance/mcp      agent-provenance-agent
    https://<host>/offsets/mcp         agent-offset-clearinghouse-agent
    https://<host>/erc8004/mcp         agent-erc8004-bridge-agent
    https://<host>/surety/mcp          agent-surety-agent
    https://<host>/notary/mcp          agent-notary-agent
    https://<host>/wavefunction/mcp    wavefunction-search-agent
    https://<host>/smartscale/mcp      smartscale-agent
    https://<host>/protogen/mcp        protogen-agent
    https://<host>/regulatory-radar/mcp regulatory-radar-agent
    https://<host>/narrative-engine/mcp narrative-engine-agent
    https://<host>/taxcredit-engine/mcp taxcredit-engine-agent
    https://<host>/ghg-ledger/mcp       ghg-ledger-agent
    https://<host>/quantity-takeoff/mcp quantity-takeoff-agent
    https://<host>/disclosure-compiler/mcp disclosure-compiler-agent
    https://<host>/verified/mcp         agent-verified-relay-agent

Plus GET /healthz (fleet-wide health) and GET / (directory).

Run:
    pip install mcp uvicorn
    python3 deploy/gateway/viridis_mcp_gateway.py --port 8402

State note: cores are in-memory (stdlib-only by design). Durability is provided
by the gateway-level StateStore (state_store.py): every state-changing
process() call is persisted to SQLite before the result is returned
(durable-before-ack, invariants PS1-PS7), and state is restored at boot.
Production mounts a docker volume at /data; /healthz reports persistence
status and degrades if the store is unavailable.
"""
import argparse
import asyncio
import contextlib
import functools
import html
import importlib.util
import inspect
import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]

# mount path -> agent directory (paths match deploy/mcp-publish manifests)
MOUNTS = {
    "identity":         "agent-identity-registry-agent",
    "trust":            "agent-trust-oracle-agent",
    "escrow":           "agent-escrow-agent",
    "metering":         "agent-metering-agent",
    "arbitration":      "agent-arbitration-agent",
    "compute-ledger":   "agent-compute-ledger-agent",
    "covenant":         "agent-covenant-agent",
    "provenance":       "agent-provenance-agent",
    "offsets":          "agent-offset-clearinghouse-agent",
    "erc8004":          "agent-erc8004-bridge-agent",
    "surety":           "agent-surety-agent",
    "notary":           "agent-notary-agent",
    "wavefunction":     "wavefunction-search-agent",
    "smartscale":       "smartscale-agent",
    "protogen":         "protogen-agent",
    "regulatory-radar": "regulatory-radar-agent",
    "narrative-engine": "narrative-engine-agent",
    "taxcredit-engine": "taxcredit-engine-agent",
    "ghg-ledger":       "ghg-ledger-agent",
    "quantity-takeoff": "quantity-takeoff-agent",
    "disclosure-compiler": "disclosure-compiler-agent",
    "verified":         "agent-verified-relay-agent",
}

# Agent-discovery ("agent SEO") metadata for the ARD /.well-known/ai-catalog.json.
# description: <=280 chars, intent-matched. queries: the natural-language phrases a
# calling agent/LLM would search — these feed vector indexing on ARD registries, so
# they are the single biggest lever on how we get surfaced. 2-5 per agent.
AGENT_SEO = {
    "identity": {
        "desc": "Verifiable agent identity (content-addressed DIDs) + capability discovery — the passport and directory of the A2A economy.",
        "queries": ["How do I verify another AI agent's identity?",
                    "Register my agent and advertise its capabilities",
                    "Discover agents that provide a specific capability"]},
    "trust": {
        "desc": "Decay-weighted agent reputation + tamper-evident trust attestations for deciding whether to trust a counterparty agent.",
        "queries": ["What is this agent's reputation score?",
                    "Get a tamper-evident trust attestation for an agent",
                    "Should I trust this counterparty agent before transacting?"]},
    "escrow": {
        "desc": "Trustless escrow and settlement between agents with an exactly-once state machine and audit hash chain.",
        "queries": ["Hold funds in escrow between two agents until delivery",
                    "Trustless settlement for an agent-to-agent transaction",
                    "Release payment only when the job is proven complete"]},
    "metering": {
        "desc": "Usage metering and SLA accounting for agent services — the meter behind x402 pay-per-call billing.",
        "queries": ["Meter usage of my agent service per call",
                    "Account for SLA and usage for x402 billing",
                    "Track how many times my tool was invoked"]},
    "arbitration": {
        "desc": "Dispute-resolution oracle for agent escrows; adjudicates contested deliveries using evidence and trust signals.",
        "queries": ["Resolve a dispute over an agent escrow",
                    "Adjudicate a disagreement between two agents",
                    "Rule on a contested delivery using evidence"]},
    "compute-ledger": {
        "desc": "Compute-is-carbon cost/energy ledger for agent work, with Landauer-bound accounting of the energy an AI workload consumed.",
        "queries": ["Account for the energy and carbon cost of agent compute",
                    "Record a Landauer-bound compute entry",
                    "How much carbon did this AI workload cost?"]},
    "covenant": {
        "desc": "Deny-by-default, revocable authority leases that scope exactly what an autonomous agent is allowed to do.",
        "queries": ["Grant a scoped authority lease to an agent",
                    "Limit what an autonomous agent is allowed to do",
                    "Issue a revocable permission for an agent action"]},
    "provenance": {
        "desc": "Genesis certificates, agent lineage tracking, and cascading recalls across derived agents.",
        "queries": ["Issue a genesis certificate for a new agent",
                    "Trace an agent's lineage and recall history",
                    "Cascade a recall across derived agents"]},
    "offsets": {
        "desc": "Verified-credit carbon offset clearinghouse — purchase, verify, and retire carbon credits with proof of retirement.",
        "queries": ["Retire a verified carbon offset credit",
                    "Purchase and verify carbon offsets",
                    "Prove a carbon credit was retired"]},
    "erc8004": {
        "desc": "MCP-native bridge to ERC-8004 on-chain agent identity: resolve registrations, decay-weighted trust scoring over their feedback, DID bindings, unsigned attestation export. No keys, no chain writes.",
        "queries": ["Resolve an ERC-8004 agent identity from MCP",
                    "Score an on-chain agent's reputation feedback",
                    "Bind an ERC-8004 token to an agent DID",
                    "Export a trust attestation for on-chain anchoring"]},
    "surety": {
        "desc": "Counterparty risk transfer: agents post bonds behind promises; machine-verifiable arbitration rulings trigger slashing; honest agents reclaim stakes. The agent-economy surety bond.",
        "queries": ["Post a bond behind my agent's promises",
                    "File a claim against a bonded agent",
                    "Slash a bond with an arbitration ruling",
                    "Is this counterparty agent bonded?"]},
    "notary": {
        "desc": "Commit-reveal content notarization for verifiable delivery: commit to a deliverable's hash before handover, reveal after, verify exactly. Digests only — never raw content.",
        "queries": ["Notarize a deliverable before handover",
                    "Prove the delivered content matches what was promised",
                    "Create a cryptographic delivery proof for an escrow"]},
    "wavefunction": {
        "desc": "Demand-side discovery: distill ambiguous intentions into commitments and match them to constitutionally-aligned agents and collectives.",
        "queries": ["Find the right agent for this job",
                    "Match my intention to aligned agents",
                    "Register my collective for agent matchmaking"]},
    "smartscale": {
        "desc": "Credit-card-calibrated visual measurement — extract real-world object dimensions from a photo using a reference object. 10 free calls/day, then $0.50/call (credit packs via redeem_payment, or x402).",
        "queries": ["Measure the dimensions of an object from a photo",
                    "Estimate real-world size using a credit-card reference",
                    "Extract measurements from an image",
                    "Cheap pay-per-call measurement API for agents"]},
    "protogen": {
        "desc": "MCP CAD services — turn a spec or a measurement into a parametric CAD design; bundles with SmartScale (measure to CAD). 10 free calls/day, then $1.00/call (credit packs via redeem_payment, or x402).",
        "queries": ["Generate a CAD design from a spec",
                    "Turn a measurement into a CAD model",
                    "Create a parametric part design",
                    "Affordable pay-per-call CAD API for agents"]},
    "regulatory-radar": {
        "desc": "CSRD/TNFD climate-disclosure compliance-as-a-service — which sustainability regulation deadlines apply to a company.",
        "queries": ["What CSRD or TNFD deadlines apply to my company?",
                    "Check climate disclosure compliance requirements",
                    "Track sustainability regulation deadlines"]},
    "narrative-engine": {
        "desc": "Grant, investor, and policy narrative generation for conservation and climate work.",
        "queries": ["Draft a grant narrative for a conservation project",
                    "Generate investor or policy narrative content",
                    "Write a compelling environmental impact story"]},
    "taxcredit-engine": {
        "desc": "Auditable US clean-energy tax-credit scenario estimates for 45Q, 45V, 45Y, 48E, and 45X. Deterministic versioned IRS rule packs; 10 free calls/day, then $2/call.",
        "queries": ["Estimate the section 45V credit for a clean hydrogen project",
                    "Calculate 45Q carbon capture tax credits with PWA",
                    "Compare 45Y production credit and 48E investment credit",
                    "Calculate a 45X manufacturing production credit"]},
    "ghg-ledger": {
        "desc": "Auditable GHG inventory calculations with bundled, versioned emission factors; Scope 1/2/3 rollups, deterministic lineage, and 10 free calls/day then $1/inventory.",
        "queries": ["Calculate a Scope 1, 2, and 3 greenhouse gas inventory",
                    "Convert activity data into auditable CO2e totals",
                    "Calculate electricity emissions with bundled eGRID factors",
                    "Verify the audit hash of a GHG inventory result"]},
    "quantity-takeoff": {
        "desc": "Auditable construction material takeoffs from typed, SmartScale, or ProtoGen measurements; locked waste factors, conservative purchase rounding, and 10 free calls/day then $0.50/takeoff.",
        "queries": ["Calculate concrete, rebar, framing, drywall, roofing, masonry, steel, sitework, or paint quantities",
                    "Turn measured dimensions into an auditable material takeoff",
                    "Standardize construction waste factors across estimators",
                    "Verify the audit hash of a material takeoff"]},
    "disclosure-compiler": {
        "desc": "Deterministic, cited, gap-flagged disclosure drafts for ESRS E1, SEC climate, IFRS S2, and TNFD; 10 free calls/day then $2/draft.",
        "queries": ["Compile an ESRS E1 disclosure draft from a verified GHG inventory",
                    "Create a cited IFRS S2 or SEC climate disclosure draft",
                    "Find missing climate disclosure datapoints before professional review",
                    "Verify the audit hash of a compliance disclosure draft"]},
    "verified": {
        "desc": "Viridis Verified: relay any MCP server's tool calls through "
                "tamper-evident delivery receipts — request/response hashes, "
                "outcome, latency — metered per call and dispute-ready. "
                "10 free calls/day then $0.02/call.",
        "queries": ["Prove what an AI agent's tool call actually returned",
                    "Get a tamper-evident receipt for an MCP tool call",
                    "Wrap a third-party MCP server with delivery verification",
                    "Audit evidence for a disputed agent-to-agent transaction"]},
}


# Federated fleet members that run on their OWN infrastructure (separate droplet,
# repo, domain) but are part of the Viridis fleet for discovery. Surfaced in the
# gateway directory and the ARD catalog so a caller finds the whole fleet in one
# place, even though these agents are hosted elsewhere.
EXTERNAL_MEMBERS = [
    {
        "identifier": "urn:air:viridis:energyai",
        "displayName": "EnergyAI",
        "url": "https://api.energyaisolution.com/mcp",
        "description": ("Energy intelligence for AI agents — solar production estimates, "
                        "US clean-energy incentives by ZIP, home Energy Node Scores, and "
                        "consented installer routing. Free tools + paid $19 roadmap (Stripe)."),
        "capabilities": ["check_incentives", "estimate_production", "get_energy_node_score",
                         "create_energy_assessment", "generate_energy_recommendation_preview",
                         "create_energy_node_roadmap_checkout", "match_installers",
                         "review_installer_quote", "generate_intelligence_bound_report"],
        "representativeQueries": [
            "What solar incentives and rebates apply to my ZIP code?",
            "Estimate annual solar production for my home",
            "Score my home's energy-node potential and get a roadmap"],
        "version": "1.0.0",
        "infra": "own droplet energyai-prod + energyaisolution.com (Cloudflare/Caddy)",
    },
]


def _load_adapter(path: str, agent_dir: str):
    """Load an agent's adapter module in isolation.

    Every adapter does `sys.path.insert(0, <its root>)` and imports `src.core`.
    Between loads we evict all `src*` modules and put the agent's root at the
    front of sys.path, so each adapter binds to ITS OWN core.
    """
    for mod in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[mod]
    agent_root = str(ROOT / agent_dir)
    while agent_root in sys.path:
        sys.path.remove(agent_root)
    sys.path.insert(0, agent_root)
    spec = importlib.util.spec_from_file_location(
        f"gateway_adapter_{path.replace('-', '_')}",
        ROOT / agent_dir / "adapters" / "mcp_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _is_sha256(value) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(ch in "0123456789abcdef" for ch in value))


def _ghg_source_ids(data: dict, factor_pack: dict) -> list:
    """Collect the source IDs actually cited by a calculated inventory."""
    found = []

    def collect(container):
        if not isinstance(container, dict):
            return
        for key in ("source_ids", "sources_used"):
            values = container.get(key, [])
            if isinstance(values, list):
                for value in values:
                    source_id = value.get("id") if isinstance(value, dict) else value
                    if isinstance(source_id, str) and source_id and source_id not in found:
                        found.append(source_id)
        values = container.get("sources", [])
        if isinstance(values, list):
            for value in values:
                source_id = value.get("id") if isinstance(value, dict) else value
                if isinstance(source_id, str) and source_id and source_id not in found:
                    found.append(source_id)

    collect(data)
    collect(factor_pack)
    for entry in data.get("entries", []):
        collect(entry)
        collect(entry.get("factor", {}) if isinstance(entry, dict) else {})
    return found


async def _call_core(core, payload: dict) -> dict:
    result = core.process(payload)
    return await result if inspect.isawaitable(result) else result


def _run_coro_blocking(coro):
    """Run a composition coroutine from a sync core, including on a live loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    outcome = {}

    def runner():
        try:
            outcome["result"] = asyncio.run(coro)
        except BaseException as exc:  # re-raised on the caller thread
            outcome["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome["result"]


def _rail_error(error_type: str, message: str) -> dict:
    return {"status": "error", "error_type": error_type,
            "message": str(message)[:300]}


def _rail_status(response: dict) -> dict:
    if not isinstance(response, dict):
        return _rail_error("invalid_rail_response", "rail returned a non-object")
    if response.get("status") != "ok":
        failed = _rail_error(
            str(response.get("error_type", "rail_rejected")),
            str(response.get("message", "rail rejected the post")))
        # Preserve structured conflict context from a rail. In particular,
        # ConflictError duplicate-ID responses must remain visibly failed;
        # only canonical idempotent replays return status=ok from the rails.
        for key in ("field", "value", "constraint"):
            if key in response:
                failed[key] = response[key]
        return failed
    data = response.get("data")
    return {"status": "ok", **(data if isinstance(data, dict) else {})}


async def _compose_ghg_result(result: dict, compute_core, provenance_core) -> dict:
    """Post a successful inventory to both free rails without changing its hash.

    rail_posts is deliberately top-level derived metadata. The GHG result's
    hashed data object remains byte-for-byte untouched, so verify_result can
    recompute audit_sha256 exactly.
    """
    derived = dict(result)
    try:
        data = result.get("data")
        if not isinstance(data, dict):
            raise ValueError("successful calculation did not return a data object")
        audit_sha256 = data.get("audit_sha256")
        input_sha256 = data.get("input_sha256", "")
        factor_pack = data.get("factor_pack")
        if not _is_sha256(audit_sha256):
            raise ValueError("audit_sha256 is missing or invalid")
        if input_sha256 and not _is_sha256(input_sha256):
            raise ValueError("input_sha256 is invalid")
        if not isinstance(factor_pack, dict):
            raise ValueError("factor_pack lineage is missing")
        pack_version = factor_pack.get("version") or factor_pack.get("pack_version")
        pack_digest = (factor_pack.get("sha256")
                       or factor_pack.get("digest")
                       or factor_pack.get("factor_pack_sha256"))
        if not isinstance(pack_version, str) or not pack_version:
            raise ValueError("factor_pack version is missing")
        if not _is_sha256(pack_digest):
            raise ValueError("factor_pack digest is missing or invalid")

        grand_total = data.get("grand_total")
        if not isinstance(grand_total, dict):
            raise ValueError("grand_total lineage is missing")
        mass_g = grand_total.get("mass_g")
        if isinstance(mass_g, bool) or not isinstance(mass_g, int) or mass_g < 0:
            raise ValueError("grand_total.mass_g must be an exact non-negative integer")
        record_id = f"ghg-{audit_sha256[:24]}"
        source_ids = _ghg_source_ids(data, factor_pack)

        compute_payload = {
            "action": "record_inventory",
            "agent_id": "ghg-ledger-agent",
            "inventory_id": record_id,
            "mass_g": mass_g,
            "content_digest": audit_sha256,
            "factor_pack_version": pack_version,
            "factor_pack_digest": pack_digest,
            "source_ids": source_ids,
        }
        provenance_payload = {
            "action": "register_artifact",
            "artifact_id": record_id,
            "artifact_hash": audit_sha256,
            "producer_agent_id": "ghg-ledger-agent",
            "parent_hashes": [pack_digest],
            "relation": "calculated_from",
            "metadata_digest": input_sha256,
        }

        posts = {}
        try:
            posts["compute_ledger"] = _rail_status(
                await _call_core(compute_core, compute_payload))
        except Exception as exc:
            posts["compute_ledger"] = _rail_error(
                f"{type(exc).__name__}", exc)
        try:
            posts["provenance"] = _rail_status(
                await _call_core(provenance_core, provenance_payload))
        except Exception as exc:
            posts["provenance"] = _rail_error(
                f"{type(exc).__name__}", exc)
        derived["rail_posts"] = posts
    except Exception as exc:
        error = _rail_error("composition_input_invalid", exc)
        derived["rail_posts"] = {
            "compute_ledger": dict(error),
            "provenance": dict(error),
        }
    return derived


def _attach_ghg_rail_composition(ghg_core, compute_core, provenance_core) -> None:
    """Wrap calculate_inventory after persistence and before PaymentGate."""
    inner = ghg_core.process

    def should_compose(payload, result) -> bool:
        return (isinstance(payload, dict)
                and payload.get("action") == "calculate_inventory"
                and isinstance(result, dict)
                and result.get("status") == "ok")

    if inspect.iscoroutinefunction(inner):
        @functools.wraps(inner)
        async def process(input_data):
            result = await inner(input_data)
            if should_compose(input_data, result):
                return await _compose_ghg_result(
                    result, compute_core, provenance_core)
            return result
    else:
        @functools.wraps(inner)
        def process(input_data):
            result = inner(input_data)
            if should_compose(input_data, result):
                return _run_coro_blocking(_compose_ghg_result(
                    result, compute_core, provenance_core))
            return result

    ghg_core.process = process


class _StripeSubscriptionProvider:
    """Narrow adapter from subscriptions-core to the existing Stripe rail.

    The rail owns all secret-key access and fixed-host HTTP. This object only
    translates structured envelopes; it never reads, stores, logs, or returns
    a Stripe secret.
    """

    def __init__(self, public_base: str = "https://mcp.viridisconservation.com"):
        # The base is deployment configuration, never request input. Stripe
        # owns every payment screen; these are only the trusted return URLs.
        self.public_base = str(public_base).rstrip("/")

    @staticmethod
    def _require_ok(response: dict, operation: str) -> dict:
        if not isinstance(response, dict) or response.get("status") != "ok":
            error_type = (response.get("error_type", "stripe_error")
                          if isinstance(response, dict) else "invalid_response")
            raise RuntimeError(f"{operation} failed: {error_type}")
        return response

    def create_subscription_checkout(self, *, price_id: str, plan_id: str,
                                     account_ref: str, catalog_version: str,
                                     catalog_sha256: str, **_ignored) -> dict:
        import stripe_payments
        return self._require_ok(stripe_payments.create_subscription_checkout(
            price_id, plan_id, account_ref,
            catalog_version=catalog_version,
            catalog_sha256=catalog_sha256,
            success_url=(self.public_base +
                         "/seats/success?session_id={CHECKOUT_SESSION_ID}"),
            cancel_url=self.public_base + "/seats"),
            "subscription checkout")

    def create_customer_portal(self, *, customer_id: str, **_ignored) -> dict:
        import stripe_payments
        return self._require_ok(
            stripe_payments.create_customer_portal(
                customer_id, return_url=self.public_base + "/seats"),
            "customer portal")

    def verify_subscription(self, reference: str) -> dict:
        import stripe_payments
        return dict(self._require_ok(
            stripe_payments.verify_subscription(reference),
            "subscription verification"))


def _attach_subscription_bearer(subscription_core, account_key_getter) -> None:
    """Inject request-local ownership proof into sensitive subscription reads.

    The public MCP schema accepts account_id only. A caller cannot smuggle a
    key through JSON; any supplied account_key is overwritten by the bearer
    extracted by AccountContextMiddleware. Read-only catalog and aggregate MRR
    actions remain open.
    """
    inner = subscription_core.process
    sensitive = frozenset({
        "subscription_status", "usage_summary", "customer_portal_link"})

    @functools.wraps(inner)
    async def process(input_data):
        payload = dict(input_data) if isinstance(input_data, dict) else input_data
        if isinstance(payload, dict) and payload.get("action") in sensitive:
            payload.pop("account_key", None)
            payload["account_key"] = account_key_getter()
        result = inner(payload)
        return await result if inspect.isawaitable(result) else result

    subscription_core.process = process


_SEAT_PLAN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_SEAT_SESSION_RE = re.compile(r"^cs_[A-Za-z0-9_]+$")
_SEAT_ACCOUNT_RE = re.compile(r"^acct_[A-Za-z0-9_-]{1,64}$")
_SEAT_SECURITY_HEADERS = {
    "Cache-Control": "no-store, private",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-Robots-Tag": "noindex, nofollow",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; "
        "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"),
}
_SEAT_PUBLIC_HEADERS = {
    key: value for key, value in _SEAT_SECURITY_HEADERS.items()
    if key != "X-Robots-Tag"
}


def _seat_pledge_percent(value=None) -> Decimal:
    """Parse the public conservation pledge without ever overstating it."""
    raw = (os.environ.get("SEAT_CONSERVATION_PLEDGE_PERCENT", "0")
           if value is None else value)
    try:
        parsed = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    if not parsed.is_finite() or parsed < 0 or parsed > 100:
        return Decimal("0")
    return parsed


def _seat_percent_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _seat_conservation_line(value: Decimal) -> str:
    percent = _seat_percent_text(value)
    return (f"{percent}% of your subscription funds are pledged for verified "
            "conservation. Offset routing is not yet active, so this is a "
            "pledge — not a claim that offsets have been retired.")


def _seat_money(minor, currency: str) -> str:
    if isinstance(minor, bool) or not isinstance(minor, int) or minor < 0:
        raise ValueError("catalog price_minor must be a non-negative integer")
    amount = Decimal(minor) / Decimal(100)
    code = str(currency).lower()
    if code == "usd":
        return "$" + format(amount, ".2f")
    return f"{format(amount, '.2f')} {code.upper()}"


def _seat_single_query(request, name: str):
    values = request.query_params.getlist(name)
    return values[0] if len(values) == 1 else None


def _seat_valid_email(value) -> bool:
    if not isinstance(value, str) or not (3 <= len(value) <= 200):
        return False
    if value != value.strip() or any(ord(ch) < 33 for ch in value):
        return False
    if value.count("@") != 1:
        return False
    local, domain = value.rsplit("@", 1)
    return bool(local and "." in domain and not domain.startswith(".")
                and not domain.endswith("."))


def _seat_hosted_url(value, hostname: str):
    if not isinstance(value, str) or len(value) > 2048:
        return None
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError:
        return None
    if (parsed.scheme != "https" or parsed.hostname != hostname
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443)):
        return None
    return value


def _seat_error_page(message: str) -> str:
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Viridis seats</title><style>body{font:16px system-ui;"
            "max-width:720px;margin:10vh auto;padding:24px;color:#18352b}"
            "a{color:#14694c}</style></head><body><h1>We couldn’t open that "
            "seat</h1><p>" + html.escape(message) + "</p><p><a href='/seats'>"
            "Return to seat plans</a></p></body></html>")


async def _seat_core_action(subscription_core, payload: dict) -> dict:
    result = subscription_core.process(payload)
    return await result if inspect.isawaitable(result) else result


def _build_seat_routes(subscription_core, *, public_base: str,
                       template_html: str, pledge_percent=None):
    """Build the four thin human routes over the subscription core.

    The routes never accept card fields or Stripe credentials. They can only
    render catalog data or redirect to a core-validated Stripe hosted URL.
    """
    from starlette.responses import HTMLResponse, RedirectResponse
    from starlette.routing import Route

    pledge = _seat_pledge_percent(pledge_percent)
    conservation_line = _seat_conservation_line(pledge)

    def response(body: str, status_code: int = 200):
        return HTMLResponse(body, status_code=status_code,
                            headers=dict(_SEAT_SECURITY_HEADERS))

    def public_response(body: str):
        # The pricing landing page is intentionally discoverable; only the
        # account/session-bearing routes carry noindex.
        return HTMLResponse(body, headers=dict(_SEAT_PUBLIC_HEADERS))

    def redirect(url: str):
        return RedirectResponse(url, status_code=302,
                                headers=dict(_SEAT_SECURITY_HEADERS))

    def render_catalog(catalog: dict) -> str:
        plans = catalog.get("plans")
        currency = catalog.get("currency")
        if (not isinstance(plans, list) or not plans
                or not isinstance(currency, str)):
            raise ValueError("catalog response is incomplete")
        cards = []
        for plan in plans:
            if not isinstance(plan, dict):
                raise ValueError("catalog plan is invalid")
            plan_id = plan.get("id")
            name = plan.get("name")
            agents = plan.get("covered_agents")
            quota = plan.get("included_calls_per_month")
            if (not isinstance(plan_id, str) or not _SEAT_PLAN_RE.fullmatch(plan_id)
                    or not isinstance(name, str) or not name
                    or not isinstance(agents, list)
                    or any(not isinstance(agent, str) for agent in agents)
                    or isinstance(quota, bool) or not isinstance(quota, int)
                    or quota <= 0):
                raise ValueError("catalog plan is invalid")
            price = _seat_money(plan.get("price_minor"), currency)
            coverage = "".join(
                f"<li><code>{html.escape(agent)}</code></li>" for agent in agents)
            ready = (plan.get("checkout_status") == "ready"
                     and plan.get("configuration_required") is False)
            if ready:
                control = (
                    '<form class="checkout" action="/seats/checkout" method="get">'
                    f'<input type="hidden" name="plan" value="{html.escape(plan_id)}">'
                    '<label>Email <input type="email" name="email" maxlength="200" '
                    'autocomplete="email" required placeholder="you@company.com"></label>'
                    '<button type="submit">Continue to Stripe</button></form>')
                state = "Available now"
                classes = "plan-card buyable"
            else:
                control = ('<div class="coming configuration-required">'
                           'Coming soon — notify me</div>')
                state = "Checkout configuration pending"
                classes = "plan-card"
            cards.append(
                f'<article class="{classes}">'
                f"<p class='eyebrow'>{html.escape(state)}</p>"
                f"<h2>{html.escape(name)}</h2>"
                f"<p class='price'>{html.escape(price)}<small>/month</small></p>"
                f"<p class='quota'>{quota:,} included inventory or calculation calls each month; "
                "overage follows the live per-call rate.</p>"
                f"<p class='covered'>Covered tools:</p><ul>{coverage}</ul>"
                f"{control}</article>")
        required = ("{{PLAN_CARDS}}", "{{CATALOG_META}}",
                    "{{CONSERVATION_LINE}}")
        if any(marker not in template_html for marker in required):
            raise ValueError("seat template is incomplete")
        catalog_meta = (f"Catalog v{html.escape(str(catalog.get('pack_version', '')))}"
                        f" · {html.escape(str(catalog.get('plan_catalog_sha256', ''))[:12])}")
        return (template_html.replace("{{PLAN_CARDS}}", "".join(cards))
                .replace("{{CATALOG_META}}", catalog_meta)
                .replace("{{CONSERVATION_LINE}}",
                         html.escape(conservation_line)))

    async def seats(request):
        view = await _seat_core_action(
            subscription_core, {"action": "record_frontdoor_view"})
        if not isinstance(view, dict) or view.get("status") != "ok":
            return response(_seat_error_page(
                "Seat plans are temporarily unavailable. Please try again."), 503)
        listed = await _seat_core_action(
            subscription_core, {"action": "list_plans"})
        if not isinstance(listed, dict) or listed.get("status") != "ok":
            return response(_seat_error_page(
                "Seat plans are temporarily unavailable. Please try again."), 503)
        try:
            body = render_catalog(listed.get("data", {}))
        except Exception:
            return response(_seat_error_page(
                "Seat plans are temporarily unavailable. Please try again."), 503)
        return public_response(body)

    async def checkout(request):
        plan_id = _seat_single_query(request, "plan")
        email = _seat_single_query(request, "email")
        if (not isinstance(plan_id, str)
                or not _SEAT_PLAN_RE.fullmatch(plan_id)
                or not _seat_valid_email(email)):
            return response(_seat_error_page(
                "Choose a listed plan and enter a valid business email."), 400)
        result = await _seat_core_action(subscription_core, {
            "action": "create_checkout_link", "plan_id": plan_id,
            "account_ref": email})
        if not isinstance(result, dict) or result.get("status") != "ok":
            configuration = (isinstance(result, dict)
                             and result.get("error_type") ==
                             "configuration_required")
            message = ("This plan is coming soon; Checkout is not configured yet."
                       if configuration else
                       "Stripe Checkout is temporarily unavailable. No charge was made.")
            return response(_seat_error_page(message), 409 if configuration else 503)
        url = _seat_hosted_url(
            (result.get("data") or {}).get("checkout_url"),
            "checkout.stripe.com")
        if url is None:
            return response(_seat_error_page(
                "Stripe Checkout is temporarily unavailable. No charge was made."), 503)
        return redirect(url)

    async def success(request):
        session_id = _seat_single_query(request, "session_id")
        if (not isinstance(session_id, str)
                or not _SEAT_SESSION_RE.fullmatch(session_id)
                or len(session_id) > 255):
            return response(_seat_error_page(
                "The Checkout confirmation is missing or invalid."), 400)
        result = await _seat_core_action(subscription_core, {
            "action": "record_subscription", "stripe_reference": session_id})
        if not isinstance(result, dict) or result.get("status") != "ok":
            return response(_seat_error_page(
                "We could not verify this subscription yet. No access was granted; "
                "please retry shortly."), 503)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        account_id = data.get("account_id")
        account_key = data.get("account_key")
        replay = data.get("idempotent_replay") is True
        portal_url = None
        if isinstance(account_key, str) and account_key:
            # The key stays request-local. The portal link contains no bearer.
            try:
                from account_auth import account_key_context
                with account_key_context(account_key):
                    portal = await _seat_core_action(subscription_core, {
                        "action": "customer_portal_link",
                        "account_id": account_id})
                if isinstance(portal, dict) and portal.get("status") == "ok":
                    portal_url = _seat_hosted_url(
                        (portal.get("data") or {}).get("portal_url"),
                        "billing.stripe.com")
            except Exception:
                portal_url = None

        if isinstance(account_key, str) and account_key:
            key_block = (
                "<p>Save this account key now. It is shown exactly once and is "
                "your Bearer token for covered agent calls.</p>"
                f"<pre>{html.escape(account_key)}</pre>")
        else:
            key_block = (
                "<p>This subscription was already activated. Your account key "
                "is not shown again. Use the key you saved on first activation.</p>")
        portal_block = (f"<p><a href='{html.escape(portal_url)}'>Manage subscription "
                        "on Stripe</a></p>" if portal_url else
                        "<p>Subscription management is temporarily unavailable. "
                        "Your verified seat remains active.</p>")
        status_note = "Activation replay verified." if replay else "Seat activated."
        body = (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Seat activated · Viridis</title><style>body{font:16px system-ui;"
            "max-width:760px;margin:8vh auto;padding:24px;color:#18352b}pre{padding:18px;"
            "background:#e9f6ef;overflow-wrap:anywhere;white-space:pre-wrap}a{color:#14694c}"
            "</style></head><body><p>Viridis Conservation</p><h1>Subscription "
            "confirmed</h1>"
            f"<p>{html.escape(status_note)}</p>{key_block}{portal_block}"
            f"<p>{html.escape(conservation_line)}</p>"
            "<p><a href='/seats'>View seat plans</a></p></body></html>")
        return response(body)

    async def manage(request):
        account_id = _seat_single_query(request, "account")
        if (not isinstance(account_id, str)
                or not _SEAT_ACCOUNT_RE.fullmatch(account_id)):
            return response(_seat_error_page(
                "A valid account and Authorization Bearer token are required."), 400)
        result = await _seat_core_action(subscription_core, {
            "action": "customer_portal_link", "account_id": account_id})
        if not isinstance(result, dict) or result.get("status") != "ok":
            return response(_seat_error_page(
                "We could not verify this account. Send your saved account key "
                "as the Authorization Bearer token and try again."), 401)
        url = _seat_hosted_url(
            (result.get("data") or {}).get("portal_url"),
            "billing.stripe.com")
        if url is None:
            return response(_seat_error_page(
                "Stripe subscription management is temporarily unavailable."), 503)
        return redirect(url)

    return [Route("/seats", seats, methods=["GET"]),
            Route("/seats/checkout", checkout, methods=["GET"]),
            Route("/seats/success", success, methods=["GET"]),
            Route("/seats/manage", manage, methods=["GET"])]


def build_app():
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    public_base = os.environ.get(
        "PUBLIC_BASE", "https://mcp.viridisconservation.com").rstrip("/")

    adapters = {}
    src_modules = {}
    for path, agent_dir in MOUNTS.items():
        adapters[path] = _load_adapter(path, agent_dir)
        # PS8: capture this agent's src modules BEFORE the next load evicts
        # them — its pickled classes must (de)serialize against these.
        src_modules[path] = {m: sys.modules[m] for m in list(sys.modules)
                             if m == "src" or m.startswith("src.")}
    servers = {path: mod.mcp for path, mod in adapters.items()}
    cores = {path: mod.agent for path, mod in adapters.items()}

    # Subscriptions is fleet revenue infrastructure, not a twenty-second leaf
    # agent. It is mounted and persisted separately so /healthz agents remains
    # the production-coherent count of 22.
    subscription_adapter = _load_adapter("subscriptions", "subscriptions-agent")
    subscription_src_modules = {
        module: sys.modules[module] for module in list(sys.modules)
        if module == "src" or module.startswith("src.")}
    subscription_core = subscription_adapter.agent
    subscription_core.config.stripe_provider = _StripeSubscriptionProvider(
        public_base)
    servers["subscriptions"] = subscription_adapter.mcp

    # Persistence (PS1-PS8, see state_store.py): restore each core's state
    # from the last snapshot, then wrap process() so every state change is
    # durable before the caller sees the result. StateStore never raises into
    # a tool call; if it is unavailable, /healthz reports degraded.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from state_store import StateStore
    from account_auth import current_account_key
    store = StateStore.open_default()
    for path, core in cores.items():
        store.register_modules(path, src_modules[path])
        store.restore(path, core)
        store.attach(path, core)
    store.register_modules("subscriptions", subscription_src_modules)
    store.restore("subscriptions", subscription_core)
    # A first-time account key is acknowledged only after the verified
    # activation snapshot is committed. The core rolls every activation/index
    # mutation back if this writer fails, so a retry can safely issue the key.
    subscription_core.config.durable_activation_commit = (
        lambda: store.save("subscriptions", subscription_core))
    _attach_subscription_bearer(subscription_core, current_account_key)
    store.attach("subscriptions", subscription_core)

    # Successful GHG inventories compose into the free rails before the paid
    # gate wraps calculate_inventory. IDs are audit-derived, so retries are
    # idempotent in both ledgers. Rail failures stay explicit in rail_posts
    # but never corrupt or replace the deterministic inventory result.
    _attach_ghg_rail_composition(
        cores["ghg-ledger"], cores["compute-ledger"], cores["provenance"])

    # Freemium x402 gate (PG1-PG11, see payment_gate.py): sellable
    # services stay "free to call today" (FREE_CALLS_PER_DAY, default 10),
    # then return a payment_required envelope with Stripe + x402 paths.
    # Every call is metered on the fleet's OWN metering agent — daily
    # invoices of real usage. Trust and settlement rails are never gated (PG6).
    from payment_gate import PaymentGate
    gate = PaymentGate(
        store, cores["metering"], subscription_core=subscription_core,
        account_key_getter=current_account_key,
        # PG13-PG16: the a2a rail — payment_ref=<escrow_id> on a gated call
        # verifies + consumes a FUNDED escrow (payee viridis:<name>) for
        # prepaid credits through escrow's own E6 exactly-once machinery.
        # Internal-ledger settlement only (PG17 deferred): not cash.
        escrow_core=cores["escrow"], escrow_persist_key="escrow")
    for path in ("smartscale", "protogen", "taxcredit-engine", "ghg-ledger",
                 "quantity-takeoff", "disclosure-compiler",
                 "narrative-engine", "regulatory-radar", "verified"):
        if path in cores:
            gate.attach(path, cores[path])

    # stateless_http: no session persistence needed for these tools; makes the
    # endpoints trivially load-balancer-friendly.
    # Round-1 posture: endpoints are open. The MCP streamable-http default
    # DNS-rebinding guard only trusts localhost and 421s real callers, so we
    # accept any Host — the gateway must work behind fly.dev and
    # mcp.viridis.earth. (Auth/allowlist attaches before money moves.)
    _sec = None
    try:
        from mcp.server.transport_security import TransportSecuritySettings
        _sec = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
            allowed_hosts=["*"], allowed_origins=["*"])
    except Exception:
        _sec = None
    for s in servers.values():
        s.settings.stateless_http = True
        if _sec is not None:
            try:
                s.settings.transport_security = _sec
            except Exception:
                pass

    # Human-payment rail: a create_payment MCP tool (Stripe Checkout), mounted at
    # /payments/mcp. A2A agents settle via x402; this serves the *human*
    # customers of the revenue agents (SmartScale / ProtoGen / tax credit / GHG /
    # quantity takeoff).
    # Reads STRIPE_API_KEY from the container env; degrades to a structured error
    # (never a crash) when the key is absent.
    try:
        import stripe_payments
        from mcp.server.fastmcp import FastMCP
        pay = FastMCP("payments")

        @pay.tool()
        async def create_payment(amount_cents: int, product_name: str,
                                 currency: str = "usd") -> dict:
            """Create a Stripe Checkout URL for a human customer to pay for a
            Viridis service. Returns {status:"ok", url, session_id, livemode} or a
            structured error envelope (e.g. no_api_key, bad_amount)."""
            return stripe_payments.create_checkout(
                amount_cents, product_name, currency=currency)

        @pay.tool()
        def redeem_payment(session_id: str, agent: str) -> dict:
            """Redeem a PAID Stripe Checkout session (from create_payment) for
            prepaid call credits on any gated revenue agent.
            Pull-verified against Stripe; idempotent on session_id; credits =
            floor(amount_paid / per-call price) and apply instantly, 1 credit
            per call after the daily free tier. This closes the payment loop:
            pay -> redeem -> call."""
            return gate.redeem(session_id, agent)

        @pay.tool()
        async def reconcile_revenue(admin_token: str, days: int = 30) -> dict:
            """Admin: reconcile the fleet's usage ledger against Stripe
            settled cash (read-only, G10/RV1-RV5). Reports gross usage value,
            frozen daily invoices, redeemed sessions, Stripe live-mode settled
            total, and explicit discrepancies (paid-not-redeemed, etc.).
            Requires the server's VIRIDIS_ADMIN_TOKEN."""
            import hmac as _hmac
            expected = os.environ.get("VIRIDIS_ADMIN_TOKEN", "")
            if not expected or not isinstance(admin_token, str) \
                    or not _hmac.compare_digest(admin_token, expected):
                return {"status": "error", "error_type": "unauthorized",
                        "message": "valid admin_token required "
                                   "(VIRIDIS_ADMIN_TOKEN)"}
            import reconciliation
            return await reconciliation.build_report(
                cores["metering"], gate, days=days)

        @pay.tool()
        async def underwrite_service_bond(service_id: str, coverage_minor: int,
                                          duration_days: int = 30) -> dict:
            """Price a surety bond behind a Viridis Verified provider from its
            tamper-evident delivery track record (composition: Verified
            receipts -> surety underwriter uw-v1). Read-only, deterministic;
            the returned quote carries a recomputable quote_hash. A provider
            with more proven successful relays gets a lower premium; one with
            no track record prices at the unknown-counterparty rate (or is
            declined). This is a quote, not a bound policy."""
            if "verified" not in cores or "surety" not in cores:
                return {"status": "error", "error_type": "unavailable",
                        "message": "verified and surety mounts are required"}
            import underwriting_bridge
            return await underwriting_bridge.quote_bond_for_service(
                cores["verified"], cores["surety"], service_id,
                coverage_minor, duration_days)

        @pay.tool()
        async def quote_insured_job(service_id: str, job_amount_minor: int,
                                    coverage_minor: int,
                                    duration_days: int = 30) -> dict:
            """One call to price + plan an INSURED agent-to-agent job. Given a
            Viridis Verified provider and a job, returns the itemized cost of
            insuring it (surety bond premium from the provider's track record +
            escrow settlement fee + total protection), whether it's insurable,
            and the exact ordered playbook to run it. Read-only. This is the
            insured-delivery product in a single call."""
            if "verified" not in cores or "surety" not in cores:
                return {"status": "error", "error_type": "unavailable",
                        "message": "verified and surety mounts are required"}
            import insured_job_bridge
            return await insured_job_bridge.quote_insured_job(
                cores["verified"], cores["surety"], service_id,
                job_amount_minor, coverage_minor, duration_days)

        pay.settings.stateless_http = True
        if _sec is not None:
            try:
                pay.settings.transport_security = _sec
            except Exception:
                pass
        servers["payments"] = pay
    except Exception:
        pass  # gateway still serves the 21 agents even if payments fails to load

    routes = [Mount(f"/{path}", app=s.streamable_http_app())
              for path, s in servers.items()]

    async def _probe_federated(member: dict) -> dict:
        """Liveness-probe a federated member on its OWN infra via a short MCP
        tools/list. Isolated: a federated outage NEVER degrades the core
        gateway status (they run their own P&L and uptime)."""
        import asyncio
        import urllib.request
        url = member["url"]
        caps = member.get("capabilities", [])
        base = {"agent": member["displayName"], "federated": True,
                "url": url, "infra": member.get("infra", ""),
                "version": member.get("version", ""),
                "checks": {"tools": len(caps), "capabilities": len(caps)}}
        def _blocking():
            body = json.dumps({"jsonrpc": "2.0", "id": 1,
                               "method": "tools/list"}).encode()
            req = urllib.request.Request(
                url, data=body,
                headers={"content-type": "application/json",
                         "accept": "application/json, text/event-stream"})
            with urllib.request.urlopen(req, timeout=6) as r:  # nosec
                return r.status, r.read(4096).decode(errors="replace")
        try:
            status, text = await asyncio.wait_for(
                asyncio.to_thread(_blocking), timeout=8)
            live = status == 200 and '"tools"' in text
            tools = text.count('"name"') if live else 0
            base["status"] = "ok" if live else "degraded"
            if tools:
                base["checks"]["tools"] = tools
        except Exception as e:
            base["status"] = "unreachable"
            base["checks"]["error"] = f"{type(e).__name__}"
        return base

    async def healthz(request):
        import asyncio
        checks = {}
        for path, core in cores.items():
            h = core.health()
            checks[path] = (await h) if asyncio.iscoroutine(h) else h
        subscription_health = subscription_core.health()
        subscription_health = (await subscription_health
                               if asyncio.iscoroutine(subscription_health)
                               else subscription_health)
        subscription_health = dict(subscription_health)
        # Aggregate-only capital visibility: no account, customer, key, or
        # subscription identifiers leave the infrastructure core.
        subscription_health["mrr_summary"] = subscription_core.mrr_summary()
        subscription_health["frontdoor_funnel"] = (
            subscription_core.frontdoor_summary())
        persistence = store.status()
        # Federated members (EnergyAI etc.) run on their own infra — probed
        # for the dashboard but EXCLUDED from the core status gate (SB: their
        # uptime is not ours).
        federated = {}
        for m in EXTERNAL_MEMBERS:
            key = m["identifier"].rsplit(":", 1)[-1]
            federated[key] = await _probe_federated(m)
        # Trust infrastructure fails loud: agents up but state not durable
        # is a degraded gateway, not a healthy one.
        ok = (all(c.get("status") == "ok" for c in checks.values())
              and subscription_health.get("status") == "ok"
              and persistence["available"] and not persistence["errors"])
        return JSONResponse({"status": "ok" if ok else "degraded",
                             "gateway": "viridis-agent-stable",
                             "persistence": persistence,
                             "payment_gate": gate.status(),
                             "subscriptions": subscription_health,
                             "agents": checks,
                             "federated": federated}, status_code=200 if ok else 503)

    async def directory(request):
        return JSONResponse({
            "gateway": "viridis-agent-stable",
            "agents": {path: {"endpoint": f"/{path}/mcp",
                              **{k: cores[path].describe()[k]
                                 for k in ("name", "version", "capabilities")}}
                       for path in MOUNTS},
            "infrastructure": {
                "subscriptions": {
                    "endpoint": "/subscriptions/mcp",
                    **{key: subscription_core.describe()[key]
                       for key in ("name", "version", "capabilities")}},
                "payments": {"endpoint": "/payments/mcp"},
            },
            "human_surfaces": {
                "seats": {
                    "endpoint": "/seats",
                    "description": ("Public monthly-seat catalog and "
                                    "Stripe-hosted subscription checkout"),
                    "money_movement": "Stripe-hosted human action only",
                },
                "deck": {"endpoint": "/deck"},
            },
            "federated_members": [
                {"name": m["displayName"], "url": m["url"],
                 "capabilities": m.get("capabilities", []), "infra": m.get("infra", "")}
                for m in EXTERNAL_MEMBERS],
        })

    # ARD — Agentic Resource Discovery (spec 1.0). One well-known manifest the
    # discovery-layer registries crawl. Generated live from the deployed agents so
    # it is always accurate and its updatedAt stays fresh on every restart.
    async def ard_catalog(request):
        now = datetime.now(timezone.utc).isoformat()
        entries = []
        for path in MOUNTS:
            d = cores[path].describe()
            seo = AGENT_SEO.get(path, {})
            entries.append({
                "identifier": f"urn:air:viridis:{path}",
                "displayName": d.get("name", path),
                "type": "application/mcp-server+json",
                "url": f"{public_base}/{path}/mcp",
                "description": seo.get("desc", f"Viridis {path} agent"),
                "tags": ["a2a", "agent-economy", "viridis", "conservation", path],
                "capabilities": [str(c) for c in d.get("capabilities", [])][:20],
                "representativeQueries": seo.get("queries", [])[:5],
                "version": str(d.get("version", "0.1.0")),
                "updatedAt": now,
                "metadata": {"a2aRole": str(d.get("a2a_role", "")),
                             "gateway": "viridis-agent-stable"},
                "trustManifest": {"identity": f"{public_base}/{path}/mcp",
                                  "identityType": "https"},
            })
        # federated members on their own infrastructure (e.g. EnergyAI)
        for m in EXTERNAL_MEMBERS:
            entries.append({
                "identifier": m["identifier"],
                "displayName": m["displayName"],
                "type": "application/mcp-server+json",
                "url": m["url"],
                "description": m["description"],
                "tags": ["viridis", "agent-economy", "federated-member"],
                "capabilities": m.get("capabilities", []),
                "representativeQueries": m.get("representativeQueries", [])[:5],
                "version": str(m.get("version", "1.0.0")),
                "updatedAt": now,
                "metadata": {"federated": "true", "infra": m.get("infra", "")},
                "trustManifest": {"identity": m["url"].rsplit("/", 1)[0],
                                  "identityType": "https"},
            })
        return JSONResponse({
            "specVersion": "1.0",
            "host": {
                "displayName": "Viridis LLC — Agent Fleet",
                "identifier": "did:web:mcp.viridisconservation.com",
                "documentationUrl": "https://github.com/jdhart81/viridis-agent-fleet",
                "description": ("Viridis deterministic agent services plus "
                                "public monthly-seat subscriptions at /seats."),
                "metadata": {"seatCheckoutUrl": public_base + "/seats"},
                "trustManifest": {"identity": public_base, "identityType": "https"},
            },
            "entries": entries,
            "humanSurfaces": [{
                "identifier": "urn:air:viridis:seats",
                "displayName": "Viridis monthly seats",
                "type": "text/html",
                "url": public_base + "/seats",
                "description": ("Human pricing and Stripe-hosted checkout for "
                                "live Viridis seat plans."),
            }],
        }, media_type="application/ai-catalog+json")

    # /deck — self-hosted command deck (same-origin fetch of /healthz, so it
    # works in ANY browser and inside Cowork artifact iframes; the artifact's
    # sandbox blocks external fetch/tool bridges — observed 2026-07-12).
    _deck_path = Path(__file__).resolve().parent / "deck.html"
    _deck_html = _deck_path.read_text() if _deck_path.exists() else \
        "<h1>deck.html not deployed</h1>"
    _seats_path = Path(__file__).resolve().parent / "seats.html"
    _seats_html = _seats_path.read_text() if _seats_path.exists() else \
        ("<h1>Seat plans are temporarily unavailable.</h1>"
         "<div>{{PLAN_CARDS}}</div><p>{{CATALOG_META}}</p>"
         "<p>{{CONSERVATION_LINE}}</p>")

    async def deck(request):
        from starlette.responses import HTMLResponse
        return HTMLResponse(_deck_html)

    # Usage-statistics dashboard (metering v0.2.0 read surface). Same
    # baked-file pattern as /deck; calls /metering/mcp + /payments/mcp
    # same-origin from the browser, so it needs no keys except the admin
    # token typed (never stored) for the reconciliation panel.
    _stats_path = Path(__file__).resolve().parent / "stats.html"
    _stats_html = _stats_path.read_text() if _stats_path.exists() else \
        "<h1>stats.html not deployed</h1>"

    async def stats(request):
        from starlette.responses import HTMLResponse
        return HTMLResponse(_stats_html)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with contextlib.AsyncExitStack() as stack:
            for s in servers.values():
                await stack.enter_async_context(s.session_manager.run())
            try:
                yield
            finally:
                store.save_all({**cores, "subscriptions": subscription_core})
                store.close()

    seat_routes = _build_seat_routes(
        subscription_core, public_base=public_base,
        template_html=_seats_html,
        pledge_percent=os.environ.get("SEAT_CONSERVATION_PLEDGE_PERCENT", "0"))
    app = Starlette(routes=[Route("/", directory), Route("/healthz", healthz),
                            Route("/deck", deck), Route("/stats", stats),
                            Route("/.well-known/ai-catalog.json", ard_catalog),
                            *seat_routes, *routes],
                    lifespan=lifespan)
    # CORS for the read-only observability surface (healthz / directory /
    # catalog are public data): lets dashboards (Cowork artifact, status
    # pages) fetch fleet metrics from the browser. GET/HEAD only.
    try:
        from starlette.middleware.cors import CORSMiddleware
        app = CORSMiddleware(app, allow_origins=["*"],
                             allow_methods=["GET", "HEAD", "POST", "OPTIONS"],
                             allow_headers=["*"], expose_headers=["*"])
    except Exception:
        pass  # CORS is an enhancement, never a boot blocker
    # Account attribution is request-local and deny-nothing: malformed,
    # duplicate, missing, or unknown bearer values continue anonymously.
    from account_auth import AccountContextMiddleware
    app = AccountContextMiddleware(app)
    # Caller classification for usage statistics (G6/PG12, request_context.py):
    # derives consumer_class/channel/caller from transport evidence per
    # request. Deny-nothing: classification failure degrades to "unknown".
    from request_context import RequestContextMiddleware
    app = RequestContextMiddleware(app)
    return app


app = None  # built lazily; `uvicorn viridis_mcp_gateway:get_app --factory` also works


def get_app():
    global app
    if app is None:
        app = build_app()
    return app


if __name__ == "__main__":
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8402)  # HTTP 402: payment required — the x402 wink
    args = ap.parse_args()
    print(f"Viridis Agent Stable gateway: {len(MOUNTS)} agents on "
          f"http://{args.host}:{args.port}  (paths: {', '.join('/' + p + '/mcp' for p in MOUNTS)})")
    uvicorn.run(get_app(), host=args.host, port=args.port, log_level="warning")
