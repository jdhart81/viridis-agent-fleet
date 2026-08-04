"""Root-only, no-network outbox for Fleet commercial review packets.

The gateway may call this module only after the delivery-bound settlement has
been durably saved. The outbox is an operator handoff surface: it never posts a
receipt, recognizes revenue, contacts the command center, or changes payment
state.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from commercial_outcome_exporter import (
    CommercialExportError,
    build_commercial_export,
    canonical_json,
)


DEFAULT_OUTBOX_DIR = "/data/commercial-receipts/pending"
DEFAULT_KEY_ID = "fleet-commercial-v1"
PRIVATE_KEY_ENV = "FLEET_COMMERCIAL_RECEIPT_PRIVATE_KEY_PKCS8_B64"
PRIVATE_KEY_FILE_ENV = "FLEET_COMMERCIAL_RECEIPT_PRIVATE_KEY_FILE"


def _private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise CommercialExportError("commercial outbox must be a real directory")
    path.chmod(0o700)


def _private_key_from_environment() -> str | None:
    inline_key = os.environ.get(PRIVATE_KEY_ENV, "").strip()
    key_file_name = os.environ.get(PRIVATE_KEY_FILE_ENV, "").strip()
    if inline_key and key_file_name:
        raise CommercialExportError(
            "commercial signing key must use exactly one source"
        )
    if inline_key:
        return inline_key
    if not key_file_name:
        return None

    key_file = Path(key_file_name)
    if key_file.is_symlink() or not key_file.is_file():
        raise CommercialExportError("commercial signing key must be a real file")
    metadata = key_file.stat()
    if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
        raise CommercialExportError(
            "commercial signing key must be owner-only and owned by the process"
        )
    value = key_file.read_text(encoding="ascii").strip()
    if not value:
        raise CommercialExportError("commercial signing key file is empty")
    return value


def write_pending_export(
    settlement: Mapping[str, Any],
    *,
    private_key_pkcs8_b64: str,
    key_id: str,
    outbox_dir: str = DEFAULT_OUTBOX_DIR,
    prior_settlements: Iterable[Mapping[str, Any]] = (),
) -> Path:
    """Atomically write one idempotent, root-readable review packet."""
    packet = build_commercial_export(
        settlement,
        private_key_pkcs8_b64=private_key_pkcs8_b64,
        key_id=key_id,
        prior_settlements=prior_settlements,
    )
    source_event = packet["commercialImport"]["receipt"]["sourceEventSha256"]
    directory = Path(outbox_dir)
    _private_directory(directory)
    destination = directory / f"{source_event}.json"
    if destination.exists():
        if destination.is_symlink() or not destination.is_file():
            raise CommercialExportError("commercial outbox entry is not a file")
        existing = destination.read_text(encoding="utf-8")
        if existing != canonical_json(packet) + "\n":
            raise CommercialExportError("commercial outbox idempotency conflict")
        destination.chmod(0o600)
        return destination

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{source_event}.", suffix=".tmp", dir=directory
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(canonical_json(packet))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        destination.chmod(0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def enqueue_from_environment(
    settlement: Mapping[str, Any],
    *,
    prior_settlements: Iterable[Mapping[str, Any]] = (),
) -> Path | None:
    """Return None when disabled; otherwise fail closed on malformed evidence."""
    private_key = _private_key_from_environment()
    if not private_key:
        return None
    key_id = os.environ.get("FLEET_COMMERCIAL_RECEIPT_KEY_ID", DEFAULT_KEY_ID).strip()
    outbox_dir = os.environ.get(
        "FLEET_COMMERCIAL_RECEIPT_OUTBOX_DIR", DEFAULT_OUTBOX_DIR
    ).strip()
    if not key_id or not outbox_dir:
        raise CommercialExportError("commercial outbox configuration is incomplete")
    return write_pending_export(
        settlement,
        private_key_pkcs8_b64=private_key,
        key_id=key_id,
        outbox_dir=outbox_dir,
        prior_settlements=prior_settlements,
    )
