"""Gated HTTP x402 v2 lane for CDP Bazaar discovery (X2 invariants).

This module is deliberately separate from ``x402_rail.py``.  The proven
in-band MCP/v1 rail stays frozen; only the Wave-6 HTTP front doors opt into
this module when ``X402_V2_ENABLED=1``.  The implementation follows the
official v1-to-v2 migration guide directly (headers + JSON) while reusing the
existing rail's configuration, atomic-price helper, and request-bound CDP JWT.

--- INVARIANTS (X2) ---
X2-1  V1 FROZEN: disabled-by-default; the caller takes its original v1 path.
X2-2  MAINNET DOMAIN: Base-mainnet native USDC advertises EIP-712 name
       ``USD Coin``; Base Sepolia advertises ``USDC``.
X2-3  FRESH JWT: every facilitator verify and settle call asks x402_rail for a
       new method/host/path-bound CDP JWT.
X2-4  SETTLE-BEFORE-SERVE: no tool executes until settle succeeds.
X2-5  EXACTLY ONCE: a stable payment identifier is durably recorded in the
       existing per-agent ``consumed_x402`` state before tool execution.
X2-6  FAIL CLOSED: malformed input, verify/settle failure, timeout, Bazaar
       rejection, or persistence failure never executes the tool.
X2-7  TWO SWITCHES: master X402_ENABLED and X402_V2_ENABLED must both be on;
       an incomplete v2 configuration refuses instead of falling back free.
X2-8  PRICE DERIVATION: atomic USDC is always PRICE_MINOR * 10^4 via the
       existing rail helper, never a route-local constant.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple

import x402_rail

logger = logging.getLogger("viridis.x402_v2")

X402_VERSION = 2
BASE_MAINNET_CAIP2 = "eip155:8453"
BASE_SEPOLIA_CAIP2 = "eip155:84532"
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
PAYMENT_REQUIRED_HEADER = "PAYMENT-REQUIRED"
PAYMENT_SIGNATURE_HEADER = "PAYMENT-SIGNATURE"
PAYMENT_RESPONSE_HEADER = "PAYMENT-RESPONSE"
EXTENSION_RESPONSES_HEADER = "EXTENSION-RESPONSES"

_feedback_lock = threading.Lock()
_extension_feedback: Dict[str, dict] = {}


def requested() -> bool:
    """True only when the separate HTTP-v2 feature flag is explicitly on."""
    return os.environ.get("X402_V2_ENABLED", "0") == "1"


def _cfg() -> dict:
    """V2-specific network overrides; the proven v1 env remains untouched."""
    legacy = x402_rail._cfg()  # frozen module, read-only reuse
    network = os.environ.get("X402_V2_NETWORK", BASE_MAINNET_CAIP2)
    default_asset = (BASE_SEPOLIA_USDC if network == BASE_SEPOLIA_CAIP2
                     else x402_rail.BASE_MAINNET_USDC)
    return {
        "pay_to": os.environ.get("X402_V2_PAY_TO", legacy["pay_to"]),
        "facilitator": os.environ.get(
            "X402_V2_FACILITATOR_URL", legacy["facilitator"]).rstrip("/"),
        "network": network,
        "asset": os.environ.get("X402_V2_ASSET", default_asset),
        "asset_name": os.environ.get("X402_V2_ASSET_NAME", ""),
        "asset_version": os.environ.get("X402_V2_ASSET_VERSION", "2"),
        "cdp_key_id": legacy["cdp_key_id"],
        "cdp_key_secret": legacy["cdp_key_secret"],
        "timeout_s": int(os.environ.get(
            "X402_V2_TIMEOUT_S", str(legacy["timeout_s"]))),
    }


def is_enabled() -> bool:
    """X2-7: both flags plus a complete v2 endpoint configuration."""
    c = _cfg()
    return (requested() and x402_rail.is_enabled()
            and bool(c["pay_to"]) and bool(c["facilitator"])
            and bool(c["network"]) and bool(c["asset"]))


def _asset_name(c: dict) -> str:
    configured = str(c.get("asset_name", "")).strip()
    if configured:
        return configured
    if (c.get("network") == BASE_MAINNET_CAIP2
            and str(c.get("asset", "")).lower()
            == x402_rail.BASE_MAINNET_USDC.lower()):
        return "USD Coin"
    return "USDC"


def _b64_json(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return base64.b64encode(raw).decode("ascii")


def parse_header(value: Any) -> Optional[dict]:
    """Decode one v2 base64-JSON header without ever raising."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        raw = base64.b64decode(value.strip(), validate=True)
        decoded = json.loads(raw.decode("utf-8"))
        return decoded if isinstance(decoded, dict) else None
    except Exception:
        return None


