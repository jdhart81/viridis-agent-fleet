import asyncio
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MARKET_STATE_DB", ":memory:")

from main import catalog  # noqa: E402


def test_public_catalog_links_the_owned_distribution_listing():
    response = asyncio.run(catalog(None))
    payload = json.loads(response.body)
    assert payload["distribution"] == {
        "mcp_registry": "io.github.jdhart81/agent-market-network",
        "remote": "https://mcp.viridisconservation.com/network/mcp",
        "source": "https://github.com/jdhart81/viridis-agent-fleet",
    }


def test_public_catalog_has_no_smithery_proxy_links():
    # Smithery's proxy, run.tools URLs and accounts shut down on 2026-10-31.
    response = asyncio.run(catalog(None))
    body = response.body.decode()
    assert "smithery.ai" not in body
    assert "run.tools" not in body
