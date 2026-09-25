# Outcome Receipt (ORC) v0.1
*Status: draft for public comment · Editor: Viridis LLC · License: CC-BY-4.0 (text), Apache-2.0 (reference code) · 2026-09-24*

## 1. Why this exists
Agent-economy standards already cover **who** an agent is (ERC-8004 Identity, A2A signed Agent Cards), **what was authorized** (AP2 mandates, Mastercard Verifiable Intent) and **how it was paid** (x402, card rails). None of them covers **what was actually delivered**. The ERC-8004 Validation Registry defines where a validator's verdict goes, but not what evidence it checks.

An ORC is that missing record. It is a small, portable JSON document proving that a specific agent produced a specific output, unaltered, optionally bound to the payment and authorization that surrounded it. It is **rail-neutral**: it binds to any rail and depends on none of them.

## 2. Receipt shape
```json
{
  "orc": "0.1",
  "profile": "generic | <issuer>.<product>/<variant>",
  "issuer":  { "id": "did:web:viridisconservation.com", "name": "Viridis LLC" },
  "subject": { "agent": "taxcredit-engine", "tool": "calculate_tax_credit", "...": "free-form" },
  "output":  { "...the agent's result object..." },
  "digest":  { "alg": "sha256", "canonicalization": "orc-canon/1",
               "excludes": ["audit_sha256", "notary_payload"], "value": "<64 hex>" },
  "commitment": { "scheme": "sha256(salt||digest)", "salt": "<64 hex>", "value": "<64 hex>" },
  "bindings": {
    "payment":    { "rail": "x402 | stripe | card", "ref": "<tx hash / charge id>", "network": "base" },
    "mandate":    { "protocol": "ap2", "ref": "<mandate hash>" },
    "validation": { "protocol": "erc-8004", "chain_id": 8453, "request_hash": "<hex>" }
  },
  "issuer_proof": { "method": "registry", "url": "https://…/orc/v0/commitments/<value>" },
  "issued_at": "RFC 3339 timestamp",
  "verify": { "page": "https://…/verify?c=<commitment.value>" }
}
```
`bindings`, `issuer_proof` and `verify` are optional. Unknown top-level fields MUST be ignored by verifiers and are not covered by the digest.

## 3. Canonicalization: `orc-canon/1`
The byte string that gets hashed is the output of Python's `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`, encoded as UTF-8:
- Object keys are sorted by code point.
- There is no insignificant whitespace.
- Every character outside U+0020–U+007E is written as a lowercase `\uXXXX` escape (a surrogate pair above U+FFFF).
- **`output` MUST NOT contain floating-point numbers.** Money and quantities are integers or decimal strings (`"720000.00"`). Under this rule, `orc-canon/1` differs from RFC 8785 (JCS) only in how non-ASCII characters are escaped. A later version may adopt JCS outright.

## 4. Sealing
1. `content` = `output` with the top-level keys in `digest.excludes` removed.
2. `digest.value` = SHA-256(`orc-canon/1`(content)), as lowercase hex.
3. `salt` = 32 random bytes, as lowercase hex.
4. `commitment.value` = SHA-256(`salt` ‖ `digest.value`), where ‖ is ASCII string concatenation.

## 5. Verification levels
| Level | Label | Requires |
|---|---|---|
| 0 | NONE | the receipt fails any L1 check or is malformed |
| 1 | **INTACT** | the digest recomputes from `output` **and** the commitment recomputes from the salt and digest |
| 2 | **ISSUED** | L1, and the issuer proves it sealed this `commitment.value` (see §6) |
| 3 | **SETTLED** | L2, and the payment binding is confirmed on its own rail |
| 4 | **VALIDATED** | L3, and an independent validator attested this `commitment.value` (for example an ERC-8004 `validationResponse`) |

Verifiers MUST report the highest level reached and MUST NOT skip a level. INTACT alone proves consistency, not authorship: anyone can seal anything. User interfaces MUST NOT label an L1 receipt "authentic".

## 6. Issuer proof (L2)
- **`registry`:** the issuer publishes `GET {url}` → `{commitment, digest, issuer, registered_at}`. It passes if the fields match and `registered_at ≤ issued_at + 5 min`. This is how the hosted notary acts as the authority of record.
- **`ed25519`:** `issuer_proof = {method, key_id, sig}`, where `sig` = Ed25519 over `commitment.value`. `key_id` resolves through the issuer's DID document (`did:web` → `/.well-known/did.json`).

## 7. ERC-8004 mapping
A validator that has checked an ORC answers the Validation Registry like this:
- `validationResponse(requestHash, response, responseURI, responseHash, tag)`
- `response` = 100 if the validator reproduced the result (a deterministic replay for deterministic profiles), otherwise 0.
- `responseURI` = where the ORC is published; `responseHash` = `0x` + `commitment.value`.
- `tag` = `"orc/0.1"`.
The receipt then carries `bindings.validation` pointing back to the request. Reputation feedback SHOULD be weighted only when it cites an ORC at SETTLED level or above. That grounds reputation in paid, delivered work instead of unverifiable reviews.

## 8. Profiles
- **`generic`:** any JSON output, with no excludes.
- **`viridis.cliff-check/48E`** (and `/45Y`): the output is a `taxcredit-engine` result, `excludes = ["audit_sha256","notary_payload"]`, and `digest.value` equals the engine's own `audit_sha256`, so the engine's built-in verifier and ORC agree.

## 9. Conformance
- Reference implementation: `fleet_utils/orc.py` (Python, stdlib only). The browser verifier core is in `products/signed-cliff-check/verify.html`.
- Test vectors: `docs/standards/orc/vectors.json` (6 cases, including non-ASCII, a tampered output, a wrong salt, an excluded-field change and the Cliff Check profile). **As of 2026-09-24 the Python and JavaScript implementations agree on all 6.**
- A conforming verifier reproduces every `expect_level` in the vectors.

## 10. Open questions for v0.2
Adopting JCS (RFC 8785); post-quantum signatures (compare IETF draft-marques-asqav, ML-DSA-65); selective disclosure of `output` (salted per-field digests); batching (a Merkle root per issuer per hour); and an AP2 mandate binding format aligned with the FIDO Agentic Payments working group.
