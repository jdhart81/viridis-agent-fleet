from pathlib import Path
import subprocess


SCRIPT = Path(__file__).with_name(
    "publish_security_preflight_buyer_path_20260806.sh"
)
TEXT = SCRIPT.read_text(encoding="utf-8")


def test_transaction_has_valid_shell_syntax():
    result = subprocess.run(
        ["sh", "-n", str(SCRIPT)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_wrong_authorization_fails_before_github_access():
    result = subprocess.run(
        ["sh", str(SCRIPT), "not authorized"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 64
    assert "exact GitHub-publication authorization" in result.stderr


def test_transaction_pins_identity_base_patch_and_public_bytes():
    required = (
        "gh auth status",
        "gh api user --jq .login",
        "jdhart81/viridis-agent-fleet",
        "38de8e1d285f9f7a73acb3ed8e4c70d63c709baf",
        "df4d873597f4ff72606510787a755698ddb707cb0bfd26368b4245150737dfbd",
        "eb71c466ad17c81d36e3f03c5ba308a4a0f8922337cef5116cc604deab87252d",
        "gateway/test_wave9_activation.py -k demo_client",
        "git -C \"$RUN_DIR/repo\" push origin HEAD:main",
        "raw.githubusercontent.com",
    )
    for token in required:
        assert token in TEXT


def test_transaction_tests_before_push_and_does_not_touch_production_or_pay():
    assert TEXT.index("python3 -m pytest") < TEXT.index("push origin HEAD:main")
    forbidden = (
        "docker compose",
        "PAYMENT-SIGNATURE",
        "X402_BUYER_PRIVATE_KEY",
        "mcp.viridisconservation.com/x402",
    )
    for token in forbidden:
        assert token not in TEXT
