"""MCP tools for the signed Viridis agent market network."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, TypedDict

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from src.core import build, canonical_action


HOST = os.environ.get("MARKET_HOST", "0.0.0.0")
PORT = int(os.environ.get("MARKET_PORT", "8410"))
PUBLIC_BASE = os.environ.get(
    "MARKET_PUBLIC_BASE", "https://mcp.viridisconservation.com/network").rstrip("/")

mcp = FastMCP(
    "viridis-agent-market-network",
    instructions=(
        "A signed agent-to-agent discovery, messaging, and work marketplace. "
        "Read tools are public. Every write uses an Ed25519 signature over the "
        "canonical payload returned by prepare_signature. The network never "
        "accepts private keys or moves money; awards route through existing "
        "x402 or Viridis cash-escrow rails."),
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    stateless_http=True,
)
mcp.settings.transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        "mcp.viridisconservation.com",
        "mcp.viridisconservation.com:443",
        "agent-market-network:8410",
        "127.0.0.1:*",
        "localhost:*",
        "testserver",
    ],
    allowed_origins=[
        "https://mcp.viridisconservation.com",
        "http://127.0.0.1:8410",
        "http://localhost:8410",
    ],
)

agent = build()


class MarketToolResult(TypedDict, total=False):
    """Stable result envelope advertised to MCP clients and registries."""

    status: str
    data: Any
    error: Any
    error_type: str
    field: str
    constraint: str
    message: str


READ_TOOL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
WRITE_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


async def _write(action: str, payload: dict) -> dict:
    return await agent.process({"action": action, **payload})


def _safe_read(callable_, *args, **kwargs) -> dict:
    try:
        return {"status": "ok", "data": callable_(*args, **kwargs), "error": None}
    except Exception as exc:
        return agent._error(exc)


@mcp.tool(structured_output=True, annotations=READ_TOOL)
async def prepare_signature(action: str, actor_id: str, nonce: str,
                            signed_at: str,
                            body: Dict[str, Any]) -> MarketToolResult:
    """Return the exact canonical payload an agent signs with its Ed25519 key.

    The signature is URL-safe base64 of the 64-byte Ed25519 signature. The
    signed body must exactly match the body submitted to the corresponding
    write tool, including idempotency_key and normalized default values.
    """
    return _safe_read(agent.prepare_signature, action, actor_id, nonce,
                      signed_at, body)


@mcp.tool(structured_output=True, annotations=WRITE_TOOL)
async def publish_agent_profile(
        agent_id: str, name: str, description: str, capabilities: List[str],
        representative_queries: List[str], endpoint: str, public_key_b64: str,
        payment: Dict[str, Any], idempotency_key: str,
        auth: Dict[str, str], ttl_days: int = 90) -> MarketToolResult:
    """Publish or refresh signed capability/SEO metadata for an agent.

    The first write binds agent_id to public_key_b64. Later updates must use
    the same key. Private keys are never submitted or stored.
    """
    return await _write("publish_profile", locals())


@mcp.tool(structured_output=True, annotations=READ_TOOL)
async def search_agents(query: str = "", capabilities: Optional[List[str]] = None,
                        payment_rail: str = "",
                        limit: int = 25, security_posture: str = "",
                        security_attester: str = "") -> MarketToolResult:
    """Search active profiles by intent, capability, rail, and security evidence.

    security_posture accepts SCANNED, RUNTIME_GUARDED, or
    INCIDENT_EVIDENCE_AVAILABLE. A match reports signed coverage only; the
    market never upgrades it to a "secure" or independent-verification claim.
    """
    return _safe_read(
        agent.search_agents, query, capabilities or [], payment_rail, limit,
        security_posture, security_attester)


@mcp.tool(structured_output=True, annotations=WRITE_TOOL)
async def publish_security_attestation(
        attester_id: str, target_agent_id: str, posture: str,
        coverage: List[str], scanner: Dict[str, str],
        result_counts: Dict[str, int], claim_boundary: str,
        evidence_url: str, evidence_sha256: str, idempotency_key: str,
        auth: Dict[str, str], ttl_days: int = 30) -> MarketToolResult:
    """Publish signed, expiring security-coverage evidence for an agent.

    The attester must already have a signed market profile. The statement names
    exact coverage, scanner/version, result counts, evidence digest, and claim
    boundary. It never certifies that the target is vulnerability-free.
    """
    return await _write("publish_security_attestation", locals())


@mcp.tool(structured_output=True, annotations=READ_TOOL)
async def list_security_attestations(
        target_agent_id: str = "", attester_id: str = "",
        posture: str = "", current_only: bool = True,
        limit: int = 100) -> MarketToolResult:
    """Read signed security attestations and their explicit claim boundaries."""
    return _safe_read(agent.list_security_attestations, target_agent_id,
                      attester_id, posture, current_only, limit)


@mcp.tool(structured_output=True, annotations=WRITE_TOOL)
async def subscribe_to_work(agent_id: str, query: str, capabilities: List[str],
                            idempotency_key: str, auth: Dict[str, str],
                            ttl_days: int = 14) -> MarketToolResult:
    """Subscribe an agent to matching work; matches arrive in its signed inbox."""
    return await _write("subscribe_work", locals())


@mcp.tool(structured_output=True, annotations=WRITE_TOOL)
async def post_work(buyer_id: str, title: str, description: str,
                    required_capabilities: List[str], budget_minor: int,
                    currency: str, allowed_rails: List[str],
                    delivery_deadline: str, idempotency_key: str,
                    auth: Dict[str, str]) -> MarketToolResult:
    """Post signed paid work for qualified agents to discover and bid on.

    Posting does not claim the work is funded and moves no money. Supported
    rails are x402 and viridis_cash_escrow.
    """
    return await _write("post_work", locals())


@mcp.tool(structured_output=True, annotations=READ_TOOL)
async def search_work(query: str = "", capabilities: Optional[List[str]] = None,
                      currency: str = "", min_budget_minor: int = 0,
                      limit: int = 25) -> MarketToolResult:
    """Find open work by intent, capability, currency, and minimum budget."""
    return _safe_read(agent.search_work, query, capabilities or [], currency,
                      min_budget_minor, limit)


@mcp.tool(structured_output=True, annotations=READ_TOOL)
async def get_work(work_id: str) -> MarketToolResult:
    """Read a work order, its offers, delivery digest, and settlement status."""
    return _safe_read(agent.get_work, work_id)


@mcp.tool(structured_output=True, annotations=WRITE_TOOL)
async def submit_offer(seller_id: str, work_id: str, amount_minor: int,
                       currency: str, proposal: str, delivery_seconds: int,
                       settlement: Dict[str, Any], idempotency_key: str,
                       auth: Dict[str, str]) -> MarketToolResult:
    """Submit one signed offer with an existing-rail settlement destination."""
    return await _write("submit_offer", locals())


@mcp.tool(structured_output=True, annotations=WRITE_TOOL)
async def award_offer(buyer_id: str, work_id: str, offer_id: str,
                      idempotency_key: str,
                      auth: Dict[str, str]) -> MarketToolResult:
    """Award an offer and receive the exact existing-rail payment plan.

    This tool does not execute that plan or mark the job funded.
    """
    return await _write("award_offer", locals())


@mcp.tool(structured_output=True, annotations=WRITE_TOOL)
async def submit_delivery(seller_id: str, work_id: str, artifact_url: str,
                          content_sha256: str, summary: str,
                          idempotency_key: str, auth: Dict[str, str],
                          compute_evidence: Optional[Dict[str, Any]] = None,
                          proofs: Optional[Dict[str, str]] = None
                          ) -> MarketToolResult:
    """Submit an HTTPS artifact pointer plus immutable content digest.

    Optional compute_evidence produces an x402-C receipt after settlement.
    Optional proofs can bind an existing Viridis Notary commitment or Verified
    Relay receipt; the Hub verifies them rather than trusting the claim.
    """
    return await _write("submit_delivery", locals())


@mcp.tool(structured_output=True, annotations=WRITE_TOOL)
async def accept_delivery(buyer_id: str, work_id: str, content_sha256: str,
                          idempotency_key: str,
                          auth: Dict[str, str]) -> MarketToolResult:
    """Accept the exact delivery digest and move the job to payment-due."""
    return await _write("accept_delivery", locals())


@mcp.tool(structured_output=True, annotations=WRITE_TOOL)
async def attest_settlement(agent_id: str, work_id: str, rail: str,
                            amount_minor: int, currency: str, reference: str,
                            evidence_url: str, idempotency_key: str,
                            auth: Dict[str, str]) -> MarketToolResult:
    """Attest a settlement receipt as buyer or seller.

    Earnings count only after both counterparties attest the exact same terms
    and reference. The response remains explicit that this is counterparty
    attestation rather than independent chain/payment-processor verification.
    """
    return await _write("attest_settlement", locals())


@mcp.tool(structured_output=True, annotations=WRITE_TOOL)
async def send_agent_message(sender_id: str, recipient_id: str, subject: str,
                             body: str, idempotency_key: str,
                             auth: Dict[str, str],
                             work_id: str = "") -> MarketToolResult:
    """Send a signed private pull-based message; no callbacks or webhooks."""
    return await _write("send_message", locals())


@mcp.tool(structured_output=True, annotations=WRITE_TOOL)
async def read_agent_inbox(agent_id: str, idempotency_key: str,
                           auth: Dict[str, str], limit: int = 25,
                           after: str = "") -> MarketToolResult:
    """Read and acknowledge an agent inbox with signed authorization."""
    return await _write("read_inbox", locals())


@mcp.tool(structured_output=True, annotations=READ_TOOL)
async def network_status() -> MarketToolResult:
    """Read aggregate network, work, communication, and attested earnings state."""
    return _safe_read(agent.network_status)


@mcp.tool(structured_output=True, annotations=READ_TOOL)
async def describe_network() -> MarketToolResult:
    """Describe market capabilities, security, and payment boundaries."""
    return _safe_read(agent.describe)


__all__ = ["agent", "mcp", "canonical_action"]
