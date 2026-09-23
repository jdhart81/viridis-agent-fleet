#!/usr/bin/env python3
"""Narrow production overlay for the Reliability Sprint buyer path.

The overlay deliberately delegates every existing gateway path byte-for-byte
to the pinned production application.  It owns only the new human offer page,
the already-reviewed read-only value decision, and crawl discovery files.
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import parse_qs

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response


PUBLIC_HEADERS = {
    "cache-control": "public, max-age=300",
    "content-security-policy": (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
        "form-action 'self' mailto:; frame-ancestors 'none'"
    ),
    "referrer-policy": "strict-origin-when-cross-origin",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
}
DECISION_HEADERS = {
    "cache-control": "no-store",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
}

logger = logging.getLogger("viridis.reliability_sprint")
logger.setLevel(logging.INFO)


def _safe_source(scope: dict) -> str:
    raw = parse_qs(
        scope.get("query_string", b"").decode("ascii", errors="ignore"),
        keep_blank_values=False,
    ).get("source", ["direct"])[0]
    normalized = re.sub(r"[^a-z0-9_-]", "-", raw.lower())[:48]
    return normalized or "direct"


class ReliabilitySprintOverlay:
    """Additive ASGI routes around an exact live-base gateway application."""

    def __init__(self, base_app, *, page_html: str, llms_text: str,
                 public_base: str):
        self.base_app = base_app
        self.page_html = page_html
        self.llms_text = llms_text
        self.public_base = public_base.rstrip("/")

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.base_app(scope, receive, send)
        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()

        if path in {"/reliability-sprint", "/reliability-sprint/"}:
            if method not in {"GET", "HEAD"}:
                response = Response(
                    "method not allowed", status_code=405,
                    headers={**PUBLIC_HEADERS, "allow": "GET, HEAD"},
                    media_type="text/plain",
                )
            else:
                logger.info(
                    "conversion_event offer=reliability-sprint event=view source=%s",
                    _safe_source(scope),
                )
                response = HTMLResponse(
                    "" if method == "HEAD" else self.page_html,
                    headers=PUBLIC_HEADERS,
                )
            return await response(scope, receive, send)

        if path == "/x402/decide":
            if method not in {"GET", "POST"}:
                response = JSONResponse(
                    {"decision": "INVALID_REQUEST", "error": "method not allowed",
                     "money_moved": False, "payment_authorized": False,
                     "tool_executed": False},
                    status_code=405,
                    headers={**DECISION_HEADERS, "allow": "GET, POST"},
                )
            else:
                from value_decision import make_value_decision_route

                handler = make_value_decision_route(self.public_base)
                response = await handler(Request(scope, receive))
                response.headers.update(DECISION_HEADERS)
                try:
                    decision = json.loads(response.body).get("decision", "UNKNOWN")
                except Exception:
                    decision = "UNKNOWN"
                logger.info(
                    "conversion_event offer=reliability-sprint event=fit-check decision=%s",
                    re.sub(r"[^A-Z_]", "", str(decision).upper())[:32],
                )
            return await response(scope, receive, send)

        if path == "/robots.txt" and method in {"GET", "HEAD"}:
            body = (
                "User-agent: *\n"
                "Allow: /\n"
                "Disallow: /internal/\n"
                "Disallow: /seats/checkout\n"
                "Disallow: /seats/success\n"
                "Disallow: /seats/manage\n"
                "Disallow: /compliance-snapshot/checkout\n"
                "Disallow: /compliance-snapshot/success\n"
                f"Sitemap: {self.public_base}/sitemap.xml\n"
            )
            response = PlainTextResponse(
                "" if method == "HEAD" else body, headers=PUBLIC_HEADERS)
            return await response(scope, receive, send)

        if path == "/llms.txt" and method in {"GET", "HEAD"}:
            response = PlainTextResponse(
                "" if method == "HEAD" else self.llms_text,
                headers=PUBLIC_HEADERS,
            )
            return await response(scope, receive, send)

        if path == "/sitemap.xml" and method in {"GET", "HEAD"}:
            escaped = html.escape(self.public_base, quote=True)
            paths = (
                "/agents", "/reliability-sprint", "/quickstart", "/seats",
                "/compliance-snapshot", "/compliance-snapshot/example",
            )
            urls = "".join(
                f"<url><loc>{escaped}{item}</loc></url>" for item in paths)
            body = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"{urls}</urlset>"
            )
            response = Response(
                "" if method == "HEAD" else body,
                headers=PUBLIC_HEADERS,
                media_type="application/xml",
            )
            return await response(scope, receive, send)

        return await self.base_app(scope, receive, send)


_app = None


def get_app():
    global _app
    if _app is None:
        import viridis_mcp_gateway

        gateway_dir = Path(__file__).resolve().parent
        page = (gateway_dir / "reliability_sprint.html").read_text(
            encoding="utf-8")
        llms_intro = (
            gateway_dir / "reliability_sprint_llms_intro.txt").read_text(
                encoding="utf-8").rstrip()
        live_llms = (gateway_dir / "llms.txt").read_text(
            encoding="utf-8").lstrip()
        try:
            from x402_http import intro_enabled
            intro_active = bool(intro_enabled())
        except Exception:
            intro_active = False
        intro_line = (
            "First paid call from every new wallet on eligible "
            "carbon/compliance routes is $0.01 USDC; Hive stays at its fixed "
            "$5.00 price and subsequent eligible calls use the unchanged "
            "list price."
            if intro_active else
            "Intro pricing is currently disabled; list prices apply."
        )
        llms = llms_intro + "\n\n" + live_llms.replace(
            "{{INTRO_STATUS}}", intro_line)
        public_base = os.environ.get(
            "PUBLIC_BASE", "https://mcp.viridisconservation.com")
        _app = ReliabilitySprintOverlay(
            viridis_mcp_gateway.get_app(),
            page_html=page,
            llms_text=llms,
            public_base=public_base,
        )
    return _app


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8402)
    args = parser.parse_args()
    uvicorn.run(get_app(), host=args.host, port=args.port, log_level="warning")
