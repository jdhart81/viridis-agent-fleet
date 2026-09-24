# Maxwell Defense: paid fleet service

Release status: paid rehearsal deployed and restart-verified. Runtime
protection remains a reference component. See the
[release receipt](../deployment/MAXWELL_FLEET_RELEASE_2026-09-13.md).

## Product decision

Sell protection of expensive agent work, with an evidence-led first purchase.
The buyer is an operator of a costly MCP tool, inference service or agent API.
Their job is to preserve useful capacity during automated abuse while keeping
legitimate client delays inside an agreed budget.

The desired advantage is computational asymmetry: fresh work per admitted
challenged request, cheap bounded verification before expensive backend work.
A proof cannot distinguish benevolent intent from a well-funded attacker.
Authentication, authorization, rate limits, resource caps and ordinary edge
protection remain necessary. Do not claim measured thermodynamic advantage
until workload/energy measurements support it.

## Monetization

| Offering | Buyer receives | Price/status |
|---|---|---|
| Defense rehearsal | Policy model, local hash benchmark, scope limits and trial acceptance checks | $1 per result; live on the fleet since September 13, 2026 |
| Integration pilot | Guard installed on one buyer-authorized endpoint, baseline and controlled load comparison, client compatibility results and rollback | Scope and price after a buyer supplies a real endpoint and acceptance criteria; not yet offered automatically |
| Managed protection | Monitored policies, calibrated difficulty, key rotation, shared replay state, quota management and incident reporting | Recurring price to be validated after useful pilot delivery and an independently initiated repeat; not implemented or listed |

The long-term economic product is the managed control service. Local puzzle
checks should stay cheap; do not call a paid remote API or charge the defender
per hostile packet. A future subscription should use a known protected-endpoint
allowance and hard spending cap, with separately agreed capacity changes.

The $1 rehearsal is an entry offer, not evidence that anyone wants recurring
protection. Separate quote, settlement, successful delivery, buyer-confirmed
usefulness, independently initiated repeat and recurring revenue in reporting.
Existing x402 telemetry and buyer-feedback flow remain the commercial record.

## Implementation delivered

New `maxwell-defense-agent` core, MCP adapter and manifest; conditional gateway
mount and x402 registration; $1 fixed price and zero anonymous execution quota;
buyer intent/discovery metadata; Docker inclusion; local ASGI guard and solver;
restart-safe replay checks and adversarial/payment tests. No new payment rail.
The old Security subscription runtime remains excluded from discovery.

The rehearsal is deliberately bounded: no remote endpoint fetch, caller code
execution, background job, hosted credential issuance or remote puzzle solving.
Workload numbers do not increase the fixed 8,192-hash benchmark. It does not
create a public security-attestation receipt or imply formal verification.

The enforcing guard is a reference component, not yet mounted on the fleet.
It rejects cross-tenant, cross-caller, changed-body, changed-URL/method, expired,
tampered and reused proofs. SQLite consumption is atomic across local workers.
Full replay storage, failed storage and admission saturation fail closed.
Rejection is not proof that an attacker was detected.

## Release sequence (steps 1–3 completed for the rehearsal service)

1. Review this candidate and proposed $1 scope. Public release is separate
   from the local implementation; the user authorized and completed that release on September 13.
2. Build the fleet image including the new directory. In an isolated candidate,
   set `MAXWELL_FLEET_ENABLED=1`; inspect MCP tools, unpaid 402 price, discovery
   and state compatibility. An unset flag keeps paid discovery absent.
3. Before publishing or deploying, follow the fleet GitHub Keychain baseline
   and deployment runbook, verify the current production artifact/state, and
   obtain release authorization for the concrete candidate.
4. Start with the paid rehearsal only. Verify a real buyer-authorized paid
   delivery and usefulness before expanding claims. Do not self-purchase to
   simulate demand.
5. For enforcement, obtain an endpoint owner and acceptance criteria. Establish
   baseline latency, completion, backend compute and traffic mix. Measure full
   verification including HMAC/body hashing/replay storage on intended hardware.
6. Run controlled tests on an isolated endpoint: supported client p95 budget,
   legitimate completion, adversarial admission rate, total defender CPU,
   restart/replay/clock/storage failures, concurrency and bandwidth limits.
   Do not label the existing hash microbenchmark a load test.
7. Add trusted selection/adaptive policy and entitlement bypass, shared replay
   storage if multi-host, and operational metrics before a managed offering.
   Do not take risk scores or paid status from unverified request data.
8. Roll out only selected compatible routes with a rollback switch. Turning
   off enforcement restores the existing auth/payment/quotas path; it must not
   bypass those controls. Preserve outstanding-proof replay state on rollback.

## Evidence and claim boundaries

Client puzzles have established precedent; they are not unique proof of the
Viridis thermodynamic thesis. [RFC 8019](https://www.rfc-editor.org/rfc/rfc8019.html)
describes client puzzles in IKEv2 DoS defense, while the
[Tor proof-of-work specification](https://spec.torproject.org/hspow-spec/)
shows a deployment-specific design. Neither certifies this implementation.

The older local hosted `mcp-services/maxwell/src/pow.ts` explicitly calls its
SHA-256 implementation a placeholder for Argon2id and uses in-memory challenge
storage. Its receipt verifier checks account and expiry but not the declared
principal/scope against an actual request. Those observations apply to the
local hosted scaffold, not a completed audit of the screenshot's public SDK.

The candidate uses accurately labelled SHA-256 with modeled geometric solve
work. Hardware acceleration and client performance differences prevent a
universal cost ratio. We have not measured joules, production availability,
real-user friction, attacker economics or buyer value.
