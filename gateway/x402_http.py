"""
x402_http.py — HTTP-402-native surface over the gated tools (H402 invariants).

The bridge from "an agent CAN pay us" to "any off-the-shelf x402 client
finds and pays us with zero custom code". A standard x402 client (the x402
CLI, x402-fetch, x402+requests) GETs the challenge or POSTs a tool's args,
gets a REAL HTTP 402
with the standard `accepts` payload, signs + retries with X-PAYMENT, and we
settle through the SAME proven rail (x402_rail) then execute the tool. This
is what makes the fleet discoverable/payable on x402 Bazaar — no in-band
MCP parsing required.

--- INVARIANTS (H402) ---
H402-1 REAL 402: an unpaid request returns HTTP 402 with a standards body
       {x402Version, accepts:[requirements], error}. A drop-in x402 client
       acts on it with no Viridis-specific code.
H402-2 SETTLE-THEN-SERVE: the tool executes ONLY after x402_rail settles
       the payment. No settlement -> HTTP 402, no execution.
H402-3 EXACTLY-ONCE: the X-PAYMENT header hashes to a key persisted in the
       core's consumed_x402 map (SHARED with the MCP surface, PRX4); a
       replay serves/settles nothing (the on-chain nonce is single-use too).
H402-4 UNGATED EXECUTION: after settlement the tool runs via the ungated
       _gate_inner (still StateStore-persisted) — the gate's free-tier /
       credit path is NOT re-run (payment already made).
H402-5 UNIFIED TELEMETRY: settlements land in the same
       gate_state["consumed_x402"] the MCP surface uses, so /healthz
       x402.settled counts both surfaces; the tx hash rides back in the
       X-PAYMENT-RESPONSE header.
H402-6 ALLOWLIST: only registered (agent, tool) pairs are payable (404
       otherwise); rail disabled -> 503.
H402-7 FAIL-CLOSED: any settlement/exec error returns a structured 402/500
       and never executes a tool for free, never double-charges.
H402-8 DISCOVERY: each shipped endpoint carries a natural-language
       description, input/output schema, exact price, MCP pointer, and the
       v1 outputSchema field CDP Bazaar indexes after a successful settle.
       The settlement adapter binds paymentPayload.resource to the endpoint.
H402-9 BUYER SIGNAL: every new HTTP-v2 settlement durably records its payer,
       route, amount, transaction, timestamp, and allowlist-based self/external
       classification before execution. Pre-instrumentation records are never
       inferred as external, so seed traffic cannot fake the first-dollar flag.
H402-10 INTRO PRICE: when the default-off x402-intro-v1 switch is enabled,
       an unseen signed payer receives one 10000-atomic-USDC call across the
       entire HTTP fleet. The payer is marked seen in the same durable commit
       as the settlement receipt; persistence failure reverts both records.
       A caller may send X402-Payer-Address on the unpaid preflight for an
       exact returning-payer quote, but the signed authorization is always the
       authority and prevents hint spoofing.
H402-11 BUYER CONTINUATION: a successful paid result may advertise compatible
       next paid routes with exact prices and endpoints. The metadata never
       signs, initiates, or executes another payment; every next call requires
       a separate buyer-authorized x402 settlement. Repeat-purchase telemetry
       counts only versioned external settlements with a known payer wallet.
H402-12 EXECUTABLE CONTINUATION: each next-route offer includes the target
       description, input schema, example, required buyer-supplied fields, MCP
       endpoint, and quote instructions. The offer is preparation metadata,
       never authorization; the next route's unpaid challenge is the only
       authoritative price/payment requirement.
H402-13 EXTERNAL EVIDENCE POINTERS: the catalog may point to immutable fixture
       files in an external verifier's repository. The index is explicitly a
       seller-published pointer, never payment authority or independent proof
       by itself; buyers verify the external file, commit, and SHA-256.
H402-15 DELIVERY TRUTH: after execution, a versioned settlement records only
       whether the paid response was delivered or failed. Historical records
       without this field remain explicitly unknown. A settlement, delivery,
       usefulness signal, and repeat purchase are four separate facts.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from commercial_outcome_outbox import enqueue_from_environment
from fleet_settlement_overlay import bind_security_preflight_delivery

logger = logging.getLogger("viridis.x402_http")

EXTERNAL_EVIDENCE_REPOSITORY = (
    "https://github.com/smartflowproai-lang/x402-endpoint-validator")
EXTERNAL_EVIDENCE_FIXTURES = (
    {
        "route": "regulatory-radar/scan_regulations",
        "evidence_posture": (
            "unpaid_preflight_current_with_dated_settlement_reference"),
        "fixture_state": "matched_on_last_comparison",
        "capture_method": "unpaid_preflight",
        "captured_at": "2026-07-26T16:47:37+00:00",
        "supersedes_capture": "2026-07-24",
        "last_compared_on": "2026-07-26",
        "matched_on_last_comparison": True,
        "payment_terms_changed": False,
        "settled_flow_provenance": {
            "current_fixture_is_settlement_receipt": False,
            "confirmed_at_merge": (
                "0920d50db53cbf59f20052c6c656f17f881c4b41"),
            "pull_request": EXTERNAL_EVIDENCE_REPOSITORY + "/pull/12",
            "payment_terms_byte_identical": True,
        },
        "pull_request": EXTERNAL_EVIDENCE_REPOSITORY + "/pull/15",
        "merge_commit": "811fef6b037cfeb71a890cac97bb822f0efcf03a",
        "fixture_path": "tests/fixtures/viridis_regulatory_radar.json",
        "immutable_url": (
            EXTERNAL_EVIDENCE_REPOSITORY
            + "/blob/811fef6b037cfeb71a890cac97bb822f0efcf03a/"
              "tests/fixtures/viridis_regulatory_radar.json"),
        "sha256": (
            "f667444013029bc98e229b0d3021426d8bf18d13afe3007db419a213d0e290b5"),
    },
    {
        "route": "ghg-ledger/calculate_inventory",
        "evidence_posture": "unpaid_preflight_only",
        "fixture_state": "matched_on_last_comparison",
        "captured_on": "2026-07-26",
        "last_compared_on": "2026-07-26",
        "matched_on_last_comparison": True,
        "payment_terms_changed": False,
        "pull_request": EXTERNAL_EVIDENCE_REPOSITORY + "/pull/14",
        "merge_commit": "45b006b42a60562101a43ffc293447793900d095",
        "fixture_path": "tests/fixtures/viridis_ghg_ledger.json",
        "immutable_url": (
            EXTERNAL_EVIDENCE_REPOSITORY
            + "/blob/45b006b42a60562101a43ffc293447793900d095/"
              "tests/fixtures/viridis_ghg_ledger.json"),
        "sha256": (
            "8cd884c016b19c2131207365e523677a9384b8463fb45eb0ca826a89497b7d40"),
    },
)


def independent_evidence_index() -> dict:
    """Return verifiable pointers without promoting seller metadata to proof."""
    return {
        "classification": "external_fixture_pointer_index",
        "index_posture": "seller_published_pointer_only",
        "authoritative_for_payment": False,
        "revenue_signal": False,
        "verification_required": True,
        "repository": EXTERNAL_EVIDENCE_REPOSITORY,
        "fixtures": [dict(fixture) for fixture in EXTERNAL_EVIDENCE_FIXTURES],
    }


# (agent_path, http_tool_name) -> core action. Extend as tools are exposed.
# Verified mappings only — an entry here makes a real paid endpoint.
X402_HTTP_TOOLS: Dict[Tuple[str, str], str] = {
    ("regulatory-radar", "scan_regulations"): "scan",
    ("regulatory-radar", "monitor_changes"): "monitor_changes",
    ("taxcredit-engine", "calculate_tax_credit"): "calculate",
    ("ghg-ledger", "calculate_inventory"): "calculate_inventory",
    ("quantity-takeoff", "calculate_takeoff"): "calculate_takeoff",
    ("disclosure-compiler", "compile_disclosure"): "compile_disclosure",
    ("hive", "solve"): "solve",
    ("security-preflight", "security_preflight"): "scan",
}

AGENT402_FIXED_ROUTE = ("regulatory-radar", "scan_regulations_agent402")
AGENT402_HTTP_TOOLS: Dict[Tuple[str, str], str] = {
    AGENT402_FIXED_ROUTE: "scan",
}

X402_HTTP_METADATA: Dict[Tuple[str, str], dict] = {
    ("regulatory-radar", "scan_regulations"): {
        "description": ("Energy and climate compliance regulation scan across "
                        "a curated 14-regulation database, with jurisdiction, "
                        "urgency, and effective-date signals, including "
                        "California SB 253 and SB 261 status. The scan step "
                        "pairs with Viridis GHG inventory, sustainability "
                        "disclosure, and clean-energy tax-credit engines."),
        "input_schema": {
            "type": "object",
            "properties": {
                "jurisdiction": {
                    "type": "string",
                    "enum": [
                        "AU", "CA", "EU", "GLOBAL", "JP", "SG", "UK", "US",
                        "au", "ca", "eu", "global", "jp", "sg", "uk", "us",
                        "CALIFORNIA", "California", "california",
                        "US-CA", "us-ca",
                    ],
                    "description": (
                        "Supported jurisdiction: AU, CA (Canada), EU, GLOBAL, "
                        "JP, SG, UK, US, or California. The server normalizes "
                        "case and accepts US-CA as a California alias"),
                },
                "sector": {"type": ["string", "null"]},
                "query": {
                    "type": ["string", "null"],
                    "description": (
                        "Optional case-insensitive text filter applied to "
                        "regulation names, descriptions, and requirements"),
                },
            },
            "required": ["jurisdiction"],
            "additionalProperties": False,
        },
        "input_error_hint": (
            "jurisdiction must be one of AU, CA (Canada), EU, GLOBAL, JP, "
            "SG, UK, US, or CALIFORNIA/US-CA"),
        "input_example": {
            "jurisdiction": "US",
            "sector": "energy",
            "query": "45V clean energy tax credit emissions disclosure",
        },
        "output_example": {"status": "success", "jurisdiction": "EU",
                           "matches": 3, "urgency": "high"},
    },
    ("regulatory-radar", "monitor_changes"): {
        "description": (
            "Monitor regulatory changes, compliance deadlines, and effective "
            "dates in a bounded, source-linked regulatory calendar over the "
            "curated Viridis dataset. Returns requirements that became "
            "effective or have a deadline approaching inside the selected day "
            "window, with alert level and recommended review actions. This is "
            "a deterministic follow-up to a regulation scan, not a live "
            "external regulatory feed."),
        "service_name": "Viridis Regulatory Radar Watch",
        "category": "climate-compliance",
        "tags": [
            "climate-compliance",
            "regulatory-calendar",
            "compliance-deadlines",
            "effective-dates",
            "change-monitoring",
        ],
        "input_schema": {
            "type": "object",
            "properties": {
                "jurisdiction": {
                    "type": "string",
                    "enum": [
                        "AU", "CA", "EU", "GLOBAL", "JP", "SG", "UK", "US",
                        "au", "ca", "eu", "global", "jp", "sg", "uk", "us",
                        "CALIFORNIA", "California", "california",
                        "US-CA", "us-ca",
                    ],
                },
                "topics": {
                    "type": ["array", "null"],
                    "items": {
                        "type": "string", "minLength": 1, "maxLength": 100,
                    },
                    "maxItems": 10,
                },
                "lookback_days": {
                    "type": "integer", "minimum": 1, "maximum": 365,
                    "description": (
                        "Window for recently effective requirements behind "
                        "today and compliance deadlines ahead of today"),
                },
            },
            "required": ["jurisdiction"],
            "additionalProperties": False,
        },
        "input_error_hint": (
            "Use a supported jurisdiction, optional topics array, and "
            "lookback_days from 1 through 365."),
        "input_example": {
            "jurisdiction": "US",
            "topics": ["emissions", "climate"],
            "lookback_days": 90,
        },
        "output_example": {
            "jurisdiction": "us",
            "lookback_days": 90,
            "change_count": 1,
            "alert_level": "critical",
            "changes": [{
                "type": "deadline_approaching",
                "regulation_id": "ca-sb253-2026",
                "days_until_deadline": 13,
                "source_verified_on": "2026-07-25",
            }],
        },
    },
    ("taxcredit-engine", "calculate_tax_credit"): {
        "description": ("Auditable US clean-energy tax-credit calculator from "
                        "explicit credit-specific facts. The claim step pairs "
                        "with the Viridis GHG inventory and sustainability "
                        "disclosure engines for a chainable compliance workflow."),
        "input_schema": {
            "type": "object",
            "properties": {
                "credit": {"type": "string", "description": "45Q, 45V, 45Y, 48E, or 45X"},
                "facts": {"type": "object", "additionalProperties": True},
            },
            "required": ["credit", "facts"],
        },
        "input_example": {"credit": "45V", "facts": {"tax_year": 2026}},
        "output_example": {"status": "ok", "credit": "45V",
                           "estimated_credit_usd": 125000,
                           "audit_trace": ["eligible production", "tier rate"]},
    },
    ("ghg-ledger", "calculate_inventory"): {
        "description": ("Deterministic greenhouse gas inventory API for "
                        "auditable Scope 1, 2, and 3 accounting from explicit "
                        "activity records. The accounting step pairs with "
                        "Viridis embodied-carbon takeoff, disclosure, and "
                        "tax-credit engines."),
        "input_schema": {
            "type": "object",
            "properties": {
                "activities": {"type": "array", "items": {"type": "object"}},
                "options": {"type": ["object", "null"]},
            },
            "required": ["activities"],
        },
        "input_example": {"activities": []},
        "output_example": {"status": "ok", "total_tco2e": 0,
                           "scope_totals": {"scope_1": 0, "scope_2": 0,
                                            "scope_3": 0}},
    },
    ("quantity-takeoff", "calculate_takeoff"): {
        "description": ("Embodied carbon quantity takeoff from a bill of "
                        "materials or explicit construction geometry, producing "
                        "auditable material quantities for carbon accounting. "
                        "The measure step pairs with the Viridis GHG inventory "
                        "and sustainability disclosure engines."),
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array", "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "assembly": {"type": "string"},
                            "unit_system": {"type": "string",
                                            "enum": ["imperial", "SI"]},
                            "dimensions": {"type": "object"},
                        },
                        "required": ["assembly", "unit_system", "dimensions"],
                        "additionalProperties": True,
                    },
                },
                "options": {"type": ["object", "null"]},
            },
            "required": ["items"],
        },
        "input_example": {
            "items": [{
                "id": "slab-1", "assembly": "concrete_slab",
                "unit_system": "imperial",
                "dimensions": {
                    "length": {"value": "20", "unit": "ft"},
                    "width": {"value": "30", "unit": "ft"},
                    "thickness": {"value": "4", "unit": "in"},
                },
            }],
            "options": {"project_id": "buyer-project-1"},
        },
        "output_example": {
            "status": "ok",
            "data": {"takeoff_status": "complete_for_supplied_items",
                     "line_items": [{"assembly": "concrete_slab",
                                     "purchase_qty": "7.78",
                                     "unit": "yd3"}]},
        },
    },
    ("disclosure-compiler", "compile_disclosure"): {
        "description": ("CSRD / IFRS S2 (TCFD-aligned) sustainability "
                        "disclosure compiler from supplied company facts and "
                        "optional verified emissions data. The disclose step "
                        "pairs with Viridis GHG inventory, regulation-scan, and "
                        "clean-energy tax-credit engines."),
        "input_schema": {
            "type": "object",
            "properties": {
                "framework": {"type": "string",
                              "enum": ["esrs-e1", "ifrs-s2",
                                       "sec-climate", "tnfd"]},
                "company_facts": {"type": "object"},
                "ghg_result": {"type": ["object", "null"]},
                "options": {"type": ["object", "null"]},
            },
            "required": ["framework", "company_facts"],
        },
        "input_example": {
            "framework": "esrs-e1",
            "company_facts": {
                "company_name": "Example Climate Works",
                "reporting_period": "2026",
                "transition_plan": {"status": "board-approved",
                                    "target_year": 2035},
                "climate_targets": {"scope": "Scopes 1-3",
                                    "target": "50% by 2035"},
            },
            "options": {
                "applicability": {"framework": "esrs-e1", "applies": True,
                                  "reason": "buyer-supplied applicability",
                                  "source": "buyer"},
            },
        },
        "output_example": {
            "status": "ok",
            "data": {"draft_status": "partial", "framework": "esrs-e1",
                     "filled_datapoints": [], "gaps": [],
                     "audit_sha256": "content-addressed-draft-digest"},
        },
    },
    ("hive", "solve"): {
        "description": (
            "Cost-bounded multi-agent solve with three independent workers, "
            "reviewer-not-author cross-review, escrow settlement, trust "
            "outcomes, compute accounting, and a content-addressed audit. "
            "The fixed $5 profile supports at most four subtasks and "
            "redundancy three."),
        "service_name": "Viridis Agent Hive",
        "category": "AI Services",
        "tags": ["agents", "orchestration", "audit", "escrow", "reasoning"],
        "input_schema": {
            "type": "object",
            "properties": {
                "problem": {
                    "type": "string", "minLength": 1,
                    "maxLength": 12000,
                },
                "budget_minor": {"type": "integer", "const": 500},
                "subtasks": {
                    "type": ["array", "null"], "minItems": 1, "maxItems": 4,
                    "items": {
                        "type": "string", "minLength": 1, "maxLength": 4000,
                    },
                },
                "depth": {"type": "integer", "const": 0},
                "redundancy": {
                    "type": "integer", "minimum": 1, "maximum": 3,
                },
                "accept_threshold": {
                    "type": "number", "exclusiveMinimum": 0,
                    "maximum": 1,
                },
                "seed": {"type": "integer"},
                "fee_bps": {"type": "integer", "const": 0},
            },
            "required": ["problem", "budget_minor"],
            "additionalProperties": False,
        },
        "input_error_hint": (
            "Use the fixed $5 profile: non-empty problem, budget_minor=500, "
            "depth=0, fee_bps=0, at most four subtasks, redundancy 1..3."),
        "input_example": {
            "problem": (
                "Compare two approaches to reducing industrial energy cost "
                "and return a reviewed recommendation with key risks."),
            "budget_minor": 500,
            "subtasks": [
                "Assess technical feasibility.",
                "Assess economics and implementation risk.",
            ],
            "depth": 0,
            "redundancy": 2,
            "accept_threshold": 0.6,
            "seed": 0,
            "fee_bps": 0,
        },
        "output_example": {
            "status": "ok",
            "data": {
                "job_id": "job-content-addressed-id",
                "state": "COMPLETED",
                "synthesis": "review-surviving answer",
                "audit_sha256": "content-addressed-audit-digest",
            },
        },
    },
    ("security-preflight", "security_preflight"): {
        "description": (
            "Deterministic security preflight of caller-supplied MCP agent "
            "metadata. Checks endpoint/auth declarations, closed tool schemas, "
            "high-impact approval policy, policy conflicts, and static "
            "injection indicators. Returns a signed, input-redacted receipt. "
            "Does not fetch or certify the deployed runtime."),
        "service_name": "Viridis Security Preflight",
        "category": "Security",
        "icon_url": (
            "https://mcp.viridisconservation.com/brand/viridis-mark.svg"),
        "tags": ["security", "MCP", "agents", "receipts", "preflight"],
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": (
                        "Existing or intended lowercase Agent Market profile "
                        "identifier"),
                },
                "subject_profile_sha256": {
                    "type": ["string", "null"],
                    "pattern": "^[0-9a-f]{64}$",
                    "description": (
                        "Optional current Agent Market profile digest. When "
                        "supplied, the signed receipt is bound to this exact "
                        "profile and becomes eligible for explicit Market "
                        "import."),
                },
                "manifest": {
                    "type": "object",
                    "description": (
                        "Caller-supplied agent manifest; common fields are "
                        "endpoint, auth, description, instructions, and tools"),
                },
                "policy": {
                    "type": ["object", "null"],
                    "description": (
                        "Optional allowed_tools, denied_tools, and "
                        "approval_required_tools lists"),
                },
                "sample_inputs": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": (
                        "Optional bounded sample text for static injection "
                        "indicator checks"),
                },
            },
            "required": ["agent_id", "manifest"],
            "additionalProperties": False,
        },
        "input_error_hint": (
            "Supply a lowercase agent_id and JSON manifest. Optional policy "
            "must be an object, subject_profile_sha256 must be 64 lowercase "
            "hex characters, and sample_inputs must be an array of strings."),
        "input_example": {
            "agent_id": "example-research-agent",
            "manifest": {
                "endpoint": "https://agent.example/mcp",
                "auth": "bearer",
                "tools": [{
                    "name": "read_status",
                    "input_schema": {
                        "type": "object",
                        "properties": {"id": {"type": "string"}},
                        "required": ["id"],
                        "additionalProperties": False,
                    },
                }],
            },
            "policy": {
                "allowed_tools": ["read_status"],
                "denied_tools": [],
                "approval_required_tools": [],
            },
            "sample_inputs": ["Summarize the supplied status record."],
        },
        "output_example": {
            "status": "ok",
            "verdict": "pass",
            "receipt": {
                "protocol": "viridis-security-receipt-v1",
                "posture": "SCANNED",
                "subject_agent_id": "example-research-agent",
            },
            "market_import": {"automatic": False},
            "claim_boundary": (
                "Static buyer-supplied artifacts only; runtime not tested."),
        },
    },
}

# Agent402 native listings advertise one static per-call price.  Keep this
# compatibility alias at Regulatory Radar's $0.25 list price so the amount in
# Agent402's PAYMENT-SIGNATURE always matches the Viridis challenge.  The
# public scan_regulations route retains its one-time $0.01 intro schedule.
X402_HTTP_METADATA[AGENT402_FIXED_ROUTE] = {
    **X402_HTTP_METADATA[("regulatory-radar", "scan_regulations")],
    "service_name": "Viridis Regulatory Radar",
    "category": "Search",
    "icon_url": (
        "https://mcp.viridisconservation.com/brand/viridis-mark.svg"),
    "tags": ["climate", "energy", "compliance", "regulation", "CSRD"],
}
HIVE_FIXED_ROUTE = ("hive", "solve")
INTRO_EXEMPT_ROUTES = frozenset({AGENT402_FIXED_ROUTE, HIVE_FIXED_ROUTE})

# A small deterministic workflow graph for paid buyers. Values are
# ((target_agent, target_tool), why_that_step_is_compatible). Targets remain
# ordinary x402 endpoints: this graph is discovery metadata, never execution.
NEXT_PAID_ROUTES = {
    ("security-preflight", "security_preflight"): (
        (("hive", "solve"),
         "Use a reviewed multi-agent solve to turn the bounded preflight "
         "findings into a remediation plan from buyer-supplied context."),
    ),
    ("quantity-takeoff", "calculate_takeoff"): (
        (("ghg-ledger", "calculate_inventory"),
         "Use measured material quantities as auditable GHG activity inputs."),
    ),
    ("ghg-ledger", "calculate_inventory"): (
        (("disclosure-compiler", "compile_disclosure"),
         "Use the verified inventory to populate a sustainability disclosure."),
    ),
    ("disclosure-compiler", "compile_disclosure"): (
        (("regulatory-radar", "scan_regulations"),
         "Check the draft against relevant climate and energy requirements."),
        (("taxcredit-engine", "calculate_tax_credit"),
         "Evaluate a clean-energy tax-credit claim from supplied project facts."),
    ),
    ("taxcredit-engine", "calculate_tax_credit"): (
        (("regulatory-radar", "scan_regulations"),
         "Check current compliance requirements around the proposed claim."),
    ),
    ("regulatory-radar", "scan_regulations"): (
        (("regulatory-radar", "monitor_changes"),
         "Watch dated requirements after the initial regulation scan."),
        (("disclosure-compiler", "compile_disclosure"),
         "Turn identified disclosure requirements into an auditable draft."),
        (("taxcredit-engine", "calculate_tax_credit"),
         "Evaluate an applicable clean-energy tax-credit opportunity."),
    ),
    ("regulatory-radar", "monitor_changes"): (
        (("regulatory-radar", "scan_regulations"),
         "Inspect the full applicable regulation set behind a dated watch."),
        (("disclosure-compiler", "compile_disclosure"),
         "Turn an identified disclosure requirement into an auditable draft."),
    ),
    AGENT402_FIXED_ROUTE: (
        (("disclosure-compiler", "compile_disclosure"),
         "Turn identified disclosure requirements into an auditable draft."),
        (("taxcredit-engine", "calculate_tax_credit"),
         "Evaluate an applicable clean-energy tax-credit opportunity."),
    ),
    HIVE_FIXED_ROUTE: (
        (("regulatory-radar", "scan_regulations"),
         "Check the reviewed recommendation against applicable requirements."),
        (("disclosure-compiler", "compile_disclosure"),
         "Turn review-surviving conclusions into an auditable disclosure."),
    ),
}

OUTPUT_SCHEMA = {"type": "object", "additionalProperties": True}
SETTLEMENT_CLASSIFICATION_VERSION = 1
PAID_DELIVERY_RECEIPT_VERSION = "viridis-paid-delivery-v1"
PAID_DELIVERY_RECEIPT_FIELD = "viridis_delivery"
INTRO_SEEN_KEY = "x402_intro_seen_payers"
INTRO_PAYER_HEADER = "x402-payer-address"
INTRO_SCHEDULE = {
    "version": "x402-intro-v1",
    "price_minor": 1,
    "amount_atomic": "10000",
    "scope": "one successful HTTP x402 v2 settlement per payer wallet",
    "sybil_posture": ("intentionally light friction: wallet-level only; "
                       "no identity collection or cross-wallet linkage"),
}


def intro_enabled() -> bool:
    """Default-off activation flag; no partial or implicit enablement."""
    return os.environ.get("X402_INTRO_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on"}


def _gate_states(cores: Dict[str, Any]) -> Dict[str, dict]:
    """Read gate state without importing payment_gate at module import time."""
    try:
        from payment_gate import GATE_ATTR
    except Exception:
        return {}
    return {name: getattr(core, GATE_ATTR, {})
            for name, core in cores.items()}


def _seen_payers(cores: Dict[str, Any]) -> set:
    """Fleet-wide payer history, including pre-schedule v2 settlements."""
    seen = set()
    for gate in _gate_states(cores).values():
        if not isinstance(gate, dict):
            continue
        recorded = gate.get(INTRO_SEEN_KEY, {})
        if isinstance(recorded, dict):
            seen.update(str(item).strip().lower() for item in recorded if item)
        elif isinstance(recorded, (set, list, tuple)):
            seen.update(str(item).strip().lower() for item in recorded if item)
        for settlement in gate.get("consumed_x402", {}).values():
            if not isinstance(settlement, dict):
                continue
            payer = str(settlement.get("payer_wallet", "")).strip().lower()
            if payer:
                seen.add(payer)
    return seen


def _payer_seen(cores: Dict[str, Any], payer: str) -> bool:
    return bool(payer) and payer.strip().lower() in _seen_payers(cores)


def intro_status(cores: Dict[str, Any]) -> dict:
    """Health-ready policy state; never exposes more than public wallets."""
    return {
        "enabled": intro_enabled(),
        "schedule": dict(INTRO_SCHEDULE),
        "seen_payers": len(_seen_payers(cores)),
        "seen_payers_evidence": {
            "classification": "seller_reported_pricing_eligibility_state",
            "independently_verifiable": False,
            "authoritative_for_payment": False,
            "revenue_signal": False,
        },
        "payer_hint_header": "X402-Payer-Address",
        "note": ("seen_payers is a seller-reported pricing-state count, not "
                 "independent buyer or revenue proof. The hint improves "
                 "preflight quoting only; signed payment authorization "
                 "determines eligibility."),
    }


def price_for_payer(cores: Dict[str, Any], route: Tuple[str, str],
                    list_price: int, payer: str = "") -> int:
    """Return the exact public price, honoring fixed-price exclusions."""
    if (intro_enabled() and route not in INTRO_EXEMPT_ROUTES
            and not _payer_seen(cores, payer)):
        return INTRO_SCHEDULE["price_minor"]
    return list_price


def _payer_wallet(payload: dict) -> str:
    """Extract the public payer address from the signed v2 authorization."""
    inner = payload.get("payload") if isinstance(payload, dict) else None
    if not isinstance(inner, dict):
        return ""
    authorization = (inner.get("authorization") or
                     inner.get("permit2Authorization"))
    if not isinstance(authorization, dict):
        return ""
    return str(authorization.get("from", "")).strip()


def _self_wallets() -> set:
    """Configured Viridis wallets; empty means every new payer is external."""
    return {item.strip().lower() for item in
            os.environ.get("VIRIDIS_X402_SELF_WALLETS", "").split(",")
            if item.strip()}


def _classified_settlement(payload: dict, agent: str, tool: str,
                           result: dict, identifier: str, *,
                           intro_applied: bool = False,
                           list_price_minor: int | None = None,
                           surface: str = "http-402-v2") -> dict:
    payer = _payer_wallet(payload)
    record = {
        "payment_identifier": identifier,
        "tx_hash": result["tx_hash"],
        "network": result["network"],
        "amount_atomic": result["amount_atomic"],
        "credits": 1,
        "at": time.strftime("%Y-%m-%d", time.gmtime()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "surface": surface,
        "route": f"{agent}/{tool}",
        "payer_wallet": payer,
        "self_settle": payer.lower() in _self_wallets(),
        "classification_version": SETTLEMENT_CLASSIFICATION_VERSION,
        "settlement_receipt": result.get("settlement_receipt"),
        "extension_responses": result.get("extension_responses", {}),
    }
    if intro_enabled():
        record.update({
            "pricing_schedule_version": INTRO_SCHEDULE["version"],
            "intro_price_applied": bool(intro_applied),
            "list_price_minor": list_price_minor,
        })
    return record


def _paid_delivery_status(payload: Any) -> str:
    """Classify transport delivery without claiming usefulness or adoption."""
    if isinstance(payload, dict):
        status = str(payload.get("status", "")).strip().lower()
        if (payload.get("error") or payload.get("error_type")
                or status in {"error", "failed", "failure"}):
            return "failed"
    return "delivered"


def _canonical_json_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _attach_paid_delivery_receipt(
    payload: Any,
    record: dict,
    agent: str,
    tool: str,
) -> tuple[Any, dict | None]:
    """Bind the returned JSON result to its settlement without overstating it.

    The buyer can remove the viridis_delivery field from the returned object,
    canonicalize the remainder using the advertised recipe, and reproduce the
    result digest. This is seller-side transport evidence, not buyer
    acceptance, usefulness, adoption, or permission for another purchase.
    """
    if not isinstance(payload, dict):
        return payload, None
    result_payload = dict(payload)
    result_payload.pop(PAID_DELIVERY_RECEIPT_FIELD, None)
    delivered_at = (
        str(record.get("delivery_recorded_at", "")).strip()
        or datetime.now(timezone.utc).isoformat()
    )
    receipt = {
        "version": PAID_DELIVERY_RECEIPT_VERSION,
        "classification": "seller_transport_delivery_receipt",
        "route": f"{agent}/{tool}",
        "settlement": {
            "transaction": record.get("tx_hash"),
            "network": record.get("network"),
            "amount_atomic": record.get("amount_atomic"),
        },
        "delivered_at": delivered_at,
        "result_canonicalization": (
            "UTF-8 JSON with sort_keys=true, separators=(',', ':'), "
            "ensure_ascii=false, excluding viridis_delivery"
        ),
        "result_sha256": _canonical_json_sha256(result_payload),
        "buyer_acceptance": "not_observed",
        "usefulness": "not_observed",
    }
    receipt["receipt_sha256"] = _canonical_json_sha256(receipt)
    enriched = dict(result_payload)
    enriched[PAID_DELIVERY_RECEIPT_FIELD] = receipt
    return enriched, receipt


def _record_delivery_status(
    record: dict,
    status: str,
    receipt: dict | None = None,
) -> None:
    if status not in {"delivered", "failed"}:
        raise ValueError("delivery status must be delivered or failed")
    record["delivery_status"] = status
    recorded_at = (
        receipt.get("delivered_at")
        if status == "delivered" and isinstance(receipt, dict)
        else None
    )
    record["delivery_recorded_at"] = (
        recorded_at or datetime.now(timezone.utc).isoformat())
    if status == "delivered" and isinstance(receipt, dict):
        record["delivery_receipt"] = dict(receipt)


def _empty_settlement_metrics() -> dict:
    return {
        "settlements_total": 0,
        "self_settlements": 0,
        "external_settlements": 0,
        "distinct_external_payers": 0,
        "repeat_external_purchases": 0,
        "external_revenue_atomic": 0,
        "external_paid_results_delivered": 0,
        "external_paid_results_receipted": 0,
        "external_paid_results_failed": 0,
        "external_paid_results_unknown": 0,
        "first_external_settlement": None,
    }


def settlement_metrics(gate_states: Dict[str, dict]) -> dict:
    """Aggregate only versioned records; legacy seeds cannot fake a stranger."""
    routes = {f"{agent}/{tool}": _empty_settlement_metrics()
              for agent, tool in X402_HTTP_TOOLS}
    total = _empty_settlement_metrics()
    payer_sets = {route: set() for route in routes}
    known_payer_purchases = {route: 0 for route in routes}
    total_payers = set()
    total_known_payer_purchases = 0
    for gate in gate_states.values():
        if not isinstance(gate, dict):
            continue
        for record in gate.get("consumed_x402", {}).values():
            if (not isinstance(record, dict)
                    or record.get("surface") not in {
                        "http-402-v2", "a2a-x402-v2"}
                    or record.get("classification_version")
                    != SETTLEMENT_CLASSIFICATION_VERSION):
                continue
            route = str(record.get("route", ""))
            if route not in routes:
                routes[route] = _empty_settlement_metrics()
                payer_sets[route] = set()
                known_payer_purchases[route] = 0
            route_metrics = routes[route]
            for metrics in (route_metrics, total):
                metrics["settlements_total"] += 1
            if record.get("self_settle") is True:
                route_metrics["self_settlements"] += 1
                total["self_settlements"] += 1
                continue
            route_metrics["external_settlements"] += 1
            total["external_settlements"] += 1
            try:
                amount = int(str(record.get("amount_atomic", "0")))
            except (TypeError, ValueError):
                amount = 0
            route_metrics["external_revenue_atomic"] += amount
            total["external_revenue_atomic"] += amount
            delivery_status = record.get("delivery_status")
            delivery_field = {
                "delivered": "external_paid_results_delivered",
                "failed": "external_paid_results_failed",
            }.get(delivery_status, "external_paid_results_unknown")
            route_metrics[delivery_field] += 1
            total[delivery_field] += 1
            delivery_receipt = record.get("delivery_receipt")
            if (
                delivery_status == "delivered"
                and isinstance(delivery_receipt, dict)
                and delivery_receipt.get("version")
                == PAID_DELIVERY_RECEIPT_VERSION
                and isinstance(delivery_receipt.get("result_sha256"), str)
                and len(delivery_receipt["result_sha256"]) == 64
                and isinstance(delivery_receipt.get("receipt_sha256"), str)
                and len(delivery_receipt["receipt_sha256"]) == 64
            ):
                route_metrics["external_paid_results_receipted"] += 1
                total["external_paid_results_receipted"] += 1
            payer = str(record.get("payer_wallet", "")).strip().lower()
            if payer:
                known_payer_purchases[route] += 1
                total_known_payer_purchases += 1
                payer_sets[route].add(payer)
                total_payers.add(payer)
            first = {"tx_hash": record.get("tx_hash"),
                     "timestamp": record.get("timestamp")}
            for metrics in (route_metrics, total):
                current = metrics["first_external_settlement"]
                if (current is None or str(first["timestamp"] or "")
                        < str(current.get("timestamp") or "")):
                    metrics["first_external_settlement"] = first
    for route, metrics in routes.items():
        metrics["distinct_external_payers"] = len(payer_sets[route])
        metrics["repeat_external_purchases"] = max(
            known_payer_purchases[route] - len(payer_sets[route]), 0)
    total["distinct_external_payers"] = len(total_payers)
    total["repeat_external_purchases"] = max(
        total_known_payer_purchases - len(total_payers), 0)
    return {"total": total, "per_route": routes}


def next_paid_routes(agent: str, tool: str, public_base: str) -> list:
    """Return exact compatible offers without authorizing or executing them."""
    from payment_gate import PRICE_MINOR, DEFAULT_PRICE_MINOR
    import x402_rail
    base = public_base.rstrip("/")
    offers = []
    for (next_agent, next_tool), reason in NEXT_PAID_ROUTES.get(
            (agent, tool), ()):
        if (next_agent, next_tool) not in X402_HTTP_TOOLS:
            continue
        price = PRICE_MINOR.get(next_agent, DEFAULT_PRICE_MINOR)
        metadata = X402_HTTP_METADATA[(next_agent, next_tool)]
        input_schema = metadata["input_schema"]
        offers.append({
            "agent": next_agent,
            "tool": next_tool,
            "endpoint": f"{base}/x402/{next_agent}/{next_tool}",
            "mcp_endpoint": f"{base}/{next_agent}/mcp",
            "method": "POST",
            "price_minor": price,
            "amount_atomic_usdc": x402_rail.price_atomic(price),
            "reason": reason,
            "description": metadata["description"],
            "input_schema": input_schema,
            "input_example": metadata["input_example"],
            "required_buyer_inputs": list(input_schema.get("required", [])),
            "quote": {
                "preflight_required": True,
                "authoritative_source": "next_route_unpaid_http_402",
                "payer_hint_header": "X402-Payer-Address",
                "payer_hint_value_source":
                    "caller_public_signing_address",
                "payer_hint_required_for_exact_quote":
                    (next_agent, next_tool) not in INTRO_EXEMPT_ROUTES,
                "payer_hint_authorizes_payment": False,
                "advertised_price_posture": "returning_payer_list_price",
            },
        })
    return offers


def repeat_paid_route(agent: str, tool: str, public_base: str) -> dict:
    """Return a same-service repurchase contract without authorizing it."""
    from payment_gate import PRICE_MINOR, DEFAULT_PRICE_MINOR
    import x402_rail
    base = public_base.rstrip("/")
    price = PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR)
    metadata = X402_HTTP_METADATA[(agent, tool)]
    input_schema = metadata["input_schema"]
    return {
        "agent": agent,
        "tool": tool,
        "endpoint": f"{base}/x402/{agent}/{tool}",
        "mcp_endpoint": f"{base}/{agent}/mcp",
        "method": "POST",
        "price_minor": price,
        "amount_atomic_usdc": x402_rail.price_atomic(price),
        "description": metadata["description"],
        "input_schema": input_schema,
        "input_example": metadata["input_example"],
        "required_buyer_inputs": list(input_schema.get("required", [])),
        "input_policy": (
            "Supply a new caller-owned request. Never reuse prior inputs or "
            "infer missing facts from the previous result."),
        "quote": {
            "preflight_required": True,
            "authoritative_source": "repeat_route_unpaid_http_402",
            "payer_hint_header": "X402-Payer-Address",
            "payer_hint_value_source": "caller_public_signing_address",
            "payer_hint_required_for_exact_quote":
                (agent, tool) not in INTRO_EXEMPT_ROUTES,
            "payer_hint_authorizes_payment": False,
            "advertised_price_posture": "returning_payer_list_price",
        },
    }


def _with_commerce_metadata(payload: Any, agent: str, tool: str,
                            public_base: str) -> Any:
    """Add continuation metadata only to an explicitly successful result."""
    if not isinstance(payload, dict) or (agent, tool) not in NEXT_PAID_ROUTES:
        return payload
    status = str(payload.get("status", "")).strip().lower()
    if (payload.get("error") or payload.get("error_type")
            or status in {"error", "failed", "failure"}):
        return payload
    enriched = dict(payload)
    enriched["viridis_commerce"] = {
        "version": "viridis-commerce-v1",
        "current_route": f"{agent}/{tool}",
        "repeat_purchase": repeat_paid_route(
            agent, tool, public_base),
        "next_paid_routes": next_paid_routes(
            agent, tool, public_base),
        "auto_execute": False,
        "payment_required": True,
        "buyer_authorization_required": True,
        "note": ("No repeat or follow-on payment was signed, initiated, or "
                 "executed. Every purchase requires new caller-owned inputs, "
                 "a fresh unpaid quote, and a separate x402 settlement."),
    }
    return enriched


def discovery_entries(public_base: str) -> list:
    """ARD/health-ready inventory of the payable HTTP front door."""
    from payment_gate import PRICE_MINOR, DEFAULT_PRICE_MINOR
    import x402_rail
    base = public_base.rstrip("/")
    try:
        import x402_v2
        v2_status = x402_v2.status()
    except Exception:
        v2_status = {"requested": False, "enabled": False,
                     "active_protocol": 1,
                     "bazaar_extension_responses": {}}
    entries = []
    for agent, tool in X402_HTTP_TOOLS:
        route_key = f"{agent}/{tool}"
        entries.append({
            "agent": agent,
            "tool": tool,
            "endpoint": f"{base}/x402/{agent}/{tool}",
            "mcp_endpoint": f"{base}/{agent}/mcp",
            "methods": ["GET", "POST"],
            "paid_execution_method": "POST",
            "price_minor": PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR),
            "amount_atomic_usdc": x402_rail.price_atomic(
                PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR)),
            "description": X402_HTTP_METADATA[(agent, tool)]["description"],
            "next_paid_routes": next_paid_routes(agent, tool, base),
            "x402_version": v2_status["active_protocol"],
            "v2_enabled": v2_status["enabled"],
            "bazaar_extension_responses":
                v2_status["bazaar_extension_responses"].get(route_key, {}),
        })
    return entries


def _decode_query_value(value: Any) -> Any:
    """GET convenience: JSON-decode objects/arrays/bools/numbers, keep text."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


