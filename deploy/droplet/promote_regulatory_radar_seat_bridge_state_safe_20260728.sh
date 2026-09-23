#!/bin/sh
# Exact production transaction for the Regulatory Radar paid-success seat bridge.
# Prepared and tested, but inert without the exact one-time approval argument.

set -eu

EXPECTED_AUTH='authorize production promotion: Regulatory Radar paid-success seat bridge 28-agent copied-state-safe refresh'
PREVIOUS_IMAGE='sha256:9dc219f22d78e8a3e2e199a62c90143468536b248b90c91f5c31a0531d5c717c'
CANDIDATE_IMAGE='sha256:52776a3fd3963d2761de74390dbf63d10826fa258488d024357a7dd6c3c55c77'
CANDIDATE_CONFIG='sha256:f4c034e25d6a2725f84d3be3a635971dfa1127626393628aeedc85401e93f0f0'
CANDIDATE_TAG='viridis-stable:regulatory-radar-seat-bridge-copied-state-safe-candidate-20260728'
ROLLBACK_TAG='viridis-stable:rollback-regulatory-radar-seat-bridge-state-safe-20260728'
LATEST_TAG='viridis-stable:latest'
LIVE_CONTAINER='viridis-fleet-gateway-1'
COMPOSE_DIR='/root/viridis-fleet/deploy/droplet'
ENV_FILE='/root/viridis-fleet/.env'
EVIDENCE_DIR=${VIRIDIS_SEAT_BRIDGE_PROMOTION_EVIDENCE_DIR:-'/root/viridis-candidates/regulatory-radar-seat-bridge-state-safe-20260728T162608Z'}
ARCHIVE="$EVIDENCE_DIR/gateway-candidate.tar.gz"
ARCHIVE_SHA='8ef0c660302986f153754f1262b5def1ec8eadc5c2a8ff333a7e2d50ea2f99ca'
ARCHIVE_SIZE=62690048
PRODUCTION_PROBE="$EVIDENCE_DIR/regulatory_radar_seat_bridge_production_probe_20260728.py"
PRODUCTION_PROBE_SHA='310e30335e357d09dfbee149655e1a2aedaaebfa95ec9b45e386050289778135'
ROLLBACK_GATE="$EVIDENCE_DIR/regulatory_radar_seat_bridge_rollback_gate_20260728.py"
ROLLBACK_GATE_SHA='7cc5efa53c2c7f16a5ed62999ac5db191e8ba50e50a76eeda3cfc77d615b2e41'
BACKUP_GATE="$EVIDENCE_DIR/regulatory_radar_promotion_backup_gate.py"
BACKUP_GATE_SHA='abf5c5738adfd5c8d1e6fe13cdac05da1b167125b7fb2b87d504b6d143837d3b'
MARGIN_GATE="$EVIDENCE_DIR/regulatory_radar_margin_gate.py"
MARGIN_GATE_SHA='210d5410aa4e50997de90a5aa97791643fdb5a94a564e1324d6bf3e00ec208d3'
MARGIN_CONTRACT="$EVIDENCE_DIR/commercial_contract.json"
MARGIN_CONTRACT_SHA='09b212cb569f835d7ce1ffc6b921f56a9201ac5af45b5b46c58fdc585909765f'
RUNTIME_PARITY="$EVIDENCE_DIR/gateway_runtime_parity.py"
RUNTIME_PARITY_SHA='7c907daba1264bb26de0da6803f85a7bdbf55ffaec484bac12729da421bd87d3'
OCI_BINDING="$EVIDENCE_DIR/verify_candidate_oci_binding.py"
OCI_BINDING_SHA='48f4519462b071ec17a53de0e3a5e4fd31dfcfb920d861367966b607d7bee585'
BACKUP_FILE="$EVIDENCE_DIR/viridis_state-20260728T171822Z.db"
BACKUP_MANIFEST="$EVIDENCE_DIR/viridis_state-20260728T171822Z.manifest.json"
BACKUP_SHA='66e45129f51a36411e0f4ad798271728dcb5199ed32ce06090ce117147f47aed'
ROLLBACK_COMPAT_DIR="$EVIDENCE_DIR/rollback-compat"
ROLLBACK_SNAPSHOT="$ROLLBACK_COMPAT_DIR/snapshot-compatibility.json"
ROLLBACK_SNAPSHOT_SHA='3fdd0fd7ceb50812b6a7eadafa3eea9780f43e371393d755b0407da0c5acabec'
ROLLBACK_HEALTH="$ROLLBACK_COMPAT_DIR/old-image-loopback-health.json"
ROLLBACK_HEALTH_SHA='d0857778e649bc6f1f02491860c9d416ef54495a0847cabb5e696c915b5c11a7'
ROLLBACK_FINAL_STATE="$ROLLBACK_COMPAT_DIR/final-state.json"
ROLLBACK_FINAL_STATE_SHA='f0910fd99bbd6ddbdf729ad2a050620bc6c231847275086a5ba48caa6528c5a3'
ROLLBACK_SOURCE_BEFORE="$ROLLBACK_COMPAT_DIR/source-before.sha256"
ROLLBACK_SOURCE_BEFORE_SHA='0fcf516b9713199463ffb86c26f445d0e8341a9cca1f66802c3378e937a4c677'
ROLLBACK_SOURCE_AFTER="$ROLLBACK_COMPAT_DIR/source-after.sha256"
ROLLBACK_SOURCE_AFTER_SHA='0fcf516b9713199463ffb86c26f445d0e8341a9cca1f66802c3378e937a4c677'
EXPECTED_X402_HTTP_SHA='33d0b79f19171f7f1ff89d92b41f4f0995a61592957720fb3a2c156628c2b980'
EXPECTED_PAYMENT_GATE_SHA='99990768fc1526fb520df20596b4fb3a3096efac44b4f93bb30ca8a3890e244f'
EXPECTED_STATE_STORE_SHA='e34b2c1bd9a0618e59e8864bacae2e1fd10404ddc41e60b4beb61bceaf7ccc73'
EXPECTED_GATEWAY_SHA='22c343594ee26db8d391ca67ef6a42306df6eaa8baf0d99f4e9f73c3d6806bec'
EXPECTED_SECURITY_SHA='d0363968474aacc5f816bd6f87a284d3620f8df5eb96e54030cc78e119a9034a'
MIN_AVAILABLE_MIB=320
MIN_DOCKER_AVAILABLE_BYTES=2147483648

