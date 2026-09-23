# Signed Cliff Check release review

## Invariants

- CX1: Every dollar figure comes from TaxCreditEngineCore; the hosted tool adds no tax arithmetic.
- CX2: Indeterminate results list every missing fact and never incur a charge.
- CX3: Each allowlisted partner code has at most three durable redemptions; a fourth uses the normal paid path.
- CX4: Every receipt binds `sha256(salt + audit_sha256)` to `commit_hash`, and engine verification of `result` is valid.
- CX5: Delivered and useful commercial-truth counters require the buyer feedback endpoint; internal, test, and self calls never advance them.
- CX6: Delivered report HTML has no script or external CSS or JS.
- CX7: The full fleet, gateway, and droplet test gates stay green.

## Buyer flow

Before: the tax engine exposes deterministic calculations, while the local `build_report.py` produces a signed report without hosted intake, payment, or buyer usefulness confirmation. After: the existing tax MCP mount offers `signed_cliff_check`; `/cliff-check` collects supplied C&I solar facts, displays the self-contained report and JSON receipt, and offers the paid buyer a one-use usefulness receipt. An indeterminate response is free. Determinate calls use the existing payment gate at 14,900 USD cents, a buyer-authorized x402 v2 settlement, or one of three durable redemptions per configured partner code. The page requires a partner code or an externally signed x402 `PAYMENT-SIGNATURE`; it does not itself sign a wallet payment.

## Source and metrics boundaries

The public GitHub `main` is a partial reference tree and omits serving source. This branch includes the local serving source required to run the full fleet gate, excluding runtime state and the named credential locations. The branch gate therefore has a different total test count than the original local tree. Only an external paid transport delivery followed by a valid feedback token is counted as an exact buyer-confirmed delivery. Transport delivery remains visible in the observed field. A buyer feedback token is possession evidence; it is not independent identity proof. Partner, internal, and self reports do not count as external paid results.

## Deployment click list for Justin (not run by this PR)

1. Review the full source sync and companion EnergyAI PR. Merge only through the normal review process, then stage the fleet checkout on the gateway host with its existing state backup and rollback image procedure.
2. In the gateway's private `.env`, set `CLIFF_CHECK_PARTNER_CODES` to comma-separated, nonempty codes intended for no more than three redemptions each. Ensure `X402_ENABLED=1`, `X402_V2_ENABLED=1`, and existing x402 v2 pay-to, network, asset, and facilitator settings are correct. Do not place codes in Git. The existing state volume must persist across restarts.
3. In Stripe Dashboard, inspect the existing Checkout payment flow; a `signed-cliff-check` call must quote USD 149.00 (`amount_cents=14900`). This code uses the existing dynamic Checkout flow and does not require a new Stripe catalog Price. Verify with a test-mode session before any live buyer attempt.
4. In the staged checkout, run `python3 run_fleet_tests.py` and `python3 -m pytest deploy/gateway deploy/droplet`. Create the gateway state backup and pin the current `viridis-stable:latest` image using the established production procedure.
5. In that staged checkout, run `docker build -f deploy/gateway/Dockerfile -t viridis-stable:latest .` then `docker compose -f deploy/droplet/docker-compose.yml up -d gateway`. This is the exact gateway build/cutover command; run it only after the backup and review gates. The compose file reads the private `.env` relative to its own `deploy/droplet` directory.
6. Check `/cliff-check`, `/.well-known/ai-catalog.json`, and `llms.txt`; call `signed_cliff_check` through the tax mount; confirm an indeterminate report is free, a paid quote is exactly $149, the receipt verifies, and a buyer feedback token updates the commercial-truth snapshot once. Then verify the companion EnergyAI link.

## Ambiguities to resolve at release review

- The supplied requirement says the page submits to the tool but does not specify a browser wallet. This implementation displays the x402 quote and accepts a buyer-signed header from an external wallet or agent. A direct browser Stripe Checkout experience would be a separate UI and payment integration.
- The repository does not have one authoritative release manifest. `deploy/droplet/candidate_file_manifest.py`, used for candidate/base file parity, now excludes the two named credential locations by default; `.gitignore` and `.dockerignore` also exclude them.
- The September 2026 live image, private environment values, Stripe configuration, and external buyer identity cannot be verified from this PR. The deploy click list requires operator checks rather than assuming them.
