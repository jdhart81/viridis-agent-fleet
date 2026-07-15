"""
agent-verified-relay-agent — Core business logic.

VIRIDIS VERIFIED: the consequence wrapper for the agent economy. Any
third-party MCP server can register and have its tool calls relayed through
Viridis rails — every call notarized into a tamper-evident receipt chain
(request hash, response hash, outcome, timing), metered, and billable in
basis points. Economies are cornered by whoever underwrites everyone else's
transactions: this agent turns every MCP server in every registry into
potential rails traffic without Viridis building another leaf service.

Composes with: agent-metering (per-call fees — wired at the gateway),
agent-surety (bonds behind registered providers), agent-notary (commit-reveal
delivery proofs), agent-trust-oracle (receipt history feeds reputation),
agent-arbitration (receipts are the evidence base for rulings).

Custody & trust note: the relay is an EVIDENCE layer, not a proxy-of-record
for funds. It never alters payloads (V4) and its receipts are recomputable by
any party (V2), so a dispute can be arbitrated from receipts alone.

Fleet-standard interface: async process(), async health(), sync describe().

--- INVARIANTS (spec-invariance contract) ---
V1  Registration is SSRF-guarded: https only, port 443/8443 only, no
    userinfo, no IP-literal hosts, no localhost/.local/.internal/.lan
    hostnames, length-capped. A URL that fails any check is rejected with a
    structured envelope and never stored, never fetched.
V2  Receipts are a tamper-evident hash chain per service: each receipt
    commits to the previous receipt's hash, the request hash, and the
    response hash. verify_receipts recomputes the full chain.
V3  Relay is idempotent on call_id: replaying a seen call_id returns the
    original receipt + cached result flagged duplicate=true — the downstream
    service is NOT called again.
V4  Payload fidelity: the downstream request is built from the caller's
    arguments canonically (sorted-key JSON) and the response body is hashed
    exactly as received; the relay never edits, truncates (beyond V10 cap),
    or reorders the downstream result it returns.
V5  Failures are evidence: a downstream error (transport failure, non-200,
    unparseable body, JSON-RPC error) produces BOTH a structured error
    envelope AND a chained receipt with outcome="error". No silent drops.
V6  Fee accounting is deterministic: every completed relay attempt (ok or
    error) accrues exactly fee_minor (integer, fixed at registration) to the
    service's fee ledger; totals are integer sums, recomputable from receipts.
V7  Read surface is pure: get_receipt, verify_receipts, list_services,
    service_stats never mutate state.
V8  Unknown service_id / receipt_id / call_id -> error envelope, never a
    crash; process() never raises on bad input.
V9  Service identity is content-addressed and idempotent: service_id =
    hash(url, provider). Re-registering the same pair returns the existing
    registration; a different URL is a different service. No mutation of a
    registration after creation.
V10 Resource safety: downstream timeout hard-capped (<= 30s), response
    bodies larger than 512 KiB are rejected as errors (and receipted, V5).
"""

import asyncio
import hashlib
import json
import logging
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_GENESIS = "0" * 64
MAX_URL_LEN = 2048
MAX_RESPONSE_BYTES = 512 * 1024          # V10
MAX_TIMEOUT_S = 30                        # V10
DEFAULT_TIMEOUT_S = 20
DEFAULT_FEE_MINOR = 2                     # $0.02 per verified call
ALLOWED_PORTS = {None, 443, 8443}         # V1
BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".lan", ".localdomain",
                         ".localhost", ".home.arpa")
BLOCKED_HOSTS = {"localhost", "metadata.google.internal",
                 "169.254.169.254"}


