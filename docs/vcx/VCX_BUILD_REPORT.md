# VCX v0.1 — local build report

Justin, the Compute Exchange MVP runs locally as a bounded extension of Agent Market Network. Three signed simulated sellers and two buyers discover capacity, buy verified work, settle once, and reinvest proceeds within owner policy. Every financial amount remains nonredeemable simulation bookkeeping. Actual revenue, live charges and payouts are zero.

## Independent review update, 2026-11-11

An independent review reproduced the original results, then found that a buyer could take verified work without paying (cancel after delivery, self-granted dispute refund, or letting the lease lapse) and that one abandoned reservation blocked a listing indefinitely. Those and nine further findings are fixed in this checkout as invariants R1 to R9 in [VCX_INVARIANTS.md](VCX_INVARIANTS.md), each with a regression test.

| Item | Result after fixes |
|---|---|
| VCX tests | 125 passed (99 original, 2 updated to the new rules, 26 added) |
| Agent Market suite including VCX | 181 passed, 1 existing skip |
| Demo reconciliation | Unchanged: 900 + 372 + 28 = 1,300, held 0 |
| Boundary guard, discovery-index check, compileall | Passed |
| Existing tracked files changed | One: `agent-market-network-agent/src/core.py`, three additive public methods for extension authentication |
| Review runtime | Python 3.10.12 on Linux; the broader Fleet run was not repeated there |

In v0.1 the exchange process executes the provider and verifies by recomputing the same function. The seller performs no computation. The build demonstrates lifecycle, authorization and accounting, not purchased or independently verified computation. Statements below that predate the review are superseded where they conflict with R1 to R9; in particular the policy is no longer immutable, a dispute no longer refunds on the buyer's request, and the signed action name now includes the exchange identifier.

## Review and run

- Branch: `codex/vcx-v01-20261110` (local staged changes, no commit/push/merge).
- Checkout: `/Users/justinhart/Desktop/Cowork /Agents to deploy  copy/_workspaces/vcx-build-20261110`.
- [Installation, commands and signed API example](README.md).
- [Demo evidence](evidence/VCX_DEMO_RESULT.json).
- [Machine-readable test results](evidence/VCX_TEST_RESULTS.json).

From the checkout root, with the documented dependencies installed:

```bash
python3 agent-market-network-agent/vcx/demo.py --output /tmp/VCX_DEMO_RESULT.json
```

## Existing components reused

Existing Market Network signed profiles, Ed25519 canonical authorization and current security evidence supply identity and eligibility. The provider allowlist invokes the existing QuantityTakeoffCore through a fixed local adapter. ORC supplies canonical, hash-bound delivery receipts; existing caller-owned signing helpers optionally authenticate their issuer. Existing marketplace schemas, paid rails, service credits and production APIs are unchanged.

The hosted payment, custody, Connect, exact-funded execution and durable delivery mechanisms were inspected for future integration. They are not imported, copied, invoked or modified by VCX. The older in-memory exchange prototype remains untouched.

## Implemented components

The `vcx` package adds immutable expiring capacity listings, transparent configurable matching, expiring quotes, atomic capacity/budget holds, signed authorization, fenced execution leases, deterministic acceptance, ORC receipts, disputes/hold refunds, restart recovery, reassignment, a double-entry capital ledger and bounded reinvestment. A local stdio MCP adapter exposes 17 operations. Account seeding, policy provisioning and simulated payment notices remain trusted server-only APIs.

SQLite IMMEDIATE transactions commit job state, journal changes, nonce consumption and canonical idempotency results together. Pending execution terms are bound before leaving RUNNING; a crash cannot repurpose an idempotency key for another job. Read transactions provide consistent financial reports. No persistence failure falls back to volatile spending authority.

## Demonstration

| Step | Result |
|---|---|
| Participants | 3 signed sellers, 2 signed buyers, 4 listings |
| First purchase | 200 simulated minor units; selected provider wins on disclosed score rather than lowest price |
| Fee and proceeds | 10 fee; 190 pending seller earnings |
| Bounded reinvestment | 150 moved to spendable simulation budget, within an 80% owner cap |
| Earnings-funded purchase | Seller purchases another job for 100; fee 5 |
| Existing Fleet service | 20 ft × 30 ft × 4 in concrete slab yields 7.407 yd³; price 250, rounded fee 13 |
| Failure demonstrations | Cancellation and expired authorization release 200 held units |
| Final accounting | Available 900 + pending 372 + fees 28 = initial simulated funding 1,300; held 0 |
| Real financial activity | 0 charges, 0 payouts, 0 actual revenue |

## Verification

| Suite/check | Result |
|---|---|
| New VCX tests | 99 passed: exchange 41, identity 14, ledger 19, providers 20, MCP/demo surface 5 |
| Existing Marketplace regression | 56 passed, 1 existing skip |
| Existing ORC regression | 15 passed |
| Final targeted total | 170 passed, 1 existing skip |
| Broader Fleet run | 1,611 passed, 18 failed, 5 skipped; 32 of 34 agent suites clean |
| Baseline comparison | The same 18 failures reproduce in an untouched archive of the base source |
| Boundary/index/compilation | Public boundary guard, discovery-index check, compileall and staged whitespace checks passed |
| Stdio integration | MCP initialize, list 17 tools, list 4 capacity listings passed |

