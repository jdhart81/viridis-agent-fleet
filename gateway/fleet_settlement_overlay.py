"""Small Fleet gateway overlay that binds delivery output to settlement state."""

from __future__ import annotations

import hashlib
import json
from typing import Any, MutableMapping


ROUTE = "security-preflight/security_preflight"


def _stable(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def bind_security_preflight_delivery(
    settlement: MutableMapping[str, Any],
    result: Any,
    *,
    asset: str,
    currency: str = "USDC",
    currency_decimals: int = 6,
) -> None:
    """Persist only hashes and exact public receipt identity after delivery."""
    if settlement.get("route") != ROUTE:
        return
    if not isinstance(result, dict) or result.get("status") != "ok":
        return
    receipt = result.get("receipt")
    if not isinstance(receipt, dict):
        return
    receipt_id = receipt.get("receipt_id")
    evidence_sha256 = receipt.get("evidence_sha256")
    if (
        not isinstance(receipt_id, str)
        or not receipt_id.startswith("vsr_")
        or not isinstance(evidence_sha256, str)
        or len(evidence_sha256) != 64
    ):
        return
    result_artifact_sha256 = _sha256(result)
    delivery_recorded_at = settlement.get("delivery_recorded_at")
    settlement["asset"] = str(asset)
    settlement["currency"] = str(currency).upper()
    settlement["currency_decimals"] = int(currency_decimals)
    settlement["result_receipt_id"] = receipt_id
    settlement["result_artifact_sha256"] = result_artifact_sha256
    settlement["delivery_evidence_sha256"] = _sha256({
        "deliveryRecordedAt": delivery_recorded_at,
        "deliveryStatus": settlement.get("delivery_status"),
        "receiptEvidenceSha256": evidence_sha256,
        "resultArtifactSha256": result_artifact_sha256,
        "route": ROUTE,
    })
