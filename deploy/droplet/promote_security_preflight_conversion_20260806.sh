#!/bin/sh
# State-safe production promotion for the Security Preflight conversion path.

set -eu

EXPECTED_AUTH='authorize production promotion: security preflight conversion 20260806'
PREVIOUS_IMAGE='sha256:4d465097726f8ca0c50eaf90559df0669be2a36715b24b7e06be2aa1556846ed'
CANDIDATE_IMAGE='sha256:6ccad07a9a325bb72f4673345289acf65188bfb31f5db7663def48876f0ec878'
CANDIDATE_TAG='viridis-stable:security-preflight-conversion-20260806-candidate'
ROLLBACK_TAG='viridis-stable:rollback-security-preflight-conversion-20260806'
LATEST_TAG='viridis-stable:latest'
LIVE_CONTAINER='viridis-fleet-gateway-1'
COMPOSE_DIR='/root/viridis-fleet/deploy/droplet'
ENV_FILE='/root/viridis-fleet/.env'
EVIDENCE_DIR='/root/viridis-candidates/security-preflight-conversion-20260806'
BACKUP="$EVIDENCE_DIR/state-backup/viridis_state-20260806T194815Z.db"
BACKUP_MANIFEST="$EVIDENCE_DIR/state-backup/viridis_state-20260806T194815Z.manifest.json"
EXPECTED_BACKUP_SHA='9f70148d95cc4ac417a5102f4fbdda5d51c2ad19330d506d7839039e29b0f0a1'
EXPECTED_BACKUP_MANIFEST_SHA='d40b1cb554ff26dec84ce3b322e8f7c73892f6c39abc44892673cc23156f89e7'
EXPECTED_OLD_AGENTS_SHA='3a0dd932ad3a91df3d6295c35b223b1c8cd6db6fc8dd3e2a82dcca55565cda39'
EXPECTED_OLD_QUICKSTART_SHA='a5fad3ef2c081bb2ffbcf0ab567e268ace5a5ad37f122e512347654a166e150b'
EXPECTED_AGENTS_SHA='089d60fec369597cd5356740fab9cafe24c0097237236290d9473045a7dc9be5'
EXPECTED_QUICKSTART_SHA='3ea80610cbc8b74d971d1b91841fbd34bfc8fa68691071f379baace1f19dd2fc'
EXPECTED_CLIENT_SHA='eb71c466ad17c81d36e3f03c5ba308a4a0f8922337cef5116cc604deab87252d'

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

public_probe() {
  suffix=$1
  health="$RUN_DIR/health-$suffix.json"
  agents="$RUN_DIR/agents-$suffix.html"
  quickstart="$RUN_DIR/quickstart-$suffix.html"
  challenge="$RUN_DIR/security-challenge-$suffix.json"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS https://mcp.viridisconservation.com/healthz > "$health"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS https://mcp.viridisconservation.com/agents > "$agents"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS https://mcp.viridisconservation.com/quickstart > "$quickstart"
  challenge_code=$(curl -sS -o "$challenge" -w '%{http_code}' \
    'https://mcp.viridisconservation.com/x402/security-preflight/security_preflight?agent_id=viridis-probe&manifest=%7B%7D')
  [ "$challenge_code" = 402 ]
  python3 -c '
import json, sys
health = json.load(open(sys.argv[1]))
agents = open(sys.argv[2]).read()
quickstart = open(sys.argv[3]).read()
challenge = json.load(open(sys.argv[4]))
assert health["status"] == "ok"
assert len(health["agents"]) == 28
assert all(item.get("status") == "ok" for item in health["agents"].values())
assert "href=\"/quickstart#security-first-call\"" in agents
assert "badge.svg?resource=" in agents and "&amp;v=2" in agents
assert "not an endorsement, runtime audit, paid usage, or revenue" in agents
assert "id=\"security-first-call\"" in quickstart
assert "--dry-run --route security-preflight" in quickstart
assert "--route security-preflight --max-payment-usdc 0.01" in quickstart
assert challenge
' "$health" "$agents" "$quickstart" "$challenge"
}

