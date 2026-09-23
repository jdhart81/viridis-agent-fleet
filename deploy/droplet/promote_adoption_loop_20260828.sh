#!/bin/sh
# State-safe production promotion for the one-entry Viridis adoption loop.

set -eu

EXPECTED_AUTH='authorize production promotion: adoption loop 20260828'
BASE_IMAGE='sha256:b807814738ff4aafb42a0c0cd461f90e802cb360d9d34fb26a75b208fc4921d6'
CANDIDATE_TAG='viridis-stable:adoption-loop-20260828-candidate'
ROLLBACK_TAG='viridis-stable:rollback-adoption-loop-20260828'
LATEST_TAG='viridis-stable:latest'
LIVE_CONTAINER='viridis-fleet-gateway-1'
REHEARSAL_CONTAINER='viridis-adoption-loop-rehearsal-20260828'
COMPOSE_DIR='/root/viridis-fleet/deploy/droplet'
SOURCE_DIR='/root/viridis-fleet'
RELEASE_DIR='/root/viridis-candidates/adoption-loop-20260828'
CONTEXT_DIR="$RELEASE_DIR/build-context"
ARTIFACT="$RELEASE_DIR/adoption-files.tgz"
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
RUN_DIR="$RELEASE_DIR/promotion-runs/$RUN_ID"
BACKUP_DIR="$RUN_DIR/backups"
REHEARSAL_DIR="$RUN_DIR/rehearsal-state"

if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]; then
  echo 'refusing: exact production-promotion authorization required' >&2
  exit 64
fi

mkdir -p "$RUN_DIR" "$BACKUP_DIR" "$REHEARSAL_DIR"

compose_gateway() {
  docker compose \
    --project-directory "$COMPOSE_DIR" \
    --file "$COMPOSE_DIR/docker-compose.yml" \
    --project-name viridis-fleet \
    --env-file "$SOURCE_DIR/.env" \
    up -d --no-deps --force-recreate gateway
}

wait_container_healthy() {
  container_name=$1
  expected_image=$2
  attempts=0
  while [ "$attempts" -lt 60 ]; do
    actual_image=$(docker inspect --format '{{.Image}}' "$container_name" 2>/dev/null || true)
    actual_health=$(docker inspect --format '{{.State.Health.Status}}' "$container_name" 2>/dev/null || true)
    if [ "$actual_image" = "$expected_image" ] && [ "$actual_health" = healthy ]; then
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 2
  done
  echo "container did not reach the expected healthy image: $container_name" >&2
  return 1
}

verify_adoption_url() {
  base_url=$1
  suffix=$2
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS "$base_url/.well-known/agent-adoption.json" \
    > "$RUN_DIR/adoption-discovery-$suffix.json"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS -X POST "$base_url/adopt" \
    -H 'content-type: application/json' \
    --data '{"objective":"monitor regulatory changes and compliance deadlines","inputs":{"jurisdiction":"US","topics":["emissions"],"lookback_days":90},"max_price_minor":25}' \
    > "$RUN_DIR/adoption-plan-$suffix.json"
  python3 - "$RUN_DIR/adoption-discovery-$suffix.json" "$RUN_DIR/adoption-plan-$suffix.json" <<'PY'
import json
import sys

discovery = json.load(open(sys.argv[1]))
plan = json.load(open(sys.argv[2]))
assert discovery["spec_version"] == "viridis-adoption-v1"
assert discovery["endpoint"].endswith("/adopt")
assert plan["spec_version"] == "viridis-adoption-v1"
assert plan["decision"] == "READY_FOR_QUOTE"
assert plan["integration"]["route"] == "regulatory-radar/monitor_changes"
assert plan["money_moved"] is False
assert plan["payment_authorized"] is False
assert plan["tool_executed"] is False
PY
}

