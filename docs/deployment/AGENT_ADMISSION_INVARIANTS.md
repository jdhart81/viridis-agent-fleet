# Agent Admission Invariants (AA1–AA7)

**Ratified 2026-07-18 (Justin Hart).** Every agent added to the Viridis MCP
network must satisfy ALL of these before its deploy is complete. They are
machine-checked by `deploy/gateway/test_admission_invariants.py` — the fleet
suite FAILS if a mount is missing any wiring. A mounted agent that is
undiscoverable, unpriced, or un-networked is inventory, not economy.

## The invariants

- **AA1 — DISCOVERABLE**: the mount has an `AGENT_SEO` entry in the gateway
  (description ≤ 280 chars, 2–5 intent-matched natural-language queries).
  The ARD catalog is the storefront; an agent absent from it does not exist
  to the market.

- **AA2 — ECONOMIC DECISION, EXPLICIT**: the mount is EITHER gated (present
  in `PRICE_MINOR` + the gateway's gate-attach list, priced per the pricing
  doctrine: value-leader, benchmarked, never race-to-bottom) OR a declared
  free rail (present in the `FREE_RAILS` set with a one-line reason). Never
  neither; never both. Free-by-omission is a bug.

- **AA3 — REVENUE MODEL ON RECORD**: `agent.yaml` exists with non-empty
  `revenue_model` and `thesis_connection`. If we cannot write down how it
  makes money or why it serves the thesis, it does not mount.

- **AA4 — NETWORK EDGES**: the agent's responses teach at least one
  composition edge to another fleet mount (PB9/FT9 doctrine: next_steps in
  success envelopes). An agent whose outputs terminate the conversation
  adds a node but no edges — network effect comes from taught edges.
  (Checked in spirit by review; the doc requires naming the edges here.)
  - verdigraph: build → notary (commit hash), identity (bind DID);
    verify FREE so brain_ids spread as shared references.
  - neurogenesis: create → verdigraph (certify genome); ledger/export FREE
    so developmental audit trails are portable.

- **AA5 — SHIPPING SURFACES CURRENT**: deck.html `ROLE` map, Glama
  `fleet_bridge.py` ROLE map, and the regenerated `fleet_manifest.json`
  include the mount; the Dockerfile has its COPY line (crash-loop gotcha);
  count-pinned release tests re-baselined in the same commit.

- **AA6 — DISTRIBUTION CHANNELS QUEUED**: public repo push (agent src +
  adapters + yaml), Glama Sync → Build & Release, Smithery per-agent
  listing (hartjustin6/*, Save Settings needs TWO clicks), official
  registry when applicable (keep agent.yaml and core version in lockstep —
  registry reads agent.yaml). Manual steps may lag deploy by ≤ 1 day and
  MUST be tracked to done in the session memory + daily brief.

- **AA7 — QUICKSTART WORKED EXAMPLE**: `docs/QUICKSTART_FIRST_CALL.md`
  gains a copy-paste call for the new mount. The tool doc is the landing
  page; the quickstart is the front porch.

## Current pricing decisions (2026-07-18)

| Mount | Model | Billable | Free (rails doctrine) |
|---|---|---|---|
| verdigraph | $0.25/build, 10 free/day | build | verify, detect_format, describe |
| neurogenesis | $0.25/mutation, 10 free/day | create_agent, submit_evaluation, import_state, delete_agent | list/get/ledger/best_next_steps/export, describe |

Rationale: verification must be free for brain_ids to function as shared
trust references (the network effect IS free verification); mutations are
the taxed transactions. Launch prices are value-leader; re-price on PG20
demand data.
