# ViridisOS — Build Handoff Prompt (for Fable)

You are building **ViridisOS**, the platform that turns Viridis's Lean-verified theorems into
certified conservation software products. This prompt is self-contained. Read the three governing docs
first, then build in the order below. Work production-ready: typed, tested, and enforcing the invariants.

## 0. Read first (do not skip)

1. `ViridisOS/VIRIDISOS_SYSTEMS_ARCHITECTURE.md` — the five-layer architecture you are implementing.
2. `ViridisOS/VIRIDISOS_BUSINESS_BRIEF.md` — what it's for and the first three modules.
3. `RESEARCH_PIPELINE_v2/RESEARCH_ARM.md` + `RESEARCH_PIPELINE_v2/product_tree.py` — where module
   concepts and their backing theorems come from.

## 1. Mission (one sentence)

Build **L2 (module runtime)** and **L3 (certification layer)** on top of the existing L0 canon and L1
planes, plus a reference module (Mutualist) and an API surface — so that a conservation claim can flow
`measure → module.compute → verify(sign) → certify → settle` and emit a certificate that anyone can
independently recompute and check against a canon DOI.

## 2. What exists (consume, do not rebuild)

- **L0 canon:** `viridis-canon` git repo (Lean theorems, DOIs) + `RESEARCH_PIPELINE_v2/` (gate, tree,
  `canon_fingerprint_index.json`). Treat DOIs as the root of trust.
- **L1 planes:** `03_APPLICATIONS/platform/` (`BUILD_MEASURE.md`, `BUILD_VERIFY.md`, `BUILD_FINANCE.md`,
  `BUILD_DATA.md`, `BUILD_CHASSIS.md`) and `07_DAO_AGENT/` (settlement ledger, `verify.py`).
