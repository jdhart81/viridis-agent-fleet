"""M1-M7 (sealer) and P1-P4 (stdio proxy) for orc-seal."""
import asyncio
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[1]
sys.path.insert(0, str(PKG))
from orc_seal import META_KEY, RegistryClient, Sealer, normalize, sealed, verify  # noqa: E402
from orc_seal import orc as vendored  # noqa: E402
from orc_seal.proxy import Tracker, transform_server_line  # noqa: E402

ISSUER = {"id": "did:web:example.com", "name": "Example"}
REQ = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
       "params": {"name": "double", "arguments": {"x": 21, "secret": "hunter2"}}}
RESP = {"jsonrpc": "2.0", "id": 7,
        "result": {"content": [{"type": "text", "text": "42"}],
                   "structuredContent": {"value": 42, "ratio": 0.1},
                   "_meta": {"other": 1}}}


class FakeResp:
    def __init__(self, status, body):
        self.status, self.body = status, body
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): return False


def opener_echo(captured):
    def op(req, timeout):
        body = json.loads(req.data)
        captured.append({"body": body, "headers": dict(req.header_items()), "timeout": timeout})
        return FakeResp(200, json.dumps({
            "commitment": body["commitment"], "digest": body["digest"],
            "issuer_proof": {"method": "registry",
                             "url": "https://reg.test/orc/v0/commitments/" + body["commitment"]}}).encode())
    return op


def test_vendored_orc_is_byte_identical_to_reference():
    assert (PKG / "orc_seal" / "orc.py").read_bytes() == (ROOT / "fleet_utils" / "orc.py").read_bytes()


def test_m1_m6_result_preserved_and_only_meta_added():
    s = Sealer(ISSUER, agent="demo")
    out = s.seal_tools_call(REQ, json.loads(json.dumps(RESP)))
    assert {k: v for k, v in out["result"].items() if k != "_meta"} == \
        {k: v for k, v in RESP["result"].items() if k != "_meta"}
    assert out["result"]["_meta"]["other"] == 1
    assert set(out["result"]["_meta"]) == {"other", META_KEY}
    assert RESP["result"]["_meta"] == {"other": 1}          # input not mutated


def test_m2_receipt_verifies_intact_and_tamper_fails():
    s = Sealer(ISSUER, agent="demo")
    r = s.seal_tools_call(REQ, RESP)["result"]["_meta"][META_KEY]
    assert verify(r)["label"] == "INTACT"
    bad = json.loads(json.dumps(r)); bad["output"]["result"]["structuredContent"]["value"] = 43
    assert verify(bad)["level"] == 0
    assert r["verify"]["page"].endswith("/verify?c=" + r["commitment"]["value"])


def test_m3_args_never_in_receipt_nor_registry_payload():
    cap = []
    s = Sealer(ISSUER, registry=RegistryClient("https://reg.test", "k", opener=opener_echo(cap)))
    r = s.seal_tools_call(REQ, RESP)["result"]["_meta"][META_KEY]
    assert "hunter2" not in json.dumps(r)
    sent = json.dumps(cap[0]["body"])
    assert "hunter2" not in sent and "42" not in sent.replace(r["commitment"]["value"], "").replace(r["digest"]["value"], "").replace(r["commitment"]["salt"], "")
    assert set(cap[0]["body"]) == {"commitment", "salt", "digest", "profile", "issuer", "subject", "issued_at"}
    assert cap[0]["headers"]["Authorization"] == "Bearer k"


def test_m4_registry_success_adds_proof_and_l2():
    cap = []
    s = Sealer(ISSUER, registry=RegistryClient("https://reg.test", "k", opener=opener_echo(cap)))
    r = s.seal("double", {"x": 1}, {"v": 2})
    assert r["issuer_proof"]["url"].endswith(r["commitment"]["value"])
    rec = {"commitment": r["commitment"]["value"], "digest": r["digest"]["value"]}
    assert verify(r, registry_lookup=lambda u: rec)["label"] == "ISSUED"
    assert verify(r, registry_lookup=lambda u: {**rec, "digest": "0" * 64})["label"] == "INTACT"