verify_state() {
  suffix=$1
  docker exec "$LIVE_CONTAINER" python3 \
    /fleet/deploy/gateway/gateway_state_backup.py verify \
    --backup /data/viridis_state.db > "$RUN_DIR/state-$suffix.json"
  python3 - "$RUN_DIR/state-$suffix.json" <<'PY'
import json
import sys

item = json.load(open(sys.argv[1]))
assert item["status"] == "ok"
assert item["integrity_check"] == "ok"
assert item["agent_state_rows"] == 35
PY
}

cleanup_rehearsal() {
  docker rm -f "$REHEARSAL_CONTAINER" >/dev/null 2>&1 || true
}

rollback_required=0
rollback() {
  trap - EXIT INT TERM
  cleanup_rehearsal
  echo 'promotion failed; restoring the pinned production image' >&2
  docker tag "$BASE_IMAGE" "$LATEST_TAG"
  compose_gateway
  wait_container_healthy "$LIVE_CONTAINER" "$BASE_IMAGE"
  verify_state rollback
  echo 'adoption-loop rollback verified' >&2
}

on_exit() {
  status=$1
  trap - EXIT INT TERM
  if [ "$status" -ne 0 ] && [ "$rollback_required" -eq 1 ]; then
    rollback || exit 70
  else
    cleanup_rehearsal
  fi
  exit "$status"
}
trap 'on_exit $?' EXIT
trap 'exit 130' INT TERM

# Immutable preconditions before candidate construction.
[ -f "$ARTIFACT" ]
[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" = "$BASE_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$BASE_IMAGE" ]

python3 "$SOURCE_DIR/deploy/droplet/gateway_state_backup.py" backup \
  --source /var/lib/docker/volumes/viridis-fleet_gateway_state/_data/viridis_state.db \
  --destination-dir "$BACKUP_DIR" > "$RUN_DIR/backup.json"
BACKUP=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["backup"])' "$RUN_DIR/backup.json")
MANIFEST="${BACKUP%.db}.manifest.json"
python3 "$SOURCE_DIR/deploy/droplet/gateway_state_backup.py" restore-drill \
  --backup "$BACKUP" --manifest "$MANIFEST" \
  --scratch "$RUN_DIR/restore-drill.db" > "$RUN_DIR/restore-drill.json"

# Build from the exact running filesystem plus the reviewed adoption overlay.
rm -rf "$CONTEXT_DIR"
mkdir -p "$CONTEXT_DIR"
docker cp "$LIVE_CONTAINER:/fleet/." "$CONTEXT_DIR/"
cp "$SOURCE_DIR/deploy/gateway/Dockerfile" "$CONTEXT_DIR/deploy/gateway/Dockerfile"
mkdir -p "$CONTEXT_DIR/deploy/droplet"
cp "$SOURCE_DIR/deploy/droplet/gateway_state_backup.py" \
  "$CONTEXT_DIR/deploy/droplet/gateway_state_backup.py"
tar -xzf "$ARTIFACT" -C "$CONTEXT_DIR"

cd "$CONTEXT_DIR"
[ "$(sha256sum deploy/gateway/adoption_loop.py | awk '{print $1}')" = '4130840cffdcc25816cc5c848929f3cac7e990fc78a5af405d4f557140db2239' ]
[ "$(sha256sum deploy/gateway/x402_http.py | awk '{print $1}')" = '0d7b32f09861b2d1553bd33ebf9c7f58c6f0d0865ae7ea333418dda57238eb0d' ]
[ "$(sha256sum deploy/gateway/viridis_mcp_gateway.py | awk '{print $1}')" = '1409c577dd377b6127de6900e1e143aa906c626ef2dfd93961d2e8c66647e0e1' ]
[ "$(sha256sum deploy/gateway/a2a_commerce.py | awk '{print $1}')" = '7583e1c640bc553369542a45eac8b759758dec06cec8c752858d4aa3c556f50b' ]
[ "$(sha256sum deploy/gateway/Dockerfile | awk '{print $1}')" = 'dca7370960e7ce4d75264c50275324dc9f9338012c55031f3371aa6248550e6b' ]
[ "$(sha256sum deploy/gateway/llms.txt | awk '{print $1}')" = '9ae9a9f338e6889f177b753208cb7ed6701edde2b540088ede8a56aaf1006ae4' ]
[ "$(sha256sum deploy/gateway/quickstart.html | awk '{print $1}')" = '7c0d85571d177e1fdb9389763e3fb1c89d374c2d74699dd7fd98c5ebce00c0f0' ]

