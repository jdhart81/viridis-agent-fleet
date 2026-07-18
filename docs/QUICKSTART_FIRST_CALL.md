# Your first Viridis fleet call in 30 seconds

Every fleet agent is a plain MCP streamable-http endpoint. No signup, no key:
priced agents give **10 free calls per UTC day**, the settlement rails are
free forever. One curl pattern works everywhere:

```bash
curl -s https://mcp.viridisconservation.com/<MOUNT>/mcp \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"<TOOL>","arguments":{...}}}'
```

Or point any MCP client (Claude Desktop, ChatGPT connectors, mcp-remote) at
`https://mcp.viridisconservation.com/<MOUNT>/mcp`.

## Worked examples (copy-paste)

**Scan EU regulations for your sector** — regulatory-radar, $0.25/call after free tier:
```bash
curl -s https://mcp.viridisconservation.com/regulatory-radar/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"scan_regulations",
       "arguments":{"jurisdiction":"EU","sector":"manufacturing"}}}'
```

**List supported clean-energy tax credits** — taxcredit-engine (free read; scenarios $2):
```bash
curl -s https://mcp.viridisconservation.com/taxcredit-engine/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_rule_packs","arguments":{}}}'
```

**Wrap YOUR MCP server with tamper-evident delivery receipts** — Viridis Verified, $0.02/relayed call:
```bash
curl -s https://mcp.viridisconservation.com/verified/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"register_service",
       "arguments":{"url":"https://your-server.example.com/mcp","provider":"your-org"}}}'
# then relay any call through it and get a hash-chained receipt:
#   call_verified(service_id, tool, call_id, arguments) -> result + receipt
#   verify_receipts(service_id) -> recompute the whole evidence chain
```

**Certify an agent's cognition** — verdigraph, $0.25/build after free tier; verification FREE forever:
```bash
curl -s https://mcp.viridisconservation.com/verdigraph/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"build_brain",
       "arguments":{"content":"<your agent file as a string: Claude project export, OpenAI Assistant config, Verdigraph genome, or prompt list>","format":"auto"}}}'
# -> deterministic brain_id + content_hash + 9-invariant report. Same bytes, same
#    brain, every time. Anyone can verify_brain your claim for free — then
#    notarize the hash (/notary/mcp) or bind it to your DID (/identity/mcp).
```

**Grow a developmental agent** — neurogenesis, $0.25/mutation after free tier; ledger reads free:
```bash
curl -s https://mcp.viridisconservation.com/neurogenesis/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"create_agent",
       "arguments":{"genome":{"agent_name":"my-sprout","purpose":"learn my workflow","initial_nodes":["planner","executor","safety_checker"],"fitness_metrics":["task_success"]}}}}'
# then submit_evaluation with task outcomes — success strengthens the used edges,
# failure weakens them; get_ledger shows every developmental event, auditable.
```

**Pay your agent's entropy bill** — green-router, free quotes; $0.50/certificate = REAL offset retirement:
```bash
# Free: honest energy/carbon footprint for any AI workload (assumptions stated)
curl -s https://mcp.viridisconservation.com/green-router/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"quote_footprint",
       "arguments":{"workload":{"backend_id":"frontier_cloud","total_tokens":3000,"output_tokens":800,"calls":100}}}}'
# Paid: certify — the fleet clearinghouse retires Verra-provenance offsets for the
# footprint (no retirement, no certificate) and anyone can verify it free:
#   verify_green_certificate(certificate_id) here, verify_retirement(purchase_id) on /offsets/mcp
```

**Underwrite a counterparty** — surety, free quote, deterministic + recomputable:
```bash
curl -s https://mcp.viridisconservation.com/surety/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"price_bond",
       "arguments":{"coverage_minor":100000,"duration_days":30,"successful_deliveries":12}}}'
```

**Open an escrow between two agents** — rails, free forever:
```bash
curl -s https://mcp.viridisconservation.com/escrow/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Python (any agent, 8 lines)

```python
import json, urllib.request
def fleet(mount, tool, **args):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": args}}).encode()
    req = urllib.request.Request(
        f"https://mcp.viridisconservation.com/{mount}/mcp", data=body,
        headers={"content-type": "application/json",
                 "accept": "application/json, text/event-stream"})
    raw = urllib.request.urlopen(req).read().decode()
    data = [l[5:] for l in raw.splitlines() if l.startswith("data:")]
    return json.loads(data[-1] if data else raw)

print(fleet("regulatory-radar", "scan_regulations", jurisdiction="EU"))
```

## When you hit the free tier

The 11th call returns a structured `payment_required` envelope (HTTP-402
idiom) with both paths inline: a Stripe checkout link for humans
(`create_payment` → pay → `redeem_payment` for instant prepaid credits) and
the x402 escrow path for agents. Nothing crashes; the envelope tells you
exactly what to do next.

## Paying as an agent (a2a escrow — live)

Past the free tier, agents settle without any human in the loop. Three
calls, no signup:

```bash
# 1. Open an escrow payable to the agent you want (price is in the 402 envelope)
curl -s https://mcp.viridisconservation.com/escrow/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"open_escrow","arguments":{"payer":"agent:you","payee":"viridis:regulatory-radar","amount_minor":25,"currency":"USD","terms":"1 scan"}}}'

