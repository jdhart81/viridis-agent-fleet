"""The landing page must not shadow the existing MCP and change-check routes."""
import json
import sys
from pathlib import Path

from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
import viridis_mcp_gateway as gateway


def test_preflight_page_is_indexable_and_keeps_machine_routes(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("SECURITY_PREFLIGHT_RECEIPT_DB_PATH", str(tmp_path / "receipts.db"))
    monkeypatch.setattr(gateway, "EXTERNAL_MEMBERS", [])
    with TestClient(gateway.build_app()) as client:
        for path in ("/security-preflight", "/security-preflight/"):
            response = client.get(path)
            assert response.status_code == 200
            assert 'href="https://mcp.viridisconservation.com/security-preflight"' in response.text
            assert 'application/ld+json' in response.text
            structured = response.text.split('<script type="application/ld+json">')[1].split('</script>')[0]
            assert json.loads(structured)["softwareVersion"] == "1.2.0"
            assert "noindex" not in response.headers.get("x-robots-tag", "")
        assert "<loc>https://mcp.viridisconservation.com/security-preflight</loc>" not in client.get("/sitemap.xml").text
        llms = client.get("/llms.txt").text
        assert "https://mcp.viridis-security.com/security-preflight" in llms
        assert "https://mcp.viridisconservation.com/security-preflight" not in llms
        assert "MCP Security Preflight" in client.get("/quickstart").text
        assert client.post("/security-preflight/watch", json={"inputs": {}}).status_code == 400
        # A mounted MCP route retains JSON protocol handling rather than HTML.
        response = client.post("/security-preflight/mcp", headers={"accept": "application/json, text/event-stream"}, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "discovery-test", "version": "1"}}})
        assert response.status_code == 200
        assert "<!doctype html>" not in response.text
        assert "protocolVersion" in response.text
