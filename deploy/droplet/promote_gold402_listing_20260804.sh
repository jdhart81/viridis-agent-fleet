#!/bin/sh
# Exact, state-safe promotion for the disclosed Gold402 listing link.

set -eu

EXPECTED_AUTH='authorize production promotion: gold402 listing 20260804'
PREVIOUS_IMAGE='sha256:f65ff7f447569152ee79698547ce119c62d0d3e71fe8ba8c9ad19c292bf37f22'
CANDIDATE_IMAGE='sha256:4d465097726f8ca0c50eaf90559df0669be2a36715b24b7e06be2aa1556846ed'
CANDIDATE_TAG='viridis-stable:gold402-listing-20260804'
ROLLBACK_TAG='viridis-stable:rollback-gold402-listing-20260804'
LATEST_TAG='viridis-stable:latest'
LIVE_CONTAINER='viridis-fleet-gateway-1'
COMPOSE_DIR='/root/viridis-fleet/deploy/droplet'
ENV_FILE='/root/viridis-fleet/.env'
EVIDENCE_DIR='/root/viridis-candidates/gold402-listing-20260804'
EXPECTED_AGENTS_SHA='3a0dd932ad3a91df3d6295c35b223b1c8cd6db6fc8dd3e2a82dcca55565cda39'
EXPECTED_X402_SHA='ca06a33a2da27cab1913684ceedce0a446907a9611cd8a065dcba021695b7524'

if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]; then
  echo 'refusing: exact Gold402-listing promotion authorization required' >&2
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

public_probe() {
  suffix=$1
  health="$RUN_DIR/health-$suffix.json"
  agents="$RUN_DIR/agents-$suffix.html"
  challenge="$RUN_DIR/security-challenge-$suffix.json"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS https://mcp.viridisconservation.com/healthz > "$health"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS https://mcp.viridisconservation.com/agents > "$agents"
  challenge_code=$(curl -sS -o "$challenge" -w '%{http_code}' \
    'https://mcp.viridisconservation.com/x402/security-preflight/security_preflight?agent_id=viridis-probe&manifest=%7B%7D')
  [ "$challenge_code" = 402 ]
  python3 -c '
import json, sys
health = json.load(open(sys.argv[1]))
page = open(sys.argv[2]).read()
assert health["status"] == "ok"
assert len(health["agents"]) == 28
assert all(item.get("status") == "ok" for item in health["agents"].values())
assert "Security Preflight on Gold402" in page
assert "no independent rater grade yet" in page
assert "not an endorsement, runtime audit, paid usage, or revenue" in page
assert "24klabs.ai/listing/viridis-mcp-security-preflight/" in page
assert "24klabs.ai/badge.svg" not in page
' "$health" "$agents"
}

rollback_required=0
rollback() {
  trap - EXIT INT TERM
  echo 'promotion failed; restoring the pinned previous image' >&2
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG" || return 1
  compose_gateway || return 1
  wait_healthy "$PREVIOUS_IMAGE" || return 1
  echo 'Gold402-listing rollback verified' >&2
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

[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" = "$PREVIOUS_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$CANDIDATE_TAG")" = "$CANDIDATE_IMAGE" ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$PREVIOUS_IMAGE" ]
docker run --rm --network none --read-only --entrypoint sha256sum \
  "$CANDIDATE_IMAGE" \
  /fleet/deploy/gateway/agents.html \
  /fleet/deploy/gateway/x402_http.py > "$RUN_DIR/candidate-source-sha256.txt"
[ "$(awk '$2=="/fleet/deploy/gateway/agents.html"{print $1}' "$RUN_DIR/candidate-source-sha256.txt")" = "$EXPECTED_AGENTS_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/x402_http.py"{print $1}' "$RUN_DIR/candidate-source-sha256.txt")" = "$EXPECTED_X402_SHA" ]
docker exec "$LIVE_CONTAINER" python3 \
  /fleet/deploy/gateway/gateway_state_backup.py verify \
  --backup /data/viridis_state.db > "$RUN_DIR/state-before.json"

docker tag "$PREVIOUS_IMAGE" "$ROLLBACK_TAG"
[ "$(docker image inspect --format '{{.Id}}' "$ROLLBACK_TAG")" = "$PREVIOUS_IMAGE" ]

rollback_required=1
docker tag "$CANDIDATE_IMAGE" "$LATEST_TAG"
compose_gateway
wait_healthy "$CANDIDATE_IMAGE"
public_probe first-boot
docker exec "$LIVE_CONTAINER" python3 \
  /fleet/deploy/gateway/gateway_state_backup.py verify \
  --backup /data/viridis_state.db > "$RUN_DIR/state-first-boot.json"

docker restart "$LIVE_CONTAINER" > "$RUN_DIR/restart-container-id.txt"
wait_healthy "$CANDIDATE_IMAGE"
public_probe restart
docker exec "$LIVE_CONTAINER" python3 \
  /fleet/deploy/gateway/gateway_state_backup.py verify \
  --backup /data/viridis_state.db > "$RUN_DIR/state-restart.json"

python3 -c '
import json, sys
rows = []
for path in sys.argv[1:]:
    item = json.load(open(path))
    assert item["status"] == "ok"
    assert item["integrity_check"] == "ok"
    rows.append(item["agent_state_rows"])
assert rows == [35, 35, 35]
' "$RUN_DIR/state-before.json" "$RUN_DIR/state-first-boot.json" "$RUN_DIR/state-restart.json"

[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" = "$CANDIDATE_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$CANDIDATE_IMAGE" ]
docker inspect "$LIVE_CONTAINER" > "$RUN_DIR/final-container-inspect.json"
sha256sum "$RUN_DIR"/* > "$RUN_DIR/evidence.sha256"

rollback_required=0
trap - EXIT INT TERM
echo "promotion verified: Gold402 listing link ($RUN_ID)"