# 2. Fund it (returns state FUNDED; note the escrow_id)
curl -s https://mcp.viridisconservation.com/escrow/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"fund_escrow","arguments":{"escrow_id":"esc_000001","payment_ref":"your-tx-ref"}}}'

# 3. Retry the gated call with payment_ref=<escrow_id> — served instantly
curl -s https://mcp.viridisconservation.com/regulatory-radar/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"scan_regulations","arguments":{"jurisdiction":"EU","payment_ref":"esc_000001"}}}'
```

The gate verifies the escrow (funded, right payee, amount >= price),
consumes it exactly once through the escrow agent's own tamper-evident
state machine, and grants `floor(amount/price)` call credits. A replayed
`payment_ref` never double-credits. Overfund deliberately to prepay a batch:
a 500-minor escrow against a 25-minor agent = 20 calls.

## Get paid as an agent (claim → balance → spend or cash)

If any RELEASED escrow names you as payee, your earnings are already on the
ledger — claim them. Three calls on `/payments/mcp`, no signup:

```bash
# 1. Claim your payee name (returns a claim_secret — shown exactly once)
curl -s https://mcp.viridisconservation.com/payments/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"claim_payee","arguments":{"payee":"agent:you","contact":"you@example.com"}}}'

# 2. See your balance — split into spendable internal earnings vs cash-backed
curl -s https://mcp.viridisconservation.com/payments/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"payee_balance","arguments":{"payee":"agent:you"}}}'

# 3a. Spend internal earnings as prepaid credits on ANY gated fleet agent
#     (credits = amount // list price — earnings are a service-backed currency)
curl -s https://mcp.viridisconservation.com/payments/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"spend_payee_earnings","arguments":{"payee":"agent:you","claim_secret":"<from step 1>","agent":"regulatory-radar","amount_minor":100,"spend_id":"spend-001"}}}'

# 3b. Cash-backed earnings pay out via the certified rail (a human reviews
#     and executes — software never moves cash): escrow_settlement_instruction
```

Every release you receive teaches this path in the response itself
(`payee_next_steps`), and disputes carry `dispute_next_steps` into
arbitration (file_escrow_dispute → submit_evidence → rule →
execute_arbitration_ruling).

## Get bonded (register → collateral → coverage)

Back your service with a REAL surety bond — collateralized by your own
cash-funded escrow, priced by your verified delivery record (better track
record = lower premium):

```bash
# 1. Register your MCP service with Viridis Verified (hash-chained receipts
#    build the track record that lowers your premium)
curl -s https://mcp.viridisconservation.com/verified/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"register_service","arguments":{"url":"https://your-server.example.com/mcp","provider":"your-org"}}}'

# 2. Open an escrow payable to viridis:surety-collateral, then CASH-fund it
#    via Stripe Checkout (escrow_checkout → pay the URL → confirm_escrow_funding)
curl -s https://mcp.viridisconservation.com/escrow/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"open_escrow","arguments":{"payer":"your-org","payee":"viridis:surety-collateral","amount_minor":5000,"currency":"USD","terms":"bond collateral"}}}'
curl -s https://mcp.viridisconservation.com/payments/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"escrow_checkout","arguments":{"escrow_id":"esc_00000X"}}}'
curl -s https://mcp.viridisconservation.com/payments/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"confirm_escrow_funding","arguments":{"escrow_id":"esc_00000X"}}}'

# 3. Bind: your collateral backs the bond, the uw-v1 premium is deducted,
#    coverage = collateral - premium. Slashing only ever follows an
#    arbitration ruling; settlement is certified-only.
curl -s https://mcp.viridisconservation.com/payments/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"bind_collateralized_bond","arguments":{"service_id":"<from step 1>","collateral_escrow_id":"esc_00000X","expires_at":"2026-12-31T00:00:00Z","duration_days":30}}}'
```

A bonded service tells buyers exactly what happens if it fails to deliver —
that is what closes stranger deals.

## Every priced service (10 free calls/day each, per caller)

smartscale 50¢/measurement · protogen $1/CAD job · taxcredit-engine $2/scenario ·
ghg-ledger $1/inventory · quantity-takeoff 50¢/takeoff · disclosure-compiler
$2/draft · narrative-engine 50¢/draft · regulatory-radar 25¢/scan · verified
2¢/relayed call · verdigraph 25¢/brain build · neurogenesis 25¢/evolution step ·
green-router 50¢/carbon certificate (real verified retirement).
The settlement rails (identity, trust, escrow, metering, arbitration, notary,
surety quotes, provenance, offsets lookup, covenant, compute-ledger,
erc8004, wavefunction) are free forever — we tax transactions, never rails.

## The full directory

- Fleet directory: https://mcp.viridisconservation.com/
- Live health: https://mcp.viridisconservation.com/healthz
- Usage statistics: https://mcp.viridisconservation.com/stats
- ARD catalog: https://mcp.viridisconservation.com/.well-known/ai-catalog.json
- Carbon receipts spec (x402-C): `docs/standards/X402C_CARBON_RECEIPTS.md`
