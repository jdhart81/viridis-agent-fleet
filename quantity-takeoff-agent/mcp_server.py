"""Compatibility entrypoint for the fleet-standard MCP adapter."""

from adapters.mcp_server import agent, mcp


if __name__ == "__main__":
    import json
    import sys

    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
