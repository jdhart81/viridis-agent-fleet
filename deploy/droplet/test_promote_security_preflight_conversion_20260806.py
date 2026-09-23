from pathlib import Path
import subprocess


SCRIPT = Path(__file__).with_name(
    "promote_security_preflight_conversion_20260806.sh"
)
TEXT = SCRIPT.read_text(encoding="utf-8")


def test_transaction_has_valid_shell_syntax():
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
    assert "exact production-promotion authorization" in result.stderr


def test_transaction_pins_images_backup_sources_and_public_client():
    required = (
        "sha256:4d465097726f8ca0c50eaf90559df0669be2a36715b24b7e06be2aa1556846ed",
        "sha256:6ccad07a9a325bb72f4673345289acf65188bfb31f5db7663def48876f0ec878",
        "9f70148d95cc4ac417a5102f4fbdda5d51c2ad19330d506d7839039e29b0f0a1",
        "d40b1cb554ff26dec84ce3b322e8f7c73892f6c39abc44892673cc23156f89e7",
        "a5fad3ef2c081bb2ffbcf0ab567e268ace5a5ad37f122e512347654a166e150b",
        "089d60fec369597cd5356740fab9cafe24c0097237236290d9473045a7dc9be5",
        "3ea80610cbc8b74d971d1b91841fbd34bfc8fa68691071f379baace1f19dd2fc",
        "eb71c466ad17c81d36e3f03c5ba308a4a0f8922337cef5116cc604deab87252d",
        "raw.githubusercontent.com/jdhart81/viridis-agent-fleet/main",
    )
    for token in required:
        assert token in TEXT


def test_transaction_has_restart_public_probe_and_automatic_rollback():
    required = (
        "rollback_required=1",
        "Security Preflight conversion rollback verified",
        "CRITICAL: automatic gateway rollback did not verify",
        "public_probe first-boot",
        "docker restart",
        "public_probe restart",
        "agent_state_rows\"] == 35",
        "/x402/security-preflight/security_preflight",
    )
    for token in required:
        assert token in TEXT


def test_transaction_cannot_send_a_payment():
    forbidden = (
        "PAYMENT-SIGNATURE",
        "X402_BUYER_PRIVATE_KEY",
        "curl -X POST",
    )
    for token in forbidden:
        assert token not in TEXT
