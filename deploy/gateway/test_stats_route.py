"""Smoke test: the gateway serves the usage-statistics dashboard at /stats
(baked-file pattern, same as /deck) without disturbing existing routes."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def test_stats_route_served_and_deck_unchanged():
    from starlette.testclient import TestClient
    import viridis_mcp_gateway as gw
    app = gw.build_app()
    with TestClient(app) as client:
        r = client.get("/stats")
        assert r.status_code == 200
        assert "USAGE STATISTICS" in r.text
        assert "usage_timeseries" in r.text          # calls the v0.2.0 tools
        assert "reconcile_revenue" in r.text
        # Existing observability surface intact.
        assert client.get("/deck").status_code == 200
        h = client.get("/healthz")
        assert h.status_code in (200, 503) and "agents" in h.text
