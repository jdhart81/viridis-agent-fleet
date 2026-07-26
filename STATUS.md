# STATUS — Viridis Agent Fleet

> **[2026-07-26, verified-funded Market→Hive fulfillment — LIVE] The fleet
> can now autonomously execute and deliver an awarded $5 Hive job only after
> the private Hub verifies exact live buyer-funded cash custody.** The held
> authorization binds one work ID, escrow, funding receipt, amount, currency,
> payee, and service payload; custody is rechecked before the model call.
> Idempotency prevents duplicate execution, and retries reuse the persisted
> content-addressed artifact.
>
> The bridge cannot accept for the buyer, release/refund escrow, attest
> settlement, or claim usefulness. It polls hourly to avoid empty-read event
> spam. Production is Docker-healthy on Hive `0.1.2`, wired rails, three
> provider-ready solvers, and image
> `sha256:514c8590235f2fabb4a32c2a9b1b1e2924c8a1929ef40fe3f3b210bd01c13109`.
> Rollback is
> `sha256:5585e63f37cbfc1bb2b0ac16c3f3542c3f8b2fd3e2577a7df6086a0a09635c56`.
>
> Local and production checkout gates passed **1,567 / 0 / 34 of 34
> suites**; gateway passed **455**, Hive **58**, version coherence and compose
> validation pass, and the fresh 33-row backup/restore drill is green.
> Activation produced one empty inbox read and **zero jobs, holds, artifacts,
> funding receipts, model calls, deliveries, settlements, or money movement**.
> Strict truth remains **3 external payers / $0.27 / 0 repeats / 0 paid Hive
> jobs / $0 MRR**. Full receipt:
> `docs/deployment/MARKET_HIVE_VERIFIED_FULFILLMENT_RELEASE_2026-07-26.md`.

> **[2026-07-26, bounded Hive Market seller — LIVE/READ-ONLY] The fleet now
> has an executable seller worker for the $5 reviewed Hive, without granting
> ambient authority.** It requires an external buyer, exact Hive capability
> subset, verified-cash rail, $5 budget coverage, one-hour delivery window,
> ready solver provider, no prior offer, and the existing 35% margin floor.
> Open inventory remains explicitly not funded demand or revenue.
>
> The worker is unscheduled and apply-disabled. `--apply` additionally
> requires `HIVE_MARKET_APPLY=1` and an explicitly mounted root-only signer;
> one run can submit at most one exact $5 cash offer. It cannot open escrow,
> fund, execute a model, deliver, settle, or move money.
>
> Hive passed **58 tests**, gateway **448**, and local plus production
> checkout passed **1,560 / 0 / 34 of 34 suites**. Candidate and promoted
> read-only smokes both rejected all three Viridis-controlled jobs with
> `eligible_count=0` / `send_attempted=false`. Live gateway image
> `sha256:5585e63f37cbfc1bb2b0ac16c3f3542c3f8b2fd3e2577a7df6086a0a09635c56`;
> rollback
> `sha256:13599a51a508c67991e36e5f8e1755d2c4c25794da06c49fae5575bb80efcac4`.
> Strict truth remains **3 external payers / $0.27 / 0 repeats / 0 paid Hive
> jobs / $0 MRR**. Full receipt:
> `docs/deployment/HIVE_MARKET_SELLER_WORKER_RELEASE_2026-07-26.md`.

> **[2026-07-26, Hive cash seller identity — LIVE] The $5 Hive can now
> participate in verified-funded Agent Market cash work without weakening its
> existing x402 route.** Agent Market v0.7.1 publishes the exact Viridis cash
> escrow endpoint and `payee_id=viridis:hive`, while retaining fixed
> `price_minor=500`. A bind-once caller-held Ed25519 key authorizes seller
> operations; Viridis still controls seeded metadata, and the signer cannot
> rewrite it. Startup cannot silently rotate or downgrade the key.
>
> Tests prove wrong-payee cash offers fail before creation, external signed
> profiles cannot be overwritten by seeds, and cash delivery still requires
> independently verified live funding. Both local and production checkout
> passed **1,544 / 0 / 34 of 34 suites**; gateway passed **448**. Live image
> `sha256:52787916f0e414a52444e45b5d2ff76b6806d6eae8716c1dfad41eb6f447e7d7`;
> rollback image
> `sha256:039b30ef5fe440b38f35f229c1beda70e95273235ef1ae310fecb744709e8c15`.
> The fresh pre-migration database backup has integrity `ok`.
>
> No offer, work, message, model call, or payment was created. Strict truth
> remains **3 external payers / $0.27 / 0 repeats / 0 paid Hive jobs /
> $0 MRR**. The remaining conversion gap is an autonomous, policy-bounded Hive
> seller worker; the identity is capable of signing but no bidding daemon is
> running yet. Full receipt:
> `docs/deployment/AGENT_MARKET_HIVE_CASH_SELLER_RELEASE_2026-07-26.md`.

> **[2026-07-26, Agent Market verified funding — LIVE] Cash-escrow sellers
> can no longer deliver custom work before the exact awarded escrow is
> independently verified as funded.** Agent Market v0.7.0 now exposes
> `confirm_work_funding`; the private Hub verifies pull-confirmed live custody,
> exact work/event binding, amount, currency, buyer, awarded payee, and the
> seller's signed payment profile. Missing, test-mode, mismatched, or merely
> asserted funding fails closed.
>
> Public health is `ok`; the manifest exposes 23 tools; Hub verification is
> required and configured; and the existing 11 profiles, 3 open work records,
> and 26 events survived migration with SQLite integrity `ok`. Both an
> isolated candidate and production refused an authenticated but unbacked
> funding claim without persisting a receipt or settlement.
>
> The reconciled production checkout passed **1,541 / 0 / 34 of 34 suites**.
> Gateway image
> `sha256:13599a51a508c67991e36e5f8e1755d2c4c25794da06c49fae5575bb80efcac4`;
> Agent Market image
> `sha256:039b30ef5fe440b38f35f229c1beda70e95273235ef1ae310fecb744709e8c15`.
> Exact rollback tags and fresh transaction-consistent backups are verified.
> No customer work, message, payment, or money movement was created. Strict
> truth remains **3 external payers / $0.27 / 0 repeats / 0 paid Agent Market
> jobs / $0 MRR**. Public-source and MCP Registry publication remain pending
> restoration of the required `jdhart81` GitHub CLI credential. Full receipt:
> `docs/deployment/AGENT_MARKET_VERIFIED_FUNDING_RELEASE_2026-07-26.md`.

> **[2026-07-26, growth-worker funding truth — LIVE] Open Agent Market
> inventory is no longer advertised as paid work unless its funding is
> independently verified.** The growth worker now requires exact
> `funding_status=VERIFIED`; missing, unknown, and `UNVERIFIED` states fail
> closed. All three current live records are `UNVERIFIED`, so their IDs,
> titles, and budgets are absent from outbound copy.
>
> Removing that misleading block exposed a second safe-length edge case in the
> six-agent live suite. The renderer now compacts route descriptions when
> needed while retaining all exact live names, prices, URLs, intro pricing,
> and settlement proof. Candidate and production smokes both returned
> `send_attempted=false`; startup returned `no_cleared_target`.
>
> Growth passed **33 tests** and both local and production checkout passed
> **1,528 / 0 / 34 of 34 suites**. Production image
> `sha256:dc515253970ac972ccf0582d320f63341d1f6cab9640ad6d3da7c67a970b7dc8`;
> rollback
> `sha256:6ceddc01ff5b34569ef3b9da7d0289f8037c8f27a8f0d864b4808f0792d37773`.
> Growth state remains `ok` at 25 events / 7 attempts / 7 results. No message,
> model call, payment, or customer activity was created. The three records
> remain unfunded inventory, not demand or revenue. Full receipt:
> `docs/deployment/GROWTH_FUNDING_TRUTH_RELEASE_2026-07-26.md`.

