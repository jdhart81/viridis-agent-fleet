"""Deterministic buyer-side value decisions for the Viridis fleet.

This module removes a discovery gap without adding another agent or payment
rail.  An autonomous buyer supplies an objective, the names of the inputs it
already controls, and an optional list-price ceiling.  The result is one of:

* REQUEST_QUOTE -- one existing route is a fit and its required input shape is
  ready for a fresh, authoritative unpaid HTTP 402;
* NEEDS_INPUT -- the route is a fit, but buyer-owned inputs are missing or do
  not match the advertised schema;
* BUDGET_TOO_LOW -- the best-fit route exceeds the caller's ceiling; or
* NO_MATCH -- the fleet should not manufacture a recommendation.

The same free endpoint also accepts a ``WORKFLOW`` decision.  That path asks
whether a buyer should use one shipped route, commission the existing Viridis
Agent Reliability Sprint, or leave the workflow manual.  It returns one of:

* BUY -- one existing route is a bounded single-result fit;
* BUILD -- the stated workflow fits the fixed-scope Reliability Sprint and its
  conservatively modelled payback is inside the buyer's target;
* DO_NOT_AUTOMATE -- the supplied economics do not clear the buyer's target;
* NEEDS_INPUT -- scope, access, acceptance, or human-approval facts are absent.

VD1 READ ONLY: the decision endpoint never signs, pays, settles, executes, or
    persists a tool call.
VD2 OBJECTIVE FIRST: price never substitutes a cheaper but irrelevant route.
VD3 FAIL CLOSED: no lexical fit produces NO_MATCH, not a forced recommendation.
VD4 BUYER INPUTS: missing facts are named and never inferred from prior calls.
VD5 LIVE QUOTE: list prices are screening data only; the unpaid 402 is the
    authoritative payment requirement.
VD6 CLAIM BOUNDARY: delivery receipts prove seller-side transport, not buyer
    acceptance, usefulness, adoption, legal advice, or future demand.
VD7 DEMAND FIRST: BUILD is available only for the existing Sprint profile; it
    never creates another fleet agent or treats a listing as demand.
VD8 CONSERVATIVE VALUE: workflow payback uses a disclosed 50% realization
    factor and remains a screening estimate, not a savings guarantee.
"""
from __future__ import annotations

import json
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


SPEC_VERSION = "viridis-agent-value-decision-v2"
DECISION_PATH = "/x402/decide"
SPRINT_LIST_PRICE_MINOR = 99_500
SPRINT_DELIVERY_BUSINESS_DAYS = 5
WATCH_LIST_PRICE_MINOR = 14_900
VALUE_REALIZATION_BPS = 5_000

WORKFLOW_REQUIRED_FIELDS = (
    "delivery_shape",
    "runs_per_month",
    "minutes_per_run",
    "loaded_hourly_cost_minor",
    "monthly_error_cost_minor",
    "implementation_budget_minor",
    "monthly_operating_cost_minor",
    "target_payback_months",
    "systems",
    "data_access_ready",
    "acceptance_criteria_ready",
    "irreversible_actions",
    "human_approval_available",
)
IRREVERSIBLE_ACTIONS = {
    "account_change",
    "customer_message",
    "data_deletion",
    "legal_acceptance",
    "other",
    "payment",
    "publication",
}