async def _request_args(request) -> dict:
    if str(getattr(request, "method", "POST")).upper() == "GET":
        query = getattr(request, "query_params", {})
        return {str(k): _decode_query_value(v) for k, v in query.items()}
    try:
        args = await request.json()
    except Exception:
        args = {}
    if not isinstance(args, dict):
        return {}
    return args


async def _paid_preflight(core: Any, action: str,
                          args: Dict[str, Any]) -> Dict[str, Any] | None:
    """Run an agent-owned, side-effect-free paid-lane admission check."""
    hook = getattr(core, "_paid_preflight", None)
    if not callable(hook):
        return None
    try:
        result = hook({"action": action, **args})
        if asyncio.iscoroutine(result):
            result = await result
    except Exception as exc:
        logger.exception("paid preflight failed closed")
        return {
            "status": "error", "error_type": "ServiceUnavailable",
            "message": f"paid preflight unavailable: {type(exc).__name__}",
        }
    if result is None:
        return None
    if isinstance(result, dict) and result.get("status") == "error":
        return result
    return {
        "status": "error", "error_type": "ServiceUnavailable",
        "message": "paid preflight returned an invalid decision",
    }


def _preflight_http_response(error: Dict[str, Any]):
    unavailable = error.get("error_type") == "ServiceUnavailable"
    return _resp({
        **error,
        "payment_required": False,
    }, 503 if unavailable else 400)


