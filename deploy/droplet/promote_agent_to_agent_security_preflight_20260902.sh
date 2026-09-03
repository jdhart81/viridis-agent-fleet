#!/bin/sh
# Promote the agent-to-agent Security Preflight activation copy on the exact live image.

set -eu

EXPECTED_AUTH='authorize production promotion: agent-to-agent Security Preflight activation 20260902'
BASE_IMAGE='sha256:aad054a5019daaf2a64ceca3a74c503494776eeabb2af28f845957cb37955d8b'
CANDIDATE_TAG='viridis-stable:agent-to-agent-security-preflight-20260902-candidate'
ROLLBACK_TAG='viridis-stable:rollback-agent-to-agent-security-preflight-20260902'
LATEST_TAG='viridis-stable:latest'
LIVE_CONTAINER='viridis-fleet-gateway-1'
REHEARSAL_CONTAINER='viridis-agent-to-agent-security-preflight-rehearsal-20260902'
COMPOSE_DIR='/root/viridis-fleet/deploy/droplet'
SOURCE_DIR='/root/viridis-fleet'
RELEASE_DIR='/root/viridis-candidates/agent-to-agent-security-preflight-20260902'
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
RUN_DIR="$RELEASE_DIR/promotion-runs/$RUN_ID"
BACKUP_DIR="$RUN_DIR/backups"
REHEARSAL_DIR="$RUN_DIR/rehearsal-state"
CONTEXT_DIR="$RUN_DIR/build-context"
EXPECTED_LIVE_QUICKSTART_SHA='7c0d85571d177e1fdb9389763e3fb1c89d374c2d74699dd7fd98c5ebce00c0f0'
EXPECTED_LIVE_LLMS_SHA='17ba2ba91ba5f40f6733ac8882c547b69cd6d6e08bdde906da6e14f6f97038e4'
EXPECTED_LIVE_SKILL_SHA='91bd4f0206df384b104a075b78329dccf4b53879be020cf5f8182c1d04103ea3'
EXPECTED_QUICKSTART_SHA='31ef166e908953e6d5e4817cca4491d719d8504b744fc81050abfb7d73c0dd84'
EXPECTED_LLMS_SHA='b3b3d231312cd13e4cac81cc3218532da7bf160c105096d8d42696e5f374c6bc'
EXPECTED_SKILL_SHA='356f55602fde20056075a416cb6d2dbb23ce2d2c65e0e5c2e0d41a8c4f3dedf3'

if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]; then
  echo 'refusing: exact production-promotion authorization required' >&2
  exit 64
fi

mkdir -p "$RUN_DIR" "$BACKUP_DIR" "$REHEARSAL_DIR" "$CONTEXT_DIR"

compose_gateway() {
  docker compose --project-directory "$COMPOSE_DIR" \
    --file "$COMPOSE_DIR/docker-compose.yml" --project-name viridis-fleet \
    --env-file "$SOURCE_DIR/.env" up -d --no-deps --force-recreate gateway
}

wait_healthy() {
  container_name=$1
  expected_image=$2
  attempts=0
  while [ "$attempts" -lt 60 ]; do
    image=$(docker inspect --format '{{.Image}}' "$container_name" 2>/dev/null || true)
    health=$(docker inspect --format '{{.State.Health.Status}}' "$container_name" 2>/dev/null || true)
    [ "$image" = "$expected_image" ] && [ "$health" = healthy ] && return 0
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
import json, sys
item = json.load(open(sys.argv[1]))
assert item["status"] == "ok"
assert item["integrity_check"] == "ok"
assert item["agent_state_rows"] == 35
PY
}