@dataclass
class AgentConfig:
    name: str
    version: str = "0.1.0"
    debug: bool = False


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentCore:
    """Minimal fleet-standard base. Subclasses override process()/describe()."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.logger = logging.getLogger(config.name)
        self.logger.setLevel(logging.DEBUG if config.debug else logging.INFO)

    async def process(self, input_data: dict) -> dict:
        raise NotImplementedError

    async def health(self) -> dict:
        return {"status": "ok", "agent": self.config.name,
                "version": self.config.version, "timestamp": _utcnow(),
                "checks": {}}

    def describe(self) -> dict:
        return {"name": self.config.name, "version": self.config.version,
                "description": "override me", "capabilities": [],
                "inputs": {}, "outputs": {}}

    def _err(self, message: str, *, error_type: str = "Error",
             field: str = "", value: Any = None, constraint: str = "") -> dict:
        return {"status": "error", "error_type": error_type, "field": field,
                "value": value, "constraint": constraint, "message": message,
                "timestamp": _utcnow()}

    def _ok(self, data: Any = None) -> dict:
        return {"status": "ok", "data": data, "error": None,
                "timestamp": _utcnow()}


class ValidationError(ValueError):
    def __init__(self, message, field="", value=None, constraint=""):
        super().__init__(message)
        self.field, self.value, self.constraint = field, value, constraint


# --------------------------------------------------------------------------- #
# V1 — SSRF guard
# --------------------------------------------------------------------------- #
def _is_ip_literal(host: str) -> bool:
    import ipaddress
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def validate_service_url(url: str) -> str:
    """V1: static SSRF guard. Returns the normalized URL or raises."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LEN:
        raise ValidationError("url must be a non-empty string (<= 2048 chars)",
                              field="url", constraint="str, 1..2048")
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise ValidationError("only https service URLs are accepted",
                              field="url", value=parts.scheme,
                              constraint="scheme == https")
    if parts.username or parts.password:
        raise ValidationError("userinfo in URL is not allowed", field="url",
                              constraint="no user:pass@")
    host = (parts.hostname or "").lower()
    if not host:
        raise ValidationError("url has no host", field="url", constraint="host required")
    if parts.port not in ALLOWED_PORTS:
        raise ValidationError("port not allowed", field="url", value=parts.port,
                              constraint="443 or 8443 only")
    if (host in BLOCKED_HOSTS or _is_ip_literal(host)
            or "." not in host
            or any(host.endswith(s) for s in BLOCKED_HOST_SUFFIXES)):
        raise ValidationError("host is not a public DNS name", field="url",
                              value=host, constraint="public FQDN; no IPs, "
                              "no localhost/.local/.internal")
    return url


# --------------------------------------------------------------------------- #
# Downstream MCP transport (injectable for tests; stdlib in production)
# --------------------------------------------------------------------------- #
def _default_transport(url: str, body: bytes, timeout_s: int) -> tuple:
    """POST JSON-RPC to a streamable-http MCP endpoint.
    Returns (http_status, content_type, body_text)."""
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"content-type": "application/json",
                 "accept": "application/json, text/event-stream",
                 "user-agent": "viridis-verified-relay/0.1"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # nosec V1-guarded
        raw = resp.read(MAX_RESPONSE_BYTES + 1)                   # V10
        return (resp.status, resp.headers.get("content-type", ""),
                raw.decode("utf-8", "replace"))


def parse_mcp_response(content_type: str, body_text: str) -> dict:
    """Extract the JSON-RPC message from a JSON or SSE response body."""
    if "text/event-stream" in (content_type or ""):
        datas = [ln[5:].strip() for ln in body_text.splitlines()
                 if ln.startswith("data:")]
        if not datas:
            raise ValueError("empty SSE stream")
        return json.loads(datas[-1])
    return json.loads(body_text)


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        default=str).encode()).hexdigest()


def _chain(prev: str, payload: dict) -> str:
    return hashlib.sha256((prev + json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        default=str)).encode()).hexdigest()


@dataclass
class Service:
    service_id: str
    url: str
    provider: str
    description: str = ""
    fee_minor: int = DEFAULT_FEE_MINOR
    registered_at: str = field(default_factory=_utcnow)
    receipts: List[dict] = field(default_factory=list)
    call_ids: Dict[str, int] = field(default_factory=dict)   # call_id -> idx
    results: Dict[str, dict] = field(default_factory=dict)   # call_id -> result (V3)
    fees_accrued_minor: int = 0                               # V6

    def public(self) -> dict:
        ok = sum(1 for r in self.receipts if r["outcome"] == "ok")
        return {"service_id": self.service_id, "url": self.url,
                "provider": self.provider, "description": self.description,
                "fee_minor": self.fee_minor,
                "registered_at": self.registered_at,
                "calls_total": len(self.receipts), "calls_ok": ok,
                "calls_error": len(self.receipts) - ok,
                "fees_accrued_minor": self.fees_accrued_minor}


