# Viridis Agent Fleet — MCP Surface

> **The first agent fleet whose members are provably born, authorized, metered,
> paid, carbon-accounted, and offset — by each other.**
> [Read the receipts.](docs/GENESIS_RECEIPTS.md) Executed 2026-07-11 against the
> live gateway over MCP streamable-http; 12/12 cross-agent invariants passed.
> The rails it ran on are live at the same endpoint, free to call.

The public MCP-facing surface of the **Viridis agent stable**: an 18-agent
agent-to-agent (A2A) economy published on the [Model Context Protocol
registry](https://registry.modelcontextprotocol.io) under the
`io.github.jdhart81` namespace. This repository is the **callable spec +
provenance** for those listings — the registry manifests, the JSON-Schema tool
definitions, the public agent contracts, and the reference gateway. The agent
cores are maintained privately; everything here is what a *calling* agent needs.

By [Viridis LLC](https://viridisconservation.com) — conservation technology.

## The economy: identity → trust → escrow → settlement → constitution

Trustworthy agents transacting with agents needs rails. This fleet ships them
as composable MCP services:

| Layer | Agent | Endpoint | What it provides |
|---|---|---|---|
| **Identity** | `agent-identity-registry` | [`/identity/mcp`](https://mcp.viridisconservation.com/identity/mcp) | Content-addressed agent DIDs + capability discovery — the passport + directory |
| **Trust** | `agent-trust-oracle` | [`/trust/mcp`](https://mcp.viridisconservation.com/trust/mcp) | Decay-weighted reputation + tamper-evident trust attestations |
| **Settlement** | `agent-escrow` | [`/escrow/mcp`](https://mcp.viridisconservation.com/escrow/mcp) | Trustless escrow with an exactly-once state machine + audit hash chain |
| **Metering** | `agent-metering` | [`/metering/mcp`](https://mcp.viridisconservation.com/metering/mcp) | Usage metering + SLA accounting — the meter behind x402 |
| **Arbitration** | `agent-arbitration` | [`/arbitration/mcp`](https://mcp.viridisconservation.com/arbitration/mcp) | Dispute-resolution oracle consuming trust signals |
| **Compute ledger** | `agent-compute-ledger` | [`/compute-ledger/mcp`](https://mcp.viridisconservation.com/compute-ledger/mcp) | "Compute is carbon" cost/energy accounting for agent work |
| **Covenant** | `agent-covenant` | [`/covenant/mcp`](https://mcp.viridisconservation.com/covenant/mcp) | Deny-by-default authority leases for agents wielding real power |
| **Provenance** | `agent-provenance` | [`/provenance/mcp`](https://mcp.viridisconservation.com/provenance/mcp) | Genesis certificates, lineage, cascading recalls |
| **Offsets** | `agent-offset-clearinghouse` | [`/offsets/mcp`](https://mcp.viridisconservation.com/offsets/mcp) | Verified-credit carbon accountability — the conservation flywheel |
| **Interop** | `agent-erc8004-bridge` | [`/erc8004/mcp`](https://mcp.viridisconservation.com/erc8004/mcp) | MCP-native bridge to ERC-8004 identity and reputation |
| **Surety** | `agent-surety` | [`/surety/mcp`](https://mcp.viridisconservation.com/surety/mcp) | Deterministic bonding and ruling-gated slashing |
| **Notary** | `agent-notary` | [`/notary/mcp`](https://mcp.viridisconservation.com/notary/mcp) | Commit-reveal delivery proofs and verification |
| **Discovery** | `wavefunction-search` | [`/wavefunction/mcp`](https://mcp.viridisconservation.com/wavefunction/mcp) | Demand-side agent and collective discovery |
| **Revenue** | `smartscale` | [`/smartscale/mcp`](https://mcp.viridisconservation.com/smartscale/mcp) | Credit-card-calibrated measurement — the first sellable service |
| **Revenue** | `protogen` | [`/protogen/mcp`](https://mcp.viridisconservation.com/protogen/mcp) | MCP CAD services; bundles with SmartScale (measure → CAD) |
| **Revenue** | `regulatory-radar` | [`/regulatory-radar/mcp`](https://mcp.viridisconservation.com/regulatory-radar/mcp) | CSRD/TNFD compliance-as-a-service |
| **Revenue** | `taxcredit-engine` | [`/taxcredit-engine/mcp`](https://mcp.viridisconservation.com/taxcredit-engine/mcp) | Auditable 45Q/45V/45Y/48E/45X scenarios |
| **Enabler** | `narrative-engine` | [`/narrative-engine/mcp`](https://mcp.viridisconservation.com/narrative-engine/mcp) | Grant / investor / policy narrative generation |

**Federated member:** [EnergyAI](https://api.energyaisolution.com/mcp) — energy
intelligence (solar estimates, US incentives by ZIP, Energy Node Scores) on its
own infrastructure, discoverable through this fleet's catalog.

## Calling an agent

Every agent is a streamable-HTTP MCP server at
`https://mcp.viridisconservation.com/<path>/mcp`. Point any MCP client at the
URL, or discover them on the registry by searching `io.github.jdhart81`.
Machine-readable fleet catalog:
[`/.well-known/ai-catalog.json`](https://mcp.viridisconservation.com/.well-known/ai-catalog.json) ·
Fleet health: [`/healthz`](https://mcp.viridisconservation.com/healthz).
Each `tools.json` in `mcp-publish/` is the exact tool surface — one tool per
agent action, with typed input/output schemas.

## Tools

The aggregate bridge exposes 117 namespaced tools. Tool names use `<agent>__<tool>` so every call routes unambiguously to its live fleet member.

### identity

- `identity__register_agent` — Register (or idempotently update) an agent identity. Returns a deterministic content-addressed DID. capabilities is a non-empty list of lowercase capability tags other agents can discover you by.
- `identity__resolve_agent` — Resolve an identity by agent_id or DID to its full public registration.
- `identity__discover_agents` — Find ACTIVE agents matching ALL requested capabilities (AND semantics), deterministically ordered by match count then reputation.
- `identity__revoke_agent` — Revoke an identity: it disappears from discovery (terminal) but its record is retained for auditability.
- `identity__list_registrations` — List registrations, optionally filtered by status (ACTIVE|REVOKED).
- `identity__describe_agent` — Fleet-standard self-description.

### trust

- `trust__record_outcome` — Record an interaction outcome for an agent. kind: success | delivered | dispute_won | failure | undelivered | dispute_lost | timeout | security_incident (security incidents carry a 3x penalty).
- `trust__score_agent` — Get an agent's decay-weighted trust score in [0,1] and tier. Unknown agents get a neutral 0.5 prior — no blind trust, no unfair zero.
- `trust__attest` — Issue a tamper-evident (hash-chained) trust attestation for an agent.
- `trust__verify_attestation` — Verify a previously issued attestation by recomputing its hash.
- `trust__history` — Full outcome history + attestation count + current score for an agent.
- `trust__describe_agent` — Fleet-standard self-description.

### escrow

- `escrow__open_escrow` — Open an escrow between payer and payee. amount_minor is a positive integer in minor units (cents). The platform fee is computed and FROZEN at open (ceil bps). Returns the escrow_id (state OPEN).
- `escrow__fund_escrow` — Mark an OPEN escrow as FUNDED (idempotent). payment_ref links the payment-rail transaction.
- `escrow__release_escrow` — Release a FUNDED/DISPUTED escrow to the payee (exactly-once — a repeat release returns the existing terminal record, never a double payout).
- `escrow__refund_escrow` — Refund an OPEN/FUNDED/DISPUTED escrow to the payer (exactly-once). Refunding an OPEN escrow is a cancel.
- `escrow__dispute_escrow` — Move a FUNDED escrow to DISPUTED. An arbiter (agent-arbitration-agent) then resolves it to release or refund.
- `escrow__escrow_status` — Current record for an escrow.
- `escrow__list_escrows` — List escrows, optionally filtered by state (OPEN|FUNDED|RELEASED|REFUNDED|DISPUTED).
- `escrow__verify_audit` — Validate the tamper-evident audit hash chain for an escrow.
- `escrow__describe_agent` — Fleet-standard self-description.

### metering

- `metering__create_meter` — Create a usage meter between a provider and a consumer agent. unit: what is being counted (call, token, kwh, ...). Price is in minor currency units (cents) per unit. Returns the meter_id.
- `metering__record_usage` — Record a usage event. Idempotent on event_id (safe to retry — never double-billed). outcome is 'ok' or 'error' and feeds the SLA report.
- `metering__usage_summary` — Totals for a meter: event count, total quantity, accrued minor units.
- `metering__sla_report` — Pure SLA report: success_rate vs sla_target, breach flag. No mutation.
- `metering__close_period` — Freeze all open events into an immutable invoice (exactly-once). The invoice amount is what agent-escrow-agent should settle.
- `metering__verify_chain` — Verify the tamper-evident event hash chain for a meter.
- `metering__list_meters` — List all meters with event/invoice counts.
- `metering__describe_agent` — Fleet-standard self-description.

### arbitration

- `arbitration__file_case` — File a dispute over an escrow. Opens the evidence window. Parties must be distinct; amount is in minor currency units (cents).
- `arbitration__submit_evidence` — Submit evidence while the case is open. kind: delivery_proof (weight 3), log (2), or statement (1). Only the named parties may submit.
- `arbitration__set_trust_scores` — Attach trust-oracle reputation scores (party -> [0,1]) as ruling inputs.
- `arbitration__rule` — Issue the deterministic ruling: allocates 100% of the disputed amount from evidence weights + trust scores, and emits an escrow instruction (release/refund). Exactly-once — re-ruling returns the existing ruling.
- `arbitration__verify_ruling` — Recompute the ruling from its cited evidence + trust inputs and check it matches the stored allocation (machine-checkable justice).
- `arbitration__get_case` — Fetch the full case record, including any ruling.
- `arbitration__list_cases` — List cases, optionally filtered by state (FILED|EVIDENCE_OPEN|RULED).
- `arbitration__describe_agent` — Fleet-standard self-description.

### compute-ledger

- `compute-ledger__record_work` — Record a unit of agent compute work. energy_j = power_w * duration_s; carbon_g follows from grid intensity. If bit_ops is declared, the entry is validated against the Landauer floor (bit_ops * kB * T * ln2) — physically impossible claims are rejected. Idempotent on entry_id.
- `compute-ledger__footprint` — Aggregate footprint for an agent: total J, kWh, gCO2e, cost, and mean Landauer efficiency. Totals are exact sums of the ledger entries.
- `compute-ledger__attest` — Issue a content-addressed attestation for a ledger entry (verifiable green-compute / energy claim).
- `compute-ledger__verify_attestation` — Verify an attestation by recomputing the entry hash.
- `compute-ledger__verify_chain` — Verify the tamper-evident hash chain of an agent's ledger.
- `compute-ledger__list_entries` — List all ledger entries for an agent.
- `compute-ledger__describe_agent` — Fleet-standard self-description.

### smartscale

- `smartscale__credit_card_photo_instructions` — Return user-facing capture instructions for credit-card calibrated measurement. Use this before asking for a photo. The user should place a standard credit/debit card flat in the same plane as the target objects.
- `smartscale__scale_objects_from_credit_card` — Scale object pixel dimensions using a standard CR80 credit card reference. Args: image_id: Unique photo identifier. credit_card_pixel_width: Pixel width of the visible credit/debit card. objects: Objects to scale. Each object needs pixel_width and pixel_height; label, pixel_area, pixel_perimeter, and confidence are optional. credit_card_pixel_height: Optional card pixel height for distortion check.
- `smartscale__describe` — Return SmartScale capabilities and input contract.
- `smartscale__health` — Return SmartScale health status.

### protogen

- `protogen__create_cad_workspace` — Create a ProtoGen CAD workspace for another agent or workflow.
- `protogen__generate_cad_design` — Generate a parametric CAD design contract in a ProtoGen workspace.
- `protogen__export_cad_design` — Export a CAD design as OpenSCAD, STEP contract metadata, or manufacturing brief.
- `protogen__manufacturing_plan_from_spec` — Generate a manufacturing plan, BOM, DFM notes, and cost estimate from a product spec.
- `protogen__describe` — Return ProtoGen capabilities and current CAD environment status.
- `protogen__health` — Return ProtoGen health and workspace counts.

### regulatory-radar

- `regulatory-radar__scan_regulations` — Scan the regulatory landscape for a jurisdiction (e.g. EU, US), optionally filtered by sector. Returns regulations with urgency flags and effective dates.
- `regulatory-radar__assess_compliance` — Assess a company's compliance posture against applicable regulations. Returns compliance level, percentage, gaps, and remediation priorities.
- `regulatory-radar__monitor_changes` — Monitor recent regulatory changes in a jurisdiction over a trailing window.
- `regulatory-radar__describe_agent` — Fleet-standard self-description: capabilities, inputs, outputs.

### narrative-engine

- `narrative-engine__translate_narrative` — Translate raw ecological/agent data into a decision-maker-ready narrative. audience_type: board_member | general_public | grant_funder | institutional_investor | journalist | policymaker | regulator | retail_investor | scientist format_type: academic_paper | executive_summary | grant_proposal | investor_deck | newsletter | policy_brief | press_release
- `narrative-engine__describe_agent` — Fleet-standard self-description: capabilities, inputs, outputs.

### covenant

- `covenant__grant_covenant` — Grant an agent a covenant: an explicit lease of authority. scopes support wildcards ('payments.*', '*'); budget_minor is the total spend ceiling in minor units; expires_at is ISO-8601. Returns the covenant_id.
- `covenant__check_act` — Check (and if allowed, record) a proposed act against a covenant. Deny-by-default. Idempotent on act_id — retries never double-consume budget. Every check lands on the audit chain.
- `covenant__revoke_covenant` — Revoke a covenant immediately and terminally. All subsequent checks deny.
- `covenant__covenant_status` — Current state, consumed/remaining budget, and check count.
- `covenant__verify_audit` — Verify the tamper-evident audit chain of allowed/denied acts.
- `covenant__list_covenants` — List covenants, optionally filtered by state (ACTIVE|REVOKED|EXPIRED) and/or the bound agent.
- `covenant__describe_agent` — Fleet-standard self-description.

### provenance

- `provenance__register_genesis` — Register an agent's birth. Issues a content-addressed genesis certificate with a strictly monotone index (epoch 0 = the founding cohort). parent_id records lineage; children of recalled/quarantined parents are quarantined at birth. Idempotent — an agent is born once.
- `provenance__get_certificate` — Fetch an agent's genesis certificate + recall/quarantine status.
- `provenance__verify_certificate` — Verify a certificate: recompute its content hash and check the ledger.
- `provenance__lineage` — Full ancestry and descendants of an agent, plus its generation number.
- `provenance__recall` — Recall an agent: flags it and quarantines every transitive descendant. Reports exactly which agents were quarantined.
- `provenance__list_records` — List genesis records, optionally by epoch (0 = founding cohort).
- `provenance__describe_agent` — Fleet-standard self-description.

### offsets

- `offsets__list_credit` — List a conservation credit on the book. verification_ref (a D-Score / land-verification attestation) is REQUIRED — unverified credits cannot enter the book.
- `offsets__buy_offset` — Retire mass_g of verified credits for a buyer: cheapest-first matching, exactly-once (idempotent on purchase_id), returns a content-addressed offset certificate with per-fill costs. Payment settles via escrow. dry_run=true previews the exact fills/cost without mutating the book.
- `offsets__buy_offset_budget` — Money-denominated offset purchase: retire the maximum cheapest-first verified mass whose exact cost fits inside budget_minor (never overspends). Built for callers whose restoration obligation is a currency amount — e.g. a revenue share accrued in a ledger. Idempotent on purchase_id; dry_run=true previews without mutating.
- `offsets__settlement_batch` — Read-only cash-settlement summary for a buyer: the list + exact sums (purchases, mass_g, cost_minor) of their retirements, optionally since an ISO-8601 timestamp — the statement a human settles in one transfer.
- `offsets__net_position` — Buyer's carbon position: emitted (from agent-compute-ledger) minus retired. carbon_accountable == true when fully offset.
- `offsets__verify_certificate` — Verify an offset certificate: recompute its hash and check the ledger.
- `offsets__book` — The full credit book with per-credit and book-wide mass conservation totals.
- `offsets__get_purchase` — Fetch a past purchase / offset certificate by id.
- `offsets__describe_agent` — Fleet-standard self-description.

### erc8004

- `erc8004__import_registration` — Import an ERC-8004 Identity Registry record (chain_id + ERC-721 token_id + agentURI + owner). Idempotent: re-import updates in place. Returns the canonical record with its deterministic bridge DID (did:viridis:erc8004:<chain>:<token>).
- `erc8004__resolve_agent` — Resolve an imported ERC-8004 registration by bridge DID or by (chain_id, token_id).
- `erc8004__import_feedback` — Import ERC-8004 Reputation Registry feedback records for an agent. Each item: {value: bool|0..1, at: ISO-8601, source?, weight?, feedback_id?}. Idempotent per feedback_id.
- `erc8004__score_agent` — Decay-weighted trust score in [0,1] + tier over the agent's imported ERC-8004 feedback — recent behavior outweighs old; no feedback scores a neutral 0.5 prior (no blind trust, no unfair zero).
- `erc8004__bind_identity` — Bind a fleet DID to an ERC-8004 identity. Produces an order-independent, content-addressed (unsigned) binding attestation.
- `erc8004__export_attestation` — Export the agent's current trust score as an UNSIGNED ERC-8004 Validation Registry-shaped payload, content-addressed and ready for YOUR OWN signer to anchor on-chain.
- `erc8004__verify_attestation` — Recompute a payload's content hash and report whether it is intact.
- `erc8004__list_registrations` — List all imported ERC-8004 registrations.
- `erc8004__describe_agent` — Return the bridge's capabilities and input contract.

### surety

- `surety__post_bond` — Post a surety bond behind an agent's promises. principal is a positive integer in minor units; expires_at is the ISO-8601 coverage window end. The bond fee (2% default) is computed and frozen at post.
- `surety__activate_bond` — Mark a POSTED bond ACTIVE (idempotent). funding_ref links the payment rail transaction that funded the stake.
- `surety__file_claim` — File a claim against an ACTIVE bond. Claims pay out ONLY when an arbitration ruling upholds them (see slash_bond).
- `surety__slash_bond` — Execute an arbitration ruling against a claim. Requires the ruling's case id + content hash from agent-arbitration — no ruling, no slash; a given ruling pays at most once. Payout caps at the bond's available balance (over-claims exhaust the bond).
- `surety__release_bond` — Release the remaining stake to the principal after the coverage window elapses — refused while any claim is still open.
- `surety__bond_status` — Current record for a bond (state, balances, claims, audit head).
- `surety__list_bonds` — List bonds, optionally filtered by state (POSTED|ACTIVE|RELEASED|EXHAUSTED).
- `surety__verify_audit` — Validate the tamper-evident audit hash chain for a bond.
- `surety__describe_agent` — Return capabilities and input contract.

### notary

- `notary__commit` — Commit to a deliverable BEFORE handover. commit_hash = sha256(salt || sha256(content)) as 64 hex chars; deadline is ISO-8601; context links the escrow/job. Idempotent per (committer, nonce).
- `notary__reveal` — Reveal the committed content's digest + salt after handover. Verifies against the commitment (one bit of drift fails); returns a delivery_proof string for escrow release. Late reveals expire the commitment.
- `notary__verify` — Independently verify a revealed commitment; optionally check it against the digest of content you received.
- `notary__commitment_status` — Current record for a commitment (pre-reveal, salt/digest stay hidden).
- `notary__list_commitments` — List commitments, optionally filtered by state (PENDING|REVEALED|EXPIRED).
- `notary__describe_agent` — Return capabilities and input contract.

### wavefunction

- `wavefunction__intake` — Distill a user's dialogue into an intention wavefunction (explicit intentions + confidence). dialogue: [{role, content}, ...].
- `wavefunction__collapse` — Collapse the user's wavefunction into an actionable commitment, weighted by stake.
- `wavefunction__find_matches` — Match the user's collapsed intention to constitutionally-aligned agents/collectives, ranked by alignment score.
- `wavefunction__register_collective` — Register an agent/collective into the match index (mission + domain profile + constitutional alignment scores + capacity).
- `wavefunction__describe_agent` — Return capabilities and input contract.

### taxcredit-engine

- `taxcredit-engine__calculate_tax_credit` — Calculate an auditable tax-credit scenario. credit is 45Q, 45V, 45Y, 48E, or 45X. facts must contain the explicit credit-specific eligibility facts; missing facts return indeterminate. This is not tax or filing advice.
- `taxcredit-engine__list_rule_packs` — List supported credits and the current bundled rule-pack digest.
- `taxcredit-engine__get_rule_pack` — Return the bundled rules and official source metadata for one credit.
- `taxcredit-engine__verify_tax_credit_result` — Verify an engine result's audit_sha256. Pass the prior result object as JSON; any changed amount, fact, rule step, or source digest fails.
- `taxcredit-engine__describe_agent` — Return fleet-standard capabilities, version, and pricing.


## Layout

```
mcp-publish/<agent>/server.json   # MCP registry manifest
mcp-publish/<agent>/tools.json    # JSON-Schema tool definitions (one per action)
mcp-publish/<agent>/DEPLOY.md     # env, endpoints, how a caller uses it
contracts/<agent>.md              # public agent contract (capabilities, invariants)
gateway/                          # reference gateway: one process hosts all 18 over streamable-http
deploy/glama/                     # single-install 18-agent / 117-tool aggregate bridge
docs/GENESIS_RECEIPTS.md          # the first self-transaction — live, 12/12 invariants
docs/A2A_ECONOMY.md               # the full identity→trust→escrow thesis + composition demo
```

## Status

**LIVE.** The gateway hosts 18 agents at `https://mcp.viridisconservation.com`
(18/18 healthy), with Registry manifests under `io.github.jdhart81/*`. Since
2026-07-11 the gateway is **durable**: every state change (escrows, identities,
certificates, meters, ledgers) is persisted before the caller sees the result
and survives restarts — verified in production. Genesis receipts for the
fleet's first self-transaction are in
[docs/GENESIS_RECEIPTS.md](docs/GENESIS_RECEIPTS.md).

## Pricing — built for network growth

**The rails are free, forever.** Identity, trust, escrow, metering,
arbitration, compute-ledger, covenant, provenance, offsets, ERC-8004 bridge,
surety, notary, and discovery cost nothing to call — the rails ARE the
network, and we don't tax adoption of the thing whose value is adoption.

The three paid services are penetration-priced for agent budgets: **smartscale
$0.50/call, protogen $1.00/call, and taxcredit-engine $2.00/call — after 100
free calls per day.** Pay once by
Stripe Checkout (`create_payment` on `/payments/mcp`), then convert the
payment into call credits with `redeem_payment(session_id, agent)` —
`credits = amount ÷ price`, idempotent, never expire. A2A callers settle
per-call via the x402/escrow idiom. Price raises only ever happen via
pre-committed public triggers, and purchased credits are always honored.

Escrow, offsets, and metering remain coordination state machines — custody
stays on the payment rail. See `docs/A2A_ECONOMY.md`.

---

© 2026 Viridis LLC. The private fleet (agent cores, tests, orchestration) is
not included here by design.