def _matches_schema(value: Any, schema: dict) -> bool:
    """Small JSON-Schema-2020-12 subset used by our fixed tool schemas."""
    if not isinstance(schema, dict):
        return True
    if "const" in schema and value != schema["const"]:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    declared = schema.get("type")
    allowed = declared if isinstance(declared, list) else [declared]
    if declared is not None:
        checks = {
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "null": lambda v: v is None,
        }
        if not any(kind in checks and checks[kind](value) for kind in allowed):
            return False
    if isinstance(value, dict):
        required = schema.get("required", [])
        if any(key not in value for key in required):
            return False
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            if any(key not in props for key in value):
                return False
        for key, child in value.items():
            if key in props and not _matches_schema(child, props[key]):
                return False
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        if any(not _matches_schema(item, schema["items"]) for item in value):
            return False
    return True


def build_bazaar_extension(method: str, input_schema: dict,
                           input_example: dict, output_example: dict) -> dict:
    """Build the official Bazaar v2 info/schema pattern for GET or POST."""
    method = str(method).upper()
    if method == "GET":
        input_info = {"type": "http", "method": "GET",
                      "queryParams": input_example}
        input_contract = {
            "type": "object",
            "properties": {
                "type": {"type": "string", "const": "http"},
                "method": {"type": "string", "enum": ["GET"]},
                "queryParams": {"type": "object", **input_schema},
            },
            "required": ["type", "method", "queryParams"],
            "additionalProperties": False,
        }
    elif method == "POST":
        input_info = {"type": "http", "method": "POST",
                      "bodyType": "json", "body": input_example}
        input_contract = {
            "type": "object",
            "properties": {
                "type": {"type": "string", "const": "http"},
                "method": {"type": "string", "enum": ["POST"]},
                "bodyType": {"type": "string", "const": "json"},
                "body": input_schema,
            },
            "required": ["type", "method", "bodyType", "body"],
            "additionalProperties": False,
        }
    else:
        raise ValueError("Bazaar HTTP method must be GET or POST")
    output_info = {"type": "json", "example": output_example}
    output_contract = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "const": "json"},
            "example": {"type": "object", "additionalProperties": True},
        },
        "required": ["type", "example"],
        "additionalProperties": False,
    }
    extension = {
        "info": {"input": input_info, "output": output_info},
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"input": input_contract,
                           "output": output_contract},
            "required": ["input", "output"],
            "additionalProperties": False,
        },
    }
    if not _matches_schema(extension["info"], extension["schema"]):
        raise ValueError("Bazaar info example does not validate against schema")
    return extension


def build_payment_required(agent: str, tool: str, price_minor: int,
                           resource_url: str, method: str,
                           metadata: dict, cfg: Optional[dict] = None) -> dict:
    """X2-2/X2-8: build one spec-correct v2 PaymentRequired object."""
    c = cfg or _cfg()
    description = str(metadata["description"])
    if len(description) > 500:
        raise ValueError("x402 resource description exceeds 500 characters")
    extension = build_bazaar_extension(
        method, metadata["input_schema"], metadata["input_example"],
        metadata["output_example"])
    resource = {
        "url": resource_url,
        "description": description,
        "mimeType": "application/json",
        "serviceName": str(metadata.get(
            "service_name", "Viridis Agent Fleet")),
        "tags": list(metadata.get(
            "tags", ["climate", "compliance", "agent-api", agent]))[:5],
    }
    if metadata.get("category"):
        resource["category"] = str(metadata["category"])
    if metadata.get("icon_url"):
        resource["iconUrl"] = str(metadata["icon_url"])
    return {
        "x402Version": X402_VERSION,
        "error": "PAYMENT-SIGNATURE required",
        "resource": resource,
        "accepts": [{
            "scheme": "exact",
            "network": c["network"],
            "asset": c["asset"],
            "amount": x402_rail.price_atomic(price_minor),
            "payTo": c["pay_to"],
            "maxTimeoutSeconds": 120,
            "extra": {"name": _asset_name(c),
                      "version": str(c.get("asset_version", "2"))},
        }],
        "extensions": {"bazaar": extension},
    }


