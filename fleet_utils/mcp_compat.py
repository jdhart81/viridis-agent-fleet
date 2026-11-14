"""One place that knows the two MCP Python SDK generations apart.

SDK 1.x speaks the handshake protocol versions (2024-11-05 to 2025-11-25).
SDK 2.x speaks those and 2026-07-28 from the same endpoint. The fleet's
adapters run on either; tests and tools that read SDK objects go through
these helpers so nothing depends on which one is installed.

  field(obj, "inputSchema")  read a model field by its wire (camelCase) name
  wire(model)                the model as its wire-format dict
  connect(server)            an in-memory client session for a server object
  MCPError                   the client-side protocol error class
  SDK_MAJOR                  1 or 2 (0 when the SDK is not installed)
  install_legacy_fastmcp_module()
                             lets code written for ``mcp.server.fastmcp``
                             (a vendored package we do not edit) run on SDK 2
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import Any

__all__ = ["field", "wire", "connect", "MCPError", "SDK_MAJOR",
           "install_legacy_fastmcp_module"]

try:
    from mcp.server.mcpserver import MCPServer as _Server2  # noqa: F401
    SDK_MAJOR = 2
except ModuleNotFoundError:
    try:
        import mcp.server.fastmcp  # noqa: F401
        SDK_MAJOR = 1
    except ModuleNotFoundError:
        SDK_MAJOR = 0

try:
    from mcp import MCPError  # SDK 2.x
except ImportError:
    try:
        from mcp import McpError as MCPError  # SDK 1.x
    except ImportError:  # no SDK
        class MCPError(Exception):  # type: ignore[no-redef]
            pass


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def field(obj: Any, name: str) -> Any:
    """Read ``name`` (wire spelling) from an SDK model on either generation."""
    try:
        return getattr(obj, name)
    except AttributeError:
        return getattr(obj, _snake(name))


def wire(model: Any) -> dict:
    """The model as the JSON a client sees (camelCase keys, no nulls)."""
    return model.model_dump(by_alias=True, exclude_none=True)


@asynccontextmanager
async def connect(server: Any):
    """An in-memory client for a FastMCP / MCPServer instance."""
    if SDK_MAJOR >= 2:
        from mcp import Client
        async with Client(server) as client:
            yield client
    else:
        from mcp.shared.memory import create_connected_server_and_client_session
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            yield client


# Transport arguments SDK 1.x took in the FastMCP constructor. SDK 2.x takes
# the first four in streamable_http_app(); the rest have no meaning when the
# gateway mounts the app itself.
_TRANSPORT_KEPT = ("stateless_http", "json_response", "streamable_http_path",
                   "transport_security")
_TRANSPORT_DROPPED = ("host", "port", "mount_path", "sse_path", "message_path",
                      "event_store", "retry_interval", "debug", "log_level")


def _legacy_fastmcp_class():
    from mcp.server.mcpserver import MCPServer

    class FastMCP(MCPServer):
        """SDK 1.x constructor and call shape on an SDK 2.x server (LF1-LF3).

        LF1 the 1.x positional order (name, instructions) and the 1.x
            transport keywords are accepted.
        LF2 streamable_http_app() with no arguments builds the app with the
            transport settings given at construction, as 1.x did.
        LF3 everything else is the SDK 2.x server, so it answers both the
            handshake versions and 2026-07-28.
        """

        def __init__(self, name=None, instructions=None, **kwargs):
            self._legacy_transport = {
                key: kwargs.pop(key) for key in _TRANSPORT_KEPT if key in kwargs}
            for key in _TRANSPORT_DROPPED:
                kwargs.pop(key, None)
            if instructions is not None:
                kwargs["instructions"] = instructions
            super().__init__(name, **kwargs)

        def streamable_http_app(self, **kwargs):
            return super().streamable_http_app(**{**self._legacy_transport, **kwargs})

    return FastMCP


def install_legacy_fastmcp_module() -> bool:
    """Make ``from mcp.server.fastmcp import FastMCP`` work on SDK 2.x.

    Returns True when the compatibility module was installed, False when the
    real module is importable (SDK 1.x) or no SDK is present. Idempotent.
    """
    import sys
    import types
    if SDK_MAJOR != 2:
        return False
    existing = sys.modules.get("mcp.server.fastmcp")
    if existing is not None and getattr(existing, "__fleet_compat__", False):
        return True
    module = types.ModuleType("mcp.server.fastmcp")
    module.FastMCP = _legacy_fastmcp_class()
    module.__fleet_compat__ = True
    module.__doc__ = "Fleet compatibility module: FastMCP on MCP SDK 2.x."
    sys.modules["mcp.server.fastmcp"] = module
    return True
