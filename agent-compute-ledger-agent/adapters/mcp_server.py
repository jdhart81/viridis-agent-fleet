"""
MCP adapter for agent-compute-ledger-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py.
Run: python adapters/mcp_server.py            (smoke: describe + health)
     python adapters/mcp_server.py --serve    (stdio MCP server; needs `mcp`)
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from mcp.server.fastmcp import FastMCP
    HAS_MCP = True
except ImportError:  # pragma: no cover
    HAS_MCP = False

    class FastMCP:  # stdlib shim so smoke tests run anywhere
        def __init__(self, name, **kw): self.name, self.tools = name, {}
        def tool(self, *a, **k):
            def deco(fn): self.tools[fn.__name__] = fn; return fn
            return deco
        def run(self): raise RuntimeError("`mcp` SDK not installed - pip install mcp")

from src.core import build

def _mk_mcp(name, description=""):
    """FastMCP compat across SDK versions (description -> instructions -> bare)."""
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)

mcp = _mk_mcp("agent-compute-ledger-agent",
              description="Compute-is-carbon energy/carbon ledger for agent work "
                          "with Landauer-limit validation.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


try:  # MCP tool annotations: let hosts and registries see which tools are safe reads
    from mcp.types import ToolAnnotations as _ToolAnnotations
except ImportError:  # pragma: no cover - stdlib shim keeps smoke tests runnable
    def _ToolAnnotations(**kw):
        return kw
_READ = _ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                         idempotentHint=True, openWorldHint=False)
_WRITE = _ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                          idempotentHint=False, openWorldHint=False)
_DESTRUCTIVE = _ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                idempotentHint=False, openWorldHint=False)


@mcp.tool(annotations=_WRITE)
async def record_work(agent_id: str, entry_id: str, power_w: float, duration_s: float,
                task: str = "", bit_ops: Optional[float] = None,
                temperature_k: float = 300.0,
                grid_intensity_g_per_kwh: float = 400.0,
                price_minor_per_kwh: Optional[float] = None) -> str:
    """Record a unit of agent compute work. energy_j = power_w * duration_s;
    carbon_g follows from grid intensity. If bit_ops is declared, the entry is
    validated against the Landauer floor (bit_ops * kB * T * ln2) — physically
    impossible claims are rejected. Idempotent on entry_id."""
    return await _run({"action": "record_work", "agent_id": agent_id, "entry_id": entry_id,
                 "power_w": power_w, "duration_s": duration_s, "task": task,
                 "bit_ops": bit_ops, "temperature_k": temperature_k,
                 "grid_intensity_g_per_kwh": grid_intensity_g_per_kwh,
                 "price_minor_per_kwh": price_minor_per_kwh})


@mcp.tool(annotations=_READ)
async def footprint(agent_id: str) -> str:
    """Aggregate footprint for an agent: total J, kWh, gCO2e, cost, and mean
    Landauer efficiency. Totals are exact sums of the ledger entries."""
    return await _run({"action": "footprint", "agent_id": agent_id})


@mcp.tool(annotations=_WRITE)
async def attest(entry_id: str) -> str:
    """Issue a content-addressed attestation for a ledger entry (verifiable
    green-compute / energy claim)."""
    return await _run({"action": "attest", "entry_id": entry_id})


@mcp.tool(annotations=_READ)
async def verify_attestation(attestation: Dict[str, Any]) -> str:
    """Verify an attestation by recomputing the entry hash."""
    return await _run({"action": "verify_attestation", "attestation": attestation})


@mcp.tool(annotations=_READ)
async def verify_chain(agent_id: str) -> str:
    """Verify the tamper-evident hash chain of an agent's ledger."""
    return await _run({"action": "verify_chain", "agent_id": agent_id})


@mcp.tool(annotations=_READ)
async def list_entries(agent_id: str) -> str:
    """List all ledger entries for an agent."""
    return await _run({"action": "list_entries", "agent_id": agent_id})


@mcp.tool(annotations=_WRITE)
async def carbon_receipt(entry_id: str, offset_ref: str = "") -> str:
    """Emit an x402-C carbon receipt for a recorded work entry — the
    physically-grounded {version, g_co2e, energy_j, method, landauer_*, ...}
    object an x402 machine-payment receipt can carry. method is
    'landauer-floor' when the workload declared bit_ops (thermodynamically
    validated), else 'measured'. Pass offset_ref (a retirement id from the
    offset clearinghouse) to assert carbon-neutrality. Read-only; the returned
    attestation_hash binds the receipt to the ledger's hash chain."""
    payload = {"action": "carbon_receipt", "entry_id": entry_id}
    if offset_ref:
        payload["offset_ref"] = offset_ref
    return await _run(payload)


@mcp.tool(annotations=_WRITE)
async def record_inventory(agent_id: str, inventory_id: str, mass_g: int,
                           content_digest: str, factor_pack_version: str,
                           factor_pack_digest: str,
                           source_ids: Optional[List[str]] = None) -> str:
    """Record an audited GHG inventory in a separate append-only chain.
    mass_g is exact integer grams; content and factor-pack digests are bare
    lowercase SHA-256 hex. Idempotent on inventory_id."""
    return await _run({"action": "record_inventory", "agent_id": agent_id,
                       "inventory_id": inventory_id, "mass_g": mass_g,
                       "content_digest": content_digest,
                       "factor_pack_version": factor_pack_version,
                       "factor_pack_digest": factor_pack_digest,
                       "source_ids": source_ids or []})


@mcp.tool(annotations=_READ)
async def get_inventory(inventory_id: str) -> str:
    """Fetch one immutable inventory record by inventory_id."""
    return await _run({"action": "get_inventory", "inventory_id": inventory_id})


@mcp.tool(annotations=_READ)
async def list_inventories(agent_id: str) -> str:
    """List the separate GHG inventory chain for an agent."""
    return await _run({"action": "list_inventories", "agent_id": agent_id})


@mcp.tool(annotations=_READ)
async def verify_inventory_chain(agent_id: str) -> str:
    """Verify an agent's inventory hash chain independently of compute work."""
    return await _run({"action": "verify_inventory_chain", "agent_id": agent_id})


@mcp.tool(annotations=_READ)
async def describe_agent() -> str:
    """Describe this agent: name, version, purpose, every action it supports
    and the inputs each one takes. Read-only and free; call it first to learn
    how to use this server."""
    return json.dumps(agent.describe(), default=str, indent=2)


try:  # report {"status": "error"} results to MCP clients as tool errors (isError)
    from fleet_utils.mcp_errors import flag_error_results
except ImportError:  # loaded without the fleet root on sys.path, as the gateway does
    import sys as _sys
    from pathlib import Path as _Path
    _fleet_root = _Path(__file__).resolve().parents[2]
    if (_fleet_root / "fleet_utils").is_dir() and str(_fleet_root) not in _sys.path:
        _sys.path.append(str(_fleet_root))
    try:
        from fleet_utils.mcp_errors import flag_error_results
    except ImportError:  # pragma: no cover - adapter copied without fleet_utils
        def flag_error_results(server):
            return 0
flag_error_results(mcp)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), default=str, indent=2))
        print(json.dumps(asyncio.run(agent.health()), default=str, indent=2))
