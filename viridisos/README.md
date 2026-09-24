# ViridisOS

The platform that turns Viridis's Lean-verified theorems into certified conservation products.
This is the working service: module runtime (L2) + certification layer (L3) + the Mutualist
reference module + an HTTP API. Pure Python stdlib — no installs. Architecture:
`VIRIDISOS_SYSTEMS_ARCHITECTURE.md`; business framing: `VIRIDISOS_BUSINESS_BRIEF.md`.

## Run

```bash
bash run_all_tests.sh        # 33 tests across runtime / certification / modules / platform / api
python3 viridis_platform.py  # print the module catalog resolved against the live canon
python3 demo.py              # end-to-end: catalog → certify (live FNT) → verify; blocked module refused
python3 -m api.app           # serve the HTTP API on :8085
```

## Modules (see PLATFORM_CATALOG.md)

Four modules, each backed by a canon theorem. Resolved against the live canon — LIVE only if the
backing theorem is published (A-1): **restoration** (FNT) · **afforestation** (AST) · **harmonization**
(GHT) are LIVE; **mutualist** (SRPT) is BLOCKED until SRPT publishes.

## What's here

```
runtime/         L2 — module contract (module.py), registry, provenance, canon resolver
certification/   L3 — claim, attestation (dev signer), certifier (issue+verify), registry, standard
modules/mutualist/  reference module wrapping the SRPT (Run-093) kernel
api/             L4 seam — service + pure dispatch + stdlib HTTP wrapper
tests/           24 tests; every invariant has a failing-if-violated test
demo.py          full-flow demonstration
```

## The invariants it enforces

- **A-1 Backing-or-nothing** — no certificate without a resolvable, gate-passed canon DOI.
- **A-2 Recompute-verifiable** — every certificate is independently, bit-identically recomputable.
- **A-3 Blocked propagation** — unverified / integrity-flagged backing ⇒ module BLOCKED, cannot certify.
- **A-4 Provenance everywhere** — every output carries backing DOI + input hashes + timestamp.
- **A-5 Never publish to canon** — ViridisOS only consumes canon DOIs.

## Add a new module (the whole point — under an hour)

1. Create `modules/<name>/engine.py` — port the research run's `verify.py` numeric core as pure functions.
2. Create `modules/<name>/module.py` — subclass `runtime.module.Module`, set `id/name/line/version`,
   declare `backing = Backing(doi=..., lean_module=..., aristotle_id=..., verified=True)`, implement
   `compute(inputs)`.
3. Register it (`registry.register(...)`) and add a `tests/test_<name>.py` (kernel checks +
   full certify→verify path).

That's it — the runtime handles provenance, the certifier handles the moat, the API exposes it.
Next modules by product-tree priority: **Tempo** (Run-060), **Restoration/Nucleation** (Run-061).

## API

| Method | Route | Body | Returns |
|---|---|---|---|
| GET | `/modules` | — | registered modules + state |
| POST | `/modules/{id}/preview` | `{inputs}` | module output (no certificate) |
| POST | `/modules/{id}/certify` | `{subject, inputs}` | issued certificate (409 if BLOCKED) |
| POST | `/certificates/verify` | `{certificate_id, module_id, inputs}` | `{valid}` |
| GET | `/standard` | — | Certification Standard v1 |
