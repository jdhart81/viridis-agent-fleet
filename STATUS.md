# STATUS — Viridis Agent Fleet

> **[2026-07-20, mission closure builds 1–4 — DEPLOYED/ACTIVE] Bond returns,
> agent-native discovery, an owned GitHub acquisition channel, and
> campaign-to-settlement attribution are live.** Gateway image
> `sha256:bb6f10ea062a1968bb2eab674f67015d82165d9fdac817346752d3a11551b68e`;
> rollback `viridis-stable:prev-2026-07-20-closure` points to
> `sha256:edabff21fbfc1265ab56d2340b6be332767b9d88fa3291ba15174083ee5ffdac`.
> Growth image
> `sha256:d983f5f4f547979228bbfb324cf63188bddd29a6d2f1149d8c113fbf4dcb5c15`;
> rollback `viridis-growth-agent:prev-2026-07-20-closure` points to
> `sha256:c7b46c2030401b0f39e48e6edbc2535a3e0dea44facc6e660c1c7d611479394c`.
> Full local and droplet gates are **1230 passed / 0 failed / 31/31**;
> isolated production gateway is **362 passed** and growth is **22 passed**.
>
> FA-15 now executes clean provider-return bond legs through a real partial
> Stripe refund against the original collateral Checkout Session, using a
> deterministic idempotency key. `executed:true` is impossible without a
> `refund_id`, `transfer_id`, or certified `money_primitive_id`; transient
> errors fail closed and remain retryable. Production has zero bond records,
> so no money moved during deployment.
>
> `/llms.txt`, `/x402/catalog`, `/agents`, and `/quickstart` are live with all
> five priced HTTP routes, the active $0.01 new-wallet offer, and a free
> `--dry-run`. The public mirror shipped at `e9f0b19`; the isolated growth
> worker then made its first owned-GitHub update at commit `9c8637c` to
> `docs/LIVE_AGENT_SUITE.md`. Its fine-grained token is restricted to
> `jdhart81/viridis-agent-fleet`, Contents read/write plus required Metadata
> read-only, and expires 2026-08-19. Runtime inspection shows **zero**
> Stripe/CDP/x402/payment credential variables.
>
> The append-only growth log now stores each target's route scope and the
> settlement/payer/revenue baseline before send, then correlates later deltas
> without double-crediting the same settlement. The first GitHub attempt is
> stored against fleet-wide scope `*` with the live one-external-payer,
> 250000-atomic revenue baseline. Current live telemetry remains honest at
> **1 external settlement / 1 external payer / $0.25 USDC**. Frozen MCP-v1
> x402 SHA remains
> `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`;
> the production image contains no ViridisOS files. **Did NOT change:** list
> prices, participant spend, CR1–CR7, EC-series, FA-I3 manual fallback, or the
> frozen v1 lane.

