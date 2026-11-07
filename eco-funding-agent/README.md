# viridis-eco-funding

**The ecological funding layer of the Viridis open-source stack.** Open tools that let people and AI agents put a value on a site's ecological complexity, check that value, and model how a pledge pool for it would behave. All of it is reproducible.

> **NOTICE.** Any real funding pool needs legal review before money moves. This software holds, moves and releases no funds. It computes ecological measures and simulates pool rules. Viridis builds and licenses software only. Viridis never runs a co-op, holds funds or sells financial products.

**Status:** v0.1.0. Private working repository with the Apache-2.0 license. Not peer reviewed. The D-Score is under journal review. The intelligence bound is a **conjecture**, and every output that uses it says so.

## What it does

| Piece | What you get |
| --- | --- |
| **Valuation core** (`value_site`) | A pure, deterministic complexity score **K = D\* x ECA** in complexity-hectares. It multiplies data richness (the published D-Score, optionally blended with a GSIP soil index) by the equivalent connected area of *verified* habitat, with links taken from HDFM. Every number states its value, units, formula, inputs, uncertainty (sigma, 95% interval, basis) and status. |
| **Complexity-capacity term** | An optional thermodynamic ceiling, B = P D\* / (k_B T ln 2), where P is the site's photosynthetic power. C is the connectivity-limited capacity, and C never exceeds B. There is also a *compute-parity* restatement: the watts at which a computer at the Landauer limit would have the same ceiling. **All of this is a conjecture.** |
| **Verification hook** (`make_receipt`, `verify_receipt`) | Sealed receipts that hold the normalized inputs, a SHA-256 digest of those inputs, the method version and the result. Anyone can re-run a receipt offline and get byte-identical output. A receipt can optionally bind a VergeCommon public project, read with a public GET only. |
| **Pool design** (`simulate_pool`) | A schema and simulator for pledges, milestone releases and outcome-linked releases. Accounting uses integer minor units: releases plus remaining balance always equal pledges, and nothing is released without a met rule. It is a model only. There is no payment code. |
| **MCP server** (`vef-mcp`) | Five read-only tools: `value_site`, `explain_valuation`, `verify_receipt`, `simulate_pool`, `describe_method`. Runs over stdio or Streamable HTTP. Agents can start from [`llms.txt`](llms.txt) and [`AGENTS.md`](AGENTS.md). |
| **Viridis fleet mount** (`adapters/mcp_server.py`) | The same five tools, packaged for the Viridis agent gateway at `/eco-funding/mcp`, as a declared **free rail**. Success envelopes teach `next_steps` edges to the notary, regulatory-radar and ghg-ledger mounts. It passes the fleet's admission invariants AA1–AA7 (`tests/test_fleet_admission.py`). See [`deploy/fleet/MOUNT.md`](deploy/fleet/MOUNT.md). |

## Quick start

```bash
pip install -e ".[mcp,dev]"          # the core itself uses only the Python standard library
vef value examples/data/woodland_site.json
vef receipt examples/data/woodland_site.json > receipt.json && vef verify receipt.json
vef simulate examples/data/woodland_pool.json
vef-mcp                                # MCP over stdio
vef-mcp --transport streamable-http --port 8765   # MCP at http://127.0.0.1:8765/mcp
pytest                                 # full suite, including all seven invariants
```

```python
from viridis_eco_funding import value_site, make_receipt, verify_receipt
receipt = make_receipt(site)            # site follows schema vef-site/0.1
assert verify_receipt(receipt)["valid"]
print(receipt["result"]["explanation"])
```

The worked example is [`examples/woodland_valuation.ipynb`](examples/woodland_valuation.ipynb). It values one VergeCommon woodland project. The project record is *synthetic*, because VergeCommon's public directory listed no co-ops when v0.1 was built.

## Invariants (each one is a test)

| # | Invariant | Test |
| --- | --- | --- |
| 1 | Determinism: same inputs and method version give byte-identical results and receipts | `tests/test_invariant_1_determinism.py` |
| 2 | Monotonicity: adding verified habitat or connectivity never lowers the complexity score | `tests/test_invariant_2_monotonicity.py` |
| 3 | Bound respected: complexity capacity never exceeds the stated bound | `tests/test_invariant_3_bound.py` |
| 4 | Conservation: releases + remaining = pledges; no release without a met milestone | `tests/test_invariant_4_pool_conservation.py` |
| 5 | No money movement: no payment SDKs, private keys, wallet code or token minting | `tests/test_invariant_5_no_money.py` |
| 6 | Read-only externally: public GET reads only; nothing written anywhere | `tests/test_invariant_6_read_only.py` |
| 7 | Honest labels: outputs that use the intelligence bound say "conjecture" | `tests/test_invariant_7_labels.py` |

[`docs/INVARIANTS.md`](docs/INVARIANTS.md) explains how each invariant is enforced in code as well as tested.

## Documents

- [`METHOD.md`](METHOD.md): the math, constants, uncertainty propagation and citations.
- [`LIMITS.md`](LIMITS.md): what the numbers do and do not mean. Read it before using a number to make a decision.
- [`AGENTS.md`](AGENTS.md): for coding agents and for agents that call the tools.
- [`CHANGELOG.md`](CHANGELOG.md)

## Where it fits

It reads [VergeCommon](https://vergecommon.com) public project records, and it was derived from EcoChain's work on verification and pricing. It uses [HDFM / Dendritic Forest Management](https://github.com/jdhart81/hdfm-framework) corridor links and its movement kernel, and [GSIP](https://github.com/global-soil-intelligence/gsip) soil units. Its scientific basis is the D-Score and the intelligence-bound papers by J. D. Hart (see METHOD.md). Wording used throughout: *pledge*, *pool*, *outcome-linked release*.

## License

Apache License 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Copyright 2026 Viridis LLC.
