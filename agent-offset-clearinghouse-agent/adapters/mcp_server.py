"""
MCP adapter for agent-offset-clearinghouse-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py.
Run: python adapters/mcp_server.py            (smoke: describe + health)
     python adapters/mcp_server.py --serve    (stdio MCP server; needs `mcp`)

Money note: purchases here retire credits and issue certificates; PAYMENT
settles separately over agent-escrow-agent. No funds move through this server.
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict

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

mcp = _mk_mcp("agent-offset-clearinghouse-agent",
              description="Verified conservation credits matched to agent compute "
                          "emissions — the conservation flywheel of the agent economy.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def list_credit(issuer: str, project_id: str, mass_g: int,
                price_minor_per_kg: int, verification_ref: str,
                registry: str = "", vcs_project_id: str = "", vintage: str = "",
                serial_number: str = "", methodology: str = "") -> str:
    """List a conservation credit on the book. verification_ref (a D-Score /
    land-verification attestation) is REQUIRED — unverified credits cannot
    enter the book. To trade on the Verra network, pass registry="verra" with
    the VCS provenance (vcs_project_id, serial_number, vintage, methodology) so
    retirements are cross-referenceable on registry.verra.org."""
    return await _run({"action": "list_credit", "issuer": issuer, "project_id": project_id,
                 "mass_g": mass_g, "price_minor_per_kg": price_minor_per_kg,
                 "verification_ref": verification_ref, "registry": registry,
                 "vcs_project_id": vcs_project_id, "vintage": vintage,
                 "serial_number": serial_number, "methodology": methodology})


@mcp.tool()
async def delist_credit(credit_id: str, reason: str) -> str:
    """Admin operation: remove a credit from the active fill path while
    retaining its listing and retirement history for audit. Idempotent for an
    already-delisted credit. Gateway state-change authentication is required."""
    return await _run({"action": "delist_credit", "credit_id": credit_id,
                       "reason": reason})


@mcp.tool()
async def verra_supply() -> str:
    """The tradeable Verra VCS book: verified credits carrying genuine Verra
    provenance (project id + serial + vintage), cross-referenceable on
    registry.verra.org. Read-only. Every retirement nets the project 85% and
    Viridis the 15% marketplace take."""
    return await _run({"action": "verra_supply"})


@mcp.tool()
async def verra_retirement_record(purchase_id: str,
                                  retirement_reason: str = "") -> str:
    """Generate the Verra-portal-ready retirement record(s) for a retirement
    made against Verra supply — VCS project id, serial, vintage, methodology,
    quantity (tCO2e), beneficiary, and the registry.verra.org cross-reference.
    Read-only. Submit these under the Viridis Verra account to finalize the
    on-registry retirement (portal today; auto-posts when Verra's transaction
    API is live)."""
    payload = {"action": "verra_retirement_record", "purchase_id": purchase_id}
    if retirement_reason:
        payload["retirement_reason"] = retirement_reason
    return await _run(payload)


@mcp.tool()
async def buy_offset(buyer: str, purchase_id: str, mass_g: int,
                     dry_run: bool = False) -> str:
    """Retire mass_g of verified credits for a buyer: cheapest-first matching,
    exactly-once (idempotent on purchase_id), returns a content-addressed
    offset certificate with per-fill costs. Payment settles via escrow.
    dry_run=true previews the exact fills/cost without mutating the book."""
    return await _run({"action": "buy_offset", "buyer": buyer,
                 "purchase_id": purchase_id, "mass_g": mass_g,
                 "dry_run": dry_run})


@mcp.tool()
async def buy_offset_budget(buyer: str, purchase_id: str, budget_minor: int,
                            dry_run: bool = False) -> str:
    """Money-denominated offset purchase: retire the maximum cheapest-first
    verified mass whose exact cost fits inside budget_minor (never overspends).
    Built for callers whose restoration obligation is a currency amount —
    e.g. a revenue share accrued in a ledger. Idempotent on purchase_id;
    dry_run=true previews without mutating."""
    return await _run({"action": "buy_offset_budget", "buyer": buyer,
                 "purchase_id": purchase_id, "budget_minor": budget_minor,
                 "dry_run": dry_run})


@mcp.tool()
async def settlement_batch(buyer: str, since: str = "") -> str:
    """Read-only cash-settlement summary for a buyer: the list + exact sums
    (purchases, mass_g, cost_minor) of their retirements, optionally since an
    ISO-8601 timestamp — the statement a human settles in one transfer."""
    payload: Dict[str, Any] = {"action": "settlement_batch", "buyer": buyer}
    if since:
        payload["since"] = since
    return await _run(payload)


@mcp.tool()
async def net_position(buyer: str, emitted_g: float) -> str:
    """Buyer's carbon position: emitted (from agent-compute-ledger) minus
    retired. carbon_accountable == true when fully offset."""
    return await _run({"action": "net_position", "buyer": buyer, "emitted_g": emitted_g})


@mcp.tool()
async def verify_certificate(certificate: Dict[str, Any]) -> str:
    """Verify an offset certificate: recompute its hash and check the ledger."""
    return await _run({"action": "verify_certificate", "certificate": certificate})


@mcp.tool()
async def book() -> str:
    """The full credit book with per-credit and book-wide mass conservation totals."""
    return await _run({"action": "book"})


@mcp.tool()
async def get_purchase(purchase_id: str) -> str:
    """Fetch a past purchase / offset certificate by id."""
    return await _run({"action": "get_purchase", "purchase_id": purchase_id})


@mcp.tool()
async def verify_retirement(purchase_id: str, required_g: int = 0) -> str:
    """x402-C C4 check: confirm a retirement (offset_ref = purchase_id)
    actually retires at least required_g grams of verified conservation
    credit — the check that lets a carbon receipt's neutrality claim be
    honored. Returns covered / retired_g / shortfall_g and the backing
    credits. Read-only."""
    return await _run({"action": "verify_retirement", "purchase_id": purchase_id,
                       "required_g": required_g})


@mcp.tool()
async def register_project(project_id: str, verification_ref: str,
                           name: str = "", location: str = "",
                           methodology: str = "", beneficiary: str = "",
                           registry_ref: str = "") -> str:
    """Register a VERIFIED restoration project so retirements against its
    credits can be funded. verification_ref (D-Score / land-verification /
    registry id) is required — only verified conservation is funded.
    project_id is immutable once registered."""
    return await _run({"action": "register_project", "project_id": project_id,
                       "verification_ref": verification_ref, "name": name,
                       "location": location, "methodology": methodology,
                       "beneficiary": beneficiary, "registry_ref": registry_ref})


@mcp.tool()
async def project_funding(project_id: str = "") -> str:
    """Supply-side disbursement ledger: how much each restoration project has
    earned from retirements and is owed (gross_proceeds_minor + retired_g).
    Pass a project_id for one project, else all. Read-only — the CEO settles
    the actual payout. This is what makes the clearinghouse fund restoration."""
    payload = {"action": "project_funding"}
    if project_id:
        payload["project_id"] = project_id
    return await _run(payload)


@mcp.tool()
async def list_projects() -> str:
    """List all registered restoration projects with their metadata."""
    return await _run({"action": "list_projects"})


@mcp.tool()
async def disbursement_schedule(project_id: str = "") -> str:
    """Automated disbursement preview: for each verified restoration project,
    splits its newly-accrued proceeds into the Viridis Conservation withhold
    (default 15%, seeds the software/business) and the project payout (85%).
    Read-only. Funded-but-unregistered projects are surfaced separately as
    pending_registration (can't pay an unverified project)."""
    payload = {"action": "disbursement_schedule"}
    if project_id:
        payload["project_id"] = project_id
    return await _run(payload)


@mcp.tool()
async def certify_disbursement(batch_id: str) -> str:
    """Freeze the current disbursement schedule into a certified, tamper-evident
    batch (content-addressed, hash-chained). Idempotent on batch_id; only
    newly-accrued proceeds for verified projects are certified (never disbursed
    twice). This is the certified investment record the CEO executes the actual
    Stripe transfers against."""
    return await _run({"action": "certify_disbursement", "batch_id": batch_id})


@mcp.tool()
async def verify_disbursement() -> str:
    """Recompute the disbursement certificate hash chain and confirm whole-book
    conservation of disbursed proceeds. Any party can audit disbursements."""
    return await _run({"action": "verify_disbursement"})


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
