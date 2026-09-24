"""
MCP adapter for agent-escrow-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py.
Run: python adapters/mcp_server.py            (smoke: describe + health)
     python adapters/mcp_server.py --serve    (stdio MCP server; needs `mcp`)

Money-custody note: this exposes the escrow STATE MACHINE. Actual fund custody
is delegated to a payment-rail adapter (Stripe/x402) — no funds move through
this server.
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from mcp.server.fastmcp import FastMCP
    HAS_MCP = True
except ImportError:  # pragma: no cover
    HAS_MCP = False

    class FastMCP:  # stdlib shim so smoke tests run anywhere
        def __init__(self, name, **kw): self.name, self.tools = name, {}
        def tool(self, *a, **k):
            def deco(fn): self.tools[fn.__name__] = fn; return fn
            return deco
        def run(self): raise RuntimeError("`mcp` SDK not installed - pip install mcp")

from src.core import build

def _mk_mcp(name, description=""):
    """FastMCP compat across SDK versions (description -> instructions -> bare)."""
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)

mcp = _mk_mcp("agent-escrow-agent",
              description="Trustless escrow & settlement for A2A transactions: "
                          "exactly-once state machine, frozen fees, tamper-evident "
                          "audit chain. Pay on delivery, no trusted middleman.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def open_escrow(payer: str, payee: str, amount_minor: int, currency: str = "USD",
                terms: str = "", deadline: str = "", fee_bps: Optional[int] = None,
                open_ref: str = "") -> str:
    """Open an escrow between payer and payee. amount_minor is a positive
    integer in minor units (cents). The platform fee is computed and FROZEN at
    open (ceil bps). Returns the escrow_id (state OPEN). RETRY-SAFE: pass
    open_ref=<your job id> and a replayed open returns the ORIGINAL escrow
    (duplicate=true) instead of minting another one (E10)."""
    payload = {"action": "open", "payer": payer, "payee": payee,
               "amount_minor": amount_minor, "currency": currency,
               "terms": terms, "deadline": deadline}
    if fee_bps is not None:
        payload["fee_bps"] = fee_bps
    if isinstance(open_ref, str) and open_ref.strip():
        payload["open_ref"] = open_ref.strip()
    return await _run(payload)


@mcp.tool()
async def fund_escrow(escrow_id: str, payment_ref: str = "") -> str:
    """Mark an OPEN escrow as FUNDED (idempotent). payment_ref links the
    payment-rail transaction."""
    return await _run({"action": "fund", "escrow_id": escrow_id, "payment_ref": payment_ref})


@mcp.tool()
async def release_escrow(escrow_id: str, delivery_proof: str = "") -> str:
    """Release a FUNDED/DISPUTED escrow to the payee (exactly-once — a repeat
    release returns the existing terminal record, never a double payout)."""
    return await _run({"action": "release", "escrow_id": escrow_id,
                 "delivery_proof": delivery_proof})


@mcp.tool()
async def refund_escrow(escrow_id: str, reason: str = "") -> str:
    """Refund an OPEN/FUNDED/DISPUTED escrow to the payer (exactly-once).
    Refunding an OPEN escrow is a cancel."""
    return await _run({"action": "refund", "escrow_id": escrow_id, "reason": reason})


@mcp.tool()
async def dispute_escrow(escrow_id: str, reason: str = "") -> str:
    """Move a FUNDED escrow to DISPUTED. An arbiter (agent-arbitration-agent)
    then resolves it to release or refund."""
    return await _run({"action": "dispute", "escrow_id": escrow_id, "reason": reason})


@mcp.tool()
async def escrow_status(escrow_id: str) -> str:
    """Current record for an escrow."""
    return await _run({"action": "status", "escrow_id": escrow_id})


@mcp.tool()
async def list_escrows(state: Optional[str] = None) -> str:
    """List escrows, optionally filtered by state
    (OPEN|FUNDED|RELEASED|REFUNDED|DISPUTED)."""
    return await _run({"action": "list", "state": state})


@mcp.tool()
async def verify_audit(escrow_id: str) -> str:
    """Validate the tamper-evident audit hash chain for an escrow."""
    return await _run({"action": "verify_audit", "escrow_id": escrow_id})


@mcp.tool()
async def describe_agent() -> str:
    """Fleet-standard self-description."""
    return json.dumps(agent.describe(), default=str, indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), default=str, indent=2))
        print(json.dumps(asyncio.run(agent.health()), default=str, indent=2))
