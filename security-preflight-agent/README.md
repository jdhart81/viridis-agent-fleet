# Viridis Security Preflight

A growth-first, paid Fleet service that turns caller-supplied MCP manifests,
tool schemas, tool policies, and sample inputs into deterministic checks plus a
signed, input-redacted `viridis-security-receipt-v1`.

List price is $1 per scan. The fleet's existing one-time x402 introduction can
quote $0.01 to a new payer wallet. A result can be imported into an existing
Viridis Agent Market profile only through a separate explicit Market action;
payment does not imply profile ownership or import consent.

The service never fetches URLs, executes tools, stores raw caller input, or
claims to test the deployed runtime. ViridisNorth LLC operates both this issuer
and the seeded Viridis fleet profiles, so Market imports must remain labeled
`common_control`, not independent proof.

Required production secret:

- `SECURITY_PREFLIGHT_SIGNING_KEY_PKCS8_B64`: base64-encoded Ed25519 PKCS8 DER.

The Agent Market receives only the corresponding raw public key through its
separate `MARKET_SECURITY_RECEIPT_KEYS_JSON` trust map.
