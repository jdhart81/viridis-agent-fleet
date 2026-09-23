#!/bin/sh
# Build and inspect one non-serving static-page candidate from the exact live image.

set -eu

EXPECTED_AUTH='authorize non-serving candidate: security preflight conversion 20260806'
EXPECTED_LIVE_IMAGE='sha256:4d465097726f8ca0c50eaf90559df0669be2a36715b24b7e06be2aa1556846ed'
BASE_TAG='viridis-stable:gold402-listing-20260804'
LATEST_TAG='viridis-stable:latest'
CANDIDATE_TAG='viridis-stable:security-preflight-conversion-20260806-candidate'
LIVE_CONTAINER='viridis-fleet-gateway-1'
EVIDENCE_DIR='/root/viridis-candidates/security-preflight-conversion-20260806'
CONTEXT="$EVIDENCE_DIR/build-context"
DOCKERFILE="$CONTEXT/deploy/gateway/Dockerfile.security-preflight-conversion-candidate-20260806"
AGENTS="$CONTEXT/deploy/gateway/agents.html"
QUICKSTART="$CONTEXT/deploy/gateway/quickstart.html"
BACKUP="$EVIDENCE_DIR/state-backup/viridis_state-20260806T194815Z.db"
BACKUP_MANIFEST="$EVIDENCE_DIR/state-backup/viridis_state-20260806T194815Z.manifest.json"
EXPECTED_AGENTS_SHA='089d60fec369597cd5356740fab9cafe24c0097237236290d9473045a7dc9be5'
EXPECTED_QUICKSTART_SHA='3ea80610cbc8b74d971d1b91841fbd34bfc8fa68691071f379baace1f19dd2fc'
EXPECTED_BACKUP_SHA='9f70148d95cc4ac417a5102f4fbdda5d51c2ad19330d506d7839039e29b0f0a1'

if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]; then
  echo 'refusing: exact non-serving-candidate authorization required' >&2
  exit 64
fi

[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" = "$EXPECTED_LIVE_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$EXPECTED_LIVE_IMAGE" ]
[ "$(docker image inspect --format '{{.Id}}' "$BASE_TAG")" = "$EXPECTED_LIVE_IMAGE" ]
[ -f "$DOCKERFILE" ]
[ "$(sha256sum "$AGENTS" | awk '{print $1}')" = "$EXPECTED_AGENTS_SHA" ]
[ "$(sha256sum "$QUICKSTART" | awk '{print $1}')" = "$EXPECTED_QUICKSTART_SHA" ]
[ "$(sha256sum "$BACKUP" | awk '{print $1}')" = "$EXPECTED_BACKUP_SHA" ]
python3 "$CONTEXT/deploy/droplet/gateway_state_backup.py" verify \
  --backup "$BACKUP" --manifest "$BACKUP_MANIFEST" \
  > "$EVIDENCE_DIR/state-backup-verify.json"

docker build --pull=false --no-cache \
  --build-arg "BASE_IMAGE=$BASE_TAG" \
  --file "$DOCKERFILE" --tag "$CANDIDATE_TAG" "$CONTEXT" \
  > "$EVIDENCE_DIR/candidate-build.log"
CANDIDATE_IMAGE=$(docker image inspect --format '{{.Id}}' "$CANDIDATE_TAG")
[ "$CANDIDATE_IMAGE" != "$EXPECTED_LIVE_IMAGE" ]

docker run --rm --network none --read-only --entrypoint sha256sum \
  "$CANDIDATE_IMAGE" \
  /fleet/deploy/gateway/agents.html \
  /fleet/deploy/gateway/quickstart.html \
  > "$EVIDENCE_DIR/candidate-source-sha256.txt"
[ "$(awk '$2=="/fleet/deploy/gateway/agents.html"{print $1}' "$EVIDENCE_DIR/candidate-source-sha256.txt")" = "$EXPECTED_AGENTS_SHA" ]
[ "$(awk '$2=="/fleet/deploy/gateway/quickstart.html"{print $1}' "$EVIDENCE_DIR/candidate-source-sha256.txt")" = "$EXPECTED_QUICKSTART_SHA" ]
[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER")" = "$EXPECTED_LIVE_IMAGE" ]
[ "$(docker inspect --format '{{.State.Health.Status}}' "$LIVE_CONTAINER")" = healthy ]
[ "$(docker image inspect --format '{{.Id}}' "$LATEST_TAG")" = "$EXPECTED_LIVE_IMAGE" ]

printf '%s\n' "$CANDIDATE_IMAGE" > "$EVIDENCE_DIR/candidate-image-id.txt"
sha256sum \
  "$DOCKERFILE" "$AGENTS" "$QUICKSTART" "$BACKUP" "$BACKUP_MANIFEST" \
  "$EVIDENCE_DIR/candidate-source-sha256.txt" \
  > "$EVIDENCE_DIR/non-serving-evidence.sha256"
echo "non-serving candidate verified: $CANDIDATE_IMAGE"
