# One assessment, then check real changes

Security Preflight checks the MCP manifest, tool schemas, policy and samples
you supply. It does not fetch, execute or certify the deployed service.

First, [inspect a reproducible sample assessment](SECURITY_PREFLIGHT_SAMPLE.md) to decide whether these bounded checks answer your question.

## 1. Prepare your inputs and inspect a free quote

Use Python 3.10 or newer. From a fresh checkout:

```sh
git clone https://github.com/jdhart81/viridis-agent-fleet.git
cd viridis-agent-fleet
cp examples/security-preflight-inputs.json inputs.json
```

Replace the example with one agent's actual manifest, policy and samples that
you are authorized to submit. Do not include credentials. Then run:

```sh
python3 scripts/viridis_preflight_buy.py --inputs inputs.json
```

This loads no wallet and makes no payment. `QUOTE_READY` prints the exact
Security resource, Base network, USDC asset, recipient and price. It is not
an assessment result. List price is $1 USDC; an eligible introductory quote
may be $0.01. The buyer-specific fresh quote governs.

## 2. Explicitly authorize one capped purchase

Only continue if you intend to buy the assessment. Install the buyer SDK in
your own environment:

```sh
python3 -m venv .venv-buyer
. .venv-buyer/bin/activate
python -m pip install "x402[requests,evm]==2.16.0"
```

Set `X402_BUYER_PRIVATE_KEY` through your existing local secret manager. The
wallet must control sufficient USDC on Base. Never paste the key into a
website, commit it, or share it with Viridis. For a purchase capped at $0.01:

```sh
python scripts/viridis_preflight_buy.py --inputs inputs.json \
  --pay --max-payment-usdc 0.01 --output paid-result-001.json
```

If that cap is too low, the client stops before payment. Raise it only after
you approve the current price. Each invocation authorizes at most one paid
HTTP attempt. The client rejects a different resource, chain, asset or
recipient and does not follow redirects or automatically retry.

`--source github`, `direct`, `search`, or `other` may be supplied when that
is your actual discovery source. Omit it if unknown. Internal rehearsals use
`--source internal`; they are not customer acquisitions.

## 3. Inspect and retain your result

`PAID_RESULT_SAVED` reports a local filename and assessment receipt ID. Open
the JSON locally and inspect `verdict`, findings and signed receipt evidence.
The client checks delivery hashes; this establishes file consistency, not
independent buyer acceptance or proof of runtime safety.

The complete result is created with owner-only file permissions and is never
overwritten. It contains a private buyer-feedback token inside
`viridis_delivery.feedback`; do not publish the complete file or commit it.
The public assessment link is under `receipt` and omits that feedback token.
Record whether a finding changed your integration decision. An unsuccessful
or incomplete response is saved too; it must not be reported as delivered.

If interrupted or shown `PAYMENT_OUTCOME_UNKNOWN`, keep the reserved file and
reconcile the wallet transaction and seller outcome before purchasing again.
A timeout is not proof that no payment settled. A redirect or failed response
also stops the client. Use a new output filename only for a separately
authorized purchase, never to bypass an unresolved result.

## 4. Reuse the baseline on a release event

```sh
python3 scripts/viridis_preflight_watch.py --inputs inputs.json \
  --paid-result paid-result-001.json
```

The free runner compares your current inputs with the authentic stored
assessment. Attach this command to your own manifest or policy release event;
keep signing keys out of that free-check job.

For a pass/fail release step, add `--ci --trust trust.json`, using the
[operator-approved verification policy](AGENT_SECURITY_INTEGRATION.md). The
diagnostic command above exits 0 when the comparison completes; CI mode exits
0 only for an unchanged, authenticated preflight pass. Stop on every nonzero
exit and review changes before authorizing another purchase.

| Decision | Next action |
|---|---|
| `UNCHANGED` | Retain the existing findings; no new payment is needed. A previous failed assessment still fails. |
| `RECHECK_REQUIRED` | Review the reason, inspect a fresh quote, and separately authorize another assessment if warranted. |
| `BASELINE_REQUIRED` | Supply the correct prior result or decide whether to buy the first assessment. |
| Error | Resolve the baseline/input/transport issue; never interpret an error as a pass. |

An unchanged result does not authorize tool execution. This runner does not
schedule managed monitoring, create a subscription or charge automatically.

## 5. Close the feedback loop

Choose whether the findings were `USEFUL`, `PARTIALLY_USEFUL` or `NOT_USEFUL`,
and independently choose whether you would buy again. Preview your feedback
locally; this example records a **partial** result and **no** repeat intent:

```sh
python3 scripts/viridis_preflight_feedback.py --paid-result paid-result-001.json \
  --outcome PARTIALLY_USEFUL --would-buy-again no --reason missing_evidence
```

Choose values that reflect your own experience. No feedback is sent by default.
To submit the choices you reviewed, repeat the same command with
`--submit --output feedback-001.json`. The helper sends once to the existing
feedback endpoint, keeps its bearer token out of logs, and saves a private
confirmation. It makes no purchase or subscription. An existing output file
is never overwritten.

If confirmation is lost, retain the output and reconcile before retrying.
An explicitly chosen retry using the **same paid result and choices** and a
new output filename uses the same idempotency key. Changed choices cannot
overwrite the original one-time outcome; a conflict requires review.

The feedback proves possession of the result token, not independent identity,
payment or a new sale. Keep the specific decision the assessment informed in
your own pilot notes. The helper does not upload free-text notes or tokens to
public issues. [Pilot and recurring-service qualification](SECURITY_PREFLIGHT_PILOT.md).

[Service contract](https://mcp.viridis-security.com/security-preflight/service.json)
and [change-check details](SECURITY_PREFLIGHT_CHANGE_CHECK.md).

## Agent integration verification

Before relying on a saved manifest assessment, follow the
[offline verification guide](AGENT_SECURITY_INTEGRATION.md). The buyer helper's
delivery hashes do not establish issuer authenticity. The verifier separately
checks an operator-pinned signing key, scanner policy, expiry and exact inputs.
