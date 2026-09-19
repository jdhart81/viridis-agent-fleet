# Put Security Preflight into one real workflow

For an MCP operator deciding whether to add or change a tool integration.
Start with one owned manifest, one policy and one decision the check should
inform. The assessment covers supplied artifacts, not deployed runtime safety.

## First useful result

1. Run the [free before-and-after example](SECURITY_PREFLIGHT_SAMPLE.md).
   Decide whether these checks address your actual question.
2. Prepare your own inputs and [inspect an unpaid quote](SECURITY_PREFLIGHT_BUYER_QUICKSTART.md).
   Pay only after approving the exact price and a spending ceiling.
3. Save the result privately and [verify its signature and exact inputs](AGENT_SECURITY_INTEGRATION.md)
   using an independently provisioned trust policy.
4. Record the decision it informed: what changed, what still needs investigation,
   or why the result was not useful. Passing a check alone is not this evidence.
5. Preview and explicitly submit your chosen feedback with the helper in the
   buyer guide. Partial and negative results are useful product feedback too.

An MCP connection alone does not provide payment support. The current paid
client requires the documented x402 SDK and a buyer-controlled Base USDC wallet.
If that is the blocker, report it when requesting an integration scope; no
alternative payment support is promised here.

## Return when the workflow changes

Retain the paid result and operator-approved trust file in private storage.
Use the [verified change gate](SECURITY_PREFLIGHT_CHANGE_CHECK.md) on your own
release event. A valid unchanged assessment is reused, with its findings.
A relevant change or expiry requires review and may justify another separately
authorized purchase. The free check never signs, pays or enrolls you.

The [manual GitHub Actions template](../examples/security-preflight-release-check.yml)
shows the wiring. It needs an operator-reviewed Viridis commit and protected
input, result and trust configuration. It contains no wallet credentials and
does not run until you install and invoke it in your own repository.
Before each run, regenerate `PREFLIGHT_CURRENT_INPUTS_JSON` from the manifest,
policy and samples for the intended release. The template compares that
supplied snapshot; it does not discover repository or deployed-runtime changes.
Reusing an old input secret could keep reporting `UNCHANGED` until expiry even
though your actual application changed.

## Request a recurring service scope

If you need someone to operate the checks and review exceptions, contact
[Viridis Security](mailto:viridissecurity1@gmail.com?subject=Security%20Preflight%20integration%20scope)
with a non-sensitive description of:

- The integration and the decision its operator is responsible for.
- Whether you already completed an assessment and what you found useful.
- How frequently the manifest or policy changes, and expected monthly checks.
- What happens when a check needs review, including the response time you need.
- The budget owner, budget range and an agreed measure of useful service.

Do not email private paid-result files, credentials or feedback tokens. An
inquiry is qualification only: it does not start monitoring, create a contract,
enroll a subscription or authorize a charge. A recurring price and support
boundary require a separate agreed scope. Existing Reliability Sprint and
post-Sprint Watch offers are distinct services.

## What to measure during the pilot

Record time to prepare inputs, time to obtain and verify the first result,
decisions informed, false alarms or missing evidence, and independently chosen
repeat checks. Record actual service and support costs separately. A paid
assessment, a useful result, a repeat purchase and an active recurring contract
are distinct milestones.
