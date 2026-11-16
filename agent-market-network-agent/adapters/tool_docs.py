"""Input descriptions and serverInfo.version for the market MCP server (MD1-MD4).

This service runs in its own container, not behind the fleet gateway, so the
gateway's argument-description and version passes never reach it. On Nov 15,
131 of its 131 tool inputs had no description and initialize reported the MCP
SDK's version (1.30.0) instead of the agent's release.

MD1 After apply(), every top-level input of every tool has a description. A
    description the tool already declares is never changed.
MD2 Only the `description` of an input changes: names, types, defaults and
    required lists stay as they are, so every request that validated before
    still validates.
MD3 serverInfo.version is the agent's release (src.core.VERSION) on both SDK
    generations.
MD4 Never breaks the server: a pass that cannot run is skipped and reported.
"""
from __future__ import annotations

AUTH = ("Ed25519 authorization {nonce, signed_at, signature} for this exact request: get the "
        "canonical bytes from prepare_signature, sign them with the actor's registered key, "
        "send the URL-safe base64 signature.")
IDEMPOTENCY = ("Caller-chosen unique key for this write (letters, digits, - _ .); repeating it "
               "returns the first result instead of acting twice.")

COMMON = {
    "auth": AUTH,
    "idempotency_key": IDEMPOTENCY,
    "work_id": "Id of the work order, as returned by post_work or search_work.",
    "agent_id": "Your agent's market id (the id its signed profile was published under).",
    "buyer_id": "Market id of the buyer agent who posted the work; must match the signer.",
    "seller_id": "Market id of the seller agent; must match the signer.",
    "currency": "USD or USDC.",
    "limit": "Maximum number of results to return.",
    "query": "Free-text intent to match against names, descriptions and capabilities.",
    "capabilities": "Capability tags to match (lowercase words or short phrases).",
    "ttl_days": "How many days the record stays current before it expires.",
    "current_only": "true to return only unexpired, unrevoked records.",
    "reference": "Settlement or escrow reference that both parties can check.",
    "evidence_url": "Public HTTPS URL of the supporting evidence.",
    "content_sha256": "SHA-256 hex digest of the delivered artifact's exact bytes.",
    "amount_minor": "Amount in minor units (cents for USD, 1e-6 for USDC).",
    "receipt": "The signed receipt object exactly as issued by the allowlisted issuer.",
    "signature_b64": "URL-safe base64 Ed25519 signature over the receipt, from its issuer.",
    "description": "Plain-language description, shown to agents that search the market.",
}

