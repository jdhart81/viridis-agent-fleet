# Viridis Agent Reliability

Local candidate for ChatGPT/Codex and Claude Code. It includes an actual HTTP
SecurityPreflight MCP connection plus an evidence-bounded diagnostic skill.
Neither the plugin nor technical health certifies runtime security or purchase
readiness. No paid-service referrals are part of the diagnostic.

The adapter exposes `describe_agent`, `get_security_receipt`, `security_preflight`,
`scan_source`, and `screen_injection`. The diagnostic uses only the first two;
the other three create priced assessments and are excluded from that workflow.
The connection still advertises all five tools: skill instructions are not a
server-side tool filter. Never grant automatic approval to priced tools.

The prepared gateway patch requires an existing registered caller and that
caller's verified fixed scan order for every direct assessment. Pass the paid
`session_id` and the exact original intake; a session cannot authorize another
caller, subject, input or second execution. Calls without a fixed order fail
closed and do not spend shared credits. Historical orders with no recorded
caller require owner review. The anonymous plugin wiring supports diagnostic
reads only; checkout examples remain inactive and contain no credentials.

Public receipt reads return an **unsigned filtered summary**: an opaque receipt
ID, allowlisted verdict/counts and hashes of the original record. Subject IDs,
input digests, detailed diagnostics, tool/policy names, scanner metadata and
original signatures are excluded. Keep the original authorized delivery for
signature verification; the filtered view cannot replace it. Original signed
records remain stored, and can repeat submitted tool/policy names verbatim.
Do not submit secrets. Retention/deletion and anonymity are not promised.

No signup, credential provisioning or OAuth is implemented. These changes are
local preparation, not verified live behavior. The previously reviewed live
source admits shared-credit assessments without caller binding and returns
full public receipt records; unrestricted installation remains blocked until
this coordinated gateway/adapter patch is released and verified.

See [COMPATIBILITY.md](COMPATIBILITY.md) for local tests, client installation
acceptance criteria, official documentation and remaining approval gates.
Status: local preparation, not installed, registered, published or directory
submitted. A package parsing successfully does not prove host MCP access.