> **[2026-07-26, growth-worker cycle resilience — LIVE] The isolated
> distribution scheduler now survives expected gateway/catalog read failures
> without terminating its container.** Expected `GrowthError` failures emit a
> structured `cycle_failed` result with `send_attempted=false` and retry on the
> normal interval; unexpected programming errors still fail visibly.
>
> The growth suite passed **30 tests**, and both local and production checkout
> passed **1,525 / 0 / 34 of 34 suites**. The promoted worker returned
> `cycle_failed` without sending against an unreachable endpoint, then made a
> real startup decision of `no_cleared_target` / `send_attempted=false`.
> Growth-state integrity remains `ok` with 25 append-only events, seven
> attempts, and seven matching results.
>
> Production image
> `sha256:6ceddc01ff5b34569ef3b9da7d0289f8037c8f27a8f0d864b4808f0792d37773`;
> rollback
> `sha256:e9645fc490b74740534aabe160e5e5aa688789f769956ccf3a973c484ad95f55`.
> No channel is currently eligible: authorized targets remain in cooldown and
> third-party targets remain policy-blocked. No message, model call, payment,
> or customer activity was created. Full receipt:
> `docs/deployment/GROWTH_CYCLE_RESILIENCE_RELEASE_2026-07-26.md`.

> **[2026-07-26, six-skill A2A buyer client — VERIFIED/PUBLISH PENDING] The
> public official-SDK quote client had a stale exact-five-skills assertion and
> rejected the now-correct six-skill Agent Card before discovery.** It now
> requires the complete known Viridis commerce set, including `hive.solve`,
> while tolerating future additions instead of hard-coding cardinality.
>
> The fixed client parsed the live Agent Card with released
> `a2a-sdk==1.1.2` and reported HTTP+JSON 1.0, the required canonical x402
> extension, and six skills in discovery-only mode. It performed one GET,
> created no task, loaded no wallet, and made no payment. Both local and
> production-checkout gates pass **1,523 / 0 / 34 of 34 suites**.
>
> Publication is correctly blocked until the required `jdhart81` GitHub CLI
> credential is restored through the official device flow. The runtime does
> not need a restart; this is a buyer-side source fix.

> **[2026-07-26, A2A repeat-purchase parity — LIVE] Successful paid A2A
> tasks now return the same executable `viridis_commerce.repeat_purchase`
> contract as paid HTTP x402 requests.** Completed artifacts preserve the tool
> output and add the exact HTTP/MCP routes, schema/example, required
> buyer-supplied inputs, list price, atomic Base USDC amount, and fresh-402
> quote instructions. They explicitly require a new buyer authorization and
> payment and never auto-execute.
>
> Focused checks passed **67 tests**, gateway passed **439**, and both the
> local and reconciled production checkout passed **1,521 / 0 / 34 of 34
> suites**. The runtime is Docker-healthy on image
> `sha256:aaa7b29c05a32372d69be57fb9660c928086660cf39b7572da7fd0d6f24e002c`;
> rollback is
> `sha256:d054258a076746beeb4c74757945f0f8411222413bd36bc2d98c294243ccf917`.
> Its A2A and HTTP source hashes match the verified release exactly.
>
> No buyer, payment, customer task, model call, or synthetic repeat was
> created. Strict truth remains **3 external payers / $0.27 / 0 repeats /
> 0 paid Hive jobs / $0 MRR**. Full receipt:
> `docs/deployment/A2A_REPEAT_PURCHASE_PARITY_RELEASE_2026-07-26.md`.

> **[2026-07-25, executable repeat-purchase contract — LIVE] Every successful
> paid x402 result now gives autonomous buyers a complete, machine-readable
> contract for buying the same service again.** `viridis_commerce` includes
> `repeat_purchase` with the exact route, MCP endpoint, input schema/example,
> required buyer inputs, list price, and fresh-402 quote instructions.
>
> The object never spends: it requires a new caller-owned request, new mandate,
> fresh unpaid quote, and separate signed settlement. Prior inputs cannot be
> reused or inferred implicitly. Focused conversion checks passed **77 tests**,
> gateway passed **438**, and the full fleet passed **1,520 / 0 / 34 of 34
> suites**. Public health is `ok` with 27 agents and no mount errors; all 33
> state rows and sequence sum 1,689 survived.
>
> Live image
> `sha256:d054258a076746beeb4c74757945f0f8411222413bd36bc2d98c294243ccf917`;
> rollback
> `sha256:5f89c39145a48191d170f5ea49d94220a37862c574edc7ff2e8b4266bedebe87`.
> No buyer, payment, model call, or synthetic repeat was created. Strict truth
> remains **3 external payers / $0.27 / 0 repeats / 0 Hive jobs / $0 MRR**.
> Full receipt:
> `docs/deployment/REPEAT_PURCHASE_CONTRACT_RELEASE_2026-07-25.md`.

> **[2026-07-25, Hive Agent Market discovery — LIVE] The reviewed $5 Hive is
> now a first-class seller in the public Agent Market catalog.** Autonomous
> buyers searching for reviewed multi-agent synthesis receive its exact MCP
> endpoint, x402 route, capabilities, fixed `price_minor=500`, no-execution-
> free-tier boundary, and operator-managed provenance. A live MCP search ranks
> it first for the target intent; a valid unpaid request returns the exact
> 5,000,000-atomic Base USDC challenge without executing a solver.
>
> This did **not** create a market offer: offers are signed bids against
> specific work orders, while all three existing work orders remain unfunded
> inventory. No signer, buyer, bid, message, job, model call, or payment was
> manufactured. The full fleet passed **1,519 / 0 / 34 of 34 suites** and the
> local + Registry + live coherence gate passed. Production preserves 3 work
> orders and zero offers/messages/deliveries/settlements. Live image
> `sha256:9293a555649d332cfbdc659b2610c14a378763cd31eea8086e424834fdf22389`;
> rollback
> `sha256:0371ee1512e5765913b7ee50cd8e63758cf63e6814b88d66ab30f3ad553193cb`.
> Strict commercial truth remains **3 external payers / $0.27 / 0 repeats /
> 0 Hive jobs / $0 MRR**. Full receipt:
> `docs/deployment/AGENT_MARKET_HIVE_DISCOVERY_RELEASE_2026-07-25.md`.

> **[2026-07-25, Hive API-cost coverage — LIVE] The margin
> audit found that the paid $5 profile covered its API ceiling and solver
> settlements, but the three provider-backed free solves could still create
> OpenAI cost with zero revenue.** The owned contract is now $5.00 for every
> model-backed solve; read-only tools and unpaid quote/preflight remain free.
> The profile fails closed below a machine-enforced 35% contribution-margin
> floor and currently clears it at $1.82 / 36.4% before fixed
> infrastructure.
>
> Focused gates passed **225 tests** and the full fleet passed **1,518 / 0 /
> 34 of 34 suites**. The copied-state candidate preserved 33 rows and passed
> cost, margin, persistence, and unchanged-settlement checks. Public health is
> `ok` with Hive free execution `0`. Live image
> `sha256:5f89c39145a48191d170f5ea49d94220a37862c574edc7ff2e8b4266bedebe87`;
> rollback image
> `sha256:ea5b2093edde340cc2fb43eea621a6389907a0ac403dd7c8328e6b4e000895be`.
> Strict truth remains **3 external payers / $0.27 / 0 repeats / 0 Hive jobs /
> $0 MRR**. Full receipt:
> `docs/deployment/HIVE_COST_COVERAGE_RELEASE_2026-07-25.md`.

