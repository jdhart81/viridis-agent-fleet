import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MARKET_STATE_DB", ":memory:")

from adapters.mcp_server import mcp  # noqa: E402


def test_mcp_exposes_complete_market_loop():
    tools = {tool.name for tool in asyncio.run(mcp.list_tools())}
    required = {
        "prepare_signature", "publish_agent_profile", "search_agents",
        "subscribe_to_work", "post_work", "search_work", "get_work",
        "submit_offer", "award_offer", "submit_delivery", "accept_delivery",
        "attest_settlement", "send_agent_message", "read_agent_inbox",
        "network_status", "describe_network",
    }
    assert required == tools


def test_mcp_transport_has_dns_rebinding_protection():
    settings = mcp.settings.transport_security
    assert settings.enable_dns_rebinding_protection is True
    assert "mcp.viridisconservation.com" in settings.allowed_hosts
    assert "127.0.0.1:*" in settings.allowed_hosts
    assert "https://mcp.viridisconservation.com" in settings.allowed_origins
