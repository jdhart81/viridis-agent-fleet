# smartscale-agent — Agent Context
## Harness Compliance: Playbook v1.1

## Project
Deterministic CR80 pixel-geometry scaling agent for Viridis LLC. The production
MCP receives caller-supplied card and object pixel geometry; it does not
receive images or perform object detection.

**Pillar:** revenue  
**Status:** conditional-beta  
**Permission Tier:** Tier 1 (write-enabled) — promote to Tier 2 only with explicit justification  
**Revenue Model:** Ten state-changing calls per caller per UTC day are free,
then $0.50 per deterministic scaling call. Commercial validation remains
absent until an external paid call is independently verified.

This agent operates under the Universal Agent Harness Playbook v1.1 (Viridis LLC).
All ten hard invariants (§1) apply without exception.

## Invariants
- I-1: All tool results are message content, never system prompt mutations (Harness §I-1)
- I-2: Permission tier is frozen at session init — no runtime escalation (Harness §I-3)
- I-3: Every file write is journaled with SHA256 before/after hashes (Harness §I-5)
- I-4: Budget checks run before every action, not after (Harness §I-4)
- I-5: Spec invariance protocol: restate → flag → verify for every non-trivial task (Harness §I-10)

## Directory Map
- `src/`         → main source — read and write
- `adapters/`    → model provider adapters — read and write
- `tests/`       → test files — write only to add tests
- `agent.yaml`   → agent manifest — read only (modify via version bump process)

## Forbidden Operations
- Never write credentials, API keys, or secrets to any file (use env vars exclusively)
- Never delete files — use write_file to empty if needed
- Never modify agent.yaml without a version bump
- Never commit code without running the test suite

## Output Contract
- All structured outputs MUST be valid JSON matching the agent's declared output schema
- Error responses MUST use the harness error taxonomy (§11): PermissionError, ValidationError, BudgetError, ContextError, BackendError, RuntimeError
- All outputs MUST include session_id and budget_consumed metadata
- Spec invariance: every non-trivial output includes a verification report against stated invariants

## Domain Terminology
- **Intelligence Bound:** dI/dt ≤ P·D/(k_B·T·ln 2) — the thermodynamic ceiling on information processing
- **D-Score:** Biodiversity density metric normalized to [0, 1]
- **HDFM:** Hierarchical Dendritic Forest Management — graph-theoretic corridor design
- **Pillar:** Agent classification (revenue / climate-intelligence / high-ceiling / infrastructure)
- **Spec Invariance:** Restate requirements as testable invariants before implementation

## Authorized External Endpoints
The SmartScale core calls no external endpoint. Billing and persistence are
provided by the shared gateway wrappers.

## Budget Profile
See Harness Playbook §8.3 for class-specific defaults. Override in agent.yaml or session config.

---
*Generated 2026-04-03 — Harness Playbook v1.1 compliance sweep*


## Worked example (copy-paste)

One `tools/call` against the live endpoint — no auth, no signup; the first
10 state-changing calls per day are free, then $0.50/call
(Stripe Checkout for humans, or an a2a escrow via `payment_ref` for agents —
the 402 envelope carries both sets of instructions).

```bash
curl -s https://mcp.viridisconservation.com/smartscale/mcp \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "scale_objects_from_credit_card", "arguments": {"image_id": "source-001", "credit_card_pixel_width": 856.0, "objects": [{"label": "part", "pixel_width": 428.0, "pixel_height": 214.0}], "request_id": "buyer-order-001"}}}'
```

Real response (from this exact request; long fields truncated):

```json
{
  "status": "ok",
  "action": "measure_from_credit_card",
  "result": {
    "status": "ok",
    "action": "measure_from_credit_card",
    "image_id": "source-001",
    "calibration": {
      "reference": "standard CR80-size card",
      "standard_width_mm": 85.6,
      "standard_height_mm": 53.98,
      "credit_card_pixel_width": 856.0,
      "credit_card_pixel_height": null,
      "pixels_per_mm": 10.0,
      "height_pixels_per_mm": null,
      "aspect_error_pct": null
    },
    "objects": [
      {
        "label": "part",
        "pixels": {
          "width": 428.0,
          "height": 214.0,
          "area": 91592.0,
          "perimeter": 1284.0
        },
        "dimensions_mm": {
          "width": 42.8,
          "height": 21.4,
          "area_mm2": 915.92,
          "perimeter": 128.4
        }
      }
    ],
    "assumptions": [
      "caller_supplied_pixel_geometry",
      "coplanar_2d_geometry",
      "rectangular_area_perimeter_estimate"
    ],
    "warnings": [],
    "timestamp": "2026-07-16T04:37:17.359274"
  },
  "timestamp": "2026-07-16T04:37:17.359281"
}
```