The broader run preceded the last additional VCX tests: its market line is 144 passes, while the final market rerun is 155 passes and 1 skip. These overlapping suite totals must not be added together. Independent review also ran 20 cancellation/dispute versus settlement races across separate SQLite connections; each conserved funds and admitted exactly one outcome.

The 18 baseline failures comprise 17 settlement-engine tests relying on Python 3.14 `get_event_loop()` without a current loop, plus an eco-funding HTTP test whose loopback listener is denied by the sandbox. They are unrelated to VCX changes and remain unresolved. No checks were suppressed or converted to passes.

Automated coverage includes successful verification/settlement, insufficient budgets and protected reserves, request/payment duplicates and conflicts, concurrent reservations/settlements, seller timeout and reassignment, cancellation and late-worker fencing, verification failure, disputed hold refunds, restart recovery, listing/profile expiry, current security evidence, unsupported execution, credential canaries, atomic rollback, conservation, optional receipt signatures and reinvestment limits.

## Security and payment findings

Buyer/seller credentials are never accepted by the provider schemas. Only bounded deterministic test and reviewed Fleet takeoff functions execute; there is no arbitrary-code, provider-URL, shell or remote model route. Signed profiles prove control of a public key; they do not establish independently verified legal identity. Seller reliability and energy estimates are explicitly declared simulation data, separate from observed local outcomes; energy is not claimed as measured.

All budget, pending earnings, fee, refund and receipt fields distinguish simulation from actual settled funds and service credits. The default fee is 500 basis points, rounded upward in integer minor units. Ledger reinvestment cannot exceed owner policy, spend cap, exposure or reserve constraints.

Technical Stripe Connect onboarding/transfers already exist in the hosted service. A later internal research note describes existing automated Connect use while retaining a marketplace-structure counsel review. VCX-specific seller eligibility, provider rights, agreements, exact funds flow, dispute responsibilities, sandbox evidence and operational readiness are not established by this local build. Existing payment credentials and rails were left unchanged.

## Source and publication blockers

The local release snapshot is commit `4a4e109750ac6c7a226d229c5a7fdc1b7336e7ee`. Its tree `f3c2f4183d42c5435e8321ddad0bffcc1b62583c` exactly equals retrieved Fleet main `eb9e05d60c10bfc89ef7cef898d9ea54176885b5`. The available bundle lacks historical ancestor `234d69c36cee40565e64c2dd359418ca0f6b6af5`; complete upstream ancestry must be fetched before a PR or publication. Shell network DNS was restricted; the sandbox's Keychain auth failure is inconclusive, and no login/token replacement was attempted.

Hosted service main `20df076dfaf898138071783923070ba83fbe7fe2` and its current payment/persistence interfaces were inspected read-only. Its OSS pin is `6b91b666c1686be03cba691b6d7956bcd32c1641`; no service pin or production configuration changed. This work is not deployed or published and performs no live financial transactions.

## Next three actions

1. Review this local handoff and recover complete upstream history in a network/Keychain-capable session; handle the two pre-existing Fleet test/environment issues separately.
2. Prepare a narrowly scoped Stripe sandbox bridge using existing custody/Connect and exact-funded delivery interfaces, with immutable receipts and failure/cancellation/duplicate evidence.
3. Resolve VCX seller rights, onboarding, funds-flow and marketplace review requirements, then seek explicit approval for any paid pilot or deployment. Keep owner spending opt-in and all live financial actions separately authorized.

## Exact files added

No pre-existing tracked source file was changed. The following new files comprise the implementation, tests, documentation and evidence:

- `agent-market-network-agent/adapters/vcx_mcp_server.py`
- `agent-market-network-agent/tests/test_vcx_exchange.py`
- `agent-market-network-agent/tests/test_vcx_identity.py`
- `agent-market-network-agent/tests/test_vcx_ledger.py`
- `agent-market-network-agent/tests/test_vcx_providers.py`
- `agent-market-network-agent/tests/test_vcx_review_fixes.py` (added by the review)
- `agent-market-network-agent/tests/test_vcx_surface.py`
- `agent-market-network-agent/vcx/__init__.py`
- `agent-market-network-agent/vcx/demo.py`
- `agent-market-network-agent/vcx/exchange.py`
- `agent-market-network-agent/vcx/identity.py`
- `agent-market-network-agent/vcx/ledger.py`
- `agent-market-network-agent/vcx/providers.py`
- `docs/vcx/README.md`
- `docs/vcx/VCX_ARCHITECTURE.md`
- `docs/vcx/VCX_BUILD_REPORT.md`
- `docs/vcx/VCX_ECONOMICS.md`
- `docs/vcx/VCX_INVARIANTS.md`
- `docs/vcx/VCX_RESEARCH.md`
- `docs/vcx/VCX_ROADMAP.md`
- `docs/vcx/evidence/BASELINE_ECO_FUNDING_TESTS.txt`
- `docs/vcx/evidence/BASELINE_SETTLEMENT_TESTS.txt`
- `docs/vcx/evidence/FLEET_TESTS.txt`
- `docs/vcx/evidence/MARKET_TESTS.txt`
- `docs/vcx/evidence/ORC_TESTS.txt`
- `docs/vcx/evidence/VCX_DEMO_RESULT.json`
- `docs/vcx/evidence/VCX_TEST_RESULTS.json`