# Intent terms are deliberately narrow.  Generic words such as "agent",
# "analysis", "audit", and "data" are excluded because they would make the
# gateway recommend a paid route when the fleet has no clear job fit.
VALUE_PROFILES: dict[tuple[str, str], dict[str, Any]] = {
    ("taxcredit-engine", "signed_cliff_check"): {
        "job": "Prepare a signed 48E or 45Y scenario report for a commercial solar project.",
        "outcome": "An engine-sourced tax-credit scenario, missing-fact flags, source trail, and verifiable signature.",
        "not_for": "Tax advice, verified construction start, guaranteed eligibility, or filing.",
        "keywords": {"48e", "45y", "cliff", "solar"},
        "phrases": ("signed cliff check", "commercial solar tax credit", "c&i solar"),
    },
    ("wu-wei-router", "plan_workload"): {"job": "Plan lower-cost workload routing under declared quality and latency requirements.", "outcome": "Eligible route selections and modeled savings after the planning fee.", "not_for": "Autonomous execution, measured savings, energy certification or guaranteed quality.", "keywords": {"wu", "wei", "routing"}, "phrases": ("wu wei", "wu-wei", "workload routing", "compute routing", "routing cost")},
    ("maxwell-defense", "rehearse_defense"): {
        "job": "Rehearse a bounded proof-of-work admission policy for an agent endpoint.",
        "outcome": "Client-budget policy model, local hash microbenchmark and deployment acceptance checks.",
        "not_for": "Activated runtime protection, measured energy savings, guaranteed availability or security certification.",
        "keywords": {"maxwell", "puzzle", "rehearsal"},
        "phrases": ("maxwell defense", "proof-of-work policy", "proof of work policy", "proof of work challenge", "proof-of-work challenge", "defense rehearsal", "client puzzle"),
    },
    ("security-preflight", "scan_source"): {
        "job": "Review caller-supplied inline source for VulnCanon security indicators.",
        "outcome": "Bounded, redacted pattern/corroboration matches and mitigation references with a signed receipt.",
        "not_for": "Proven exploitation, repository fetching, runtime testing or formal code verification.",
        "keywords": {"vulncanon", "source", "code", "scanner"},
        "phrases": ("source scan", "scan source", "scan code", "inline source", "vulncanon"),
    },
    ("security-preflight", "screen_injection"): {
        "job": "Screen supplied text samples for deterministic injection indicators.",
        "outcome": "Redacted pattern matches for up to twenty samples and a signed receipt, without model calls.",
        "not_for": "Guaranteed attack detection, calibrated probabilities, runtime protection or model-based analysis.",
        "keywords": {"screen", "screening", "text", "texts", "samples", "messages", "prompts", "injection"},
        "phrases": ("screen injection", "injection screening", "screen text", "text samples", "prompt injection", "injection detection"),
    },
    ("regulatory-radar", "scan_regulations"): {
        "job": "Find which climate or energy requirements need review.",
        "outcome": (
            "A bounded, structured regulation shortlist with jurisdiction, "
            "urgency, effective-date, and next-check signals."),
        "not_for": (
            "Legal advice, an exhaustive legal search, or a live external "
            "regulatory feed."),
        "keywords": {
            "applicability", "climate", "compliance", "energy", "jurisdiction",
            "regulation", "regulations", "regulatory", "requirement",
            "requirements", "screen", "scan",
        },
        "phrases": (
            "applicable regulations", "compliance requirements",
            "regulation scan", "regulatory requirements",
            "which regulations",
        ),
    },
    ("regulatory-radar", "monitor_changes"): {
        "job": "Decide which dated regulatory changes or deadlines need review now.",
        "outcome": (
            "A bounded, source-linked window of recently effective requirements "
            "and approaching key dates with alert levels and review actions."),
        "not_for": (
            "A scheduled monitoring service, automatic alert delivery, legal "
            "advice, or a live external feed."),
        "keywords": {
            "change", "changes", "deadline", "deadlines", "effective",
            "monitor", "monitoring", "watch", "window",
        },
        "phrases": (
            "compliance deadlines", "effective dates", "key dates",
            "monitor changes", "regulatory changes", "regulatory deadlines",
        ),
    },
    ("taxcredit-engine", "calculate_tax_credit"): {
        "job": "Estimate a supported US clean-energy tax-credit scenario.",
        "outcome": (
            "A deterministic credit estimate with eligibility assumptions and "
            "an audit trace for supported 45Q, 45V, 45Y, 48E, or 45X facts."),
        "not_for": "Tax advice, filing, or eligibility facts the buyer does not supply.",
        "keywords": {
            "45q", "45v", "45x", "45y", "48e", "credit", "credits",
            "incentive", "incentives", "tax",
        },
        "phrases": (
            "clean energy credit", "clean energy tax", "tax credit",
        ),
    },
    ("ghg-ledger", "calculate_inventory"): {
        "job": "Calculate a greenhouse-gas inventory from activity records.",
        "outcome": (
            "Deterministic Scope 1, 2, and 3 totals with auditable factor and "
            "activity traces."),
        "not_for": "Inventing missing activity data or independently verifying source records.",
        "keywords": {
            "carbon", "emissions", "ghg", "greenhouse", "inventory", "scope",
        },
        "phrases": (
            "carbon accounting", "emissions inventory", "greenhouse gas",
            "scope 1", "scope 2", "scope 3",
        ),
    },
    ("quantity-takeoff", "calculate_takeoff"): {
        "job": "Turn buyer-supplied construction geometry into material quantities.",
        "outcome": (
            "An auditable material quantity takeoff suitable for embodied-carbon "
            "and downstream inventory inputs."),
        "not_for": "Image detection, missing geometry, or professional quantity-surveyor signoff.",
        "keywords": {
            "assembly", "bill", "bom", "construction", "embodied", "geometry",
            "material", "materials", "quantity", "takeoff",
        },
        "phrases": (
            "bill of materials", "embodied carbon", "material quantities",
            "quantity takeoff",
        ),
    },
    ("disclosure-compiler", "compile_disclosure"): {
        "job": "Compile supplied climate evidence into a disclosure draft and gap list.",
        "outcome": (
            "A structured CSRD, IFRS S2, or TCFD-aligned draft with evidence "
            "links, assumptions, and unresolved gaps."),
        "not_for": "Filing, assurance, legal advice, or fabricating missing evidence.",
        "keywords": {
            "csrd", "disclosure", "disclosures", "ifrs", "report", "reporting",
            "sustainability", "tcfd",
        },
        "phrases": (
            "climate disclosure", "ifrs s2", "sustainability disclosure",
        ),
    },
    ("hive", "solve"): {
        "job": "Get a bounded multi-agent answer with cross-review and an audit digest.",
        "outcome": (
            "A cost-bounded three-worker synthesis that retains only "
            "review-surviving contributions and returns a content-addressed audit."),
        "not_for": (
            "Open-ended autonomous work, guaranteed correctness, or tasks that "
            "lack buyer-supplied context and acceptance criteria."),
        "keywords": {
            "complex", "cross-review", "multi-agent", "orchestrate",
            "orchestration", "reviewed", "solver", "synthesis",
        },
        "phrases": (
            "multi agent", "reviewed recommendation", "reviewed solve",
        ),
    },
    ("security-preflight", "security_preflight"): {
        "job": "Statically screen buyer-supplied agent artifacts before deployment.",
        "outcome": (
            "A bounded verdict over an MCP manifest, tool schemas, authority "
            "policy, and sample text with a signed, input-redacted receipt."),
        "not_for": (
            "Fetching or executing the target, scanning a repository, runtime "
            "penetration testing, or certifying that an agent is secure."),
        "keywords": {
            "injection", "manifest", "mcp", "policy", "preflight", "schema",
            "schemas", "secure", "security", "tool",
        },
        "phrases": (
            "agent security", "mcp security",
            "security preflight", "tool policy",
        ),
    },
}


