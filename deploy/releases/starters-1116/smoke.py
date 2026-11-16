"""Offline smoke test for the starters-1116 release (run inside an image).

    python3 smoke.py probe <fleet_root> <out.json | ->
        Loads the three adapters the way the tests do (one subprocess each,
        no network) and records, per server: the instructions it answers
        initialize with, its tools (name + input-schema hash), its prompts,
        and the rendered length of each starter prompt.

    python3 smoke.py compare <before.json> <after.json>
        Stdlib only. Passes when, on every server:
          R1 the new instructions are served (known opening words),
          R2 the starter prompts are listed, render non-empty text, and every
             prompt that existed before is still there,
          R3 tools and input schemas are identical before and after.
        Prints SMOKE_OK or exits 1 with the reason.
"""
import json
import subprocess
import sys

AGENTS = {"ghg-ledger": "ghg-ledger-agent",
          "regulatory-radar": "regulatory-radar-agent",
          "disclosure-compiler": "disclosure-compiler-agent"}
OPENING = {"ghg-ledger": "Use this server when someone wants greenhouse-gas",
           "regulatory-radar": "Use this server when someone asks which climate",
           "disclosure-compiler": "Use this server to draft a climate disclosure"}
STARTERS = {"ghg-ledger": ["footprint_from_bills"],
            "regulatory-radar": ["which_climate_rules_apply",
                                 "what_changed_since_last_time"],
            "disclosure-compiler": ["sb253_first_draft"]}
SAMPLES = {
    "footprint_from_bills": {"electricity_kwh": "12000", "year": "2025"},
    "which_climate_rules_apply": {"jurisdiction": "california"},
    "what_changed_since_last_time": {"jurisdiction": "california"},
    "sb253_first_draft": {"company": "Example Co", "reporting_year": "2025",
                          "electricity_kwh": "12000"},
}

PROBE = r"""
import asyncio, hashlib, json, sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from adapters import mcp_server as adapter
from fleet_utils.mcp_compat import connect, field
samples = json.loads(sys.argv[3])
server = adapter.mcp

def h(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]

async def main():
    out = {}
    async with connect(server) as client:
        inst = getattr(client, "instructions", None)
        if inst is None:
            low = getattr(server, "_mcp_server", None)
            if low is not None:
                inst = low.create_initialization_options().instructions
        out["instructions"] = inst or ""
        tools = await client.list_tools()
        out["tools"] = sorted([field(t, "name"), h(field(t, "inputSchema"))]
                              for t in field(tools, "tools"))
        prompts = await client.list_prompts()
        out["prompts"] = sorted(field(p, "name") for p in field(prompts, "prompts"))
        out["rendered"] = {}
        for name in out["prompts"]:
            if name in samples:
                got = await client.get_prompt(name, samples[name])
                msgs = field(got, "messages")
                text = field(field(msgs[0], "content"), "text") if msgs else ""
                out["rendered"][name] = len(text or "")
    print("SMOKE_JSON " + json.dumps(out))

asyncio.run(main())
"""


def probe(root, out_path):
    result = {}
    for key, folder in AGENTS.items():
        agent_dir = f"{root}/{folder}"
        res = subprocess.run([sys.executable, "-c", PROBE, agent_dir, root,
                              json.dumps(SAMPLES)], capture_output=True,
                             text=True, cwd=agent_dir, timeout=120)
        line = [l for l in res.stdout.splitlines() if l.startswith("SMOKE_JSON ")]
        if res.returncode != 0 or not line:
            print(f"PROBE FAILED for {key}:\n{res.stderr[-2000:]}")
            sys.exit(1)
        result[key] = json.loads(line[-1][len("SMOKE_JSON "):])
        r = result[key]
        print(f"{key}: {len(r['tools'])} tools, prompts {r['prompts']}, "
              f"instructions start {r['instructions'][:40]!r}")
    if out_path == "-":  # print it, for a container that cannot write out
        print("SMOKE_RESULT " + json.dumps(result))
        return
    with open(out_path, "w") as fh:
        json.dump(result, fh)


def compare(before_path, after_path):
    before = json.load(open(before_path))
    after = json.load(open(after_path))
    bad = []
    for key in AGENTS:
        b, a = before[key], after[key]
        if not a["instructions"].startswith(OPENING[key]):
            bad.append(f"{key}: R1 new instructions not served")
        for name in STARTERS[key]:
            if name not in a["prompts"]:
                bad.append(f"{key}: R2 prompt {name} missing")
            elif a["rendered"].get(name, 0) < 50:
                bad.append(f"{key}: R2 prompt {name} rendered no text")
        lost = sorted(set(b["prompts"]) - set(a["prompts"]))
        if lost:
            bad.append(f"{key}: R2 prompts lost {lost}")
        if a["tools"] != b["tools"]:
            bad.append(f"{key}: R3 tools or schemas changed")
        elif not bad:
            print(f"{key}: {len(a['tools'])} tools identical, "
                  f"+{len(set(a['prompts']) - set(b['prompts']))} prompts, new instructions")
    if bad:
        print("SMOKE FAILED: " + "; ".join(bad))
        sys.exit(1)
    print("SMOKE_OK")


if __name__ == "__main__":
    if sys.argv[1] == "probe":
        probe(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "compare":
        compare(sys.argv[2], sys.argv[3])
    else:
        sys.exit("usage: smoke.py probe <root> <out.json> | compare <before> <after>")