@pytest.mark.parametrize("opener", [
    lambda req, timeout: (_ for _ in ()).throw(OSError("down")),
    lambda req, timeout: FakeResp(500, b"{}"),
    lambda req, timeout: FakeResp(200, b"not json"),
    lambda req, timeout: FakeResp(200, json.dumps({"commitment": "0" * 64, "digest": "0" * 64,
                                                   "issuer_proof": {"method": "registry", "url": "https://x"}}).encode()),
])
def test_m4_registry_failures_fail_open_to_intact(opener):
    reg = RegistryClient("https://reg.test", "k", opener=opener)
    s = Sealer(ISSUER, registry=reg)
    out = s.seal_tools_call(REQ, RESP)
    r = out["result"]["_meta"][META_KEY]
    assert "issuer_proof" not in r and verify(r)["label"] == "INTACT"
    assert reg.last_error


def test_m5_normalization_deterministic_and_idempotent():
    x = {1: (0.1, float("nan"), float("inf"), -float("inf"), b"ab"), "k": [True, None, 3]}
    n = normalize(x)
    assert n == {"1": ["0.1", "NaN", "Infinity", "-Infinity",
                       {"bytes_sha256": "fb8e20fc2e4c3f248c60c39bd652f3c1347298bb977b8b4d5903b85055620603"}],
                 "k": [True, None, 3]}
    assert normalize(n) == n
    s = Sealer(ISSUER)
    a, b = s.seal("t", {"x": 0.1}, {"y": 1.5}), s.seal("t", {"x": 0.1}, {"y": 1.5})
    assert a["digest"]["value"] == b["digest"]["value"]


def test_m6_errors_and_iserror_pass_through():
    s = Sealer(ISSUER)
    err = {"jsonrpc": "2.0", "id": 7, "error": {"code": -1, "message": "x"}}
    assert s.seal_tools_call(REQ, err) is err
    ie = {"jsonrpc": "2.0", "id": 7, "result": {"content": [], "isError": True}}
    assert s.seal_tools_call(REQ, ie) is ie
    other = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
    assert s.seal_tools_call({"method": "tools/list", "id": 1}, other) is other


def test_m7_oversized_not_sealed():
    s = Sealer(ISSUER)
    big = {"jsonrpc": "2.0", "id": 7, "result": {"content": [{"type": "text", "text": "a" * 300_000}]}}
    out = s.seal_tools_call(REQ, big)
    assert out["result"]["_meta"][META_KEY] == {"skipped": "too_large"}
    assert out["result"]["content"] == big["result"]["content"]


def test_decorator_sync_and_async():
    s = Sealer(ISSUER)

    @sealed(s)
    def add(a, b): return a + b

    @sealed(s, tool="mul")
    async def mul(a, b): return a * b

    r1 = add(2, 3)
    assert r1["result"] == 5 and verify(r1["orc"])["level"] == 1
    r2 = asyncio.run(mul(2, 3))
    assert r2["result"] == 6 and r2["orc"]["subject"]["tool"] == "mul"


def test_issuer_required():
    with pytest.raises(ValueError):
        Sealer({"name": "no id"})


# ---- proxy -----------------------------------------------------------------
def test_p1_non_tool_lines_byte_identical():
    s, t = Sealer(ISSUER), Tracker()
    for line in [b"garbage\n", b'{"jsonrpc":"2.0","method":"notifications/x"}\n',
                 b'{"jsonrpc":"2.0","id":9,"result":{"a":1.50}}\n', b"[1,2]\n"]:
        assert transform_server_line(line, t, s) == line


def test_p_end_to_end_subprocess_proxy():
    cmd = [sys.executable, "-m", "orc_seal", "--issuer", "did:web:example.com", "--",
           sys.executable, str(HERE / "fake_server.py")]
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": "a", "method": "tools/call", "params": {"name": "double", "arguments": {"x": 4}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "fail"}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "iserror"}}]
    stdin = "".join(json.dumps(m) + "\n" for m in msgs).encode()
    p = subprocess.run(cmd, input=stdin, capture_output=True, cwd=PKG, timeout=30,
                       env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(PKG)})
    assert p.returncode == 0, p.stderr
    lines = [json.loads(x) for x in p.stdout.decode().splitlines()]
    assert [m["id"] for m in lines] == [1, "a", 3, 4]                     # P2
    assert lines[0]["result"] == {"echo": "initialize"}
    r = lines[1]["result"]
    assert r["content"][0]["text"] == "8" and r["structuredContent"]["ratio"] == 0.1
    assert verify(r["_meta"][META_KEY])["label"] == "INTACT"
    assert "error" in lines[2] and "_meta" not in lines[3]["result"]