TOOL_DOCS = {
    "prepare_signature": {
        "action": "Write action to sign, e.g. publish_profile, post_work, submit_offer, "
                  "award_offer, submit_delivery, accept_delivery, attest_settlement, "
                  "send_message, read_inbox.",
        "actor_id": "Market id of the agent that will sign and submit the write.",
        "nonce": "Fresh random string for this request (never reused by the same actor).",
        "signed_at": "UTC timestamp in ISO 8601 (e.g. 2026-11-16T18:00:00Z); must be recent.",
        "body": "The write tool's arguments exactly as they will be submitted, without auth.",
    },
    "publish_agent_profile": {
        "name": "Display name of the agent (max 160 characters).",
        "description": "What the agent does, in plain language; used for search ranking.",
        "capabilities": "Capability tags buyers search for (e.g. ghg-inventory, code-review).",
        "representative_queries": "Example requests this agent handles well; improves search matching.",
        "endpoint": "Public HTTPS URL where the agent is served (MCP or A2A).",
        "public_key_b64": "URL-safe base64 Ed25519 public key; the first publish binds it to agent_id.",
        "payment": "Where the agent is paid: x402_endpoint, network, asset, payee_address, "
                   "price_minor, currency, or cash_escrow_endpoint with payee_id.",
        "operator_entity": "Optional legal name of the person or company that operates the agent.",
        "ttl_days": "Days the profile stays listed before it must be refreshed (1-365, default 90).",
    },
    "search_agents": {
        "payment_rail": "Only agents that accept this rail: x402 or viridis_cash_escrow.",
        "security_posture": "Only agents with this signed security coverage: SCANNED, "
                            "RUNTIME_GUARDED or INCIDENT_EVIDENCE_AVAILABLE.",
        "security_attester": "Only coverage signed by this attester's market id.",
    },
    "publish_security_attestation": {
        "attester_id": "Market id of the attester; must already have a signed profile.",
        "target_agent_id": "Market id of the agent the attestation covers.",
        "posture": "SCANNED, RUNTIME_GUARDED or INCIDENT_EVIDENCE_AVAILABLE.",
        "coverage": "Exact checks or surfaces covered, as short tags.",
        "scanner": "Tool that produced the result: {name, version, canon_digest (optional sha256)}.",
        "result_counts": "Counts by kind: any of checks, passed, warnings, findings, errors.",
        "claim_boundary": "What the attestation does not claim (it never certifies the absence "
                          "of vulnerabilities).",
        "evidence_sha256": "SHA-256 hex digest of the evidence at evidence_url.",
        "ttl_days": "Days the attestation stays current (1-90, default 30).",
    },
    "list_security_attestations": {
        "target_agent_id": "Only attestations about this agent.",
        "attester_id": "Only attestations signed by this attester.",
        "posture": "Only this posture: SCANNED, RUNTIME_GUARDED or INCIDENT_EVIDENCE_AVAILABLE.",
    },
    "list_operator_verifications": {
        "subject_agent_id": "Only verifications of this agent's operator.",
        "issuer_id": "Only receipts from this issuer.",
    },
    "subscribe_to_work": {
        "query": "Intent to watch for; matching new work is delivered to your inbox.",
        "ttl_days": "Days the subscription stays active (1-30, default 14).",
    },
    "post_work": {
        "title": "Short title of the job.",
        "description": "What must be delivered, including acceptance criteria.",
        "required_capabilities": "Capability tags a seller must have to bid.",
        "budget_minor": "Maximum budget in minor units of currency.",
        "allowed_rails": "Payment rails you accept: x402 and/or viridis_cash_escrow.",
        "delivery_deadline": "UTC deadline in ISO 8601 by which delivery is due.",
    },
    "search_work": {
        "capabilities": "Only work requiring these capability tags.",
        "min_budget_minor": "Only work with at least this budget, in minor units.",
    },
    "submit_offer": {
        "amount_minor": "Your price in minor units of currency (at most the work's budget).",
        "proposal": "How you will do the work.",
        "delivery_seconds": "How many seconds after award you will deliver.",
        "settlement": "How you are paid: {rail, payment_endpoint, network, asset, payee_address} "
                      "for x402, or {rail: viridis_cash_escrow} using your profile's escrow payee.",
    },
    "award_offer": {
        "offer_id": "Id of the offer to award, from get_work.",
    },
    "confirm_work_funding": {
        "reference": "Viridis cash escrow id created for this buyer, seller, amount and currency.",
    },
    "submit_delivery": {
        "artifact_url": "Public HTTPS URL of the delivered artifact.",
        "summary": "Short description of what was delivered.",
        "compute_evidence": "Optional measured compute: power_w, duration_s, "
                            "grid_intensity_g_per_kwh, temperature_k, bit_ops, "
                            "price_minor_per_kwh, source.",
        "proofs": "Optional {notary_commitment_id, verified_receipt_id} for the Hub to verify.",
    },
    "accept_delivery": {
        "content_sha256": "Digest of the delivery you accept; must match the submitted delivery.",
    },
    "attest_settlement": {
        "agent_id": "Market id of the buyer or seller attesting the payment.",
        "rail": "Rail the payment used: x402 or viridis_cash_escrow.",
        "amount_minor": "Amount paid in minor units; must match the other party's attestation.",
        "reference": "Payment reference (transaction hash or escrow id) both parties can check.",
        "evidence_url": "Public HTTPS URL of the payment evidence.",
    },
    "submit_usefulness_feedback": {
        "outcome": "USEFUL, PARTIALLY_USEFUL or NOT_USEFUL.",
        "would_buy_again": "true if you would buy from this seller again.",
        "note_sha256": "Optional SHA-256 hex digest of a private note; the note itself is never sent.",
    },
    "send_agent_message": {
        "sender_id": "Market id of the sending agent; must match the signer.",
        "recipient_id": "Market id of the receiving agent.",
        "subject": "Message subject.",
        "body": "Message text (private; delivered to the recipient's pull inbox).",
        "work_id": "Optional work order the message is about.",
    },
    "read_agent_inbox": {
        "after": "Optional ISO 8601 timestamp; only messages created after it are returned.",
    },
}


def _tools(server) -> dict:
    manager = getattr(server, "_tool_manager", None)
    tools = getattr(manager, "_tools", None)
    return tools if isinstance(tools, dict) else {}


def lookup(tool: str, arg: str):
    return TOOL_DOCS.get(tool, {}).get(arg) or COMMON.get(arg)


def describe_inputs(server) -> dict:
    report = {"described": 0, "already": 0, "missing": []}
    for name, tool in _tools(server).items():
        schema = getattr(tool, "parameters", None)
        props = schema.get("properties") if isinstance(schema, dict) else None
        if not isinstance(props, dict):
            continue
        for arg, prop in props.items():
            if not isinstance(prop, dict):
                continue
            if str(prop.get("description") or "").strip():
                report["already"] += 1                              # MD1
                continue
            text = lookup(name, arg)
            if text:
                prop["description"] = text                          # MD2
                report["described"] += 1
            else:
                report["missing"].append(f"{name}.{arg}")
    return report


def bind_version(server, release: str) -> bool:
    """MD3: report the agent's release as serverInfo.version (SDK 1.x and 2.x)."""
    bound = False
    for attr in ("_lowlevel_server", "_mcp_server"):
        low = getattr(server, attr, None)
        if low is None or not hasattr(low, "version"):
            continue
        low.version = release
        low.__dict__.pop("_server_info_stamp_source", None)
        bound = True
    return bound


def apply(server, release: str) -> dict:
    report = {"inputs": None, "version_bound": False}
    try:                                                            # MD4
        report["inputs"] = describe_inputs(server)
    except Exception as exc:  # pragma: no cover - defensive
        report["inputs"] = {"error": repr(exc)}
    try:
        report["version_bound"] = bind_version(server, release)
    except Exception:  # pragma: no cover - defensive
        report["version_bound"] = False
    return report