docker build --pull=false -f deploy/gateway/Dockerfile -t "$CANDIDATE_TAG" . \
  > "$RUN_DIR/docker-build.log"
CANDIDATE_IMAGE=$(docker image inspect --format '{{.Id}}' "$CANDIDATE_TAG")
printf '%s\n' "$CANDIDATE_IMAGE" > "$RUN_DIR/candidate-image-id.txt"
docker run --rm --network none --read-only \
  -e PYTHONDONTWRITEBYTECODE=1 --entrypoint python3 "$CANDIDATE_TAG" -c \
  'import sys; sys.path.insert(0, "/fleet/deploy/gateway"); import adoption_loop, x402_http, a2a_commerce, viridis_mcp_gateway'

# Copied-state, loopback-only rehearsal, including restart behavior.
cp "$BACKUP" "$REHEARSAL_DIR/viridis_state.db"
docker run -d --name "$REHEARSAL_CONTAINER" \
  --network viridis-fleet_default \
  --env-file "$SOURCE_DIR/.env" \
  -e PUBLIC_BASE=http://127.0.0.1:18402 \
  -e STATE_DB=/data/viridis_state.db \
  -e HUB_KERNEL_REQUIRED=1 \
  -p 127.0.0.1:18402:8402 \
  -v "$REHEARSAL_DIR:/data" \
  "$CANDIDATE_TAG" > "$RUN_DIR/rehearsal-container-id.txt"
wait_container_healthy "$REHEARSAL_CONTAINER" "$CANDIDATE_IMAGE"
verify_adoption_url http://127.0.0.1:18402 rehearsal-first-boot
docker restart "$REHEARSAL_CONTAINER" > "$RUN_DIR/rehearsal-restart.txt"
wait_container_healthy "$REHEARSAL_CONTAINER" "$CANDIDATE_IMAGE"
verify_adoption_url http://127.0.0.1:18402 rehearsal-restart
cleanup_rehearsal

# Production promotion with automatic rollback on every post-tag failure.
docker tag "$BASE_IMAGE" "$ROLLBACK_TAG"
docker tag "$CANDIDATE_IMAGE" "$LATEST_TAG"
rollback_required=1
compose_gateway
wait_container_healthy "$LIVE_CONTAINER" "$CANDIDATE_IMAGE"
verify_adoption_url https://mcp.viridisconservation.com production-first-boot
verify_state first-boot
docker restart "$LIVE_CONTAINER" > "$RUN_DIR/production-restart.txt"
wait_container_healthy "$LIVE_CONTAINER" "$CANDIDATE_IMAGE"
verify_adoption_url https://mcp.viridisconservation.com production-restart
verify_state restart

# Align the non-serving source checkout only after the live image verifies.
for relative_path in \
  deploy/gateway/adoption_loop.py \
  deploy/gateway/x402_http.py \
  deploy/gateway/viridis_mcp_gateway.py \
  deploy/gateway/a2a_commerce.py \
  deploy/gateway/Dockerfile \
  deploy/gateway/llms.txt \
  deploy/gateway/quickstart.html
do
  cp "$CONTEXT_DIR/$relative_path" "$SOURCE_DIR/$relative_path"
done
sha256sum "$RUN_DIR"/*.json "$RUN_DIR"/*.txt > "$RUN_DIR/evidence.sha256"

rollback_required=0
trap - EXIT INT TERM
echo "production promotion verified: adoption loop ($RUN_ID) image=$CANDIDATE_IMAGE backup=$BACKUP"
