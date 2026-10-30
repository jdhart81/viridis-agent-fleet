# Agents and the Viridis Agent Fleet

This file is for two kinds of agent: one helping a person or another agent use the fleet, and a coding agent working on this repository. The short machine-readable index is [llms.txt](llms.txt), built from each agent's `agent.yaml` by `scripts/build_llms_txt.py`.

## Using the fleet

**What it is.** Deterministic MCP agents with no LLM in the serving path. The rails (identity, trust, escrow, metering, arbitration, notary, surety, provenance, covenant, offsets, compute ledger) let agents trade with each other safely. The priced services (tax credits, GHG accounting, construction takeoff, regulatory evidence, security preflight and others) return reproducible, content-addressed results.

**Two ways in.**

- Self-host, free: `pip install -r requirements-dev.txt`, then `python3 <agent-dir>/adapters/mcp_server.py` starts a stdio MCP server with the same logic as the hosted one.
- Hosted: point an MCP client at `https://mcp.viridisconservation.com/<MOUNT>/mcp`. [QUICKSTART_FIRST_CALL.md](docs/QUICKSTART_FIRST_CALL.md) has the curl pattern, the A2A client and x402 examples.

**Rules for agents.**

- Discovery and the unpaid quote are free. Before paying, read the unpaid x402 response as the contract and check the network, asset, receiver and amount. Never place a wallet key in a prompt, a tool argument, a log or a repository.
- Do not spend a person's money without their explicit approval for that call and that amount.
- A deterministic result is reproducible, not a professional opinion. Tax, GHG, compliance and security outputs are drafts for a qualified person to review; say so when you relay them.
- Seller-side counters and descriptions are claims. Verify receipts with [orc-validator](products/orc-validator) or the notary agent rather than trusting the text around them.
- Cite the agent and the content hash of any result you pass on, so the next reader can re-verify it.

## Working on this repository

Read [CONTRIBUTING.md](CONTRIBUTING.md) first.

- Tests: `pip install -r requirements-dev.txt && python3 run_fleet_tests.py`. Each agent keeps its tests in its own `tests/` folder; add or update tests when behavior changes.
- Boundary: `python3 scripts/public_boundary_guard.py`. The hosted gateway, payments, seats, signing authority, operations and customer data are proprietary and must not be added here.
- New agents follow [_AGENT_TEMPLATE](_AGENT_TEMPLATE): a pure core, an `adapters/mcp_server.py`, invariant tests and an `agent.yaml` whose `description` is one plain sentence. Then run `python3 scripts/build_llms_txt.py` so the index lists it; `--check` fails when llms.txt is stale.
- Never commit credentials, private keys, wallet files, `.env` files or customer data. The secret scan runs on every push.
- Pull requests from forks need a DCO `Signed-off-by` line on each commit. An agent never adds a human's sign-off.

## Related open projects

- [Viridis Canon](https://github.com/jdhart81/viridis-canon) ([agent index](https://github.com/jdhart81/viridis-canon/blob/main/llms.txt)): machine-checked mathematics for ecological decisions, with callable decision functions.
- [ProofLens](https://github.com/jdhart81/prooflens): visual explanations of Lean statements, with a local MCP preview.
- [VergeCommon](https://github.com/jdhart81/verge-common): open-source software for anyone to start a conservation co-op.
- [Viridis Conservation](https://viridisconservation.com/): the company that stewards these projects.