if os.environ.get("WU_WEI_FLEET_ENABLED") != "1":
    VALUE_PROFILES.pop(("wu-wei-router", "plan_workload"))

if os.environ.get("MAXWELL_FLEET_ENABLED") != "1":
    VALUE_PROFILES.pop(("maxwell-defense", "rehearse_defense"))


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _fit_score(objective: str, profile: dict[str, Any]) -> tuple[int, list[str]]:
    lowered = objective.lower()
    tokens = _tokens(objective)
    matched_phrases = [
        phrase for phrase in profile["phrases"] if phrase in lowered
    ]
    matched_keywords = sorted(tokens & set(profile["keywords"]))
    # Phrases carry the decision.  Keywords break ties and allow concise agent
    # objectives such as "45V" or "CSRD" without broad semantic guessing.
    score = 20 * len(matched_phrases) + 3 * len(matched_keywords)
    return score, [*matched_phrases, *matched_keywords]


def route_value_contract(agent: str, tool: str) -> dict[str, Any]:
    """Return public value/claim metadata without exposing ranking internals."""
    profile = VALUE_PROFILES[(agent, tool)]
    return {
        "spec_version": SPEC_VERSION,
        "job_to_be_done": profile["job"],
        "expected_outcome": profile["outcome"],
        "not_for": profile["not_for"],
        "proof_contract": {
            "quote_authority": "live_unpaid_http_402",
            "paid_transport_receipt": "viridis-paid-delivery-v1",
            "buyer_acceptance": "not_proven_by_seller_receipt",
            "usefulness": "not_proven_by_seller_receipt",
        },
    }


