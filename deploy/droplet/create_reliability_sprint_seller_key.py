#!/usr/bin/env python3
"""Create the gated Reliability Sprint Agent Market seller identity.

The private Ed25519 key stays in a root-only caller dotenv file. Agent Market
receives only the raw public key through MARKET_OPERATOR_WRITE_KEYS_JSON. This
helper never restarts a service, changes a database, submits an offer, or moves
money.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


EXPECTED_AUTHORIZATION = (
    "authorize seller key creation: Viridis Agent Reliability Sprint"
)
AGENT_ID = "viridis-mcp-delivery"
PRIVATE_ENV_NAME = "VIRIDIS_AGENT_MARKET_PRIVATE_KEY_B64"
SIGNER_FILENAME = "reliability-sprint-market-signer.env"
PUBLIC_ENV_NAME = "MARKET_OPERATOR_WRITE_KEYS_JSON"


class SellerKeyError(RuntimeError):
    """Fail-closed seller-key creation error."""


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_public(value: str) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(
            value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise SellerKeyError("configured public key is not base64") from exc
    if len(decoded) != 32:
        raise SellerKeyError("configured public key is not Ed25519 raw-32")
    return decoded


def _read_dotenv(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text().splitlines()
    parsed: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name in parsed:
            raise SellerKeyError(f"duplicate dotenv variable: {name}")
        parsed[name] = value
    return lines, parsed


def _write_exclusive(path: Path, payload: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def create_seller_key(root: Path, authorization: str) -> dict:
    if authorization != EXPECTED_AUTHORIZATION:
        raise SellerKeyError("exact seller-key authorization required")

    root = root.resolve()
    public_env = root / ".env.market"
    private_dir = root / "private"
    signer_env = private_dir / SIGNER_FILENAME

    if not public_env.is_file():
        raise SellerKeyError(".env.market is missing")
    if not private_dir.is_dir():
        raise SellerKeyError("private directory is missing")
    if _mode(public_env) != 0o600:
        raise SellerKeyError(".env.market must be mode 0600")
    if _mode(private_dir) != 0o700:
        raise SellerKeyError("private directory must be mode 0700")
    if public_env.stat().st_uid != os.geteuid():
        raise SellerKeyError(".env.market must be owned by the executing user")
    if private_dir.stat().st_uid != os.geteuid():
        raise SellerKeyError("private directory must be owned by the executing user")
    if signer_env.exists():
        raise SellerKeyError("Reliability Sprint signer already exists; refusing rotation")

    original = public_env.read_bytes()
    lines, parsed = _read_dotenv(public_env)
    try:
        public_keys = json.loads(parsed.get(PUBLIC_ENV_NAME, "{}") or "{}")
    except json.JSONDecodeError as exc:
        raise SellerKeyError(
            "MARKET_OPERATOR_WRITE_KEYS_JSON is invalid JSON") from exc
    if not isinstance(public_keys, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in public_keys.items()):
        raise SellerKeyError("public key configuration must be a string map")
    for value in public_keys.values():
        _decode_public(value)
    if AGENT_ID in public_keys:
        raise SellerKeyError("Reliability Sprint public key already exists; refusing rotation")

    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    private_b64 = _b64(private_raw)
    public_b64 = _b64(public_raw)
    fingerprint = hashlib.sha256(public_raw).hexdigest()

    created_at = datetime.now(timezone.utc)
    stamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    backup = root / f".env.market.pre-reliability-seller-key-{stamp}"
    temp_public = root / f".env.market.reliability-seller-key.tmp-{os.getpid()}"

    _write_exclusive(
        signer_env,
        f"{PRIVATE_ENV_NAME}={private_b64}\n".encode(),
        0o600,
    )
    try:
        _write_exclusive(backup, original, 0o600)
        public_keys[AGENT_ID] = public_b64
        encoded_map = json.dumps(
            public_keys, sort_keys=True, separators=(",", ":"))
        replacement = f"{PUBLIC_ENV_NAME}={encoded_map}"
        found = False
        updated: list[str] = []
        for line in lines:
            if line.strip().startswith(PUBLIC_ENV_NAME + "="):
                if found:
                    raise SellerKeyError(
                        "duplicate public-key configuration during rewrite")
                updated.append(replacement)
                found = True
            else:
                updated.append(line)
        if not found:
            updated.append(replacement)
        _write_exclusive(
            temp_public,
            ("\n".join(updated).rstrip("\n") + "\n").encode(),
            0o600,
        )
        os.replace(temp_public, public_env)
        _fsync_dir(root)
    except Exception:
        if temp_public.exists():
            temp_public.unlink()
        raise

    # Verify both files from disk without returning private material.
    if _mode(signer_env) != 0o600 or _mode(public_env) != 0o600:
        raise SellerKeyError("post-write file mode verification failed")
    signer_lines, signer_values = _read_dotenv(signer_env)
    if len(signer_lines) != 1 or set(signer_values) != {PRIVATE_ENV_NAME}:
        raise SellerKeyError("private signer file contract verification failed")
    stored_private = base64.urlsafe_b64decode(
        signer_values[PRIVATE_ENV_NAME]
        + "=" * (-len(signer_values[PRIVATE_ENV_NAME]) % 4))
    if len(stored_private) != 32:
        raise SellerKeyError("stored private signer is not Ed25519 raw-32")
    derived_public = Ed25519PrivateKey.from_private_bytes(
        stored_private).public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    _, final_values = _read_dotenv(public_env)
    final_keys = json.loads(final_values[PUBLIC_ENV_NAME])
    if _decode_public(final_keys[AGENT_ID]) != derived_public:
        raise SellerKeyError("private signer and public configuration mismatch")

    return {
        "status": "created",
        "created_at": created_at.isoformat(),
        "agent_id": AGENT_ID,
        "public_key_sha256": fingerprint,
        "configured_public_key_ids": sorted(final_keys),
        "private_signer_path": str(signer_env),
        "private_signer_mode": "0600",
        "public_configuration_path": str(public_env),
        "public_configuration_mode": "0600",
        "backup_path": str(backup),
        "private_key_exposed": False,
        "service_restarted": False,
        "production_database_changed": False,
        "offer_submitted": False,
        "money_moved": False,
        "next_gate": "AWAITING_EXACT_PRODUCTION_PROMOTION_AUTHORIZATION",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--authorization", required=True)
    args = parser.parse_args()
    try:
        receipt = create_seller_key(args.root, args.authorization)
    except SellerKeyError as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