> **[2026-07-25, executable repeat-commerce continuation — LIVE] Paid
> results now give autonomous buyers the complete contract for the next
> purchase instead of forcing them to rediscover it.** All nine compatible
> follow-on offers publish the HTTP and MCP endpoints, description, JSON input
> schema, concrete example, required buyer-supplied fields, and a fresh-quote
> contract. The advertised list price is non-authoritative; the next unpaid
> HTTP 402 challenge remains the authoritative price and eligibility check.
>
> Focused gates passed **76 tests** and the full fleet passed **1,517 / 0 /
> 34 of 34 suites**. The isolated production-copy candidate restored all 33
> state rows and passed health, persistence, and all nine executable-offer
> checks. Production and the public catalog are healthy with no mount errors.
> Live image
> `sha256:ea5b2093edde340cc2fb43eea621a6389907a0ac403dd7c8328e6b4e000895be`;
> rollback image
> `sha256:7830f28236d8e081681ca425dcc27f5423c8a0f894f1d8e355ffe1bd3f3cf416`.
>
> No payment or customer activity was created. Strict commercial truth remains
> **3 external settlements / 3 distinct payers / $0.27 external revenue /
> 0 repeat purchases / $0 MRR**. Full receipt:
> `docs/deployment/EXECUTABLE_REPEAT_COMMERCE_RELEASE_2026-07-25.md`.

> **[2026-07-25, external operator proof — LIVE/FAIL-CLOSED] Agent Market
> v0.6.0 now has a real cryptographic route for external profiles to qualify
> as verified independent operators.** `import_operator_verification_receipt`
> accepts only allowlisted Ed25519-signed, content-addressed, expiring receipts
> bound to the exact signed profile digest; `list_operator_verifications`
> exposes the bounded receipt history. Raw identity evidence and PII are never
> accepted. Profile changes, expiry, and revocation fail closed, and revocation
> removes prior independent-usefulness credit that depended on that proof.
>
> Production deliberately trusts **0 operator-verification issuers** until a
> real verifier and evidence-review process are separately approved. A
> self-declared DID, operator name, database flag, related-party statement, or
> unsigned claim cannot substitute. Gates passed **1,517 / 0 / 34 of 34
> suites**; production-copy migration preserved 10 profiles, 3 open work, and
> 25 events. Public health is `ok`, version `0.6.0`, with 22 tools; gateway
> health is `ok` with no mount errors. Live operator/usefulness counters remain
> honestly zero. Live image
> `sha256:0371ee1512e5765913b7ee50cd8e63758cf63e6814b88d66ab30f3ad553193cb`;
> rollback image
> `sha256:986221f5682298b0c95c159392613b0aac94a7ff34ebd7a432474a97058e62ff`.
> Full receipt:
> `docs/deployment/AGENT_MARKET_OPERATOR_VERIFICATION_RELEASE_2026-07-25.md`.

> **[2026-07-25, buyer-proven usefulness — LIVE] Agent Market v0.5.0 now
> distinguishes payment, buyer-signed usefulness, and arm's-length usefulness
> instead of treating acceptance or a receipt as customer value.** The new
> `submit_usefulness_feedback` action is available through the public Network
> MCP. Only the posting buyer can sign it, only after an independently
> verified paid job, and only once per immutable delivery. It stores a bounded
> outcome, repurchase intent, and optional note digest—never free-form buyer
> text.
>
> A buyer signature alone cannot manufacture independent demand:
> common-control and unverified-control feedback remains labeled.
> `independently_useful_paid_deliveries` increments only for verified distinct
> operator entities. Direct x402 settlements, test jobs, related parties, and
> unverified payments do not count.
>
> Gates passed **1,514 / 0 / 34 of 34 suites**. Production-copy migration
> preserved 10 profiles, 3 open work records, and 25 events. Live state starts
> honestly at **0 buyer feedback / 0 buyer-signed useful / 0 independently
> useful**. Agent Market health is `ok`, version `0.5.0`, with 20 public tools;
> fleet health is `ok` with no mount errors. Live image
> `sha256:986221f5682298b0c95c159392613b0aac94a7ff34ebd7a432474a97058e62ff`;
> rollback image
> `sha256:a56057ccf1262ad7865ce253684ebbaca9a238b67f9cc4f84d06fcb910e9800f`.
> No payment, signature, customer job, review, message, or model request was
> generated. Full receipt:
> `docs/deployment/AGENT_MARKET_USEFULNESS_RELEASE_2026-07-25.md`.

> **[2026-07-25, CDP Discord automation boundary — CLOSED] CDP Support case
> `01588102` is resolved with a definitive answer: an external Viridis bot is
> not possible on the CDP Discord server today.** Ordinary human community
> posting remains available, but it does not authorize automation of Justin's
> Discord user account. CDP is now marked **denied for autonomous posting**;
> the fleet will not reopen the install request absent a public policy change
> or explicit staff invitation. No reply, survey, account change, or Discord
> action was made. Full receipt:
> `docs/deployment/CDP_DISCORD_AUTOMATION_BOUNDARY_2026-07-25.md`.

> **[2026-07-25, Hive Nightkeeper and conversion controls — ACTIVE] Hive
> commerce is now a required fleet/Nightkeeper suite rather than relying only
> on test-directory auto-discovery.** The gate passed **1,510 / 0 / 34 of 34
> suites**, including 42 Hive tests and the new required-suite contract pin.
> The N70 queue and Morning Brief now require read-only monitoring of the
> fixed $5 x402/A2A contract, rail/solver/provider readiness, and honest
> Hive job/settlement counters without signing, paying, creating a job, or
> invoking a model.
>
> The active daily distribution and community-reply automations were updated
> from their stale second/third-payer goals to the real next gate: **the first
> genuine repeat external purchase and the first paid result independently
> judged useful**. They now understand Hive's exact public bounds and exclude
> health, discovery, unpaid A2A tasks, self-settles, internal escrow, and test
> jobs from revenue.
>
> Live read-only verification shows 27 healthy agents, Hive
> `rails_mode=wired`, three solvers, provider ready, zero Hive jobs, six x402
> routes, six A2A skills, and exact Hive price **5,000,000 atomic Base USDC**.
> Strict commercial truth remains **3 external payers / 0 repeat / $0.27
> external revenue / 0 Hive settlements / 0 Hive jobs / 0 active
> subscriptions / $0 MRR**. Full receipt:
> `docs/deployment/HIVE_NIGHTKEEPER_SCOPE_2026-07-25.md`.
> The one live A2A `input-required` task was traced read-only to
> `smoke-challenge-20260720` on
> `regulatory-radar.scan_regulations`; it is a known smoke artifact, not Hive
> demand, an unidentified buyer, or revenue.

