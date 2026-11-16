#!/usr/bin/env python3
"""Per-server docs for every MCP Registry entry (SD1-SD6).

GitHub's MCP Registry review asks, for each server: what it does, its tools
with inputs and outputs, an example request and response, how a client
connects (with authentication and pricing), and how the hosted endpoint
relates to this repository and who publishes it. This script writes one page
per registry entry, docs/servers/<name>.md, from two inputs:

  deploy/mcp-publish-github/*/server.json   registry name, endpoint, version
  docs/servers/snapshot.json                what the live endpoint serves

    python3 scripts/server_docs.py capture   # refresh the snapshot (network)
    python3 scripts/server_docs.py build     # write the pages (no network)
    python3 scripts/server_docs.py check     # fail if a page is stale

SD1 one page per registry entry, named after the registry name.
SD2 every tool the endpoint lists appears with its description and every
    input with its type, whether it is required, and its description.
SD3 the example is a real request sent to the live endpoint and the answer it
    returned (shortened), recorded in the snapshot with its capture time. The
    example tool is read-only or a published example, so capturing never
    changes production records.
SD4 prices come from the live x402 catalog; nothing is priced by hand.
SD5 connection, payment and ownership text is the same on every page and
    points to docs/HOSTED_MCP.md.
SD6 build is deterministic: the same snapshot gives the same bytes.
SD8 every page and README row shows the mcptry live-status badge (all
    listings are claimed by jdhart81, so the badge reports live checks).
SD7 the root README's registry table lists every entry with its page; a
    hand-written agent README stays linked beside its page.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "deploy" / "mcp-publish-github"
OUT = ROOT / "docs" / "servers"
SNAPSHOT = OUT / "snapshot.json"
HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream",
           "MCP-Protocol-Version": "2026-07-28", "x-viridis-probe": "1",
           "user-agent": "viridis-server-docs/1"}
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "viridis-server-docs", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {}}

# SD3: example calls that only compute or read. Anything not listed uses the
# tool's own published "Example arguments", else describe_agent / describe_method.
SAFE_EXAMPLES = {
    "compute-ledger": ("intelligence_bound", {"power_w": 100}),
    "green-router": ("quote_footprint", {"workload": {"backend_id": "efficient_cloud",
                                                      "total_tokens": 10000, "output_tokens": 2000}}),
    "surety": ("price_bond", {"coverage_minor": 100000, "duration_days": 30}),
    "trust": ("score_agent", {"agent_id": "example-agent"}),
    "regulatory-radar": ("scan_regulations", {"jurisdiction": "california", "sector": "energy"}),
}
MAX_EXAMPLE_LINES = 40
# The hosted gateway's shared rails: a tool there that changes records needs a
# caller credential (read-only tools never do). Mirrors the gateway's
# credential gate; its tests (SA1-SA4) keep "open" and "read-only" aligned.
CREDENTIAL_MOUNTS = frozenset({
    "arbitration", "compute-ledger", "covenant", "escrow", "green-router", "hive",
    "identity", "metering", "notary", "offsets", "provenance", "security-preflight",
    "subscriptions", "surety", "trust", "verified",
})


def _summary(entry: dict, record: dict) -> str:
    """The agent's own one-sentence description (agent.yaml), else the registry's."""
    manifest = ROOT / entry["folder"] / "agent.yaml"
    if manifest.exists():
        match = re.search(r'^description:\s*"?(.*?)"?\s*$', manifest.read_text(), re.M)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return entry["description"]


def registry_entries() -> list[dict]:
    entries = []
    for path in sorted(REGISTRY.glob("*/server.json")):
        meta = json.loads(path.read_text())
        url = meta["remotes"][0]["url"]
        mount = url.rstrip("/").split("/")[-2]
        entries.append({"name": meta["name"], "short": meta["name"].split("/")[-1],
                        "folder": path.parent.name, "url": url, "mount": mount,
                        "version": meta.get("version", ""), "description": meta.get("description", "")})
    return entries


LEGACY_VERSION = "2025-06-18"
_legacy_sessions: dict = {}


def _send(url: str, payload: dict, headers: dict):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers,
                                 method="POST")
    with urllib.request.urlopen(req, timeout=60) as response:
        text = response.read().decode()
        session = response.headers.get("mcp-session-id")
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:]), session
    return (json.loads(text) if text.strip() else {}), session


def _legacy_post(url: str, method: str, params: dict) -> dict:
    """Servers not yet on protocol 2026-07-28: initialize, then call in that session."""
    base = {k: v for k, v in HEADERS.items() if k != "MCP-Protocol-Version"}
    if url not in _legacy_sessions:
        _, session = _send(url, {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
            "protocolVersion": LEGACY_VERSION, "capabilities": {},
            "clientInfo": {"name": "viridis-server-docs", "version": "1"}}}, base)
        headers = {**base, "MCP-Protocol-Version": LEGACY_VERSION}
        if session:
            headers["mcp-session-id"] = session
        _send(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, headers)
        _legacy_sessions[url] = headers
    answer, _ = _send(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                      _legacy_sessions[url])
    return answer


def _post(url: str, method: str, params: dict) -> dict:
    if url in _legacy_sessions:
        return _legacy_post(url, method, params)
    headers = {**HEADERS, "Mcp-Method": method}
    if method == "tools/call":
        headers["Mcp-Name"] = params["name"]
    try:
        answer, _ = _send(url, {"jsonrpc": "2.0", "id": 1, "method": method,
                                "params": {**params, "_meta": META}}, headers)
        return answer
    except urllib.error.HTTPError as exc:
        if exc.code == 400 and b"Unsupported protocol version" in exc.read():
            return _legacy_post(url, method, params)
        raise


def _published_example(tool: dict):
    match = re.search(r"Example arguments:\s*(\{.*\})\s*$", tool.get("description") or "", re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


def pick_example(mount: str, tools: list[dict]):
    if mount in SAFE_EXAMPLES:
        return SAFE_EXAMPLES[mount]
    for tool in tools:
        args = _published_example(tool)
        if args is not None:
            return tool["name"], args
    names = [t["name"] for t in tools]
    for name in ("describe_agent", "describe_method", "describe_network"):
        if name in names:
            return name, {}
    for tool in tools:
        hints = tool.get("annotations") or {}
        required = (tool.get("inputSchema") or {}).get("required") or []
        if hints.get("readOnlyHint") and not required:
            return tool["name"], {}
    return None


def capture() -> None:
    entries = registry_entries()
    catalog = {}
    for base in sorted({e["url"].split("/" + e["mount"] + "/")[0] for e in entries}):
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    base + "/x402/catalog", headers=HEADERS), timeout=60) as response:
                catalog[base] = json.loads(response.read())
        except Exception as exc:                                   # noqa: BLE001
            catalog[base] = {"error": repr(exc)}
    servers = {}
    for entry in entries:
        tools = _post(entry["url"], "tools/list", {})["result"]["tools"]
        example = pick_example(entry["mount"], tools)
        record = {"tools": tools, "example": None}
        if example:
            name, args = example
            try:
                answer = _post(entry["url"], "tools/call", {"name": name, "arguments": args})
            except urllib.error.HTTPError as exc:            # SD3: no example beats a fake one
                record["example_skipped"] = f"{name}: HTTP {exc.code}"
                answer = None
            result = (answer or {}).get("result") or {}
            if answer is not None and (result.get("isError") or "error" in answer):
                record["example_skipped"] = f"{name}: tool returned an error"
                answer = None
            if answer is not None:
                content = result.get("content") or [{}]
                text = content[0].get("text", json.dumps(result))
                try:
                    text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
                except ValueError:
                    pass
                record["example"] = {"tool": name, "arguments": args, "response": text}
        servers[entry["name"]] = record
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps({
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "catalog": catalog, "servers": servers}, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"captured {len(servers)} servers")


def _type(prop: dict) -> str:
    if "anyOf" in prop:
        kinds = [p.get("type") or ("object" if "$ref" in p else "?") for p in prop["anyOf"]]
        return " or ".join(k for k in kinds if k != "null") or "any"
    if "$ref" in prop:
        return "object"
    kind = prop.get("type", "any")
    if kind == "array" and isinstance(prop.get("items"), dict):
        inner = prop["items"].get("type") or ("object" if "$ref" in prop["items"] else "any")
        return f"array of {inner}"
    return kind


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _first_sentence(text: str, limit: int = 220) -> str:
    text = " ".join((text or "").split())
    text = re.split(r"\s*Example arguments:", text)[0]
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def _prices(catalog: dict, mount: str) -> dict:
    """tool -> price string, from the live x402 catalog (SD4)."""
    out = {}
    for base, data in catalog.items():
        items = data.get("routes") or data.get("items") or data.get("tools") or []
        if isinstance(items, dict):
            items = list(items.values())
        for item in items:
            if not isinstance(item, dict):
                continue
            agent = item.get("agent") or item.get("server")
            tool = item.get("tool")
            minor = item.get("price_minor") or item.get("amount_minor")
            if agent == mount and tool and isinstance(minor, int):
                out[tool] = f"${minor / 100:.2f}"
    return out


def badge(name: str) -> str:
    """mcptry's live status and score for a claimed listing (SD8)."""
    return f"[![mcptry](https://mcptry.com/badge/{name})](https://mcptry.com/servers/{name})"


