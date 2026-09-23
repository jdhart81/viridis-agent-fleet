#!/usr/bin/env python3
"""Render an exact, pinned Regulatory Radar growth promotion transaction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import sys
from typing import Any


SCHEMA = "viridis-regulatory-radar-growth-promotion-pins-v1"
EXPECTED_AUTH = "authorize production promotion: Regulatory Radar growth wedge"
PREVIOUS_IMAGE = (
    "sha256:"
    "e1e7346fd3a79d1a41533084f02d8da9197b0c0236bede2b68dd2837b4bfa3b9"
)
CANDIDATE_IMAGE = (
    "sha256:"
    "f1bd8e3d69b9606bf3d686a16bb9374d1090bc4031ed5e56795f41844f9b5985"
)
CANDIDATE_TAG = (
    "viridis-growth-agent:"
    "regulatory-radar-wedge-candidate-20260726"
)
BACKUP_GATE_SHA = (
    "8872373ddfeed046d91a322f6451b0bcfb29c4df3c41b85e323383d67015e32a"
)
RUNTIME_PROBE_SHA = (
    "11a8e4c516664552356b58811439af80d109d2fc94e2b081650412403ed2b3ab"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class RenderFailure(RuntimeError):
    """Candidate evidence cannot produce an armed transaction."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RenderFailure(message)


def validate_pins(payload: dict[str, Any]) -> dict[str, Any]:
    require(payload.get("schema") == SCHEMA, "candidate receipt schema changed")
    for gate in (
        "gateway_public_probe_passed",
        "candidate_runtime_passed",
        "offsite_backup_verified",
        "restore_drill_passed",
    ):
        require(payload.get(gate) is True, f"candidate receipt gate is not green: {gate}")
    backup = payload.get("backup")
    require(isinstance(backup, dict), "candidate receipt backup is missing")
    filename = backup.get("filename")
    manifest_filename = backup.get("manifest_filename")
    require(
        isinstance(filename, str) and _SAFE_NAME.fullmatch(filename) is not None,
        "backup filename is unsafe",
    )
    require(
        isinstance(manifest_filename, str)
        and _SAFE_NAME.fullmatch(manifest_filename) is not None,
        "backup manifest filename is unsafe",
    )
    require(filename.endswith(".db"), "backup filename must end in .db")
    require(
        manifest_filename.endswith(".manifest.json"),
        "backup manifest filename must end in .manifest.json",
    )
    digest = backup.get("sha256")
    require(
        isinstance(digest, str) and _SHA256.fullmatch(digest) is not None,
        "backup SHA-256 is malformed",
    )
    rows = backup.get("minimum_rows")
    max_seq = backup.get("minimum_max_seq")
    require(
        isinstance(rows, int) and not isinstance(rows, bool) and rows >= 0,
        "backup row floor is invalid",
    )
    require(
        isinstance(max_seq, int)
        and not isinstance(max_seq, bool)
        and max_seq >= 0,
        "backup sequence floor is invalid",
    )
    return {
        "filename": filename,
        "manifest_filename": manifest_filename,
        "sha256": digest,
        "minimum_rows": rows,
        "minimum_max_seq": max_seq,
    }


def _q(value: str | int) -> str:
    return shlex.quote(str(value))


