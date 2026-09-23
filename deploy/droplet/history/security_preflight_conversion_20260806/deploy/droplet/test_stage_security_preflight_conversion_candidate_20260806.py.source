from pathlib import Path
import subprocess


SCRIPT = Path(__file__).with_name(
    "stage_security_preflight_conversion_candidate_20260806.sh"
)
TEXT = SCRIPT.read_text(encoding="utf-8")


def test_stage_transaction_has_valid_shell_syntax():
    result = subprocess.run(
        ["sh", "-n", str(SCRIPT)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_wrong_authorization_fails_before_any_docker_action():
    result = subprocess.run(
        ["sh", str(SCRIPT), "not authorized"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 64
    assert "exact non-serving-candidate authorization" in result.stderr


def test_stage_transaction_pins_live_source_backup_and_candidate():
    required = (
        "sha256:4d465097726f8ca0c50eaf90559df0669be2a36715b24b7e06be2aa1556846ed",
        "089d60fec369597cd5356740fab9cafe24c0097237236290d9473045a7dc9be5",
        "3ea80610cbc8b74d971d1b91841fbd34bfc8fa68691071f379baace1f19dd2fc",
        "9f70148d95cc4ac417a5102f4fbdda5d51c2ad19330d506d7839039e29b0f0a1",
        "gateway_state_backup.py",
        "--network none",
        "--read-only",
        "candidate-image-id.txt",
    )
    for token in required:
        assert token in TEXT


def test_stage_transaction_cannot_promote_or_serve_candidate():
    forbidden = (
        "docker compose",
        "docker restart",
        "tag \"$CANDIDATE_IMAGE\" \"$LATEST_TAG\"",
        "up -d",
        "PAYMENT-SIGNATURE",
        "curl -X POST",
    )
    for token in forbidden:
        assert token not in TEXT
    assert "docker run --rm --network none --read-only --entrypoint sha256sum" \
        in TEXT