def render(entry: dict, record: dict, catalog: dict, captured_at: str) -> str:
    tools = record["tools"]
    prices = _prices(catalog, entry["mount"])
    folder = entry["folder"]
    has_folder = (ROOT / folder).is_dir()
    lines = [f"# {entry['name']}", "", badge(entry["name"]), "",
             f"{_cell(_summary(entry, record))}", "",
             "| | |", "|---|---|",
             f"| Registry name | `{entry['name']}` |",
             f"| Endpoint (Streamable HTTP) | `{entry['url']}` |",
             f"| Version | {entry['version']} |",
             f"| Tools | {len(tools)} |"]
    if has_folder:
        lines.append(f"| Source | [`{folder}/`](../../{folder}/) |")
    lines += ["", "## Connect", "",
              "No account, API key or OAuth is needed to connect, list tools or call free tools.", "",
              "```json", json.dumps({"mcpServers": {f"viridis-{entry['short']}": {
                  "type": "http", "url": entry["url"]}}}, indent=2), "```", "",
              f"Claude Code: `claude mcp add --transport http viridis-{entry['short']} {entry['url']}`",
              "",
              "Claude, ChatGPT, VS Code, API and stdio-only clients: "
              "[docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).", "",
              "## Tools", ""]
    for tool in tools:
        schema = tool.get("inputSchema") or {}
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        hints = tool.get("annotations") or {}
        kind = "read-only" if hints.get("readOnlyHint") else "changes records"
        price = prices.get(tool["name"])
        lines.append(f"### `{tool['name']}`")
        lines.append("")
        lines.append(_first_sentence(tool.get("description") or ""))
        lines.append("")
        meta = [kind]
        if not hints.get("readOnlyHint") and entry["mount"] in CREDENTIAL_MOUNTS:
            meta.append("may need a caller credential (see below)")
        if price:
            meta.append(f"{price} per call after the free daily calls (x402 catalog)")
        if tool.get("outputSchema"):
            meta.append("structured output")
        lines.append("*" + "; ".join(meta) + "*")
        lines.append("")
        if props:
            lines += ["| Input | Type | Required | Description |", "|---|---|---|---|"]
            for arg, prop in props.items():
                lines.append(f"| `{arg}` | {_type(prop)} | {'yes' if arg in required else 'no'} | "
                             f"{_cell(prop.get('description') or '')} |")
            lines.append("")
        else:
            lines += ["No inputs.", ""]
    example = record.get("example")
    if example:
        response = example["response"].splitlines()
        if len(response) > MAX_EXAMPLE_LINES:
            response = response[:MAX_EXAMPLE_LINES] + ["  …"]
        lines += ["## Example", "",
                  f"Request (`tools/call`, captured from the live endpoint on {captured_at[:10]}):", "",
                  "```json", json.dumps({"name": example["tool"], "arguments": example["arguments"]},
                                        indent=2, ensure_ascii=False), "```", "",
                  "Response (shortened):", "", "```json", *response, "```", ""]
    lines += ["## Pricing and authentication", "",
              "Read-only and verification tools are free. Paid tools include 10 free calls per "
              "caller per UTC day over MCP; after that a call returns `payment_required` with the "
              "exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). "
              "Per-call prices shown above come from the live x402 catalog; a paid tool without "
              "one states its price in that `payment_required` answer. "
              "Nothing is charged without a separate, explicit payment. A call that cannot be "
              "attempted, or that determines nothing, is not charged. Details: "
              "[docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).", ""]
    if entry["mount"] in CREDENTIAL_MOUNTS:
        lines += ["This server is one of the fleet's shared rails, so on the hosted endpoint a "
                  "tool that changes records needs a caller credential (`Authorization: Bearer "
                  "<token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns "
                  "HTTP 401 and nothing changes. Read-only tools never need one. To get a "
                  "credential, email <justin@viridisconservation.com>, or self-host from the "
                  "source folder, where no credential applies.", ""]
    lines += [
              "## Hosted service and this repository", "",
              ("This server's logic, MCP adapter and tests are open source (Apache-2.0) in "
               f"[`{folder}/`](../../{folder}/); self-hosting gives the same results for the same "
               "inputs. " if has_folder else
               "This server is operated by Viridis; its hosted adapter is not in this repository. ")
              + "The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) "
              "is operated by Viridis and is not in this repository. The hosted service is operated "
              "by ViridisNorth LLC; the \"Viridis\" marks belong to Viridis LLC; both are owned by "
              "Justin Hart, who publishes as GitHub `jdhart81`. Contact: "
              "<justin@viridisconservation.com>.", "",
              f"*Generated by `scripts/server_docs.py` from the live endpoint ({captured_at}).*", ""]
    return "\n".join(lines)


