# Fleet Release Gate

No candidate image is deployed, tagged as `latest`, or published to a registry
unless every required item below has contemporaneous evidence. A failed item is
a release block, not a warning.

## Local candidate

```bash
python3 run_fleet_tests.py
python3 -m pytest deploy/gateway deploy/droplet fleet_utils -q
python3 deploy/check_version_coherence.py --local-only
python3 deploy/gateway/check_snapshot_compatibility.py \
  --db /path/to/offline-production-backup.db
```

The snapshot path must be a verified copy, never the live database. The
coherence check covers every `agent.yaml`, core `describe()`/`health()`, both
publish manifest trees, generated tool names/counts, per-agent read policy, and
the canonical `mcp.viridisconservation.com` domain.

## Backup and recovery

Before any paid-service release:

- latest online SQLite backup and manifest are less than 25 hours old;
- SHA-256 and SQLite integrity checks pass;
- the backup and manifest have been copied to a verified off-droplet target;
- the candidate code passes snapshot compatibility against that copy;
- a scratch restore drill has completed in the last 30 days;
- measured restore time is recorded; and
- seven daily copies are retained.

Pilot objective: RPO 24 hours. RTO is the latest measured full scratch restore
time; never substitute an unmeasured promise.

## Candidate image and rollback

Record immutable digests, not mutable tags:

```text
candidate_image:
candidate_repo_digest:
candidate_image_id:
previous_repo_digest:
production_state_backup_sha256:
offsite_destination:
snapshot_compatibility_result:
restore_drill_started_at:
restore_drill_finished_at:
measured_rto:
coherence_result:
full_test_result:
operator:
```

Verify the running container digest equals `candidate_repo_digest`. Retain the
previous digest as the rollback target. Rollback must not overwrite or discard
the SQLite volume.

## Post-deploy

Run public `/healthz`, directory, and MCP `initialize` + `tools/list` checks for
every expected mount. Re-run the registry/live coherence check:

```bash
python3 deploy/check_version_coherence.py
```

Any degraded mount, version mismatch, missing listing, stale tool manifest, or
wrong domain means the release is incomplete and registry publication stops.