def _sanitize_extension_response(raw_header: Optional[str]) -> dict:
    if not raw_header:
        return {"status": "missing"}
    decoded = parse_header(raw_header)
    if decoded is None:
        return {"status": "malformed"}
    value = decoded.get("bazaar")
    if not isinstance(value, dict):
        return {"status": "missing", "raw_keys": sorted(decoded)[:10]}
    clean = {key: value[key] for key in
             ("status", "rejectedReason", "reason", "code") if key in value}
    clean.setdefault("status", "unknown")
    return clean


def _record_feedback(agent: str, tool: str, phase: str, feedback: dict) -> None:
    with _feedback_lock:
        entry = _extension_feedback.setdefault(f"{agent}/{tool}", {})
        entry[phase] = {**feedback, "at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def _extension_rejected(feedback: dict) -> bool:
    return str(feedback.get("status", "")).lower() == "rejected"


def status() -> dict:
    """Health-ready v2 flag/config and last Bazaar verify/settle feedback."""
    c = _cfg()
    with _feedback_lock:
        feedback = json.loads(json.dumps(_extension_feedback))
    return {
        "requested": requested(),
        "enabled": is_enabled(),
        "active_protocol": 2 if is_enabled() else 1,
        "network": c["network"] if requested() else None,
        "asset_name": _asset_name(c) if requested() else None,
        "bazaar_extension_responses": feedback,
    }


def _facilitator_post(url: str, body: dict, c: dict) -> Tuple[dict, dict]:
    """X2-3: stdlib transport with a fresh existing-rail JWT per call."""
    parts = urllib.parse.urlsplit(url)
    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = {"content-type": "application/json"}
    if c.get("cdp_key_id") and c.get("cdp_key_secret"):
        token = x402_rail.cdp_jwt(
            c["cdp_key_id"], c["cdp_key_secret"], "POST",
            parts.netloc, parts.path)
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=c["timeout_s"]) as response:
        payload = json.loads(response.read().decode("utf-8"))
        response_headers = {str(k).lower(): str(v)
                            for k, v in response.headers.items()}
        return payload, response_headers


def _accepted_matches(supplied: Any, advertised: dict) -> bool:
    if not isinstance(supplied, dict):
        return False
    for key in ("scheme", "network", "asset", "amount", "payTo"):
        if str(supplied.get(key, "")) != str(advertised.get(key, "")):
            return False
    return True


def bind_and_validate_payload(payload: dict, payment_required: dict) -> Tuple[Optional[dict], str]:
    """Bind public resource/Bazaar metadata and reject payment mismatches."""
    if not isinstance(payload, dict) or payload.get("x402Version") != 2:
        return None, "wrong_x402_version"
    advertised = payment_required["accepts"][0]
    if not _accepted_matches(payload.get("accepted"), advertised):
        return None, "accepted_requirements_mismatch"
    supplied_resource = payload.get("resource")
    expected_resource = payment_required["resource"]
    if (supplied_resource is not None
            and (not isinstance(supplied_resource, dict)
                 or supplied_resource.get("url") != expected_resource["url"])):
        return None, "resource_mismatch"
    supplied_extensions = payload.get("extensions")
    if (supplied_extensions is not None
            and (not isinstance(supplied_extensions, dict)
                 or ("bazaar" in supplied_extensions
                     and supplied_extensions["bazaar"]
                     != payment_required["extensions"]["bazaar"]))):
        return None, "bazaar_extension_mismatch"
    bound = dict(payload)
    bound["resource"] = expected_resource
    bound_extensions = dict(supplied_extensions or {})
    bound_extensions["bazaar"] = payment_required["extensions"]["bazaar"]
    bound["extensions"] = bound_extensions
    return bound, "ok"


