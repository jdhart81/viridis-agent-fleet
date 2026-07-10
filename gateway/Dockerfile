# Viridis Agent Stable — MCP Gateway (13 agents, one container)
# Build from the FLEET ROOT:  docker build -f deploy/gateway/Dockerfile -t viridis-stable .
FROM python:3.12-slim
WORKDIR /fleet
COPY deploy/gateway/requirements.txt /fleet/deploy/gateway/requirements.txt
RUN pip install --no-cache-dir -r deploy/gateway/requirements.txt
# copy only what the gateway serves: the 13 agents + the gateway itself
COPY agent-identity-registry-agent/ agent-identity-registry-agent/
COPY agent-trust-oracle-agent/ agent-trust-oracle-agent/
COPY agent-escrow-agent/ agent-escrow-agent/
COPY agent-metering-agent/ agent-metering-agent/
COPY agent-arbitration-agent/ agent-arbitration-agent/
COPY agent-compute-ledger-agent/ agent-compute-ledger-agent/
COPY agent-covenant-agent/ agent-covenant-agent/
COPY agent-provenance-agent/ agent-provenance-agent/
COPY agent-offset-clearinghouse-agent/ agent-offset-clearinghouse-agent/
COPY smartscale-agent/ smartscale-agent/
COPY protogen-agent/ protogen-agent/
COPY regulatory-radar-agent/ regulatory-radar-agent/
COPY narrative-engine-agent/ narrative-engine-agent/
COPY deploy/gateway/viridis_mcp_gateway.py deploy/gateway/
EXPOSE 8402
HEALTHCHECK --interval=30s --timeout=5s CMD python3 -c "import urllib.request,sys; sys.exit(0 if b'ok' in urllib.request.urlopen('http://127.0.0.1:8402/healthz').read() else 1)"
CMD ["python3", "deploy/gateway/viridis_mcp_gateway.py", "--port", "8402"]
