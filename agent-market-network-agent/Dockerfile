FROM python:3.12-slim
WORKDIR /app
COPY agent-market-network-agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY agent-market-network-agent/src/ ./src/
COPY agent-market-network-agent/adapters/ ./adapters/
COPY agent-market-network-agent/main.py ./main.py
COPY agent-market-network-agent/seed_profiles.json ./seed_profiles.json
RUN useradd --system --uid 10002 --home /nonexistent viridis-market \
    && mkdir -p /state \
    && chown viridis-market:viridis-market /state
USER viridis-market
VOLUME ["/state"]
ENV MARKET_HOST=0.0.0.0 \
    MARKET_PORT=8410 \
    MARKET_PUBLIC_BASE=https://mcp.viridisconservation.com/network \
    MARKET_STATE_DB=/state/agent_market_network.sqlite3 \
    MARKET_SEED_PROFILES=/app/seed_profiles.json
EXPOSE 8410
HEALTHCHECK --interval=30s --timeout=5s CMD python3 -c "import urllib.request,sys; sys.exit(0 if b'\"status\":\"ok\"' in urllib.request.urlopen('http://127.0.0.1:8410/healthz').read() else 1)"
CMD ["python3", "main.py"]

