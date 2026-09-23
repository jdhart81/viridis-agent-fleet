import json
import sys
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from request_limits import RequestLimitsMiddleware


async def echo(request):
    return JSONResponse(await request.json())


def client(limit=1_000_000):
    app = Starlette(routes=[Route("/echo", echo, methods=["POST"])])
    return TestClient(RequestLimitsMiddleware(app, max_body_bytes=limit))


def test_valid_json_reaches_downstream_unchanged():
    with client() as test_client:
        response = test_client.post("/echo", json={"value": 12.5})
    assert response.status_code == 200
    assert response.json() == {"value": 12.5}


def test_content_length_above_limit_is_rejected():
    with client(limit=10) as test_client:
        response = test_client.post(
            "/echo", content=json.dumps({"value": "too large"}),
            headers={"content-type": "application/json"})
    assert response.status_code == 413
    assert response.json()["error_type"] == "request_body_too_large"


def test_exponent_overflow_is_rejected_before_agent_dispatch():
    with client() as test_client:
        response = test_client.post(
            "/echo", content='{"value":1e999}',
            headers={"content-type": "application/json"})
    assert response.status_code == 400
    assert response.json()["error_type"] == "non_finite_number"


def test_nonstandard_nan_and_infinity_are_rejected():
    with client() as test_client:
        for token in ("NaN", "Infinity", "-Infinity"):
            response = test_client.post(
                "/echo", content=f'{{"value":{token}}}',
                headers={"content-type": "application/json"})
            assert response.status_code == 400
            assert response.json()["error_type"] == "non_finite_number"


def test_edge_and_gateway_limits_are_both_release_artifacts():
    caddy = (HERE.parent / "droplet" / "Caddyfile").read_text()
    dockerfile = (HERE / "Dockerfile").read_text()
    gateway = (HERE / "viridis_mcp_gateway.py").read_text()
    assert "max_size 1MB" in caddy
    assert "COPY deploy/gateway/request_limits.py" in dockerfile
    assert "RequestLimitsMiddleware" in gateway
