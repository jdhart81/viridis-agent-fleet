"""
MCP adapter for agent-surety-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py.

Custody note: this exposes the surety STATE MACHINE. Real fund custody is
delegated to a payment rail (Stripe/x402) — no funds move through this server.
Slashing requires a machine-verifiable arbitration ruling reference.
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

    class FastMCP:
        def __init__(self, name, **kw): self.name, self.tools = name, {}
        def tool(self, *a, **k):
            def deco(fn): self.tools[fn.__name__] = fn; return fn
            return deco
        def run(self): raise RuntimeError("`mcp` SDK not installed - pip install mcp")

from src.core import build


def _mk_mcp(name, description=""):
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)


mcp = _mk_mcp("agent-surety-agent",
              description="Counterparty risk transfer for the agent economy: "
                          "agents post bonds behind their promises, wronged "
                          "counterparties file claims, machine-verifiable "
                          "arbitration rulings trigger slashing, honest agents "
                          "reclaim their stake. Conservation-checked, "
                          "tamper-evident, exactly-once.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def post_bond(principal_agent: str, principal: int, expires_at: str,
                    coverage: str = "", currency: str = "USD") -> str:
    """Post a surety bond behind an agent's promises. principal is a positive
    integer in minor units; expires_at is the ISO-8601 coverage window end.
    The bond fee (2% default) is computed and frozen at post."""
    return await _run({"action": "post_bond", "principal_agent": principal_agent,
                       "principal": principal, "expires_at": expires_at,
                       "coverage": coverage, "currency": currency})


@mcp.tool()
async def activate_bond(bond_id: str, funding_ref: str = "") -> str:
    """Mark a POSTED bond ACTIVE (idempotent). funding_ref links the payment
    rail transaction that funded the stake."""
    return await _run({"action": "activate", "bond_id": bond_id,
                       "funding_ref": funding_ref})


@mcp.tool()
async def file_claim(bond_id: str, claimant: str, amount_minor: int,
                     reason: str = "") -> str:
    """File a claim against an ACTIVE bond. Claims pay out ONLY when an
    arbitration ruling upholds them (see slash_bond)."""
    return await _run({"action": "file_claim", "bond_id": bond_id,
                       "claimant": claimant, "amount_minor": amount_minor,
                       "reason": reason})


@mcp.tool()
async def slash_bond(bond_id: str, claim_id: str, ruling_case_id: str,
                     ruling_hash: str, upheld: bool = True) -> str:
    """Execute an arbitration ruling against a claim. Requires the ruling's
    case id + content hash from agent-arbitration — no ruling, no slash; a
    given ruling pays at most once. Payout caps at the bond's available
    balance (over-claims exhaust the bond)."""
    return await _run({"action": "slash", "bond_id": bond_id,
                       "claim_id": claim_id, "ruling_case_id": ruling_case_id,
                       "ruling_hash": ruling_hash, "upheld": upheld})


@mcp.tool()
async def release_bond(bond_id: str) -> str:
    """Release the remaining stake to the principal after the coverage window
    elapses — refused while any claim is still open."""
    return await _run({"action": "release", "bond_id": bond_id})


@mcp.tool()
async def bond_status(bond_id: str) -> str:
    """Current record for a bond (state, balances, claims, audit head)."""
    return await _run({"action": "status", "bond_id": bond_id})


@mcp.tool()
async def list_bonds(state: Optional[str] = None) -> str:
    """List bonds, optionally filtered by state
    (POSTED|ACTIVE|RELEASED|EXHAUSTED)."""
    return await _run({"action": "list", "state": state})


@mcp.tool()
async def verify_audit(bond_id: str) -> str:
    """Validate the tamper-evident audit hash chain for a bond."""
    return await _run({"action": "verify_audit", "bond_id": bond_id})


@mcp.tool()
async def price_bond(coverage_minor: int, duration_days: int,
                     attestations: int = 0, successful_deliveries: int = 0,
                     bonds_completed: int = 0, slashes: int = 0,
                     slashed_minor: int = 0) -> str:
    """Underwrite a surety bond: deterministic actuarial premium quote from a
    counterparty's track record (attestations, notarized deliveries, completed
    bonds lower the rate; slashes raise it or decline outright). Integer-only
    model uw-v1; the returned quote_hash lets any party recompute and verify
    the quote. Pure — never mutates bond state."""
    return await _run({"action": "price_bond",
                       "coverage_minor": coverage_minor,
                       "duration_days": duration_days,
                       "history": {"attestations": attestations,
                                   "successful_deliveries": successful_deliveries,
                                   "bonds_completed": bonds_completed,
                                   "slashes": slashes,
                                   "slashed_minor": slashed_minor}})


@mcp.tool()
async def describe_agent() -> str:
    """Return capabilities and input contract."""
    return json.dumps(agent.describe(), indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(asyncio.run(agent.health()), indent=2))
