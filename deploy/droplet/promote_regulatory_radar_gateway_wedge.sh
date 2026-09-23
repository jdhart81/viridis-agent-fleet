#!/bin/sh
# Exact-scope production transaction for the Regulatory Radar gateway wedge.
# This script does not back up state; the runbook's fresh verified off-host
# backup gate must pass before it is invoked.

set -eu

EXPECTED_AUTH='authorize production promotion: Regulatory Radar gateway wedge'
PREVIOUS_IMAGE='sha256:6e9828e6302bf38957731d5f695202749f4e6732ddb915b06ca43ea618dd6695'
CANDIDATE_IMAGE='sha256:fc6cd0c3622811a7d6f821f7d488597fa6ad1bf781d25e1190dde3181b041309'
CANDIDATE_TAG='viridis-stable:regulatory-radar-wedge-gateway-candidate-20260726'
ROLLBACK_TAG='viridis-stable:rollback-regulatory-radar-gateway-wedge-20260726'
LATEST_TAG='viridis-stable:latest'
LIVE_CONTAINER='viridis-fleet-gateway-1'
COMPOSE_DIR='/root/viridis-fleet/deploy/droplet'
ENV_FILE='/root/viridis-fleet/.env'
EVIDENCE_DIR=${VIRIDIS_PROMOTION_EVIDENCE_DIR:-'/root/viridis-candidates/regulatory-radar-gateway-wedge'}
CANDIDATE_PROBE_SHA='c825ca9068ded02eb2bac2429087d96151e55093c0ee8d51ab868df8be61e04a'
PUBLIC_PROBE_SHA='3b7bbd923bc331ffbc8edd895b1e401050f267c8e7b135a40ef5c1d3c5b98470'
BACKUP_GATE_SHA='abf5c5738adfd5c8d1e6fe13cdac05da1b167125b7fb2b87d504b6d143837d3b'
MARGIN_GATE_SHA='210d5410aa4e50997de90a5aa97791643fdb5a94a564e1324d6bf3e00ec208d3'
MARGIN_CONTRACT_SHA='09b212cb569f835d7ce1ffc6b921f56a9201ac5af45b5b46c58fdc585909765f'
RUNTIME_PARITY_SHA='7c907daba1264bb26de0da6803f85a7bdbf55ffaec484bac12729da421bd87d3'
BACKUP_FILE="$EVIDENCE_DIR/runs/20260727T044427Z/viridis_state-20260727T044427Z.db"
BACKUP_MANIFEST="$EVIDENCE_DIR/runs/20260727T044427Z/viridis_state-20260727T044427Z.manifest.json"
RUNTIME_BEFORE="$EVIDENCE_DIR/runtime-before-promotion.json"
RUNTIME_CANDIDATE="$EVIDENCE_DIR/runtime-candidate-promotion.json"
RUNTIME_ROLLBACK="$EVIDENCE_DIR/runtime-rollback-promotion.json"
BACKUP_SHA='2cf022ea6f640aebd3814271bc059b7df9fb08ac3b11fbd463516aa994bcbe68'
MIN_AVAILABLE_MIB=320
MIN_DOCKER_AVAILABLE_BYTES=2147483648

if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]; then
  echo "refusing: exact production-promotion authorization is required" >&2
  exit 64
fi

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
  while [ "$attempts" -lt 30 ]; do
    running_image=$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")
    health=$(docker inspect \
      --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")
    if [ "$running_image" = "$expected_image" ] && [ "$health" = healthy ]; then
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 2
  done
  echo "gateway did not reach the exact healthy image in 60 seconds" >&2
  return 1
}

