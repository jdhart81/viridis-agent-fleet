import sys
import base64
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for module_name in list(sys.modules):
    if (module_name == "src" or module_name.startswith("src.")
            or module_name == "adapters"
            or module_name.startswith("adapters.")):
        sys.modules.pop(module_name, None)


@pytest.fixture(autouse=True)
def signing_key(monkeypatch):
    monkeypatch.delenv(
        "SECURITY_PREFLIGHT_RECEIPT_DB_PATH", raising=False)
    key = Ed25519PrivateKey.generate()
    der = key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    monkeypatch.setenv(
        "SECURITY_PREFLIGHT_SIGNING_KEY_PKCS8_B64",
        base64.b64encode(der).decode("ascii"))
    return key
