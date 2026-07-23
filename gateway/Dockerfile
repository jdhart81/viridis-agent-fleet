# Viridis Agent Stable — MCP Gateway (fleet agents, one container)
# Build from the FLEET ROOT:  docker build -f deploy/gateway/Dockerfile -t viridis-stable .
FROM python:3.12-slim
WORKDIR /fleet
COPY deploy/gateway/requirements.txt /fleet/deploy/gateway/requirements.txt
RUN pip install --no-cache-dir -r deploy/gateway/requirements.txt
# copy only what the gateway serves: 22 leaf agents, subscription/payment
# infrastructure, and the gateway itself
COPY agent-identity-registry-agent/ agent-identity-registry-agent/
COPY agent-trust-oracle-agent/ agent-trust-oracle-agent/
COPY agent-escrow-agent/ agent-escrow-agent/
COPY agent-metering-agent/ agent-metering-agent/
COPY agent-arbitration-agent/ agent-arbitration-agent/
COPY agent-compute-ledger-agent/ agent-compute-ledger-agent/
COPY agent-covenant-agent/ agent-covenant-agent/
COPY agent-provenance-agent/ agent-provenance-agent/
COPY agent-offset-clearinghouse-agent/ agent-offset-clearinghouse-agent/
COPY agent-erc8004-bridge-agent/ agent-erc8004-bridge-agent/
COPY agent-surety-agent/ agent-surety-agent/
COPY agent-notary-agent/ agent-notary-agent/
COPY wavefunction-search-agent/ wavefunction-search-agent/
COPY smartscale-agent/ smartscale-agent/
COPY protogen-agent/ protogen-agent/
COPY regulatory-radar-agent/ regulatory-radar-agent/
COPY narrative-engine-agent/ narrative-engine-agent/
COPY taxcredit-engine-agent/ taxcredit-engine-agent/
COPY ghg-ledger-agent/ ghg-ledger-agent/
COPY quantity-takeoff-agent/ quantity-takeoff-agent/
COPY disclosure-compiler-agent/ disclosure-compiler-agent/
COPY subscriptions-agent/ subscriptions-agent/
COPY agent-verified-relay-agent/ agent-verified-relay-agent/
COPY verdigraph-brain-agent/ verdigraph-brain-agent/
COPY neurogenesis-agent/ neurogenesis-agent/
COPY green-router-agent/ green-router-agent/
COPY viridisos/ viridisos/
ENV VIRIDISOS_CANON_INDEX=/fleet/viridisos/_canon/canon_fingerprint_index.json
COPY deploy/gateway/viridis_mcp_gateway.py deploy/gateway/
COPY deploy/gateway/stripe_payments.py deploy/gateway/
COPY deploy/gateway/state_store.py deploy/gateway/
COPY deploy/gateway/payment_gate.py deploy/gateway/
COPY deploy/gateway/account_auth.py deploy/gateway/
COPY deploy/gateway/request_context.py deploy/gateway/
COPY deploy/gateway/reconciliation.py deploy/gateway/
COPY deploy/gateway/x402_rail.py deploy/gateway/
COPY deploy/gateway/x402_http.py deploy/gateway/
COPY deploy/gateway/x402_v2.py deploy/gateway/
COPY deploy/gateway/a2a_commerce.py deploy/gateway/
COPY deploy/gateway/hub_kernel.py deploy/gateway/
COPY deploy/gateway/escrow_custody.py deploy/gateway/
COPY deploy/gateway/connect_rail.py deploy/gateway/
COPY deploy/gateway/weave.py deploy/gateway/
COPY deploy/gateway/participant_bridge.py deploy/gateway/
COPY deploy/gateway/bond_bridge.py deploy/gateway/
COPY deploy/gateway/underwriting_bridge.py deploy/gateway/
COPY deploy/gateway/insured_job_bridge.py deploy/gateway/
COPY deploy/gateway/persistence_probe.py deploy/gateway/
COPY deploy/gateway/deck.html deploy/gateway/
COPY deploy/gateway/stats.html deploy/gateway/
COPY deploy/gateway/seats.html deploy/gateway/
COPY deploy/gateway/agents.html deploy/gateway/
COPY deploy/gateway/quickstart.html deploy/gateway/
COPY deploy/gateway/llms.txt deploy/gateway/
COPY deploy/gateway/viridis-mark.svg deploy/gateway/
COPY scripts/genesis_receipts.py scripts/
COPY scripts/viridis_market_router.py scripts/
# persistence volume mounts here (compose: gateway_state:/data, STATE_DB env)
RUN mkdir -p /data docs/deployment
EXPOSE 8402
HEALTHCHECK --interval=30s --timeout=5s CMD python3 -c "import urllib.request,sys; sys.exit(0 if b'ok' in urllib.request.urlopen('http://127.0.0.1:8402/healthz').read() else 1)"
CMD ["python3", "deploy/gateway/viridis_mcp_gateway.py", "--port", "8402"]
