from pathlib import Path
import os
import subprocess


SCRIPT = (
    Path(__file__).with_name(
        "promote_regulatory_radar_gateway_wedge.sh"
    )
)
TEXT = SCRIPT.read_text(encoding="utf-8")


def test_promotion_transaction_has_valid_shell_syntax():
    result = subprocess.run(
        ["/bin/sh", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_promotion_requires_the_exact_named_authorization():
    assert (
        "EXPECTED_AUTH='authorize production promotion: "
        "Regulatory Radar gateway wedge'"
    ) in TEXT
    assert 'if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]' in TEXT


def test_promotion_pins_images_probes_capacity_and_public_edge():
    for required in (
        "sha256:6e9828e6302bf38957731d5f695202749f4e6732ddb915b06ca43ea618dd6695",
        "sha256:fc6cd0c3622811a7d6f821f7d488597fa6ad1bf781d25e1190dde3181b041309",
        "c825ca9068ded02eb2bac2429087d96151e55093c0ee8d51ab868df8be61e04a",
        "3b7bbd923bc331ffbc8edd895b1e401050f267c8e7b135a40ef5c1d3c5b98470",
        "abf5c5738adfd5c8d1e6fe13cdac05da1b167125b7fb2b87d504b6d143837d3b",
        "210d5410aa4e50997de90a5aa97791643fdb5a94a564e1324d6bf3e00ec208d3",
        "09b212cb569f835d7ce1ffc6b921f56a9201ac5af45b5b46c58fdc585909765f",
        "7c907daba1264bb26de0da6803f85a7bdbf55ffaec484bac12729da421bd87d3",
        "runs/20260727T044427Z/viridis_state-20260727T044427Z.db",
        "2cf022ea6f640aebd3814271bc059b7df9fb08ac3b11fbd463516aa994bcbe68",
        "MIN_AVAILABLE_MIB=320",
        "MIN_DOCKER_AVAILABLE_BYTES=2147483648",
        "VIRIDIS_PROMOTION_EVIDENCE_DIR:-",
        "--maximum-age-hours 25",
        "--base https://mcp.viridisconservation.com",
    ):
        assert required in TEXT


def test_promotion_automatically_rolls_back_without_volume_commands():
    assert "trap 'on_exit $?' EXIT" in TEXT
    assert "docker tag \"$PREVIOUS_IMAGE\" \"$LATEST_TAG\"" in TEXT
    assert 'wait_healthy "$PREVIOUS_IMAGE"' in TEXT
    for forbidden in (
        "docker compose down",
        "docker volume",
        "docker build",
        "docker system prune",
        "rm -",
    ):
        assert forbidden not in TEXT


PREVIOUS = (
    "sha256:"
    "6e9828e6302bf38957731d5f695202749f4e6732ddb915b06ca43ea618dd6695"
)
CANDIDATE = (
    "sha256:"
    "fc6cd0c3622811a7d6f821f7d488597fa6ad1bf781d25e1190dde3181b041309"
)
AUTHORIZATION = (
    "authorize production promotion: Regulatory Radar gateway wedge"
)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _fake_transaction_environment(tmp_path: Path, *, fail_public: bool):
    commands = tmp_path / "commands"
    state = tmp_path / "state"
    commands.mkdir()
    state.mkdir()
    (state / "running").write_text(PREVIOUS, encoding="utf-8")
    (state / "latest").write_text(PREVIOUS, encoding="utf-8")
    (state / "rollback").write_text("", encoding="utf-8")
    (state / "health").write_text("healthy", encoding="utf-8")

    _write_executable(commands / "docker", """#!/bin/sh
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
  "image inspect")
    ref=$5
    case "$ref" in
      viridis-stable:latest) cat "$state/latest" ;;
      viridis-stable:regulatory-radar-wedge-gateway-candidate-20260726)
        printf '%s\\n' "$candidate"
        ;;
      viridis-stable:rollback-regulatory-radar-gateway-wedge-20260726)
        cat "$state/rollback"
        ;;
      "$candidate") printf '%s\\n' "$candidate" ;;
      *) exit 92 ;;
    esac
    ;;
  "ps -a")
    ;;
  "tag "*)
    source=$2
    target=$3
    case "$target" in
      viridis-stable:latest) printf '%s' "$source" > "$state/latest" ;;
      viridis-stable:rollback-regulatory-radar-gateway-wedge-20260726)
        printf '%s' "$source" > "$state/rollback"
        ;;
      *) exit 93 ;;
    esac
    if [ "$target" = viridis-stable:latest ] && \
       [ "$source" = "$candidate" ] && \
       [ "${FAKE_FAIL_CANDIDATE_TAG_AFTER_WRITE:-0}" = 1 ]; then
      exit 99
    fi
    ;;
  "compose --project-directory")
    cat "$state/latest" > "$state/running"
    printf 'healthy' > "$state/health"
    if [ "${FAKE_DRIFT_LATEST_DURING_ROLLBACK:-0}" = 1 ] && \
       [ "$(cat "$state/running")" = "$previous" ]; then
      printf '%s' "$candidate" > "$state/latest"
    fi
    ;;
  *) exit 94 ;;
esac
""")
    _write_executable(commands / "df", """#!/bin/sh
printf 'Avail\\n9999999999\\n'
""")
    _write_executable(commands / "awk", """#!/bin/sh
case "$*" in
  */proc/meminfo*) printf '9999' ;;
  *) exec /usr/bin/awk "$@" ;;
esac
""")
    _write_executable(commands / "sha256sum", """#!/bin/sh
case "$1" in
  *regulatory_radar_wedge_probe.py)
    digest=c825ca9068ded02eb2bac2429087d96151e55093c0ee8d51ab868df8be61e04a
    ;;
  *regulatory_radar_wedge_public_probe.py)
    digest=3b7bbd923bc331ffbc8edd895b1e401050f267c8e7b135a40ef5c1d3c5b98470
    ;;
  *regulatory_radar_promotion_backup_gate.py)
    digest=abf5c5738adfd5c8d1e6fe13cdac05da1b167125b7fb2b87d504b6d143837d3b
    ;;
  *regulatory_radar_margin_gate.py)
    digest=210d5410aa4e50997de90a5aa97791643fdb5a94a564e1324d6bf3e00ec208d3
    ;;
  *commercial_contract.json)
    digest=09b212cb569f835d7ce1ffc6b921f56a9201ac5af45b5b46c58fdc585909765f
    ;;
  *gateway_runtime_parity.py)
    digest=7c907daba1264bb26de0da6803f85a7bdbf55ffaec484bac12729da421bd87d3
    ;;
  *) exit 95 ;;
esac
printf '%s  %s\\n' "$digest" "$1"
""")
    _write_executable(commands / "python3", """#!/bin/sh
case "$1" in
  *regulatory_radar_promotion_backup_gate.py)
    printf '{"status":"ok"}\\n'
    ;;
  *regulatory_radar_margin_gate.py)
    if [ "${FAKE_FAIL_MARGIN:-0}" = 1 ]; then
      exit 98
    fi
    printf '{"status":"ok"}\\n'
    ;;
  *regulatory_radar_wedge_public_probe.py)
    if [ "${FAKE_FAIL_PUBLIC:-0}" = 1 ]; then
      exit 96
    fi
    if [ "${FAKE_DRIFT_LATEST_DURING_PUBLIC:-0}" = 1 ]; then
      printf '%s' "$FAKE_PREVIOUS" > "$FAKE_DOCKER_STATE/latest"
    fi
    printf '{"status":"ok"}\\n'
    ;;
  *gateway_runtime_parity.py)
    action=$2
    if [ "$action" = capture ]; then
      output=
      shift 2
      while [ "$#" -gt 0 ]; do
        if [ "$1" = --output ]; then
          output=$2
          break
        fi
        shift
      done
      printf '{"schema":"fake-runtime"}\\n' > "$output"
      printf '{"status":"ok"}\\n'
    elif [ "$action" = compare ]; then
      marker=$FAKE_DOCKER_STATE/runtime-compare-failed
      if [ "${FAKE_FAIL_RUNTIME_ONCE:-0}" = 1 ] && [ ! -e "$marker" ]; then
        : > "$marker"
        exit 100
      fi
      printf '{"status":"ok"}\\n'
    else
      exit 101
    fi
    ;;
  *) exit 97 ;;
esac
""")
    _write_executable(commands / "sleep", "#!/bin/sh\nexit 0\n")
    env = {
        **os.environ,
        "PATH": f"{commands}:/usr/bin:/bin",
        "FAKE_DOCKER_STATE": str(state),
        "FAKE_PREVIOUS": PREVIOUS,
        "FAKE_CANDIDATE": CANDIDATE,
        "FAKE_FAIL_PUBLIC": "1" if fail_public else "0",
        "FAKE_FAIL_MARGIN": "0",
        "FAKE_FAIL_CANDIDATE_TAG_AFTER_WRITE": "0",
        "FAKE_DRIFT_LATEST_DURING_PUBLIC": "0",
        "FAKE_DRIFT_LATEST_DURING_ROLLBACK": "0",
        "FAKE_FAIL_RUNTIME_ONCE": "0",
        "VIRIDIS_PROMOTION_EVIDENCE_DIR": str(state),
    }
    return state, env


def test_transaction_reaches_exact_candidate_on_full_success(tmp_path):
    state, env = _fake_transaction_environment(
        tmp_path,
        fail_public=False,
    )

    result = subprocess.run(
        ["/bin/sh", str(SCRIPT), AUTHORIZATION],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (state / "running").read_text(encoding="utf-8") == CANDIDATE
    assert (state / "latest").read_text(encoding="utf-8") == CANDIDATE
    assert (state / "rollback").read_text(encoding="utf-8") == PREVIOUS


def test_public_failure_executes_and_verifies_rollback(tmp_path):
    state, env = _fake_transaction_environment(
        tmp_path,
        fail_public=True,
    )

    result = subprocess.run(
        ["/bin/sh", str(SCRIPT), AUTHORIZATION],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "rollback verified" in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "latest").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "rollback").read_text(encoding="utf-8") == PREVIOUS


def test_partial_candidate_retag_failure_executes_and_verifies_rollback(
    tmp_path,
):
    state, env = _fake_transaction_environment(
        tmp_path,
        fail_public=False,
    )
    env["FAKE_FAIL_CANDIDATE_TAG_AFTER_WRITE"] = "1"

    result = subprocess.run(
        ["/bin/sh", str(SCRIPT), AUTHORIZATION],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "rollback verified" in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "latest").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "rollback").read_text(encoding="utf-8") == PREVIOUS


def test_restart_tag_drift_executes_and_verifies_rollback(tmp_path):
    state, env = _fake_transaction_environment(
        tmp_path,
        fail_public=False,
    )
    env["FAKE_DRIFT_LATEST_DURING_PUBLIC"] = "1"

    result = subprocess.run(
        ["/bin/sh", str(SCRIPT), AUTHORIZATION],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "rollback verified" in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "latest").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "rollback").read_text(encoding="utf-8") == PREVIOUS


