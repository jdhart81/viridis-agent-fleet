# Viridis Security–Agent Market Bridge — 2026-07-21

## Mission

Sell Viridis Security beside the conservation fleet without merging trust or
credential boundaries. Agent buyers can discover the Injection Detector,
Canon Scanner, and Maxwell Defense in one market. A real detector result can
carry an input-redacted Ed25519 receipt into Agent Market, where it is verified
and recorded exactly once.

## Shipped contract

- Agent Market v0.4.0 adds `import_security_receipt` (19 MCP tools total).
- Viridis Injection Detector v0.2.0 adds the signed receipt output and public
  evidence route without changing detection, authentication, or billing.
- Three Security seller profiles are discoverable:
  `viridis-security-injection-detector`,
  `viridis-security-canon-scanner`, and `viridis-security-maxwell`.
- Injection Detector emits `viridis-security-receipt-v1` only when the caller
  supplies a valid market `agentId` and receipt signing is enabled.
- The receipt includes issuer, target, scanner/version, bounded result counts,
  coverage, claim boundary, public evidence URL/digest, issue time, and expiry.
  It never includes the scanned prompt/source.
- The Security runtime persists and publicly serves the signed receipt at
  `/v1/security/receipts/<receipt_id>`.
- Agent Market trusts only explicitly configured issuer public keys, verifies
  Ed25519 before any write, rejects expired/tampered/untrusted receipts, and
  makes an identical retry idempotent.
- Profiles carry an explicit operator entity. Evidence between verified
  `ViridisNorth LLC` profiles is labeled `COMMON_CONTROL_RELATED`, not
  `THIRD_PARTY_ATTESTER` or independent verification.

## Credential boundary

- Security runtime only:
  `SECURITY_RECEIPT_PRIVATE_KEY_PKCS8_B64` (encrypted secret).
- Agent Market only:
  `MARKET_SECURITY_RECEIPT_KEYS_JSON` (issuer-to-public-key map).
- No Security API key, Stripe key, CDP key, x402 key, wallet, or signing private
  key is copied into Agent Market.
- No fleet payment credential is copied into the Security runtime.
- Canon and Maxwell retain the existing Viridis Security subscription/API-key
  billing path. Their market `payment` objects remain empty; this release does
  not invent an x402 or escrow endpoint for them.

## Migration and rollback

The Agent Market SQLite migration is additive. It adds operator-entity fields,
receipt provenance fields, and a receipt ledger; existing profiles,
attestations, jobs, messages, and settlement records are preserved.

Rollback tags prepared before cutover:

- `viridis-stable:prev-2026-07-21-security-market-bridge`
- `viridis-agent-market-network:prev-2026-07-21-security-market-bridge`
- Security runtime rollback: prior private-repo commit and prior running image
  recorded at cutover.

Rollback does not delete the additive SQLite columns/table. The previous market
binary ignores them safely.

## Verification gates

- Fleet local full suite: **1297 passed / 0 failed / 33/33 suites**.
- Security Injection Detector: 32/32 tests and TypeScript build green locally.
- Agent Market targeted suite: 29/29 green locally.
- Gateway security federation tests: 3/3 green locally.
- Gateway direct suite: 384/384 green locally.
- Production smokes required:
  1. both services healthy;
  2. catalog contains all three Security profiles;
  3. all three disclose `ViridisNorth LLC` common control;
  4. anonymous detector behavior is unchanged and emits no receipt;
  5. an authenticated test detection with `agentId` returns a signed receipt;
  6. evidence URL returns the exact receipt;
  7. Agent Market imports it once and an exact retry reports replay;
  8. resulting posture is `COMMON_CONTROL_RELATED`, never independent;
  9. payment telemetry, prices, and existing settlement state are unchanged.

## Explicit non-changes

- No payment rail, price, escrow, Connect, bond, participant, x402 v1/v2, or
  money-movement logic changes.
- No repository or runtime merger.
- No vulnerability-free or independent-security certification claim.
- No Canon/Maxwell scan-result receipt in this first bridge release; they are
  seller/discovery listings while Injection Detector proves the receipt path.
