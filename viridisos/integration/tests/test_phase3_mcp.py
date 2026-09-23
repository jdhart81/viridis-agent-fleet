"""Phase 3b acceptance — the unified MCP tool surface.

Run from the ViridisOS package root:
    python3 integration/tests/test_phase3_mcp.py
Green ("N passed, 0 failed") == Phase 3b done. DO NOT EDIT — implement mcp_tools.py instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from integration.trust_root import TrustRoot
from integration.toll import compute_toll
from integration.mcp_tools import MANIFEST, call_tool, _TOOL_NAMES

_PASS = 0; _FAIL = 0
def check(name, cond):
    global _PASS, _FAIL
    if cond: _PASS += 1
    else: _FAIL += 1; print(f"  FAIL: {name}")


# ---- manifest shape -------------------------------------------------------
def m_manifest_shape():
    ok = isinstance(MANIFEST, list) and len(MANIFEST) >= 4
    for t in MANIFEST:
        ok = ok and all(k in t for k in ("name", "description", "input_schema"))
        ok = ok and t["name"].startswith("viridis_")
    check("MCP manifest well-formed", ok)


# ---- bind_did -------------------------------------------------------------
def m_bind_did():
    root = TrustRoot()
    expected = root.bind_did("agent-42", "PK")
    r = call_tool("viridis_bind_did", {"agent_id": "agent-42", "pubkey": "PK"})
    check("bind_did returns canonical did", r.get("did") == expected)
    check("bind_did is did:viridis", str(r.get("did", "")).startswith("did:viridis:"))


# ---- compute_toll ---------------------------------------------------------
def m_toll():
    r = call_tool("viridis_compute_toll", {"amount_minor": 10_000, "payee_tier": "connect_verified"})
    check("toll matches compute_toll", r == compute_toll(10_000, "connect_verified"))

def m_toll_bad_tier():
    r = call_tool("viridis_compute_toll", {"amount_minor": 10_000, "payee_tier": "platinum"})
    check("toll bad tier -> error (no raise)", "error" in r)


# ---- agent_attestation round-trips through verify_mark --------------------
def m_attestation_roundtrip():
    root = TrustRoot()
    issued = call_tool("viridis_agent_attestation", {"event": {"did": "did:viridis:x", "act": "deliver"}},
                       root=root)
    env = issued.get("envelope")
    check("attestation returns envelope dict", isinstance(env, dict) and env.get("mark"))
    v = call_tool("viridis_verify_mark", {"envelope": env, "profile": "agent-attestation"}, root=root)
    check("verify_mark accepts fresh attestation", v.get("valid") is True)

def m_verify_rejects_tamper():
    root = TrustRoot()
    issued = call_tool("viridis_agent_attestation", {"event": {"act": "deliver"}}, root=root)
    env = dict(issued["envelope"])
    env["payload"] = {"act": "TAMPERED"}
    v = call_tool("viridis_verify_mark", {"envelope": env, "profile": "agent-attestation"}, root=root)
    check("verify_mark rejects tampered envelope", v.get("valid") is False)


# ---- unknown tool ---------------------------------------------------------
def m_unknown_tool():
    r = call_tool("viridis_not_a_tool", {})
    check("unknown tool -> error (no raise)", "error" in r)
    check("tool name set matches manifest", _TOOL_NAMES == {t["name"] for t in MANIFEST})


TESTS = [
    m_manifest_shape, m_bind_did, m_toll, m_toll_bad_tier,
    m_attestation_roundtrip, m_verify_rejects_tamper, m_unknown_tool,
]

if __name__ == "__main__":
    for t in TESTS:
        try: t()
        except NotImplementedError:
            _FAIL += 1; print(f"  FAIL: {t.__name__} (NotImplementedError — stub not yet implemented)")
        except Exception as e:  # noqa: BLE001
            _FAIL += 1; print(f"  FAIL: {t.__name__} ({type(e).__name__}: {e})")
    print(f"{_PASS} passed, {_FAIL} failed")
    sys.exit(0 if _FAIL == 0 else 1)
