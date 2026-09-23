# Robustness Engine Agent rollback plan

The service is stateless and non-actuating. It has no database volume, no
payment path, no secret, and no authority to execute a decision.

Before promotion, record the currently running container identity and preserve
the candidate image by immutable digest. Deploy the candidate under a distinct
container and service name; do not replace the gateway or its persistent
volumes.

Rollback is verified by stopping the candidate container, confirming the
existing gateway and agent-market services remain healthy, then starting the
same candidate again from its retained immutable image digest and re-running
`/health`, `/describe`, and the canonical cyber-identity evaluation. A rollback
must never rebuild an old mutable tag and call it the same artifact.

If final health, the canonical record hash, or the non-execution boundary does
not match, stop the robustness container and retain its logs and mounted release
manifest for diagnosis. No other fleet service or persistent volume is to be
changed as part of this rollback.