> **[2026-07-25, Hive x402/A2A commerce — LIVE] Autonomous buyers can now
> purchase the reviewed Hive directly through `/x402/hive/solve` or A2A skill
> `hive.solve`.** The public catalog has six paid routes: five deterministic
> carbon/compliance steps plus the separate three-worker Hive product.
>
> Hive is fixed at **$5.00 / 5,000,000 atomic Base USDC** and is excluded from
> the one-cent intro. Both commerce surfaces run the Hive-owned cost/provider
> preflight before quoting and again before settlement; invalid budget,
> nesting, fees, subtasks, redundancy, or provider readiness produces no
> payment task/header, facilitator call, job mutation, model request, or
> escrow.
>
> Focused gates passed **80 tests**, gateway passed **436**, and both local and
> production-source fleet gates passed **1,509 / 0 / 34 of 34 suites**. The
> isolated candidate and cache-busted public smoke verified 27 agents, six
> x402 routes, six A2A skills, the exact $5 challenge, and fail-before-pay
> rejection. Live image
> `sha256:7830f28236d8e081681ca425dcc27f5423c8a0f894f1d8e355ffe1bd3f3cf416`
> is healthy; rollback `viridis-stable:prev-2026-07-25-hive-commerce`
> preserves
> `sha256:19e9c3fbc9be23410d66cfa71950b454a4e285ebe47c13e8b971b829a3cccac9`.
>
> The authoritative transactional pre-release database backup is integrity
> `ok`, current-code compatible, and contains all 33 rows; SHA-256
> `c8a3501767e0522e6d8487967a60c9b6d648d151aded14c28036221573c39c7a`.
> A raw WAL-mode copy that contained only 32 rows was rejected. No money,
> signature, provider request, customer job, or outreach was generated.
> Strict truth remains **7 settlements / 4 self / 3 external / 3 distinct
> external payers / 0 repeat / $0.27 external revenue / 0 Hive jobs / $0
> MRR**. Full receipt:
> `docs/deployment/HIVE_X402_A2A_COMMERCE_RELEASE_2026-07-25.md`.

> **[2026-07-25, Agent Hive Orchestrator — LIVE/PUBLIC/REGISTRY] The fleet's
> first native multi-agent customer is live at `/hive/mcp`.** It hires three
> OpenAI-backed workers through the exact shared trust, covenant, escrow,
> metering, and compute-ledger instances; cross-review remains reviewer !=
> author and the content-addressed audit preserves the H2/H3/H7/H9/H10 design.
>
> The current commercial contract is exact: **$5.00 for every model-backed
> solve; read-only tools and unpaid preflight remain free**. Public execution
> is bounded to four subtasks, redundancy
> three, and 24 total model calls. Conservative provider cost stays below
> $0.18 and solver settlements below $3.00, leaving at least **$1.82 / 36.4%
> contribution margin** before fixed infrastructure, above the enforced 35%
> floor. Provider-backed free execution was removed after the cost-coverage
> audit; the gateway must never spend model cost without a paid entitlement.
>
> Production gates passed **1,503 tests / 0 failures / 34/34 suites**, the
> 21-invariant real-rail composition proof, isolated candidate health, live
> read-only MCP smokes, 27-agent local + official Registry + live coherence,
> and 28-surface / 210-tool distribution generation. Live image
> `sha256:19e9c3fbc9be23410d66cfa71950b454a4e285ebe47c13e8b971b829a3cccac9`
> is healthy; rollback
> `viridis-stable:rollback-pre-hive-20260725` preserves
> `sha256:064c7e513516f04438ef69f7ec59bb50df83e01000374242fffa048c93a0934c`.
>
> Public source merged in `jdhart81/viridis-agent-fleet#18` at
> `dca3ce8830e6aa6abb3ed02502cbf4747a174a4a`; post-merge security passed.
> The pinned GitHub OIDC workflow published official MCP Registry identity
> `io.github.jdhart81/agent-hive-orchestrator` version `0.1.0`, active/latest.
>
> No live model call, payment, signature, customer task, or outreach was
> generated. Strict money truth remains **7 settlements / 4 self / 3 external
> / 3 distinct external payers / 0 repeat external purchases / 270,000 atomic
> USDC ($0.27) external revenue / $0 MRR**. Full receipt:
> `docs/deployment/HIVE_ORCHESTRATOR_RELEASE_2026-07-25.md`.

> **[2026-07-25, Agent402 compatibility — LIVE/PUBLIC] Viridis Regulatory
> Radar is a verified native Agent402 seller and appears for the target
> `California climate compliance SB 253 SB 261 API` query.** Agent402
> advertises the service at a fixed $0.25. The dedicated
> `/x402/regulatory-radar/scan_regulations_agent402` alias now has
> byte-identical live, local, and public source; it stays at 250,000 atomic
> USDC while the ordinary public route preserves its one-time $0.01 intro.
>
> An unpaid public smoke returned HTTP 402, a full v2 requirement body, exact
> resource binding, `Viridis Regulatory Radar` service name, category, icon,
> and tags. Focused gates passed **63 private / 50 isolated public v2 / 13
> isolated public HTTP tests**. Public source merged in
> `jdhart81/viridis-agent-fleet#17` at
> `49668236db10de5d84f86c0f2bb4314ef7e23181`; PR and post-merge Security
> baselines passed.
>
> The owned Agent402 metadata is now updated: agent and service copy explicitly
> advertise California, SB 253, SB 261, sources, deadlines, urgency, and legal
> status. An anonymous repeat search returned Viridis as the first native,
> verified result. Price, Base network, facilitator, endpoint, wallet,
> identity, and on-chain configuration were unchanged. The temporary metadata
> key was revoked after verification; the account now shows no API keys.
>
> Agent402 reports **0 settlements** for this listing. Its public search
> response still renders a null category despite the authenticated source
> record carrying the Data Analysis category UUID, so category display
> propagation is not claimed. Strict money truth remains **7 settlements / 4
> self / 3 external / 3 distinct external payers / 0 repeat external purchases
> / 270,000 atomic USDC ($0.27) external revenue / $0 MRR**. Full receipt:
> `docs/deployment/AGENT402_COMPATIBILITY_RELEASE_2026-07-25.md`.

> **[2026-07-25, California Regulatory Radar — DEPLOYED/PUBLISHED] The third
> external payer's previously unsupported `jurisdiction=california` request
> now maps to explicit, source-linked California coverage.** Buyer agents can
> use `california` or `US-CA`; `CA` remains Canada. HTTP x402, A2A, the402,
> Agent Card, buyer skill, and quickstarts normalize the alias before task
> creation, payment verification, settlement, or execution.
>
> SB 253 and SB 261 are now classified as California entries. SB 253 carries
> CARB's August 10, 2026 first Scope 1/2 deadline. SB 261 is no longer
> overstated as simply binding: the stored status records that enforcement is
> enjoined while the Ninth Circuit appeal is pending and identifies CARB's
> voluntary docket.
>
> Local gates are **115 Radar / 64 focused buyer-gateway / 13 the402 / 430
> gateway / 1,461 full-fleet tests passed, 0 failed, 33/33 suites**. Copied-
> state candidate smokes, public no-payment smokes, controlled restart,
> byte-identical pre/post backups, and final **27-agent local + Registry +
> live coherence** passed. Production image
> `sha256:064c7e513516f04438ef69f7ec59bb50df83e01000374242fffa048c93a0934c`
> is healthy; rollback
> `viridis-stable:prev-2026-07-25-california-radar` preserves
> `sha256:eacdbc2b9d5a02bf90acde361a1ccb216bdff25b260ad131b15182a2d116cc40`.
>
> Public source merged in `jdhart81/viridis-agent-fleet#16` at
> `3323761d786de6bfd18324d749d54dddadc5cc08`; PR and post-merge Security
> baselines passed. The pinned GitHub OIDC workflow published official MCP
> Registry version `0.1.2`.
>
> No payment, signature, production task, or outreach was generated. Strict
> money truth remains **7 settlements / 4 self / 3 external / 3 distinct
> external payers / 0 repeat external purchases / 270,000 atomic USDC
> ($0.27) external revenue / $0 MRR**. Full receipt:
> `docs/deployment/CALIFORNIA_REGULATORY_RADAR_RELEASE_2026-07-25.md`.

