# Handoff to Sol — Phase 3c Deploy (gateway mount)

**Attach BOTH folders:** "Agents to deploy copy" (the fleet + gateway) AND "Viridis Core docs 2.0"
(the ViridisOS source). Copy the block below into Sol.

---

```
Two-part deploy task: make ViridisOS's canon-index path relocatable, then mount ViridisOS into the
existing fleet MCP gateway as one more agent. Pure stdlib for Task A. Do not break any existing tests.

CONTEXT
- ViridisOS lives in "Viridis Core docs 2.0/ViridisOS/" (package: certification/, runtime/, modules/,
  integration/, adapters/, viridis_platform.py). Full suite is green (103 integration + 33 existing).
- The fleet lives in "Agents to deploy copy/". Its MCP gateway (viridis_mcp_gateway.py) hosts each agent
  by loading <agent-dir>/adapters/mcp_server.py and mounting it at /<name>/mcp. Fleet gate = 635 tests.
- ViridisOS already has a fleet-convention adapter at ViridisOS/adapters/mcp_server.py (7 tools, FastMCP).

KNOWN GOTCHA (must fix, or the live modules silently break)
runtime/canon_resolver.py finds the canon index via Path(__file__).resolve().parents[2] /
"RESEARCH_PIPELINE_v2/canon_fingerprint_index.json". When ViridisOS is copied under the fleet root, that
relative path no longer resolves and ALL modules go BLOCKED (verified). Fix with an env override.

TASK A — make the canon index relocatable (in "Viridis Core docs 2.0/ViridisOS")
1. In runtime/canon_resolver.py, change the default index to honor an env var, falling back to today's
   path:  _DEFAULT_INDEX = Path(os.environ.get("VIRIDISOS_CANON_INDEX", <the current parents[2] default>))
   (add `import os`). Do not change the CanonResolver interface or any other behavior.
2. Add ViridisOS/integration/tests/test_phase3c_canonenv.py (stdlib, house style):
   - with VIRIDISOS_CANON_INDEX unset, catalog_status() still shows restoration/afforestation/harmonization
     READY and mutualist BLOCKED (unchanged).
   - with VIRIDISOS_CANON_INDEX set to the real index file, same result from a resolver built with no args.
   - with VIRIDISOS_CANON_INDEX set to a nonexistent path, all modules BLOCKED (proves the override is read).
3. Re-run and keep green:
     python3 integration/tests/test_integration.py        (27)
     python3 integration/tests/test_phase2_bridge.py       (14)
     python3 integration/tests/test_phase3_hardening.py    (6)
     python3 integration/tests/test_phase3_mcp.py          (10)
     python3 integration/tests/test_phase3c_server.py      (13)
     python3 integration/tests/test_phase3c_canonenv.py    (new)
     bash run_all_tests.sh                                  (33)

TASK B — mount into the fleet gateway (in "Agents to deploy copy")
1. Co-locate the ViridisOS package at the fleet root where the other agent dirs live (the directory the
   gateway's MOUNTS values resolve against — parents[2] of the gateway file). Copy the whole ViridisOS
   package there as `viridisos/`. Also copy the canon index to `viridisos/_canon/canon_fingerprint_index.json`.
2. In the gateway (viridis_mcp_gateway.py), add ONE MOUNTS entry:  "viridisos": "viridisos"
   Leave everything else untouched.
3. Ensure the gateway process sets the env var before loading mounts:
     VIRIDISOS_CANON_INDEX=<abs path>/viridisos/_canon/canon_fingerprint_index.json
   (set it in the gateway launch / Dockerfile / fly.toml env — wherever the other agents' env is set).
4. Add a publish manifest at deploy/mcp-publish-github/viridisos/ mirroring an existing agent's manifest
   (name "viridisos", mount "/viridisos/mcp", the 7 tool schemas from ViridisOS/integration/mcp_tools.py
   MANIFEST plus viridis_list_modules / viridis_certify / viridis_certify_envelope).

DEFINITION OF DONE
- ViridisOS adapter smoke from the co-located dir shows 3 READY + mutualist BLOCKED (NOT all BLOCKED):
    cd <fleet root>/viridisos && VIRIDISOS_CANON_INDEX=$(pwd)/_canon/canon_fingerprint_index.json \
      python3 adapters/mcp_server.py
- The fleet gateway smoke passes and now lists /viridisos/mcp in GET / :  python3 gateway/gateway_smoke.py
  (or the documented smoke) — /viridisos/mcp responds to tools/list with 7 tools.
- Fleet test gate stays green (635). ViridisOS suites stay green (Task A list above).

HARD RULES
- Additive. The ONLY edits are: canon_resolver.py (env line + import os), the new canonenv test, the
  single MOUNTS line, the gateway env var, and the new deploy/mcp-publish-github/viridisos/ manifest.
- Do NOT touch any agent core, any other gateway logic, escrow/payment code, or Stripe.
- Do NOT swap the signer — the dev HMAC stays; this deploy is the staging preview (mark is preview-only).

WHEN DONE
- Paste: the adapter smoke line showing 3 READY, the gateway smoke result, the fleet gate total, and the
  ViridisOS suite totals. In <=5 bullets say exactly what you changed. Flag any assumption.
```

---

## Notes for Justin (not part of the prompt)
- Both folders must be attached or Sol can't copy ViridisOS into the fleet.
- This is the **staging** mount (dev HMAC). The K3 signer swap is a separate, later task — the mark is
  preview-only until then, by design.
- After this: `/viridisos/mcp` serves the 7 tools next to your 20 agents, one gateway, one directory.