- **Module kernels:** each research run's `verify.py`/engine under the science-engine `compound research
  papers/Run-NNN/`. The Mutualist kernel = Run-093's engine (SRPT).
- **Surfaces:** `viridis-conservation-app/` (Next.js + Supabase; see its `SYSTEM_ARCHITECTURE.md`).

## 3. Invariants — restate as tests, enforce in code (non-negotiable)

- **A-1 Backing-or-nothing.** No certified output without a resolvable, gate-passed canon DOI +
  Lean-module reference. A module missing backing may run in preview but MUST NOT certify.
- **A-2 Recompute-verifiable.** Every certificate is deterministically, bit-identically recomputable
  from `{module_id, inputs, backing}`; a `verify(certificate)` call re-runs and must match.
- **A-3 Blocked propagation.** If a module's backing theorem is unverified or integrity-flagged, its
  state is BLOCKED and `certify()` raises; only `preview()` is allowed.
- **A-4 Provenance everywhere.** Every output object carries `{backing_doi, lean_module, input_hashes,
  timestamp, module_version}`.
- **A-5 Never publish to canon.** ViridisOS consumes canon DOIs; it never writes/publishes to the canon
  or Zenodo. Publication stays human-gated in the research pipeline.

Each invariant gets at least one test that fails if the invariant is violated.

## 4. Build order (phased; each phase ships with tests green)

### Phase 1 — Module runtime (L2)
Create `ViridisOS/runtime/` (Python 3.11+, stdlib + pydantic; no heavy deps).
- `module.py` — an abstract base class `Module` implementing the contract:
  ```
  class Backing(BaseModel): doi: str; lean_module: str; aristotle_id: str; verified: bool; integrity_flag: bool
  class Provenance(BaseModel): backing_doi: str; lean_module: str; input_hashes: dict[str,str]; timestamp: str; module_version: str
  class ModuleOutput(BaseModel): values: dict; units: dict; provenance: Provenance
  class Module(ABC):
      id: str; name: str; line: str; version: str; backing: Backing
      @abstractmethod
      def compute(self, inputs: dict) -> dict          # the kernel (wraps a run engine)
      def preview(self, inputs: dict) -> ModuleOutput   # always allowed
      def certify_ready(self) -> bool                   # A-1/A-3: backing.verified and not integrity_flag
  ```
- `registry.py` — register/discover modules by id + line; reject duplicate ids; expose `list_modules()`.
- `provenance.py` — deterministic input hashing (sorted-key canonical JSON → sha256) + provenance stamping.
- Tests `test_runtime.py`: registration, preview always works, `certify_ready()` false when unverified or
  integrity-flagged, provenance determinism (same inputs → same hashes).

### Phase 2 — Certification layer (L3)
Create `ViridisOS/certification/`.
- `claim.py` — `Claim {subject, module_id, output, backing, input_hashes, timestamp}`.
- `attestation.py` — sign a claim (wrap L1 VERIFY's K3 signer; if unavailable in-repo, stub the signer
  behind an interface `Signer.sign(bytes)->sig` / `verify(bytes,sig)->bool` with a deterministic HMAC dev
  implementation, clearly marked, so the flow is testable now and swaps to the real K3 signer later).
- `certifier.py` — `issue(claim) -> Certificate` enforcing A-1 (backing DOI resolves + gate-passed) and
  A-2 (store enough to recompute); `verify(certificate) -> bool` performing the **three-part check**:
  (a) backing DOI resolves to a gate-passed canon entry, (b) signed recompute matches, (c) input hashes
  verify.
- `registry.py` — record issued certificates (JSON store now, DATA plane later) with revoke-on-weakened-backing.
- `standard.py` — machine-readable spec of "ViridisOS Certification Standard v1" (id, version, required
  fields, backing families) so registries can require it.
- Tests `test_certification.py`: issue+verify round-trips; A-1 blocks issuance without backing; A-2 a
  tampered output fails verify; A-3 a BLOCKED module cannot issue; revocation works.

### Phase 3 — Mutualist reference module
Create `ViridisOS/modules/mutualist/`.
- Wrap Run-093's SRPT engine as `compute()` (import or port the numeric core: risk-premium floor
  π ≥ ρ·k_B/Σ, Diversification-Wall residual, contagion sign). Declare backing = SRPT DOI + Lean module +
  Aristotle id, `verified=True`.
- Inputs from MEASURE (energy-throughput proxies) + DATA (portfolio); outputs {premium_floor,
  diversification_residual, contagion_sign} with units + provenance.
- Tests `test_mutualist.py`: known-input → known-output (port the run's `verify.py` checks); certify_ready
  true; full `measure→compute→certify→verify` happy path.

### Phase 4 — API surface (L4 seam)
Create `ViridisOS/api/` — a FastAPI app exposing: `GET /modules`, `POST /modules/{id}/preview`,
`POST /modules/{id}/certify`, `POST /certificates/verify`, `GET /standard`. Typed request/response models.
No business logic in the API layer — it only calls the runtime + certifier. Add `test_api.py` (TestClient)
covering each route + the blocked-module 4xx path. Document the integration point for the Next.js app
(the conservation app calls these endpoints; do not modify app internals in this phase).

### Phase 5 — Docs + wiring
- `ViridisOS/README.md` — how to run the service, run all tests, add a new module (the module-authoring
  guide: wrap a run engine, declare backing, register, done).
- A `Makefile`/`run_all_tests.sh` running every `test_*.py`; all green is the gate for "done".
- A short `HANDOFF_NOTES.md` recording: what's real vs. stubbed (the dev HMAC signer, the JSON cert store),
  and the exact swaps to production (real K3 signer, DATA-plane cert registry, live canon DOI resolver).

## 5. Tech constraints

- Python 3.11+, `pydantic` for models, `fastapi`+`httpx`/`starlette` TestClient for the API. Avoid other
  heavy deps. Pure functions where possible; deterministic; no network calls in tests.
- The canon-DOI resolver: implement `CanonResolver.resolve(doi) -> {verified: bool, lean_module, ...}`
  reading `RESEARCH_PIPELINE_v2/canon_fingerprint_index.json` + the ledger; stub with a local fixture if
  the live index isn't reachable, behind the same interface.
- Deterministic hashing = canonical JSON (`json.dumps(sort_keys=True, separators=(',',':'))`) → sha256.

## 6. Definition of done

1. `run_all_tests.sh` green across all phases (runtime, certification, mutualist, api).
2. Every invariant A-1…A-5 has a failing-if-violated test.
3. A demo script `ViridisOS/demo.py` runs the full flow on a sample portfolio and prints an issued
   certificate + a successful independent `verify`.
4. `HANDOFF_NOTES.md` clearly lists every stub and its production swap.
5. Nothing writes to the canon / Zenodo (A-5).

## 7. Do NOT

- Do not invent theorem backings or ARR; only reference real canon DOIs (resolver-checked).
- Do not modify the research pipeline, the canon repo, or publish anything.
- Do not build the remaining modules yet — ship the runtime, certification, Mutualist, and API first so
  the pattern is proven; Tempo and Restoration follow the same contract afterward.

Deliver a working, tested `ViridisOS/` service that a new module can be added to in under an hour by
wrapping a run engine and declaring its backing. That extensibility is the whole point.