if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]; then
  echo "refusing: exact seat-bridge production authorization is required" >&2
  exit 64
fi

run_stamp=$(date -u +%Y%m%dT%H%M%SZ)
RUN_DIR="$EVIDENCE_DIR/promotion-runs/$run_stamp"
umask 077
mkdir -p "$EVIDENCE_DIR/promotion-runs"
mkdir "$RUN_DIR"

RUNTIME_BEFORE="$RUN_DIR/runtime-before.json"
RUNTIME_CANDIDATE="$RUN_DIR/runtime-candidate.json"
RUNTIME_RESTART="$RUN_DIR/runtime-restart.json"
RUNTIME_ROLLBACK="$RUN_DIR/runtime-rollback.json"
PUBLIC_BEFORE="$RUN_DIR/public-before.json"
PUBLIC_CANDIDATE="$RUN_DIR/public-candidate.json"
PUBLIC_RESTART="$RUN_DIR/public-restart.json"
PUBLIC_ROLLBACK="$RUN_DIR/public-rollback.json"

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
    running_image=$(
      docker inspect --format '{{.Image}}' "$LIVE_CONTAINER" 2>/dev/null || true
    )
    health=$(
      docker inspect --format '{{.State.Health.Status}}' \
        "$LIVE_CONTAINER" 2>/dev/null || true
    )
    if [ "$running_image" = "$expected_image" ] && [ "$health" = healthy ]; then
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 2
  done
  echo "gateway did not reach the exact healthy image in 90 seconds" >&2
  return 1
}

