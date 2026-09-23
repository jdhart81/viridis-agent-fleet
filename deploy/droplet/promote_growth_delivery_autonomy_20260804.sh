#!/usr/bin/env bash
# Promote the receipt-gated growth worker and enable one bounded daily action.
set -Eeuo pipefail

EXPECTED_AUTH='authorize growth autonomy: eight-route delivery distribution'
LIVE_CONTAINER='growth-agent-growth-agent-1'
COMPOSE_DIR='/root/viridis-fleet/growth-agent'
ENV_FILE="$COMPOSE_DIR/.env"
CANDIDATE_TAG='viridis-growth-agent:eight-route-delivery-20260804'
CANDIDATE_IMAGE='sha256:f69733b11ddcdc1eff28cb1e5fb4beef4bfa39e7ff17d03f609ffda32996a1ef'
PREVIOUS_IMAGE='sha256:e1e7346fd3a79d1a41533084f02d8da9197b0c0236bede2b68dd2837b4bfa3b9'
LATEST_TAG='viridis-growth-agent:latest'
ROLLBACK_TAG='viridis-growth-agent:rollback-eight-route-delivery-20260804'
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_DIR="/root/viridis-growth-candidate-20260804/promotion-$RUN_ID"
FIRST_CYCLE="$EVIDENCE_DIR/first-cycle.json"
ENV_BACKUP="$EVIDENCE_DIR/growth.env.before"
DB_BACKUP="$EVIDENCE_DIR/viridis_growth.before.db"
DB_TEMP="/state/.viridis_growth.before-$RUN_ID.db"
rollback_required=0

