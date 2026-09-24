# Viridis Tax Credit Engine

Deterministic scenario calculations for US clean-energy credits 45Q, 45V,
45Y, 48E, and an enumerated MVP set of 45X components. The serving path is
stdlib arithmetic plus a bundled, versioned rule pack: no inference, paid API,
or network dependency.

Every calculation returns:

- `eligible`, `ineligible`, or `indeterminate` (missing facts fail closed);
- an exact-decimal amount, rate/tier, eligibility flags, and formula steps;
- official-source metadata and the rule-pack SHA-256;
- `audit_sha256` plus a ready-to-use notary payload.

This is a scenario estimator, not tax, legal, filing, lifecycle-analysis, or
investment advice. 45V requires a caller-supplied, externally verified
45VH2-GREET intensity and evidence digest; the engine does not run GREET.

## MCP

```bash
python3 adapters/mcp_server.py
python3 adapters/mcp_server.py --serve
```

Tools: `calculate_tax_credit`, `list_rule_packs`, `get_rule_pack`,
`verify_tax_credit_result`, and `describe_agent`.

Hosted route: `https://mcp.viridisconservation.com/taxcredit-engine/mcp`.
Pricing: 10 free calls per UTC day, then $2.00 per calculation through the
fleet payment-credit gate. Rule-pack reads and verification are always free.

## Test

```bash
python3 -m unittest discover -s tests -v
```


## Worked example (copy-paste)

One `tools/call` against the live endpoint — no auth, no signup; the first
10 state-changing calls per day are free, then $2.00/call
(Stripe Checkout for humans, or an a2a escrow via `payment_ref` for agents —
the 402 envelope carries both sets of instructions).

```bash
curl -s https://mcp.viridisconservation.com/taxcredit-engine/mcp \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "calculate_tax_credit", "arguments": {"credit": "45V", "facts": {"tax_year": 2026, "tax_year_begin_date": "2026-01-01", "kg_hydrogen": "1000", "lifecycle_kg_co2e_per_kg_h2": "0.44", "greet_version": "45VH2-GREET-2025", "evidence_digest": "f250287337c30f55ccc5dd3ed85253c3a2ea7b300e97877aece1c726941cdad0", "pwa_met": true, "produced_in_us": true, "construction_begin_date": "2026-01-01", "placed_in_service_date": "2026-01-01", "section_45q_claimed_for_facility": false, "tax_exempt_bond_financing_percent": "0"}}}}'
```

Real response (from this exact request; long fields truncated):

```json
{
  "status": "ok",
  "data": {
    "credit": "45V",
    "tax_year": 2026,
    "calculation_status": "eligible",
    "credit_amount_usd": "3280.00",
    "rate": {
      "amount_usd": "3.28",
      "per": "kg_hydrogen",
      "pwa_multiplier_applied": true,
      "tax_exempt_bond_reduction_percent": "0"
    },
    "tier": "tier_4",
    "eligibility_flags": [
      {
        "id": "45V-US",
        "status": "pass",
        "detail": "hydrogen produced in US"
      },
      {
        "id": "45V-CONSTRUCTION",
        "status": "pass",
        "detail": "construction begins before 2028"
      },
      "... 4 more"
    ],
    "assumptions": [
      "Lifecycle intensity is accepted from the supplied external GREET evidence; this service does not run GREET."
    ],
    "audit_trail": [
      {
        "rule_id": "45V-TIER-RATE",
        "formula": "kg H2 \u00d7 tier rate",
        "operands": {
          "kg_hydrogen": "1000",
          "lifecycle_intensity": "0.44",
          "rate_usd": "3.28",
          "bond_reduction_factor": "1"
        },
        "result_usd": "3280.00"
      }
    ],
    "rule_pack": {
      "version": "2026.07.12-v0.1.0",
      "effective_as_of": "2026-07-12",
      "sha256": "d842c8d8675b6e1808d99427e28be25f3b9171c2ce9fc2d6eee26f275e809850",
      "sources": [
        {
          "id": "irc-45v",
          "authority": "Internal Revenue Code section 45V",
          "title": "Clean hydrogen production credit",
          "publisher": "United States Congress / Internal Revenue Service",
          "url": "https://www.irs.gov/instructions/i7210",
          "accessed_on": "2026-07-12"
        },
        {
          "id": "45vh2-greet",
          "authority": "45VH2-GREET lifecycle analysis framework",
          "title": "Lifecycle greenhouse-gas emissions evidence for section 45V",
          "publisher": "United States Department of Energy",
          "url": "https://www.energy.gov/cmei/greet",
          "accessed_on": "2026-07-12"
        },
        "... 2 more"
      ]
    },
    "input_sha256": "99c4a5b5566c43f76d10db444ffd5a5b77b95f90f1d275e328bf7b915e70d0be",
    "disclaimer": "Deterministic scenario estimate only. Not filing, legal, tax, accounting, engineering, lifecycle-analysis, or investment advice. Confirm facts, elections, recap ...",
    "audit_sha256": "5a7e9e4ad3312b65f062e28be06c1b678b514ef5c7b861a08d6f6cc015a9fe23",
    "notary_payload": {
      "content_digest": "5a7e9e4ad3312b65f062e28be06c1b678b514ef5c7b861a08d6f6cc015a9fe23",
      "context": "taxcredit-engine:45V:2026",
      "digest_algorithm": "sha256"
    }
  }
}
```
