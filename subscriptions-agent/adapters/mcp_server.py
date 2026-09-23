"""Thin MCP adapter for the Viridis subscription infrastructure."""

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
except ImportError:  # stdlib smoke shim
    class FastMCP:
        def __init__(self, name, **kwargs):
            self.name, self.tools = name, {}

        def tool(self, *args, **kwargs):
            def decorator(fn):
                self.tools[fn.__name__] = fn
                return fn
            return decorator

        def run(self):
            raise RuntimeError("mcp SDK is required to serve")

from src.core import build

try:
    # Bound by the gateway's Authorization: Bearer middleware. Keeping this
    # request-local key out of tool arguments prevents it from appearing in
    # LLM transcripts, registry schemas, or MCP payload logs.
    from account_auth import current_account_key
except ImportError:  # isolated adapter smoke: sensitive reads fail closed
    def current_account_key():
        return None


def _server(name: str, description: str):
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)


mcp = _server(
    "subscriptions-agent",
    "Verified monthly-seat catalog, account attribution, quota, overage, and MRR infrastructure.",
)
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), indent=2, default=str)


@mcp.tool()
async def list_plans() -> str:
    """List the versioned monthly-seat catalog, exact prices/coverage, catalog
    SHA-256, readiness flags, and pending owner-confirmation notice."""
    return await _run({"action": "list_plans"})


@mcp.tool()
async def get_plan(plan_id: str) -> str:
    """Get one exact monthly plan and its versioned catalog lineage."""
    return await _run({"action": "get_plan", "plan_id": plan_id})


@mcp.tool()
async def create_account(account_ref: str) -> str:
    """Create a free account for bearer attribution. The full account key is
    returned once; only its SHA-256 and last four characters are retained."""
    return await _run({"action": "create_account", "account_ref": account_ref})


@mcp.tool()
async def create_checkout_link(plan_id: str, account_ref: str) -> str:
    """Prepare a Stripe-hosted subscription Checkout URL. It never charges a
    card. Draft plans, missing owner approval, unavailable covered agents, or
    missing recurring Price IDs fail closed without creating a session."""
    return await _run({"action": "create_checkout_link", "plan_id": plan_id,
                       "account_ref": account_ref})


@mcp.tool()
async def record_subscription(stripe_session_or_sub_id: str) -> str:
    """Pull-verify a Stripe session/subscription and idempotently activate its
    exact subscription period. A newly created account receives its key once."""
    return await _run({"action": "record_subscription",
                       "stripe_reference": stripe_session_or_sub_id})


@mcp.tool()
async def subscription_status(account_id: str) -> str:
    """Return bearer-owned subscription lifecycle and current-period quota.
    The account key is always masked in output."""
    return await _run({"action": "subscription_status", "account_id": account_id,
                       "account_key": current_account_key()})


@mcp.tool()
async def customer_portal_link(account_id: str) -> str:
    """Return a bearer-owned Stripe-hosted billing-portal URL. The human
    manages or cancels there; this tool never moves money."""
    return await _run({"action": "customer_portal_link", "account_id": account_id,
                       "account_key": current_account_key()})


@mcp.tool()
async def usage_summary(account_id: str) -> str:
    """Return bearer-owned, period-resolved included and overage usage with
    exact catalog lineage and conservation totals."""
    return await _run({"action": "usage_summary", "account_id": account_id,
                       "account_key": current_account_key()})


@mcp.tool()
async def mrr_summary() -> str:
    """Return aggregate active live-mode subscription count, MRR minor units,
    and plan mix. No account or Stripe identifiers are exposed."""
    return await _run({"action": "mrr_summary"})


@mcp.tool()
async def describe_agent() -> str:
    """Return the fleet-standard version, catalog digest, security posture,
    lifecycle policy, and capabilities."""
    return json.dumps(agent.describe(), indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(asyncio.run(agent.health()), indent=2))