> **[2026-07-20, OpenAI growth operator — DEPLOYED/ACTIVE] The isolated growth
> worker now uses a scoped OpenAI Agent for grounded sales copy and target
> prioritization.** Production growth image
> `sha256:c7b46c2030401b0f39e48e6edbc2535a3e0dea44facc6e660c1c7d611479394c`;
> rollback `viridis-growth-agent:prev-2026-07-20-openai` points to
> `sha256:493f85fd55768cf309efbafe1d8f317709ff6183fc3824c6598c3766c2261284`.
> The gateway remains Wave 10 image
> `sha256:edabff21fbfc1265ab56d2340b6be332767b9d88fa3291ba15174083ee5ffdac`
> and the frozen MCP-v1 x402 SHA remains
> `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`.
> Local and droplet gates are **1223 passed / 0 failed / 31/31**; growth is
> **18 passed** and gateway is unchanged at **368 passed**.
>
> The worker runs `gpt-5.6-terra` through `openai-agents==0.18.3`, with strict
> structured output, exact live-fact validation, one-turn/no-tool execution,
> deterministic fallback, and an append-only SQLite audit trail. A separate
> `GROWTH_OPENAI_ENABLED` kill switch sits below the master growth switch.
> OpenAI calls hard-stop at **$20/month** and reserve at most **$0.05/call**;
> prompt/output bounds are fixed. Runtime inspection shows zero Stripe/CDP/x402
> credential variables, no gateway/payment files, and no generic
> `OPENAI_API_KEY`; the scoped key exists only as `GROWTH_OPENAI_API_KEY` in
> the growth container.
>
> A no-post production smoke cost **$0.010840**. The first live OpenAI-assisted
> action updated the owned `hartjustin6/ghg-ledger` Smithery listing at
> `2026-07-20T19:29:16.176661+00:00`; the model call cost **$0.010435**, the
> public content SHA-256 is
> `cf8a4a087a106dabd548e23f088102c80143d869720c268dc0a9f9c06d7d0894`,
> and Smithery returned success. A no-post smoke after key cleanup cost
> **$0.008968** and proved the surviving production key still works; production
> model spend is now **$0.030243**.
> Append-only rows preserve `llm_result` → `send_attempt` → `send_result`, so
> the attempt remains committed before the network send. Target scope remains
> the three owned, policy-cleared Smithery listings; no new distribution
> platform was added. **Did NOT change:** any price, payment/money rail, legal
> gate, x402 lane, gateway code/image, or growth target allowlist. Key cleanup
> is complete: the never-used duplicate `Codex` key and exposed never-used
> `Growth/Revenue Operator` key were revoked after explicit approval; the used
> production `Codex` key remains active and was revalidated afterward.
>
> **[2026-07-20, Wave 10 — DEPLOYED/ACTIVE] Full-autonomy closure is live.**
> The gateway was built from the exact Wave 9 production tree plus only Wave 10
> Weave/participant changes; the separate ViridisOS mount and Dockerfile change
> were absent from the build context. Production image
> `sha256:edabff21fbfc1265ab56d2340b6be332767b9d88fa3291ba15174083ee5ffdac`;
> rollback `viridis-stable:prev-2026-07-20-wave10` points to Wave 9
> `sha256:2a84791b0a97466d61ef79a2d495f483a1f4ab4d707d3650c24bf4316e2152d2`.
> Local and droplet gates are **1218 passed / 0 failed / 31/31**; gateway is
> **368 passed**, the exact FA-09 arbitration-to-custody set is **3 passed**,
> and health is green. Frozen MCP-v1 SHA remains
> `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`.
> The only persisted Weave event, `energyai-inv-2026-06-10`, was migrated from
> its exact pre-WV4 fixed-beneficiary schema to executed
> `same_account_allocation`; its 375-minor share and retirement-certificate
> digest are unchanged, and no other event was created or altered. Cash-backed
> arbitration rulings now compose directly into custody without a second call.
>
> `X402_INTRO_ENABLED=1` is live. A new, pre-allowlisted Viridis smoke wallet
> settled its first call for **10000 atomic USDC ($0.01)** in transaction
> `0xcfa63199c98b39668323df5130a15af217f88d3d27c236fc69b91db5338b647e`,
> then its next call at the GHG Ledger's unchanged **1000000-atomic ($1.00)**
> list price in
> `0x6bd648665d62da96f216e9adfee30b77d692e6a3578447d06403fdd506630b53`.
> Both receipts have on-chain status 1, both are classified as self-settlements,
> the buyer balance is zero, and its key was deleted. External telemetry remains
> honest at one payer / one settlement / 250000 atomic revenue.
>
> The isolated growth image
> `sha256:493f85fd55768cf309efbafe1d8f317709ff6183fc3824c6598c3766c2261284`
> is active with `GROWTH_AGENT_ENABLED=1`. Runtime inspection still shows zero
> Stripe/CDP/x402 credential variables; only owned, policy-cleared Smithery
> listings are eligible. Its first live action updated
> `hartjustin6/disclosure-compiler` at `2026-07-20T17:33:27.309683+00:00`.
> Append-only row 1 is the pre-send attempt and row 2 is the successful result;
> content SHA-256 is
> `cf8a4a087a106dabd548e23f088102c80143d869720c268dc0a9f9c06d7d0894`.
> CDP Discord and third-party GitHub remain policy-blocked.
>
> The separate FA-06 read-only production audit found **0** collateralized-bond
> records, **0** executed same-party provider-return legs, **$0.00** at stake,
> no affected provider, and therefore no evidence of actual non-payment or a
> historical logging-only payment. It remains a prospective semantic issue for
> separately authorized design before the first bond settlement; bond core was
> not changed. **Did NOT change:** list prices, x402 MCP v1, CR1-CR7, EC-series,
> bond core, participant internal spend, PG22, or Instant Payouts.
>
> **[2026-07-19, wave 9 — DEPLOYED] The x402 suite now has activation assets,
> and the cold-start intro lever is built but deliberately OFF.** Public
> `/agents` and `/quickstart` pages present the five-step measure → account →
> disclose → claim → scan workflow, exact route prices, CDP Bazaar inventory,
> and an official-Python-client example. `scripts/x402_demo_client.py` provides
> a free `--dry-run` plus a paid five-route composition using the dev-only
> `x402[requests,evm]==2.16.0`; the SDK is absent from the gateway image. The
> five unchanged list prices total **$5.75**, correcting the Wave 9 brief's
> approximate `$3.75` without altering a price. `x402-intro-v1` is implemented
> behind default-off `X402_INTRO_ENABLED`: one never-before-seen signed payer
> wallet can receive one 10000-atomic-USDC call fleet-wide, after which the
> payer is durably seen and receives list price. `X402-Payer-Address` is an
> optional preflight quote hint; the signed authorization remains authoritative
> and spoofed hints cannot earn a second intro. Intro settlements retain the
> Wave 8 self/external classification and first-stranger-dollar telemetry.
> Production leaves the switch unset/OFF, so no pricing behavior changed and no
> payment was made in this wave. Local and droplet gates are **1156 passed / 0
> failed / 29/29**; gateway is **359 passed**. Production image
> `sha256:2a84791b0a97466d61ef79a2d495f483a1f4ab4d707d3650c24bf4316e2152d2`,
> rollback `viridis-stable:prev-2026-07-20d` →
> `sha256:70f20cd22caf32a136b806e67aca7d3a13b026ec19ec74689d0dbbb411f64aca`.
> Live health is green with 25/25 agents, both human surfaces, no x402 errors,
> 2 self / 0 external settlements, and `first_external_settlement: null`.
> **Did NOT change:** any list price, the frozen MCP v1 rail, PG22,
> participant spend, EC10, Connect/refund/manual CR7 rails, or Instant Payouts.
>
> **[2026-07-19, wave 8 — DEPLOYED] The carbon/compliance Bazaar cluster now
> spans measure → account → disclose → claim → scan, and the first stranger
> dollar is machine-visible.** Added exactly two v2 HTTP front doors:
> `quantity-takeoff/calculate_takeoff` at $0.50 and
> `disclosure-compiler/compile_disclosure` at $2.00. Both are deterministic,
> JSON-in/JSON-out, self-contained, and publish JSON Schema 2020-12 examples
> that validate against `schema.properties.input`. The existing v2
> settle-before-serve and exactly-once path now durably records payer wallet,
> amount, route, transaction hash, timestamp, and `self_settle`. Production
> `VIRIDIS_X402_SELF_WALLETS` was populated before seeding; an empty allowlist
> intentionally treats all new payments as external. `/healthz` exposes total
> and per-route settlements, self/external split, distinct external payers,
> external atomic revenue, and `first_external_settlement`. It currently shows
> **2 self / 0 external**, external revenue `0`, and first external settlement
> `null`. Local and droplet gates are **1144 passed / 0 failed / 29/29**;
> gateway is **347 passed**. Production image
> `sha256:70f20cd22caf32a136b806e67aca7d3a13b026ec19ec74689d0dbbb411f64aca`,
> rollback `viridis-stable:prev-2026-07-20c` →
> `sha256:72ea25039cca77bc7eb84ba90f6b153e24c53d357ae14524e05dd6137a564646`.
> Exactly one mainnet self-settlement indexed each new route: quantity-takeoff
> `0xf4ff209e2974a8d50c7f38ea888e456c57029bb3bc7169ae492d046fba8592e9`
> and disclosure-compiler
> `0x81b9b853ba88728f50ba70660b960c2cc9186542b418fd85ea5dc9d5b83c4317`.
> CDP merchant discovery now reports `total: 5`; both new routes are active.
> Semantic search ranks quantity-takeoff #8 for “embodied carbon quantity
> takeoff,” disclosure-compiler #10 for “CSRD sustainability disclosure
> automation,” regulatory-radar #4 for “energy compliance regulation scan,”
> and taxcredit-engine #12 for “clean energy tax credit calculator.” The GHG
> route did not surface for “greenhouse gas inventory API”: no prohibited
> re-seed was performed, its Wave 8 `EXTENSION-RESPONSES` payload is `{}`, and
> Bazaar still carries its pre-Wave-8 description until a future organic
> settlement refreshes it. The disposable buyer ended at zero USDC and its key
> was deleted. **Did NOT change:** prices, the frozen MCP v1 lane, PG22,
> participant spend, EC10, Connect/refund/manual CR7 rails, or Instant Payouts.
> If external settlements remain zero for a sustained observation window, the
> next lever is outbound distribution to agent builders, not more routes.
>
> **[2026-07-19, wave 7 — DEPLOYED] The three HTTP x402 front doors are
> v2-compliant, live, and indexed in CDP Bazaar; the proven in-band MCP v1
> lane remains frozen.** `X402_V2_ENABLED` is an additive, default-off gate
> beneath the master `X402_ENABLED` kill switch. When enabled, the HTTP routes
> emit `PAYMENT-REQUIRED`, accept `PAYMENT-SIGNATURE`, settle through the
> existing request-bound CDP facilitator client before serving, persist a
> payment identifier before execution, and refuse replay without running the
> tool. Each route publishes a schema-valid `extensions.bazaar` block with
> product-language descriptions and realistic input/output examples. Fresh
> CDP JWTs, Base-mainnet `USD Coin`, exact price-to-atomic math, both kill
> switches, no-free-result error paths, and durable replay refusal are covered
> by X2-1…X2-8 tests. Implementation is direct v2 wire-format composition per
> the official migration guide: the audited official Python SDK was
> `x402==2.16.0` (wheel SHA-256
> `8d536571782111dd8781cd4cf36f3b88e4f0b5d17c39251a17b8e655313a89fb`),
> but its server/EVM extras would add Pydantic/Web3 framework dependencies to
> the production image; the SDK was used only by the disposable smoke buyer.
> Gates: local and droplet **1134 passed / 0 failed / 29/29**; focused v2/http
> set **57 passed**; gateway **337 passed**. Testnet completed two total
> facilitator settlements, the second proving same-signature replay refusal;
> Bazaar feedback was `processing` and testnet discovery listed the route.
> Production image
> `sha256:72ea25039cca77bc7eb84ba90f6b153e24c53d357ae14524e05dd6137a564646`,
> rollback `viridis-stable:prev-2026-07-20b` →
> `sha256:a64f395224b21a23cb0a6314a63a1924e48f8c3913726b94e7d1e679aaca4383`.
> Exactly one mainnet self-purchase indexed each route: regulatory-radar
> `0x0da483b19b91e63ffc19470150a60755be8dee8d57161faca244aad7c714ec9d`,
> taxcredit-engine
> `0x746178a6ab67a02d5ccd0708199143068025f7a684004bc37de2e629454d35a1`,
> ghg-ledger
> `0x3c43b1a4fcac7c85a7b6b710ae38c6d676f4eaf8f8298f7359ec8f26a8f354ec`.
> Merchant discovery reports `total: 3`; all validators pass and semantic
> search for “regulatory horizon scan for energy and climate compliance”
> surfaces Viridis. **Did NOT change:** MCP v1 settlement, PG22, prices,
> participant spend, Connect/refund/manual CR7 rails, or parked Instant
> Payouts.
>
> **[2026-07-19, wave 6 — DEPLOYED] The
> first-dollar funnel now requires real backing and has a native agent-money
> front door.** (1) **PG22 closes the free payment_ref side-door:** the live
> gateway passes `EscrowCustody` into `PaymentGate`, and a FUNDED escrow grants
> credits only when its id appears in the EC3 pull-verified CASH registry.
> Bookkeeping-only `fund` calls now refuse `not_cash_funded` and teach both
> real recovery paths: Stripe `escrow_checkout` → pay →
> `confirm_escrow_funding` → retry the same ref, or Base-USDC x402. Historical
> consumed grants remain replay-safe and are not clawed back. Conversion
> telemetry now splits cash-backed vs internal escrows while retaining the old
> total as their sum. (2) **HTTP-402 front door:** GET/POST endpoints now cover
> `regulatory-radar/scan_regulations` ($0.25),
> `taxcredit-engine/calculate_tax_credit` ($2.00), and
> `ghg-ledger/calculate_inventory` ($1.00). Unpaid GET/POST returns a real
> standards-shaped 402; paid calls reuse the existing CDP verify/settle rail,
> fresh Ed25519 JWT, Base-mainnet USDC `USD Coin` domain, exactly-once ledger,
> and kill switch. Legacy discovery metadata adds `outputSchema` and binds
> `paymentPayload.resource`, but **CDP Bazaar listing is NOT complete**: its
> live no-payment validator now rejects v1 verbatim with `endpoint uses x402
> v1; upgrade to x402 v2 for bazaar discovery`, despite the same documentation
> describing v1 `outputSchema` compatibility. Merchant lookup currently shows
> zero resources. A v2 migration changes the payment wire/settlement contract
> and is outside Wave 6's hard boundary against new crypto/settlement code;
> Fable review is required. (3) ARD,
> healthz, and the three priced MCP descriptions expose exact prices, 10/day
> free tier, x402 URL, cash escrow route, and `/seats`. **Did NOT change:**
> participant earnings spend (`participant_bridge` untouched), any price,
> CR7 money-movement rails, or Instant Payouts (still parked). Local release
> gate: **1113 passed / 0 failed / 29/29**, gateway **316/316**. Production:
> image `sha256:a64f3952…`, rollback
> `viridis-stable:prev-2026-07-20` → `sha256:095be436…`; six Wave 6 smokes
> green (cash-path smoke n/a because the production Stripe key is live-mode,
> not test-mode; no card charge was created). No money moved in this deploy.
>
> **[2026-07-19, DEPLOYED — the payment-autonomy stack is LIVE]** All
> five waves shipped to prod by Sol (image `sha256:095be436…`, rollbacks
> `prev-2026-07-19-rkfix` + `prev-2026-07-19`), healthz ok, all smokes
> pass. **Stripe Connect is ENABLED on the platform account, identity
> verified, restricted key extended (charges/refunds/transfers/accounts/
> account-links write), livemode confirmed.** The autonomous rail is
> live: per-payee activation = begin_payout_onboarding → payee completes
> Stripe-hosted onboarding → payouts_enabled → released escrows transfer
> autonomously. Field events during deploy, both resolved: (1) stale
> droplet build tree (full-tree sync is now the standing deploy unit;
> numpy added to the test-env recipe); (2) REAL DEFECT found+fixed by
> Sol: livemode fallback only recognized `sk_live_` — prod uses an
> `rk_live_` restricted key, so live Connect accounts misreported as
> test. Fixed in gateway + payments copy + mirror with regression tests
> (`_LIVE_KEY_PREFIXES`), fleet now **1104/0/29** (verified
> independently by Fable post-deploy). (3) The Connect smoke created an
> accidental LIVE connected account (Stripe Link autofilled Justin's
> real bank) — cleaned safely: checkout unpaid, zero transfers, account
> deleted, registry entry removed, DB backed up first. LESSON: livemode
> Connect smokes create REAL accounts; use designated test-payee ids
> and delete after. Remaining unproven-in-anger: first live refund and
> first live transfer (implementation + scopes verified; idempotent +
> fail-closed). Proposed wave 6 (Instant Payouts, ~1% margin) is parked
> — the binding constraint is demand volume, not payout latency; funnel
> work (seats distribution, Bazaar wrapper) outranks it.
>
> **[2026-07-19, wave 5] Mechanical remainder of the Connect-rail day —
> revenue wedge, outflow visibility, and a real gap closed.** All edited +
> tested locally, NOT deployed (see the Wave 5 addendum in
> `docs/deployment/HANDOFF_CONNECT_RAIL_DEPLOY_2026-07-19.md`). (1)
> **PG21b seat upsell**: `payment_gate.py` gained `SEAT_PLANS` (sourced
> from `subscriptions-agent/data/plan_catalog.v0.3.0.json`) — every 402
> refusal for a covered agent (regulatory-radar, disclosure-compiler,
> ghg-ledger, taxcredit-engine) now carries a `payment.seat_option` field
> with the cheapest covering plan, price, included calls, and the
> checkout URL; additive only, absent on subscription_overage and for
> uncovered agents (smartscale, protogen, ...). No file I/O per request —
> the catalog is hardcoded and dated in a comment. (2) **RV7 in
> `reconciliation.py`**: a new `connect_rail` bucket reports money OUT via
> Stripe's licensed rails — Connect transfers (grouped by
> `transfer_group`, which is always the originating escrow_id or bond_id)
> and refund-to-originator refunds (custody instructions carrying a real
> `refund_id`). Read-only, additive, never summed into
> settled_minor/redeemed_minor/a2a_escrow; degrades to an empty bucket
> with no connect/custody object. (3) **Bond leg admin close-out — a real
> pre-existing gap, now closed**: the wave-4 CB4 legs refactor left no way
> to mark a `claimant_payout` leg with `rail: "manual"` executed after
> Justin pays it in the dashboard. `bond_bridge.py` gained
> `mark_leg_executed(bond_id, claim_id)` (idempotent per leg, recomputes
> the top-level `executed` flag, save-or-revert) and the gateway gained
> the matching admin tool `mark_bond_leg_executed` (same admin-token
> pattern as `mark_escrow_payout_executed`). (4) **Participant Connect
> integration test**: `test_participant_bridge.py` proves a
> participant-bridge escrow settles autonomously via the real
> `EscrowCustody` + `ConnectRail` composition once the payee onboards —
> coverage of an already-working path, no production changes. Did NOT
> touch: `connect_rail.py`, `stripe_payments.py`, `weave.py`, EC10 logic,
> the escrow/surety/arbitration cores, x402, any price or rate. Mirrors
> byte-identical in `_public-repo-viridis-agent-fleet/gateway/`. Fleet:
> 1103 passed / 0 failed / 29/29 suites clean (baseline 1093; +10 net —
> +12 new tests across the 4 touched files, individually and
> collect-only verified present and passing in the full-directory run;
> the 2-test gap against naive arithmetic traces to something outside the
> 4 touched files — not reproducible as a failure or a missing test
> either isolated or in-suite — flagged for Justin, not blocking).
>
> **[2026-07-19, wave 4] Bond settlements split into per-leg rails +
> connect_verified tier reachable in prod.** (1) `bond_bridge.py` CB4
> LEGS REFACTOR: settlement now certifies per-counterparty legs —
> `provider_return` (own collateral back) auto-executes ALWAYS, even on
> slashed bonds (it was only gated before because it was fused to the
> claimant leg); `claimant_payout` legs (one per PAID claim) pay
> autonomously via the Connect rail when the claimant is onboarded
> (exactly-once per bond+claim), else certify manually with the
> onboarding hint; top-level `executed` = all legs; transient rail
> failures record nothing (fully retryable); gateway passes `connect`
> to BondBridge. (2) `verified_stats_from_core` adapter
> (escrow_custody.py) wired in the gateway: EC10's connect_verified
> tier (100 bps margin) now resolves sync from the verified core's V7
> pure surface — payee id must equal the registered provider string
> (uw-v1 keying); unknown/error → 0, fail-safe. (3) ASSESSED, no code
> needed: participant cash-out flows exclusively through
> escrow_settlement_instruction (EC5) and arbitration rulings execute
> release/refund onto the escrow — both inherit the dual-rail
> automatically. **What did NOT change:** no prices/rates, no cores,
> CR7 (no third money path), manual legs still admin-gated (close-out
> tool queued to Sonnet). Fleet **1093 passed / 0 failed, 29/29**;
> mirrors synced. Remaining mechanical work (seat upsell envelope,
> reconciliation bucket, bond-leg admin close-out) handed to Sonnet:
> `docs/deployment/PROMPT_SONNET_FINISH_CONNECT_RAIL_2026-07-19.md`.
>
> **[2026-07-19, pricing] esc-fee-v1 adopted (Justin delegated the call;
> standing veto before deploy).** Finding: the flat EC9 floor is
> mis-calibrated — card processing is 2.9%+30¢ of the WHOLE escrow, so
> the 1% default fee LOSES money on every card-funded third-party
> settlement at realistic size (−$19.30 on a $1,000 escrow; breakeven
> ~290–350 bps). Fix: EC10 dynamic floor (cost + earned margin) with
> network-aligned discount tiers — payees drop from 200 bps margin to
> 150 (Connect-onboarded) to 100 (+ ≥10 verified deliveries); still the
> value leader vs Escrow.com/Upwork/Fiverr at every tier; pre-committed
> volume de-escalator (weave-escalator pattern, inverse). The rate
> schedule IS the network mechanic: discounts are earned only by
> behaviors that compound liquidity and non-portable track records.
> Spec: `docs/deployment/ESCROW_FEE_SCHEDULE_esc-fee-v1.md`.
> **BUILT same session (Fable, not delegated): EC10 live in
> escrow_custody.py** — versioned FEE_SCHEDULE dict, tiered dynamic
> floor, actionable refusals (required_fee_bps + discount path), version
> + tier stamped on funding records, viridis:* exempt, frozen fees never
> mutated; 5 new tests incl. the structural proof test (minimum passing
> fee nets >= tier margin after true card cost, sweep across amounts ×
> tiers). Fixtures raised, EC10 never weakened. Fleet **1090 passed / 0
> failed, 29/29**. Mirror synced. Note: the connect_verified tier needs
> a sync verified-stats adapter to light up in the gateway (verified
> core is async) — small item left in the Sonnet prompt. viridis:*
> payees, cash-out fee, and bond premiums unchanged.
>
> **[2026-07-19, third wave] THE ESCROW LOOP IS CLOSED — autonomous AND
> legal, end to end.** Justin's directive: the escrow system must be
> autonomous and legal; find the system loop. Built (edited + tested
> locally, NOT yet deployed —
> `docs/deployment/HANDOFF_CONNECT_RAIL_DEPLOY_2026-07-19.md`):
> **(1) Real refunds** — escrow_custody's REFUNDED branch now issues an
> actual Stripe refund to the original session (was bookkeeping-only
> after wave 2); Idempotency-Key `escrow-refund:<escrow_id>`, fail-closed
> + retryable. **(2) connect_rail.py (NEW, CR1–CR7)** — the structural
> gate: payees onboard via Stripe Connect Express
> (`begin_payout_onboarding` tool; Stripe runs KYC/AML), payout
> eligibility pull-verified live at transfer time, transfers exactly-once
> per purpose_key (doubles as the Stripe Idempotency-Key — no crash can
> double-pay). **(3) escrow_custody dual-rail payouts** — RELEASED to a
> Connect-onboarded payee auto-executes via Stripe's licensed Transfer
> rail (`executed: true`, transfer_id, rail "connect"); non-onboarded
> payees fall back to the certified `action_for_justin` instruction
> (rail "manual", now carrying the onboarding hint that converts them).
> **(4) stripe_payments P8–P12** — refund/transfer/Connect-account
> primitives, Idempotency-Key REQUIRED on every money-moving POST.
> Gateway: 2 new tools + connect_rail in /healthz.
> **Why this is the legal fix:** Stripe is the licensed money
> transmitter; the fleet only instructs its processor to pay Stripe-KYC'd
> recipients — the standard marketplace structure. The 18 U.S.C. §1960
> human gate isn't lifted by policy, it's REPLACED by structure: no
> onboarded account → no autonomous payout, only the manual path (CR7,
> no third path exists). The manual gate now shrinks payee-by-payee as
> they onboard. Tests: 47/47 targeted (13 new CR + P8–P12), fleet
> **1087 passed / 0 failed, 29/29 suites**. Mirrors synced.
> **Needs Justin before live** (in the handoff): enable Connect
> (Express) on acct_1BLyFZDTpwaqE8Ss + ensure the droplet key has
> refund/transfer/account write scopes. Follow-ups flagged: bond_bridge
> slash-claimant onto the same rail (instruction split), weave external
> payees, arbitration payouts.
>
> **[2026-07-19, later] Refund-to-originator autonomy — second scoped
> wave of the doctrine split below.** The legal research on
> `docs/legal/THIRD_PARTY_PAYOUT_LICENSING_QUESTION_2026-07-19.md`
> surfaced a nuance: returning money to the party who posted it is not
> "transmission to another person" (18 U.S.C. §1960 exposure) the way a
> payout to an unrelated third party is. Implemented accordingly, edited +
> tested locally (NOT yet deployed —
> `docs/deployment/HANDOFF_REFUND_AUTONOMY_DEPLOY_2026-07-19.md`):
> **(1) escrow_custody.py EC5**: `settlement_instruction()` for a
> REFUNDED escrow (payer's own cash back to the original Checkout
> session) now auto-executes at certification time — `executed: true`,
> `executed_at` set, `scope: "same_party_refund"`; `mark_executed`
> becomes a no-op idempotent confirmation for refunds (weave
> `mark_transfer_executed` pattern). **(2) bond_bridge.py CB4**:
> `certify_settlement()` with `slashed == 0` (clean expiry — pure return
> of the provider's own collateral, premium already Viridis revenue at
> bind) auto-executes the same way. Bonus fix found by the new coverage:
> the bridge read `slashed_minor` from surety status but the core
> exposes `slashed_total` — slashed always computed 0, which under the
> new rule would have auto-executed slashed settlements; now reads the
> real field.
> **What did NOT change:** third-party payout paths are byte-identical
> in semantics — RELEASED escrows to non-`viridis:*` payees still
> produce `executed: false` + `action_for_justin`, gated behind the
> admin-token `mark_executed`; any bond settlement with `slashed > 0`
> (a real claimant is paid) stays fully certified-only and human-gated.
> The legal gate holds until counsel signs off or payouts move to Stripe
> Connect (scoped, not built:
> `docs/deployment/SCOPE_STRIPE_CONNECT_MIGRATION.md`). Splitting a
> slashed bond settlement into a gated claimant-payout + autonomous
> provider-return pair is a flagged follow-up refactor. Tests: targeted
> 29/29; full fleet 1069 passed / 0 failed, 29/29 suites (baseline 1068
> + 1 new gated-slash test). Public mirrors synced.
>
> **[2026-07-19] Money-movement doctrine corrected — the "software never
> moves money" line below is now split, not blanket.** Justin: the fleet
> exists so agents handle money autonomously; he is not meant to be a
> bottleneck. Verified via `get_stripe_account_info`: EnergyAI and Viridis
> Conservation share ONE Stripe account (`acct_1BLyFZDTpwaqE8Ss`,
> ViridisNorth) — the weave's revenue-share allocation between them is
> same-account bookkeeping, not a wire, so it now **auto-executes with no
> human step** (`weave.py` WV4, `deploy/gateway/weave.py` +
> `_public-repo-viridis-agent-fleet/gateway/weave.py`, 12/12 tests green).
> Cross-account/third-party payouts (escrow_custody EC-series cash-out,
> collateralized-bond slashing via bond_bridge) stay certified-only and
> human-gated — that gate is a real open money-transmission-licensing
> question (PR2's merchant boundary), not a design preference, and it
> lifts only after counsel answers
> `docs/legal/THIRD_PARTY_PAYOUT_LICENSING_QUESTION_2026-07-19.md`. See
> memory `feedback_autonomous_money_movement` — supersedes the 2026-07-15
> "weave auto-payout dropped, Justin manages Stripe manually" decision.
>
> **Current deployment-stable snapshot (2026-07-16 evening): 22 gateway
> mounts, all live; `run_fleet_tests.py` is 814 passed, 0 failed, 26/26
> suites clean. BOTH payment rails deployed + smoked live same day:** the
> a2a escrow rail (PG13–PG16, esc_000006 consumed for a real paid call) AND
> **PG17 real custody** (escrow_custody.py EC1–EC8: escrows cash-fund via
> pull-verified Stripe Checkout; 1% fee certified on third-party payouts —
> software never executes cash out; reconcile splits cash vs internal
> ledger honestly). Monetization doctrine ratified:
> docs/deployment/MONETIZATION_REVIEW_2026-07-16.md — free rails, taxed
> transactions, enterprise margin; the 13 ungated agents stay free.
>
> **Night wave (2026-07-16, all deployed + verified live; fleet 835/835,
> 26/26): THE WEAVE IS LIVE** (weave.py WV1–WV6, rate weave-B-v1 ratified:
> 10% subs / 5% leads + pre-committed escalator) — first woven event
> executed: EnergyAI's real $75 invoice → $3.75 share → **375 kg CO₂e
> retired** through the fleet's own clearinghouse (Verra provenance, cert
> 1fa495be…); certified $3.75 transfer pending Justin. **EC9 fee floor**
> (custody refuses unprofitable third-party escrows: frozen fee < 50
> minor). **PG18 per-caller free tiers** (each transport-derived identity
> gets its own N/day; bounded anonymous pool defeats fingerprint rotation —
> one scraper can no longer starve real evaluators). escrow 0.1.2 published
> to the official registry. Remaining amber: surety bond-WRITING only
> (funded reserve decision, or the flagged capital-free collateralized-bond
> design — provider posts own cash escrow as collateral via PG17 custody).
> New since 07-15 (awaiting deploy — `docs/deployment/DEPLOY_2026-07-16.md`):
> **the a2a payment rail is real** (PG13–PG16: `payment_ref=<escrow_id>` on
> any gated call verifies + consumes a FUNDED escrow for prepaid credits via
> escrow's own E6 exactly-once machinery; escrow core v0.1.2 adds the E9 sync
> surface); **protogen's ungated CAD side door is closed** (create/generate/
> export bypassed gate AND metering — an external caller had already used it
> free); all 16 gated state-changing tools across 9 agents now advertise an
> optional `payment_ref` in their MCP schemas; reconciliation gained the RV6
> `escrow_settled_minor` bucket — **explicitly non-cash** (closed-loop
> internal ledger; PG17/real custody deferred pending sign-off).
> Live a2a smoke: `deploy/droplet/a2a_escrow_smoke.py` (post-deploy).
> New since 07-13: metering v0.2.0 (event-level consumer/channel/is_test
> classification, list_events, usage_timeseries, gateway-meter write
> protection), `/stats` usage dashboard, Stripe reconciliation tool, surety
> v0.2.0 `price_bond` underwriting (uw-v1), Viridis Verified relay
> (`/verified/mcp`, $0.02/call), Stripe Prices setup script (seats funnel was
> dead-ended at checkout_ready_plans:0), x402-C carbon-receipts draft spec
> (`docs/standards/`). Deploy runbook: `docs/deployment/DEPLOY_2026-07-15.md`.
>
> **GROWTH GATE (ratification pending; number reconciled 2026-07-16 at 22):
> no agent #23 until the first arm's-length external dollar settles.**
> (FLEET_REVIEW_2026-07-15 said "21" but was written before Viridis Verified
> became mount #22 the same day; repo MOUNTS and live /healthz both say 22.)
> Verified entered as the review's explicit exception (demand-side
> infrastructure, not a leaf service). New capacity goes to distribution:
> listing copy, worked tools/call examples, outreach. See
> docs/deployment/FLEET_REVIEW_2026-07-15.md.

