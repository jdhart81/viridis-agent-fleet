# settlement-engine-agent — the settlement layer for outcome-based capital

**What it is.** A progressive-settlement engine. Any contract, grant, offset or pay-for-success agreement that settles on an
officially published series — ISO electricity prices, election counts, restoration survival, canopy cover, soil carbon,
grid intensity — has a growing *already-known* component. This agent is that arithmetic, served: what is published (with
source hashes), what the remainder must do for an outcome to settle, which strikes are **decided by arithmetic alone**, and
immutable settlements any third party can recompute. It never forecasts, never trades, holds no keys.

**Where it comes from.** Sixty days of preregistered Kalshi research (Viridis count lane, ENERGY-1, DECIDE-1/US-1, MAKER-1,
DATA-1) found one mechanism that pays and one that never does: forecasting loses to the price; reading the official number
before anyone has done the arithmetic wins. Restoration finance is linear because nobody trusts the settlement of ecological
outcomes. Capital that pays only on verified outcomes is circular capital; the settlement seat earns on every dollar of it.

## Tools (MCP)
| tool | price | what |
|---|---|---|
| `register_series` | free | declare a series: unit, aggregate (mean/sum/share/last), expected slots, declared value bounds, strikes |
| `ingest` | free | append observations `{slot, value, source_url, source_sha256, observed_at}`; re-posts are logged revisions |
| `period_status` | free | published share and aggregate; per strike: required remainder, decided (facts) and a labelled model p (separate) |
| `required_remainder` | free | the one number a buyer needs: what the rest of the period must average / sum to / hit |
| `decided_strikes` | free | every strike across series decided by the published part alone |
| `explain` | free | deterministic plain-language reading (no LLM in the serving path) |
| `compile_contract` | **paid** | Verified Outcome Contract v0: series + strike + rule + closing time, content-addressed |
| `settle_contract` | **paid** | YES / NO / UNDECIDED at an explicit time, with every observation hash used |
| `verify_settlement` | free | recompute a settlement from its stored evidence (hash, aggregate, result checked separately) |

## Invariants (spec-invariance contract; full text in `src/core.py`)
S1 facts and models separate · S2 deterministic (Decimal, sorted-key JSON, explicit `now`) · S3 no trading/keys/network ·
S4 every observation is hashed evidence · S5 **decided means decided** (YES only if the strike clears with every remaining
slot at the declared minimum; NO only if it misses with every slot at the maximum; no bounds → nothing decided until
complete) · S6 never raises · S7 revisions visible · S8 settlements immutable and recomputable · S9 bounded · S10 closure
declared, never inferred (incomplete + undecided at closure = UNDECIDED, never a guess).

## Run
```bash
python3 -m unittest discover -s tests -v          # 27 tests; 12/12 arithmetic mutants killed (2026-11-06)
python3 adapters/mcp_server.py                     # describe
python3 adapters/mcp_server.py --serve             # MCP (needs `pip install mcp`)
python3 examples/restoration_survival.py           # the circular lane on one planting (sample CSV included)
python3 examples/ercot_from_energy1.py --db /opt/energy1/state/energy1.sqlite --hub HB_NORTH \
    --start 2026-11-03T00:00 --end 2026-11-10T00:00 --strikes 25,30,35,40   # live ERCOT week from the ENERGY-1 store
```

## First live output (2026-11-06 13:10Z, ERCOT North week of Nov 3, from the research droplet)
316 of 672 intervals published (47%), published mean $27.55/MWh (min −15.51, max 193.05). Strike 30: undecided; the remaining
356 intervals must average $32.18 for YES (model p 0.00). Strike 25: remainder must average $22.74 (p 0.22). Nothing is
decided at 47% because ERCOT's declared bounds (−251 to 5,000 $/MWh) leave every strike reachable — which is the honest
answer; "decided" arrives late in a period, when the arithmetic closes.

## Restoration example (the circular lane)
A watershed fund pays a VergeCommon coop on "≥ 80% of 120 planted stems alive at month 12", verified by Viridis D-Score.
With 104 stems surveyed and 99 alive, the share is 0.825 even if all 16 unsurveyed stems are dead → **DECIDED YES** before the
survey is complete; the settlement lists all 104 field-record hashes and `verify_settlement` recomputes it: `match: true`.

## Composition
ghg-ledger (grid-intensity series as a Scope 2 input) · regulatory-radar (buyers under disclosure deadlines) · notary /
verified-relay (receipt hardening) · escrow (release on YES) · green-router (certificates settle on retired-mass series).

## Known limits (stated before data)
- The ERCOT adapter's `source_sha256` is the hash of the canonical store row, not yet of ERCOT's document; the ENERGY-1 store
  will record document hashes next.
- The remainder model is v0 (trailing Normal, sd doubled) and is display-only by S1; a calibrated v1 is a new version.
- State is in-process (`StateStore`); the gateway's persistent store wiring is the deployment step.
- Prices at the fleet gate are launch proposals; Justin sets them.
