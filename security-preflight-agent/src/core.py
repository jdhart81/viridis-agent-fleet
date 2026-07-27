"""Deterministic, input-redacted security preflight for MCP/agent manifests.

The service inspects only caller-supplied metadata. It never fetches a URL,
executes a tool, or claims to test a deployed runtime. Successful scans emit a
signed ``viridis-security-receipt-v1`` receipt that the Viridis Agent Market
can verify and, with a separate explicit import action, attach to a profile.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
except ImportError:  # pragma: no cover - the production image provides this
    serialization = None
    Ed25519PrivateKey = None


VERSION = "1.0.0"
ISSUER_ID = "viridis-security-preflight"
PROTOCOL = "viridis-security-receipt-v1"
MAX_INPUT_BYTES = 131_072
MAX_TOOLS = 100
MAX_SAMPLES = 20
MAX_SAMPLE_CHARS = 8_192
RECEIPT_TTL_DAYS = 30
AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")

CLAIM_BOUNDARY = (
    "Covers only the buyer-supplied manifest, tool schemas, policy, and sample "
    "inputs evaluated by deterministic static checks. It does not fetch or "
    "test the deployed runtime and does not certify the agent as secure, "
    "vulnerability-free, or independently audited."
)

RULES = (
    {
        "id": "VSP-001",
        "title": "HTTPS endpoint declaration",
        "source": "bounded deployment-surface hygiene",
    },
    {
        "id": "VSP-002",
        "title": "Authentication declaration",
        "source": "bounded access-control hygiene",
    },
    {
        "id": "VSP-003",
        "title": "Closed tool input schemas",
        "source": "T-IB-29 distilled rule",
    },
    {
        "id": "VSP-004",
        "title": "Human approval for high-impact tools",
        "source": "bounded tool-authority hygiene",
    },
    {
        "id": "VSP-005",
        "title": "Non-conflicting tool policy",
        "source": "deny-by-default policy hygiene",
    },
    {
        "id": "VSP-006",
        "title": "Static injection indicators",
        "source": "distilled prompt-boundary patterns",
    },
)

HIGH_IMPACT_TERMS = frozenset({
    "admin", "approve", "delete", "deploy", "email", "exec", "message",
    "pay", "publish", "refund", "send", "shell", "transfer", "withdraw",
    "write",
})

INJECTION_PATTERNS = (
    ("VSP-INJ-001", re.compile(
        r"\b(ignore|disregard|override)\b.{0,60}\b("
        r"previous|prior|system|developer|instructions?)\b", re.I | re.S)),
    ("VSP-INJ-002", re.compile(
        r"\b(reveal|print|exfiltrate|leak)\b.{0,60}\b("
        r"secret|token|credential|system prompt|api key)\b", re.I | re.S)),
    ("VSP-INJ-003", re.compile(
        r"\b(do not|don't)\b.{0,30}\b(tell|inform|notify)\b.{0,30}\b("
        r"user|operator|owner)\b", re.I | re.S)),
)


class PreflightError(ValueError):
    """Caller-safe validation error."""

    def __init__(self, message: str, field: str,
                 error_type: str = "ValidationError"):
        super().__init__(message)
        self.field = field
        self.error_type = error_type


def _stable(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _check(check_id: str, status: str, severity: str, summary: str,
           evidence_path: str) -> dict:
    return {
        "check_id": check_id,
        "status": status,
        "severity": severity,
        "summary": summary,
        "evidence_path": evidence_path,
    }


def _string_list(value: Any, field: str, maximum: int = MAX_TOOLS) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > maximum:
        raise PreflightError(
            f"{field} must be a list with at most {maximum} entries", field)
    result: List[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip() or len(item) > 160:
            raise PreflightError(
                f"{field}[{index}] must be a non-empty string up to 160 chars",
                f"{field}[{index}]")
        result.append(item.strip())
    return result


def _tool_name(tool: dict, index: int) -> str:
    value = tool.get("name")
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise PreflightError(
            "each manifest tool requires a non-empty name up to 160 chars",
            f"manifest.tools[{index}].name")
    return value.strip()


def _tool_schema(tool: dict) -> Any:
    for field in ("input_schema", "inputSchema", "parameters"):
        if field in tool:
            return tool[field]
    return None


def _high_impact(name: str) -> bool:
    tokens = {
        token for token in re.findall(r"[a-z0-9]+", name.casefold())
        if token
    }
    return bool(tokens & HIGH_IMPACT_TERMS)


def _load_signing_key():
    if serialization is None or Ed25519PrivateKey is None:
        raise PreflightError(
            "receipt signing dependency is unavailable",
            "SECURITY_PREFLIGHT_SIGNING_KEY_PKCS8_B64",
            "ServiceUnavailable")
    encoded = os.environ.get(
        "SECURITY_PREFLIGHT_SIGNING_KEY_PKCS8_B64", "").strip()
    if not encoded:
        raise PreflightError(
            "receipt signer is not configured",
            "SECURITY_PREFLIGHT_SIGNING_KEY_PKCS8_B64",
            "ServiceUnavailable")
    try:
        raw = base64.b64decode(encoded, validate=True)
        key = serialization.load_der_private_key(raw, password=None)
    except Exception as exc:
        raise PreflightError(
            "receipt signer configuration is invalid",
            "SECURITY_PREFLIGHT_SIGNING_KEY_PKCS8_B64",
            "ServiceUnavailable") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise PreflightError(
            "receipt signer must be an Ed25519 PKCS8 private key",
            "SECURITY_PREFLIGHT_SIGNING_KEY_PKCS8_B64",
            "ServiceUnavailable")
    return key


def _signer_fingerprint() -> Optional[str]:
    try:
        public = _load_signing_key().public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return hashlib.sha256(public).hexdigest()
    except PreflightError:
        return None


class SecurityPreflightCore:
    """Fleet-standard deterministic Security Preflight core."""

    KNOWN_ACTIONS = frozenset({"scan", "get_receipt"})
    READ_ACTIONS = frozenset({"get_receipt"})

    def __init__(self):
        self._receipts: Dict[str, dict] = {}

    @staticmethod
    def _validate_scan(payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise PreflightError("input_data must be an object", "input_data")
        agent_id = payload.get("agent_id")
        if not isinstance(agent_id, str) or not AGENT_ID_RE.fullmatch(agent_id):
            raise PreflightError(
                "agent_id must be 3..128 lowercase letters, digits, '.', '_' "
                "or '-', beginning with a letter or digit",
                "agent_id")
        manifest = payload.get("manifest")
        if not isinstance(manifest, dict):
            raise PreflightError("manifest must be an object", "manifest")
        policy = payload.get("policy", {})
        if policy is None:
            policy = {}
        if not isinstance(policy, dict):
            raise PreflightError("policy must be an object", "policy")
        samples = payload.get("sample_inputs", [])
        if samples is None:
            samples = []
        if not isinstance(samples, list) or len(samples) > MAX_SAMPLES:
            raise PreflightError(
                f"sample_inputs must contain at most {MAX_SAMPLES} strings",
                "sample_inputs")
        for index, sample in enumerate(samples):
            if not isinstance(sample, str) or len(sample) > MAX_SAMPLE_CHARS:
                raise PreflightError(
                    f"sample_inputs[{index}] must be a string up to "
                    f"{MAX_SAMPLE_CHARS} characters",
                    f"sample_inputs[{index}]")
        try:
            encoded_size = len(_stable({
                "agent_id": agent_id,
                "manifest": manifest,
                "policy": policy,
                "sample_inputs": samples,
            }).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise PreflightError(
                "inputs must be finite JSON data", "input_data") from exc
        if encoded_size > MAX_INPUT_BYTES:
            raise PreflightError(
                f"canonical input exceeds {MAX_INPUT_BYTES} bytes",
                "input_data")
        tools = manifest.get("tools", [])
        if tools is None:
            tools = []
        if not isinstance(tools, list) or len(tools) > MAX_TOOLS:
            raise PreflightError(
                f"manifest.tools must contain at most {MAX_TOOLS} objects",
                "manifest.tools")
        normalized_tools = []
        for index, tool in enumerate(tools):
            if not isinstance(tool, dict):
                raise PreflightError(
                    "each manifest tool must be an object",
                    f"manifest.tools[{index}]")
            normalized_tools.append(
                {"name": _tool_name(tool, index), "schema": _tool_schema(tool)})
        allowed = _string_list(
            policy.get("allowed_tools"), "policy.allowed_tools")
        denied = _string_list(
            policy.get("denied_tools"), "policy.denied_tools")
        approvals = _string_list(
            policy.get("approval_required_tools"),
            "policy.approval_required_tools")
        return {
            "agent_id": agent_id,
            "manifest": manifest,
            "tools": normalized_tools,
            "policy_present": bool(policy),
            "allowed": allowed,
            "denied": denied,
            "approvals": approvals,
            "samples": samples,
        }

    def _paid_preflight(self, payload: dict) -> Optional[dict]:
        """Fail before settlement when inputs or receipt signing are unusable."""
        try:
            if payload.get("action", "scan") != "scan":
                raise PreflightError(
                    "paid Security Preflight supports only scan", "action")
            self._validate_scan(payload)
            _load_signing_key()
            return None
        except PreflightError as exc:
            return {
                "status": "error",
                "error_type": exc.error_type,
                "field": exc.field,
                "message": str(exc),
                "claim_boundary": CLAIM_BOUNDARY,
            }

    @staticmethod
    def _checks(data: dict) -> List[dict]:
        checks: List[dict] = []
        manifest = data["manifest"]
        endpoint = manifest.get("endpoint")
        if isinstance(endpoint, str) and endpoint.startswith("https://"):
            checks.append(_check(
                "VSP-001", "pass", "info",
                "Manifest declares an HTTPS endpoint.",
                "manifest.endpoint"))
        else:
            checks.append(_check(
                "VSP-001", "warning", "medium",
                "No HTTPS endpoint is declared; runtime transport was not "
                "verified.",
                "manifest.endpoint"))

        auth = manifest.get("auth")
        declared_auth = bool(auth) and str(auth).strip().casefold() not in {
            "none", "null", "false", "{}",
        }
        checks.append(_check(
            "VSP-002",
            "pass" if declared_auth else "warning",
            "info" if declared_auth else "medium",
            ("Manifest declares an authentication mode."
             if declared_auth else
             "No authentication mode is declared; access control remains "
             "unverified."),
            "manifest.auth"))

        tools = data["tools"]
        if not tools:
            checks.append(_check(
                "VSP-003", "warning", "medium",
                "No tool schemas were supplied, so tool inputs were not "
                "evaluated.",
                "manifest.tools"))
        for index, tool in enumerate(tools):
            schema = tool["schema"]
            path = f"manifest.tools[{index}].input_schema"
            if not isinstance(schema, dict):
                checks.append(_check(
                    "VSP-003", "finding", "high",
                    f"Tool '{tool['name']}' does not declare an object input "
                    "schema.",
                    path))
            elif schema.get("type") != "object":
                checks.append(_check(
                    "VSP-003", "finding", "high",
                    f"Tool '{tool['name']}' input schema is not typed as an "
                    "object.",
                    path))
            elif schema.get("additionalProperties") is not False:
                checks.append(_check(
                    "VSP-003", "warning", "medium",
                    f"Tool '{tool['name']}' accepts undeclared input fields.",
                    path + ".additionalProperties"))
            else:
                checks.append(_check(
                    "VSP-003", "pass", "info",
                    f"Tool '{tool['name']}' has a closed object input schema.",
                    path))

        approvals = set(data["approvals"])
        known_tools = {item["name"] for item in tools}
        high_impact = {
            item["name"] for item in tools if _high_impact(item["name"])}
        missing_approvals = sorted(high_impact - approvals)
        if missing_approvals:
            checks.append(_check(
                "VSP-004", "finding", "high",
                "High-impact tools lack an explicit approval requirement: "
                + ", ".join(missing_approvals),
                "policy.approval_required_tools"))
        elif high_impact:
            checks.append(_check(
                "VSP-004", "pass", "info",
                "All detected high-impact tools require explicit approval.",
                "policy.approval_required_tools"))
        else:
            checks.append(_check(
                "VSP-004", "pass", "info",
                "No high-impact tool names were detected.",
                "manifest.tools"))
        unknown_approvals = sorted(approvals - known_tools)
        if unknown_approvals:
            checks.append(_check(
                "VSP-004", "warning", "low",
                "Approval policy names tools absent from the manifest: "
                + ", ".join(unknown_approvals),
                "policy.approval_required_tools"))

        overlap = sorted(set(data["allowed"]) & set(data["denied"]))
        if overlap:
            checks.append(_check(
                "VSP-005", "finding", "high",
                "Policy both allows and denies: " + ", ".join(overlap),
                "policy"))
        elif data["policy_present"]:
            checks.append(_check(
                "VSP-005", "pass", "info",
                "No allow/deny conflict was detected in the supplied policy.",
                "policy"))
        else:
            checks.append(_check(
                "VSP-005", "warning", "medium",
                "No tool policy was supplied.",
                "policy"))

        descriptions: List[str] = []
        for value in (
                manifest.get("description"), manifest.get("instructions")):
            if isinstance(value, str):
                descriptions.append(value)
        descriptions.extend(data["samples"])
        matched = sorted({
            pattern_id
            for value in descriptions
            for pattern_id, pattern in INJECTION_PATTERNS
            if pattern.search(value)
        })
        if matched:
            checks.append(_check(
                "VSP-006", "finding", "high",
                "Static injection indicators matched: " + ", ".join(matched)
                + ". Raw text is not stored in the result.",
                "manifest.description|manifest.instructions|sample_inputs"))
        else:
            checks.append(_check(
                "VSP-006", "pass", "info",
                "No configured static injection indicator matched.",
                "manifest.description|manifest.instructions|sample_inputs"))
        return checks

    @staticmethod
    def _counts(checks: Iterable[dict]) -> dict:
        materialized = list(checks)
        return {
            "checks": len(materialized),
            "passed": sum(item["status"] == "pass" for item in materialized),
            "warnings": sum(
                item["status"] == "warning" for item in materialized),
            "findings": sum(
                item["status"] == "finding" for item in materialized),
            "errors": 0,
        }

    def _scan(self, payload: dict) -> dict:
        data = self._validate_scan(payload)
        key = _load_signing_key()
        checks = self._checks(data)
        counts = self._counts(checks)
        verdict = (
            "fail" if counts["findings"]
            else "review" if counts["warnings"]
            else "pass"
        )
        coverage = ["manifest"]
        if data["tools"]:
            coverage.append("tool-schemas")
        if data["policy_present"]:
            coverage.append("tool-policy")
        if data["samples"]:
            coverage.append("sample-inputs")
        scanner = {
            "name": "Viridis Security Preflight",
            "version": VERSION,
            "canon_digest": _sha256(RULES),
        }
        evidence = {
            "protocol": "viridis-security-preflight-evidence-v1",
            "subject_agent_id": data["agent_id"],
            "verdict": verdict,
            "posture": "SCANNED",
            "coverage": coverage,
            "scanner": scanner,
            "result_counts": counts,
            "checks": checks,
            "claim_boundary": CLAIM_BOUNDARY,
            "input_redacted": True,
            "runtime_tested": False,
            "independent_assessment": False,
        }
        evidence_sha256 = _sha256(evidence)
        issued = _now()
        unsigned = {
            "protocol": PROTOCOL,
            "issuer_id": ISSUER_ID,
            "subject_agent_id": data["agent_id"],
            "posture": "SCANNED",
            "coverage": coverage,
            "scanner": scanner,
            "result_counts": counts,
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_sha256": evidence_sha256,
            "issued_at": _iso(issued),
            "expires_at": _iso(issued + timedelta(days=RECEIPT_TTL_DAYS)),
        }
        receipt_id = "vsr_" + _sha256(unsigned)[:24]
        public_base = os.environ.get(
            "PUBLIC_BASE",
            "https://mcp.viridisconservation.com").rstrip("/")
        receipt = {
            **unsigned,
            "receipt_id": receipt_id,
            "evidence_url": (
                f"{public_base}/security-preflight/receipts/{receipt_id}"),
        }
        signature_b64 = _b64url(key.sign(_stable(receipt).encode("utf-8")))
        public_record = {
            "status": "ok",
            "service": "viridis-security-preflight",
            "receipt": receipt,
            "signature_b64": signature_b64,
            "evidence": evidence,
            "privacy": {
                "raw_manifest_stored": False,
                "raw_policy_stored": False,
                "raw_samples_stored": False,
            },
        }
        self._receipts[receipt_id] = public_record
        return {
            **public_record,
            "verdict": verdict,
            "market_import": {
                "automatic": False,
                "reason": (
                    "Profile ownership and import consent are not inferred "
                    "from a payment wallet."),
                "market_endpoint":
                    "https://mcp.viridisconservation.com/network/mcp",
                "market_tool": "import_security_receipt",
                "arguments": {
                    "receipt": receipt,
                    "signature_b64": signature_b64,
                },
                "relation_disclosure": (
                    "ViridisNorth LLC operates both the issuer and seeded "
                    "Viridis fleet profiles; the Market labels that common "
                    "control rather than treating it as independent proof."),
            },
            "upgrade_path": {
                "offer": "Viridis Security developer evidence pack",
                "starting_price_usd": 99,
                "included": [
                    "manual finding review",
                    "remediation priorities",
                    "receipt refresh after fixes",
                ],
                "purchase_automated": False,
            },
        }

    def _get_receipt(self, receipt_id: Any) -> dict:
        if not isinstance(receipt_id, str) or not receipt_id.startswith("vsr_"):
            raise PreflightError(
                "receipt_id must be a Viridis Security receipt id",
                "receipt_id")
        record = self._receipts.get(receipt_id)
        if record is None:
            return {
                "status": "error",
                "error_type": "NotFound",
                "message": "receipt not found",
                "receipt_id": receipt_id,
            }
        return dict(record)

    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                raise PreflightError(
                    "input_data must be an object", "input_data")
            action = input_data.get("action", "scan")
            if action == "scan":
                return self._scan(input_data)
            if action == "get_receipt":
                return self._get_receipt(input_data.get("receipt_id"))
            raise PreflightError(
                "unknown action; supported actions: scan, get_receipt",
                "action")
        except PreflightError as exc:
            return {
                "status": "error",
                "error_type": exc.error_type,
                "field": exc.field,
                "message": str(exc),
                "claim_boundary": CLAIM_BOUNDARY,
            }
        except Exception as exc:  # fail closed without returning caller input
            return {
                "status": "error",
                "error_type": "InternalError",
                "message": (
                    "security preflight failed: " + type(exc).__name__),
                "claim_boundary": CLAIM_BOUNDARY,
            }

    async def health(self) -> dict:
        fingerprint = _signer_fingerprint()
        required = os.environ.get(
            "SECURITY_PREFLIGHT_REQUIRED", "0").strip().casefold() in {
                "1", "true", "yes", "on",
            }
        return {
            "status": "ok" if fingerprint or not required else "degraded",
            "agent": "security-preflight-agent",
            "version": VERSION,
            "signer_required": required,
            "signer_ready": bool(fingerprint),
            "signer_public_key_sha256": fingerprint,
            "stored_receipts": len(self._receipts),
            "raw_inputs_stored": False,
            "runtime_fetches_enabled": False,
        }

    def describe(self) -> dict:
        return {
            "name": "security-preflight-agent",
            "version": VERSION,
            "description": (
                "Deterministic preflight of caller-supplied MCP manifests, "
                "tool schemas, policies, and sample inputs with signed, "
                "input-redacted receipts."),
            "capabilities": [
                "mcp-manifest-security-preflight",
                "tool-schema-analysis",
                "tool-authority-policy-check",
                "static-injection-indicator-scan",
                "signed-security-receipts",
            ],
            "inputs": [
                "agent_id", "manifest", "policy", "sample_inputs",
            ],
            "outputs": [
                "verdict", "checks", "signed_receipt",
                "explicit_market_import_payload",
            ],
            "claim_boundary": CLAIM_BOUNDARY,
            "receipt_protocol": PROTOCOL,
            "receipt_issuer_id": ISSUER_ID,
            "privacy": "raw caller inputs are neither persisted nor returned",
        }
