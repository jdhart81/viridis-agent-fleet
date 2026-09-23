#!/bin/sh
# Exact production transaction for the eight-route fleet and durable paid-delivery receipts.

set -eu

EXPECTED_AUTH='authorize production promotion: fleet eight-route delivery 20260804'
PREVIOUS_IMAGE='sha256:b59caadfce0ef9234ff68eb62530730b96aff376c9a1d79d86367305803f4cc5'
CANDIDATE_IMAGE='sha256:5a5402b4c490c53cda9e28c0115fafc11a2bd60a11b6f85740764e39ae036f67'
CANDIDATE_TAG='viridis-stable:eight-route-delivery-exact-live-20260804'
ROLLBACK_TAG='viridis-stable:rollback-eight-route-delivery-20260804'
LATEST_TAG='viridis-stable:latest'
LIVE_CONTAINER='viridis-fleet-gateway-1'
COMPOSE_DIR='/root/viridis-fleet/deploy/droplet'
ENV_FILE='/root/viridis-fleet/.env'
EVIDENCE_DIR='/root/viridis-candidates/fleet-eight-route-delivery-20260804'
BACKUP_FILE="$EVIDENCE_DIR/viridis_state-20260804T154734Z.db"
BACKUP_MANIFEST="$EVIDENCE_DIR/viridis_state-20260804T154734Z.manifest.json"
BACKUP_SHA='2d9ce3009f608839a7dd886e7a63b86907eddd1d12622e44e043665fe92b36d6'
ARCHIVE="$EVIDENCE_DIR/viridis-eight-route-delivery-exact-live-20260804.tar.gz"
ARCHIVE_SHA='98267113daa4cbbfa52c510cc1770791993a3b8ee7de9975f33c316926e9dc63'
ARCHIVE_SIZE='63074543'
RUNTIME_PARITY="$EVIDENCE_DIR/gateway_runtime_parity.py"
BACKUP_TOOL="$COMPOSE_DIR/gateway_state_backup.py"
RUNTIME_PARITY_SHA='6b43fa30e510bb460ce137a6dc95b43e0df6f4287ba02ccda432f92c317dfc8b'
BACKUP_TOOL_SHA='a4d1ae3ae6959d3c2a9c2aca9a88b5359d9d7b9daa5ec2eca3df15c547b8a101'
EXPECTED_X402_SHA='a201431b5a3c0f55ae671e872914eb83878732af925fbbb6499ad090aa7ba8d9'
EXPECTED_A2A_SHA='433d0dd81ce7c3fc9de07bf07a92629acd244970063ea0829fc9d24638003c21'
EXPECTED_PAYMENT_SHA='0dd1d02f2841a1e682c3c6222c8f3c78e3eb92dbde24c7cae9b533ab77cdba95'
EXPECTED_STATE_SHA='6272581daa541f74f97e75f1f5cb663ff625ebdcc101e1a03518401783d89b9c'
EXPECTED_GATEWAY_SHA='143606e11beff81511d32b5ba3825ff28951f914d5cb8d0a9b917937657806a2'

if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]; then
  echo 'refusing: exact production-promotion authorization is required' >&2
  exit 64
fi

RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
RUN_DIR="$EVIDENCE_DIR/promotion-runs/$RUN_ID"
mkdir -p "$RUN_DIR"
RUNTIME_BEFORE="$RUN_DIR/runtime-before.json"
RUNTIME_CANDIDATE="$RUN_DIR/runtime-candidate.json"
RUNTIME_RESTART="$RUN_DIR/runtime-restart.json"
RUNTIME_ROLLBACK="$RUN_DIR/runtime-rollback.json"

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