def decision_discovery(public_base: str) -> dict[str, Any]:
    base = public_base.rstrip("/")
    return {
        "spec_version": SPEC_VERSION,
        "endpoint": base + DECISION_PATH,
        "methods": ["GET", "POST"],
        "price_minor": 0,
        "state_changing": False,
        "payment_signed": False,
        "tool_executed": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string", "minLength": 3, "maxLength": 1000},
                "inputs": {"type": "object"},
                "max_price_minor": {"type": ["integer", "null"], "minimum": 0},
                "decision_type": {
                    "type": "string", "enum": ["ROUTE", "WORKFLOW"],
                    "default": "ROUTE",
                },
                "workflow": {
                    "type": ["object", "null"],
                    "properties": {
                        "delivery_shape": {
                            "type": "string",
                            "enum": ["SINGLE_RESULT", "INTEGRATED_WORKFLOW"],
                        },
                        "runs_per_month": {
                            "type": "integer", "minimum": 1,
                            "maximum": 100000,
                        },
                        "minutes_per_run": {
                            "type": "number", "minimum": 0,
                            "maximum": 1440,
                        },
                        "loaded_hourly_cost_minor": {
                            "type": "integer", "minimum": 0,
                            "maximum": 10000000,
                        },
                        "monthly_error_cost_minor": {
                            "type": "integer", "minimum": 0,
                            "maximum": 100000000,
                        },
                        "implementation_budget_minor": {
                            "type": "integer", "minimum": 0,
                            "maximum": 10000000,
                        },
                        "monthly_operating_cost_minor": {
                            "type": "integer", "minimum": 0,
                            "maximum": 10000000,
                        },
                        "target_payback_months": {
                            "type": "integer", "minimum": 1, "maximum": 36,
                        },
                        "systems": {
                            "type": "array", "maxItems": 20,
                            "items": {"type": "string", "minLength": 1,
                                      "maxLength": 120},
                        },
                        "data_access_ready": {"type": "boolean"},
                        "acceptance_criteria_ready": {"type": "boolean"},
                        "irreversible_actions": {
                            "type": "array", "uniqueItems": True,
                            "items": {"type": "string",
                                      "enum": sorted(IRREVERSIBLE_ACTIONS)},
                        },
                        "human_approval_available": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
            },
            "required": ["objective"],
            "additionalProperties": False,
        },
        "route_decisions": [
            "REQUEST_QUOTE", "NEEDS_INPUT", "BUDGET_TOO_LOW", "NO_MATCH"
        ],
        "workflow_decisions": [
            "BUY", "BUILD", "DO_NOT_AUTOMATE", "NEEDS_INPUT"
        ],
        "reliability_sprint": {
            "existing_profile_id": "viridis-mcp-delivery",
            "list_price_minor": SPRINT_LIST_PRICE_MINOR,
            "delivery_business_days": SPRINT_DELIVERY_BUSINESS_DAYS,
            "new_agent_created": False,
        },
    }


def _missing_fields(required: list[str], inputs: dict[str, Any]) -> list[str]:
    missing = []
    for field in required:
        value = inputs.get(field)
        # Empty arrays/objects can be valid according to the advertised JSON
        # schema (for example, a zero-activity GHG inventory).  Let the schema
        # validator decide those cases instead of inventing a stricter rule.
        if field not in inputs or value is None or value == "":
            missing.append(field)
    return missing


def _bounded_integer(value: Any, field: str, *, minimum: int,
                     maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"workflow.{field} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(
            f"workflow.{field} must be within {minimum}..{maximum}")
    return value


def _bounded_decimal(value: Any, field: str, *, minimum: Decimal,
                     maximum: Decimal) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"workflow.{field} must be a number")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"workflow.{field} must be a number") from exc
    if not number.is_finite() or not minimum <= number <= maximum:
        raise ValueError(
            f"workflow.{field} must be within {minimum}..{maximum}")
    return number


