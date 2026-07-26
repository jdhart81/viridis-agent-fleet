# Returning Buyer Exact-Quote Release — 2026-07-26

## Outcome

Returning x402 buyers can now construct the first unpaid preflight correctly
from the machine-readable continuation contract. Eligible repeat and
cross-route offers explicitly say:

- which header carries the payer hint;
- that its value comes from the caller's public signing address;
- whether the route requires that hint for an exact first quote; and
- that the hint does not authorize payment.

This removes an avoidable corrective 402 for returning wallets. It does not
change any price, introductory-pricing eligibility rule, settlement behavior,
payment ceiling, or private-key boundary.

The fixed-price Hive route correctly advertises that a payer hint is not
required for an exact quote. Intro-eligible deterministic routes advertise
that it is required.

## Buyer safety

The public buyer skill, Hermes guide, and first-call quickstart tell buyers to
send only their public signing address in `X402-Payer-Address`. A private key
must never be sent in that header, a prompt, a tool argument, or a log. The
live unpaid 402 remains the only authoritative payment requirement, and every
repeat purchase still requires a fresh mandate and fresh signature.

## Verification

| Gate | Result |
|---|---|
| Focused HTTP x402, A2A, activation, and Hermes tests | 90 passed |
| Canonical isolated fleet | 1,571 passed, 0 failed, 34/34 suites |

No paid request was made for this release candidate.
