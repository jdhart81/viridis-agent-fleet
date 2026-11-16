"""
First-call starters: say when to use a server, and offer ready-made prompts.

MOTIVATION (fleet funnel, 2026-11-16):
Outside agent hosts (Claude-User, coda-agent-runtime, node, python-httpx)
connect to the hosted servers every day and list tools, then stop. Almost
no outside call computes. Hosts put a server's ``instructions`` in the
model's context, and ours were one-line taglines that never said when the
tools apply. No fleet server offered MCP prompts, the user-facing starters
that hosts show as "add from <connector>" or slash commands.

``apply_starters(mcp, key)`` fixes both in one place per adapter:
  - it replaces the server's ``instructions`` with a short, factual "use
    this server when" text for that agent, and
  - it registers a few MCP prompts that turn a user's own numbers into the
    first tool call (and, for Radar, a repeat call).

INVARIANTS (verified in test_starters.py):
  S1. Tools are untouched: names, schemas, annotations and results of
      ``tools/list`` and ``tools/call`` are the same before and after.
  S2. Each prompt only renders a user message from the arguments given. It
      calls no tool, reads no data, stores nothing and charges nothing.
  S3. Every prompt and instruction names only tools that exist on that
      server, or on a named sibling server for a cross-server chain.
  S4. Texts claim nothing that was not tested: free calls per day, coverage,
      and "a screening / a draft for review, not a determination / filing".
      No price, payment instruction or promotional wording is in any prompt.
  S5. Without the ``mcp`` SDK (stdlib smoke shim) it is a no-op that returns
      0 and never raises. An unknown key is a no-op too.
  S6. Idempotent: a second call registers nothing new.
  S7. Instructions stay under 1,200 characters; prompt descriptions under
      200; prompt names are snake_case and unique per server.

Usage (once, after the last ``@mcp.tool`` and after flag_error_results):
    from fleet_utils.starters import apply_starters
    apply_starters(mcp, "ghg-ledger")
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

FREE_LINE = "The first 10 calls per day are free, with no key or account."

INSTRUCTIONS: Dict[str, str] = {
    "ghg-ledger": (
        "Use this server when someone wants greenhouse-gas emissions (a carbon "
        "footprint) calculated from their own activity data: electricity in kWh, "
        "natural gas, diesel, propane or gasoline, refrigerants, travel, waste or "
        "spend. Call calculate_inventory with one activity per line "
        "(activity_type, quantity, unit, region, year). It returns Scope 1, 2 and 3 "
        "totals in tCO2e, the emission factor and source used on every line, and an "
        "audit hash that verify_result can recheck. US electricity covers all 27 EPA "
        "eGRID subregions; fuels are US 2025 onward; the UK grid is 2025. A line it "
        "cannot determine comes back as indeterminate with the reason, never a "
        "guess. list_factor_packs shows the activity types and regions. For a "
        "California SB 253 report, pass the result's data object to the "
        "disclosure-compiler server's compile_disclosure with framework ca-sb253. "
        + FREE_LINE + " This is calculation, not advice."
    ),
    "regulatory-radar": (
        "Use this server when someone asks which climate or sustainability "
        "disclosure rules may apply to a company, or what deadlines are coming: "
        "for example California SB 253 and SB 261, SEC climate rules, EU CSRD and "
        "ESRS, ISSB and TNFD, across eu, uk, us, california, ca (Canada), au, jp, sg "
        "and global. scan_regulations lists rules with effective dates, urgency and "
        "source links; assess_compliance checks one company; watch_changes reports "
        "text changes on official regulator pages since the cursor from the last "
        "answer, so call it again later with that cursor to see only what is new. "
        + FREE_LINE + " Results are a screening with sources, not a legal "
        "determination of whether a company is covered."
    ),
    "disclosure-compiler": (
        "Use this server to draft a climate disclosure from facts the user "
        "supplies: California SB 253 first-cycle Scope 1 and 2 (ca-sb253), ESRS E1, "
        "IFRS S2, SEC climate and TNFD. Pass a ghg-ledger calculate_inventory "
        "result's data object as ghg_result to fill the emission datapoints; it is "
        "verified before use. Missing facts are listed as gaps and never invented. "
        "list_frameworks shows what each framework needs. " + FREE_LINE + " The "
        "output is a cited draft for professional review, not a filing and not a "
        "decision on whether the company is covered."
    ),
}


def _num(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip()
    return text or None


# --- prompt bodies (S2: render text only) -------------------------------

def _footprint_from_bills(electricity_kwh: str, year: str,
                          electricity_region: str = "",
                          natural_gas_therms: str = "",
                          organization: str = "") -> str:
    region = _num(electricity_region) or "US"
    who = _num(organization) or "my organization"
    lines = [f"- purchased electricity: {electricity_kwh} kWh, region {region}, year {year}"]
    if _num(natural_gas_therms):
        lines.append(f"- natural gas: {natural_gas_therms} therm, region US, year {year}")
    return (
        f"Calculate the Scope 1 and 2 emissions of {who} for {year} with the GHG "
        "Ledger tool calculate_inventory, one activity per line:\n"
        + "\n".join(lines)
        + "\nShow the total in tCO2e, each line's emission factor and source, and "
        "any line that came back indeterminate with its reason. If my region "
        "is not one the ledger lists, use list_factor_packs and tell me which "
        "region you used instead."
    )


def _which_rules_apply(jurisdiction: str, sector: str = "",
                       topic: str = "") -> str:
    extra = []
    if _num(sector):
        extra.append(f"sector {sector}")
    if _num(topic):
        extra.append(f"looking for {topic}")
    scope = f" ({', '.join(extra)})" if extra else ""
    return (
        f"Use the Regulatory Radar tool scan_regulations for {jurisdiction}{scope}. "
        "List the climate disclosure rules that may apply, each with its "
        "effective date or next deadline and its source link, nearest deadline "
        "first. This is a screening, so do not tell me whether we are legally "
        "covered. At the end, ask whether I want you to check later for changes "
        "to these rules."
    )


def _what_changed(jurisdiction: str, cursor: str = "") -> str:
    since = _num(cursor) or "0"
    return (
        f"Use the Regulatory Radar tool watch_changes for {jurisdiction} with "
        f"since={since}. Tell me which official pages changed, when the change "
        "was detected and a one-line summary of each diff, then give me the "
        "cursor from the answer so I can ask again next time and see only "
        "what is new."
    )


def _sb253_first_draft(company: str, reporting_year: str, electricity_kwh: str,
                       electricity_region: str = "",
                       natural_gas_therms: str = "") -> str:
    region = _num(electricity_region) or "US-CAMX"
    gas = (f" and natural gas {natural_gas_therms} therm (region US)"
           if _num(natural_gas_therms) else "")
    return (
        f"Prepare a first-cycle California SB 253 Scope 1 and 2 draft for {company}, "
        f"reporting year {reporting_year}, for professional review.\n"
        f"1. With the GHG Ledger tool calculate_inventory, compute purchased "
        f"electricity {electricity_kwh} kWh (region {region}){gas}, year "
        f"{reporting_year}.\n"
        "2. With the Disclosure Compiler tool compile_disclosure, use framework "
        "ca-sb253, company_facts with company_name and reporting_period, and pass "
        "the inventory result's data object as ghg_result. For options."
        "applicability, ask me why SB 253 applies to us and use my words; do "
        "not decide it yourself.\n"
        "Show the draft, every gap it lists, and the verify link. Do not call it "
        "a filing. If the GHG Ledger tools are not available, tell me what to "
        "connect and stop."
    )


PromptSpec = Dict[str, Any]

PROMPTS: Dict[str, List[PromptSpec]] = {
    "ghg-ledger": [{
        "name": "footprint_from_bills",
        "title": "Carbon footprint from my bills",
        "description": "Scope 1 and 2 emissions from your electricity (and gas) "
                       "use for one year, with the factor and source on every line.",
        "fn": _footprint_from_bills,
        "tools": ["calculate_inventory", "list_factor_packs"],
    }],
    "regulatory-radar": [{
        "name": "which_climate_rules_apply",
        "title": "Which climate rules may apply to us?",
        "description": "Screen one jurisdiction's climate disclosure rules, with "
                       "deadlines and source links.",
        "fn": _which_rules_apply,
        "tools": ["scan_regulations"],
    }, {
        "name": "what_changed_since_last_time",
        "title": "What changed in the climate rules?",
        "description": "Changes on official regulator pages since your last check; "
                       "keep the cursor to ask again later.",
        "fn": _what_changed,
        "tools": ["watch_changes"],
    }],
    "disclosure-compiler": [{
        "name": "sb253_first_draft",
        "title": "California SB 253 first draft",
        "description": "Scope 1 and 2 inventory plus a cited SB 253 first-cycle "
                       "draft for review. Uses the GHG Ledger server too.",
        "fn": _sb253_first_draft,
        "tools": ["compile_disclosure"],
        "sibling_tools": {"ghg-ledger": ["calculate_inventory"]},
    }],
}


def _set_instructions(mcp: Any, text: str) -> bool:
    for attr in ("_lowlevel_server", "_mcp_server"):  # SDK 2.x, SDK 1.x
        low = getattr(mcp, attr, None)
        if low is not None and hasattr(low, "instructions"):
            try:
                low.instructions = text
                return True
            except (AttributeError, TypeError):
                return False
    return False


def _existing_prompt_names(mcp: Any) -> set:
    manager = getattr(mcp, "_prompt_manager", None)
    prompts = getattr(manager, "_prompts", None)
    return set(prompts or {})


def apply_starters(mcp: Any, key: str) -> int:
    """Set instructions and register prompts for ``key``. Returns prompts added."""
    if key not in INSTRUCTIONS or not callable(getattr(mcp, "prompt", None)):
        return 0  # S5
    _set_instructions(mcp, INSTRUCTIONS[key])
    have = _existing_prompt_names(mcp)
    added = 0
    for spec in PROMPTS.get(key, []):
        if spec["name"] in have:
            continue  # S6
        decorator: Callable = mcp.prompt(name=spec["name"], title=spec["title"],
                                         description=spec["description"])
        decorator(spec["fn"])
        added += 1
    return added
