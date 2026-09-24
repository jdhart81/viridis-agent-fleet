# Verify a Security Preflight result before relying on it

Viridis Security gives agents deterministic checks of supplied MCP manifests,
schemas, tool policies and sample text, with signed, redacted evidence. This
integration adds offline verification of that evidence. It does not certify
an agent, execute a tool, or prove that a remote server matches its manifest.

## Operator setup

Install Python 3.10+ and `cryptography>=46.0.5,<47` in your application environment.
Use `scripts/viridis_security_verify.py` alongside the existing
[buyer quickstart](SECURITY_PREFLIGHT_BUYER_QUICKSTART.md).

Provision `trust.json` through your operator's authenticated configuration
process, containing:

```json
{
  "public_key_b64": "OPERATOR_APPROVED_ED25519_PUBLIC_KEY",
  "scanner": {
    "name": "Viridis Security Preflight",
    "version": "OPERATOR_APPROVED_VERSION",
    "canon_digest": "OPERATOR_APPROVED_RULES_SHA256"
  }
}
```

These placeholders intentionally fail verification. Obtain the issuer key from
the service description through an authenticated HTTPS/operator channel and
confirm its SHA-256 fingerprint against the operator's recorded value. Approve
the scanner version and rules digest against the release record before adding
them to configuration. Never copy a key or scanner policy out of the untrusted
result merely to make verification pass. A first-time trust decision belongs
to the operator; this verifier cannot establish it automatically. Rotate pins
through that same process. Do not put wallet keys in this file.

## Agent workflow

1. Capture the exact manifest, tool policy and sample inputs as `inputs.json`.
   Do not submit credentials, private keys, customer secrets or unnecessary text.
2. Use the buyer helper in quote mode. The operator must fund and authorize a
   purchase budget; the agent verifies the exact quote and makes at most one
   paid attempt within that ceiling. Existing pricing applies; the quote is
   authoritative. Save the complete paid response as `paid-result.json`.
3. Independently verify the retained result:

```sh
python scripts/viridis_security_verify.py \
  --result paid-result.json --inputs inputs.json --trust trust.json
```

| Exit | Meaning | Application response |
| --- | --- | --- |
| 0 | Authentic, current, approved manifest preflight with no reported issues | Continue the application's remaining checks |
| 2 | Authentic assessment requires review | Pause the affected integration for operator review |
| 1 | Missing, altered, stale, wrong-input or untrusted evidence | Stop; inspect the retained result; do not automatically repurchase |

All subprocess errors, missing dependencies and unexpected exits must also stop
the integration. Python callers can import `verify(result, inputs, trust)`;
only `decision == "PREFLIGHT_PASS"` satisfies this preflight condition.

The application must separately enforce authentication, least privilege,
tool allowlists, human approvals, spending limits and runtime isolation. A
preflight pass is one condition, never permission to execute arbitrary tools.
Do not trust unsigned wrapper fields such as the top-level `verdict`.

4. Retain evidence with the exact input version. Run the existing free change
   check before paying again; an unchanged result must still pass local expiry,
   input and scanner-policy verification. Changed inputs, expired evidence or
   changed rules require review and, when appropriate, a fresh quote and budget.

## Verification coverage and limits

The verifier checks the Ed25519 signature using the operator-pinned public key,
the evidence hash, receipt identity, issuer, scanner pin, timestamps and exact
agent/manifest/policy/sample/profile binding. It derives the assessment from
signed evidence and returns `tool_execution_authorized: false`.

Only manifest preflight receipts are accepted. Source-scan and text-screening
receipts are deliberately rejected by this integration; they have different
contracts. Signature verification establishes origin and integrity, not scanner
accuracy, payment settlement, buyer acceptance, runtime safety or absence of
vulnerabilities. The signer can still produce an incorrect assessment.

The existing purchase helper validates delivery hashes; this separate verifier
must run before an application relies on the assessment. Payment reconciliation
remains a separate responsibility. There are no network calls, payments, tool
executions or automatic retries in the verifier itself.
