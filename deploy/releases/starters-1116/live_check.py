"""Live MCP check for the starters-1116 release (stdlib only; run on the host).

    python3 live_check.py <base_url> record <tools.json>
        Before the swap: records each server's tools (name + schema hash).
    python3 live_check.py <base_url> verify <tools.json>
        After the swap, over the public Streamable HTTP endpoint, per server:
          L1 initialize answers with the new instructions,
          L2 prompts/list shows the starter prompts and prompts/get renders them,
          L3 tools/list is identical to the recording.
        Prints LIVE_STARTERS_OK or exits 1. Calls no tool, so it uses no
        free allowance and charges nothing.
"""
import hashlib
import json
import sys
import urllib.request

MOUNTS = ["ghg-ledger", "regulatory-radar", "disclosure-compiler"]
OPENING = {"ghg-ledger": "Use this server when someone wants greenhouse-gas",
           "regulatory-radar": "Use this server when someone asks which climate",
           "disclosure-compiler": "Use this server to draft a climate disclosure"}
STARTERS = {"ghg-ledger": {"footprint_from_bills": "calculate_inventory"},
            "regulatory-radar": {"which_climate_rules_apply": "scan_regulations",
                                 "what_changed_since_last_time": "watch_changes"},
            "disclosure-compiler": {"sb253_first_draft": "compile_disclosure"}}
SAMPLES = {
    "footprint_from_bills": {"electricity_kwh": "12000", "year": "2025"},
    "which_climate_rules_apply": {"jurisdiction": "california"},
    "what_changed_since_last_time": {"jurisdiction": "california"},
    "sb253_first_draft": {"company": "Example Co", "reporting_year": "2025",
                          "electricity_kwh": "12000"},
}
UA = "viridis-release-check/starters-1116"


class Session:
    def __init__(self, url):
        self.url, self.sid, self.proto, self.n = url, None, None, 0

    def _post(self, body):
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream",
                     "User-Agent": UA})
        if self.sid:
            req.add_header("Mcp-Session-Id", self.sid)
        if self.proto:
            req.add_header("MCP-Protocol-Version", self.proto)
        with urllib.request.urlopen(req, timeout=60) as resp:
            self.sid = resp.headers.get("mcp-session-id") or self.sid
            ctype = resp.headers.get("content-type", "")
            raw = resp.read().decode()
        if not raw.strip():
            return None
        if "text/event-stream" in ctype:
            found = None
            for line in raw.splitlines():
                if line.startswith("data:"):
                    msg = json.loads(line[5:].strip())
                    if msg.get("id") == body.get("id"):
                        found = msg
            return found
        return json.loads(raw)

    def call(self, method, params=None):
        self.n += 1
        msg = self._post({"jsonrpc": "2.0", "id": self.n, "method": method,
                          "params": params or {}})
        if not msg or "error" in msg:
            raise RuntimeError(f"{method}: {msg and msg.get('error')}")
        return msg["result"]

    def open(self):
        init = self.call("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": UA, "version": "1"}})
        self.proto = init.get("protocolVersion")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return init

    def all(self, method, key):
        items, cursor = [], None
        while True:
            res = self.call(method, {"cursor": cursor} if cursor else {})
            items += res.get(key, [])
            cursor = res.get("nextCursor")
            if not cursor:
                return items

    def close(self):
        if not self.sid:
            return
        try:
            req = urllib.request.Request(self.url, method="DELETE",
                                         headers={"Mcp-Session-Id": self.sid,
                                                  "User-Agent": UA})
            urllib.request.urlopen(req, timeout=10).close()
        except Exception:
            pass


def tool_sig(tools):
    return sorted([t["name"], hashlib.sha256(json.dumps(
        t.get("inputSchema"), sort_keys=True).encode()).hexdigest()[:16]]
        for t in tools)


def main(base, mode, path):
    base = base.rstrip("/")
    if mode == "record":
        rec = {}
        for mount in MOUNTS:
            s = Session(f"{base}/{mount}/mcp")
            s.open()
            rec[mount] = tool_sig(s.all("tools/list", "tools"))
            s.close()
            print(f"{mount}: recorded {len(rec[mount])} tools")
        json.dump(rec, open(path, "w"))
        return
    rec = json.load(open(path))
    bad = []
    for mount in MOUNTS:
        s = Session(f"{base}/{mount}/mcp")
        try:
            init = s.open()
            inst = init.get("instructions") or ""
            if not inst.startswith(OPENING[mount]):
                bad.append(f"{mount}: L1 instructions are {inst[:50]!r}")
            names = {p["name"] for p in s.all("prompts/list", "prompts")}
            for name, tool in STARTERS[mount].items():
                if name not in names:
                    bad.append(f"{mount}: L2 prompt {name} not listed")
                    continue
                got = s.call("prompts/get", {"name": name, "arguments": SAMPLES[name]})
                text = (got.get("messages") or [{}])[0].get("content", {}).get("text", "")
                if tool not in text:
                    bad.append(f"{mount}: L2 prompt {name} did not render")
            tools = tool_sig(s.all("tools/list", "tools"))
            if tools != rec[mount]:
                bad.append(f"{mount}: L3 tools changed")
            print(f"{mount}: instructions {'new' if inst.startswith(OPENING[mount]) else 'OLD'}, "
                  f"prompts {sorted(names & set(STARTERS[mount]))}, {len(tools)} tools")
        except Exception as exc:  # network or protocol failure counts as a fail
            bad.append(f"{mount}: {exc}")
        finally:
            s.close()
    if bad:
        print("LIVE CHECK FAILED: " + "; ".join(bad))
        sys.exit(1)
    print("LIVE_STARTERS_OK")


if __name__ == "__main__":
    main(*sys.argv[1:4])