rollback_required=0
rollback() {
  trap - EXIT INT TERM
  echo 'promotion failed; restoring the pinned previous image' >&2
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG" || return 1
  compose_gateway || return 1
  wait_healthy "$PREVIOUS_IMAGE" || return 1
  verify_state "$RUN_DIR/state-rollback.json" || return 1
  echo 'Security Preflight conversion rollback verified' >&2
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

# All external and immutable preconditions are proven before the first tag move.
[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" = "$PREVIOUS_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$PREVIOUS_IMAGE" ]
[ "$(docker image inspect --format '{{.Id}}' "$CANDIDATE_TAG")" = "$CANDIDATE_IMAGE" ]
[ -z "$(docker ps -q --filter ancestor="$CANDIDATE_IMAGE")" ]
[ "$(sha256sum "$BACKUP" | awk '{print $1}')" = "$EXPECTED_BACKUP_SHA" ]
[ "$(sha256sum "$BACKUP_MANIFEST" | awk '{print $1}')" = "$EXPECTED_BACKUP_MANIFEST_SHA" ]
python3 "$EVIDENCE_DIR/build-context/deploy/droplet/gateway_state_backup.py" verify \
  --backup "$BACKUP" --manifest "$BACKUP_MANIFEST" \
  > "$RUN_DIR/offline-backup-before.json"
verify_state "$RUN_DIR/state-before.json"

docker exec "$LIVE_CONTAINER" sha256sum \
  /fleet/deploy/gateway/agents.html \
  /fleet/deploy/gateway/quickstart.html > "$RUN_DIR/live-source-before.sha256"
[ "$(awk '$2==\"/fleet/deploy/gateway/agents.html\"{print $1}' "$RUN_DIR/live-source-before.sha256")" = "$EXPECTED_OLD_AGENTS_SHA" ]
[ "$(awk '$2==\"/fleet/deploy/gateway/quickstart.html\"{print $1}' "$RUN_DIR/live-source-before.sha256")" = "$EXPECTED_OLD_QUICKSTART_SHA" ]

docker run --rm --network none --read-only --entrypoint sha256sum \
  "$CANDIDATE_IMAGE" \
  /fleet/deploy/gateway/agents.html \
  /fleet/deploy/gateway/quickstart.html > "$RUN_DIR/candidate-source-before.sha256"
[ "$(awk '$2==\"/fleet/deploy/gateway/agents.html\"{print $1}' "$RUN_DIR/candidate-source-before.sha256")" = "$EXPECTED_AGENTS_SHA" ]
[ "$(awk '$2==\"/fleet/deploy/gateway/quickstart.html\"{print $1}' "$RUN_DIR/candidate-source-before.sha256")" = "$EXPECTED_QUICKSTART_SHA" ]

curl --retry 8 --retry-delay 2 --retry-all-errors -fsS \
  https://raw.githubusercontent.com/jdhart81/viridis-agent-fleet/main/scripts/x402_demo_client.py \
  > "$RUN_DIR/public-x402-demo-client.py"
[ "$(sha256sum "$RUN_DIR/public-x402-demo-client.py" | awk '{print $1}')" = "$EXPECTED_CLIENT_SHA" ]

docker tag "$PREVIOUS_IMAGE" "$ROLLBACK_TAG"
[ "$(docker image inspect --format '{{.Id}}' "$ROLLBACK_TAG")" = "$PREVIOUS_IMAGE" ]

rollback_required=1
docker tag "$CANDIDATE_IMAGE" "$LATEST_TAG"
compose_gateway
wait_healthy "$CANDIDATE_IMAGE"
public_probe first-boot
verify_state "$RUN_DIR/state-first-boot.json"

docker restart "$LIVE_CONTAINER" > "$RUN_DIR/restart-container-id.txt"
wait_healthy "$CANDIDATE_IMAGE"
public_probe restart
verify_state "$RUN_DIR/state-restart.json"

[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" = "$CANDIDATE_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$CANDIDATE_IMAGE" ]
docker inspect "$LIVE_CONTAINER" > "$RUN_DIR/final-container-inspect.json"
sha256sum "$RUN_DIR"/* > "$RUN_DIR/evidence.sha256"

rollback_required=0
trap - EXIT INT TERM
echo "production promotion verified: Security Preflight conversion ($RUN_ID)"
