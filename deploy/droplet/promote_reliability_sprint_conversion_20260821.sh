#!/bin/sh
# State-safe promotion for the outcome-first Reliability Sprint overlay.

set -eu

EXPECTED_AUTH='authorize production promotion: reliability sprint conversion 20260821'
PREVIOUS_IMAGE='sha256:ff7a2a21dc15d7d25bdaabd3e6607afb38594d5e04a9c36f2602fadd957524c0'
CANDIDATE_IMAGE='sha256:b807814738ff4aafb42a0c0cd461f90e802cb360d9d34fb26a75b208fc4921d6'
CANDIDATE_TAG='viridis-stable:reliability-sprint-conversion-20260821-candidate'
ROLLBACK_TAG='viridis-stable:rollback-reliability-sprint-conversion-20260821'
LATEST_TAG='viridis-stable:latest'
LIVE_CONTAINER='viridis-fleet-gateway-1'
COMPOSE_DIR='/root/viridis-fleet/deploy/droplet'
ENV_FILE='/root/viridis-fleet/.env'
EVIDENCE_DIR='/root/viridis-candidates/reliability-sprint-conversion-20260821'
BACKUP="$EVIDENCE_DIR/viridis_state-20260821T051501Z.db"
BACKUP_MANIFEST="$EVIDENCE_DIR/viridis_state-20260821T051501Z.manifest.json"
BACKUP_TOOL="$EVIDENCE_DIR/build-context/deploy/droplet/gateway_state_backup.py"
VERIFY_TOOL="$EVIDENCE_DIR/verify_candidate.py"
EXPECTED_BACKUP_SHA='3f96958490a065e1539c3804b6d8c8848128fa4778fd5f4a1e0db36b47532aef'
EXPECTED_MANIFEST_SHA='ac9554e080870a1f9944b42d25aaf0086a5626660796b7d9af034d75cbe17b83'
EXPECTED_VERIFY_SHA='d65ab391c1d5b9cbda3da9967c9c36b9077a5c1f6d10cd9d8f85ac0a8bdbfc00'
EXPECTED_BASE_GATEWAY_SHA='c0230bec95df7d74d2bd0e32db44dd7bee3f396f737c949254ec9c9e5dcc0d4f'
EXPECTED_BASE_LLMS_SHA='97b4af2017193593d606305045b8b75efd0986a511d49e70a2e7ad59aa33c0d4'
EXPECTED_OLD_AGENTS_SHA='a4556f32d4f714901feaced9a3c3c81ba165861f9f2482a8884acccbdb673dd4'
EXPECTED_NEW_AGENTS_SHA='f73a2bd34d92762b1fbc067749b66aa365c1659dbf1a9c03ab91e8167fca1332'
EXPECTED_OFFER_SHA='cae039de4b81acff9bbf62e374c2437aa3e36427992094ab87f8c42d6dac1ce1'
EXPECTED_OVERLAY_SHA='90d6a7fe0cf3440e09dd65726b6b7eab1d1fcc4ad959d7f3c8f9d3f3d4a35c04'
EXPECTED_DECISION_SHA='9026733e1165844cc15489c2348a0103d306dbae58597ad6d91ac6495de31bc4'

if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]; then
  echo 'refusing: exact production-promotion authorization required' >&2
  exit 64
fi

RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
RUN_DIR="$EVIDENCE_DIR/promotion-runs/$RUN_ID"
mkdir -p "$RUN_DIR"

compose_gateway() {
  docker compose \
    --project-directory "$COMPOSE_DIR" \
    --file "$COMPOSE_DIR/docker-compose.yml" \
    --project-name viridis-fleet \
    --env-file "$ENV_FILE" \
    up -d --no-deps --force-recreate gateway
}

wait_healthy() {
  expected_image=$1
  attempts=0
  while [ "$attempts" -lt 45 ]; do
    running_image=$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER" 2>/dev/null || true)
    health=$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER" 2>/dev/null || true)
    if [ "$running_image" = "$expected_image" ] && [ "$health" = healthy ]; then
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 2
  done
  echo 'gateway did not reach the exact healthy image in 90 seconds' >&2
  return 1
}

verify_state() {
  output=$1
  docker exec "$LIVE_CONTAINER" python3 \
    /fleet/deploy/gateway/gateway_state_backup.py verify \
    --backup /data/viridis_state.db > "$output"
  python3 -c '
import json, sys
item = json.load(open(sys.argv[1]))
assert item["status"] == "ok"
assert item["integrity_check"] == "ok"
assert item["agent_state_rows"] == 35
' "$output"
}

record_runtime() {
  suffix=$1
  docker inspect --format \
    'image={{.Image}} config_image={{.Config.Image}} health={{.State.Health.Status}} state={{.State.Status}} restart_count={{.RestartCount}} mounts={{range .Mounts}}{{.Destination}}:{{.RW}};{{end}}' \
    "$LIVE_CONTAINER" > "$RUN_DIR/runtime-$suffix.txt"
}

public_probe_candidate() {
  suffix=$1
  python3 "$VERIFY_TOOL" https://mcp.viridisconservation.com \
    > "$RUN_DIR/public-$suffix.json"
}

public_probe_previous() {
  suffix=$1
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS https://mcp.viridisconservation.com/healthz \
    > "$RUN_DIR/health-$suffix.json"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS https://mcp.viridisconservation.com/agents \
    > "$RUN_DIR/agents-$suffix.html"
  python3 -c '
import json, sys
item = json.load(open(sys.argv[1]))
assert item["status"] == "ok"
assert len(item["agents"]) == 28
assert all(v.get("status") == "ok" for v in item["agents"].values())
' "$RUN_DIR/health-$suffix.json"
  [ "$(sha256sum "$RUN_DIR/agents-$suffix.html" | awk '{print $1}')" = "$EXPECTED_OLD_AGENTS_SHA" ]
}

