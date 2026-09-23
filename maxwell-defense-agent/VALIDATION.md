# Local validation — September 13, 2026

Final combined run: **120 passed** using Python's local pytest environment.

```sh
python3 -m pytest -q \
  deploy/gateway/test_maxwell_fleet.py \
  maxwell-defense-agent/tests/test_maxwell.py \
  deploy/gateway/test_value_decision.py \
  deploy/gateway/test_adoption_loop.py \
  deploy/gateway/test_static_security_migration.py \
  deploy/gateway/test_x402_http.py \
  deploy/gateway/test_x402_v2.py \
  deploy/gateway/test_security_plane_federation.py
```

Ten new tests cover the candidate; the remaining 110 exercise existing payment,
discovery, adoption and security behavior. During integration, the discovery
regression test found that the candidate's value profile was present with the
feature disabled. The profile now follows the same startup flag as its route;
the final combined run passed.

New checks cover default-off and enabled discovery, adapter loading, exact $1
unpaid quote, invalid/disabled rejection before settlement, simulated paid
delivery, payment replay rejection and MCP gating. The settlement test uses a
mocked local fixture; no real money moved. Guard checks cover request/caller/
tenant binding, token tampering, replay after restart, concurrent consumption
across local workers, expiry, store capacity/failure, rate and solve bounds,
body limits and blocking before backend execution.

[Sample rehearsal](examples/rehearsal.local.json) was produced by the included
local example. Its timing is a local hash-only microbenchmark, not an endpoint
load test. The service's client timings are explicitly modeled.

Production deployment and restart verification passed subsequently; see the
[release receipt](../docs/deployment/MAXWELL_FLEET_RELEASE_2026-09-13.md).

Not performed: live paid purchase, actual attack/load
testing, multi-host replay-store validation, independent security review,
energy measurements or buyer usefulness validation. Adaptive selection and
managed operation remain planned work. Reference middleware is not mounted on
the current fleet; enabling paid discovery does not enable enforcement.
