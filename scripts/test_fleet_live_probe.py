"""Offline tests for fleet_live_probe.py against a local fake registry + MCP servers."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet_live_probe as p  # noqa: E402

CALLS = []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", headers=None):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        servers = [
            {"server": {"name": "io.github.jdhart81/json-ok", "version": "1",
                        "remotes": [{"url": base + "/json/mcp"}]},
             "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
            {"server": {"name": "io.github.jdhart81/sse-ok", "version": "1",
                        "remotes": [{"url": base + "/sse/mcp"}]},
             "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
            {"server": {"name": "io.github.jdhart81/down", "version": "1",
                        "remotes": [{"url": base + "/down/mcp"}]},
             "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
            {"server": {"name": "io.github.jdhart81/json-ok", "version": "0",
                        "remotes": [{"url": base + "/old/mcp"}]},
             "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": False}}},
            {"server": {"name": "io.github.someoneelse/x", "version": "1",
                        "remotes": [{"url": base + "/x/mcp"}]},
             "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
        ]
        self._send(200, json.dumps({"servers": servers, "metadata": {}}))

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        kind = self.path.split("/")[1]
        CALLS.append((kind, body.get("method"), self.headers.get("Mcp-Session-Id"),
                      (body.get("params") or {}).get("name")))
        if kind == "down":
            return self._send(502, "bad gateway", "text/plain")
        if "id" not in body:
            return self._send(202, b"")
        m = body["method"]
        if m == "initialize":
            res = {"protocolVersion": p.PROTOCOL, "capabilities": {},
                   "serverInfo": {"name": kind, "version": "9.9"}}
        elif m == "tools/list":
            res = {"tools": [
                {"name": "describe_agent", "description": "Describe this agent fully, read-only and free.",
                 "annotations": {"readOnlyHint": True}, "inputSchema": {"type": "object"}},
                {"name": "do_thing", "description": "short", "inputSchema": {"type": "object"}}]}
        elif m == "tools/call":
            res = {"content": [{"type": "text", "text": "{}"}], "isError": False}
        msg = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": res})
        hdr = {"Mcp-Session-Id": "sess-" + kind} if m == "initialize" else {}
        if kind == "sse":
            return self._send(200, f"event: message\ndata: {msg}\n\n", "text/event-stream", hdr)
        return self._send(200, msg, "application/json", hdr)


def run_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_invariants(tmp_path):
    srv = run_server()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        entries = p.registry_entries(base + "/v0/servers", ("io.github.jdhart81/",))
        # I1: latest entries only, own namespace only, each once
        assert sorted(entries) == ["io.github.jdhart81/down", "io.github.jdhart81/json-ok",
                                   "io.github.jdhart81/sse-ok"]
        assert entries["io.github.jdhart81/json-ok"]["url"].endswith("/json/mcp")
        CALLS.clear()
        r_json = p.probe("json-ok", entries["io.github.jdhart81/json-ok"]["url"], True)
        r_sse = p.probe("sse-ok", entries["io.github.jdhart81/sse-ok"]["url"], True)
        r_down = p.probe("down", entries["io.github.jdhart81/down"]["url"], True)
        # I2 + I3
        assert r_json["up"] and r_sse["up"] and not r_down["up"]
        assert r_json["tools"] == r_sse["tools"] == 2
        assert "HTTP 502" in r_down["error"]
        # lint
        assert r_json["unannotated"] == ["do_thing"] and r_json["short_desc"] == ["do_thing"]
        # I4: session id reused after initialize
        for kind in ("json", "sse"):
            later = [c for c in CALLS if c[0] == kind and c[1] != "initialize"]
            assert later and all(c[2] == "sess-" + kind for c in later)
        # I5: only describe_agent is ever called
        called = {c[3] for c in CALLS if c[1] == "tools/call"}
        assert called == {"describe_agent"}
        CALLS.clear()
        p.probe("json-ok", entries["io.github.jdhart81/json-ok"]["url"], False)
        assert not [c for c in CALLS if c[1] == "tools/call"]
        # I6: exit code
        out = tmp_path / "o.json"
        os.environ.pop("GITHUB_STEP_SUMMARY", None)
        assert p.main(["--registry", base + "/v0/servers", "--json", str(out)]) == 1
        data = json.loads(out.read_text())
        assert {r["name"].split("/")[-1] for r in data["results"]} >= {"json-ok", "sse-ok", "down"}
        md = p.markdown([r_json, r_sse])
        assert "2/2 healthy" in md
    finally:
        srv.shutdown()


class Flaky(BaseHTTPRequestHandler):
    """Registry that fails the first FAILS GETs with 503, then lists one server."""
    FAILS = 0
    seen = 0

    def log_message(self, *a):
        pass

    def do_GET(self):
        type(self).seen += 1
        if type(self).seen <= type(self).FAILS:
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.dumps({"servers": [
            {"server": {"name": "io.github.jdhart81/a", "version": "1",
                        "remotes": [{"url": "http://127.0.0.1:9/mcp"}]},
             "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}}],
            "metadata": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _flaky(fails):
    Flaky.FAILS, Flaky.seen = fails, 0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Flaky)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# I7: transient registry failures are retried
def test_registry_retries_transient_failures():
    srv = _flaky(p.REGISTRY_TRIES - 1)
    waits = []
    try:
        got = p.registry_entries(f"http://127.0.0.1:{srv.server_port}/v0/servers",
                                 ("io.github.jdhart81/",), sleep=waits.append)
    finally:
        srv.shutdown()
    assert list(got) == ["io.github.jdhart81/a"]
    assert len(waits) == p.REGISTRY_TRIES - 1 and waits == sorted(waits)


def test_client_errors_are_not_retried():
    import urllib.error
    import pytest
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise urllib.error.HTTPError("u", 404, "nf", {}, None)
    orig = p.urllib.request.urlopen
    p.urllib.request.urlopen = boom
    try:
        with pytest.raises(urllib.error.HTTPError):
            p._registry_get("http://x", sleep=lambda s: None)
    finally:
        p.urllib.request.urlopen = orig
    assert calls == [1]


# I7: a registry that stays down still yields a probe file with registry_error
def test_unreachable_registry_still_writes_probe_file(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "REGISTRY_BACKOFF", 0)
    out = tmp_path / "o.json"
    # port 9 (discard) on loopback refuses connections
    assert p.main(["--registry", "http://127.0.0.1:9/v0/servers", "--json", str(out)]) == 1
    data = json.loads(out.read_text())
    assert data["results"] == [] and "registry_error" in data