def test_p_real_mcp_sdk_server_through_proxy(tmp_path):
    # The fleet (and production gateway) pins mcp 1.x. mcp 2.x renamed FastMCP
    # to MCPServer; skip rather than fail if a 2.x SDK is installed here.
    pytest.importorskip("mcp.server.fastmcp", reason="needs the mcp 1.x SDK (FastMCP)")
    server = tmp_path / "srv.py"
    server.write_text(
        "from mcp.server.fastmcp import FastMCP\n"
        "m = FastMCP('demo')\n"
        "@m.tool()\n"
        "def carbon(kwh: float) -> dict:\n"
        "    return {'kg_co2e': round(kwh * 0.386, 3)}\n"
        "m.run()\n")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "orc_seal", "--issuer", "did:web:example.com", "--agent", "demo",
                  "--", sys.executable, str(server)],
            env={"PYTHONPATH": str(PKG), "PATH": "/usr/bin:/bin"}, cwd=str(PKG))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = await s.list_tools()
                assert [t.name for t in tools.tools] == ["carbon"]
                res = await s.call_tool("carbon", {"kwh": 1000})
                return res
    res = asyncio.run(go())
    receipt = res.meta[META_KEY]
    assert verify(receipt)["label"] == "INTACT"
    sealed_text = json.dumps(receipt["output"]["result"])
    assert "386.0" in sealed_text                      # the tool's answer is what got sealed
    assert [c.text for c in res.content] == [c["text"] for c in receipt["output"]["result"]["content"]]
    assert receipt["subject"] == {"agent": "demo", "tool": "carbon"}


def test_browser_verifier_agrees(tmp_path):
    """The public verify page's JS core accepts orc-seal receipts and rejects tampering."""
    import shutil
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = Sealer(ISSUER, agent="demo").seal(
        "carbon", {"kwh": 1000},
        {"content": [{"type": "text", "text": "Café ☀ 386.0"}], "structuredContent": {"kg": 0.386}})
    good = tmp_path / "good.json"; good.write_text(json.dumps(r))
    t = json.loads(json.dumps(r)); t["output"]["result"]["structuredContent"]["kg"] = "0.387"
    bad = tmp_path / "bad.json"; bad.write_text(json.dumps(t))
    js = (
        "const fs=require('fs');"
        f"const h=fs.readFileSync({json.dumps(str(ROOT / 'products/signed-cliff-check/verify.html'))},'utf8');"
        "const s=[...h.matchAll(/<script(?:\\s[^>]*)?>([\\s\\S]*?)<\\/script>/g)].map(x=>x[1]).find(x=>x.includes('verifyReceipt'));"
        "const m={exports:{}};new Function('module','require',s)(m,require);"
        f"Promise.all([{json.dumps(str(good))},{json.dumps(str(bad))}].map(p=>m.exports.verifyReceipt(fs.readFileSync(p,'utf8'))))"
        ".then(v=>console.log(JSON.stringify(v.map(x=>x.verified))))")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "[true,false]", out.stderr


def test_p4_server_dies_early_proxy_exits_with_its_code_cleanly(tmp_path):
    """P4 regression: server exits while the client's stdin is still open."""
    dead = tmp_path / "dead.py"
    dead.write_text("import sys; sys.stderr.write('boom\\n'); sys.exit(3)\n")
    p = subprocess.Popen([sys.executable, "-m", "orc_seal", "--issuer", "did:web:example.com", "--",
                          sys.executable, str(dead)],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         cwd=PKG, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(PKG)})
    try:
        out, err = p.communicate(timeout=15)   # stdin is left open until communicate closes it
    except subprocess.TimeoutExpired:
        p.kill(); raise
    assert p.returncode == 3
    assert b"Fatal Python error" not in err


def test_p4_server_dies_early_with_client_still_writing(tmp_path):
    """Same, but the client keeps its stdin pipe open (not closed by communicate)."""
    import time
    dead = tmp_path / "dead.py"
    dead.write_text("import sys, time; time.sleep(0.2); sys.exit(5)\n")
    p = subprocess.Popen([sys.executable, "-m", "orc_seal", "--issuer", "did:web:example.com", "--",
                          sys.executable, str(dead)],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         cwd=PKG, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(PKG)})
    p.stdin.write(b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'); p.stdin.flush()
    deadline = time.time() + 15
    while p.poll() is None and time.time() < deadline:
        time.sleep(0.05)
    assert p.returncode == 5, "proxy must exit when the server exits, even with stdin open"
    err = p.stderr.read()
    assert b"Fatal Python error" not in err
    p.stdin.close()