class VerifiedRelayCore(AgentCore):
    """Viridis Verified — receipted relay for third-party MCP services."""

    def __init__(self, config: Optional[AgentConfig] = None,
                 transport: Optional[Callable] = None):
        super().__init__(config or AgentConfig(name="agent-verified-relay-agent"))
        self._services: Dict[str, Service] = {}
        self._receipt_index: Dict[str, tuple] = {}   # receipt_id -> (sid, idx)
        self._transport = transport or _default_transport
        self._rpc_seq = 0

    # ------------------------------------------------------------------ #
    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object",
                                 error_type="ValidationError", field="input",
                                 value=type(input_data).__name__, constraint="dict")
            action = input_data.get("action")
            handler = {
                "register_service": self._register_service,
                "call_verified": self._call_verified,
                "get_receipt": self._get_receipt,
                "verify_receipts": self._verify_receipts,
                "list_services": self._list_services,
                "service_stats": self._service_stats,
            }.get(action)
            if handler is None:
                return self._err(
                    f"unknown action '{action}'", error_type="ValidationError",
                    field="action", value=action,
                    constraint="one of: register_service, call_verified, "
                               "get_receipt, verify_receipts, list_services, "
                               "service_stats")
            if handler is self._call_verified:
                # V10 corollary (found in prod 2026-07-15): the downstream
                # HTTP call is blocking; run it in a worker thread so the
                # host event loop keeps serving — otherwise a slow downstream
                # stalls every mount and a self-referential relay (relaying a
                # service hosted on this same gateway) deadlocks to timeout.
                return await asyncio.to_thread(handler, input_data)
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError",
                             field=e.field, value=e.value, constraint=e.constraint)
        except Exception as e:                                          # V8
            self.logger.exception("verified-relay process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # ------------------------------------------------------------------ #
    def _register_service(self, d: dict) -> dict:
        url = validate_service_url(d.get("url"))                        # V1
        provider = d.get("provider")
        if not provider or not isinstance(provider, str) or len(provider) > 128:
            raise ValidationError("provider must be a non-empty string (<=128)",
                                  field="provider", value=provider,
                                  constraint="str, 1..128")
        fee = d.get("fee_minor", DEFAULT_FEE_MINOR)
        if isinstance(fee, bool) or not isinstance(fee, int) or fee < 0:
            raise ValidationError("fee_minor must be a non-negative integer",
                                  field="fee_minor", value=fee, constraint="int >= 0")
        sid = "vsvc-" + _hash({"url": url, "provider": provider})[:16]  # V9
        existing = self._services.get(sid)
        if existing is not None:                                        # V9 idempotent
            return self._ok({**existing.public(), "duplicate": True})
        svc = Service(service_id=sid, url=url, provider=provider,
                      description=str(d.get("description", ""))[:280],
                      fee_minor=fee)
        self._services[sid] = svc
        return self._ok({**svc.public(), "duplicate": False})

    # ------------------------------------------------------------------ #
    def _get_service(self, d: dict) -> Service:
        sid = d.get("service_id")
        svc = self._services.get(sid)
        if svc is None:                                                 # V8
            raise ValidationError("unknown service", field="service_id",
                                  value=sid, constraint="must be registered")
        return svc

    def _append_receipt(self, svc: Service, call_id: str, tool: str,
                        request_hash: str, response_hash: str,
                        outcome: str, detail: str, elapsed_ms: int) -> dict:
        prev = svc.receipts[-1]["receipt_hash"] if svc.receipts else _GENESIS
        body = {"call_id": call_id, "service_id": svc.service_id,
                "tool": tool, "request_hash": request_hash,
                "response_hash": response_hash, "outcome": outcome,
                "detail": detail[:200], "fee_minor": svc.fee_minor,
                "relayed_at": _utcnow(), "elapsed_ms": elapsed_ms,
                "prev_hash": prev}
        receipt = {**body, "receipt_hash": _chain(prev, body)}          # V2
        receipt_id = f"vrc-{receipt['receipt_hash'][:16]}"
        receipt["receipt_id"] = receipt_id
        svc.receipts.append(receipt)
        svc.call_ids[call_id] = len(svc.receipts) - 1
        svc.fees_accrued_minor += svc.fee_minor                         # V6
        self._receipt_index[receipt_id] = (svc.service_id,
                                           len(svc.receipts) - 1)
        return receipt

    def _call_verified(self, d: dict) -> dict:
        svc = self._get_service(d)
        call_id = d.get("call_id")
        if not call_id or not isinstance(call_id, str) or len(call_id) > 128:
            raise ValidationError("call_id must be a non-empty string (<=128)",
                                  field="call_id", value=call_id,
                                  constraint="str, 1..128")
        if call_id in svc.call_ids:                                     # V3
            idx = svc.call_ids[call_id]
            return self._ok({"receipt": svc.receipts[idx],
                             "result": svc.results.get(call_id),
                             "duplicate": True})
        tool = d.get("tool")
        if not tool or not isinstance(tool, str) or len(tool) > 128:
            raise ValidationError("tool must be a non-empty string (<=128)",
                                  field="tool", value=tool, constraint="str, 1..128")
        arguments = d.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValidationError("arguments must be an object",
                                  field="arguments",
                                  value=type(arguments).__name__, constraint="dict")
        timeout_s = d.get("timeout_s", DEFAULT_TIMEOUT_S)
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, int) \
                or not 1 <= timeout_s <= MAX_TIMEOUT_S:                 # V10
            raise ValidationError("timeout_s must be an int in [1, 30]",
                                  field="timeout_s", value=timeout_s,
                                  constraint="1..30")

        self._rpc_seq += 1
        rpc = {"jsonrpc": "2.0", "id": self._rpc_seq, "method": "tools/call",
               "params": {"name": tool, "arguments": arguments}}
        request_bytes = json.dumps(rpc, sort_keys=True,
                                   separators=(",", ":")).encode()      # V4
        request_hash = hashlib.sha256(request_bytes).hexdigest()

        started = datetime.now(timezone.utc)
        outcome, detail, result, response_hash = "error", "", None, _hash(None)
        try:
            status, ctype, body_text = self._transport(
                svc.url, request_bytes, timeout_s)
            if len(body_text.encode("utf-8", "replace")) > MAX_RESPONSE_BYTES:
                detail = "response exceeds 512KiB cap"                  # V10
            elif status != 200:
                detail = f"downstream HTTP {status}"
                response_hash = hashlib.sha256(
                    body_text.encode("utf-8", "replace")).hexdigest()
            else:
                response_hash = hashlib.sha256(
                    body_text.encode("utf-8", "replace")).hexdigest()   # V4
                msg = parse_mcp_response(ctype, body_text)
                if msg.get("error"):
                    detail = f"jsonrpc error: {msg['error'].get('message', '')}"
                else:
                    outcome, result = "ok", msg.get("result")
        except Exception as e:                                          # V5
            detail = f"transport: {type(e).__name__}: {e}"
        elapsed_ms = int((datetime.now(timezone.utc) - started)
                         .total_seconds() * 1000)

        receipt = self._append_receipt(svc, call_id, tool, request_hash,
                                       response_hash, outcome, detail,
                                       elapsed_ms)
        if outcome == "ok":
            svc.results[call_id] = result                               # V3 cache
            return self._ok({"receipt": receipt, "result": result,
                             "duplicate": False})
        # V5: error envelope AND a chained receipt.
        return {**self._err(f"verified relay failed: {detail}",
                            error_type="DownstreamError", field="service_id",
                            value=svc.service_id, constraint="downstream must "
                            "return a valid JSON-RPC result"),
                "receipt": receipt}

    # ------------------------------------------------------------------ #
    def _get_receipt(self, d: dict) -> dict:                            # V7
        rid = d.get("receipt_id")
        loc = self._receipt_index.get(rid)
        if loc is None:                                                 # V8
            raise ValidationError("unknown receipt", field="receipt_id",
                                  value=rid, constraint="must exist")
        sid, idx = loc
        return self._ok(self._services[sid].receipts[idx])

    def _verify_receipts(self, d: dict) -> dict:                        # V2/V7
        svc = self._get_service(d)
        prev = _GENESIS
        for i, r in enumerate(svc.receipts):
            body = {k: v for k, v in r.items()
                    if k not in ("receipt_hash", "receipt_id")}
            if r["prev_hash"] != prev or _chain(prev, body) != r["receipt_hash"]:
                return self._ok({"service_id": svc.service_id,
                                 "valid": False, "broken_at_index": i})
            prev = r["receipt_hash"]
        # V6: fee ledger must equal what the receipts imply.
        fees_recomputed = sum(r["fee_minor"] for r in svc.receipts)
        return self._ok({"service_id": svc.service_id, "valid": True,
                         "receipt_count": len(svc.receipts),
                         "fees_accrued_minor": svc.fees_accrued_minor,
                         "fees_recomputed_minor": fees_recomputed,
                         "fees_consistent":
                             fees_recomputed == svc.fees_accrued_minor})

    def _list_services(self, d: dict) -> dict:                          # V7
        items = [s.public() for s in self._services.values()]
        return self._ok({"count": len(items), "services": items})

    def _service_stats(self, d: dict) -> dict:                          # V7
        return self._ok(self._get_service(d).public())

    # ------------------------------------------------------------------ #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {
            "services": len(self._services),
            "receipts": sum(len(s.receipts) for s in self._services.values()),
            "fees_accrued_minor": sum(s.fees_accrued_minor
                                      for s in self._services.values())}
        return h

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "Viridis Verified — receipted relay wrapping any "
                           "third-party MCP server with tamper-evident "
                           "delivery receipts, metered fees, and rails "
                           "composition (bonds, arbitration, reputation).",
            "capabilities": ["register_service", "call_verified", "get_receipt",
                             "verify_receipts", "list_services", "service_stats"],
            "inputs": {"action": "str", "url": "https URL (public FQDN)",
                       "provider": "str", "service_id": "str",
                       "tool": "str", "arguments": "dict", "call_id": "str",
                       "fee_minor": "int >= 0", "timeout_s": "int 1..30"},
            "outputs": {"status": "ok|error", "data": "per action"},
            "a2a_role": "verified-relay",
        }


def build(config: Optional[AgentConfig] = None,
          transport: Optional[Callable] = None) -> VerifiedRelayCore:
    return VerifiedRelayCore(config, transport=transport)
