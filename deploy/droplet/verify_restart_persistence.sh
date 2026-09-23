#!/usr/bin/env bash
# Restart-persistence verification — run ON THE DROPLET after deploying the
# StateStore build. Proves the production invariant end-to-end:
#   an escrow opened before `docker compose restart gateway` still exists,
#   in the same state, with a valid audit chain, after it.
#
# Usage (from /root/viridis-fleet):  bash verify_restart_persistence.sh
# Exit 0 = invariant holds in production.
set -euo pipefail
BASE="${BASE:-https://mcp.viridisconservation.com}"
PROBE="python3 /fleet/deploy/gateway/persistence_probe.py"   # inside the image (WORKDIR /fleet)

echo "[1/3] marking: opening a marker escrow via $BASE ..."
MARK=$(docker compose exec -T gateway sh -c "BASE=http://127.0.0.1:8402 $PROBE mark")
echo "$MARK"
EID=$(echo "$MARK" | grep -o 'esc_[0-9]*' | head -1)
[ -n "$EID" ] || { echo "FAIL: no escrow id from probe"; exit 1; }

echo "[2/3] restarting the gateway container ..."
docker compose restart gateway
sleep 5
curl -sf --max-time 30 "$BASE/healthz" >/dev/null || sleep 10

echo "[3/3] verifying marker $EID survived ..."
docker compose exec -T gateway sh -c \
  "BASE=http://127.0.0.1:8402 $PROBE verify --escrow-id $EID"
echo "RESULT: PASS — production state survives restart."
