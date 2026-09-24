"""
MCP Server Deployment Adapter

Registers the agent as an MCP (Model Context Protocol) server using FastMCP.
Enables Claude, other LLMs, and MCP clients to discover and use your agent.

To run:
    python adapters/mcp_server.py

This will start the MCP server which other tools can connect to.
"""

import os
import logging
import asyncio
from typing import Any

try:
    from fastmcp import FastMCP
except ImportError:
    raise ImportError(
        "FastMCP not installed. Install with: pip install fastmcp"
    )

# Import your core agent
from src.core import AgentCore, AgentConfig

# ============================================================================
# Configuration
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
AGENT_NAME = os.getenv("AGENT_NAME", "agent")
AGENT_VERSION = "0.1.0"

# Configure logging
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# Initialize MCP and Agent
# ============================================================================

mcp = FastMCP(AGENT_NAME, version=AGENT_VERSION)

# Create agent instance
config = AgentConfig(
    name=AGENT_NAME,
    version=AGENT_VERSION,
    debug=(LOG_LEVEL == "DEBUG")
)
agent = AgentCore(config)

logger.info(f"Initialized MCP server for {AGENT_NAME} v{AGENT_VERSION}")


# ============================================================================
# MCP Tools Registration
# ============================================================================

@mcp.tool()
async def process(input_data: dict) -> dict:
    """
    Main processing tool.

    Processes input data through the agent and returns results.

    Args:
        input_data: Agent-specific input dictionary

    Returns:
        Result dictionary with status, data, and optional error
    """
    logger.info(f"MCP: processing request")
    try:
        result = await agent.process(input_data)
        logger.info(f"MCP: process succeeded")
        return result
    except Exception as e:
        logger.error(f"MCP: process failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "data": None
        }


@mcp.tool()
async def health() -> dict:
    """
    Health check tool.

    Returns the agent's current health status.

    Returns:
        Health status dictionary
    """
    logger.debug("MCP: health check")
    try:
        result = await agent.health()
        return result
    except Exception as e:
        logger.error(f"MCP: health check failed: {e}", exc_info=True)
        return {
            "status": "error",
            "agent": AGENT_NAME,
            "error": str(e)
        }


@mcp.tool()
def describe() -> dict:
    """
    Discovery tool.

    Returns detailed information about agent capabilities.

    Returns:
        Agent description dictionary
    """
    logger.debug("MCP: describe request")
    try:
        result = agent.describe()
        return result
    except Exception as e:
        logger.error(f"MCP: describe failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "name": AGENT_NAME
        }


# ============================================================================
# MCP Resources (Optional)
# ============================================================================

@mcp.resource("agent://metadata")
def agent_metadata() -> str:
    """
    Resource: Agent metadata.

    Provides static agent information.
    """
    metadata = agent.describe()
    return f"Agent: {metadata.get('name', 'unknown')}\nVersion: {metadata.get('version', 'unknown')}"


# ============================================================================
# Entrypoint
# ============================================================================

async def main():
    """Run the MCP server."""
    logger.info(f"Starting MCP server for {AGENT_NAME}")
    async with mcp.run() as server:
        logger.info(f"MCP server running. Waiting for connections...")
        # Keep the server running
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    logger.info(f"Launching {AGENT_NAME} as MCP Server")
    asyncio.run(main())