rollback_required=0
rollback() {
  trap - EXIT INT TERM
  echo 'promotion failed; restoring the pinned previous image' >&2
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG" || return 1
  compose_gateway || return 1
  wait_healthy "$PREVIOUS_IMAGE" || return 1
  verify_state "$RUN_DIR/state-rollback.json" || return 1
  public_probe_previous rollback || return 1
  record_runtime rollback || return 1
  echo 'Reliability Sprint conversion rollback verified' >&2
}

on_exit() {
  status=$1
  trap - EXIT INT TERM
  if [ "$status" -ne 0 ] && [ "$rollback_required" -eq 1 ]; then
    if ! rollback; then
      echo 'CRITICAL: automatic gateway rollback did not verify' >&2
      exit 70
    fi
  fi
  exit "$status"
}
trap 'on_exit $?' EXIT
trap 'exit 130' INT TERM

# Prove all immutable preconditions before the first production tag move.
[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" = "$PREVIOUS_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$PREVIOUS_IMAGE" ]
[ "$(docker image inspect --format '{{.Id}}' "$CANDIDATE_TAG")" = "$CANDIDATE_IMAGE" ]
[ -z "$(docker ps -q --filter ancestor="$CANDIDATE_IMAGE")" ]
[ "$(sha256sum "$BACKUP" | awk '{print $1}')" = "$EXPECTED_BACKUP_SHA" ]
[ "$(sha256sum "$BACKUP_MANIFEST" | awk '{print $1}')" = "$EXPECTED_MANIFEST_SHA" ]
[ "$(sha256sum "$VERIFY_TOOL" | awk '{print $1}')" = "$EXPECTED_VERIFY_SHA" ]
python3 "$BACKUP_TOOL" verify --backup "$BACKUP" \
  --manifest "$BACKUP_MANIFEST" > "$RUN_DIR/offline-backup-before.json"
verify_state "$RUN_DIR/state-before.json"
record_runtime before

docker exec "$LIVE_CONTAINER" sha256sum \
  /fleet/deploy/gateway/viridis_mcp_gateway.py \
  /fleet/deploy/gateway/llms.txt \
  /fleet/deploy/gateway/agents.html > "$RUN_DIR/live-source-before.sha256"
[ "$(awk '$2=="/fleet/deploy/gateway/viridis_mcp_gateway.py"{print $1}' "$RUN_DIR/live-source-before.sha256")" = "$EXPECTED_BASE_GATEWAY_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/llms.txt"{print $1}' "$RUN_DIR/live-source-before.sha256")" = "$EXPECTED_BASE_LLMS_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/agents.html"{print $1}' "$RUN_DIR/live-source-before.sha256")" = "$EXPECTED_OLD_AGENTS_SHA" ]

docker run --rm --network none --read-only --entrypoint sha256sum \
  "$CANDIDATE_IMAGE" \
  /fleet/deploy/gateway/viridis_mcp_gateway.py \
  /fleet/deploy/gateway/llms.txt \
  /fleet/deploy/gateway/agents.html \
  /fleet/deploy/gateway/reliability_sprint.html \
  /fleet/deploy/gateway/reliability_sprint_overlay.py \
  /fleet/deploy/gateway/value_decision.py > "$RUN_DIR/candidate-source-before.sha256"
[ "$(awk '$2=="/fleet/deploy/gateway/viridis_mcp_gateway.py"{print $1}' "$RUN_DIR/candidate-source-before.sha256")" = "$EXPECTED_BASE_GATEWAY_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/llms.txt"{print $1}' "$RUN_DIR/candidate-source-before.sha256")" = "$EXPECTED_BASE_LLMS_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/agents.html"{print $1}' "$RUN_DIR/candidate-source-before.sha256")" = "$EXPECTED_NEW_AGENTS_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/reliability_sprint.html"{print $1}' "$RUN_DIR/candidate-source-before.sha256")" = "$EXPECTED_OFFER_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/reliability_sprint_overlay.py"{print $1}' "$RUN_DIR/candidate-source-before.sha256")" = "$EXPECTED_OVERLAY_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/value_decision.py"{print $1}' "$RUN_DIR/candidate-source-before.sha256")" = "$EXPECTED_DECISION_SHA" ]

docker tag "$PREVIOUS_IMAGE" "$ROLLBACK_TAG"
[ "$(docker image inspect --format '{{.Id}}' "$ROLLBACK_TAG")" = "$PREVIOUS_IMAGE" ]

docker tag "$CANDIDATE_IMAGE" "$LATEST_TAG"
rollback_required=1
compose_gateway
wait_healthy "$CANDIDATE_IMAGE"
public_probe_candidate first-boot
verify_state "$RUN_DIR/state-first-boot.json"
record_runtime first-boot

docker restart "$LIVE_CONTAINER" > "$RUN_DIR/restart-container-id.txt"
wait_healthy "$CANDIDATE_IMAGE"
public_probe_candidate restart
verify_state "$RUN_DIR/state-restart.json"
record_runtime restart

[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" = "$CANDIDATE_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$CANDIDATE_IMAGE" ]
sha256sum "$RUN_DIR"/* > "$RUN_DIR/evidence.sha256"

rollback_required=0
trap - EXIT INT TERM
echo "production promotion verified: Reliability Sprint conversion ($RUN_ID)"