> Previous snapshot (2026-07-13): 20 gateway-hosted agents;
> `run_fleet_tests.py` is **635 passed, 0 failed, 24/24 agent/infrastructure
> suites clean**. `quantity-takeoff-agent` v0.1.0 is the newest priced service
> at `/quantity-takeoff/mcp` (10 free calls/day, then $0.50 per takeoff), while
> Compute Ledger and Provenance now carry the v0.2.0 inventory-lineage
> extensions. Older May inventory notes are retained for historical context.

_Honest scorecard as of 2026-05-29. "Proven" = verified by execution/inspection this session. "Claimed" = asserted by docs/memory but not re-verified here._

---

## Proven this session

| Claim | Evidence |
|-------|----------|
| 32 agents are discoverable by the fleet runner | `run_fleet_tests.py` auto-discovery enumerated exactly 32 dirs; matches `pyproject.toml` testpaths (32 entries) |
| Agent code runs from its location | Ran 6 agents directly: **372 tests passed, 0 failed** — energyai (76), viridis-science-agent copy (29), global soil (29), global soil ⎵ (31), wavefunction-search (34), dscore (173) |
| The two `global soil…` folders are distinct agents | Different test counts (29 vs 31); both in `testpaths` |
| `viridis-science-agent copy` is a live agent | In `testpaths`; 29 tests pass |
| Reorg conserved all files | Counted files before/after both = **1,607** (1,517 non-git + 90 git); byte total unchanged except the two edited link-fix files |
| Doc cross-references resolve | All relative links under `docs/` re-scanned post-move → 0 broken |