def _normalize_request_args(agent: str, tool: str, args: dict) -> dict:
    """Normalize advertised aliases without mutating the caller's object."""
    if not isinstance(args, dict):
        return {}
    normalized = dict(args)
    if agent == "regulatory-radar":
        jurisdiction = normalized.get("jurisdiction")
        if isinstance(jurisdiction, str):
            jurisdiction = jurisdiction.strip().lower()
            normalized["jurisdiction"] = {
                "us-ca": "california",
                "ca-us": "california",
            }.get(jurisdiction, jurisdiction)
    return normalized


def _resp(payload, status=200, headers=None):
    from starlette.responses import JSONResponse
    return JSONResponse(payload, status_code=status, headers=headers or {})


def make_x402_http_route(cores, store, public_base, tools=None):
    """Factory: build the GET/POST /x402/{agent}/{tool} handler, closing over the
    gateway's cores + StateStore. `tools` overrides the registered allowlist
    (test hook). Import-guarded so the gateway still serves if x402 absent."""
    import x402_rail
    from payment_gate import PRICE_MINOR, DEFAULT_PRICE_MINOR, GATE_ATTR
    registry = (tools if tools is not None else
                {**X402_HTTP_TOOLS, **AGENT402_HTTP_TOOLS})

    async def handler(request):
        agent = request.path_params.get("agent", "")
        tool = request.path_params.get("tool", "")
        action = registry.get((agent, tool))
        core = cores.get(agent)
        if action is None or core is None:                     # H402-6
            return _resp({"error": "unknown x402 tool",
                          "available": [f"{a}/{t}"
                                        for (a, t) in registry]}, 404)
        if not x402_rail.is_enabled():                         # H402-6
            return _resp({"error": "x402 rail disabled"}, 503)
        list_price = PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR)
        payer_hint = str(request.headers.get(INTRO_PAYER_HEADER, "")).strip()
        route = (agent, tool)
        intro_for_route = intro_enabled() and route not in INTRO_EXEMPT_ROUTES
        price = price_for_payer(cores, route, list_price, payer_hint)
        resource = f"{public_base}/x402/{agent}/{tool}"
        meta = X402_HTTP_METADATA.get(route, {
            "description": f"Viridis {agent} {tool} tool call",
            "input_schema": {"type": "object", "additionalProperties": True},
            "input_example": {},
        })
        args = _normalize_request_args(
            agent, tool, await _request_args(request))
        try:
            import x402_v2
            schema_matches = x402_v2._matches_schema(
                args, meta["input_schema"])
        except Exception:
            schema_matches = True
        if not schema_matches:
            return _resp({
                "error": "input does not match advertised schema",
                "error_type": "input_validation_error",
                "payment_required": False,
                "hint": meta.get(
                    "input_error_hint",
                    "Correct the request to match the advertised JSON "
                    "input schema."),
            }, 400)
        preflight_error = await _paid_preflight(core, action, args)
        if preflight_error is not None:
            return _preflight_http_response(preflight_error)
        # X2-1/X2-7: a separate, default-off v2 lane.  Flag off continues at
        # the byte-stable Wave-6 v1 behavior below; flag on never falls back.
        try:
            import x402_v2
            if x402_v2.requested():
                if not x402_v2.is_enabled():
                    return _resp({"error": "x402 v2 rail disabled or "
                                           "incompletely configured"}, 503)
                payment_required = x402_v2.build_payment_required(
                    agent, tool, price, resource,
                    str(getattr(request, "method", "POST")).upper(), meta)
                required_headers = x402_v2.response_headers(payment_required)
                signature = request.headers.get("payment-signature")
                if not signature:
                    body = (payment_required
                            if (agent, tool) == AGENT402_FIXED_ROUTE
                            else {"error": "PAYMENT-SIGNATURE required"})
                    return _resp(body, 402, required_headers)
                payload = x402_v2.parse_header(signature)
                if payload is None:
                    return _resp({"error": "malformed PAYMENT-SIGNATURE"},
                                 402, required_headers)
                payer = _payer_wallet(payload)
                if intro_for_route:
                    if not payer:
                        return _resp({"error": "signed payer address required "
                                              "for intro-price eligibility"},
                                     402, required_headers)
                    expected_price = price_for_payer(
                        cores, route, list_price, payer)
                    if expected_price != price:
                        payment_required = x402_v2.build_payment_required(
                            agent, tool, expected_price, resource,
                            str(getattr(request, "method", "POST")).upper(),
                            meta)
                        required_headers = x402_v2.response_headers(
                            payment_required)
                        return _resp({
                            "error": ("intro price already used; retry with "
                                      "the full-price PAYMENT-REQUIRED"
                                      if expected_price == list_price else
                                      "payer is eligible for the intro price; "
                                      "retry with this PAYMENT-REQUIRED"),
                            "pricing_schedule": INTRO_SCHEDULE["version"],
                        }, 402, required_headers)
                gate_state = getattr(core, GATE_ATTR, None)
                inner = getattr(core, "_gate_inner", None)
                if gate_state is None or inner is None:
                    return _resp({"error": "agent is not gated"}, 500)
                identifier = x402_v2.payment_identifier(payload, signature)
                key = "v2:" + hashlib.sha256(identifier.encode()).hexdigest()
                consumed = gate_state.setdefault("consumed_x402", {})
                if key in consumed:
                    prior = consumed[key]
                    replay_headers = x402_v2.settlement_headers({
                        "settled": True,
                        "tx_hash": prior.get("tx_hash", ""),
                        "network": prior.get("network", ""),
                        "settlement_receipt":
                            prior.get("settlement_receipt")})
                    return _resp({"error": "payment already consumed",
                                  "idempotent": True,
                                  "transaction": prior.get("tx_hash")},
                                 402, replay_headers)
                result = x402_v2.verify_and_settle(
                    payload, payment_required, agent, tool)
                if not result.get("settled"):
                    return _resp({"error": "settlement failed: "
                                           f"{result.get('reason')}",
                                  "extension_responses":
                                      result.get("extension_responses", {})},
                                 402, required_headers)
                consumed[key] = _classified_settlement(
                    payload, agent, tool, result, identifier,
                    intro_applied=(intro_for_route and
                                   price == INTRO_SCHEDULE["price_minor"]),
                    list_price_minor=list_price)
                intro_seen = gate_state.get(INTRO_SEEN_KEY, {})
                if intro_for_route and not isinstance(intro_seen, dict):
                    intro_seen = {}
                if intro_for_route and INTRO_SEEN_KEY not in gate_state:
                    gate_state[INTRO_SEEN_KEY] = intro_seen
                seen_key = payer.strip().lower() if intro_for_route else ""
                seen_added = False
                if seen_key and isinstance(intro_seen, dict):
                    seen_added = seen_key not in intro_seen
                    intro_seen[seen_key] = {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "route": f"{agent}/{tool}",
                        "tx_hash": result["tx_hash"],
                        "pricing_schedule_version": INTRO_SCHEDULE["version"],
                    }
                persisted = False
                try:
                    persisted = bool(store.save(agent, core))
                except Exception:
                    logger.critical("x402_v2[%s]: persistence raised after "
                                    "settled tx=%s", agent, result["tx_hash"])
                paid_headers = x402_v2.settlement_headers(result)
                if not persisted:
                    consumed.pop(key, None)
                    if seen_added:
                        intro_seen.pop(seen_key, None)
                    return _resp({"error": "payment settled but durable "
                                           "receipt persistence failed; tool "
                                           "not executed",
                                  "transaction": result["tx_hash"]},
                                 500, paid_headers)
                if not result.get("serve", True):
                    _record_delivery_status(consumed[key], "failed")
                    try:
                        store.save(agent, core)
                    except Exception:
                        pass
                    return _resp({"error": result.get("reason"),
                                  "transaction": result["tx_hash"],
                                  "extension_responses":
                                      result.get("extension_responses", {})},
                                 502, paid_headers)
                args = {k: v for k, v in args.items() if k != "action"}
                try:
                    out = inner({"action": action, **args})
                    if asyncio.iscoroutine(out):
                        out = await out
                    try:
                        store.save(agent, core)
                    except Exception:
                        pass
                except Exception as exc:
                    logger.exception("x402_v2[%s]: tool failed after settle",
                                     agent)
                    out = {"status": "error", "error_type": "tool_error",
                           "message": "paid call errored: "
                                      f"{type(exc).__name__} (payment settled; "
                                      "contact support with the transaction)",
                           "tx_hash": result["tx_hash"]}
                delivery_status = _paid_delivery_status(out)
                _record_delivery_status(consumed[key], delivery_status)
                accepted = payment_required["accepts"][0]
                bind_security_preflight_delivery(
                    consumed[key],
                    out,
                    asset=accepted["asset"],
                    currency="USDC",
                    currency_decimals=6,
                )
                out = _with_commerce_metadata(
                    out, agent, tool, public_base)
                delivery_receipt = None
                if delivery_status == "delivered":
                    out, delivery_receipt = _attach_paid_delivery_receipt(
                        out, consumed[key], agent, tool)
                    _record_delivery_status(
                        consumed[key], delivery_status, delivery_receipt)
                delivery_persisted = False
                try:
                    delivery_persisted = bool(store.save(agent, core))
                except Exception:
                    logger.error(
                        "x402_v2[%s]: delivery outcome persistence failed",
                        agent,
                    )
                if delivery_persisted:
                    try:
                        enqueue_from_environment(
                            consumed[key],
                            prior_settlements=consumed.values(),
                        )
                    except Exception as exc:
                        logger.error(
                            "x402_v2[%s]: commercial export refused: %s",
                            agent,
                            type(exc).__name__,
                        )
                return _resp(out, 200, paid_headers)
        except Exception as exc:
            logger.exception("x402 v2 route failed closed")
            return _resp({"error": f"x402 v2 error: {type(exc).__name__}"},
                         500)
        reqs = dict(x402_rail.build_accepts(agent, price, resource))
        reqs["description"] = (f"{meta['description']} MCP pointer: "
                               f"{public_base}/{agent}/mcp tool={tool}")
        # CDP Bazaar's backwards-compatible v1 discovery hook. It indexes
        # this after a successful settle; no dashboard registration exists.
        reqs["outputSchema"] = OUTPUT_SCHEMA
        body = {"x402Version": x402_rail.X402_VERSION, "accepts": [reqs]}

        xpay = request.headers.get("x-payment")
        if not xpay:                                           # H402-1
            return _resp({**body, "error": "X-PAYMENT required"}, 402)
        payload = x402_rail.parse_payment_header(xpay)
        if payload is None:
            return _resp({**body, "error": "malformed X-PAYMENT"}, 402)

        gate_state = getattr(core, GATE_ATTR, None)
        inner = getattr(core, "_gate_inner", None)
        if gate_state is None or inner is None:
            return _resp({"error": "agent is not gated"}, 500)
        key = hashlib.sha256(xpay.encode()).hexdigest()
        consumed = gate_state.setdefault("consumed_x402", {})
        if key in consumed:                                    # H402-3
            return _resp({**body, "error": "payment already consumed"}, 402)

        result = x402_rail.verify_and_settle(payload, reqs)    # H402-2
        if not result.get("settled"):                          # H402-7
            return _resp({**body,
                          "error": f"settlement failed: {result.get('reason')}"},
                         402)
        consumed[key] = {"tx_hash": result["tx_hash"],
                         "network": result["network"],
                         "amount_atomic": result["amount_atomic"],
                         "credits": 1,
                         "at": time.strftime("%Y-%m-%d", time.gmtime()),
                         "surface": "http-402"}                # H402-5
        try:
            store.save(agent, core)
        except Exception:
            logger.critical("x402_http[%s]: SETTLED tx=%s but persist failed "
                            "— tx hash is the receipt", agent,
                            result["tx_hash"])

        # H402-4: execute via the ungated inner (payment already made).
        args = {k: v for k, v in args.items() if k != "action"}
        try:
            out = inner({"action": action, **args})
            if asyncio.iscoroutine(out):
                out = await out
            try:
                store.save(agent, core)
            except Exception:
                pass
        except Exception as exc:                               # H402-7
            logger.exception("x402_http[%s]: tool exec failed after settle",
                             agent)
            out = {"status": "error", "error_type": "tool_error",
                   "message": f"paid call errored: {type(exc).__name__} "
                              "(payment settled; contact support with the tx)",
                   "tx_hash": result["tx_hash"]}
        delivery_status = _paid_delivery_status(out)
        _record_delivery_status(consumed[key], delivery_status)
        out = _with_commerce_metadata(out, agent, tool, public_base)
        delivery_receipt = None
        if delivery_status == "delivered":
            out, delivery_receipt = _attach_paid_delivery_receipt(
                out, consumed[key], agent, tool)
            _record_delivery_status(
                consumed[key], delivery_status, delivery_receipt)
        try:
            store.save(agent, core)
        except Exception:
            logger.error(
                "x402_http[%s]: delivery outcome persistence failed",
                agent,
            )
        receipt = base64.b64encode(json.dumps(
            result.get("settlement_receipt")
            or {"transaction": result["tx_hash"]}).encode()).decode()
        return _resp(out, 200, {
                "X-PAYMENT-RESPONSE": receipt,
                "X-Payment-Tx": result["tx_hash"]})

    return handler
