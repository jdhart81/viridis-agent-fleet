"""
MCP adapter for wavefunction-search-agent: the Wavefunction Field (v0.1).

This replaces the prototype intent-routing core with the open-source
wavefunction-field reference implementation (Apache-2.0), vendored as a
pure-Python wheel in ../vendor and imported straight from the zip.

Gateway contract: this module exposes
  mcp   - FastMCP server, mounted by the gateway at /wavefunction (tools + REST)
  agent - fleet core with async process()/health() and describe()

State: the field persists to its own append-only, hash-chained SQLite log
(WF_DB_PATH, default /data/wavefunction_field.sqlite3). `agent` carries no
instance state, so gateway StateStore snapshots stay empty. The legacy
prototype module (src/core.py) is imported if present so an existing
pre-upgrade snapshot still unpickles (PS2/PS11); its restored attributes are
inert.
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_WHEELS = sorted((ROOT / "vendor").glob("wavefunction_field-*.whl"))
if not _WHEELS:
    raise RuntimeError("vendored wavefunction_field wheel missing")
if str(_WHEELS[-1]) not in sys.path:
    sys.path.insert(0, str(_WHEELS[-1]))

try:  # legacy prototype: kept importable for snapshot compatibility only
    import src.core  # noqa: F401
except Exception:  # pragma: no cover - absent in fresh checkouts
    pass

from wavefunction_field.fleet.gateway import build_gateway_surface  # noqa: E402

mcp, agent = build_gateway_surface()

try:  # report {"status": "error"} results to MCP clients as tool errors (isError)
    from fleet_utils.mcp_errors import flag_error_results
except ImportError:  # loaded without the fleet root on sys.path, as the gateway does
    _fleet_root = Path(__file__).resolve().parents[2]
    if (_fleet_root / "fleet_utils").is_dir() and str(_fleet_root) not in sys.path:
        sys.path.append(str(_fleet_root))
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
        print(json.dumps(asyncio.run(agent.health()), indent=2))
