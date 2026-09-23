"""Opt-in ASGI reference guard. Not mounted on production by discovery flags.

The identity callback is trusted server code returning a stable subject string.
It must authenticate credentials/session state and enforce per-subject quotas.
No entitlement or identity is taken directly from client headers here.
"""
import json
from .defense import MAX_BODY, binding


class MaxwellMiddleware:
    def __init__(self, app, *, guard, tenant, paths, identity):
        self.app, self.guard, self.tenant = app, guard, tenant
        self.paths, self.identity = frozenset(paths), identity

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] not in self.paths:
            return await self.app(scope, receive, send)

        async def reply(status, body):
            data = json.dumps(body).encode()
            await send({"type": "http.response.start", "status": status,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": data})

        subject = await self.identity(scope)
        if not isinstance(subject, str) or not 1 <= len(subject) <= 512:
            return await reply(401, {"error": "server-verified identity required"})
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > MAX_BODY:
                return await reply(413, {"error": "body too large"})
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        # Bind the raw URL path and query without normalization.
        target = (scope.get("raw_path", scope["path"].encode())
                  + b"?" + scope.get("query_string", b"")).hex()
        try:
            digest = binding(self.tenant, subject, scope["method"], target, bytes(body))
        except ValueError:
            return await reply(400, {"error": "request binding too large"})
        headers = scope.get("headers", [])
        tokens = [v for k, v in headers if k.lower() == b"x-maxwell-token"]
        nonces = [v for k, v in headers if k.lower() == b"x-maxwell-nonce"]
        if len(tokens) > 1 or len(nonces) > 1:
            return await reply(400, {"error": "duplicate proof headers"})
        if not tokens and not nonces:
            challenge = self.guard.issue(digest)
            return await reply(503 if challenge.get("status") == "busy" else 429,
                               {"maxwell": challenge, "payment_required": False})
        result = self.guard.verify(tokens[0].decode("latin1") if tokens else "",
                                   nonces[0].decode("latin1") if nonces else "", digest)
        if not result["admitted"]:
            return await reply(503 if result["reason"] in {"busy", "capacity", "store_unavailable"} else 403, result)
        replayed_body = False

        async def forward():
            nonlocal replayed_body
            if not replayed_body:
                replayed_body = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        # Proof grants one admission only; the downstream app still authorizes
        # and settles payment. A solution does not buy the protected service.
        return await self.app(scope, forward, send)
