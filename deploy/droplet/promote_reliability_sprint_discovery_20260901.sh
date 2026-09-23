#!/bin/sh
# Promote the two reviewed Reliability Sprint discovery corrections.

set -eu

EXPECTED_AUTH='deploy the updates'
BASE_IMAGE='sha256:d3dc66dc8697647e45327b8afbcf8ac7c619f6e2b0483bfb1bdc459de333b1ab'
BASE_TAG='viridis-stable:base-reliability-sprint-discovery-20260901'
CANDIDATE_TAG='viridis-stable:reliability-sprint-discovery-20260901-candidate'
ROLLBACK_TAG='viridis-stable:rollback-reliability-sprint-discovery-20260901'
LATEST_TAG='viridis-stable:latest'
LIVE_CONTAINER='viridis-fleet-gateway-1'
REHEARSAL_CONTAINER='viridis-reliability-sprint-discovery-rehearsal-20260901'
COMPOSE_DIR='/root/viridis-fleet/deploy/droplet'
SOURCE_DIR='/root/viridis-fleet'
RELEASE_DIR='/root/viridis-candidates/reliability-sprint-discovery-20260901'
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
RUN_DIR="$RELEASE_DIR/promotion-runs/$RUN_ID"
BACKUP_DIR="$RUN_DIR/backups"
REHEARSAL_DIR="$RUN_DIR/rehearsal-state"
CONTEXT_DIR="$RUN_DIR/build-context"
EXPECTED_LIVE_GATEWAY_SHA='01fa93d3d0b84ac0521e045b5e44b96f0fbd7df486e855356eaf9dedd5a1f76f'
EXPECTED_LIVE_LLMS_SHA='9ae9a9f338e6889f177b753208cb7ed6701edde2b540088ede8a56aaf1006ae4'
EXPECTED_GATEWAY_SHA='7a3b2e428635d3c8cc5dc47394c618621aa503f8431c7315daeada15cc2a9204'
EXPECTED_LLMS_SHA='17ba2ba91ba5f40f6733ac8882c547b69cd6d6e08bdde906da6e14f6f97038e4'
EXPECTED_DOCKERFILE_SHA='cd77cc9203f3d127129bb3cb2686e9e4ec8190b16d57b7c984ea7e581ea543f5'

if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]; then
  echo 'refusing: exact deployment authorization required' >&2
  exit 64
fi

mkdir -p "$RUN_DIR" "$BACKUP_DIR" "$REHEARSAL_DIR" "$CONTEXT_DIR"

compose_gateway() {
  docker compose \
    --project-directory "$COMPOSE_DIR" \
    --file "$COMPOSE_DIR/docker-compose.yml" \
    --project-name viridis-fleet \
    --env-file "$SOURCE_DIR/.env" \
    up -d --no-deps --force-recreate gateway
}

wait_healthy() {
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
  echo "container did not reach expected healthy image: $container_name" >&2
  return 1
}