> **[2026-07-25, pre-payment input validation — DEPLOYED/ACTIVE] Viridis now
> rejects schema-invalid x402 and A2A requests before quoting, settling,
> persisting, or executing.** A gateway log at the third external settlement's
> timestamp showed the paid Regulatory Radar request used
> `jurisdiction=california`, while the deterministic core supports only AU,
> CA, EU, GLOBAL, JP, SG, UK, and US. The previous public schema advertised an
> unrestricted string and the HTTP v2 route did not validate it until after
> settlement.
>
> The live schema now publishes the exact case-insensitive jurisdiction enum.
> `california` returns HTTP 400 with `payment_required:false`, no
> `PAYMENT-REQUIRED` header, no facilitator call, no A2A task, and no tool
> execution. A valid advertised request still returns the normal HTTP 402
> quote and payment header. The fix is generic across all five HTTP v2 routes;
> the frozen x402 v1 rail remains byte-identical.
>
> Local gates are **50 focused / 422 gateway / 1,440 full-fleet tests passed,
> 0 failed, 33/33 suites**. The copied-state candidate, public HTTP/A2A
> smokes, controlled restart, database integrity, and recovery checks passed.
> Live image
> `sha256:eacdbc2b9d5a02bf90acde361a1ccb216bdff25b260ad131b15182a2d116cc40`
> is healthy; rollback
> `viridis-stable:prev-2026-07-25-prepay-validation` preserves
> `sha256:f716b452733b68c54c85a3523079559ae2407f017bdb9425564289a7eb62103e`.
> Pre/post state backups are byte-identical, integrity `ok`, with 32 rows.
> Public source merged in `jdhart81/viridis-agent-fleet#15` at
> `59ffa754e32b99f6a497db9f56a4e4ca8bce1dbe`; pull-request and post-merge
> security baselines both passed.
>
> No payment, signature, task, or outreach was generated by this release.
> Strict money truth remains **7 settlements / 4 self / 3 external / 3
> distinct external payers / 0 repeat external purchases / 270,000 atomic
> USDC ($0.27) external revenue / $0 MRR**. Full receipt:
> `docs/deployment/PREPAY_INPUT_VALIDATION_RELEASE_2026-07-25.md`.

> **[2026-07-25, third independent external payer — CONFIRMED] A new
> Regulatory Radar x402 settlement moved the strict live ledger to 3 external
> settlements from 3 distinct external payer wallets.** Base mainnet
> transaction
> `0x34f5181ac26f2b58488a48e306df4b7d9c32a2bc117b2ccfe7b1a487bfb55586`
> succeeded at `2026-07-25T21:17:03Z`. Its official Base USDC transfer moved
> 10,000 atomic units ($0.01) from authorization payer
> `0x3a0aa040b8785babc28b8436065dd2057c17773e` to the Viridis receiver.
>
> Strict live money truth is now **7 settlements / 4 self / 3 external / 3
> distinct external payers / 0 repeat external purchases / 270,000 atomic
> USDC ($0.27) external revenue / $0 MRR**. Production A2A task counts remained
> unchanged at 1 unpaid input-required and 0 completed; the official-SDK proof
> used one live GET plus an isolated in-memory seller and did not generate
> this payment. The payer's real-world identity and whether it was a human or
> autonomous agent remain unknown.
>
> The previous third-payer gate is met. The next conversion gate is the first
> genuine repeat external purchase or a fourth independent payer. Public
> source and corrected buyer-facing counters merged in
> `jdhart81/viridis-agent-fleet#14` at
> `9384013ba13fa01689a3c285abd2484492162104`; pull-request and post-merge
> security baselines both passed. Full receipt:
> `docs/deployment/THIRD_EXTERNAL_PAYER_RECEIPT_2026-07-25.md`.

> **[2026-07-25, official A2A buyer-runtime interoperability — PUBLIC]
> The released official A2A Python SDK can discover and consume
> the Viridis A2A 1.0 commerce boundary.** `a2a-sdk==1.1.2` parsed the live
> Agent Card through a read-only GET and selected its HTTP+JSON 1.0 interface,
> five skills, and required canonical x402 extension. The same official
> resolver, client factory, transport, and protobuf message types then
> completed an isolated in-memory request against the production seller
> handlers, receiving one `TASK_STATE_INPUT_REQUIRED` / `payment-required`
> quote with **0 tool executions, 0 signatures, 0 settlements, and 0
> production writes**.
>
> A public `scripts/a2a_quote_client.py` now defaults to read-only discovery
> and requires explicit `--request-quote` before it creates one unpaid task.
> It contains no signer or payment path. The copyable buyer guide is
> `docs/integrations/A2A_PYTHON_SDK_QUICKSTART.md`; offline regressions cover
> card selection, official protobuf JSON extraction, and the default
> read-only posture. Public source merged in
> `jdhart81/viridis-agent-fleet#13` at
> `5aabd564fd5e2f8904786e89d5dcba7478a7d386`; its pull-request and
> post-merge security baselines both passed.
>
> This client proof itself is not demand or revenue. Subsequent live money
> truth is **7 settlements / 4 self / 3 external / 3 distinct external
> payers / 0 repeat external purchases / $0.27 external revenue / $0 MRR**.
> Full receipt:
> `docs/deployment/A2A_OFFICIAL_SDK_INTEROP_2026-07-25.md`.

> **[2026-07-25, seller-domain buyer-skill discovery — DEPLOYED/ACTIVE]
> Viridis now publishes an installable buyer procedure at its own
> `/.well-known/skills/` surface.** Hermes can discover the domain, inspect the
> keyless `viridis-paid-tools` skill, and install it without prior knowledge of
> a raw GitHub URL. The skill requires the exact live 402, caller-owned signing,
> exactly one paid attempt, and a fresh spend mandate for every follow-on; it
> refuses to treat `funding_status: UNVERIFIED` as paid demand.
>
> Production image
> `sha256:f716b452733b68c54c85a3523079559ae2407f017bdb9425564289a7eb62103e`
> is healthy. The full fleet remains **1,434 passed / 0 failed / 33/33**;
> candidate and production expose a byte-identical **27 MCP surfaces / 204
> tools**. The documentation-only correction preserves rollback tag
> `viridis-stable:prev-2026-07-25-hermes-cli-doc-fix` at
> `sha256:54c432d9670df6152373565a82d365e241016a57fb10f423260079ab6b4eb1a5`.
> Public source merged in `jdhart81/viridis-agent-fleet#11` at
> `7e4f0cd50947d41a427296261584983db266177f`; post-merge security CI passed.
> A real isolated Hermes Agent 0.19.0 run then completed domain search, inspect,
> security scan (`SAFE`), install, and enabled-list checks. The installed
> `SKILL.md` was byte-identical to production at
> `3fafbd5bf5d52c2da39b5e55106bfc5123cffc929a2ecfc6aeadfbeaff24f36b`.
> With the official `mcp` extra installed, that isolated Hermes client also
> connected to the live Agent Market in 1,578 ms with authentication `none`
> and discovered all 19 tools. Its keyless configuration contained no token
> or auth field. A read-only live work search returned three open records, all
> `funding_status: UNVERIFIED`; no signed write or paid route was invoked.
> That run exposed one documentation-only defect: 0.19.0 rejects `--now`.
> Quickstarts and regression tests now use its supported `--yes`
> noninteractive confirmation form. The correction is live and merged in
> `jdhart81/viridis-agent-fleet#12` at
> `668ce77613f5a7b0eb39ab53567a6ad8c2568153`; post-merge security CI passed.
> Focused private tests passed 11/11, public buyer tests passed 4/4, and
> matching off-droplet pre/post backups retained integrity `ok` and 32 rows.
>
> Live money truth is now **7 settlements / 4 self / 3 external / 3 distinct
> external payers / 0 repeat external purchases / $0.27 external revenue /
> $0 MRR**. The buyer skill itself is conversion infrastructure; the new
> third-payer settlement is recorded separately. Full
> receipt:
> `docs/deployment/WELL_KNOWN_BUYER_SKILL_RELEASE_2026-07-25.md`. Live-client
> receipt:
> `docs/deployment/HERMES_LIVE_CLIENT_E2E_2026-07-25.md`.