public_candidate_probe() {
  suffix=$1
  health="$RUN_DIR/public-health-$suffix.json"
  catalog="$RUN_DIR/public-catalog-$suffix.json"
  card="$RUN_DIR/public-agent-card-$suffix.json"
  watch="$RUN_DIR/public-watch-$suffix.json"
  security="$RUN_DIR/public-security-$suffix.json"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS https://mcp.viridisconservation.com/healthz > "$health"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS https://mcp.viridisconservation.com/x402/catalog > "$catalog"
  curl --retry 8 --retry-delay 2 --retry-connrefused --retry-all-errors \
    -fsS https://mcp.viridisconservation.com/.well-known/agent-card.json > "$card"
  watch_code=$(curl -sS -o "$watch" -w '%{http_code}' \
    -H 'content-type: application/json' \
    --data-binary '{"jurisdiction":"US","topics":["emissions","climate"],"lookback_days":90}' \
    https://mcp.viridisconservation.com/x402/regulatory-radar/monitor_changes)
  security_code=$(curl -sS -o "$security" -w '%{http_code}' \
    -H 'content-type: application/json' \
    --data-binary '{"agent_id":"example-research-agent","manifest":{"endpoint":"https://agent.example/mcp","auth":"bearer","tools":[]}}' \
    https://mcp.viridisconservation.com/x402/security-preflight/security_preflight)
  printf 'watch=%s\nsecurity=%s\n' "$watch_code" "$security_code" \
    > "$RUN_DIR/public-payment-challenges-$suffix.txt"
  [ "$watch_code" = 402 ]
  [ "$security_code" = 402 ]
  python3 -c '
import json, sys
h, c, a = (json.load(open(path)) for path in sys.argv[1:4])
assert h["status"] == "ok"
assert len(h["agents"]) == 28
assert all(item.get("status") == "ok" for item in h["agents"].values())
assert h["agents"]["hive"]["checks"]["solver_provider_ready"] is True
routes = c["routes"]
skills = a["skills"]
assert len(routes) == 8 and len(skills) == 8
route_ids = {item["agent"] + "." + item["tool"] for item in routes}
skill_ids = {item["id"] for item in skills}
required = {"regulatory-radar.monitor_changes", "security-preflight.security_preflight"}
assert required <= route_ids and required <= skill_ids
assert a["description"].startswith("Eight paid skills")
' "$health" "$catalog" "$card"
  docker exec "$LIVE_CONTAINER" python3 -c '
import sys
sys.path.insert(0, "/fleet/deploy/gateway")
import x402_http
assert x402_http.PAID_DELIVERY_RECEIPT_VERSION == "viridis-paid-delivery-v1"
assert x402_http.PAID_DELIVERY_RECEIPT_FIELD == "viridis_delivery"
'
}

rollback_required=0
rollback() {
  trap - EXIT INT TERM
  echo 'promotion failed; restoring the pinned previous image' >&2
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG" || return 1
  compose_gateway || return 1
  wait_healthy "$PREVIOUS_IMAGE" || return 1
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG" || return 1
  [ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$PREVIOUS_IMAGE" ]
  python3 "$RUNTIME_PARITY" capture \
    --container "$LIVE_CONTAINER" --expected-image "$PREVIOUS_IMAGE" \
    --output "$RUNTIME_ROLLBACK" || return 1
  python3 "$RUNTIME_PARITY" compare \
    --before "$RUNTIME_BEFORE" --after "$RUNTIME_ROLLBACK" || return 1
  curl -fsS https://mcp.viridisconservation.com/healthz \
    > "$RUN_DIR/public-health-rollback.json" || return 1
  echo 'fleet rollback verified' >&2
}

on_exit() {
  status=$1
  trap - EXIT INT TERM
  if [ "$status" -ne 0 ] && [ "$rollback_required" -eq 1 ]; then
    if ! rollback; then
      echo 'CRITICAL: automatic fleet rollback did not verify' >&2
      exit 70
    fi
  fi
  exit "$status"
}
trap 'on_exit $?' EXIT
trap 'exit 130' INT TERM

available_mib=$(awk '/MemAvailable:/ {printf "%d", $2/1024}' /proc/meminfo)
docker_available_bytes=$(df --output=avail -B1 /var/lib/docker | tail -1 | tr -d ' ')
[ "$available_mib" -ge 800 ]
[ "$docker_available_bytes" -ge 2147483648 ]
[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" = "$PREVIOUS_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$PREVIOUS_IMAGE" ]
[ "$(docker image inspect --format '{{.Id}}' "$CANDIDATE_TAG")" = "$CANDIDATE_IMAGE" ]
[ -z "$(docker ps -a --filter name=viridis-candidate-eight-route-delivery-20260804 --format '{{.Names}}')" ]
[ "$(sha256sum "$ARCHIVE" | awk '{print $1}')" = "$ARCHIVE_SHA" ]
[ "$(stat -c %s "$ARCHIVE")" = "$ARCHIVE_SIZE" ]
gzip -t "$ARCHIVE"
[ "$(sha256sum "$RUNTIME_PARITY" | awk '{print $1}')" = "$RUNTIME_PARITY_SHA" ]
[ "$(sha256sum "$BACKUP_TOOL" | awk '{print $1}')" = "$BACKUP_TOOL_SHA" ]

python3 "$BACKUP_TOOL" verify \
  --backup "$BACKUP_FILE" --manifest "$BACKUP_MANIFEST" \
  > "$RUN_DIR/backup-verify.json"
python3 -c '
import datetime as dt, json, sys
verify = json.load(open(sys.argv[1]))
manifest = json.load(open(sys.argv[2]))
assert verify["status"] == "ok" and verify["integrity_check"] == "ok"
assert verify["agent_state_rows"] == 35
assert verify["sha256"] == sys.argv[3] == manifest["sha256"]
created = dt.datetime.fromisoformat(manifest["created_at"])
assert dt.datetime.now(dt.timezone.utc) - created < dt.timedelta(hours=2)
' "$RUN_DIR/backup-verify.json" "$BACKUP_MANIFEST" "$BACKUP_SHA"

docker run --rm --network none --read-only --memory=256m --memory-swap=256m \
  --entrypoint sha256sum "$CANDIDATE_IMAGE" \
  /fleet/deploy/gateway/x402_http.py \
  /fleet/deploy/gateway/a2a_commerce.py \
  /fleet/deploy/gateway/payment_gate.py \
  /fleet/deploy/gateway/state_store.py \
  /fleet/deploy/gateway/viridis_mcp_gateway.py \
  > "$RUN_DIR/candidate-source-sha256.txt"
[ "$(awk '$2=="/fleet/deploy/gateway/x402_http.py"{print $1}' "$RUN_DIR/candidate-source-sha256.txt")" = "$EXPECTED_X402_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/a2a_commerce.py"{print $1}' "$RUN_DIR/candidate-source-sha256.txt")" = "$EXPECTED_A2A_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/payment_gate.py"{print $1}' "$RUN_DIR/candidate-source-sha256.txt")" = "$EXPECTED_PAYMENT_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/state_store.py"{print $1}' "$RUN_DIR/candidate-source-sha256.txt")" = "$EXPECTED_STATE_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/viridis_mcp_gateway.py"{print $1}' "$RUN_DIR/candidate-source-sha256.txt")" = "$EXPECTED_GATEWAY_SHA" ]

python3 "$RUNTIME_PARITY" capture \
  --container "$LIVE_CONTAINER" --expected-image "$PREVIOUS_IMAGE" \
  --output "$RUNTIME_BEFORE"
docker tag "$PREVIOUS_IMAGE" "$ROLLBACK_TAG"
[ "$(docker image inspect --format '{{.Id}}' "$ROLLBACK_TAG")" = "$PREVIOUS_IMAGE" ]

rollback_required=1
docker tag "$CANDIDATE_IMAGE" "$LATEST_TAG"
compose_gateway
wait_healthy "$CANDIDATE_IMAGE"
public_candidate_probe first-boot
docker exec "$LIVE_CONTAINER" python3 \
  /fleet/deploy/gateway/gateway_state_backup.py verify \
  --backup /data/viridis_state.db > "$RUN_DIR/live-state-first-boot.json"
python3 "$RUNTIME_PARITY" capture \
  --container "$LIVE_CONTAINER" --expected-image "$CANDIDATE_IMAGE" \
  --output "$RUNTIME_CANDIDATE"
python3 "$RUNTIME_PARITY" compare --before "$RUNTIME_BEFORE" --after "$RUNTIME_CANDIDATE"

docker restart "$LIVE_CONTAINER" > "$RUN_DIR/restart-container-id.txt"
wait_healthy "$CANDIDATE_IMAGE"
public_candidate_probe restart
python3 "$RUNTIME_PARITY" capture \
  --container "$LIVE_CONTAINER" --expected-image "$CANDIDATE_IMAGE" \
  --output "$RUNTIME_RESTART"
python3 "$RUNTIME_PARITY" compare --before "$RUNTIME_BEFORE" --after "$RUNTIME_RESTART"

[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" = "$CANDIDATE_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$CANDIDATE_IMAGE" ]
docker inspect "$LIVE_CONTAINER" > "$RUN_DIR/final-container-inspect.json"
sha256sum "$RUN_DIR"/* > "$RUN_DIR/evidence.sha256"

rollback_required=0
trap - EXIT INT TERM
echo "promotion verified: fleet eight-route delivery receipts ($RUN_ID)"
