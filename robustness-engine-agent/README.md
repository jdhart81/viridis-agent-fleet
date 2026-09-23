# Viridis Robustness Engine Agent

This service exposes the deterministic robustness kernel through a bounded HTTP
interface. It accepts a complete decision case and outcome bundle, then returns
the same hash-bound record as the reference command-line engine.

The service evaluates only. It cannot execute a selected candidate, call an
external model, move money, mutate a ledger, publish a paper, or create
authority. `HOLD` and `NO_ADMISSIBLE_OPTION` are successful fail-closed kernel
results rather than transport failures.

## Current state

Version 0.6 is bound to the Aristotle-reviewed and independently Viridis-audited
v1 formal package. The returned frozen Lean source is byte-identical to the
submitted source; the 930-job audit passes statement freeze, zero-proof-hole,
forbidden-construct, allowed-axiom, non-vacuity, and significance gates.

Source adoption and an audited paper do not by themselves prove production
deployment. `ROBUSTNESS_SERVICE_RELEASE_MODE=final` remains fail-closed until a
separately mounted `RELEASE_MANIFEST.json` records the exact deployed artifact
digest and every reconciliation field required by final health.

That deployment gate passed on 7 August 2026. The exact AMD64 OCI manifest is
running as an internal-only service on `viridis-fleet_default`; final health,
gateway-to-service reachability, the canonical cyber evaluation, and the
stop/start rollback drill pass. No public route or host port was added. The
production receipt is `PRODUCTION_DEPLOYMENT_RECEIPT.json`. Publication and
public canon admission remain separately held.

## Interfaces

- `GET /health` — runtime and release-gate health
- `GET /describe` — capability and boundary declaration
- `POST /evaluate` — accepts `operation`, `case`, `outcomes`, and optional
  `request_id`

No secret environment variables are used. Request bodies are capped at 2 MiB
by default, including chunked bodies. Final mode also requires an externally
mounted release manifest whose recorded OCI digest matches the running
artifact digest supplied by the deployment control plane.
