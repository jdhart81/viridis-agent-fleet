from pathlib import Path
import os
import subprocess

import pytest


SCRIPT = Path(__file__).with_name(
    "promote_regulatory_radar_seat_bridge_state_safe_20260728.sh"
)
TEXT = SCRIPT.read_text(encoding="utf-8")
PREVIOUS = (
    "sha256:"
    "9dc219f22d78e8a3e2e199a62c90143468536b248b90c91f5c31a0531d5c717c"
)
CANDIDATE = (
    "sha256:"
    "52776a3fd3963d2761de74390dbf63d10826fa258488d024357a7dd6c3c55c77"
)
AUTHORIZATION = (
    "authorize production promotion: Regulatory Radar paid-success "
    "seat bridge 28-agent copied-state-safe refresh"
)


def test_transaction_has_valid_shell_syntax_and_is_executable():
    result = subprocess.run(
        ["/bin/sh", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert os.access(SCRIPT, os.X_OK)


def test_transaction_requires_one_exact_production_authorization():
    assert f"EXPECTED_AUTH='{AUTHORIZATION}'" in TEXT
    assert 'if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]' in TEXT
    assert "exit 64" in TEXT


def test_transaction_pins_image_archive_backup_controls_and_rollback_evidence():
    for value in (
        PREVIOUS,
        CANDIDATE,
        "sha256:f4c034e25d6a2725f84d3be3a635971dfa1127626393628aeedc85401e93f0f0",
        "8ef0c660302986f153754f1262b5def1ec8eadc5c2a8ff333a7e2d50ea2f99ca",
        "66e45129f51a36411e0f4ad798271728dcb5199ed32ce06090ce117147f47aed",
        "310e30335e357d09dfbee149655e1a2aedaaebfa95ec9b45e386050289778135",
        "7cc5efa53c2c7f16a5ed62999ac5db191e8ba50e50a76eeda3cfc77d615b2e41",
        "3fdd0fd7ceb50812b6a7eadafa3eea9780f43e371393d755b0407da0c5acabec",
        "d0857778e649bc6f1f02491860c9d416ef54495a0847cabb5e696c915b5c11a7",
        "f0910fd99bbd6ddbdf729ad2a050620bc6c231847275086a5ba48caa6528c5a3",
        "0fcf516b9713199463ffb86c26f445d0e8341a9cca1f66802c3378e937a4c677",
        "--maximum-age-hours 25",
        "--minimum-rows 35",
        "MIN_AVAILABLE_MIB=320",
        "MIN_DOCKER_AVAILABLE_BYTES=2147483648",
    ):
        assert value in TEXT


def test_transaction_has_two_runtime_public_and_parity_gates():
    assert TEXT.count('runtime_probe "$RUN_DIR/runtime-probe-') == 2
    assert 'public_verify "$PUBLIC_CANDIDATE"' in TEXT
    assert 'public_verify "$PUBLIC_RESTART"' in TEXT
    assert TEXT.count('"$RUNTIME_PARITY" compare') == 3
    assert 'docker restart "$LIVE_CONTAINER"' in TEXT
    assert "empty payment" not in TEXT  # implemented inside the pinned probe


def test_transaction_automatically_rolls_back_without_state_restore_or_paid_call():
    assert "trap 'on_exit $?' EXIT" in TEXT
    assert "seat-bridge rollback verified" in TEXT
    assert 'docker tag "$PREVIOUS_IMAGE" "$LATEST_TAG"' in TEXT
    assert 'wait_healthy "$PREVIOUS_IMAGE"' in TEXT
    for forbidden in (
        "docker compose down",
        "docker volume",
        "docker system prune",
        "gateway_state",
        "restore-drill",
        "X-PAYMENT",
        "PAYMENT-SIGNATURE",
        "curl ",
        "wget ",
    ):
        assert forbidden not in TEXT


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def fake_environment(tmp_path: Path):
    commands = tmp_path / "commands"
    state = tmp_path / "state"
    evidence = tmp_path / "evidence"
    commands.mkdir()
    state.mkdir()
    evidence.mkdir()
    (state / "running").write_text(PREVIOUS, encoding="utf-8")
    (state / "latest").write_text(PREVIOUS, encoding="utf-8")
    (state / "rollback").write_text("", encoding="utf-8")
    (state / "health").write_text("healthy", encoding="utf-8")
    for name in (
        "gateway-candidate.tar.gz",
        "regulatory_radar_seat_bridge_production_probe_20260728.py",
        "regulatory_radar_seat_bridge_rollback_gate_20260728.py",
        "regulatory_radar_promotion_backup_gate.py",
        "regulatory_radar_margin_gate.py",
        "commercial_contract.json",
        "gateway_runtime_parity.py",
        "verify_candidate_oci_binding.py",
        "viridis_state-20260728T171822Z.db",
        "viridis_state-20260728T171822Z.manifest.json",
    ):
        (evidence / name).write_text("fixture\n", encoding="utf-8")
    rollback = evidence / "rollback-compat"
    rollback.mkdir()
    for name in (
        "snapshot-compatibility.json",
        "old-image-loopback-health.json",
        "final-state.json",
        "source-before.sha256",
        "source-after.sha256",
    ):
        (rollback / name).write_text("fixture\n", encoding="utf-8")

    _write_executable(
        commands / "docker",
        """#!/bin/sh
set -eu
state=$FAKE_DOCKER_STATE
previous=$FAKE_PREVIOUS
candidate=$FAKE_CANDIDATE
case "$1 $2" in
  "inspect --format")
    format=$3
    case "$format" in
      *Image*) cat "$state/running" ;;
      *Health.Status*) cat "$state/health" ;;
      *) exit 91 ;;
    esac
    ;;
  "inspect viridis-fleet-gateway-1")
    printf '[{"Image":"%s"}]\\n' "$(cat "$state/running")"
    ;;
  "image inspect")
    format=$4
    ref=$5
    case "$format" in
      *Architecture*)
        printf 'amd64/linux\\n'
        ;;
      *Id*)
        case "$ref" in
          viridis-stable:latest) cat "$state/latest" ;;
          viridis-stable:regulatory-radar-seat-bridge-copied-state-safe-candidate-20260728)
            printf '%s\\n' "$candidate"
            ;;
          viridis-stable:rollback-regulatory-radar-seat-bridge-state-safe-20260728)
            cat "$state/rollback"
            ;;
          "$candidate") printf '%s\\n' "$candidate" ;;
          *) exit 92 ;;
        esac
        ;;
      *) exit 93 ;;
    esac
    ;;
  "ps -a")
    ;;
  "run --rm")
    cat <<EOF
33d0b79f19171f7f1ff89d92b41f4f0995a61592957720fb3a2c156628c2b980  /fleet/deploy/gateway/x402_http.py
99990768fc1526fb520df20596b4fb3a3096efac44b4f93bb30ca8a3890e244f  /fleet/deploy/gateway/payment_gate.py
e34b2c1bd9a0618e59e8864bacae2e1fd10404ddc41e60b4beb61bceaf7ccc73  /fleet/deploy/gateway/state_store.py
22c343594ee26db8d391ca67ef6a42306df6eaa8baf0d99f4e9f73c3d6806bec  /fleet/deploy/gateway/viridis_mcp_gateway.py
d0363968474aacc5f816bd6f87a284d3620f8df5eb96e54030cc78e119a9034a  /fleet/security-preflight-agent/src/core.py
EOF
    ;;
  "tag "*)
    source=$2
    target=$3
    case "$target" in
      viridis-stable:latest) printf '%s' "$source" > "$state/latest" ;;
      viridis-stable:rollback-regulatory-radar-seat-bridge-state-safe-20260728)
        printf '%s' "$source" > "$state/rollback"
        ;;
      *) exit 94 ;;
    esac
    if [ "$target" = viridis-stable:latest ] && \
       [ "$source" = "$candidate" ] && \
       [ "${FAKE_FAIL_CANDIDATE_TAG:-0}" = 1 ]; then
      exit 95
    fi
    ;;
  "compose --project-directory")
    target=$(cat "$state/latest")
    if [ "$target" = "$previous" ] && \
       [ "${FAKE_FAIL_ROLLBACK:-0}" = 1 ]; then
      exit 96
    fi
    printf '%s' "$target" > "$state/running"
    printf 'healthy' > "$state/health"
    ;;
  "exec -i")
    cat >/dev/null
    marker="$state/runtime-failed"
    if [ "${FAKE_FAIL_RUNTIME_ONCE:-0}" = 1 ] && [ ! -e "$marker" ]; then
      : > "$marker"
      exit 97
    fi
    printf '{"status":"ok","paid_route_called":false}\\n'
    ;;
  "restart viridis-fleet-gateway-1")
    if [ "${FAKE_FAIL_RESTART:-0}" = 1 ]; then
      exit 98
    fi
    printf 'fake-container-id\\n'
    printf 'healthy' > "$state/health"
    ;;
  *) exit 99 ;;
esac
""",
    )
    _write_executable(
        commands / "df",
        "#!/bin/sh\nprintf 'Avail\\n9999999999\\n'\n",
    )
    _write_executable(
        commands / "awk",
        """#!/bin/sh
case "$*" in
  */proc/meminfo*) printf '9999' ;;
  *) exec /usr/bin/awk "$@" ;;
esac
""",
    )
    _write_executable(
        commands / "sha256sum",
        """#!/bin/sh
case "$1" in
  *regulatory_radar_seat_bridge_production_probe_20260728.py)
    digest=310e30335e357d09dfbee149655e1a2aedaaebfa95ec9b45e386050289778135 ;;
  *regulatory_radar_seat_bridge_rollback_gate_20260728.py)
    digest=7cc5efa53c2c7f16a5ed62999ac5db191e8ba50e50a76eeda3cfc77d615b2e41 ;;
  *regulatory_radar_promotion_backup_gate.py)
    digest=abf5c5738adfd5c8d1e6fe13cdac05da1b167125b7fb2b87d504b6d143837d3b ;;
  *regulatory_radar_margin_gate.py)
    digest=210d5410aa4e50997de90a5aa97791643fdb5a94a564e1324d6bf3e00ec208d3 ;;
  *commercial_contract.json)
    digest=09b212cb569f835d7ce1ffc6b921f56a9201ac5af45b5b46c58fdc585909765f ;;
  *gateway_runtime_parity.py)
    digest=7c907daba1264bb26de0da6803f85a7bdbf55ffaec484bac12729da421bd87d3 ;;
  *verify_candidate_oci_binding.py)
    digest=48f4519462b071ec17a53de0e3a5e4fd31dfcfb920d861367966b607d7bee585 ;;
  *)
    for path in "$@"; do printf '%064d  %s\\n' 0 "$path"; done
    exit 0 ;;
esac
printf '%s  %s\\n' "$digest" "$1"
""",
    )
    _write_executable(
        commands / "python3",
        """#!/bin/sh
set -eu
case "$1" in
  *gateway_runtime_parity.py)
    action=$2
    if [ "$action" = capture ]; then
      output=
      shift 2
      while [ "$#" -gt 0 ]; do
        if [ "$1" = --output ]; then output=$2; break; fi
        shift
      done
      printf '{"schema":"fake-runtime"}\\n' > "$output"
      printf '{"status":"ok"}\\n'
    elif [ "$action" = compare ]; then
      marker=$FAKE_DOCKER_STATE/parity-failed
      if [ "${FAKE_FAIL_PARITY_ONCE:-0}" = 1 ] && [ ! -e "$marker" ]; then
        : > "$marker"
        exit 101
      fi
      printf '{"status":"ok"}\\n'
    else
      exit 102
    fi
    ;;
  *regulatory_radar_seat_bridge_production_probe_20260728.py)
    action=$2
    if [ "$action" = public-capture ]; then
      printf '{"schema":"viridis-seat-bridge-public-snapshot-v1"}\\n'
    elif [ "$action" = public-verify ]; then
      marker=$FAKE_DOCKER_STATE/public-failed
      if [ "${FAKE_FAIL_PUBLIC_ONCE:-0}" = 1 ] && [ ! -e "$marker" ]; then
        : > "$marker"
        exit 103
      fi
      printf '{"status":"ok"}\\n'
    else
      exit 104
    fi
    ;;
  *regulatory_radar_promotion_backup_gate.py)
    if [ "${FAKE_FAIL_BACKUP:-0}" = 1 ]; then exit 105; fi
    printf '{"status":"ok"}\\n'
    ;;
  *regulatory_radar_seat_bridge_rollback_gate_20260728.py|\
  *regulatory_radar_margin_gate.py|*verify_candidate_oci_binding.py)
    printf '{"status":"ok"}\\n'
    ;;
  *) exit 106 ;;
esac
""",
    )
    _write_executable(commands / "sleep", "#!/bin/sh\nexit 0\n")
    env = {
        **os.environ,
        "PATH": f"{commands}:/usr/bin:/bin",
        "FAKE_DOCKER_STATE": str(state),
        "FAKE_PREVIOUS": PREVIOUS,
        "FAKE_CANDIDATE": CANDIDATE,
        "FAKE_FAIL_BACKUP": "0",
        "FAKE_FAIL_CANDIDATE_TAG": "0",
        "FAKE_FAIL_PUBLIC_ONCE": "0",
        "FAKE_FAIL_RUNTIME_ONCE": "0",
        "FAKE_FAIL_PARITY_ONCE": "0",
        "FAKE_FAIL_RESTART": "0",
        "FAKE_FAIL_ROLLBACK": "0",
        "VIRIDIS_SEAT_BRIDGE_PROMOTION_EVIDENCE_DIR": str(evidence),
    }
    return state, env


def invoke(env):
    return subprocess.run(
        ["/bin/sh", str(SCRIPT), AUTHORIZATION],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def assert_rollback(state):
    assert (state / "running").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "latest").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "rollback").read_text(encoding="utf-8") == PREVIOUS


def test_transaction_reaches_exact_candidate_after_restart(tmp_path):
    state, env = fake_environment(tmp_path)
    result = invoke(env)
    assert result.returncode == 0, result.stderr
    assert (state / "running").read_text(encoding="utf-8") == CANDIDATE
    assert (state / "latest").read_text(encoding="utf-8") == CANDIDATE
    assert (state / "rollback").read_text(encoding="utf-8") == PREVIOUS


@pytest.mark.parametrize(
    "failure_flag",
    (
        "FAKE_FAIL_CANDIDATE_TAG",
        "FAKE_FAIL_PUBLIC_ONCE",
        "FAKE_FAIL_RUNTIME_ONCE",
        "FAKE_FAIL_PARITY_ONCE",
        "FAKE_FAIL_RESTART",
    ),
)
def test_post_retag_failure_executes_and_verifies_rollback(
    tmp_path, failure_flag
):
    state, env = fake_environment(tmp_path)
    env[failure_flag] = "1"
    result = invoke(env)
    assert result.returncode != 0
    assert "seat-bridge rollback verified" in result.stderr
    assert "CRITICAL" not in result.stderr
    assert_rollback(state)


def test_backup_failure_stops_before_any_retag(tmp_path):
    state, env = fake_environment(tmp_path)
    env["FAKE_FAIL_BACKUP"] = "1"
    result = invoke(env)
    assert result.returncode != 0
    assert "rollback verified" not in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "latest").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "rollback").read_text(encoding="utf-8") == ""


def test_unverified_rollback_returns_critical_exit_70(tmp_path):
    state, env = fake_environment(tmp_path)
    env["FAKE_FAIL_PUBLIC_ONCE"] = "1"
    env["FAKE_FAIL_ROLLBACK"] = "1"
    result = invoke(env)
    assert result.returncode == 70
    assert "CRITICAL: automatic seat-bridge rollback did not verify" in result.stderr
