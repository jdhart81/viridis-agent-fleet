# Deployment Guide

## Prototype verification

1. Bundle the exact `robustness_engine` package under `vendor/` and the matching
   schemas under `schemas/`.
2. Run the agent tests and the authoritative fleet runner.
3. Build the container and verify `/health`, `/describe`, one valid evaluation,
   one structural `HOLD`, and the request-size rejection.

## Final promotion gate

Do not set `ROBUSTNESS_SERVICE_RELEASE_MODE=final` until
`RELEASE_MANIFEST.json` is generated from the reconciled v1.0 package and
contains:

- state `FINAL_LEAN_PROVEN_FLEET_DEPLOYED`;
- the exact engine version;
- formal state `ARISTOTLE_AUDITED_VERIFIED_ZERO_SORRY`;
- paper PDF and package-manifest hashes; theorem, audit, and formal-receipt
  hashes; engine-receipt, canon-candidate, service-source, and rollback-plan
  hashes;
- `paper_reconciled=true`, `canon_candidate_reconciled=true`, and
  `production_deployed=true`; and
- the deployed OCI digest.

Mount that final manifest read-only outside the image, set
`ROBUSTNESS_RELEASE_MANIFEST_PATH` to its path, and set
`ROBUSTNESS_DEPLOYED_ARTIFACT_DIGEST` to the running `sha256:...` OCI digest.
This avoids a self-referential image hash. Final health fails closed when the
manifest is missing, inconsistent, or names a different running artifact.

## Rollback

Retain the previously verified image digest and release manifest. Roll back by
redeploying that exact digest, then verify its health and a known canonical
evaluation receipt. Never rebuild an old tag and call it the same artifact.