def _workflow_common(public_base: str, objective: str,
                     workflow: dict[str, Any]) -> dict[str, Any]:
    return {
        "spec_version": SPEC_VERSION,
        "decision_type": "WORKFLOW",
        "objective": objective,
        "workflow": workflow,
        "money_moved": False,
        "payment_authorized": False,
        "tool_executed": False,
        "offer_submitted": False,
        "work_started": False,
        "new_agent_created": False,
        "next_action_requires_buyer_authorization": True,
        "agent_market": public_base.rstrip("/") + "/network/catalog",
    }


def build_workflow_value_decision(
    public_base: str,
    objective: str,
    *,
    workflow: dict[str, Any] | None,
    inputs: dict[str, Any] | None = None,
    max_price_minor: int | None = None,
) -> dict[str, Any]:
    """Qualify one buyer workflow without submitting work or an offer."""
    if not isinstance(objective, str) or not 3 <= len(objective.strip()) <= 1000:
        raise ValueError("objective must be a 3-1000 character string")
    objective = objective.strip()
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be an object")
    if (max_price_minor is not None
            and (isinstance(max_price_minor, bool)
                 or not isinstance(max_price_minor, int)
                 or max_price_minor < 0)):
        raise ValueError(
            "max_price_minor must be a non-negative integer or null")
    if workflow is None:
        workflow = {}
    if not isinstance(workflow, dict):
        raise ValueError("workflow must be an object")
    unknown = set(workflow) - set(WORKFLOW_REQUIRED_FIELDS)
    if unknown:
        raise ValueError(
            "unknown workflow fields: " + ", ".join(sorted(unknown)))
    common = _workflow_common(public_base, objective, workflow)
    missing = [field for field in WORKFLOW_REQUIRED_FIELDS
               if field not in workflow or workflow[field] is None]
    if missing:
        return {
            **common,
            "decision": "NEEDS_INPUT",
            "reason": "Buyer-owned workflow facts are incomplete.",
            "missing_buyer_inputs": missing,
            "blocking_reasons": ["missing_workflow_facts"],
        }

    shape = str(workflow["delivery_shape"]).strip().upper()
    if shape not in {"SINGLE_RESULT", "INTEGRATED_WORKFLOW"}:
        raise ValueError(
            "workflow.delivery_shape must be SINGLE_RESULT or "
            "INTEGRATED_WORKFLOW")
    runs = _bounded_integer(
        workflow["runs_per_month"], "runs_per_month", minimum=1,
        maximum=100000)
    minutes = _bounded_decimal(
        workflow["minutes_per_run"], "minutes_per_run",
        minimum=Decimal("0"), maximum=Decimal("1440"))
    hourly = _bounded_integer(
        workflow["loaded_hourly_cost_minor"], "loaded_hourly_cost_minor",
        minimum=0, maximum=10000000)
    error_cost = _bounded_integer(
        workflow["monthly_error_cost_minor"], "monthly_error_cost_minor",
        minimum=0, maximum=100000000)
    budget = _bounded_integer(
        workflow["implementation_budget_minor"],
        "implementation_budget_minor", minimum=0, maximum=10000000)
    operating = _bounded_integer(
        workflow["monthly_operating_cost_minor"],
        "monthly_operating_cost_minor", minimum=0, maximum=10000000)
    target = _bounded_integer(
        workflow["target_payback_months"], "target_payback_months",
        minimum=1, maximum=36)

    systems = workflow["systems"]
    if not isinstance(systems, list) or len(systems) > 20:
        raise ValueError("workflow.systems must be an array with at most 20 items")
    normalized_systems = []
    for item in systems:
        if not isinstance(item, str) or not 1 <= len(item.strip()) <= 120:
            raise ValueError(
                "workflow.systems items must be 1-120 character strings")
        normalized_systems.append(item.strip())

    for field in ("data_access_ready", "acceptance_criteria_ready",
                  "human_approval_available"):
        if not isinstance(workflow[field], bool):
            raise ValueError(f"workflow.{field} must be boolean")
    actions = workflow["irreversible_actions"]
    if not isinstance(actions, list) or len(actions) > len(IRREVERSIBLE_ACTIONS):
        raise ValueError("workflow.irreversible_actions must be a bounded array")
    normalized_actions = []
    for action in actions:
        normalized = str(action).strip().lower()
        if normalized not in IRREVERSIBLE_ACTIONS:
            raise ValueError(
                "workflow.irreversible_actions contains an unknown action")
        if normalized not in normalized_actions:
            normalized_actions.append(normalized)

    blockers = []
    if not workflow["data_access_ready"]:
        blockers.append("data_or_system_access_not_ready")
    if not workflow["acceptance_criteria_ready"]:
        blockers.append("acceptance_criteria_not_ready")
    if shape == "INTEGRATED_WORKFLOW" and not 1 <= len(normalized_systems) <= 2:
        blockers.append("sprint_requires_one_or_two_existing_systems")
    if normalized_actions and not workflow["human_approval_available"]:
        blockers.append("irreversible_actions_require_human_approval")
    if blockers:
        return {
            **common,
            "decision": "NEEDS_INPUT",
            "reason": (
                "The workflow is not ready for a bounded purchase or Sprint."
            ),
            "missing_buyer_inputs": [],
            "blocking_reasons": blockers,
        }

    labor_value = int((
        Decimal(runs) * minutes * Decimal(hourly) / Decimal(60)
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    gross_value = labor_value + error_cost
    conservative_value = int((
        Decimal(gross_value) * Decimal(VALUE_REALIZATION_BPS)
        / Decimal(10000)
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    economics = {
        "currency": "USD",
        "labor_value_minor": labor_value,
        "monthly_error_cost_minor": error_cost,
        "gross_monthly_value_minor": gross_value,
        "value_realization_bps": VALUE_REALIZATION_BPS,
        "conservative_monthly_value_minor": conservative_value,
        "buyer_stated_monthly_operating_cost_minor": operating,
        "claim_boundary": (
            "Screening estimate only. The 50% realization factor is disclosed; "
            "no savings, revenue, adoption, or payback is guaranteed."
        ),
    }

    route_decision = None
    if shape == "SINGLE_RESULT":
        route_decision = build_value_decision(
            public_base, objective, inputs=inputs,
            max_price_minor=max_price_minor)
        if route_decision["decision"] == "NEEDS_INPUT":
            return {
                **common,
                "decision": "NEEDS_INPUT",
                "reason": (
                    "A shipped route fits, but its buyer-owned input shape is "
                    "not ready."
                ),
                "missing_buyer_inputs": route_decision["selected"][
                    "missing_buyer_inputs"],
                "blocking_reasons": ["existing_route_inputs_not_ready"],
                "existing_route_decision": route_decision,
                "economics": economics,
            }
        if route_decision["decision"] == "REQUEST_QUOTE":
            selected = route_decision["selected"]
            monthly_list_cost = int(selected["list_price_minor"]) * runs
            monthly_net_value = conservative_value - monthly_list_cost - operating
            economics["existing_route_monthly_list_cost_minor"] = monthly_list_cost
            economics["conservative_monthly_net_value_minor"] = monthly_net_value
            if monthly_net_value <= 0:
                return {
                    **common,
                    "decision": "DO_NOT_AUTOMATE",
                    "reason": (
                        "The existing route fits, but its screened monthly cost "
                        "does not clear the conservative monthly value."
                    ),
                    "economics": economics,
                    "existing_route_decision": route_decision,
                }
            return {
                **common,
                "decision": "BUY",
                "reason": (
                    "One shipped route fits this single-result job. Fetch its "
                    "fresh unpaid 402 before any separate buyer payment mandate."
                ),
                "economics": economics,
                "existing_route_decision": route_decision,
                "sprint_required": False,
            }

    monthly_net_value = conservative_value - operating
    economics["conservative_monthly_net_value_minor"] = monthly_net_value
    if monthly_net_value > 0:
        payback = (
            Decimal(SPRINT_LIST_PRICE_MINOR) / Decimal(monthly_net_value)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        economics["sprint_payback_months"] = str(payback)
    else:
        payback = None
        economics["sprint_payback_months"] = None

    failed_reasons = []
    if budget < SPRINT_LIST_PRICE_MINOR:
        failed_reasons.append("implementation_budget_below_sprint_price")
    if payback is None or payback > Decimal(target):
        failed_reasons.append("payback_exceeds_buyer_target")
    if failed_reasons:
        return {
            **common,
            "decision": "DO_NOT_AUTOMATE",
            "reason": (
                "The workflow does not clear the buyer's stated budget and "
                "payback screen under conservative value assumptions."
            ),
            "economics": economics,
            "blocking_reasons": failed_reasons,
            "existing_route_decision": route_decision,
        }

    return {
        **common,
        "decision": "BUILD",
        "reason": (
            "The complete scope fits the existing Agent Reliability Sprint and "
            "clears the buyer's conservative budget/payback screen."
        ),
        "economics": economics,
        "sprint": {
            "existing_profile_id": "viridis-mcp-delivery",
            "name": "Viridis Agent Reliability Sprint",
            "list_price_minor": SPRINT_LIST_PRICE_MINOR,
            "delivery_business_days": SPRINT_DELIVERY_BUSINESS_DAYS,
            "scope": "one workflow and up to two existing systems or APIs",
            "funding_required_before_work": True,
            "funding_evidence": "independently_verified_live_cash_escrow",
            "offer_submitted_by_this_decision": False,
        },
        "optional_follow_on": {
            "name": "Viridis Reliability Watch",
            "list_price_minor_per_month": WATCH_LIST_PRICE_MINOR,
            "included": False,
            "auto_enrolled": False,
            "active_subscription_created": False,
        },
        "existing_route_decision": route_decision,
    }


def build_value_decision(
    public_base: str,
    objective: str,
    *,
    inputs: dict[str, Any] | None = None,
    max_price_minor: int | None = None,
) -> dict[str, Any]:
    """Select one relevant existing route without authorizing a purchase."""
    from payment_gate import DEFAULT_PRICE_MINOR, PRICE_MINOR
    from x402_http import (
        X402_HTTP_METADATA,
        X402_HTTP_TOOLS,
        _normalize_request_args,
        next_paid_routes,
    )
    import x402_rail

    if not isinstance(objective, str) or not 3 <= len(objective.strip()) <= 1000:
        raise ValueError("objective must be a 3-1000 character string")
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be an object")
    if (max_price_minor is not None
            and (isinstance(max_price_minor, bool)
                 or not isinstance(max_price_minor, int)
                 or max_price_minor < 0)):
        raise ValueError("max_price_minor must be a non-negative integer or null")

    objective = objective.strip()
    ranked = []
    for route in X402_HTTP_TOOLS:
        if route not in VALUE_PROFILES:
            continue
        score, signals = _fit_score(objective, VALUE_PROFILES[route])
        if score <= 0:
            continue
        price = int(PRICE_MINOR.get(route[0], DEFAULT_PRICE_MINOR))
        ranked.append((score, -len(signals), f"{route[0]}/{route[1]}", route,
                       signals, price))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))

    common = {
        "spec_version": SPEC_VERSION,
        "objective": objective,
        "max_price_minor": max_price_minor,
        "money_moved": False,
        "payment_authorized": False,
        "tool_executed": False,
        "next_action_requires_buyer_authorization": True,
    }
    if not ranked:
        return {
            **common,
            "decision": "NO_MATCH",
            "reason": (
                "The objective has no narrow lexical fit to a shipped Viridis "
                "paid route. No paid recommendation was manufactured."),
            "catalog": public_base.rstrip("/") + "/x402/catalog",
        }

    _, _, _, route, signals, price = ranked[0]
    agent, tool = route
    metadata = X402_HTTP_METADATA[route]
    schema = metadata["input_schema"]
    normalized_inputs = _normalize_request_args(agent, tool, inputs)
    required = list(schema.get("required", []))
    missing = _missing_fields(required, normalized_inputs)
    schema_matches = False
    if not missing:
        try:
            import x402_v2
            schema_matches = bool(
                x402_v2._matches_schema(normalized_inputs, schema))
        except Exception:
            schema_matches = False

    from preflight_origin import service_origin
    endpoint = service_origin(agent, public_base) + f"/x402/{agent}/{tool}"
    selected = {
        "agent": agent,
        "tool": tool,
        "route": f"{agent}/{tool}",
        "endpoint": endpoint,
        "method": "POST",
        "list_price_minor": price,
        "list_amount_atomic_usdc": x402_rail.price_atomic(price),
        "list_price_only": True,
        "matched_intent_signals": signals,
        "value": route_value_contract(agent, tool),
        "input_schema": schema,
        "input_example": metadata["input_example"],
        "required_buyer_inputs": required,
        "provided_input_fields": sorted(str(key) for key in inputs),
        "missing_buyer_inputs": missing,
        "input_shape_ready": bool(not missing and schema_matches),
        "fresh_quote": {
            "endpoint": endpoint,
            "method": "POST",
            "authoritative_for_payment": True,
            "payment_header_required_for_preflight": False,
            "payment_authorized_by_this_decision": False,
        },
        "possible_follow_on_routes": next_paid_routes(
            agent, tool, public_base),
    }
    alternatives = [{
        "route": f"{candidate[3][0]}/{candidate[3][1]}",
        "fit_score": candidate[0],
        "list_price_minor": candidate[5],
    } for candidate in ranked[1:4]]

    if max_price_minor is not None and price > max_price_minor:
        return {
            **common,
            "decision": "BUDGET_TOO_LOW",
            "reason": (
                "The best-fit route exceeds the caller's list-price ceiling. "
                "No cheaper unrelated route was substituted."),
            "selected": selected,
            "alternatives": alternatives,
        }
    if missing or not schema_matches:
        return {
            **common,
            "decision": "NEEDS_INPUT",
            "reason": (
                "The route fits the objective, but buyer-owned inputs are "
                "missing or do not match the advertised schema."),
            "selected": selected,
            "alternatives": alternatives,
        }
    return {
        **common,
        "decision": "REQUEST_QUOTE",
        "reason": (
            "The objective and supplied input shape fit one shipped route "
            "inside the caller's list-price screen. Fetch the unpaid 402; it "
            "is the only authoritative payment requirement."),
        "selected": selected,
        "alternatives": alternatives,
    }


def make_value_decision_route(public_base: str):
    """Return a Starlette handler for the free read-only decision surface."""
    from starlette.responses import JSONResponse

    async def handler(request):
        try:
            if str(getattr(request, "method", "GET")).upper() == "GET":
                payload = dict(getattr(request, "query_params", {}))
                raw_inputs = payload.get("inputs", "{}")
                if isinstance(raw_inputs, str):
                    raw_inputs = json.loads(raw_inputs)
                raw_max = payload.get("max_price_minor")
                if raw_max in {None, "", "null"}:
                    raw_max = None
                elif isinstance(raw_max, str):
                    raw_max = int(raw_max)
                payload["inputs"] = raw_inputs
                payload["max_price_minor"] = raw_max
                raw_workflow = payload.get("workflow")
                if isinstance(raw_workflow, str):
                    raw_workflow = json.loads(raw_workflow)
                payload["workflow"] = raw_workflow
            else:
                payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("request body must be an object")
            unknown = set(payload) - {
                "decision_type", "objective", "inputs", "max_price_minor",
                "workflow",
            }
            if unknown:
                raise ValueError(
                    "unknown fields: " + ", ".join(sorted(unknown)))
            decision_type = str(
                payload.get("decision_type") or "ROUTE").strip().upper()
            if decision_type == "ROUTE":
                if payload.get("workflow") not in (None, {}):
                    raise ValueError(
                        "workflow is only accepted for WORKFLOW decisions")
                result = build_value_decision(
                    public_base,
                    payload.get("objective"),
                    inputs=payload.get("inputs"),
                    max_price_minor=payload.get("max_price_minor"),
                )
                result["decision_type"] = "ROUTE"
            elif decision_type == "WORKFLOW":
                result = build_workflow_value_decision(
                    public_base,
                    payload.get("objective"),
                    workflow=payload.get("workflow"),
                    inputs=payload.get("inputs"),
                    max_price_minor=payload.get("max_price_minor"),
                )
            else:
                raise ValueError("decision_type must be ROUTE or WORKFLOW")
            return JSONResponse(result)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return JSONResponse({
                "spec_version": SPEC_VERSION,
                "decision": "INVALID_REQUEST",
                "error": str(exc),
                "money_moved": False,
                "payment_authorized": False,
                "tool_executed": False,
            }, status_code=400)

    return handler
