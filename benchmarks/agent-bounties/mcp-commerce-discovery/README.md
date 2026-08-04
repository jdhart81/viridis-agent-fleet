# MCP commerce discovery checker benchmark

This benchmark defines the acceptance contract for an independently solved
Agent Bounties child task.  The benchmark is committed without the requested
implementation so the solver performs real work.

## Goal

Add a dependency-free Node.js CLI at
`scripts/check-mcp-commerce-discovery.mjs` that verifies the three public
discovery documents used by an MCP service with x402/A2A commerce:

- `x402-catalog.json`
- `agent-card.json`
- `skills-index.json`

The CLI must use only Node.js built-ins and must not access the network.

## Invocation

```text
node scripts/check-mcp-commerce-discovery.mjs <bundle-directory>
```

With no argument or more than one argument, exit `64`, write exactly this line
to stderr, and write nothing to stdout:

```text
usage: node scripts/check-mcp-commerce-discovery.mjs <bundle-directory>
```

## Required validation

Validation is fail-closed and ordered:

1. Read and parse the three named files.  Each file must be a regular file no
   larger than 1 MiB.  A missing, unreadable, non-regular, or oversized file is
   `bundle_read_error`; malformed JSON is `invalid_json`.
2. Validate `x402-catalog.json`: `spec_version` is
   `viridis-x402-catalog-v1`; `routes` contains exactly eight entries; route
   `(agent, tool)` pairs are unique; every endpoint is HTTPS and ends in
   `/x402/<agent>/<tool>`; every MCP endpoint is HTTPS and ends in
   `/<agent>/mcp`; `methods` includes `POST`; `paid_execution_method` is
   `POST`; `amount_atomic_usdc` is a positive base-10 integer string;
   `x402_version` is `2`; and `v2_enabled` is `true`.
3. Validate `agent-card.json`: it contains exactly eight unique skills; the
   required x402 extension URI is
   `https://github.com/google-a2a/a2a-x402/v0.1`; each skill id is
   `<agent>.<tool>`; and each skill's `metadata.httpX402Endpoint` and
   `metadata.amountAtomicUsdc` exactly match the corresponding catalog route.
4. Validate `skills-index.json`: it contains exactly one skill named
   `viridis-paid-tools`, and its `files` array contains `SKILL.md`.

The first failure wins.  Contract failures use, in order,
`catalog_contract`, `card_contract`, `surface_mismatch`, then
`skill_index_contract`.

## Output contract

On success, exit `0`, write nothing to stderr, and write exactly one compact
JSON line to stdout:

```json
{"a2a_skills":8,"buyer_skills":1,"routes":8,"status":"ok"}
```

On a data or contract failure, write nothing to stdout and write exactly one
compact JSON line to stderr with keys in this order:

```json
{"status":"error","code":"<code>","file":"<file>","message":"<message>"}
```

Messages are fixed by the benchmark fixtures.  Do not include paths outside
the supplied bundle directory, stack traces, timestamps, environment values,
or input contents.

## Run the benchmark

From the repository root:

```text
node benchmarks/agent-bounties/mcp-commerce-discovery/test.mjs .
```

The benchmark uses temporary local fixtures, performs no network access, and
prints `benchmark ok` only after every success and failure case passes.
