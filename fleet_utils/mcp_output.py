"""Canonical structured-output contract for Viridis FastMCP adapters."""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional, TypedDict, cast


class _FleetToolStatus(TypedDict):
    status: str


class FleetToolResult(_FleetToolStatus, total=False):
    """Stable result envelope advertised directly through MCP outputSchema."""

    data: Any
    result: Any
    error: Any
    error_type: Optional[str]
    field: Optional[str]
    constraint: Optional[str]
    message: Optional[str]
    timestamp: Optional[str]


def structured_result(result: Mapping[str, Any]) -> FleetToolResult:
    """Return a JSON-safe result mapping without double encoding it."""
    if not isinstance(result, Mapping):
        raise TypeError("MCP tool results must be mappings")
    value = dict(result)
    if not isinstance(value.get("status"), str) or not value["status"]:
        raise ValueError("MCP tool results require a non-empty status")
    json.dumps(value, allow_nan=False)
    return cast(FleetToolResult, value)
