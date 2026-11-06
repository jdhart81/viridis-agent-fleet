"""X1: the npm port (products/orc-seal-js) and this package are interchangeable.

Same canonical bytes, same float spelling, same digests for the same tool
response, and each verifies the other's receipts. Runs the JS unit suite too,
so the CI `standards` job (which already has node) covers both packages.
"""
import json
import random
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
JS = PKG.parent / "orc-seal-js"
sys.path.insert(0, str(PKG))
from orc_seal import META_KEY, Sealer, verify  # noqa: E402
from orc_seal import orc  # noqa: E402

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node not installed")


def js(job: dict):
    p = subprocess.run([NODE, str(JS / "test" / "parity_cli.mjs")], input=json.dumps(job),
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def _rand_value(rng: random.Random, depth: int = 0):
    kinds = ["int", "bigint", "float", "str", "bool", "null"] + (["list", "dict"] if depth < 3 else [])
    k = rng.choice(kinds)
    if k == "int":
        return rng.randint(-10**6, 10**6)
    if k == "bigint":
        return rng.randint(-10**30, 10**30)
    if k == "float":
        return rng.choice([rng.uniform(-1e6, 1e6), rng.uniform(-1, 1) * 10 ** rng.randint(-30, 30),
                           0.1, -0.0, 1e16, 1e-5, 5e-324, 1.7976931348623157e308])
    if k == "str":
        alphabet = "aZ09 \"\\/\n\t\x01\x7f\u00e9\u2600\uffff\U0001F600\ud800"
        return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8)))
    if k == "bool":
        return rng.random() < 0.5
    if k == "null":
        return None
    if k == "list":
        return [_rand_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    key = lambda: "".join(rng.choice("ab_1\u00e9\uffff\U0001F600") for _ in range(rng.randint(0, 3)))
    return {key(): _rand_value(rng, depth + 1) for _ in range(rng.randint(0, 4))}


def test_x1_canonical_bytes_match_python():
    rng = random.Random(8004)
    texts = [json.dumps(_rand_value(rng), ensure_ascii=rng.random() < 0.5) for _ in range(400)]
    texts += ['{"a":1.0,"a":2}', "[1e400,-1e400,NaN,Infinity,-Infinity]", '{"__proto__":{"x":0.10}}',
              "1" * 4300, "[0.000001,1e-7,123456789012345678]", '"\\ud83d\\ude00\\udc00"']
    want = [orc.canonical(json.loads(t)) for t in texts]
    assert js({"op": "canonical", "texts": texts}) == want


def test_x1_float_repr_matches_python_on_random_doubles():
    rng = random.Random(402)
    hexes, want = [], []
    while len(hexes) < 20000:
        bits = rng.getrandbits(64)
        x = struct.unpack(">d", struct.pack(">Q", bits))[0]
        if x != x or x in (float("inf"), float("-inf")):
            continue
        hexes.append(f"{bits:016x}")
        want.append(repr(x))
    assert js({"op": "repr", "hex": hexes}) == want


PAIRS = [
    ('{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"double","arguments":{"x":21,"secret":"hunter2"}}}',
     '{"jsonrpc":"2.0","id":7,"result":{"content":[{"type":"text","text":"42"}],"structuredContent":{"value":42,"ratio":0.10,"one":1.0},"_meta":{"other":1}}}'),
    ('{"jsonrpc":"2.0","id":"x","method":"tools/call","params":{"name":"caf\\u00e9","arguments":{"f":1e-7,"big":123456789012345678901}}}',
     '{"jsonrpc":"2.0","id":"x","result":{"content":[{"type":"text","text":"Café ☀ \U0001F600"}],"structuredContent":{"n":NaN,"i":-Infinity,"e":1E5}}}'),
    ('{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"noargs"}}',
     '{"jsonrpc":"2.0","id":2,"result":{"content":[]}}'),
]


def test_x1_same_digest_for_the_same_tool_response():
    py = []
    for req, resp in PAIRS:
        r = Sealer({"id": "did:web:example.com", "name": "Example"}, agent="demo").seal_tools_call(
            json.loads(req), json.loads(resp))["result"]["_meta"][META_KEY]
        py.append(r)
    js_lines = js({"op": "seal", "pairs": [list(p) for p in PAIRS]})
    for pr, line in zip(py, js_lines):
        jr = json.loads(line)["result"]["_meta"][META_KEY]
        assert jr["digest"] == pr["digest"]
        assert orc.canonical(jr["output"]) == orc.canonical(pr["output"])
        assert jr["subject"] == pr["subject"] and jr["issuer"] == pr["issuer"]
        assert verify(jr)["label"] == "INTACT"                          # JS seal, Python verify


def test_x1_js_verifies_python_receipts_and_catches_tampering():
    s = Sealer({"id": "did:web:example.com"}, agent="demo")
    good = s.seal("carbon", {"kwh": 1000}, {"content": [{"type": "text", "text": "Café ☀ 386.0"}],
                                            "structuredContent": {"kg": 0.386, "big": 10**25}})
    bad = json.loads(json.dumps(good))
    bad["output"]["result"]["structuredContent"]["kg"] = "0.387"
    out = js({"op": "verify", "receipts": [json.dumps(good), json.dumps(good, ensure_ascii=False),
                                           json.dumps(bad), "{}"]})
    assert [o["label"] for o in out] == ["INTACT", "INTACT", "NONE", "NONE"]


def test_x1_js_conformance_vectors_and_unit_suite():
    p = subprocess.run([NODE, "--test", *sorted(str(f) for f in (JS / "test").glob("*.test.js"))],
                       capture_output=True, text=True, timeout=300, cwd=JS)
    assert p.returncode == 0, p.stdout[-4000:] + p.stderr[-2000:]


def test_x1_npx_proxy_in_front_of_a_real_mcp_sdk_server(tmp_path):
    """The Node proxy fronting a Python MCP SDK server; Python verifies the receipt."""
    pytest.importorskip("mcp.server.fastmcp", reason="needs the mcp 1.x SDK (FastMCP)")
    import asyncio
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
            command=NODE,
            args=[str(JS / "bin" / "orc-seal.js"), "--issuer", "did:web:example.com", "--agent", "demo",
                  "--", sys.executable, str(server)],
            env={"PATH": "/usr/bin:/bin"})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                assert [t.name for t in (await s.list_tools()).tools] == ["carbon"]
                return await s.call_tool("carbon", {"kwh": 1000})
    res = asyncio.run(go())
    receipt = res.meta[META_KEY]
    assert verify(receipt)["label"] == "INTACT"
    assert receipt["subject"] == {"agent": "demo", "tool": "carbon"}
    assert "386.0" in json.dumps(receipt["output"]["result"])
