import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from create_reliability_sprint_seller_key import (
    AGENT_ID,
    EXPECTED_AUTHORIZATION,
    PRIVATE_ENV_NAME,
    SIGNER_FILENAME,
    SellerKeyError,
    create_seller_key,
)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _fixture(tmp_path: Path) -> tuple[Path, str, bytes]:
    root = tmp_path / "viridis-fleet"
    private = root / "private"
    private.mkdir(parents=True, mode=0o700)
    private.chmod(0o700)
    hive = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    original = (
        "MARKET_SECURITY_RECEIPT_KEYS_JSON={}\n"
        "MARKET_OPERATOR_WRITE_KEYS_JSON="
        + json.dumps({"viridis-hive-orchestrator": _b64(hive)})
        + "\n"
    )
    env = root / ".env.market"
    env.write_text(original)
    env.chmod(0o600)
    return root, original, hive


def _dotenv(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line and not line.startswith("#")
    )


def test_wrong_authorization_makes_no_change(tmp_path):
    root, original, _ = _fixture(tmp_path)
    with pytest.raises(SellerKeyError, match="exact seller-key authorization"):
        create_seller_key(root, "authorize something else")
    assert (root / ".env.market").read_text() == original
    assert not (root / "private" / SIGNER_FILENAME).exists()


def test_creates_root_style_custody_and_public_only_configuration(tmp_path):
    root, original, hive = _fixture(tmp_path)
    receipt = create_seller_key(root, EXPECTED_AUTHORIZATION)

    signer = root / "private" / SIGNER_FILENAME
    assert signer.stat().st_mode & 0o777 == 0o600
    signer_values = _dotenv(signer)
    assert set(signer_values) == {PRIVATE_ENV_NAME}
    private_raw = base64.urlsafe_b64decode(
        signer_values[PRIVATE_ENV_NAME]
        + "=" * (-len(signer_values[PRIVATE_ENV_NAME]) % 4))
    assert len(private_raw) == 32
    public_raw = Ed25519PrivateKey.from_private_bytes(
        private_raw).public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )

    env = root / ".env.market"
    assert env.stat().st_mode & 0o777 == 0o600
    public_keys = json.loads(_dotenv(env)["MARKET_OPERATOR_WRITE_KEYS_JSON"])
    assert set(public_keys) == {"viridis-hive-orchestrator", AGENT_ID}
    assert base64.urlsafe_b64decode(
        public_keys["viridis-hive-orchestrator"]
        + "=" * (-len(public_keys["viridis-hive-orchestrator"]) % 4)
    ) == hive
    assert base64.urlsafe_b64decode(
        public_keys[AGENT_ID] + "=" * (-len(public_keys[AGENT_ID]) % 4)
    ) == public_raw

    backup = Path(receipt["backup_path"])
    assert backup.read_text() == original
    assert backup.stat().st_mode & 0o777 == 0o600
    assert signer_values[PRIVATE_ENV_NAME] not in json.dumps(receipt)
    assert receipt["private_key_exposed"] is False
    assert receipt["service_restarted"] is False
    assert receipt["production_database_changed"] is False
    assert receipt["offer_submitted"] is False
    assert receipt["money_moved"] is False

    with pytest.raises(SellerKeyError, match="refusing rotation"):
        create_seller_key(root, EXPECTED_AUTHORIZATION)
