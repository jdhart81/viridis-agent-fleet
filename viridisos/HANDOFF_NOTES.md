# ViridisOS — Handoff Notes (real vs. stubbed, and production swaps)

The L2 runtime, L3 certification, the Mutualist module, and the API are **real and tested**
(24 tests green). Three things are deliberately stubbed behind stable interfaces so the whole
certify→verify flow works today; each swaps to production without touching the certifier or modules.

## 1. Attestation signer — DEV HMAC → production K3 signer

- **Now:** `certification/attestation.py::HmacSigner` — deterministic HMAC-SHA256. Proves the
  sign/verify flow; NOT a real cryptographic attestation.
- **Production:** implement the `Signer` Protocol (`sign(bytes)->str`, `verify(bytes,str)->bool`,
  `key_id`) against the L1 VERIFY plane's **K3 signer** (`03_APPLICATIONS/platform/BUILD_VERIFY.md`,
  the VW3 signed-attestation path). Pass it to `Certifier(signer=...)`. No other change.

## 2. Canon DOI resolver — index fixture → live canon + ledger

- **Now:** `runtime/canon_resolver.py::CanonResolver` reads `RESEARCH_PIPELINE_v2/canon_fingerprint_index.json`
  when present, else an injected `entries` fixture. A record in the published index is treated as
  gate-passed.
- **Production:** point it at the live canon (`viridis-canon` git) + `ZENODO_SUBMISSION_LEDGER.md`
  so a DOI resolves to true canon status and **weakened/retracted theorems flip to unverified**
  (auto-BLOCKING their modules — A-3). Same `resolve()` / `is_gate_passed()` interface.

## 3. Certificate registry — JSON store → DATA plane

- **Now:** `certification/registry.py::CertificateRegistry` — in-memory + optional JSON file.
- **Production:** back it with the DATA plane (Supabase Postgres, ref `eldfngwmgyebevoxqxwm`) for
  durable issuance + revocation. Same `record()` / `is_revoked()` / `revoke()` interface.

## Known open items / decisions for Justin

- **SRPT backing DOI is a placeholder** (`10.5281/zenodo.SRPT-PENDING`) — the Mutualist module is
  BLOCKED until SRPT (Run-093) is published to the canon and the real DOI is wired. This is correct
  A-1 behavior: it will not certify against an unpublished theorem. Wire the DOI at SRPT publish.
- **API transport:** stdlib `http.server` (zero-dep). Swap to FastAPI/uvicorn if you want OpenAPI docs
  + async — `api/service.py::dispatch` is the reusable core; only `api/app.py` changes.
- **Next modules:** Tempo (Run-060) and Restoration/Nucleation (Run-061), same contract.

## What must never change (the moat)

The three-part certificate check in `certification/certifier.py::verify` — (a) backing resolves to a
gate-passed canon entry, (b) deterministic recompute reproduces the values + signature verifies,
(c) input hashes match — is the product. Keep it; only swap the signer/resolver/registry behind it.