runtime_probe() {
  output=$1
  docker exec -i "$LIVE_CONTAINER" \
    python3 - runtime --base http://127.0.0.1:8402 \
    < "$PRODUCTION_PROBE" > "$output"
}

public_verify() {
  output=$1
  python3 "$PRODUCTION_PROBE" public-verify \
    --base https://mcp.viridisconservation.com \
    --baseline "$PUBLIC_BEFORE" > "$output"
}

rollback_required=0
rollback() {
  trap - EXIT INT TERM
  echo "seat-bridge promotion failed; restoring the pinned previous image" >&2
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG" || return 1
  compose_gateway || return 1
  wait_healthy "$PREVIOUS_IMAGE" || return 1
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG" || return 1
  [ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" \
    = "$PREVIOUS_IMAGE" ] || return 1
  [ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" \
    = "$PREVIOUS_IMAGE" ] || return 1
  python3 "$RUNTIME_PARITY" capture \
    --container "$LIVE_CONTAINER" \
    --expected-image "$PREVIOUS_IMAGE" \
    --output "$RUNTIME_ROLLBACK" || return 1
  python3 "$RUNTIME_PARITY" compare \
    --before "$RUNTIME_BEFORE" \
    --after "$RUNTIME_ROLLBACK" || return 1
  public_verify "$PUBLIC_ROLLBACK" || return 1
  echo "seat-bridge rollback verified" >&2
  return 0
}

on_exit() {
  status=$1
  trap - EXIT INT TERM
  if [ "$status" -ne 0 ] && [ "$rollback_required" -eq 1 ]; then
    if ! rollback; then
      echo "CRITICAL: automatic seat-bridge rollback did not verify" >&2
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
[ "$(docker image inspect --format '{{.Architecture}}/{{.Os}}' \
  "$CANDIDATE_IMAGE")" = amd64/linux ]
[ -z "$(docker ps -a \
  --filter name=viridis-radar-seat-bridge \
  --format '{{.Names}}')" ]

for pinned in \
  "$PRODUCTION_PROBE:$PRODUCTION_PROBE_SHA" \
  "$ROLLBACK_GATE:$ROLLBACK_GATE_SHA" \
  "$BACKUP_GATE:$BACKUP_GATE_SHA" \
  "$MARGIN_GATE:$MARGIN_GATE_SHA" \
  "$MARGIN_CONTRACT:$MARGIN_CONTRACT_SHA" \
  "$RUNTIME_PARITY:$RUNTIME_PARITY_SHA" \
  "$OCI_BINDING:$OCI_BINDING_SHA"
do
  path=${pinned%:*}
  expected=${pinned##*:}
  [ "$(sha256sum "$path" | awk '{print $1}')" = "$expected" ]
done

python3 "$OCI_BINDING" \
  --archive "$ARCHIVE" \
  --archive-sha256 "$ARCHIVE_SHA" \
  --size-bytes "$ARCHIVE_SIZE" \
  --manifest-digest "$CANDIDATE_IMAGE" \
  --config-digest "$CANDIDATE_CONFIG" \
  --tag "$CANDIDATE_TAG" \
  > "$RUN_DIR/oci-binding.json"

python3 "$ROLLBACK_GATE" \
  --snapshot "$ROLLBACK_SNAPSHOT" \
  --health "$ROLLBACK_HEALTH" \
  --final-state "$ROLLBACK_FINAL_STATE" \
  --source-before "$ROLLBACK_SOURCE_BEFORE" \
  --source-after "$ROLLBACK_SOURCE_AFTER" \
  --snapshot-sha256 "$ROLLBACK_SNAPSHOT_SHA" \
  --health-sha256 "$ROLLBACK_HEALTH_SHA" \
  --final-state-sha256 "$ROLLBACK_FINAL_STATE_SHA" \
  --source-before-sha256 "$ROLLBACK_SOURCE_BEFORE_SHA" \
  --source-after-sha256 "$ROLLBACK_SOURCE_AFTER_SHA" \
  > "$RUN_DIR/rollback-compatibility-gate.json"

python3 "$BACKUP_GATE" \
  --backup "$BACKUP_FILE" \
  --manifest "$BACKUP_MANIFEST" \
  --expected-sha256 "$BACKUP_SHA" \
  --minimum-rows 35 \
  --maximum-age-hours 25 \
  > "$RUN_DIR/backup-promotion-gate.json"

python3 "$MARGIN_GATE" \
  --contract "$MARGIN_CONTRACT" \
  --source-dir /root/viridis-fleet/regulatory-radar-agent/src \
  --health-url https://mcp.viridisconservation.com/healthz \
  > "$RUN_DIR/margin-promotion-gate.json"

docker run --rm --network none --read-only \
  --entrypoint sha256sum "$CANDIDATE_IMAGE" \
  /fleet/deploy/gateway/x402_http.py \
  /fleet/deploy/gateway/payment_gate.py \
  /fleet/deploy/gateway/state_store.py \
  /fleet/deploy/gateway/viridis_mcp_gateway.py \
  /fleet/security-preflight-agent/src/core.py \
  > "$RUN_DIR/candidate-source-sha256.txt"
[ "$(awk '$2=="/fleet/deploy/gateway/x402_http.py"{print $1}' \
  "$RUN_DIR/candidate-source-sha256.txt")" = "$EXPECTED_X402_HTTP_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/payment_gate.py"{print $1}' \
  "$RUN_DIR/candidate-source-sha256.txt")" = "$EXPECTED_PAYMENT_GATE_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/state_store.py"{print $1}' \
  "$RUN_DIR/candidate-source-sha256.txt")" = "$EXPECTED_STATE_STORE_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/viridis_mcp_gateway.py"{print $1}' \
  "$RUN_DIR/candidate-source-sha256.txt")" = "$EXPECTED_GATEWAY_SHA" ]
[ "$(awk '$2=="/fleet/security-preflight-agent/src/core.py"{print $1}' \
  "$RUN_DIR/candidate-source-sha256.txt")" = "$EXPECTED_SECURITY_SHA" ]

python3 "$PRODUCTION_PROBE" public-capture \
  --base https://mcp.viridisconservation.com > "$PUBLIC_BEFORE"
python3 "$RUNTIME_PARITY" capture \
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
runtime_probe "$RUN_DIR/runtime-probe-first-boot.json"
public_verify "$PUBLIC_CANDIDATE"
python3 "$RUNTIME_PARITY" capture \
  --container "$LIVE_CONTAINER" \
  --expected-image "$CANDIDATE_IMAGE" \
  --output "$RUNTIME_CANDIDATE"
python3 "$RUNTIME_PARITY" compare \
  --before "$RUNTIME_BEFORE" \
  --after "$RUNTIME_CANDIDATE"

docker restart "$LIVE_CONTAINER" > "$RUN_DIR/restart-container-id.txt"
wait_healthy "$CANDIDATE_IMAGE"
runtime_probe "$RUN_DIR/runtime-probe-restart.json"
public_verify "$PUBLIC_RESTART"
python3 "$RUNTIME_PARITY" capture \
  --container "$LIVE_CONTAINER" \
  --expected-image "$CANDIDATE_IMAGE" \
  --output "$RUNTIME_RESTART"
python3 "$RUNTIME_PARITY" compare \
  --before "$RUNTIME_BEFORE" \
  --after "$RUNTIME_RESTART"

[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" \
  = "$CANDIDATE_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" \
  = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" \
  = "$CANDIDATE_IMAGE" ]
docker inspect "$LIVE_CONTAINER" > "$RUN_DIR/final-container-inspect.json"
sha256sum "$RUN_DIR"/* > "$RUN_DIR/evidence.sha256"

rollback_required=0
trap - EXIT INT TERM
echo "promotion verified: Regulatory Radar paid-success seat bridge"
