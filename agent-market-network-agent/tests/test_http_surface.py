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
        "smithery": (
            "https://smithery.ai/servers/hartjustin6/agent-market-network"
        ),
        "source": "https://github.com/jdhart81/viridis-agent-fleet",
    }