def payment_identifier(payload: dict, header_value: str) -> str:
    """Prefer the official idempotency extension, then EIP-3009 nonce."""
    extensions = payload.get("extensions")
    if isinstance(extensions, dict):
        identifier = extensions.get("payment-identifier")
        if isinstance(identifier, dict):
            info = identifier.get("info")
            if isinstance(info, dict) and isinstance(info.get("id"), str):
                return "id:" + info["id"]
    inner = payload.get("payload")
    if isinstance(inner, dict):
        auth = inner.get("authorization") or inner.get("permit2Authorization")
        if isinstance(auth, dict) and auth.get("nonce") is not None:
            return "nonce:" + str(auth["nonce"])
    return "header:" + hashlib.sha256(header_value.encode()).hexdigest()


def verify_and_settle(payload: dict, payment_required: dict,
                      agent: str, tool: str, cfg: Optional[dict] = None,
                      _transport: Optional[
                          Callable[[str, dict, dict], Tuple[dict, dict]]] = None,
                      ) -> dict:
    """X2-3/4/6: verify, inspect Bazaar response, then settle."""
    c = cfg or _cfg()
    post = _transport or _facilitator_post
    try:
        if not is_enabled():
            return {"settled": False, "reason": "x402_v2_disabled"}
        bound, reason = bind_and_validate_payload(payload, payment_required)
        if bound is None:
            return {"settled": False, "reason": reason}
        requirements = payment_required["accepts"][0]
        envelope = {"x402Version": 2, "paymentPayload": bound,
                    "paymentRequirements": requirements}
        base = c["facilitator"]
        verify, verify_headers = post(f"{base}/verify", envelope, c)
        verify_feedback = _sanitize_extension_response(
            verify_headers.get(EXTENSION_RESPONSES_HEADER.lower()))
        _record_feedback(agent, tool, "verify", verify_feedback)
        if _extension_rejected(verify_feedback):
            return {"settled": False, "reason": "extension_rejected:verify",
                    "extension_responses": {"verify": verify_feedback}}
        if not (isinstance(verify, dict) and verify.get("isValid") is True):
            invalid = (verify.get("invalidReason") if isinstance(verify, dict)
                       else "verify_failed")
            return {"settled": False, "reason": f"verify:{invalid}",
                    "extension_responses": {"verify": verify_feedback}}
        settle, settle_headers = post(f"{base}/settle", envelope, c)
        settle_feedback = _sanitize_extension_response(
            settle_headers.get(EXTENSION_RESPONSES_HEADER.lower()))
        _record_feedback(agent, tool, "settle", settle_feedback)
        feedback = {"verify": verify_feedback, "settle": settle_feedback}
        if not (isinstance(settle, dict) and settle.get("success") is True):
            failed = (settle.get("errorReason") if isinstance(settle, dict)
                      else "settle_failed")
            return {"settled": False, "reason": f"settle:{failed}",
                    "extension_responses": feedback}
        tx = settle.get("transaction") or settle.get("txHash")
        if not tx:
            return {"settled": False, "reason": "settle:no_tx_hash",
                    "extension_responses": feedback}
        return {
            "settled": True,
            "serve": not _extension_rejected(settle_feedback),
            "reason": ("extension_rejected:settle"
                       if _extension_rejected(settle_feedback) else "ok"),
            "tx_hash": str(tx),
            "network": requirements["network"],
            "amount_atomic": requirements["amount"],
            "settlement_receipt": settle,
            "extension_responses": feedback,
        }
    except Exception as exc:
        logger.warning("x402 v2 verify/settle failed (%s) — refusing",
                       type(exc).__name__)
        return {"settled": False, "reason": f"exception:{type(exc).__name__}"}


def response_headers(payment_required: dict) -> dict:
    return {
        PAYMENT_REQUIRED_HEADER: _b64_json(payment_required),
        "Access-Control-Expose-Headers": (
            f"{PAYMENT_REQUIRED_HEADER}, {PAYMENT_RESPONSE_HEADER}"),
    }


def settlement_headers(result: dict) -> dict:
    receipt = result.get("settlement_receipt") or {
        "success": bool(result.get("settled")),
        "transaction": result.get("tx_hash", ""),
        "network": result.get("network", ""),
    }
    return {
        PAYMENT_RESPONSE_HEADER: _b64_json(receipt),
        "X-Payment-Tx": str(result.get("tx_hash", "")),
        "Access-Control-Expose-Headers": (
            f"{PAYMENT_REQUIRED_HEADER}, {PAYMENT_RESPONSE_HEADER}"),
    }
