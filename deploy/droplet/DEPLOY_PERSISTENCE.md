# Deploy: persistence build + genesis receipts — one session on the droplet

> **CURRENT SAFETY OVERRIDE (2026-07-26): NEVER build the gateway image on
> the 1 GB production droplet.** An in-place Docker build exhausted host
> availability and required a control-plane power cycle. Build
> `--platform linux/amd64` on an off-host BuildKit worker, export and checksum
> the image, transfer it, then use `docker load` on production. The droplet may
> load and run a resource-limited copied-state candidate; it must not compile
> or build the image. See
> `docs/deployment/HIVE_COST_COVERAGE_RELEASE_2026-07-25.md`.

> Ships the StateStore build (PS1–PS8), proves state survives restart in
> production, then executes the fleet's first self-transaction with
> publishable receipts. ~15 minutes. All commands run on the droplet
> (`ssh root@192.34.62.16`, key `justinhart-mbp-deploy`).

## 0. What changed (this build)

- `deploy/gateway/state_store.py` — NEW: SQLite write-through persistence, invariants PS1–PS8, 11 tests
- `deploy/gateway/viridis_mcp_gateway.py` — restores state at boot, wraps process() durable-before-ack, `/healthz` now reports (and degrades on) persistence status
- `deploy/gateway/persistence_probe.py` — NEW: mark/verify/selftest probes
- `deploy/droplet/docker-compose.yml` — `gateway_state:/data` volume + `STATE_DB` env
- All 13 cores version-bumped to match the registry (`deploy/check_version_coherence.py` must pass after deploy)
- `scripts/genesis_receipts.py` — NEW: first self-transaction, 12 invariants, writes GENESIS_RECEIPTS.{md,json}
- Fleet gate: 417 tests, 14/14 clean (13 agents + gateway persistence suite)

## 1. Ship the code (historical procedure; do not build on production)

```bash
cd "/Users/justinhart/Desktop/Cowork /Agents to deploy  copy"
tar czf /tmp/fleet-persist.tgz deploy scripts \
    agent-*-agent smartscale-agent protogen-agent \
    regulatory-radar-agent narrative-engine-agent \
    --exclude='__pycache__' --exclude='*.bak_*'
scp /tmp/fleet-persist.tgz root@192.34.62.16:/root/viridis-fleet/
```

## 2. Build off-host + load + roll

```bash
cd /root/viridis-fleet
docker tag viridis-stable:latest viridis-stable:prev   # rollback point
tar xzf fleet-persist.tgz
# Build linux/amd64 off-host, checksum and transfer the image archive.
# On production, verify the checksum and use:
gzip -dc viridis-stable-amd64.tar.gz | docker load
docker tag viridis-stable:candidate viridis-stable:latest
docker compose up -d --force-recreate gateway    # volume + STATE_DB from compose
sleep 5 && curl -s https://mcp.viridisconservation.com/healthz | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d['status'], d['persistence'])"
# expect: ok {'available': True, 'db_path': '/data/viridis_state.db', 'errors': {}}
```

## 3. Prove the invariant in production

```bash
bash deploy/droplet/verify_restart_persistence.sh
# expect: RESULT: PASS — production state survives restart.
```

## 4. First self-transaction (the launch story)

```bash
docker compose exec -T gateway sh -c \
  "cd /fleet && BASE=http://127.0.0.1:8402 python3 scripts/genesis_receipts.py"
# expect: ALL 12 INVARIANTS PASSED — then copy the two receipt files out:
docker compose cp gateway:/fleet/docs/deployment/GENESIS_RECEIPTS.md .
docker compose cp gateway:/fleet/docs/deployment/GENESIS_RECEIPTS.json .
# commit them to the public repo (jdhart81/viridis-agent-fleet) — they ARE the marketing
```

## 5. Version coherence (should now be green)

```bash
python3 deploy/check_version_coherence.py
# expect: COHERENT — advertised == running for all 13 agents.
```

## Rollback

`docker tag viridis-stable:prev viridis-stable:latest && docker compose up -d --force-recreate gateway`.
State volume is additive-only; the old build simply ignores it.

## Invariant summary being deployed

| ID | Invariant |
|---|---|
| PS1 | state change durable before the caller sees the result (hard-kill safe) |
| PS2 | restore(save(x)) == x, audit chains intact across restarts |
| PS3 | persistence failure never raises into a tool call; healthz degrades loudly |
| PS4 | per-agent namespace isolation |
| PS5 | monotonic snapshot sequence |
| PS6 | config/logger/process rebuilt fresh — code upgrades beat stale snapshots |
| PS7 | read-only actions do zero disk IO |
| PS8 | each agent (de)serializes against its own `src.core` (gateway eviction-safe) |
| E6× | escrow exactly-once settlement holds ACROSS restarts (tested) |
