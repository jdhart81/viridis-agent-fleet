# Verified Outcome Contract v0 — the first turn of the circular-capital flywheel

A pay-for-success restoration agreement that settles itself on verified field data. This is the packet a buyer sees;
the engine behind it is the hosted Viridis Settlement Engine. Nothing here is legal, financial or investment advice; the
payment terms live in the parties' own agreement, and a settlement is evidence, not a payment.

## The deal (template, one planting)
| field | value (template) |
|---|---|
| Buyer | a watershed fund, municipality, or a company under SB 253/261 disclosure pressure (Regulatory Radar's California list) |
| Steward | a VergeCommon neighborhood co-op (owns the planting; does the work) |
| Verifier | Viridis LLC — Viridis D-Score field records, hashed per stem |
| Milestone | ≥ 80% of 120 planted riparian stems alive at month 12 |
| Series | `aggregate: share`, `n_expected: 120`, one slot per stem (0 dead / 1 alive), source = the D-Score plot URL |
| Strike / rule | 0.8 / `above` |
| Closes | 15 days after the month-12 survey window |
| Payment on YES | $9,600 to the steward (e.g. $80/stem) |
| Verification fee | 5% of the outcome value ($480) to the verifier on any settlement, YES or NO |
| UNDECIDED at closure | re-settle after the full survey; no payment moves until a YES |

## How it settles (what the engine guarantees)
1. The steward's survey records arrive as observations (`ingest`), each with the record URL and the record's SHA-256.
2. From the published part alone, the strike is **decided** the moment the remaining stems cannot change the answer
   (99 alive of 104 surveyed → 0.825 ≥ 0.8 even if all 16 unsurveyed are dead → DECIDED YES before the survey ends).
3. `settle_contract` writes an immutable settlement carrying every record hash it used; `verify_settlement` recomputes
   it for free, for the buyer, the steward, an auditor, or another agent.
4. The buyer's payment can be escrowed on the fleet (`escrow` rail) and released on a YES settlement — the composition
   that makes capital circular: no verified outcome, no money moves; verified outcome, money moves to the next planting.

## Why a buyer pays for this
- They pay for outcomes, not promises, and they can check the arithmetic themselves.
- Disclosure-grade evidence: hashed field records, deterministic settlement, versioned engine — the same discipline as
  the GHG Ledger and Disclosure Compiler the fleet already runs.
- The verifier is paid on any settlement, so there is no incentive to shade the result.

## What Viridis earns per contract
Verification fee (5% of outcome value) + $1 compile + $1 settle at the gate, + the field-record data set. At 20
contracts a season on $10k outcomes that is $10k of verification revenue — small, repeatable, and every dollar of it is
tied to an acre that was actually restored.

## Steps to the first signed contract
1. Pick the planting (a VergeCommon co-op plot with a month-12 survey due within 90 days).
2. Register the series on the hosted engine (free) and ingest the records surveyed so far; share `period_status`.
3. Send this packet plus the live `explain` text to two buyers from the California list; ask for one.
4. Compile the contract (`compile_contract`, $1) with both parties named; escrow the outcome value on the fleet.
5. Settle on the survey; verify; release.

Live demo today: series `f08c7fdd5e7157e825da7b23` (Mad River riparian planting) on the hosted engine; the sample
records are in `examples/restoration_survival_sample.csv`.
