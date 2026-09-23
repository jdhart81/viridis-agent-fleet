import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp_initialize_recovery import MCPInitializeRecoveryMiddleware


def _scope():
    return {
        "type": "http", "method": "POST", "path": "/offsets/mcp",
        "headers": [(b"content-type", b"application/json")],
    }


def _initialize():
    return json.dumps({
        "jsonrpc": "2.0",
        "id": 7,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    }).encode()


def _run(app, body=None):
    sent = []
    first = True

    async def receive():
        nonlocal first
        if first:
            first = False
            return {"type": "http.request", "body": body or _initialize(),
                    "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(MCPInitializeRecoveryMiddleware(app)(
        _scope(), receive, send))
    return sent


def _response(sent):
    status = next(m["status"] for m in sent
                  if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent
                    if m["type"] == "http.response.body")
    return status, body


def test_valid_initialize_response_passes_through_unchanged():
    original = json.dumps({
        "jsonrpc": "2.0", "id": 7,
        "result": {"protocolVersion": "2025-03-26", "capabilities": {}},
    }).encode()

    async def app(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": original})

    status, body = _response(_run(app))
    assert status == 200
    assert body == original


def test_empty_http_200_is_recovered_to_parseable_initialize():
    async def app(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/event-stream")]})
        await send({"type": "http.response.body", "body": b""})

    sent = _run(app)
    status, body = _response(sent)
    payload = json.loads(body)
    assert status == 200
    assert payload["id"] == 7
    assert payload["result"]["protocolVersion"] == "2025-03-26"
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert (b"x-viridis-initialize-recovered", b"1") in start["headers"]


def test_non_initialize_request_is_not_intercepted():
    body = json.dumps({
        "jsonrpc": "2.0", "id": 2, "method": "tools/list",
    }).encode()

    async def app(scope, receive, send):
        request = await receive()
        assert request["body"] == body
        await send({"type": "http.response.start", "status": 418,
                    "headers": []})
        await send({"type": "http.response.body", "body": b"teapot"})

    status, response_body = _response(_run(app, body))
    assert status == 418
    assert response_body == b"teapot"