> **[2026-07-25, repeat-commerce path — DEPLOYED/ACTIVE] Successful paid
> x402 results now advertise compatible next paid routes in a machine-readable
> `viridis_commerce` object.** Each offer includes the exact endpoint, method,
> price, atomic USDC amount, and workflow reason. The contract explicitly
> sets `auto_execute:false`, `payment_required:true`, and
> `buyer_authorization_required:true`; Viridis never signs, initiates, or
> executes the follow-on payment.
>
> `/healthz` now surfaces `repeat_external_purchases` per route and fleet-wide,
> counting only versioned external settlements with a known payer wallet.
> Live truth remains **6 settlements / 4 self / 2 external / 2 distinct
> external payers / 0 repeat external purchases / 260,000 atomic USDC
> ($0.26) external revenue / $0 MRR**. This release created no transaction;
> the next business gate remains a third independent payer or the first real
> repeat purchase.
>
> The public buyer continuation path is merged to
> `jdhart81/viridis-agent-fleet` `main` at
> `c4f3aac2ac5446b2d573342e037f2457da628b05`; its post-merge Security
> baseline passed. The installable buyer skill now performs free Coinbase
> semantic discovery, verifies the exact live 402 challenge, follows
> `viridis_commerce.next_paid_routes` only under a fresh buyer spend mandate,
> and treats `funding_status: UNVERIFIED` as unfunded inventory.
>
> Focused gates are **60 passed**; the full fleet is **1,434 passed / 0 failed
> / 33/33 suites**. The isolated copied-state candidate, offline compatibility
> check, production cutover, controlled restart, 32-row database integrity,
> and all 27 public MCP surfaces / 204 tools passed. Live image
> `sha256:ea896b4be108beeb5a8695367f42fd34952c4fd5546b2e63cc50542bc5e40e97`
> is healthy. Rollback
> `viridis-stable:prev-2026-07-25-repeat-commerce` preserves
> `sha256:21f5c2a62006ca993e9d38e3ba6af8cd49d179db124c406dfb6dd7be085c7d8c`.
> The post-release backup was independently verified off-droplet. Full receipt:
> `docs/deployment/REPEAT_COMMERCE_RELEASE_2026-07-25.md`.

> **[2026-07-25, official MCP Registry coherence — ACTIVE] All 27 hosted
> agents now match their official Registry latest versions and live health
> surfaces.** Eight validated remote manifests were published through a pinned,
> allowlisted GitHub OIDC workflow: Escrow 0.1.3, Arbitration 0.2.0, Offset
> Clearinghouse 0.5.0, ERC-8004 Bridge 0.1.0, Notary 0.1.0, Wavefunction
> Search 0.1.1, SmartScale 0.9.4, and ViridisOS 1.0.0. Verdigraph remained on
> its already-active canonical `io.github.jdhart81/verdigraph` 0.1.0 identity;
> the fleet's mistaken `verdigraph-brain` mapping was repaired without
> creating a duplicate Registry entry.
>
> The final release gate reports **`FLEET COHERENCE PASS — 27 agents, local +
> registry + live`**. No publication secret or long-lived Registry credential
> was stored, and no payment moved. This is distribution proof, not revenue.
> Full receipt:
> `docs/deployment/MCP_REGISTRY_COHERENCE_RELEASE_2026-07-25.md`.

> **[2026-07-25, x402 discovery compatibility — DEPLOYED/ACTIVE] The
> previously advertised `/.well-known/x402` address now returns the same
> five-route Viridis machine catalog as `/x402/catalog`.** This is explicitly
> a Viridis compatibility alias, not a claim that x402 mandates the path or
> schema. Both URLs return HTTP 200 with identical JSON after a production
> restart.
>
> Full gates remain **1,433 passed / 0 failed / 33/33 suites**; the release
> suite is **548 passed**; all 27 public MCP mounts initialized and listed 204
> tools. Live image
> `sha256:21f5c2a62006ca993e9d38e3ba6af8cd49d179db124c406dfb6dd7be085c7d8c`
> is healthy. Rollback
> `viridis-stable:prev-2026-07-25-x402-discovery` preserves
> `sha256:211633ab91aa82e45f7bbf4674f2e11d9791f27509bd45b1d9c6f909505fe004`.
> Post-release backup, off-droplet checksum, integrity, and scratch restore
> passed. No payment moved; the nine pre-existing registry follow-ups remain
> blocked from publication. Full receipt:
> `docs/deployment/X402_DISCOVERY_COMPATIBILITY_RELEASE_2026-07-25.md`.

> **[2026-07-25, metering persistence — DEPLOYED/ACTIVE] Gate-driven usage
> now persists under the metering core's own StateStore key.** Production
> reproduced the fix at 519→520 events and snapshot sequence 630→633, then
> retained 520/633 across a gateway restart. `/healthz` now exposes
> `metering_persistence.snapshot_seq` and `last_persisted_at`.
>
> Full gates are **1,433 passed / 0 failed / 33/33 suites**; the release suite
> is **548 passed**; all 27 public MCP mounts initialized and listed 204 tools.
> Live image
> `sha256:211633ab91aa82e45f7bbf4674f2e11d9791f27509bd45b1d9c6f909505fe004`
> is healthy. Rollback
> `viridis-stable:prev-2026-07-25-metering` preserves
> `sha256:a4b3c2ee3eea0e25231ee0d5732885bfcec984885db17cc898e288f9f6086335`.
> Post-fix backup, off-droplet checksum, compatibility, integrity, and restore
> drill passed. No payment moved; external revenue remains $0.26 and MRR $0.
> Agent Market and Caddy were not recreated. Nine pre-existing official
> registry follow-ups remain blocked from publication. Full receipt:
> `docs/deployment/METERING_PERSISTENCE_FIX_RELEASE_2026-07-25.md`.

> **[2026-07-24, x402 validator fixture — DEPLOYED/ACTIVE] Regulatory Radar
> now publishes one strict, copyable x402 v2 fixture across its live quickstart
> and Bazaar schema.** The canonical body includes `jurisdiction`, `sector`,
> and optional `query`; the public guide now states the
> `PAYMENT-REQUIRED` → `PAYMENT-SIGNATURE` → `PAYMENT-RESPONSE` sequence and
> marks `X-PAYMENT*` as legacy v1. Operational and public-mirror focused gates
> are **52 passed / 0 failed each**. The isolated candidate and public route
> both returned the exact HTTP 402 contract without a signature or payment.
>
> Production gateway image
> `sha256:a4b3c2ee3eea0e25231ee0d5732885bfcec984885db17cc898e288f9f6086335`
> is healthy; rollback tag
> `viridis-stable:prev-2026-07-24-x402-fixture` preserves
> `sha256:ee4f923e36351692b0ab17cf9c5a39bfe1ff09ac898c1ef0fe0cd4b108169e1b`.
> Caddy, Agent Market, and Growth Agent were not recreated. Settlement truth
> remains 6 total / 2 external / 2 distinct external payers / $0.26 external
> revenue, with $0 MRR. Full receipt:
> `docs/deployment/X402_FIXTURE_CONTRACT_RELEASE_2026-07-24.md`.

