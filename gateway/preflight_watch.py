"""Free, stateless change detection against an authentic stored assessment.

The caller owns scheduling and current artifacts. This service never fetches
an arbitrary endpoint, executes a scan, saves a watch, or authorizes spending.
An unchanged baseline may still contain findings; reuse never authorizes tools.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERSION = "viridis-preflight-watch-v1"
PATH = "/security-preflight/watch"
RECEIPT_PATH = "/security-preflight/receipts/{receipt_id}"
RECEIPT_ID = re.compile(r"^vsr_[a-f0-9]{24}$")
INPUT_KEYS = {"agent_id", "manifest", "policy", "sample_inputs",
              "subject_profile_sha256"}


def _stable(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_stable(value)).hexdigest()


def discovery(public_base):
    base = public_base.rstrip("/")
    return {
        "version": VERSION,
        "name": "Security Preflight change check",
        "description": "Compare current supplied artifacts with a prior signed "
                       "assessment; quote a new scan only when needed.",
        "endpoint": base + PATH,
        "method": "POST", "price_minor": 0, "state_changing": False,
        "input_schema": {
            "type": "object", "additionalProperties": False,
            "required": ["inputs"],
            "properties": {
                "inputs": {"type": "object", "required": ["agent_id", "manifest"],
                           "additionalProperties": False,
                           "properties": {
                               "agent_id": {"type": "string"},
                               "manifest": {"type": "object"},
                               "policy": {"type": "object"},
                               "sample_inputs": {"type": "array", "items": {"type": "string"}},
                               "subject_profile_sha256": {"type": "string"}}},
                "baseline_receipt_id": {"type": ["string", "null"],
                                        "pattern": RECEIPT_ID.pattern},
            },
        },
        "decisions": ["BASELINE_REQUIRED", "UNCHANGED", "RECHECK_REQUIRED"],
        "triggers": ["inputs_changed", "assessment_expired", "scanner_changed"],
        "public_receipt_template": base + RECEIPT_PATH,
        "buyer_owns_schedule": True,
        "auto_pay": False, "runtime_tested": False,
        "managed_subscription_active": False,
    }


def plan(core, payload, public_base, *, now=None):
    if not isinstance(payload, dict) or set(payload) - {"inputs", "baseline_receipt_id"}:
        raise ValueError("expected inputs and optional baseline_receipt_id")
    inputs = payload.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) - INPUT_KEYS:
        raise ValueError("inputs must contain only documented assessment fields")
    # Reject non-finite JSON even outside the gateway middleware.
    if len(_stable(inputs)) > 131072:
        raise ValueError("assessment inputs exceed 131072 bytes")
    data = core._validate_scan(inputs)
    binding = core.watch_binding(data)
    baseline_id = payload.get("baseline_receipt_id")
    now = now or datetime.now(timezone.utc)
    result = {
        "version": VERSION, "decision": "BASELINE_REQUIRED",
        "reasons": ["no_baseline"], "current_binding": binding,
        "baseline": None, "payment_authorized": False,
        "tool_executed": False, "state_persisted": False,
        "runtime_execution_authorized": False, "runtime_tested": False,
        "managed_subscription_active": False,
    }
    if baseline_id is not None:
        if not isinstance(baseline_id, str) or not RECEIPT_ID.fullmatch(baseline_id):
            raise ValueError("invalid baseline_receipt_id")
        record = core._get_receipt(baseline_id)
        if record.get("status") != "ok":
            raise LookupError("baseline receipt not found")
        receipt, evidence = record["receipt"], record["evidence"]
        if receipt["subject_agent_id"] != data["agent_id"]:
            raise ValueError("baseline belongs to a different agent_id")
        # Verify the signed evidence digest as well as the actual signature.
        # describe() publishes the current trusted signing key; it is never a
        # caller-supplied key. Retired/unavailable keys fail closed.
        description = core.describe()
        key_b64 = description.get("receipt_public_key_b64")
        if not key_b64:
            raise RuntimeError("trusted receipt verification key unavailable")
        try:
            key = Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(
                key_b64 + "=" * (-len(key_b64) % 4)))
            signature = record["signature_b64"]
            key.verify(base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)),
                       _stable(receipt))
            if receipt["evidence_sha256"] != _digest(evidence):
                raise ValueError("evidence digest mismatch")
            issued = datetime.fromisoformat(receipt["issued_at"].replace("Z", "+00:00"))
            expires = datetime.fromisoformat(receipt["expires_at"].replace("Z", "+00:00"))
            if issued.tzinfo is None or expires.tzinfo is None or issued > now or expires <= issued:
                raise ValueError("invalid receipt time interval")
        except Exception as exc:
            raise RuntimeError("baseline receipt integrity check failed") from exc
        previous = evidence.get("subject_binding", {})
        changed = sorted(k for k, v in binding.items() if previous.get(k) != v)
        reasons = []
        if changed:
            reasons.append("inputs_changed" if "sample_inputs_sha256" in previous
                           else "baseline_binding_upgrade_required")
        if expires <= now:
            reasons.append("assessment_expired")
        if receipt.get("scanner", {}).get("version") != description.get("version"):
            reasons.append("scanner_changed")
        result.update({
            "decision": "RECHECK_REQUIRED" if reasons else "UNCHANGED",
            "reasons": reasons, "changed_fields": changed,
            "baseline": {"receipt_id": baseline_id, "expires_at": receipt["expires_at"],
                         "verdict": evidence.get("verdict"),
                         "result_counts": receipt["result_counts"],
                         "evidence_url": public_base.rstrip("/") +
                             RECEIPT_PATH.format(receipt_id=baseline_id)},
        })
    if result["decision"] == "UNCHANGED":
        result["next_action"] = "reuse_assessment_with_existing_findings"
        result["quote_request"] = None
    else:
        result["next_action"] = "fetch_unpaid_quote"
        result["quote_request"] = {
            "method": "POST",
            "url": public_base.rstrip("/") + "/x402/security-preflight/security_preflight",
            "body": inputs,
            "expected_status": 402,
            "authoritative_price": "PAYMENT-REQUIRED",
            "payer_hint_header": "X402-Payer-Address",
            "operator_budget_required": True, "auto_pay": False,
        }
    result["claim_boundary"] = (
        "Comparison of supplied artifacts with a signed static assessment. "
        "Unchanged artifacts can retain findings. This is not runtime safety, "
        "buyer acceptance, scheduled monitoring, a subscription, or payment.")
    return result


def make_watch_route(cores, public_base):
    from starlette.responses import JSONResponse

    async def handler(request):
        core = cores.get("security-preflight")
        if core is None:
            return JSONResponse({"error": "service unavailable"}, status_code=503)
        try:
            payload = await request.json()
            result = plan(core, payload, public_base)
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except LookupError:
            return JSONResponse({"error": "baseline receipt not found"}, status_code=404)
        except (ValueError, TypeError):
            return JSONResponse({"error": "invalid watch inputs or baseline subject"}, status_code=400)
        except Exception:
            return JSONResponse({"error": "baseline verification unavailable"}, status_code=503)
    return handler


def make_receipt_route(cores):
    from starlette.responses import JSONResponse

    async def handler(request):
        receipt_id = request.path_params["receipt_id"]
        if not RECEIPT_ID.fullmatch(receipt_id):
            return JSONResponse({"error": "invalid receipt id"}, status_code=400)
        core = cores.get("security-preflight")
        if core is None:
            return JSONResponse({"error": "service unavailable"}, status_code=503)
        try:
            record = core._get_receipt(receipt_id)
            return JSONResponse(record, status_code=200 if record.get("status") == "ok" else 404,
                                headers={"Cache-Control": "no-store"})
        except Exception:
            return JSONResponse({"error": "receipt store unavailable"}, status_code=503)
    return handler
