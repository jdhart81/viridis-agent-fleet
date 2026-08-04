"""Fail-closed Fleet to Viridis Security commercial receipt exporter.

The exporter consumes only a fully bound Security Preflight settlement record.
It emits a signed, privacy-minimized candidate plus an exact review packet.
Nothing in this module sends a request or recognizes revenue. A verified
Viridis operator must inspect the evidence and post the candidate from the
private command center before any commercial truth can advance.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


RECEIPT_VERSION = "viridis-commercial-outcome/v1"
SOURCE_SYSTEM = "viridis-fleet"
PRODUCT = "security_preflight"
ROUTE = "security-preflight/security_preflight"
CLASSIFICATION_VERSION = 1
ALLOWED_SURFACES = frozenset({"http-402-v2", "a2a-x402-v2"})
SHA256_HEX_LENGTH = 64


class CommercialExportError(ValueError):
    """The source evidence cannot support a commercial receipt."""


def canonical_json(value: Any) -> str:
    """Match the command center's sorted compact JSON for bounded inputs."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _required_text(record: Mapping[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CommercialExportError(f"{field} is required")
    return value.strip()


def _required_sha256(record: Mapping[str, Any], field: str) -> str:
    value = _required_text(record, field).lower()
    if len(value) != SHA256_HEX_LENGTH or any(
            character not in "0123456789abcdef" for character in value):
        raise CommercialExportError(f"{field} must be a lowercase SHA-256")
    return value


def _iso_utc(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CommercialExportError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise CommercialExportError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise CommercialExportError(f"{field} must include an offset")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _amount_usd(amount_atomic: Any, decimals: Any) -> int | float:
    try:
        amount = int(str(amount_atomic))
        places = int(decimals)
    except (TypeError, ValueError) as exc:
        raise CommercialExportError(
            "amount_atomic and currency_decimals must be integers") from exc
    if amount <= 0 or places != 6:
        raise CommercialExportError(
            "Security Preflight requires positive six-decimal USDC evidence")
    whole, remainder = divmod(amount, 10 ** places)
    return whole if remainder == 0 else amount / (10 ** places)


def _load_private_key(private_key_pkcs8_b64: str) -> Ed25519PrivateKey:
    try:
        raw = base64.b64decode(private_key_pkcs8_b64.strip(), validate=True)
        key = serialization.load_der_private_key(raw, password=None)
    except Exception as exc:
        raise CommercialExportError(
            "Fleet commercial signing key is invalid") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise CommercialExportError(
            "Fleet commercial signing key must be Ed25519 PKCS8")
    return key


def public_key_spki_b64(private_key_pkcs8_b64: str) -> str:
    key = _load_private_key(private_key_pkcs8_b64)
    return base64.b64encode(key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )).decode("ascii")


def _order_reference_sha256(settlement: Mapping[str, Any]) -> str:
    return sha256_json({
        "paymentIdentifierSha256": sha256_text(
            _required_text(settlement, "payment_identifier")),
        "route": ROUTE,
        "txHashSha256": sha256_text(
            _required_text(settlement, "tx_hash")),
    })


