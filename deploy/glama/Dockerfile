# Viridis Agent Fleet — single-install stdio bridge.
# Glama builds this image for its automated safety/quality checks: it starts,
# connects to the live hosted fleet on mcp.viridisconservation.com,
# lists their tools, and re-exposes them namespaced <agent>__<tool> over stdio.
# The same image lets any user install the whole fleet in one line.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "mcp>=1.2"
COPY fleet_bridge.py /app/fleet_bridge.py
COPY fleet_manifest.json /app/fleet_manifest.json
# Optional override: point at a different gateway origin.
ENV VIRIDIS_BASE=https://mcp.viridisconservation.com
# stdio MCP server (Glama / Claude Desktop / Cursor connect over stdio)
CMD ["python3", "/app/fleet_bridge.py"]