rollback_required=0
rollback() {
  trap - EXIT INT TERM
  echo "promotion failed; restoring the pinned previous image" >&2
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG"
  compose_gateway
  wait_healthy "$PREVIOUS_IMAGE"
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG"
  [ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" \
    = "$PREVIOUS_IMAGE" ]
  python3 "$EVIDENCE_DIR/gateway_runtime_parity.py" capture \
    --container "$LIVE_CONTAINER" \
    --expected-image "$PREVIOUS_IMAGE" \
    --output "$RUNTIME_ROLLBACK"
  python3 "$EVIDENCE_DIR/gateway_runtime_parity.py" compare \
    --before "$RUNTIME_BEFORE" \
    --after "$RUNTIME_ROLLBACK"
  echo "rollback verified" >&2
}

on_exit() {
  status=$1
  trap - EXIT INT TERM
  if [ "$status" -ne 0 ] && [ "$rollback_required" -eq 1 ]; then
    if ! rollback; then
      echo "CRITICAL: automatic rollback did not verify" >&2
      exit 70
    fi
  fi
  exit "$status"
}
trap 'on_exit $?' EXIT
trap 'exit 130' INT TERM

available_mib=$(awk '/MemAvailable:/ {printf "%d", $2/1024}' /proc/meminfo)
docker_available_bytes=$(
  df --output=avail -B1 /var/lib/docker | tail -1 | tr -d ' '
)
[ "$available_mib" -ge "$MIN_AVAILABLE_MIB" ]
[ "$docker_available_bytes" -ge "$MIN_DOCKER_AVAILABLE_BYTES" ]

[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" \
  = "$PREVIOUS_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" \
  = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" \
  = "$PREVIOUS_IMAGE" ]
[ "$(docker image inspect --format '{{.Id}}' "$CANDIDATE_TAG")" \
  = "$CANDIDATE_IMAGE" ]
[ "$(docker image inspect --format '{{.Id}}' "$CANDIDATE_IMAGE")" \
  = "$CANDIDATE_IMAGE" ]
[ -z "$(docker ps -a \
  --filter name=viridis-radar-gateway-wedge-candidate \
  --format '{{.Names}}')" ]
[ "$(sha256sum "$EVIDENCE_DIR/regulatory_radar_wedge_probe.py" \
  | awk '{print $1}')" = "$CANDIDATE_PROBE_SHA" ]
[ "$(sha256sum "$EVIDENCE_DIR/regulatory_radar_wedge_public_probe.py" \
  | awk '{print $1}')" = "$PUBLIC_PROBE_SHA" ]
[ "$(sha256sum "$EVIDENCE_DIR/regulatory_radar_promotion_backup_gate.py" \
  | awk '{print $1}')" = "$BACKUP_GATE_SHA" ]
[ "$(sha256sum "$EVIDENCE_DIR/regulatory_radar_margin_gate.py" \
  | awk '{print $1}')" = "$MARGIN_GATE_SHA" ]
[ "$(sha256sum "$EVIDENCE_DIR/commercial_contract.json" \
  | awk '{print $1}')" = "$MARGIN_CONTRACT_SHA" ]
[ "$(sha256sum "$EVIDENCE_DIR/gateway_runtime_parity.py" \
  | awk '{print $1}')" = "$RUNTIME_PARITY_SHA" ]

python3 "$EVIDENCE_DIR/regulatory_radar_promotion_backup_gate.py" \
  --backup "$BACKUP_FILE" \
  --manifest "$BACKUP_MANIFEST" \
  --expected-sha256 "$BACKUP_SHA" \
  --minimum-rows 34 \
  --maximum-age-hours 25 \
  > "$EVIDENCE_DIR/backup-promotion-gate.json"

python3 "$EVIDENCE_DIR/regulatory_radar_margin_gate.py" \
  --contract "$EVIDENCE_DIR/commercial_contract.json" \
  --source-dir /root/viridis-fleet/regulatory-radar-agent/src \
  --health-url https://mcp.viridisconservation.com/healthz \
  > "$EVIDENCE_DIR/margin-promotion-gate.json"

python3 "$EVIDENCE_DIR/gateway_runtime_parity.py" capture \
  --container "$LIVE_CONTAINER" \
  --expected-image "$PREVIOUS_IMAGE" \
  --output "$RUNTIME_BEFORE"

docker tag "$PREVIOUS_IMAGE" "$ROLLBACK_TAG"
[ "$(docker image inspect --format '{{.Id}}' "$ROLLBACK_TAG")" \
  = "$PREVIOUS_IMAGE" ]

rollback_required=1
docker tag "$CANDIDATE_IMAGE" "$LATEST_TAG"
compose_gateway
wait_healthy "$CANDIDATE_IMAGE"

python3 "$EVIDENCE_DIR/regulatory_radar_wedge_public_probe.py" \
  --base https://mcp.viridisconservation.com \
  --intro-state enabled \
  > "$EVIDENCE_DIR/probe-public-promotion.json"

python3 "$EVIDENCE_DIR/gateway_runtime_parity.py" capture \
  --container "$LIVE_CONTAINER" \
  --expected-image "$CANDIDATE_IMAGE" \
  --output "$RUNTIME_CANDIDATE"
python3 "$EVIDENCE_DIR/gateway_runtime_parity.py" compare \
  --before "$RUNTIME_BEFORE" \
  --after "$RUNTIME_CANDIDATE"

[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" \
  = "$CANDIDATE_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" \
  = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" \
  = "$CANDIDATE_IMAGE" ]

rollback_required=0
trap - EXIT INT TERM
echo "promotion verified: Regulatory Radar gateway wedge"
