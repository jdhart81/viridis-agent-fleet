#!/usr/bin/env python3
"""Credential gate for state-changing MCP calls.

Discovery and read-only tools remain public. Raw MCP writes on the fleet's
shared infrastructure rails require a caller credential. The short rollout
mode ``observe`` accepts legacy unauthenticated EnergyAI mutation calls while
all other mutations are already enforced; ``enforce`` closes that final
compatibility window.

Configuration (secrets stay in the deployment environment):

    VIRIDIS_STATE_AUTH_MODE=off|observe|enforce
    VIRIDIS_STATE_AUTH_TOKENS_JSON={
      "viridis:energyai": {"token": "...", "role": "agent"},
      "fleet-admin": {"token": "...", "role": "admin"}
    }

Wire format:

    Authorization: Bearer <token>
    X-Viridis-Agent-Id: viridis:energyai
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("viridis.state_change_auth")

# Unknown tools on these infrastructure mounts fail closed as mutations. This
# makes newly added write tools protected by default; maintainers explicitly
# add only proven read-only tools here.
OPEN_READ_ONLY_TOOLS = {
    "identity": {
        "resolve_agent", "discover_agents", "list_registrations",
        "describe_agent",
    },
    "trust": {
        "score_agent", "verify_attestation", "history", "describe_agent",
    },
    "escrow": {
        "escrow_status", "list_escrows", "verify_audit", "describe_agent",
    },
    "metering": {
        "usage_summary", "sla_report", "verify_chain", "list_meters",
        "list_events", "usage_timeseries", "describe_agent",
    },
    "arbitration": {
        "verify_ruling", "get_case", "list_cases", "describe_agent",
    },
    "compute-ledger": {
        "footprint", "verify_attestation", "verify_chain", "list_entries",
        "carbon_receipt", "get_inventory", "list_inventories",
        "verify_inventory_chain", "describe_agent",
    },
    "covenant": {
        "check_act", "covenant_status", "verify_audit", "list_covenants",
        "describe_agent",
    },
    "hive": {
        "job_status", "audit_job", "verify_audit", "list_solvers",
        "describe_agent",
    },
    "provenance": {
        "get_certificate", "verify_certificate", "lineage", "list_records",
        "get_artifact", "verify_artifact", "list_artifacts",
        "describe_agent",
    },
    "offsets": {
        "verra_supply", "verra_retirement_record", "settlement_batch",
        "net_position", "verify_certificate", "book", "get_purchase",
        "verify_retirement", "project_funding", "list_projects",
        "disbursement_schedule", "verify_disbursement", "describe_agent",
    },
    "surety": {
        "bond_status", "list_bonds", "verify_audit", "price_bond",
        "describe_agent",
    },
    "notary": {
        "verify", "commitment_status", "list_commitments", "describe_agent",
    },
    "verified": {
        "get_receipt", "verify_receipts", "list_services", "service_stats",
        "describe_agent",
    },
    "green-router": {
        "estimate_footprint", "rank_backends", "get_certificate",
        "verify_certificate", "describe_agent",
    },
    "subscriptions": {
        "list_plans", "get_plan", "subscription_status", "usage_summary",
        "mrr_summary", "describe_agent",
    },
    "payments": {
        "payout_onboarding_status", "payee_balance", "weave_status",
        "underwrite_service_bond", "quote_insured_job",
    },
}

# Only these exact EnergyAI calls remain temporarily compatible in observe
# mode. Dry runs are read-only and never need a credential.
OBSERVE_COMPATIBILITY_TOOLS = {
    ("offsets", "buy_offset"),
    ("offsets", "buy_offset_budget"),
    ("compute-ledger", "record_work"),
}

_CLAIM_FIELDS = ("buyer", "agent_id")
_lock = threading.Lock()
_counters = {
    "authenticated": 0,
    "observed_legacy": 0,
    "rejected": 0,
    "identity_mismatch": 0,
}
_DIAGNOSTIC_BUCKET_MAX = 128
_DIAGNOSTIC_LABEL_MAX = 64
_diagnostic_counts = {
    "authenticated_by_route_action": {},
    "observed_legacy_by_route_action": {},
    "rejected_by_route_action_reason": {},
}
_last_rejection: Optional[dict] = None


@dataclass(frozen=True)
class Mutation:
    mount: str
    tool: str
    arguments: Dict[str, Any]
    request_id: Any


@dataclass(frozen=True)
class Principal:
    actor: str
    role: str


@dataclass(frozen=True)
class AuthenticationAttempt:
    principal: Optional[Principal]
    reason: str
    principal_class: str


def _mode() -> str:
    value = str(os.environ.get("VIRIDIS_STATE_AUTH_MODE", "off")).lower()
    return value if value in {"off", "observe", "enforce"} else "enforce"


def _token_config() -> Dict[str, dict]:
    raw = os.environ.get("VIRIDIS_STATE_AUTH_TOKENS_JSON", "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.error("VIRIDIS_STATE_AUTH_TOKENS_JSON is invalid JSON")
        return {}
    if not isinstance(parsed, dict):
        return {}
    result = {}
    for actor, config in parsed.items():
        if not isinstance(actor, str) or not actor:
            continue
        if isinstance(config, str):
            token, role = config, "agent"
        elif isinstance(config, dict):
            token = config.get("token")
            role = config.get("role", "agent")
        else:
            continue
        if (isinstance(token, str) and len(token) >= 24
                and role in {"agent", "admin"}):
            result[actor] = {"token": token, "role": role}
    return result


def _headers(scope) -> Dict[bytes, list[bytes]]:
    result: Dict[bytes, list[bytes]] = {}
    for name, value in scope.get("headers", []):
        result.setdefault(name.lower(), []).append(value)
    return result


def _authentication_attempt(scope) -> AuthenticationAttempt:
    headers = _headers(scope)
    auth_values = headers.get(b"authorization", [])
    actor_values = headers.get(b"x-viridis-agent-id", [])
    if not auth_values and not actor_values:
        return AuthenticationAttempt(
            None, "missing_credentials", "uncredentialed")
    if len(auth_values) != 1 or len(actor_values) != 1:
        return AuthenticationAttempt(
            None, "malformed_credentials", "uncredentialed")
    try:
        auth = auth_values[0].decode("utf-8")
        actor = actor_values[0].decode("utf-8").strip()
    except UnicodeDecodeError:
        return AuthenticationAttempt(
            None, "malformed_credentials", "uncredentialed")
    if not auth.startswith("Bearer ") or not actor:
        return AuthenticationAttempt(
            None, "malformed_credentials", "uncredentialed")
    supplied = auth[len("Bearer "):]
    config = _token_config().get(actor)
    if not config:
        return AuthenticationAttempt(
            None, "unknown_principal", "unknown")
    principal_class = f"configured-{config['role']}"
    if not hmac.compare_digest(supplied, config["token"]):
        return AuthenticationAttempt(
            None, "invalid_token", principal_class)
    return AuthenticationAttempt(
        Principal(actor=actor, role=config["role"]),
        "authenticated",
        principal_class,
    )


def _authenticate(scope) -> Optional[Principal]:
    """Compatibility helper retained for focused callers and tests."""
    return _authentication_attempt(scope).principal


def _mutation(scope, payload: Any) -> Optional[Mutation]:
    if scope.get("type") != "http" or scope.get("method") != "POST":
        return None
    parts = [part for part in str(scope.get("path", "")).split("/") if part]
    if len(parts) < 2 or parts[-1] != "mcp":
        return None
    mount = parts[0]
    if mount not in OPEN_READ_ONLY_TOOLS or not isinstance(payload, dict):
        return None
    if payload.get("method") != "tools/call":
        return None
    params = payload.get("params")
    if not isinstance(params, dict):
        return None
    tool = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(tool, str) or not isinstance(arguments, dict):
        return None
    if tool in OPEN_READ_ONLY_TOOLS[mount]:
        return None
    if (mount == "offsets" and tool in {"buy_offset", "buy_offset_budget"}
            and arguments.get("dry_run") is True):
        return None
    return Mutation(mount, tool, arguments, payload.get("id"))


def _identity_matches(principal: Principal, mutation: Mutation) -> bool:
    if principal.role == "admin":
        return True
    for field in _CLAIM_FIELDS:
        claimed = mutation.arguments.get(field)
        if claimed is not None and claimed != principal.actor:
            return False
    return True


def _observe_compatible(
        mutation: Mutation, attempt: AuthenticationAttempt) -> bool:
    """Allow only the exact, genuinely credential-less EnergyAI legacy path.

    An invalid token, unknown principal, malformed credential, identity
    mismatch, or another claimed actor never falls through the compatibility
    window. Observe mode is a bounded migration bridge, not an authentication
    bypass.
    """
    if attempt.reason != "missing_credentials":
        return False
    if (mutation.mount, mutation.tool) not in OBSERVE_COMPATIBILITY_TOOLS:
        return False
    claimed = [
        mutation.arguments.get(field)
        for field in _CLAIM_FIELDS
        if mutation.arguments.get(field) is not None
    ]
    return bool(claimed) and all(
        actor == "viridis:energyai" for actor in claimed)


def _diagnostic_label(value: str) -> str:
    """Return a bounded, non-sensitive label safe for public health output."""
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value))
    return text[:_DIAGNOSTIC_LABEL_MAX] or "unknown"


def _increment_diagnostic(bucket_name: str, key: str) -> None:
    bucket = _diagnostic_counts[bucket_name]
    if key not in bucket:
        if "_overflow" in bucket or len(bucket) >= _DIAGNOSTIC_BUCKET_MAX - 1:
            key = "_overflow"
    bucket[key] = bucket.get(key, 0) + 1


def _record_outcome(
        outcome: str, mutation: Mutation, reason: str,
        principal_class: str) -> None:
    global _last_rejection
    route_action = (
        f"{_diagnostic_label(mutation.mount)}/"
        f"{_diagnostic_label(mutation.tool)}"
    )
    with _lock:
        if outcome == "rejected":
            safe_reason = _diagnostic_label(reason)
            safe_principal = _diagnostic_label(principal_class)
            key = f"{route_action}/{safe_reason}/{safe_principal}"
            _increment_diagnostic(
                "rejected_by_route_action_reason", key)
            _last_rejection = {
                "mount": _diagnostic_label(mutation.mount),
                "tool": _diagnostic_label(mutation.tool),
                "reason": safe_reason,
                "principal_class": safe_principal,
                "at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        elif outcome == "authenticated":
            _increment_diagnostic(
                "authenticated_by_route_action", route_action)
        elif outcome == "observed_legacy":
            _increment_diagnostic(
                "observed_legacy_by_route_action", route_action)


def status() -> dict:
    with _lock:
        counters = dict(_counters)
        diagnostics = {
            name: dict(values)
            for name, values in _diagnostic_counts.items()
        }
        last_rejection = (
            dict(_last_rejection) if _last_rejection is not None else None)
    return {
        "mode": _mode(),
        "configured_principals": len(_token_config()),
        **counters,
        "diagnostics": {
            "privacy": (
                "bounded route/action/reason aggregates only; no tokens, "
                "arguments, request ids, IPs, caller fingerprints, or actor "
                "identities"),
            "bucket_limit": _DIAGNOSTIC_BUCKET_MAX,
            **diagnostics,
            "last_rejection": last_rejection,
        },
    }


def _increment(name: str) -> None:
    with _lock:
        _counters[name] += 1


class StateChangeAuthMiddleware:
    """ASGI middleware that replays the request body after classification."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        chunks = []
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunks.append(message.get("body", b""))
            more = bool(message.get("more_body", False))
        body = b"".join(chunks)
        try:
            payload = json.loads(body) if body else None
        except (UnicodeDecodeError, ValueError):
            payload = None
        mutation = _mutation(scope, payload)
        mode = _mode()
        auth_state = "not-applicable"
        principal = None
        if mutation is not None and mode != "off":
            attempt = _authentication_attempt(scope)
            principal = attempt.principal
            if principal is not None and _identity_matches(principal, mutation):
                auth_state = "authenticated"
                _increment("authenticated")
                _record_outcome(
                    "authenticated", mutation, "authenticated",
                    attempt.principal_class)
            elif principal is not None:
                auth_state = "identity-mismatch"
                _increment("identity_mismatch")
                rejection_reason = "identity_mismatch"
            else:
                auth_state = "missing-or-invalid"
                rejection_reason = attempt.reason
            compatible = (
                mode == "observe"
                and _observe_compatible(mutation, attempt)
            )
            if auth_state != "authenticated" and not compatible:
                _increment("rejected")
                _record_outcome(
                    "rejected", mutation, rejection_reason,
                    attempt.principal_class)
                status_code = 403 if auth_state == "identity-mismatch" else 401
                message = (
                    "authenticated actor does not match the requested identity"
                    if status_code == 403 else
                    "credential required for state-changing fleet tool"
                )
                response = {
                    "jsonrpc": "2.0",
                    "id": mutation.request_id,
                    "error": {"code": -32001, "message": message},
                }
                encoded = json.dumps(response, separators=(",", ":")).encode()
                await send({
                    "type": "http.response.start",
                    "status": status_code,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(encoded)).encode()),
                        (b"cache-control", b"no-store"),
                        (b"x-viridis-state-auth", auth_state.encode()),
                    ],
                })
                await send({"type": "http.response.body", "body": encoded})
                return
            if auth_state != "authenticated":
                auth_state = "observed-legacy"
                _increment("observed_legacy")
                _record_outcome(
                    "observed_legacy", mutation, attempt.reason,
                    attempt.principal_class)

        replayed = False

        async def replay_receive():
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def auth_send(message):
            if mutation is not None and message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(
                    (b"x-viridis-state-auth", auth_state.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, replay_receive, auth_send)