verify_state() {
  container_name=$1
  suffix=$2
  docker exec "$container_name" python3 \
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

verify_discovery() {
  base_url=$1
  suffix=$2
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS "$base_url/healthz" > "$RUN_DIR/health-$suffix.json"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS "$base_url/reliability-sprint" > "$RUN_DIR/sprint-$suffix.html"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS "$base_url/llms.txt" > "$RUN_DIR/llms-$suffix.txt"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS "$base_url/sitemap.xml" > "$RUN_DIR/sitemap-$suffix.xml"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS "$base_url/.well-known/agent-adoption.json" \
    > "$RUN_DIR/adoption-$suffix.json"
  python3 - \
    "$RUN_DIR/health-$suffix.json" \
    "$RUN_DIR/sprint-$suffix.html" \
    "$RUN_DIR/llms-$suffix.txt" \
    "$RUN_DIR/sitemap-$suffix.xml" \
    "$RUN_DIR/adoption-$suffix.json" <<'PY'
import json
import sys
health = json.load(open(sys.argv[1]))
sprint = open(sys.argv[2]).read()
llms = open(sys.argv[3]).read()
sitemap = open(sys.argv[4]).read()
adoption = json.load(open(sys.argv[5]))
assert health["status"] == "ok"
assert len(health["agents"]) == 28
assert health["mount_errors"] == {}
assert health["human_surfaces"]["reliability_sprint"].endswith(
    "/reliability-sprint")
assert "Bring one fragile workflow" in sprint
assert "https://mcp.viridisconservation.com/reliability-sprint" in llms
assert "<loc>" in sitemap
assert "/reliability-sprint</loc>" in sitemap
assert adoption["spec_version"] == "viridis-adoption-v1"
PY
}

cleanup_rehearsal() {
  docker rm -f "$REHEARSAL_CONTAINER" >/dev/null 2>&1 || true
}

rollback_required=0
rollback() {
  trap - EXIT INT TERM
  cleanup_rehearsal
  echo 'promotion failed; restoring exact prior image' >&2
  docker tag "$BASE_IMAGE" "$LATEST_TAG"
  compose_gateway
  wait_healthy "$LIVE_CONTAINER" "$BASE_IMAGE"
  verify_state "$LIVE_CONTAINER" rollback
  echo 'Reliability Sprint discovery rollback verified' >&2
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

[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" = "$BASE_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$BASE_IMAGE" ]
[ "$(docker exec "$LIVE_CONTAINER" sha256sum /fleet/deploy/gateway/viridis_mcp_gateway.py | awk '{print $1}')" = "$EXPECTED_LIVE_GATEWAY_SHA" ]
[ "$(docker exec "$LIVE_CONTAINER" sha256sum /fleet/deploy/gateway/llms.txt | awk '{print $1}')" = "$EXPECTED_LIVE_LLMS_SHA" ]

for item in \
  "$RELEASE_DIR/viridis_mcp_gateway.py:$EXPECTED_GATEWAY_SHA" \
  "$RELEASE_DIR/llms.txt:$EXPECTED_LLMS_SHA" \
  "$RELEASE_DIR/Dockerfile.reliability-sprint-discovery-20260901:$EXPECTED_DOCKERFILE_SHA"
do
  file=${item%%:*}
  expected=${item##*:}
  [ "$(sha256sum "$file" | awk '{print $1}')" = "$expected" ]
done

python3 "$SOURCE_DIR/deploy/droplet/gateway_state_backup.py" backup \
  --source /var/lib/docker/volumes/viridis-fleet_gateway_state/_data/viridis_state.db \
  --destination-dir "$BACKUP_DIR" > "$RUN_DIR/backup.json"
BACKUP=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["backup"])' "$RUN_DIR/backup.json")
MANIFEST="${BACKUP%.db}.manifest.json"
python3 "$SOURCE_DIR/deploy/droplet/gateway_state_backup.py" restore-drill \
  --backup "$BACKUP" --manifest "$MANIFEST" \
  --scratch "$RUN_DIR/restore-drill.db" > "$RUN_DIR/restore-drill.json"

cp "$RELEASE_DIR/viridis_mcp_gateway.py" "$CONTEXT_DIR/viridis_mcp_gateway.py"
cp "$RELEASE_DIR/llms.txt" "$CONTEXT_DIR/llms.txt"
cp "$RELEASE_DIR/Dockerfile.reliability-sprint-discovery-20260901" \
  "$CONTEXT_DIR/Dockerfile"

docker tag "$BASE_IMAGE" "$BASE_TAG"
docker build --pull=false -f "$CONTEXT_DIR/Dockerfile" \
  -t "$CANDIDATE_TAG" "$CONTEXT_DIR" > "$RUN_DIR/docker-build.log"
CANDIDATE_IMAGE=$(docker image inspect --format '{{.Id}}' "$CANDIDATE_TAG")
printf '%s\n' "$CANDIDATE_IMAGE" > "$RUN_DIR/candidate-image-id.txt"
docker run --rm --network none --read-only -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 "$CANDIDATE_TAG" -c \
  'import sys; sys.path.insert(0, "/fleet/deploy/gateway"); import viridis_mcp_gateway, adoption_loop'
docker run --rm --network none --read-only --entrypoint sha256sum \
  "$CANDIDATE_TAG" /fleet/deploy/gateway/viridis_mcp_gateway.py \
  /fleet/deploy/gateway/llms.txt > "$RUN_DIR/candidate-source.sha256"
[ "$(awk '$2=="/fleet/deploy/gateway/viridis_mcp_gateway.py"{print $1}' "$RUN_DIR/candidate-source.sha256")" = "$EXPECTED_GATEWAY_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/llms.txt"{print $1}' "$RUN_DIR/candidate-source.sha256")" = "$EXPECTED_LLMS_SHA" ]

cp "$BACKUP" "$REHEARSAL_DIR/viridis_state.db"
docker run -d --name "$REHEARSAL_CONTAINER" \
  --network viridis-fleet_default \
  --env-file "$SOURCE_DIR/.env" \
  -e PUBLIC_BASE=http://127.0.0.1:18403 \
  -e STATE_DB=/data/viridis_state.db \
  -e HUB_KERNEL_REQUIRED=1 \
  -p 127.0.0.1:18403:8402 \
  -v "$REHEARSAL_DIR:/data" \
  "$CANDIDATE_TAG" > "$RUN_DIR/rehearsal-container-id.txt"
wait_healthy "$REHEARSAL_CONTAINER" "$CANDIDATE_IMAGE"
verify_discovery http://127.0.0.1:18403 rehearsal-first-boot
verify_state "$REHEARSAL_CONTAINER" rehearsal-first-boot
docker restart "$REHEARSAL_CONTAINER" > "$RUN_DIR/rehearsal-restart.txt"
wait_healthy "$REHEARSAL_CONTAINER" "$CANDIDATE_IMAGE"
verify_discovery http://127.0.0.1:18403 rehearsal-restart
verify_state "$REHEARSAL_CONTAINER" rehearsal-restart
cleanup_rehearsal

docker tag "$BASE_IMAGE" "$ROLLBACK_TAG"
docker tag "$CANDIDATE_IMAGE" "$LATEST_TAG"
rollback_required=1
compose_gateway
wait_healthy "$LIVE_CONTAINER" "$CANDIDATE_IMAGE"
verify_discovery https://mcp.viridisconservation.com production-first-boot
verify_state "$LIVE_CONTAINER" production-first-boot
docker restart "$LIVE_CONTAINER" > "$RUN_DIR/production-restart.txt"
wait_healthy "$LIVE_CONTAINER" "$CANDIDATE_IMAGE"
verify_discovery https://mcp.viridisconservation.com production-restart
verify_state "$LIVE_CONTAINER" production-restart

cp "$RELEASE_DIR/viridis_mcp_gateway.py" \
  "$SOURCE_DIR/deploy/gateway/viridis_mcp_gateway.py"
cp "$RELEASE_DIR/llms.txt" "$SOURCE_DIR/deploy/gateway/llms.txt"
sha256sum "$RUN_DIR"/*.json "$RUN_DIR"/*.txt "$RUN_DIR"/*.html \
  "$RUN_DIR"/*.xml > "$RUN_DIR/evidence.sha256"

rollback_required=0
trap - EXIT INT TERM
echo "production promotion verified: Reliability Sprint discovery ($RUN_ID) image=$CANDIDATE_IMAGE backup=$BACKUP"
