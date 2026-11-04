"""Applicability gates for size- and entity-limited obligations (A6).

Pure, stdlib-only, no imports from core.py. A gate is a plain dict stored on
a Regulation (see data/regulations.py), so the dataset stays import-free:

    {
        "revenue_exceeds_usd": 1_000_000_000,   # strictly greater than
        "revenue_fiscal_years": 2,               # lesser of N previous FYs
        "entity_conditions": ["entity_form", "formed_under_us_law",
                              "does_business_in_california", "exemption"],
        "citation": "...",
    }

Invariants (California SB 253, 17 CCR 96071-96072, Health & Safety Code
38532(b)(2)):

  G1 Revenue must be strictly greater than the threshold. Revenue equal to
     the threshold is out of scope.
  G2 With revenue_fiscal_years == 2, revenue is the lesser of the two previous
     fiscal years. annual_revenue_usd is the most recent completed fiscal
     year; prior_year_revenue_usd is the year before it. Either year at or
     below the threshold puts the entry out of scope (the lesser cannot
     exceed it). A single year above the threshold, with the other year
     unknown, cannot establish applicability: unconfirmed.
  G3 Every listed entity condition must be established from inputs. A known
     failing condition puts the entry out of scope; an unknown one leaves it
     unconfirmed.
  G4 A definite out-of-scope reason wins over missing inputs.
  G5 Only "in_scope" lets the entry count as a binding obligation. Nothing
     here is a legal determination; callers label results screening only.
"""
from typing import Any, Dict, List, Optional

ENTITY_FORMS = ("corporation", "partnership", "llc", "other_business_entity")

EXEMPTIONS = {
    "none": None,
    "tax_exempt_nonprofit": "tax-exempt non-profit or charitable organization",
    "insurance": "regulated by the California Department of Insurance or in the "
                 "business of insurance in another state",
    "government_majority_owned": "government entity or more than 50% "
                                 "government-owned",
    "wholesale_electricity_only": "only California activity is wholesale "
                                  "electricity transactions",
    "payroll_only": "only California business is employee compensation or "
                    "payroll",
}

ENTITY_PROFILE_FIELDS = ("entity_form", "formed_under_us_law",
                         "does_business_in_california", "exemption")

IN_SCOPE = "in_scope"
OUT_OF_SCOPE = "out_of_scope"
UNCONFIRMED = "unconfirmed"


def evaluate_gate(
    gate: Dict[str, Any],
    annual_revenue_usd: Optional[float] = None,
    prior_year_revenue_usd: Optional[float] = None,
    entity_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return {"status", "reasons", "missing_inputs", "revenue_basis_usd"}."""
    reasons: List[str] = []
    missing: List[str] = []
    basis: Optional[float] = None

    threshold = gate.get("revenue_exceeds_usd")
    if threshold is not None:
        years = int(gate.get("revenue_fiscal_years", 1))
        named = [("annual_revenue_usd", annual_revenue_usd)]
        if years >= 2:
            named.append(("prior_year_revenue_usd", prior_year_revenue_usd))
        known = [(n, v) for n, v in named if v is not None]
        low = [(n, v) for n, v in known if v <= threshold]
        if low:
            n, v = low[0]
            reasons.append(
                f"{n} ${v:,.0f} is not more than the ${threshold:,} threshold"
                + (" (revenue is the lesser of the two previous fiscal years)"
                   if years >= 2 else ""))
        elif len(known) < len(named):
            missing.extend(n for n, v in named if v is None)
        else:
            basis = min(v for _, v in known)

    profile = entity_profile or {}
    for cond in gate.get("entity_conditions", ()):
        value = profile.get(cond)
        if value is None:
            missing.append(f"entity_profile.{cond}")
        elif cond == "formed_under_us_law" and value is False:
            reasons.append("not formed under the law of a US state, the "
                           "District of Columbia or an Act of Congress")
        elif cond == "does_business_in_california" and value is False:
            reasons.append("does not do business in California")
        elif cond == "exemption" and value != "none":
            reasons.append(f"exempt: {EXEMPTIONS.get(value, value)}")
        # entity_form: every accepted value is a covered business entity form.

    if reasons:
        status = OUT_OF_SCOPE
    elif missing:
        status = UNCONFIRMED
    else:
        status = IN_SCOPE
    return {"status": status, "reasons": reasons, "missing_inputs": missing,
            "revenue_basis_usd": basis}


def describe_gate(gate: Dict[str, Any]) -> str:
    """One-line plain description of what makes a gated entry binding."""
    parts = []
    if gate.get("entity_conditions"):
        parts.append("a business entity formed under US law, doing business "
                     "in California and not exempt")
    threshold = gate.get("revenue_exceeds_usd")
    if threshold is not None:
        if int(gate.get("revenue_fiscal_years", 1)) >= 2:
            parts.append(f"with revenue over ${threshold:,} in each of its two "
                         "previous fiscal years")
        else:
            parts.append(f"with annual revenue over ${threshold:,}")
    return "binding only for " + " ".join(parts) if parts else "binding"