def test_rollback_reseals_latest_after_restore_time_tag_drift(tmp_path):
    state, env = _fake_transaction_environment(
        tmp_path,
        fail_public=True,
    )
    env["FAKE_DRIFT_LATEST_DURING_ROLLBACK"] = "1"

    result = subprocess.run(
        ["/bin/sh", str(SCRIPT), AUTHORIZATION],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "rollback verified" in result.stderr
    assert "CRITICAL" not in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "latest").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "rollback").read_text(encoding="utf-8") == PREVIOUS


def test_runtime_parity_failure_executes_and_verifies_rollback(tmp_path):
    state, env = _fake_transaction_environment(
        tmp_path,
        fail_public=False,
    )
    env["FAKE_FAIL_RUNTIME_ONCE"] = "1"

    result = subprocess.run(
        ["/bin/sh", str(SCRIPT), AUTHORIZATION],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "rollback verified" in result.stderr
    assert "CRITICAL" not in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "latest").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "rollback").read_text(encoding="utf-8") == PREVIOUS


def test_margin_failure_stops_before_any_retag(tmp_path):
    state, env = _fake_transaction_environment(
        tmp_path,
        fail_public=False,
    )
    env["FAKE_FAIL_MARGIN"] = "1"

    result = subprocess.run(
        ["/bin/sh", str(SCRIPT), AUTHORIZATION],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "rollback verified" not in result.stderr
    assert (state / "running").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "latest").read_text(encoding="utf-8") == PREVIOUS
    assert (state / "rollback").read_text(encoding="utf-8") == ""
