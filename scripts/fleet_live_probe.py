#!/usr/bin/env python3
"""Live health probe for every hosted Viridis MCP server.

Reads the official MCP registry for this fleet's latest entries, then for each
remote URL runs the same handshake an agent host runs: initialize,
notifications/initialized and tools/list. With --call-describe it also calls
`describe_agent` (free, read-only) where a server offers it.

It also lints what agent hosts and registries grade: tools without
annotations and tools with very short descriptions.

Stdlib only. Exit code 1 when any server fails, so a scheduled workflow
turns red and notifies the owner.

Invariants (checked by scripts/test_fleet_live_probe.py):
  I1  every latest registry entry for the configured namespaces is probed once
  I2  a server is UP only if initialize AND tools/list succeed with a JSON-RPC result
  I3  JSON and SSE (text/event-stream) responses are both understood
  I4  the Mcp-Session-Id header from initialize is sent on later requests
  I5  the probe never calls a tool other than describe_agent, and only with --call-describe
  I6  exit code is 0 iff every probed server is UP (and describe calls succeed when requested)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers"
NAMESPACES = ("io.github.jdhart81/", "io.github.viridis-security/")
UA = "viridis-fleet-probe/1.0 (+synthetic health check; exclude from usage stats)"
PROTOCOL = "2025-06-18"
SHORT_DESC = 40


def registry_entries(base: str = REGISTRY, namespaces=NAMESPACES) -> dict:
    out: dict = {}
    for ns in namespaces:
        cursor = None
        while True:
            q = {"search": ns.rstrip("/").split("/")[-1],
                 "limit": "100"}
            if cursor:
                q["cursor"] = cursor
            req = urllib.request.Request(f"{base}?{urllib.parse.urlencode(q)}",
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            for item in data.get("servers", []):
                srv = item.get("server", item)
                meta = item.get("_meta", {}).get(
                    "io.modelcontextprotocol.registry/official", {})
                name = srv.get("name", "")
                if not name.startswith(ns) or not meta.get("isLatest"):
                    continue
                if meta.get("status", "active") != "active":
                    continue
                remotes = [x.get("url") for x in srv.get("remotes", []) if x.get("url")]
                if remotes:
                    out[name] = {"version": srv.get("version"), "url": remotes[0]}
            cursor = data.get("metadata", {}).get("nextCursor")
            if not cursor:
                break
    return out


def _parse_body(raw: str, content_type: str):
    if "event-stream" in content_type:
        msg = None
        for line in raw.splitlines():
            if line.startswith("data:"):
                try:
                    j = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if isinstance(j, dict) and "id" in j:
                    msg = j
        return msg
    try:
        return json.loads(raw) if raw.strip() else None
    except ValueError:
        return None


def rpc(url: str, body: dict, session: str | None = None, timeout: float = 30):
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "User-Agent": UA}
    if session:
        headers["Mcp-Session-Id"] = session
        headers["MCP-Protocol-Version"] = PROTOCOL
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, hdrs, raw = r.status, r.headers, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, hdrs, raw = e.code, e.headers, e.read().decode("utf-8", "replace")
    except Exception as e:  # network, TLS, timeout
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "ms": int((time.monotonic() - t0) * 1000)}
    ms = int((time.monotonic() - t0) * 1000)
    msg = _parse_body(raw, hdrs.get("Content-Type", ""))
    out = {"ok": 200 <= status < 300, "status": status, "ms": ms, "msg": msg,
           "session": hdrs.get("Mcp-Session-Id")}
    if not out["ok"] or msg is None:
        out["ok"] = False
        out["error"] = f"HTTP {status}: {raw[:200]}"
    elif "error" in msg:
        out["ok"] = False
        out["error"] = f"JSON-RPC error: {json.dumps(msg['error'])[:200]}"
    return out


def probe(name: str, url: str, call_describe: bool = False) -> dict:
    res = {"name": name, "url": url, "up": False}
    init = rpc(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                                "clientInfo": {"name": "viridis-fleet-probe",
                                               "version": "1.0"}}})
    res["init_ms"] = init.get("ms")
    if not init["ok"]:
        res["error"] = "initialize: " + init.get("error", "")
        return res
    info = init["msg"].get("result", {}).get("serverInfo", {})
    res["server_version"] = info.get("version")
    sid = init.get("session")
    rpc(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    tl = rpc(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, sid)
    res["list_ms"] = tl.get("ms")
    if not tl["ok"]:
        res["error"] = "tools/list: " + tl.get("error", "")
        return res
    tools = tl["msg"].get("result", {}).get("tools", [])
    res["tools"] = len(tools)
    res["unannotated"] = sorted(t["name"] for t in tools if not t.get("annotations"))
    res["short_desc"] = sorted(t["name"] for t in tools
                               if len(t.get("description") or "") < SHORT_DESC)
    res["up"] = len(tools) > 0
    if not tools:
        res["error"] = "tools/list returned no tools"
    if call_describe and res["up"] and any(t["name"] == "describe_agent" for t in tools):
        c = rpc(url, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                      "params": {"name": "describe_agent", "arguments": {}}}, sid)
        result = (c.get("msg") or {}).get("result", {})
        res["describe_ms"] = c.get("ms")
        res["describe_ok"] = bool(c["ok"] and not result.get("isError"))
        if not res["describe_ok"]:
            res["error"] = "describe_agent: " + (c.get("error") or "isError=true")
    return res


def markdown(results: list) -> str:
    up = sum(1 for r in results if r["up"] and r.get("describe_ok", True))
    lines = [f"## Viridis MCP fleet: {up}/{len(results)} healthy", "",
             "| Server | Up | Tools | Init ms | List ms | Unannotated | Error |",
             "|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda x: (x["up"], x["name"])):
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            r["name"].split("/")[-1], "yes" if r["up"] else "NO", r.get("tools", "-"),
            r.get("init_ms", "-"), r.get("list_ms", "-"), len(r.get("unannotated", [])),
            (r.get("error") or "").replace("|", "/")[:120]))
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--registry", default=REGISTRY)
    ap.add_argument("--call-describe", action="store_true",
                    help="also call the free read-only describe_agent tool")
    ap.add_argument("--json", default="fleet_probe.json")
    ap.add_argument("--summary", default="", help="append markdown here (e.g. $GITHUB_STEP_SUMMARY)")
    a = ap.parse_args(argv)
    entries = registry_entries(a.registry)
    results = [probe(n, e["url"], a.call_describe) for n, e in sorted(entries.items())]
    with open(a.json, "w") as f:
        json.dump({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "results": results}, f, indent=1)
    md = markdown(results)
    print(md)
    if a.summary:
        with open(a.summary, "a") as f:
            f.write(md)
    healthy = all(r["up"] and r.get("describe_ok", True) for r in results)
    return 0 if healthy and results else 1


if __name__ == "__main__":
    sys.exit(main())
