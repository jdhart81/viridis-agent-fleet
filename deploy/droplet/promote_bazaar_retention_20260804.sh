#!/bin/sh
# Exact, state-safe promotion for the buyer-visible Bazaar retention offer.

set -eu

EXPECTED_AUTH='authorize production promotion: bazaar retention 20260804'
PREVIOUS_IMAGE='sha256:5a5402b4c490c53cda9e28c0115fafc11a2bd60a11b6f85740764e39ae036f67'
CANDIDATE_IMAGE='sha256:f65ff7f447569152ee79698547ce119c62d0d3e71fe8ba8c9ad19c292bf37f22'
CANDIDATE_TAG='viridis-stable:bazaar-retention-20260804'
ROLLBACK_TAG='viridis-stable:rollback-bazaar-retention-20260804'
LATEST_TAG='viridis-stable:latest'
LIVE_CONTAINER='viridis-fleet-gateway-1'
COMPOSE_DIR='/root/viridis-fleet/deploy/droplet'
ENV_FILE='/root/viridis-fleet/.env'
EVIDENCE_DIR='/root/viridis-candidates/bazaar-retention-20260804'
EXPECTED_X402_SHA='ca06a33a2da27cab1913684ceedce0a446907a9611cd8a065dcba021695b7524'

if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]; then
  echo 'refusing: exact Bazaar-retention promotion authorization required' >&2
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
  catalog="$RUN_DIR/catalog-$suffix.json"
  challenge="$RUN_DIR/scan-challenge-$suffix.json"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS https://mcp.viridisconservation.com/healthz > "$health"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS https://mcp.viridisconservation.com/x402/catalog > "$catalog"
  challenge_code=$(curl -sS -o "$challenge" -w '%{http_code}' \
    -H 'content-type: application/json' \
    --data-binary '{"jurisdiction":"US","sector":"energy","query":"45V clean energy tax credit emissions disclosure"}' \
    https://mcp.viridisconservation.com/x402/regulatory-radar/scan_regulations)
  [ "$challenge_code" = 402 ]
  python3 -c '
import json, sys
health, catalog = (json.load(open(path)) for path in sys.argv[1:3])
assert health["status"] == "ok"
assert len(health["agents"]) == 28
assert all(item.get("status") == "ok" for item in health["agents"].values())
routes = catalog["routes"]
assert len(routes) == 8
assert any(item["agent"] == "regulatory-radar" and item["tool"] == "monitor_changes" for item in routes)
' "$health" "$catalog"
}

module_probe() {
  docker exec "$LIVE_CONTAINER" python3 -B -c '
import sys
sys.path.insert(0, "/fleet/deploy/gateway")
import x402_http
out = x402_http._with_commerce_metadata(
    {"status": "success"}, "regulatory-radar", "scan_regulations",
    "https://mcp.viridisconservation.com")
offer = out["viridis_commerce"]["recommended_retention_offer"]
assert offer["agent"] == "regulatory-radar"
assert offer["tool"] == "monitor_changes"
assert offer["priority"] == 1
assert offer["auto_execute"] is False
assert offer["buyer_authorization_required"] is True
assert offer["quote"]["preflight_required"] is True
assert offer["quote"]["payer_hint_authorizes_payment"] is False
'
}

rollback_required=0
rollback() {
  trap - EXIT INT TERM
  echo 'promotion failed; restoring the pinned previous image' >&2
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG" || return 1
  compose_gateway || return 1
  wait_healthy "$PREVIOUS_IMAGE" || return 1
  public_probe rollback || return 1
  echo 'Bazaar-retention rollback verified' >&2
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
[ "$(docker run --rm --network none --read-only --entrypoint sha256sum "$CANDIDATE_IMAGE" /fleet/deploy/gateway/x402_http.py | awk '{print $1}')" = "$EXPECTED_X402_SHA" ]
public_probe before
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
module_probe
docker exec "$LIVE_CONTAINER" python3 \
  /fleet/deploy/gateway/gateway_state_backup.py verify \
  --backup /data/viridis_state.db > "$RUN_DIR/state-first-boot.json"

docker restart "$LIVE_CONTAINER" > "$RUN_DIR/restart-container-id.txt"
wait_healthy "$CANDIDATE_IMAGE"
public_probe restart
module_probe
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
echo "promotion verified: Bazaar retention offer ($RUN_ID)"
