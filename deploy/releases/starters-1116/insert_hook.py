"""Add the starters hook to a live adapter file (stdlib only; run on the host).

    python3 insert_hook.py <key> <live mcp_server.py> <out mcp_server.py>

Works from the file that is live, so unrelated changes made there since are
kept. Refuses (exit 1) unless the file has exactly one line
``flag_error_results(mcp)`` and no ``apply_starters`` yet. The block goes
right after that line, as in commit 39c3399.
"""
import sys

ANCHOR = "flag_error_results(mcp)\n"
BLOCK = (
    "\n"
    "try:  # first-call starters: \"use this server when\" instructions + MCP prompts\n"
    "    from fleet_utils.starters import apply_starters\n"
    "except ImportError:  # pragma: no cover - adapter copied without fleet_utils\n"
    "    def apply_starters(server, key):\n"
    "        return 0\n"
    "apply_starters(mcp, \"{key}\")\n"
)

key, src, dst = sys.argv[1:4]
if key not in ("ghg-ledger", "regulatory-radar", "disclosure-compiler"):
    sys.exit(f"unknown key {key}")
lines = open(src).readlines()
if any("apply_starters" in line for line in lines):
    sys.exit(f"{src}: already has apply_starters")
hits = [i for i, line in enumerate(lines) if line == ANCHOR]
if len(hits) != 1:
    sys.exit(f"{src}: expected one '{ANCHOR.strip()}' line, found {len(hits)}")
i = hits[0] + 1
lines[i:i] = BLOCK.format(key=key).splitlines(keepends=True)
open(dst, "w").writelines(lines)
print(f"{key}: hook added after line {i}")