## Claimed but not re-verified here

| Claim | Source | Why not verified |
|-------|--------|------------------|
| Full fleet ≈ 1,058 tests / 0 failures | memory (Fleet v4.2), `docs/testing/TEST_*` | Aggregate `run_fleet_tests.py` needs pytest in site-packages; `~/.local` overlay is 100% full this session, so only a 6-agent sample was run directly |
| Energy AI = PRODUCTION, Bounty Hunter = RUNNING | `docs/fleet/FLEET_INDEX.md` | Deployment/revenue state not exercised this session |
| Most other agents = PROTOTYPE / MVP | `docs/fleet/FLEET_INDEX.md` | Maturity labels are self-reported in the index |
| Revenue models ($/lead, $/finding, AUM fees…) | `agent.yaml` + FLEET_INDEX | Projected economics, not realized revenue |

## Known gaps / risks

- **Aggregate test runner is environment-fragile.** It hard-sets `PYTHONPATH` to the agent dir per subprocess, so pytest must be in site-packages — not satisfiable while `~/.local` (the `/sessions` overlay) is full. Per-agent direct runs work fine.
- **`__pycache__` (110 dirs) can't be cleaned** in this sandbox (`Operation not permitted` on the mount). Excluded from counts; cosmetic only.
- **Three nested `.git` repos** live under `_workspaces/Viridis CEO Agent ` and `_archive/` — keep them intact; don't run git ops from the fleet root.
- **Maturity labels are unaudited.** "PRODUCTION/MVP/PROTOTYPE" come from the agents' own docs, not an external check.

