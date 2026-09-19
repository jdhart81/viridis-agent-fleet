# Contributing to Viridis Agent Fleet

Contributions should make one documented integration safer, clearer or easier
to reproduce. This repository exposes schemas, clients, examples and selected
reference implementations; it is not a complete self-hosted copy of the
production fleet.

## Start small

1. Run the free Security Preflight sample from the repository root:

   ```bash
   python3 scripts/preflight_sample_report.py
   ```

2. If the result helped or the path failed, file an
   [integration trial](https://github.com/jdhart81/viridis-agent-fleet/issues/new?template=integration_trial.yml)
   with public or synthetic inputs.
3. For a code or documentation change, open or comment on an issue before
   beginning substantial work. Include the smallest reproducible example and
   the decision the output is meant to support.

Never post wallet keys, credentials, private manifests, complete paid-result
files, feedback tokens or personal information. Security vulnerabilities should
be reported through GitHub private vulnerability reporting as described in
[SECURITY.md](SECURITY.md), not in a public issue.

## Pull requests

- Keep the change narrowly scoped and document its trust boundary.
- Add or update a regression test for behavior changes.
- Preserve quote-only and no-spend defaults. A test must never sign or submit a
  payment.
- Do not claim that a receipt proves usefulness, runtime behavior, independent
  review or certification.
- Run the tests closest to the files changed. For the repository security
  baseline:

  ```bash
  python3 -m unittest \
    scripts/test_workflow_actions_pinned.py \
    scripts/test_publish_mcp_registry_idempotent.py \
    scripts/test_a2a_quote_client.py \
    scripts/test_viridis_preflight_buy.py \
    scripts/test_viridis_preflight_feedback.py \
    scripts/test_static_security_buyer.py \
    scripts/test_agent_search_audit.py \
    scripts/test_repo_funnel_snapshot.py
  ```

By participating, you agree to keep discussion professional, specific and
focused on the work. Maintainers may close unsafe requests, payment solicitations,
spam, harassment or reports that expose private data.