README = ROOT / "README.md"
TABLE_START = "| Registry name | Remote endpoint | Docs | Live status |"
DEDICATED = {"security-preflight", "regulatory-radar", "ghg-ledger"}


def readme_text() -> str:
    text = README.read_text()
    start = text.index(TABLE_START)
    end = text.index("\n\n", start)
    rows = [TABLE_START, "|---|---|---|---|"]
    for entry in registry_entries():
        links = [f"[docs/servers/{entry['short']}.md](docs/servers/{entry['short']}.md)"]
        if entry["short"] in DEDICATED:
            links.append(f"[{entry['folder']}/README.md]({entry['folder']}/README.md)")
        rows.append(f"| `{entry['name']}` | `{entry['url']}` | {' · '.join(links)} | {badge(entry['name'])} |")
    return text[:start] + "\n".join(rows) + text[end:]


def build(write: bool = True) -> list[str]:
    snapshot = json.loads(SNAPSHOT.read_text())
    stale = []
    for entry in registry_entries():
        record = snapshot["servers"].get(entry["name"])
        if record is None:
            raise SystemExit(f"SD1: {entry['name']} is not in the snapshot; run capture")
        text = render(entry, record, snapshot["catalog"], snapshot["captured_at"])
        path = OUT / f"{entry['short']}.md"
        if not path.exists() or path.read_text() != text:
            stale.append(str(path.relative_to(ROOT)))
            if write:
                path.write_text(text)
    index = readme_text()
    if README.read_text() != index:
        stale.append("README.md")
        if write:
            README.write_text(index)
    return stale


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    if mode == "capture":
        capture()
    elif mode == "build":
        print("\n".join(build()) or "up to date")
    elif mode == "check":
        stale = build(write=False)
        if stale:
            raise SystemExit("stale: " + ", ".join(stale))
        print("up to date")
    else:
        raise SystemExit(__doc__)