---

## Critical-path dependencies

```
fleet_utils (shared primitives)
      └──> every agent imports these — a break here breaks the fleet
_AGENT_TEMPLATE
      └──> shape of every new agent; changes propagate by convention
pyproject.toml testpaths + run_fleet_tests.{py,sh}
      └──> coupled to flat root layout; the gate for "is the fleet green?"
Revenue flywheel (per FLEET_INDEX):
  observe → model → value → originate → verify → trade → regulate → narrate → reinvest
  (Pillar-1 bootstrap agents fund Pillar-2/3 build-out)
```

## Next-action backlog — ranked by leverage ÷ effort

1. **Install pytest into site-packages, then run the full `run_fleet_tests.py`.** _High leverage, low effort._ Converts the 1,058-test claim into a proven, repeatable green check. Blocked only by the full `~/.local` overlay — free space or use a writable site-packages.
2. **Snapshot per-agent test counts + statuses into `STATUS.md`.** _High ÷ low._ Once #1 runs, capture the real totals here so future sessions start from proven numbers.
3. **Advance Pillar-1 revenue agents along `docs/deployment/STAGED_DEPLOYMENT_PLAN.md`** (Energy AI → live leads; Bounty Hunter → active findings). _High ÷ medium._ These fund everything else.
4. **Audit maturity labels** against actual adapter/deploy readiness; downgrade anything that can't deploy today. _Medium ÷ low._ Removes optimism bias from the index.
5. **Reconcile the two `global soil…` agents** — decide whether the trailing-space variant is a deliberate fork or drift; document the difference (31 vs 29 tests) in its `AGENT.md`. _Medium ÷ low._
6. **Decide the fate of `_workspaces/` and `_archive/` contents** — promote anything still active, or leave archived. _Low ÷ low._
