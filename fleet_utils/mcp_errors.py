"""
Report fleet error envelopes to MCP clients as tool errors.

MOTIVATION (fleet health scorecard, 2026-10-28):
Fleet tools return their result as JSON text (or a ``FleetToolResult``
mapping). A failed call comes back as ``{"status": "error", ...}``, but
FastMCP only sets ``isError`` when the tool raises. So every failed call
reached agent hosts, registries and usage stats as a success, and the
fleet's real success rate could not be seen.

``flag_error_results(mcp)`` fixes that in one place per adapter. It wraps
each registered tool so that a result whose top-level ``status`` is
``"error"`` is sent as a ``CallToolResult`` with ``isError=True``. The body
the client receives does not change; only the flag does.

INVARIANTS (verified in test_mcp_errors.py):
  E1. A result whose top-level JSON object has ``status == "error"`` reaches
      the MCP client with ``isError=True``.
  E2. That error result carries the same text content and the same
      structured content the client got before this change.
  E3. Every other result (another status, non-JSON text, a JSON value that
      is not an object) is returned unchanged.
  E4. Calling the decorated module-level function directly is unchanged:
      only the registered tool is wrapped, not the module symbol.
  E5. Wrapping is idempotent; a second call wraps nothing.
  E6. Without the ``mcp`` SDK (the stdlib smoke shim) it is a no-op that
      returns 0 and never raises.
  E7. ``tools/list`` output (names, schemas, annotations) is unchanged.
  E8. An exception raised by a tool propagates exactly as before.

Usage (once, after the last ``@mcp.tool``):
    from fleet_utils.mcp_errors import flag_error_results
    flag_error_results(mcp)
"""

from __future__ import annotations

import functools
import inspect
import json
from typing import Any, Mapping, Optional

__all__ = ["is_error_result", "flag_error_results"]

_MARKER = "__fleet_flags_errors__"


def _as_mapping(result: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(result, Mapping):
        return result
    if isinstance(result, (str, bytes, bytearray)):
        try:
            value = json.loads(result)
        except (TypeError, ValueError):
            return None
        return value if isinstance(value, Mapping) else None
    return None


def is_error_result(result: Any) -> bool:
    """True when ``result`` is a fleet error envelope (``status == "error"``)."""
    value = _as_mapping(result)
    return value is not None and value.get("status") == "error"


def _error_call_result(tool: Any, result: Any, call_tool_result: type) -> Any:
    """Build the CallToolResult FastMCP would have sent, with isError set (E2)."""
    try:
        converted = tool.fn_metadata.convert_result(result)
    except Exception:  # pragma: no cover - leave anything unconvertible as it was
        return result
    if isinstance(converted, tuple):
        content, structured = converted
    else:
        content, structured = converted, None
    return call_tool_result(content=list(content), structuredContent=structured,
                            isError=True)


def _wrap(fn: Any, tool: Any, call_tool_result: type) -> Any:
    def flag(result: Any) -> Any:
        if is_error_result(result):
            return _error_call_result(tool, result, call_tool_result)
        return result

    # Keep the sync/async kind: FastMCP awaits based on how the tool was registered.
    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return flag(await fn(*args, **kwargs))
    else:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return flag(fn(*args, **kwargs))
    setattr(wrapper, _MARKER, True)
    return wrapper


def flag_error_results(server: Any) -> int:
    """Wrap every tool registered on a FastMCP ``server``; return how many."""
    try:
        from mcp.types import CallToolResult
    except ImportError:  # E6: stdlib smoke shim
        return 0
    manager = getattr(server, "_tool_manager", None)
    if manager is None or not hasattr(manager, "list_tools"):
        return 0
    tools = manager.list_tools()
    if inspect.isawaitable(tools):  # another FastMCP flavour: leave it alone
        getattr(tools, "close", lambda: None)()
        return 0
    wrapped = 0
    for tool in tools:
        if not hasattr(tool, "fn_metadata") or getattr(tool.fn, _MARKER, False):
            continue
        tool.fn = _wrap(tool.fn, tool, CallToolResult)
        wrapped += 1
    return wrapped
