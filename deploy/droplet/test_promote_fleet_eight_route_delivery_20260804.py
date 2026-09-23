from pathlib import Path
import subprocess


SCRIPT = Path(__file__).with_name(
    "promote_fleet_eight_route_delivery_20260804.sh"
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


def test_transaction_pins_release_backup_runtime_and_rollback_gates():
    required = (
        "sha256:b59caadfce0ef9234ff68eb62530730b96aff376c9a1d79d86367305803f4cc5",
        "sha256:5a5402b4c490c53cda9e28c0115fafc11a2bd60a11b6f85740764e39ae036f67",
        "98267113daa4cbbfa52c510cc1770791993a3b8ee7de9975f33c316926e9dc63",
        "2d9ce3009f608839a7dd886e7a63b86907eddd1d12622e44e043665fe92b36d6",
        "viridis-stable:rollback-eight-route-delivery-20260804",
        "gateway_runtime_parity.py",
        "gateway_state_backup.py",
        "rollback_required=1",
        "fleet rollback verified",
        "CRITICAL: automatic fleet rollback did not verify",
    )
    for token in required:
        assert token in TEXT


def test_transaction_probes_public_routes_receipts_and_restart():
    required = (
        "/x402/regulatory-radar/monitor_changes",
        "/x402/security-preflight/security_preflight",
        "Eight paid skills",
        "viridis-paid-delivery-v1",
        "viridis_delivery",
        "docker restart",
        "runtime-restart.json",
    )
    for token in required:
        assert token in TEXT
    assert "curl -X POST" not in TEXT
    assert "PAYMENT-SIGNATURE" not in TEXT