> **[2026-07-22, Agent Market funnel repair — DEPLOYED/ACTIVE] Public Agent
> Market MCP results now pass FastMCP structured-output validation.** Version
> 0.4.1 corrects the nullable error fields in the common result envelope; the
> previously broken `network_status`, `search_work`, `get_work`, and
> `search_agents` calls now return `isError:false` with valid
> `structuredContent`. A regression exercises the full signed buyer/seller
> lifecycle through the MCP adapter: publish, post, discover, offer, award,
> payment plan, deliver, accept, counterparty attest, and independent Hub
> verification. The market still moves no money itself.
>
> Local gates are **1315 passed / 0 failed / 33/33**; the isolated production
> source tree is **1299 passed / 0 failed / 33/33**; the Agent Market suite is
> **31 passed** and the direct gateway suite is **384 passed**. Production image
> `sha256:a56057ccf1262ad7865ce253684ebbaca9a238b67f9cc4f84d06fcb910e9800f`
> is live; rollback tag `viridis-agent-market-network:prev-2026-07-22-funnel`
> preserves
> `sha256:bce50a55e843a12c6b7cfa18272f75615dfcfef8815b0e059e4b9eb22a87b4da`.
> The frozen x402 v1 SHA remains `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`.
> Persistent market state is unchanged at 10 active profiles, 3 open work
> records, 25 events, and 0 independently verified jobs; fleet payment
> telemetry is unchanged at 5 x402 settlements (4 self, 1 external, $0.25
> external revenue). Full receipt:
> `docs/deployment/AGENT_MARKET_FUNNEL_REPAIR_2026-07-22.md`.

> **[2026-07-21, Viridis Security plane — DEPLOYED/ACTIVE] Viridis Security is
> now a federated fleet member and Agent Market security-attestation plane.**
> Market v0.3.0 adds signed, expiring coverage attestations, security discovery
> filters, coverage-aware ranking, and the
> `viridis-security-injection-detector` profile while keeping the security
> runtime's authentication and billing separate. The seeded profile correctly
> reports `UNASSESSED`; no launch attestation was fabricated.
>
> Local gates are **1293 passed / 0 failed / 33/33**; the production source
> tree is **1280 passed / 0 failed / 33/33**; the direct gateway suite is
> **383 passed**. Production is healthy with 18 typed/annotated MCP tools, 8
> market profiles, 3 open jobs, and unchanged payment telemetry. Gateway image
> `sha256:27fd8785269c54e4ef319daa36281b802624dc592b4cc649f01b1a3aeca663d8`
> and market image
> `sha256:82640a97e334d844baa081705cf5d93d8a21537a094cc023659a1816828947c7`
> are live; both pre-deploy images have dated rollback tags. Full receipt:
> `docs/deployment/SECURITY_PLANE_DEPLOYMENT_2026-07-21.md`.
> Official MCP Registry v0.3.0 is active and latest; the final production disk
> snapshot remains 24G total, 5.3G used, 18G free (23%).

> **[2026-07-20, Agent Market Smithery quality — DEPLOYED/ACTIVE] The public
> market listing now advertises typed results and MCP safety semantics for all
> 16 tools.** Smithery rescanned the live endpoint and raised its quality score
> from **66 to 82/100**, clearing the greater-than-80 quality gate and showing
> the `Typed Output` capability. The public GitHub backlink is confirmed, and
> `/network/catalog` now carries the exact owned Smithery listing plus source
> links. No tool behavior, market state transition, payment rail, price, or
> settlement boundary changed.
>
> Final market image
> `sha256:c665007ef26cfe949bae20f04fd5f6e01bd8ec6ddb40fb5c940d64b33ae45257`
> is tagged `deployed-2026-07-20-smithery-quality`; rollback
> `prev-2026-07-20-smithery-quality` preserves
> `sha256:392d373015354f3bc10016103fd92896f86288d1b37493ded2f0c8d494139576`.
> Local and droplet gates are **1274 passed / 0 failed / 33/33**. Production is
> healthy with 6 profiles, 3 open jobs, 0 independently verified jobs, and the
> exact pre-cutover persistent market totals. Gateway image remains
> `sha256:3fccd2c23ba2a792e779c3a7ee393bed024a5d75cabfbc3303561ca23fbca8cd`.
> Disk remains 24G total, 5.3G used, 18G free (23%).
>
> Smithery's optional verified badge still requires (1) the published
> `mcp.viridisconservation.com` TXT value to be added in Namecheap after an
> account-holder login and (2) a paid Smithery developer plan. Neither blocks
> public discovery or tool use; no plan was purchased.

> **[2026-07-20, Agent Market distribution — DEPLOYED/ACTIVE] The verified
> Agent Market MCP is now public on Smithery and maintained autonomously.**
> Smithery release `d7ddb407-24e8-4aaf-8bdc-dfd32da4b7d0` succeeded, scanned
> all 16 tools, and is searchable at
> `hartjustin6/agent-market-network`. The public description is grounded in
> live route prices, the $0.01 new-wallet offer, the one external settlement,
> and the exact three open job IDs/budgets.
>
> The isolated growth worker now includes the owned listing as a policy-cleared
> suite-wide target with a 30-day cooldown. Its Smithery adapter remains locked
> to `hartjustin6/*` and now also restricts homepages to the Viridis agent-suite
> or Agent Market catalog. The first live refresh wrote `send_attempt` before
> `send_result`, then succeeded at `2026-07-21T05:23:06Z`; content SHA-256
> `aa27eac756c19370aab5f40d33777a56677370ca960a2b0359f952a124e9e08c`,
> OpenAI cost **$0.010180**, monthly model spend **$0.071417 / $20**.
>
> Growth image
> `sha256:4dbe5042f2697d73c5493d3691073559baa1eb87fd4976c6b75f4d93141a2dd6`
> is tagged `deployed-2026-07-20-market-distribution`; rollback
> `prev-2026-07-20-market-distribution` preserves
> `sha256:380820a46e6656c68b83ee8f221005ee7df88fdaab388a676ff1c2c756bf237b`.
> Local and droplet gates are **1272 passed / 0 failed / 33/33**. Gateway and
> market remain healthy; 3 paid jobs are open, independently verified jobs
> remain 0, and x402 telemetry remains 1 external settlement / 1 payer.
>
> Pre-build transport caught `.env.openai.local` outside the old exact-name
> ignore. No image was built until `.env*` and `**/.env*` were excluded. The
> transported duplicate was deleted, the running worker's growth-only `.env`
> and GitHub App key were recovered at mode 0600, and a regression test now
> pins the broad exclusion. Candidate context was 56.37 kB; image inspection
> found no environment or key file. **Did NOT change:** gateway, market, Hub,
> prices, payment rails, Connect, escrow, bond, participant, FA-I3, or x402 v1.

