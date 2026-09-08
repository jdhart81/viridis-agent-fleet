# One assessment, then check real changes

Security Preflight checks the MCP manifest, tool schemas, policy and samples
you supply. It does not fetch, execute or certify the deployed service.

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

| Decision | Next action |
|---|---|
| `UNCHANGED` | Retain the existing findings; no new payment is needed. A previous failed assessment still fails. |
| `RECHECK_REQUIRED` | Review the reason, inspect a fresh quote, and separately authorize another assessment if warranted. |
| `BASELINE_REQUIRED` | Supply the correct prior result or decide whether to buy the first assessment. |
| Error | Resolve the baseline/input/transport issue; never interpret an error as a pass. |

An unchanged result does not authorize tool execution. This runner does not
schedule managed monitoring, create a subscription or charge automatically.

## 5. Close the feedback loop

Tell the operator assisting your pilot whether the findings were useful,
partially useful or not useful, and whether you would buy again. Share the
specific integration decision without sharing the private result token.
Machine clients can submit the one-time outcome using the supported
`viridis_delivery.feedback` contract and the documented gateway feedback
schema. Only the buyer chooses that outcome; successful transport alone does
not establish usefulness.

[Service contract](https://mcp.viridis-security.com/security-preflight/service.json)
and [change-check details](SECURITY_PREFLIGHT_CHANGE_CHECK.md).
