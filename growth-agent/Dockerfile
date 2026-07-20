FROM python:3.12-slim
WORKDIR /app
COPY growth-agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY growth-agent/growth_agent.py growth-agent/main.py growth-agent/targets.json ./
RUN useradd --system --uid 10001 --home /nonexistent viridis-growth \
    && mkdir -p /state \
    && chown viridis-growth:viridis-growth /state
USER viridis-growth
VOLUME ["/state"]
ENV GROWTH_AGENT_ENABLED=0 \
    GROWTH_AGENT_INTERVAL_SECONDS=86400 \
    GROWTH_STATE_DB=/state/viridis_growth.sqlite3
CMD ["python3", "main.py"]