verify_surface() {
  base=$1
  suffix=$2
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS "$base/healthz" > "$RUN_DIR/health-$suffix.json"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS "$base/quickstart" > "$RUN_DIR/quickstart-$suffix.html"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS "$base/llms.txt" > "$RUN_DIR/llms-$suffix.txt"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS "$base/.well-known/skills/viridis-paid-tools/SKILL.md" \
    > "$RUN_DIR/skill-$suffix.md"
  code=$(curl -sS -D "$RUN_DIR/challenge-$suffix.headers" \
    -o "$RUN_DIR/challenge-$suffix.json" -w '%{http_code}' \
    -X POST "$base/x402/security-preflight/security_preflight" \
    -H 'content-type: application/json' \
    --data '{"agent_id":"buyer-security-demo","manifest":{"endpoint":"https://buyer.example/mcp","auth":"bearer","tools":[]},"policy":{"allowed_tools":[],"denied_tools":[],"approval_required_tools":[]}}')
  [ "$code" = 402 ]
  python3 - "$RUN_DIR/health-$suffix.json" "$RUN_DIR/quickstart-$suffix.html" \
    "$RUN_DIR/llms-$suffix.txt" "$RUN_DIR/skill-$suffix.md" \
    "$RUN_DIR/challenge-$suffix.json" \
    "$RUN_DIR/challenge-$suffix.headers" <<'PY'
import base64, json, sys
health = json.load(open(sys.argv[1]))
quickstart = open(sys.argv[2]).read()
llms = open(sys.argv[3]).read()
skill = open(sys.argv[4]).read()
challenge = json.load(open(sys.argv[5]))
headers = open(sys.argv[6]).read().splitlines()
assert health["status"] == "ok"
assert health["mount_errors"] == {}
assert "Let your agent pay to screen an MCP server before it connects." in quickstart
assert "Use Coinbase Payments MCP" in quickstart
assert "--route security-preflight --max-payment-usdc 0.01" in quickstart
assert "# Viridis paid MCP security and evidence tools" in llms
assert "Coinbase Payments MCP" in llms
assert "For a new wallet, prefer one Security Preflight call" in skill
assert challenge["error"] == "PAYMENT-SIGNATURE required"
encoded = next(
    line.split(":", 1)[1].strip() for line in headers
    if line.lower().startswith("payment-required:")
)
encoded += "=" * (-len(encoded) % 4)
requirements = json.loads(base64.urlsafe_b64decode(encoded))
assert requirements["x402Version"] == 2
accepts = requirements["accepts"]
assert accepts and accepts[0]["network"] == "eip155:8453"
assert accepts[0]["amount"] == "10000"
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
  echo 'agent-to-agent Security Preflight rollback verified' >&2
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
[ "$(docker exec "$LIVE_CONTAINER" sha256sum /fleet/deploy/gateway/quickstart.html | awk '{print $1}')" = "$EXPECTED_LIVE_QUICKSTART_SHA" ]
[ "$(docker exec "$LIVE_CONTAINER" sha256sum /fleet/deploy/gateway/llms.txt | awk '{print $1}')" = "$EXPECTED_LIVE_LLMS_SHA" ]
[ "$(docker exec "$LIVE_CONTAINER" sha256sum /fleet/integrations/viridis-paid-tools/SKILL.md | awk '{print $1}')" = "$EXPECTED_LIVE_SKILL_SHA" ]

for item in \
  "$RELEASE_DIR/quickstart.html:$EXPECTED_QUICKSTART_SHA" \
  "$RELEASE_DIR/llms.txt:$EXPECTED_LLMS_SHA" \
  "$RELEASE_DIR/SKILL.md:$EXPECTED_SKILL_SHA"
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

cp "$RELEASE_DIR/quickstart.html" "$CONTEXT_DIR/quickstart.html"
cp "$RELEASE_DIR/llms.txt" "$CONTEXT_DIR/llms.txt"
cp "$RELEASE_DIR/SKILL.md" "$CONTEXT_DIR/SKILL.md"
cat > "$CONTEXT_DIR/Dockerfile" <<EOF
FROM $ROLLBACK_TAG
COPY quickstart.html /fleet/deploy/gateway/quickstart.html
COPY llms.txt /fleet/deploy/gateway/llms.txt
COPY SKILL.md /fleet/integrations/viridis-paid-tools/SKILL.md
EOF

docker tag "$BASE_IMAGE" "$ROLLBACK_TAG"
docker build --pull=false -f "$CONTEXT_DIR/Dockerfile" \
  -t "$CANDIDATE_TAG" "$CONTEXT_DIR" > "$RUN_DIR/docker-build.log"
CANDIDATE_IMAGE=$(docker image inspect --format '{{.Id}}' "$CANDIDATE_TAG")
printf '%s\n' "$CANDIDATE_IMAGE" > "$RUN_DIR/candidate-image-id.txt"
docker run --rm --network none --read-only --entrypoint sha256sum \
  "$CANDIDATE_TAG" /fleet/deploy/gateway/quickstart.html \
  /fleet/deploy/gateway/llms.txt \
  /fleet/integrations/viridis-paid-tools/SKILL.md \
  > "$RUN_DIR/candidate-source.sha256"
[ "$(awk '$2=="/fleet/deploy/gateway/quickstart.html"{print $1}' "$RUN_DIR/candidate-source.sha256")" = "$EXPECTED_QUICKSTART_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/llms.txt"{print $1}' "$RUN_DIR/candidate-source.sha256")" = "$EXPECTED_LLMS_SHA" ]
[ "$(awk '$2=="/fleet/integrations/viridis-paid-tools/SKILL.md"{print $1}' "$RUN_DIR/candidate-source.sha256")" = "$EXPECTED_SKILL_SHA" ]

cp "$BACKUP" "$REHEARSAL_DIR/viridis_state.db"
docker run -d --name "$REHEARSAL_CONTAINER" --network viridis-fleet_default \
  --env-file "$SOURCE_DIR/.env" -e PUBLIC_BASE=http://127.0.0.1:18403 \
  -e STATE_DB=/data/viridis_state.db -e HUB_KERNEL_REQUIRED=1 \
  -p 127.0.0.1:18403:8402 -v "$REHEARSAL_DIR:/data" \
  "$CANDIDATE_TAG" > "$RUN_DIR/rehearsal-container-id.txt"
wait_healthy "$REHEARSAL_CONTAINER" "$CANDIDATE_IMAGE"
verify_surface http://127.0.0.1:18403 rehearsal-first-boot
verify_state "$REHEARSAL_CONTAINER" rehearsal-first-boot
docker restart "$REHEARSAL_CONTAINER" > "$RUN_DIR/rehearsal-restart.txt"
wait_healthy "$REHEARSAL_CONTAINER" "$CANDIDATE_IMAGE"
verify_surface http://127.0.0.1:18403 rehearsal-restart
verify_state "$REHEARSAL_CONTAINER" rehearsal-restart
cleanup_rehearsal

docker tag "$CANDIDATE_IMAGE" "$LATEST_TAG"
rollback_required=1
compose_gateway
wait_healthy "$LIVE_CONTAINER" "$CANDIDATE_IMAGE"
verify_surface https://mcp.viridisconservation.com production-first-boot
verify_state "$LIVE_CONTAINER" production-first-boot
docker restart "$LIVE_CONTAINER" > "$RUN_DIR/production-restart.txt"
wait_healthy "$LIVE_CONTAINER" "$CANDIDATE_IMAGE"
verify_surface https://mcp.viridisconservation.com production-restart
verify_state "$LIVE_CONTAINER" production-restart

cp "$RELEASE_DIR/quickstart.html" "$SOURCE_DIR/deploy/gateway/quickstart.html"
cp "$RELEASE_DIR/llms.txt" "$SOURCE_DIR/deploy/gateway/llms.txt"
mkdir -p "$SOURCE_DIR/integrations/viridis-paid-tools"
cp "$RELEASE_DIR/SKILL.md" "$SOURCE_DIR/integrations/viridis-paid-tools/SKILL.md"
sha256sum "$RUN_DIR"/*.json "$RUN_DIR"/*.txt "$RUN_DIR"/*.html \
  "$RUN_DIR"/*.md > "$RUN_DIR/evidence.sha256"

rollback_required=0
trap - EXIT INT TERM
echo "production promotion verified: agent-to-agent Security Preflight ($RUN_ID) image=$CANDIDATE_IMAGE backup=$BACKUP"
