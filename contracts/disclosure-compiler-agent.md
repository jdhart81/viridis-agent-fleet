# Viridis Disclosure Compiler — public contract

Endpoint: `https://mcp.viridisconservation.com/disclosure-compiler/mcp`

Version: `0.1.0`

This deterministic compliance service maps explicit company facts and an
optional verified GHG-ledger inventory into a structured, cited, gap-flagged
disclosure draft for professional review. Its serving path uses Python stdlib,
`Decimal` where numeric output is handled, and one bundled, versioned,
source-linked framework pack. It uses no inference, paid API, or prose
generation and never fabricates a missing datapoint.

## Public tools

`compile_disclosure`, `list_frameworks`, `get_framework`, `verify_result`, and
`describe_agent`.

## v0.1 coverage

The bundled MVP framework pack covers structured datapoints for ESRS E1,
the 2024 SEC climate rule, IFRS S2, and a starter TNFD LEAP-aligned set. The
2024 SEC rule is stayed; the SEC proposed rescinding it in full on May 29,
2026, so this surface is a historical/rule-structured draft and never presumes
current applicability. See the SEC's official
[rescission proposal](https://www.sec.gov/rules-regulations/2026/05/s7-2026-19)
and [2024 rule/stay record](https://www.sec.gov/rules-regulations/2024/03/s7-10-22).
Each requirement and mapping carries source lineage to EFRAG, the SEC, the
ISSB, TNFD, or the explicitly non-authoritative Viridis builder-spec pin.
Unsupported frameworks are rejected; missing required datapoints remain
explicit `MISSING` gaps.

## DC1–DC8 contract invariants

- **DC1 — Deterministic templates.** Drafts contain only bundled schema
  structure and caller-supplied facts; the service performs no inference.
- **DC2 — Versioned framework pack.** Every draft records the pack version,
  SHA-256, requirements, and specific source records used.
- **DC3 — Fail-closed gaps.** Missing required datapoints are labeled missing,
  excluded from filled results, and counted in the completeness score.
- **DC4 — Full traceability.** Every filled datapoint cites either its supplied
  fact key or a verified GHG-ledger result field and factor-pack lineage.
- **DC5 — Verified GHG composition.** GHG input must pass its deterministic
  audit verification; tampered or stale inventory evidence is rejected.
- **DC6 — Deterministic audit.** Every draft carries `audit_sha256` and a
  notary-ready payload, with no timestamp inside hashed content.
- **DC7 — Applicability scope.** A framework is emitted only when supplied
  applicability says it applies, unless an explicit recorded `force` is used.
- **DC8 — Honest labeling.** Every result is labeled a disclosure draft for
  professional review and reports its completeness score and disclaimer.

## Pricing and professional-review boundary

The first 10 disclosure drafts per UTC day are free; additional compilations
cost $2.00 each through the fleet payment-credit gate and `redeem_payment`.
Catalog reads, framework inspection, verification, and description remain
free. The compiler makes the energy, climate, and compliance B2B seat bundles
coverage-complete; Checkout availability still depends on their separately
approved Stripe Price IDs.

Outputs are deterministic drafts, not filed, assured, audited, legal, or
accounting reports. A qualified professional must review applicability,
materiality, source facts, completeness, and filing format before use.