def _repeat_purchase(
    settlement: Mapping[str, Any],
    prior_settlements: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    payer = _required_text(settlement, "payer_wallet").lower()
    current_order = _order_reference_sha256(settlement)
    for prior in prior_settlements:
        if (
            prior.get("route") == ROUTE
            and prior.get("self_settle") is False
            and str(prior.get("payer_wallet", "")).strip().lower() == payer
        ):
            prior_order = _order_reference_sha256(prior)
            if prior_order == current_order:
                continue
            return {
                "status": "yes",
                "priorOrderReferenceSha256": prior_order,
                "evidenceSha256": sha256_json({
                    "currentOrderReferenceSha256": current_order,
                    "payerWalletSha256": sha256_text(payer),
                    "priorOrderReferenceSha256": prior_order,
                    "route": ROUTE,
                }),
            }
    return {"status": "unknown"}


def build_commercial_export(
    settlement: Mapping[str, Any],
    *,
    private_key_pkcs8_b64: str,
    key_id: str,
    prior_settlements: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a signed candidate; never post or recognize it automatically."""
    if settlement.get("route") != ROUTE:
        raise CommercialExportError("only the Security Preflight route is eligible")
    if settlement.get("surface") not in ALLOWED_SURFACES:
        raise CommercialExportError("settlement surface is not a current x402 v2 rail")
    if settlement.get("classification_version") != CLASSIFICATION_VERSION:
        raise CommercialExportError("settlement classification is missing or stale")
    if settlement.get("self_settle") is not False:
        raise CommercialExportError("self-settlements cannot become commercial truth")
    if _required_text(settlement, "currency").upper() != "USDC":
        raise CommercialExportError("only exact USDC settlement evidence is supported")
    asset = _required_text(settlement, "asset")
    network = _required_text(settlement, "network")
    timestamp = _iso_utc(settlement.get("timestamp"), "timestamp")
    payment_identifier = _required_text(settlement, "payment_identifier")
    tx_hash = _required_text(settlement, "tx_hash")
    payer_wallet = _required_text(settlement, "payer_wallet").lower()
    amount_usd = _amount_usd(
        settlement.get("amount_atomic"), settlement.get("currency_decimals"))
    result_artifact_sha256 = _required_sha256(
        settlement, "result_artifact_sha256")
    delivery_evidence_sha256 = _required_sha256(
        settlement, "delivery_evidence_sha256")
    result_receipt_id = _required_text(settlement, "result_receipt_id")
    if settlement.get("delivery_status") != "delivered":
        raise CommercialExportError("only a delivered result can be exported")
    delivered_at = _iso_utc(
        settlement.get("delivery_recorded_at"), "delivery_recorded_at")
    settlement_receipt = settlement.get("settlement_receipt")
    if not isinstance(settlement_receipt, dict):
        raise CommercialExportError("settlement_receipt is required")

    order_reference_sha256 = _order_reference_sha256(settlement)
    payment_evidence_sha256 = sha256_json({
        "amountAtomic": str(settlement.get("amount_atomic")),
        "asset": asset,
        "network": network,
        "paymentIdentifierSha256": sha256_text(payment_identifier),
        "settlementReceipt": settlement_receipt,
        "surface": settlement["surface"],
        "txHashSha256": sha256_text(tx_hash),
    })
    source_event_sha256 = sha256_json({
        "deliveryEvidenceSha256": delivery_evidence_sha256,
        "orderReferenceSha256": order_reference_sha256,
        "paymentEvidenceSha256": payment_evidence_sha256,
        "resultArtifactSha256": result_artifact_sha256,
    })
    receipt = {
        "receiptVersion": RECEIPT_VERSION,
        "sourceSystem": SOURCE_SYSTEM,
        "sourceEventSha256": source_event_sha256,
        "product": PRODUCT,
        "orderReferenceSha256": order_reference_sha256,
        "resultArtifactSha256": result_artifact_sha256,
        "payment": {
            "status": "verified",
            "amountUsd": amount_usd,
            "currency": "USDC",
            "evidenceSha256": payment_evidence_sha256,
        },
        "delivery": {
            "status": "delivered",
            "deliveredAt": delivered_at,
            "evidenceSha256": delivery_evidence_sha256,
        },
        "usefulness": {"status": "unknown"},
        "repeatPurchase": _repeat_purchase(settlement, prior_settlements),
        "evidenceReview": {"status": "unreviewed"},
        "occurredAt": timestamp,
        "sanitizedMetadata": {
            "asset": asset,
            "classificationVersion": CLASSIFICATION_VERSION,
            "deliveryStatus": "delivered",
            "network": network,
            "payerWalletSha256": sha256_text(payer_wallet),
            "resultReceiptId": result_receipt_id,
            "route": ROUTE,
            "surface": settlement["surface"],
            "txHashSha256": sha256_text(tx_hash),
        },
    }
    key = _load_private_key(private_key_pkcs8_b64)
    signature = base64.urlsafe_b64encode(
        key.sign(canonical_json(receipt).encode("utf-8"))
    ).decode("ascii").rstrip("=")
    if not isinstance(key_id, str) or not key_id.strip():
        raise CommercialExportError("key_id is required")
    review_packet = {
        "claimBoundary": (
            "Payment and transport delivery are evidenced independently. "
            "Usefulness, repeat demand, recurring revenue, and runtime security "
            "are not inferred."
        ),
        "deliveryEvidenceSha256": delivery_evidence_sha256,
        "orderReferenceSha256": order_reference_sha256,
        "paymentEvidenceSha256": payment_evidence_sha256,
        "resultArtifactSha256": result_artifact_sha256,
        "sourceEventSha256": source_event_sha256,
    }
    review_evidence_sha256 = sha256_json(review_packet)
    return {
        "status": "PENDING_OPERATOR_REVIEW",
        "automaticPostAllowed": False,
        "reviewPacket": {
            **review_packet,
            "evidenceSha256": review_evidence_sha256,
        },
        "commercialImport": {
            "receipt": receipt,
            "signature": {
                "algorithm": "Ed25519",
                "keyId": key_id.strip(),
                "signatureB64Url": signature,
            },
        },
    }
