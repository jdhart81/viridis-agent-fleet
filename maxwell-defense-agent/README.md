# Maxwell Defense fleet service

Maxwell gives the endpoint operator an asymmetric computational cost advantage:
callers selected for challenges search for a nonce; the defender checks one
candidate hash, authenticates a small token and atomically consumes its ID.
That is not a measurement of joules, proof of good intent, or an availability
guarantee. SHA-256 solvers can be accelerated with specialized hardware.

## What is implemented

- **Paid rehearsal:** fixed $1 through existing fleet x402 and MCP
  payment gates. Four bounded workload inputs produce a policy model, 8,192-hash
  local microbenchmark and concrete deployment acceptance checks.
- **Reference enforcement:** ASGI middleware binds each proof to tenant,
  server-verified caller identity, HTTP method, raw path/query and exact body.
  Missing proofs get a 429 challenge; invalid proofs get 403. The downstream
  service still checks authorization and payment after valid work.
- **Replay protection:** atomic SQLite consumption survives restart and works
  across processes sharing the same local database. No state for unsolved
  challenges. Live consumed entries are never evicted to make room.
- **Resource bounds:** request/token/nonce limits, short expiry, capped client
  solver, per-process admission bucket and capped replay store. Saturation and
  database failure refuse admission.

This is a new `maxwell-sha256-v1` protocol. The older hosted implementation in
the Security workspace labels its SHA-256 proxy `argon2id-pow`, keeps challenge
state in memory, and does not bind verification to the protected request.
We do not copy that protocol or its hardcoded amplification/energy claims.
We do not claim that the screenshot's public SDK was audited in this task.

## Local rehearsal

From this directory, with the candidate enabled only for this process:

```sh
MAXWELL_FLEET_ENABLED=1 python3 examples/rehearse.py
```

No network calls or payments occur. Output labels the local run as unpaid.
For the paid gateway candidate, the proposed route is
`POST /x402/maxwell-defense/rehearse_defense`; the MCP tool is
`/maxwell-defense/mcp` → `rehearse_defense`. Both require the existing gateway
and `MAXWELL_FLEET_ENABLED=1` at process startup. The HTTP route is excluded
from introductory discounts. Execution has no anonymous free quota.

Inputs:

```json
{
  "client_hashes_per_second": 100000,
  "client_p95_budget_ms": 250,
  "backend_cost_ms": 2000,
  "peak_requests_per_second": 100
}
```

Client throughput and backend cost are buyer declarations, not observations.
The report chooses the highest supported difficulty inside a geometric-model
p95 client budget and the reference solver's maximum attempt count. A budget
too small returns `CLIENT_BUDGET_TOO_LOW`. No report activates enforcement.
The hash benchmark excludes full request verification and must not be used as
a full verifier latency or cost figure.

## Reference enforcement integration

Import `Guard`, `binding`, and `solve` from `src.defense` and
`MaxwellMiddleware` from `src.middleware` in an isolated application package.
The framework's generic `src` package layout follows fleet adapters; vendor or
package this directory under a unique application namespace before distribution.

```python
guard = Guard(secret_bytes, "/data/maxwell-replay.sqlite3", bits=12)
app = MaxwellMiddleware(
    existing_app,
    guard=guard,
    tenant="operator-owned-tenant-id",
    paths=["/expensive-operation"],
    identity=authenticate_and_check_quota,
)
```

`authenticate_and_check_quota(scope)` is an async server-owned callback. It
returns a stable authenticated subject only after checking credentials and
quotas, otherwise `None`. Do not implement it by trusting a caller's identity,
payment, risk or `X-Trusted` declaration. The reference middleware challenges
every admitted subject on the explicitly selected paths. Adaptive risk-based
selection and entitlement bypass are not implemented; add only from trusted
server-side signals with abuse/latency evidence.

Client flow: save exact original request bytes; read the 429 `maxwell`
challenge; explicitly call `solve` within the policy's `client_max_attempts`
and `client_max_seconds`; retry the same request with `X-Maxwell-Token` and
`X-Maxwell-Nonce`. On budget exhaustion, stop. A proof does not authorize or
pay for the backend call. Do not automatically retry a consumed proof after a
backend error; use downstream operation/payment idempotency and reconcile.

Each tenant must have an operator-generated secret of at least 32 random bytes.
Secrets stay at the enforcing endpoint, never in a report or client. Key rotation
invalidates outstanding tokens. Do not delete or reset replay state while its
key's outstanding proofs remain valid. Use a persistent local volume and a
reliable clock. Cross-host replicas need a shared atomic replay store before
deployment; SQLite on independent hosts does not provide that property.

Upstream must cap connections, header sizes, aggregate request rates and body
read time. The middleware's per-process bucket is not a volumetric DDoS defense.
Its URL binding allows at most 256 raw path/query bytes including the separator.
Restrict to explicit expensive routes; do not challenge discovery, payments,
webhooks, health checks or arbitrary existing clients without compatibility work.

## Commercial and release status

The $1 paid rehearsal is live on the fleet as of September 13, 2026, with
startup and restart verification. There are 29 healthy native gateway agents
and 11 paid routes. No customer purchase, buyer usefulness or savings is
established by this release. The prior Security subscription runtime stays
halted. `MAXWELL_FLEET_ENABLED` exposes only the paid rehearsal; it never mounts
the guard. Adaptive and managed protection remain planned work.

See [release receipt](../docs/deployment/MAXWELL_FLEET_RELEASE_2026-09-13.md)
and [product plan](../docs/products/MAXWELL_DEFENSE_FLEET_2026-09-13.md).
