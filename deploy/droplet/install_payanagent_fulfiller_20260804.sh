#!/usr/bin/env bash
# Install the exact-bid PayanAgent fulfiller with a five-minute systemd timer.
set -Eeuo pipefail

EXPECTED_AUTH='install-payanagent-exact-bid-fulfiller'
CANDIDATE_DIR='/root/viridis-payanagent-candidate-20260804'
APP_DIR='/root/viridis-fleet/payanagent'
STATE_DIR='/root/viridis-fleet/payanagent-state'
EVIDENCE_ROOT='/root/viridis-fleet/payanagent-evidence'
SERVICE='viridis-payanagent-fulfiller.service'
TIMER='viridis-payanagent-fulfiller.timer'
SCRIPT_SHA='f66c11dcdd8065f44c74ab74b687e3b44c35fc99d8c732214998132e3e7adb94'
DELIVERABLE_SHA='039f0c41796166d7f349b945204428638268f553143048571374c920ceb87591'
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_DIR="$EVIDENCE_ROOT/$RUN_ID"
rollback_required=0

if [[ $# -ne 1 || $1 != "$EXPECTED_AUTH" ]]; then
  echo 'refusing: exact PayanAgent fulfiller-install authorization is required' >&2
  exit 64
fi

rollback() {
  trap - EXIT INT TERM
  systemctl disable --now "$TIMER" >/dev/null 2>&1 || true
  systemctl stop "$SERVICE" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/$TIMER" "/etc/systemd/system/$SERVICE"
  rm -f "$APP_DIR/catalog-health-check.mjs" "$APP_DIR/payanagent_fulfiller.py"
  systemctl daemon-reload
  echo 'PayanAgent fulfiller installation rolled back' >&2
}

on_exit() {
  local status=$?
  trap - EXIT INT TERM
  if [[ $status -ne 0 && $rollback_required -eq 1 ]]; then
    rollback
  fi
  exit "$status"
}
trap on_exit EXIT
trap 'exit 130' INT TERM

[[ "$(sha256sum "$CANDIDATE_DIR/payanagent_fulfiller.py" | awk '{print $1}')" == "$SCRIPT_SHA" ]]
[[ "$(sha256sum "$CANDIDATE_DIR/catalog-health-check.mjs" | awk '{print $1}')" == "$DELIVERABLE_SHA" ]]
python3 -m py_compile "$CANDIDATE_DIR/payanagent_fulfiller.py"
systemd-analyze verify \
  "$CANDIDATE_DIR/$SERVICE" \
  "$CANDIDATE_DIR/$TIMER"

if [[ -e /etc/systemd/system/$SERVICE || -e /etc/systemd/system/$TIMER ]]; then
  echo 'refusing: PayanAgent fulfiller units already exist' >&2
  exit 1
fi

install -d -m 700 "$APP_DIR" "$STATE_DIR" "$EVIDENCE_DIR"
rollback_required=1
install -m 700 "$CANDIDATE_DIR/payanagent_fulfiller.py" "$APP_DIR/payanagent_fulfiller.py"
install -m 600 "$CANDIDATE_DIR/catalog-health-check.mjs" "$APP_DIR/catalog-health-check.mjs"
install -m 644 "$CANDIDATE_DIR/$SERVICE" "/etc/systemd/system/$SERVICE"
install -m 644 "$CANDIDATE_DIR/$TIMER" "/etc/systemd/system/$TIMER"

systemctl daemon-reload
systemctl start "$SERVICE"
[[ "$(systemctl show "$SERVICE" -p Result --value)" == success ]]
[[ "$(systemctl show "$SERVICE" -p ExecMainStatus --value)" == 0 ]]
journal_line="$(journalctl -u "$SERVICE" --since "5 minutes ago" --no-pager -o cat \
  | grep '^{' | tail -n 1)"
python3 - "$journal_line" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["status"] in {
    "pending_buyer_acceptance",
    "already_fulfilled",
    "fulfilled_pending_buyer_approval",
}, payload
assert payload["request_id"] == "ks76vc9pzpz3qfgf8aawjckn5n8bezhf", payload
if "bid_id" in payload:
    assert payload["bid_id"] == "jd73dk32bsyybfzt5bqj0vkq718bt8cd", payload
PY

systemctl enable --now "$TIMER"
[[ "$(systemctl is-enabled "$TIMER")" == enabled ]]
[[ "$(systemctl is-active "$TIMER")" == active ]]

python3 - "$EVIDENCE_DIR/fulfiller-install.json" "$RUN_ID" "$journal_line" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = {
    "run_id": sys.argv[2],
    "service": "viridis-payanagent-fulfiller.service",
    "timer": "viridis-payanagent-fulfiller.timer",
    "timer_enabled": True,
    "timer_active": True,
    "poll_interval_seconds": 300,
    "exact_request_id": "ks76vc9pzpz3qfgf8aawjckn5n8bezhf",
    "exact_bid_id": "jd73dk32bsyybfzt5bqj0vkq718bt8cd",
    "initial_worker_result": json.loads(sys.argv[3]),
    "fulfiller_sha256": "f66c11dcdd8065f44c74ab74b687e3b44c35fc99d8c732214998132e3e7adb94",
    "deliverable_sha256": "039f0c41796166d7f349b945204428638268f553143048571374c920ceb87591",
    "revenue_boundary": "No revenue until buyer approval releases escrow and settlement plus paid delivery are verified.",
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
path.chmod(0o600)
print(json.dumps(payload, sort_keys=True))
PY

rollback_required=0
