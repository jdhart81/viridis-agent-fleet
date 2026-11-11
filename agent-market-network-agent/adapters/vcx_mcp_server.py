"""Opt-in local stdio MCP adapter for the simulation-only VCX extension.

No hosted mount or billing entry is added. Operators must enroll signed
profiles in the existing Market Network and bootstrap simulated account policy
through trusted local code. No funding, policy override, credential or payout
operation is exposed as a tool.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

AGENT = Path(__file__).resolve().parents[1]
FLEET = AGENT.parent
for path in (AGENT, FLEET):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from src.core import MarketNetworkCore
from vcx.exchange import ComputeExchange

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                       idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                        idempotentHint=True, openWorldHint=False)


def build_server(exchange: ComputeExchange):
    """Bind an explicitly constructed simulation exchange without credentials."""
    mcp = FastMCP("viridis-vcx-local-simulation", instructions=(
        "VCX local simulation, integrated with signed Fleet Market profiles. "
        "All balances are simulated and nonredeemable. Sign each private "
        "operation using existing canonical_action with the action "
        "'vcx.<exchange_id>.<tool name>' (list_capacity returns the prefix), "
        "actor_id, nonce, signed_at and the exact body. Every call, reads "
        "included, needs a fresh nonce. "
        "Writes require body.idempotency_key. No private key, credential, "
        "executable, provider URL or live financial operation is accepted."))

    def invoke(action, actor_id, body, auth):
        return exchange.process({"action": action, "actor_id": actor_id,
                                 "body": body, "auth": auth})

    @mcp.tool(annotations=READ)
    def list_capacity() -> dict[str, Any]:
        """Discover active signed simulated task capacity and fixed service schemas."""
        return exchange.process({"action": "list_capacity"})

    @mcp.tool(annotations=WRITE)
    def register_capacity(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Register immutable authorized simulated service capacity; use disclosed schema."""
        return invoke("register_capacity", actor_id, body, auth)

    @mcp.tool(annotations=WRITE)
    def request_compute(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Create a bounded job with maximum price, deadline, requirements and fixed payload."""
        return invoke("request_compute", actor_id, body, auth)

    @mcp.tool(annotations=WRITE)
    def get_compute_quotes(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Record ranked, expiring simulated quotes with transparent score components."""
        return invoke("get_compute_quotes", actor_id, body, auth)

    @mcp.tool(annotations=WRITE)
    def reserve_compute(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Reserve capacity and hold owner-authorized simulated budget atomically."""
        return invoke("reserve_compute", actor_id, body, auth)

    @mcp.tool(annotations=WRITE)
    def authorize_compute(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Authorize one reserved simulated job within its existing budget and lease."""
        return invoke("authorize_compute", actor_id, body, auth)

    @mcp.tool(annotations=WRITE)
    def execute_compute_job(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Execute one fixed, bounded, deterministic provider; arbitrary code is forbidden."""
        return invoke("execute_compute_job", actor_id, body, auth)

    @mcp.tool(annotations=READ)
    def get_compute_job(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Read a job as its signed buyer or seller; the delivery is disclosed once settled."""
        return invoke("get_compute_job", actor_id, body, auth)

    @mcp.tool(annotations=WRITE)
    def verify_compute_result(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Buyer or seller: check submitted output against the deterministic contract."""
        return invoke("verify_compute_result", actor_id, body, auth)

    @mcp.tool(annotations=WRITE)
    def settle_compute(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Buyer or seller: settle accepted work once into simulated earnings and fees."""
        return invoke("settle_compute", actor_id, body, auth)

    @mcp.tool(annotations=READ)
    def get_compute_budget(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Read only the caller's available simulation budget, policy and exposure."""
        return invoke("get_compute_budget", actor_id, body, auth)

    @mcp.tool(annotations=READ)
    def get_compute_earnings(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Read only the caller's pending simulated earnings, fees and spending."""
        return invoke("get_compute_earnings", actor_id, body, auth)

    @mcp.tool(annotations=WRITE)
    def cancel_compute(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Buyer: cancel before a result exists and release the held simulated budget once."""
        return invoke("cancel_compute", actor_id, body, auth)

    @mcp.tool(annotations=WRITE)
    def dispute_compute(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Buyer: freeze a delivered job for third-party review; this never refunds by itself."""
        return invoke("dispute_compute", actor_id, body, auth)

    @mcp.tool(annotations=WRITE)
    def refund_compute(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Seller only: concede a disputed job and release the buyer's held simulated budget."""
        return invoke("refund_compute", actor_id, body, auth)

    @mcp.tool(annotations=WRITE)
    def reinvest_compute(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Reinvest simulated earnings within the owner's existing immutable policy."""
        return invoke("reinvest_compute", actor_id, body, auth)

    @mcp.tool(annotations=WRITE)
    def recover_compute_jobs(actor_id: str, body: dict[str, Any], auth: dict[str, str]) -> dict[str, Any]:
        """Recover caller-owned expired leases: unpaid holds release, accepted work settles."""
        return invoke("recover_compute_jobs", actor_id, body, auth)

    return mcp


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-db", type=Path, required=True,
                        help="Existing Market Network database with enrolled signed profiles.")
    parser.add_argument("--vcx-db", type=Path, required=True,
                        help="Separate VCX simulation state database with owner-authorized accounts.")
    args = parser.parse_args(argv)
    if not args.market_db.is_file() or not args.vcx_db.is_file():
        parser.error("both databases must already exist; bootstrap only through trusted local setup")
    if args.market_db.resolve() == args.vcx_db.resolve():
        parser.error("Market and VCX require separate databases")
    market = MarketNetworkCore(db_path=str(args.market_db))
    exchange = ComputeExchange(market, args.vcx_db)
    exchange.recover()  # expired leases from a previous run never hold capacity or budget
    try:
        build_server(exchange).run(transport="stdio")
    finally:
        exchange.close()
        market.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
