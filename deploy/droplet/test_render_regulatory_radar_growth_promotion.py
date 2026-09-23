import copy
import json
import os
from pathlib import Path
import subprocess

import pytest

from deploy.droplet import render_regulatory_radar_growth_promotion as render


def pins():
    return {
        "schema": render.SCHEMA,
        "gateway_public_probe_passed": True,
        "candidate_runtime_passed": True,
        "offsite_backup_verified": True,
        "restore_drill_passed": True,
        "backup": {
            "filename": "viridis_growth-20260727T120000Z.db",
            "manifest_filename": (
                "viridis_growth-20260727T120000Z.manifest.json"
            ),
            "sha256": "a" * 64,
            "minimum_rows": 26,
            "minimum_max_seq": 26,
        },
    }


def test_renders_exact_authorization_and_candidate_receipt_pins():
    script = render.render_transaction(pins())
    assert render.EXPECTED_AUTH in script
    assert render.PREVIOUS_IMAGE in script
    assert render.CANDIDATE_IMAGE in script
    assert "BACKUP_SHA=" + "a" * 64 in script
    assert "MINIMUM_ROWS=26" in script
    assert "MINIMUM_MAX_SEQ=26" in script


def test_rendered_transaction_has_valid_shell_syntax(tmp_path):
    path = tmp_path / "transaction.sh"
    path.write_text(render.render_transaction(pins()), encoding="utf-8")
    result = subprocess.run(
        ["/bin/sh", "-n", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_rendered_transaction_has_automatic_rollback_and_safe_flags():
    script = render.render_transaction(pins())
    for required in (
        "trap 'on_exit $?' EXIT",
        "growth rollback verified",
        "GROWTH_AGENT_DRY_RUN=1",
        "GROWTH_OPENAI_ENABLED=0",
        "GROWTH_CAMPAIGN=",
        "GROWTH_CAMPAIGN_AUTHORIZATION=",
        "growth-agent_growth_state",
        "--inspect-json -",
        "--mode promotion",
        "--maximum-age-hours 25",
        "| grep -qx 'GROWTH_AGENT_DRY_RUN=1'",
    ):
        assert required in script
    for forbidden in (
        "docker compose down",
        "docker volume",
        "docker build",
        "GROWTH_OPENAI_ENABLED=1",
        "authorize outbound:",
        ".growth-env-check",
    ):
        assert forbidden not in script


@pytest.mark.parametrize(
    "gate",
    [
        "gateway_public_probe_passed",
        "candidate_runtime_passed",
        "offsite_backup_verified",
        "restore_drill_passed",
    ],
)
def test_refuses_any_candidate_receipt_gate_that_is_not_green(gate):
    payload = pins()
    payload[gate] = False
    with pytest.raises(render.RenderFailure, match=gate):
        render.render_transaction(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("filename", "../state.db", "unsafe"),
        ("manifest_filename", "/tmp/manifest.json", "unsafe"),
        ("sha256", "not-a-digest", "malformed"),
        ("minimum_rows", -1, "row floor"),
        ("minimum_max_seq", True, "sequence floor"),
    ],
)
def test_refuses_unsafe_or_unpinned_backup_fields(field, value, message):
    payload = pins()
    payload["backup"][field] = value
    with pytest.raises(render.RenderFailure, match=message):
        render.render_transaction(payload)


def test_cli_refuses_to_overwrite_transaction(tmp_path):
    pins_path = tmp_path / "pins.json"
    output = tmp_path / "transaction.sh"
    pins_path.write_text(json.dumps(pins()), encoding="utf-8")
    output.write_text("keep", encoding="utf-8")
    result = subprocess.run(
        [
            "python3",
            str(Path(render.__file__)),
            "--pins",
            str(pins_path),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert output.read_text(encoding="utf-8") == "keep"
    assert json.loads(result.stdout)["status"] == "error"


def test_validation_does_not_mutate_candidate_receipt():
    payload = pins()
    original = copy.deepcopy(payload)
    render.validate_pins(payload)
    assert payload == original


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _fake_environment(
    tmp_path: Path,
    *,
    fail_runtime: bool = False,
    fail_backup: bool = False,
    partial_candidate_tag: bool = False,
    drift_after_runtime: bool = False,
    drift_during_rollback: bool = False,
    omit_campaign_variables: bool = False,
    unsafe_campaign: bool = False,
):
    commands = tmp_path / "commands"
    state = tmp_path / "state"
    evidence = tmp_path / "evidence"
    commands.mkdir()
    state.mkdir()
    evidence.mkdir()
    (state / "running").write_text(render.PREVIOUS_IMAGE, encoding="utf-8")
    (state / "latest").write_text(render.PREVIOUS_IMAGE, encoding="utf-8")
    (state / "rollback").write_text("", encoding="utf-8")
    (state / "status").write_text("running", encoding="utf-8")

    _write_executable(commands / "docker", """#!/bin/sh
set -eu
state=$FAKE_GROWTH_STATE
previous=$FAKE_GROWTH_PREVIOUS
candidate=$FAKE_GROWTH_CANDIDATE
case "$1 $2" in
  "inspect --format")
    format=$3
    case "$format" in
      *".Image"*) cat "$state/running" ;;
      *".State.Status"*) cat "$state/status" ;;
      *".Config.Env"*)
        printf '%s\\n' \
          'GROWTH_AGENT_ENABLED=1' \
          'GROWTH_AGENT_DRY_RUN=1' \
          'GROWTH_OPENAI_ENABLED=0'
        if [ "${FAKE_OMIT_GROWTH_CAMPAIGN:-0}" != 1 ]; then
          if [ "${FAKE_UNSAFE_GROWTH_CAMPAIGN:-0}" = 1 ]; then
            printf '%s\\n' 'GROWTH_CAMPAIGN=regulatory_radar_repeat'
          else
            printf '%s\\n' \
              'GROWTH_CAMPAIGN=' \
              'GROWTH_CAMPAIGN_AUTHORIZATION='
          fi
        fi
        printf '%s\\n' 'GROWTH_AGENT_RUN_ONCE=0'
        ;;
      *"RestartPolicy.Name"*) printf 'unless-stopped\\n' ;;
      *".Mounts"*) printf 'growth-agent_growth_state\\n' ;;
      *) exit 91 ;;
    esac
    ;;
  "inspect growth-agent-growth-agent-1")
    printf '[{"Image":"%s"}]\\n' "$(cat "$state/running")"
    ;;
  "image inspect")
    ref=$5
    case "$ref" in
      viridis-growth-agent:latest) cat "$state/latest" ;;
      viridis-growth-agent:regulatory-radar-wedge-candidate-20260726)
        printf '%s\\n' "$candidate"
        ;;
      viridis-growth-agent:rollback-regulatory-radar-wedge-20260726)
        cat "$state/rollback"
        ;;
      *) exit 92 ;;
    esac
    ;;
  "tag "*)
    source=$2
    target=$3
    case "$target" in
      viridis-growth-agent:latest)
        printf '%s' "$source" > "$state/latest"
        ;;
      viridis-growth-agent:rollback-regulatory-radar-wedge-20260726)
        printf '%s' "$source" > "$state/rollback"
        ;;
      *) exit 93 ;;
    esac
    if [ "$target" = viridis-growth-agent:latest ] && \
       [ "$source" = "$candidate" ] && \
       [ "${FAKE_PARTIAL_GROWTH_TAG:-0}" = 1 ]; then
      exit 98
    fi
    ;;
  "compose --project-directory")
    cat "$state/latest" > "$state/running"
    printf 'running' > "$state/status"
    if [ "${FAKE_DRIFT_GROWTH_ROLLBACK:-0}" = 1 ] && \
       [ "$(cat "$state/running")" = "$previous" ]; then
      printf '%s' "$candidate" > "$state/latest"
    fi
    ;;
  "logs --since")
    printf '%s\\n' \
      '{"status":"dry_run","enabled":true,"campaign":null,"send_attempted":false,"model":{"mode":"deterministic","reason":"dry_run_no_api"}}'
    ;;
  *) exit 94 ;;
esac
""")
    _write_executable(commands / "sha256sum", """#!/bin/sh
case "$1" in
  *regulatory_radar_growth_promotion_backup_gate.py)
    digest=8872373ddfeed046d91a322f6451b0bcfb29c4df3c41b85e323383d67015e32a
    ;;
  *regulatory_radar_growth_runtime_probe.py)
    digest=11a8e4c516664552356b58811439af80d109d2fc94e2b081650412403ed2b3ab
    ;;
  *) exit 95 ;;
esac
printf '%s  %s\\n' "$digest" "$1"
""")
    _write_executable(commands / "python3", """#!/bin/sh
case "$1 $2" in
  "-m json.tool") exit 0 ;;
esac
case "$1" in
  *regulatory_radar_growth_promotion_backup_gate.py)
    if [ "${FAKE_FAIL_GROWTH_BACKUP:-0}" = 1 ]; then
      exit 95
    fi
    printf '{"status":"ok"}\\n'
    ;;
  *regulatory_radar_growth_runtime_probe.py)
    if [ "${FAKE_FAIL_GROWTH_RUNTIME:-0}" = 1 ]; then
      exit 96
    fi
    if [ "${FAKE_DRIFT_GROWTH_AFTER_RUNTIME:-0}" = 1 ]; then
      printf '%s' "$FAKE_GROWTH_PREVIOUS" > "$FAKE_GROWTH_STATE/latest"
    fi
    printf '{"status":"ok"}\\n'
    ;;
  *) exit 97 ;;
esac
""")
    _write_executable(commands / "sleep", "#!/bin/sh\nexit 0\n")
    transaction = tmp_path / "transaction.sh"
    transaction.write_text(render.render_transaction(pins()), encoding="utf-8")
    transaction.chmod(0o700)
    env = {
        **os.environ,
        "PATH": f"{commands}:/usr/bin:/bin",
        "FAKE_GROWTH_STATE": str(state),
        "FAKE_GROWTH_PREVIOUS": render.PREVIOUS_IMAGE,
        "FAKE_GROWTH_CANDIDATE": render.CANDIDATE_IMAGE,
        "FAKE_FAIL_GROWTH_RUNTIME": "1" if fail_runtime else "0",
        "FAKE_FAIL_GROWTH_BACKUP": "1" if fail_backup else "0",
        "FAKE_PARTIAL_GROWTH_TAG": "1" if partial_candidate_tag else "0",
        "FAKE_DRIFT_GROWTH_AFTER_RUNTIME": (
            "1" if drift_after_runtime else "0"
        ),
        "FAKE_DRIFT_GROWTH_ROLLBACK": (
            "1" if drift_during_rollback else "0"
        ),
        "FAKE_OMIT_GROWTH_CAMPAIGN": (
            "1" if omit_campaign_variables else "0"
        ),
        "FAKE_UNSAFE_GROWTH_CAMPAIGN": "1" if unsafe_campaign else "0",
        "VIRIDIS_GROWTH_PROMOTION_EVIDENCE_DIR": str(evidence),
    }
    return transaction, state, env


def test_generated_transaction_executes_exact_success_path(tmp_path):
    transaction, state, env = _fake_environment(
        tmp_path,
        fail_runtime=False,
    )
    result = subprocess.run(
        ["/bin/sh", str(transaction), render.EXPECTED_AUTH],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (state / "running").read_text(encoding="utf-8") == render.CANDIDATE_IMAGE
    assert (state / "latest").read_text(encoding="utf-8") == render.CANDIDATE_IMAGE
    assert (state / "rollback").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE


def test_generated_runtime_failure_executes_verified_rollback(tmp_path):
    transaction, state, env = _fake_environment(
        tmp_path,
        fail_runtime=True,
    )
    result = subprocess.run(
        ["/bin/sh", str(transaction), render.EXPECTED_AUTH],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "growth rollback verified" in result.stderr
    assert "CRITICAL" not in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE
    assert (state / "latest").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE
    assert (state / "rollback").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE


def test_generated_transaction_refuses_wrong_authorization_without_retag(tmp_path):
    transaction, state, env = _fake_environment(tmp_path)
    result = subprocess.run(
        ["/bin/sh", str(transaction), "not authorized"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "growth rollback verified" not in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE
    assert (state / "latest").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE
    assert (state / "rollback").read_text(encoding="utf-8") == ""


def test_generated_backup_failure_stops_before_any_retag(tmp_path):
    transaction, state, env = _fake_environment(tmp_path, fail_backup=True)
    result = subprocess.run(
        ["/bin/sh", str(transaction), render.EXPECTED_AUTH],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "growth rollback verified" not in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE
    assert (state / "latest").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE
    assert (state / "rollback").read_text(encoding="utf-8") == ""


def test_generated_partial_candidate_retag_executes_rollback(tmp_path):
    transaction, state, env = _fake_environment(
        tmp_path,
        partial_candidate_tag=True,
    )
    result = subprocess.run(
        ["/bin/sh", str(transaction), render.EXPECTED_AUTH],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "growth rollback verified" in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE
    assert (state / "latest").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE
    assert (state / "rollback").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE


def test_generated_restart_tag_drift_executes_rollback(tmp_path):
    transaction, state, env = _fake_environment(
        tmp_path,
        drift_after_runtime=True,
    )
    result = subprocess.run(
        ["/bin/sh", str(transaction), render.EXPECTED_AUTH],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "growth rollback verified" in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE
    assert (state / "latest").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE


def test_generated_rollback_reseals_tag_after_restore_time_drift(tmp_path):
    transaction, state, env = _fake_environment(
        tmp_path,
        fail_runtime=True,
        drift_during_rollback=True,
    )
    result = subprocess.run(
        ["/bin/sh", str(transaction), render.EXPECTED_AUTH],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "growth rollback verified" in result.stderr
    assert "CRITICAL" not in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE
    assert (state / "latest").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE


def test_generated_transaction_accepts_absent_campaign_variables(tmp_path):
    transaction, state, env = _fake_environment(
        tmp_path,
        omit_campaign_variables=True,
    )
    result = subprocess.run(
        ["/bin/sh", str(transaction), render.EXPECTED_AUTH],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (state / "running").read_text(encoding="utf-8") == render.CANDIDATE_IMAGE


def test_generated_transaction_rejects_nonempty_campaign_before_retag(tmp_path):
    transaction, state, env = _fake_environment(
        tmp_path,
        unsafe_campaign=True,
    )
    result = subprocess.run(
        ["/bin/sh", str(transaction), render.EXPECTED_AUTH],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "growth rollback verified" not in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE
    assert (state / "latest").read_text(encoding="utf-8") == render.PREVIOUS_IMAGE
    assert (state / "rollback").read_text(encoding="utf-8") == ""