if [[ $# -ne 1 || $1 != "$EXPECTED_AUTH" ]]; then
  echo 'refusing: exact growth-autonomy authorization is required' >&2
  exit 64
fi

compose_growth() {
  docker compose \
    --project-directory "$COMPOSE_DIR" \
    --file "$COMPOSE_DIR/docker-compose.yml" \
    --project-name growth-agent \
    up -d --no-deps --force-recreate growth-agent
}

wait_running() {
  local expected_image=$1
  local attempt image status
  for attempt in $(seq 1 30); do
    image="$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")"
    status="$(docker inspect --format '{{.State.Status}}' "$LIVE_CONTAINER")"
    if [[ $image == "$expected_image" && $status == running ]]; then
      return 0
    fi
    sleep 2
  done
  echo 'growth worker did not reach the expected running image' >&2
  return 1
}

require_runtime() {
  local expected_image=$1
  local expected_dry_run=$2
  [[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" == "$expected_image" ]]
  [[ "$(docker inspect --format '{{.State.Status}}' "$LIVE_CONTAINER")" == running ]]
  [[ "$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$LIVE_CONTAINER")" == unless-stopped ]]
  [[ "$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/state"}}{{.Name}}{{end}}{{end}}' "$LIVE_CONTAINER")" == growth-agent_growth_state ]]
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$LIVE_CONTAINER" \
    | grep -qx 'GROWTH_AGENT_ENABLED=1'
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$LIVE_CONTAINER" \
    | grep -qx "GROWTH_AGENT_DRY_RUN=$expected_dry_run"
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$LIVE_CONTAINER" \
    | grep -qx 'GROWTH_AGENT_INTERVAL_SECONDS=86400'
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$LIVE_CONTAINER" \
    | grep -qx 'GROWTH_OPENAI_ENABLED=0'
  if docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$LIVE_CONTAINER" \
    | grep '^GROWTH_CAMPAIGN=' | grep -qvx 'GROWTH_CAMPAIGN='; then
    return 1
  fi
  if docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$LIVE_CONTAINER" \
    | grep '^GROWTH_CAMPAIGN_AUTHORIZATION=' \
      | grep -qvx 'GROWTH_CAMPAIGN_AUTHORIZATION='; then
    return 1
  fi
}

set_dry_run() {
  local value=$1
  python3 - "$ENV_FILE" "$value" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
value = sys.argv[2]
lines = path.read_text().splitlines()
matches = [i for i, line in enumerate(lines) if line.startswith("GROWTH_AGENT_DRY_RUN=")]
if len(matches) != 1:
    raise SystemExit("expected exactly one GROWTH_AGENT_DRY_RUN entry")
lines[matches[0]] = f"GROWTH_AGENT_DRY_RUN={value}"
path.write_text("\n".join(lines) + "\n")
PY
}

rollback() {
  trap - EXIT INT TERM
  echo 'growth promotion failed; restoring previous image in preview mode' >&2
  cp "$ENV_BACKUP" "$ENV_FILE"
  set_dry_run 1
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG"
  compose_growth
  wait_running "$PREVIOUS_IMAGE"
  require_runtime "$PREVIOUS_IMAGE" 1
  echo 'growth rollback verified; truthful outbound ledger preserved' >&2
}

on_exit() {
  local status=$?
  trap - EXIT INT TERM
  docker exec "$LIVE_CONTAINER" rm -f "$DB_TEMP" >/dev/null 2>&1 || true
  if [[ $status -ne 0 && $rollback_required -eq 1 ]]; then
    if ! rollback; then
      echo 'CRITICAL: automatic growth rollback did not verify' >&2
      exit 70
    fi
  fi
  exit "$status"
}
trap on_exit EXIT
trap 'exit 130' INT TERM

mkdir -p "$EVIDENCE_DIR"
chmod 700 "$EVIDENCE_DIR"

[[ "$(docker image inspect --format '{{.Id}}' "$CANDIDATE_TAG")" == "$CANDIDATE_IMAGE" ]]
[[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" == "$PREVIOUS_IMAGE" ]]
[[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" == "$PREVIOUS_IMAGE" ]]
require_runtime "$PREVIOUS_IMAGE" 1

cp "$ENV_FILE" "$ENV_BACKUP"
chmod 600 "$ENV_BACKUP"
docker tag "$PREVIOUS_IMAGE" "$ROLLBACK_TAG"

docker exec -i "$LIVE_CONTAINER" python3 - "$DB_TEMP" <<'PY'
import sqlite3
import sys

source = sqlite3.connect('/state/viridis_growth.sqlite3')
destination = sqlite3.connect(sys.argv[1])
with destination:
    source.backup(destination)
destination.close()
source.close()
PY
docker cp "$LIVE_CONTAINER:$DB_TEMP" "$DB_BACKUP" >/dev/null
chmod 600 "$DB_BACKUP"
docker exec "$LIVE_CONTAINER" rm -f "$DB_TEMP"

python3 - "$DB_BACKUP" > "$EVIDENCE_DIR/backup-verification.json" <<'PY'
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

path = Path(sys.argv[1])
db = sqlite3.connect(path)
integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
rows, max_seq = db.execute(
    'SELECT COUNT(*), COALESCE(MAX(seq), 0) FROM outbound_log').fetchone()
db.close()
assert integrity == 'ok'
print(json.dumps({
    'integrity': integrity,
    'rows': rows,
    'max_seq': max_seq,
    'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
}, sort_keys=True))
PY

rollback_required=1
set_dry_run 0
docker tag "$CANDIDATE_IMAGE" "$LATEST_TAG"
compose_growth
wait_running "$CANDIDATE_IMAGE"
require_runtime "$CANDIDATE_IMAGE" 0

for attempt in $(seq 1 45); do
  docker logs "$LIVE_CONTAINER" 2>&1 | awk '/^{/ {print; exit}' > "$FIRST_CYCLE.tmp"
  if [[ -s "$FIRST_CYCLE.tmp" ]] && python3 -m json.tool "$FIRST_CYCLE.tmp" >/dev/null; then
    mv "$FIRST_CYCLE.tmp" "$FIRST_CYCLE"
    break
  fi
  sleep 2
done
[[ -s "$FIRST_CYCLE" ]]

python3 - "$FIRST_CYCLE" <<'PY'
import json
import re
import sys

result = json.load(open(sys.argv[1]))
assert result.get('status') == 'sent', result
assert result.get('target') == 'viridis-owned-github', result
assert re.fullmatch(r'[0-9a-f]{64}', str(result.get('content_sha256') or ''))
receipt = result.get('receipt') or {}
assert receipt.get('platform') == 'github_owned_content', result
assert receipt.get('repo') == 'jdhart81/viridis-agent-fleet', result
assert receipt.get('path') == 'docs/LIVE_AGENT_SUITE.md', result
assert re.fullmatch(r'[0-9a-f]{40}', str(receipt.get('commit_sha') or ''))
PY

docker exec -e GROWTH_AGENT_RUN_ONCE=1 -e GROWTH_AGENT_DRY_RUN=1 \
  "$LIVE_CONTAINER" python3 /app/main.py > "$EVIDENCE_DIR/next-cycle-preview.json"
python3 - "$EVIDENCE_DIR/next-cycle-preview.json" <<'PY'
import json
import sys

result = json.load(open(sys.argv[1]))
assert result.get('status') == 'dry_run', result
assert result.get('send_attempted') is False, result
assert 'viridis-paid-delivery-v1' in str(result.get('content') or ''), result
assert str(result.get('content') or '').count('• ') == 8, result
PY

python3 - "$EVIDENCE_DIR" <<'PY'
import json
from pathlib import Path
import sqlite3
import sys

out = Path(sys.argv[1]) / 'post-promotion-ledger.json'
db = sqlite3.connect('/var/lib/docker/volumes/growth-agent_growth_state/_data/viridis_growth.sqlite3')
db.row_factory = sqlite3.Row
integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
rows, max_seq = db.execute(
    'SELECT COUNT(*), COALESCE(MAX(seq), 0) FROM outbound_log').fetchone()
latest = db.execute(
    "SELECT event_type, target_id, occurred_at, payload_json "
    "FROM outbound_log ORDER BY seq DESC LIMIT 1").fetchone()
payload = json.loads(latest['payload_json']) if latest else {}
db.close()
assert integrity == 'ok'
assert latest and latest['event_type'] == 'send_result'
assert latest['target_id'] == 'viridis-owned-github'
assert payload.get('success') is True
out.write_text(json.dumps({
    'integrity': integrity,
    'rows': rows,
    'max_seq': max_seq,
    'latest_event_type': latest['event_type'],
    'latest_target_id': latest['target_id'],
    'latest_occurred_at': latest['occurred_at'],
    'latest_success': payload.get('success'),
}, sort_keys=True) + '\n')
PY

python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen('https://mcp.viridisconservation.com/healthz', timeout=15) as response:
    health = json.load(response)
assert health.get('status') == 'ok'
total = health['payment_gate']['x402']['http_settlement_telemetry']['total']
assert 'external_paid_results_receipted' in total
PY

require_runtime "$CANDIDATE_IMAGE" 0
rollback_required=0
trap - EXIT INT TERM
printf 'growth delivery autonomy verified: %s\n' "$RUN_ID"