def render_transaction(payload: dict[str, Any]) -> str:
    backup = validate_pins(payload)
    return f"""#!/bin/sh
# Generated exact-scope growth promotion transaction. Do not edit by hand.
set -eu

EXPECTED_AUTH={_q(EXPECTED_AUTH)}
PREVIOUS_IMAGE={_q(PREVIOUS_IMAGE)}
CANDIDATE_IMAGE={_q(CANDIDATE_IMAGE)}
CANDIDATE_TAG={_q(CANDIDATE_TAG)}
ROLLBACK_TAG='viridis-growth-agent:rollback-regulatory-radar-wedge-20260726'
LATEST_TAG='viridis-growth-agent:latest'
LIVE_CONTAINER='growth-agent-growth-agent-1'
COMPOSE_DIR='/root/viridis-fleet/growth-agent'
EVIDENCE_DIR=${{VIRIDIS_GROWTH_PROMOTION_EVIDENCE_DIR:-'/root/viridis-candidates/regulatory-radar-growth-wedge'}}
BACKUP_GATE_SHA={_q(BACKUP_GATE_SHA)}
RUNTIME_PROBE_SHA={_q(RUNTIME_PROBE_SHA)}
BACKUP_FILE="$EVIDENCE_DIR/{backup['filename']}"
BACKUP_MANIFEST="$EVIDENCE_DIR/{backup['manifest_filename']}"
BACKUP_SHA={_q(backup['sha256'])}
MINIMUM_ROWS={_q(backup['minimum_rows'])}
MINIMUM_MAX_SEQ={_q(backup['minimum_max_seq'])}
CYCLE_FILE="$EVIDENCE_DIR/result-promotion.json"
RUNTIME_RESULT="$EVIDENCE_DIR/runtime-promotion.json"

if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]; then
  echo "refusing: exact growth-promotion authorization is required" >&2
  exit 64
fi

compose_growth() {{
  docker compose \
    --project-directory "$COMPOSE_DIR" \
    --file "$COMPOSE_DIR/docker-compose.yml" \
    --project-name growth-agent \
    up -d --no-deps --force-recreate growth-agent
}}

wait_running() {{
  expected_image=$1
  attempts=0
  while [ "$attempts" -lt 30 ]; do
    image=$(docker inspect --format '{{{{.Image}}}}' "$LIVE_CONTAINER")
    status=$(docker inspect --format '{{{{.State.Status}}}}' "$LIVE_CONTAINER")
    if [ "$image" = "$expected_image" ] && [ "$status" = running ]; then
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 2
  done
  echo "growth worker did not reach the exact running image" >&2
  return 1
}}

require_safe_runtime() {{
  docker inspect --format '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' \
    "$LIVE_CONTAINER" | grep -qx 'GROWTH_AGENT_ENABLED=1'
  docker inspect --format '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' \
    "$LIVE_CONTAINER" | grep -qx 'GROWTH_AGENT_DRY_RUN=1'
  docker inspect --format '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' \
    "$LIVE_CONTAINER" | grep -qx 'GROWTH_OPENAI_ENABLED=0'
  if docker inspect \
    --format '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' \
    "$LIVE_CONTAINER" | grep '^GROWTH_CAMPAIGN=' \
      | grep -qvx 'GROWTH_CAMPAIGN='; then
    return 1
  fi
  if docker inspect \
    --format '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' \
    "$LIVE_CONTAINER" | grep '^GROWTH_CAMPAIGN_AUTHORIZATION=' \
      | grep -qvx 'GROWTH_CAMPAIGN_AUTHORIZATION='; then
    return 1
  fi
  if docker inspect \
    --format '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' \
    "$LIVE_CONTAINER" | grep -qx 'GROWTH_AGENT_RUN_ONCE=1'; then
    return 1
  fi
  [ "$(docker inspect --format \
    '{{{{.HostConfig.RestartPolicy.Name}}}}' "$LIVE_CONTAINER")" = unless-stopped ]
  [ "$(docker inspect --format \
    '{{{{range .Mounts}}}}{{{{if eq .Destination "/state"}}}}{{{{.Name}}}}{{{{end}}}}{{{{end}}}}' \
    "$LIVE_CONTAINER")" = growth-agent_growth_state ]
}}

capture_cycle() {{
  since=$1
  attempts=0
  temporary="$CYCLE_FILE.tmp"
  while [ "$attempts" -lt 30 ]; do
    docker logs --since "$since" "$LIVE_CONTAINER" 2>&1 \
      | awk '/^{{/ {{print; exit}}' > "$temporary"
    if [ -s "$temporary" ] && python3 -m json.tool "$temporary" >/dev/null; then
      mv "$temporary" "$CYCLE_FILE"
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 2
  done
  rm -f "$temporary"
  echo "growth worker emitted no structured first cycle" >&2
  return 1
}}

rollback_required=0
rollback() {{
  trap - EXIT INT TERM
  echo "growth promotion failed; restoring previous image" >&2
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG"
  compose_growth
  wait_running "$PREVIOUS_IMAGE"
  require_safe_runtime
  docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG"
  [ "$(docker image inspect --format '{{{{.Id}}}}' "$LATEST_TAG")" \
    = "$PREVIOUS_IMAGE" ]
  echo "growth rollback verified" >&2
}}

on_exit() {{
  status=$1
  trap - EXIT INT TERM
  if [ "$status" -ne 0 ] && [ "$rollback_required" -eq 1 ]; then
    if ! rollback; then
      echo "CRITICAL: automatic growth rollback did not verify" >&2
      exit 70
    fi
  fi
  rm -f "$CYCLE_FILE.tmp"
  exit "$status"
}}
trap 'on_exit $?' EXIT
trap 'exit 130' INT TERM

[ "$(docker inspect --format '{{{{.Image}}}}' "$LIVE_CONTAINER")" \
  = "$PREVIOUS_IMAGE" ]
[ "$(docker inspect --format '{{{{.State.Status}}}}' "$LIVE_CONTAINER")" \
  = running ]
require_safe_runtime
[ "$(docker image inspect --format '{{{{.Id}}}}' "$LATEST_TAG")" \
  = "$PREVIOUS_IMAGE" ]
[ "$(docker image inspect --format '{{{{.Id}}}}' "$CANDIDATE_TAG")" \
  = "$CANDIDATE_IMAGE" ]
[ "$(sha256sum "$EVIDENCE_DIR/regulatory_radar_growth_promotion_backup_gate.py" \
  | awk '{{print $1}}')" = "$BACKUP_GATE_SHA" ]
[ "$(sha256sum "$EVIDENCE_DIR/regulatory_radar_growth_runtime_probe.py" \
  | awk '{{print $1}}')" = "$RUNTIME_PROBE_SHA" ]

python3 "$EVIDENCE_DIR/regulatory_radar_growth_promotion_backup_gate.py" \
  --backup "$BACKUP_FILE" \
  --manifest "$BACKUP_MANIFEST" \
  --expected-sha256 "$BACKUP_SHA" \
  --minimum-rows "$MINIMUM_ROWS" \
  --minimum-max-seq "$MINIMUM_MAX_SEQ" \
  --maximum-age-hours 25 \
  > "$EVIDENCE_DIR/backup-growth-promotion-gate.json"

docker tag "$PREVIOUS_IMAGE" "$ROLLBACK_TAG"
[ "$(docker image inspect --format '{{{{.Id}}}}' "$ROLLBACK_TAG")" \
  = "$PREVIOUS_IMAGE" ]
promotion_started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
rollback_required=1
docker tag "$CANDIDATE_IMAGE" "$LATEST_TAG"
compose_growth
wait_running "$CANDIDATE_IMAGE"
require_safe_runtime
capture_cycle "$promotion_started"
docker inspect "$LIVE_CONTAINER" | python3 \
  "$EVIDENCE_DIR/regulatory_radar_growth_runtime_probe.py" \
  --inspect-json - \
  --cycle-json "$CYCLE_FILE" \
  --mode promotion \
  > "$RUNTIME_RESULT"
[ "$(docker image inspect --format '{{{{.Id}}}}' "$LATEST_TAG")" \
  = "$CANDIDATE_IMAGE" ]

rollback_required=0
trap - EXIT INT TERM
rm -f "$CYCLE_FILE.tmp"
echo "promotion verified: Regulatory Radar growth wedge"
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pins", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(args.pins.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RenderFailure("candidate receipt must be an object")
        rendered = render_transaction(payload)
        if args.output.exists():
            raise RenderFailure("refusing to overwrite an existing transaction")
        args.output.write_text(rendered, encoding="utf-8")
        args.output.chmod(0o700)
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "error": {
                "code": "GROWTH_PROMOTION_RENDER_FAILED",
                "message": str(exc),
            },
        }, sort_keys=True))
        return 1
    print(json.dumps({
        "status": "ok",
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