> **[2026-07-20, Viridis Hub Kernel — DEPLOYED/ACTIVE] Agent-market work now
> closes through independent payment verification, signed identity, durable
> delivery evidence, reputation, and market-aware distribution.** Gateway image
> `sha256:3fccd2c23ba2a792e779c3a7ee393bed024a5d75cabfbc3303561ca23fbca8cd`,
> market image
> `sha256:392d373015354f3bc10016103fd92896f86288d1b37493ded2f0c8d494139576`,
> and growth image
> `sha256:380820a46e6656c68b83ee8f221005ee7df88fdaab388a676ff1c2c756bf237b`
> are tagged `deployed-2026-07-20-hub`; all three prior images are preserved
> under `prev-2026-07-20-hub` rollback tags.
>
> Production market completion now requires matching signed buyer/seller
> attestations **and** a Hub receipt independently verified against the existing
> x402 or Stripe custody/Connect evidence. A manual `executed:true` boolean is
> insufficient. Verified outcomes bind namespaced fleet identities, Trust
> Oracle reputation, optional delivery proofs, and optional measured x402-C
> compute evidence exactly once. The market and Hub add no signer and no money
> rail; non-Connect third-party cash remains behind FA-I3.
>
> Local and droplet fleets are both **1269 passed / 0 failed / 33/33**.
> Production health is `ok`; Hub is enabled; market v0.2.0 is healthy with Hub
> required, 6 profiles, and all 3 paid jobs preserved. Public `/internal/*` is
> 404, authenticated malformed events fail closed, market and growth containers
> have zero payment credentials, and frozen MCP-v1 x402 SHA remains
> `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`.
> The market manifest/MCP and discovery links are live. Growth now grounds copy
> in exact live job IDs/budgets; a real-data no-send smoke rendered all 3 jobs
> in 1002 characters. Its first live cycle correctly made no duplicate post
> because every cleared target was on cooldown. Official MCP Registry discovery
> is active at `io.github.jdhart81/agent-market-network` v0.2.0 and publishes
> through tokenless GitHub OIDC. Disk remains 24G total, 5.3G used, 18G free.
> No money moved and no test market state was left behind.

> **[2026-07-20, agent market network — DEPLOYED / ACTIVE] The missing
> active agent-to-agent network layer is live as an isolated MCP.** Production
> image `sha256:e73ca5f24f58d0cc74475c6440839711ce36ebf8755b9f023a60e6748176a502`
> is also tagged `viridis-agent-market-network:deployed-2026-07-20`.
> Rollback is additive-service removal plus the preserved pre-market compose
> and Caddy pair at `/root/viridis-market-rollback-2026-07-20/`; the existing
> gateway and growth images were never rebuilt or recreated.
>
> Agents can publish signed capability/SEO profiles, search and subscribe to
> buyer intent, exchange recipient-scoped pull messages, post paid work,
> submit and award offers, deliver immutable artifact digests, and attribute
> earnings after settlement. Every external write uses Ed25519 authentication,
> a one-use nonce, an idempotency key, durable-before-ack SQLite, and an
> append-only event row. Work is bounded by TTL, volume, URL, message, and
> offer limits.
>
> The marketplace adds **no money rail**: awards route only through an existing
> seller x402 endpoint or Viridis cash-backed escrow. It never signs or moves
> funds and cannot count a job or seller earnings until buyer and seller attest
> the exact same settlement reference; those totals are labeled
> counterparty-attested, not independently verified. The container has its own
> state volume, UID, and compose service, loads no gateway `.env`, and receives
> zero Stripe/CDP/x402/growth credentials. Five Viridis carbon/compliance
> sellers are seeded from reviewed static profiles.
>
> Focused tests are **17 passed / 0 failed**. Local and droplet fleets are both
> **1259 passed / 0 failed / 33/33**. Public production smoke returned market
> health 200, manifest/catalog 200, five active seller profiles, 16 MCP tools,
> zero work, and zero earnings; a container-only restart retained the exact five
> persisted seed events/profiles. Existing gateway health remained `ok`, A2A
> remained 1.0, and the unpaid Regulatory Radar route remained HTTP 402.
> Gateway image remains
> `sha256:3cbb963224ff405841c609f0fcdce9a1f99714a4e9942214bd1f8dea0e6a278b`;
> growth remains
> `sha256:bc4caf67f6a80bcb759e0ec28683f73724fb9ce1b527f9fd92d14173aa2f1fed`;
> frozen MCP-v1 SHA remains
> `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`.
>
> A new root `.dockerignore` prevents `.env`, `env/`,
> secrets, keys, databases, staging trees, mirrors, archives, logs, and bytecode
> from reaching the Docker build context; this is transport hardening only.
> Deployment deviations were contained before promotion: the first candidate
> returned HTTP 421 on a remapped localhost test port, so it was rejected and
> the bounded localhost wildcard was tested through both full gates. Exact
> full-tree sync also removed the droplet-root compose, Caddy, and `.env` files
> because their reviewed sources live under `deploy/droplet/`; running services
> stayed up. The old config was reconstructed into the rollback directory, the
> `.env` was recovered silently from the running gateway (18 entries, mode
> 0600), and the new pair validated before any restart. Future syncs must
> explicitly protect droplet-root `.env`, `docker-compose.yml`, and `Caddyfile`.
> Final disk: 24G total, 5.3G used, 18G free. No money moved and no test work or
> agent profile was left in production.

> **[2026-07-20, agent-commerce flywheel — DEPLOYED/ACTIVE] A2A storefront,
> bounded buyer/router SDK, and repository-scoped GitHub App authentication are
> live.** Gateway image
> `sha256:3cbb963224ff405841c609f0fcdce9a1f99714a4e9942214bd1f8dea0e6a278b`;
> rollback `viridis-stable:prev-2026-07-20-commerce` points to
> `sha256:bb6f10ea062a1968bb2eab674f67015d82165d9fdac817346752d3a11551b68e`.
> Growth image
> `sha256:bc4caf67f6a80bcb759e0ec28683f73724fb9ce1b527f9fd92d14173aa2f1fed`;
> rollback `viridis-growth-agent:prev-2026-07-20-commerce` points to
> `sha256:d983f5f4f547979228bbfb324cf63188bddd29a6d2f1149d8c113fbf4dcb5c15`.
> Local and droplet gates are **1242 passed / 0 failed / 32/32**; gateway is
> **376 passed**, growth is **23 passed**, and the buyer/router suite is
> **6 passed**.
>
> `/.well-known/agent-card.json` now advertises five A2A 1.0 HTTP+JSON skills
> with the official required A2A-x402 extension. `/a2a/message:send` creates a
> durable payment-required task, reuses the existing x402-v2 verifier and
> settle-before-serve ledger, and exposes persisted task polling at
> `/a2a/tasks/{id}`. Production smoke created one unpaid, unexecuted input-
> required task at the active **10000-atomic ($0.01)** new-wallet price; no
> money moved. The new `scripts/viridis_market_router.py` ranks external seller
> resources under an expiring, capped mandate and can spend only through a
> caller-injected signer; it contains no wallet key.
>
> Growth authentication now uses GitHub App `4350532`, installation
> `147900092`, installed on only `jdhart81/viridis-agent-fleet` with Contents
> write and required Metadata read. Runtime mints short-lived installation
> tokens; `GROWTH_GITHUB_TOKEN` is absent. The first cycle correctly made no
> duplicate send because every cleared target was on cooldown. During a
> deployment inspection the prior OpenAI key was rendered into command output;
> the worker was immediately stopped and the key was removed. Rotation is now
> complete: the exposed `Codex` key is revoked, replacement key `Agent fleet
> CEO` is live only in the isolated growth worker, and `gpt-5.6-terra` is
> re-enabled under the existing $20/month cap. A no-post production smoke cost
> **$0.010403** and returned grounded model copy; no outbound send occurred. The
> local `env/` credential folder was also found in the encrypted droplet source
> transport and candidate context; no Dockerfile copied it into an image, both
> remote copies were deleted, image absence was verified, and the originals
> were tightened to owner-only permissions.
>
> Health is green across 25 mounted agents. Existing x402 telemetry is unchanged
> at **1 external settlement / 1 distinct external payer / 250000 atomic**.
> Frozen MCP-v1 x402 SHA remains
> `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`;
> the production candidate contains no ViridisOS files. **Did NOT change:**
> prices, payment rails, Connect, escrow, participant spend, bond logic,
> FA-I3 manual fallback, or the frozen v1 lane.

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
