# Viridis Agent Reliability

Inspect an agent service's scope, MCP compatibility and security evidence. This
package connects to the hosted SecurityPreflight MCP server and includes the
`agent-reliability-check` diagnostic skill. It does not certify runtime security.

## Installation

For Claude Code, add the public repository marketplace and install locally in
an intended project:

```sh
claude plugin marketplace add jdhart81/viridis-agent-fleet
claude plugin install viridis-agent-reliability@viridis-agent-fleet --scope local
```

For a temporary Claude Code session, load the checked-out plugin directory:

```sh
claude --plugin-dir ./plugins/viridis-agent-reliability
```

Codex supports the repository's `.agents/plugins/marketplace.json` and the
plugin's `.codex-plugin/plugin.json` compatibility manifest. Choose an explicit
project scope. ChatGPT and Claude hosted account installation are separate from
local CLI installation; neither platform directory lists this package yet.

## What is available

The HTTP server advertises five tools. `describe_agent` explains its scope;
`get_security_receipt` reads an unsigned filtered public summary. The diagnostic
skill uses only these two tools. Three assessment tools also exist:
`security_preflight`, `scan_source`, and `screen_injection`. They require an
existing registered caller and a verified fixed-order session belonging to that
caller. Installation does not create an account or an entitlement.

A diagnostic is not an assessment. To run an assessment, retain the original
intake and use its existing paid session under the same authorized caller.
Another caller, subject, input or second execution cannot consume that order.
Credential setup needs an explicitly approved scope; never paste secrets into a
conversation or plugin package. No OAuth or self-service signup is implemented.

Use exact host tool controls to restrict a diagnostic session to the two read
operations. Skill instructions and MCP annotations are not authorization or
server-side tool filtering. Do not automatically approve assessment tools.

## Privacy and evidence

Public receipt views contain an opaque ID, allowlisted verdict/counts and hashes
of the original record. They omit subject IDs, input digests, detailed findings,
tool/policy names, scanner metadata and original signatures. Keep the original
authorized delivery for signature verification; the public summary is unsigned.
Original signed records remain stored and may repeat submitted names. Never
submit secrets. Anonymity and a deletion period are not promised. A published
service privacy policy covering retention and user controls is still required
before directory submission; this technical description is not that policy.

## Verified release status

The caller-bound fixed-order boundary and filtered receipt contract were
published and deployed on 2026-10-06. The earlier shared-credit/raw-public-receipt
behavior is closed. Native version 0.1.1 installation/discovery passed in bundled
Codex 0.160.0 and Claude Code 2.1.241. Codex invoked live `describe_agent` and a
local synthetic receipt read; Claude discovered the skill and all five tools
through its zero-model native control interface. No real paid assessment or
hosted ChatGPT/Claude account workflow was tested.

Version 0.1.2 adds distribution packaging, documentation and adapter display
titles. Live runtime titles remain absent until the coordinated service pin and
image release. Model-driven Claude Code use is blocked by its current logged-out
state. Hosted authenticated use and directory review are not complete.

See [COMPATIBILITY.md](COMPATIBILITY.md) for each platform's evidence and gates,
and [REVIEW.md](REVIEW.md) for proposed reviewer cases. Licensed under
[Apache-2.0](LICENSE).
