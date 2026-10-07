# Viridis Agent Reliability

Inspect an agent service's declared scope, MCP compatibility and evidence limits.
The diagnostic skill uses `describe_agent` and `get_security_receipt` only.
A public receipt summary is unsigned; preserve the original authorized signed
record for verification. This package does not certify runtime security.

The existing MCP endpoint also advertises `security_preflight`, `scan_source`
and `screen_injection`. Those assessments require an existing exact entitlement.
Do not invoke them from this diagnostic skill. Hosted authenticated assessments
await OAuth activation and platform review; installation creates no account,
paid order or access grant. The OAuth-only hosted path will use the platform's
consent flow rather than collecting credentials through this skill.

The package does not read environment variables or credential files, accept
secrets through skill inputs, or define sensitive user_config fields. Do not
paste tokens, cookies, keys or private payment identifiers into a conversation.
No checkout, referral, subscription or payment-administration tools are bundled.

## Data handling

When used, the platform receives the user's conversation and supplied diagnostic
material under its own policies. The existing Viridis MCP receives only tool
arguments sent to it. Static assessment inputs may contain identifiers and are
stored with their signed receipt and order state. Public receipt views omit
subject IDs, detailed findings and original signatures, retaining an opaque ID,
verdict/counts and record hashes. Do not submit secrets or sensitive records.

The existing [soft-launch privacy notice](https://viridisconservation.com/privacy)
identifies Viridis North LLC as operator and justin@viridisconservation.com as
privacy contact. Its service retention depends on purpose and engagement terms;
this package establishes no new retention period, deletion deadline, refund
policy or anonymity promise. Hosted OAuth token persistence and platform-specific
assessment disclosures need review before authenticated release. The notice's
existing payment activation language is not a claim about this plugin's readiness.
See [PRIVACY.md](PRIVACY.md) for current technical boundaries.

The icon is a PNG rendering of the existing public Viridis site icon, without
changing its design. Publisher verification in the OpenAI draft is Individual —
JUSTIN DANIEL HART; this does not assert business verification of the operator.
Version 0.1.3 is prepared for draft validation, not directory approval.

Licensed under [Apache-2.0](LICENSE).
