# QuantaOptima fleet integration boundary

QuantaOptima is an external alpha dependency maintained in the
[`jdhart81/quantaoptima`](https://github.com/jdhart81/quantaoptima) repository.
It is not a hosted fleet agent, not a paid fleet route, and not evidence of
customer delivery or revenue.

Current state:

- latest published release: `v0.4.0`
- reviewed hardening candidate: `v0.4.1` at source commit `7abfc6a` (unreleased)
- public paid sales: disabled
- production Stripe fulfillment: not verified
- fleet deployment: none

Permitted interpretation: QuantaOptima authenticates explicitly recorded action
data and detects modification without the HMAC key. It does not prove execution,
actor identity, completeness, automatic capture, regulatory compliance, or
optimality. A key holder can rewrite history; completeness requires an external
checkpoint.

Integration rules:

1. Use only `quantaoptima-server` or `python -m quantaoptima.server`.
2. Never use the retired `mcp_server.server` expression interface or
   `SETUP_MCP.sh`.
3. Keep MCP exports inside the configured `QUANTAOPTIMA_EXPORT_DIR`; the tool
   accepts filenames only and must not overwrite existing files.
4. Treat optimizer step verification as current-process HMAC integrity unless a
   separate trusted checkpoint/signature is established.
5. Do not reuse historical benchmark or scaling claims. Only results from the
   corrected hard-budget runner may be evaluated, and new results still require
   independent methodology review before publication.
6. Do not surface checkout, price, subscription, revenue, or fulfillment claims
   until the QuantaOptima repository records signed test-mode purchase, renewal,
   delivery, public-key distribution, activation, durable backup, and recovery.
7. Updating this record does not authorize fleet deployment, registry
   publication, production promotion, billing changes, or customer messages.

The machine-readable companion is `policy.json`. Validate locally with:

```bash
python3 -m pytest -q integrations/quantaoptima/test_policy.py
```
