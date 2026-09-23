# Gateway State Backup and Restore Gate

SmartScale cannot accept an external paid customer until the shared gateway
state database has a current off-droplet backup and one performed restore
drill. SQLite WAL and `synchronous=FULL` protect committed writes; they do not
protect against droplet or volume loss.

This procedure covers the shared database because SmartScale billing,
idempotency, prepaid credits, and other fleet entitlement state live together
in `/data/viridis_state.db`.

## Required evidence

- backup and manifest created less than 25 hours ago;
- SHA-256 and SQLite `integrity_check` pass;
- the backup exists outside the DigitalOcean droplet;
- a restore into a new scratch path succeeds;
- the restored database contains the expected agent-state rows;
- the production database is never overwritten during a drill.

## Create the online backup

Run from the deployment directory on the droplet:

```bash
docker compose exec -T gateway \
  python3 deploy/gateway/gateway_state_backup.py backup \
  --source /data/viridis_state.db \
  --destination-dir /data/backups \
  --retain-days 7
```

The command prints the exact backup path, manifest path, SHA-256, integrity
result, row count, and agent names.

## Copy it off the droplet

Copy both the `.db` and `.manifest.json` files to a destination that is not on
the droplet. Examples are a restricted DigitalOcean Spaces bucket or an
operator-controlled backup machine.

Do not mark the launch gate complete because a file exists under
`/data/backups`; that directory is still on the same Docker volume.

Record:

```text
backup_created_at:
backup_sha256:
offsite_destination:
offsite_copy_verified_at:
operator:
```

Never place API keys, SSH private keys, or storage credentials in this
repository. Supply them through the operator environment or the destination's
credential helper.

## Restore drill

The restore target must be a new path:

```bash
docker compose exec -T gateway \
  python3 deploy/gateway/gateway_state_backup.py restore-drill \
  --backup /data/backups/<backup>.db \
  --manifest /data/backups/<backup>.manifest.json \
  --scratch /data/restore-drills/<backup>.db
```

The utility refuses to overwrite an existing file. A successful result must
show:

```json
{
  "status": "ok",
  "integrity_check": "ok",
  "agent_state_rows": 1
}
```

The actual row count can be greater than one.

After the file-level drill, boot a scratch gateway against the restored path
and run the existing marker-state probe:

```bash
STATE_DB=/data/restore-drills/<backup>.db \
python3 deploy/gateway/persistence_probe.py verify \
  --escrow-id <known-marker-escrow-id> \
  --base http://127.0.0.1:<scratch-port>
```

Production stays untouched throughout the drill.

## Nightly schedule

Schedule the backup command once per night, then perform the off-droplet copy.
Alert or fail the paid-service readiness check if:

- the latest manifest is 25 hours old or older;
- integrity or SHA verification fails;
- the off-droplet copy is absent; or
- the last recorded restore drill is older than 30 days.

Keep seven daily backups for the pilot. The declared pilot objectives are
RPO 24 hours and a restore-drill RTO that is measured and recorded rather than
promised in advance.
