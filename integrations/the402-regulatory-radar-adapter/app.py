"""Hardened the402 provider adapter for Viridis Regulatory Radar.

The adapter accepts signed the402 provider webhooks, replies once to inbound
service inquiries, fulfills paid Regulatory Radar jobs with the local
deterministic core, and posts the result back to the platform. It never holds a
wallet key, signs a payment, bids on work, or trusts a callback host supplied by
the request.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import importlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Optional

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


MAX_BODY_BYTES = 256 * 1024
MAX_CLOCK_SKEW_SECONDS = 300
THE402_API_HOST = "api.the402.ai"
EVENT_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
CALLBACK_PATH_RE = re.compile(
    r"^/v1/(?:threads|jobs)/[A-Za-z0-9_.:-]{1,160}/"
    r"(?:update|messages)$"
)
VALID_JURISDICTIONS = frozenset(
    {"eu", "uk", "us", "california", "ca", "au", "jp", "sg", "global"}
)
JURISDICTION_ALIASES = {
    "us-ca": "california",
    "ca-us": "california",
}
VALID_SECTORS = frozenset(
    {
        "agriculture",
        "energy",
        "forestry",
        "fisheries",
        "manufacturing",
        "financial_services",
        "consumer_goods",
        "technology",
    }
)


class AdapterError(RuntimeError):
    """Base error whose message is safe to return to the platform."""


class AuthenticationError(AdapterError):
    pass


class InputError(AdapterError):
    pass


class CallbackError(AdapterError):
    pass


@dataclass(frozen=True)
class Config:
    api_key: str
    webhook_secret: str
    state_db: str
    radar_package_root: str
    service_id: str = ""
    api_base: str = "https://api.the402.ai"
    auto_reply: bool = True
    request_timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "Config":
        workspace_root = Path(__file__).resolve().parents[2]
        return cls(
            api_key=os.environ.get("THE402_API_KEY", "").strip(),
            webhook_secret=os.environ.get(
                "THE402_WEBHOOK_SECRET", ""
            ).strip(),
            state_db=os.environ.get(
                "THE402_STATE_DB",
                str(
                    Path(tempfile.gettempdir())
                    / "viridis-the402"
                    / "regulatory-radar-events.sqlite3"
                ),
            ).strip(),
            radar_package_root=os.environ.get(
                "RADAR_PACKAGE_ROOT",
                str(workspace_root / "regulatory-radar-agent"),
            ).strip(),
            service_id=os.environ.get("THE402_SERVICE_ID", "").strip(),
            api_base=os.environ.get(
                "THE402_API_BASE", "https://api.the402.ai"
            ).strip(),
            auto_reply=os.environ.get(
                "THE402_AUTO_REPLY", "1"
            ).strip().lower()
            in {"1", "true", "yes", "on"},
            request_timeout_seconds=float(
                os.environ.get("THE402_REQUEST_TIMEOUT_SECONDS", "10")
            ),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.webhook_secret)


def verify_webhook(
    raw_body: bytes,
    signature: str,
    timestamp: str,
    secret: str,
    *,
    now: Optional[float] = None,
) -> bool:
    """Verify the documented HMAC contract and five-minute replay window."""
    if not raw_body or not signature or not timestamp or not secret:
        return False
    try:
        signed_at = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = time.time() if now is None else now
    if abs(current - signed_at) > MAX_CLOCK_SKEW_SECONDS:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("ascii") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


def _safe_event_id(value: Any, field: str) -> str:
    event_id = str(value or "").strip()
    if not EVENT_ID_RE.fullmatch(event_id):
        raise InputError(f"{field} is missing or invalid")
    return event_id


def event_key(event: Mapping[str, Any]) -> str:
    event_type = str(event.get("type", "")).strip()
    if event_type == "job_dispatch":
        return f"job_dispatch:{_safe_event_id(event.get('job_id'), 'job_id')}"
    if event_type == "thread_inquiry":
        return (
            "thread_inquiry:"
            + _safe_event_id(event.get("thread_id"), "thread_id")
        )
    if event_type == "request.created":
        return (
            "request.created:"
            + _safe_event_id(event.get("posting_id"), "posting_id")
        )
    digest = hashlib.sha256(
        json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24]
    return f"ignored:{event_type or 'unknown'}:{digest}"


def validate_brief(brief: Any) -> dict[str, str]:
    if not isinstance(brief, dict):
        raise InputError("brief must be an object")
    jurisdiction = str(brief.get("jurisdiction", "")).strip().lower()
    jurisdiction = JURISDICTION_ALIASES.get(jurisdiction, jurisdiction)
    sector = str(brief.get("sector", "")).strip().lower()
    query = str(brief.get("query", "")).strip()
    if jurisdiction not in VALID_JURISDICTIONS:
        raise InputError(
            "jurisdiction must be one of " + ", ".join(sorted(VALID_JURISDICTIONS))
        )
    if sector not in VALID_SECTORS:
        raise InputError(
            "sector must be one of " + ", ".join(sorted(VALID_SECTORS))
        )
    if not query or len(query) > 1000:
        raise InputError("query must contain 1 to 1000 characters")
    return {
        "jurisdiction": jurisdiction,
        "sector": sector,
        "query": query,
    }


class EventLedger:
    """Durable event idempotency without storing credentials or full bodies."""

    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_events (
                    event_key TEXT PRIMARY KEY,
                    body_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_json TEXT,
                    attempts INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def reserve(self, key: str, body_sha256: str) -> tuple[str, Optional[dict]]:
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT body_sha256, status, response_json, attempts
                FROM webhook_events WHERE event_key = ?
                """,
                (key,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO webhook_events
                    (event_key, body_sha256, status, created_at, updated_at)
                    VALUES (?, ?, 'processing', ?, ?)
                    """,
                    (key, body_sha256, now, now),
                )
                return "new", None
            prior_sha, status, response_json, attempts = row
            if prior_sha != body_sha256:
                return "conflict", None
            if status == "completed":
                prior = json.loads(response_json) if response_json else {}
                return "replay", prior
            if status == "failed":
                connection.execute(
                    """
                    UPDATE webhook_events
                    SET status = 'processing', attempts = ?, updated_at = ?
                    WHERE event_key = ?
                    """,
                    (attempts + 1, now, key),
                )
                return "new", None
            return "processing", None

    def complete(self, key: str, response: Mapping[str, Any]) -> None:
        encoded = json.dumps(
            dict(response), sort_keys=True, separators=(",", ":")
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE webhook_events
                SET status = 'completed', response_json = ?, updated_at = ?
                WHERE event_key = ?
                """,
                (encoded, int(time.time()), key),
            )

    def fail(self, key: str, error_type: str) -> None:
        safe = json.dumps({"status": "failed", "error_type": error_type})
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE webhook_events
                SET status = 'failed', response_json = ?, updated_at = ?
                WHERE event_key = ?
                """,
                (safe, int(time.time()), key),
            )


class RadarRunner:
    """Load the existing Regulatory Radar package under an isolated namespace."""

    def __init__(self, package_root: str):
        source_dir = Path(package_root).resolve() / "src"
        init_file = source_dir / "__init__.py"
        if not init_file.is_file():
            raise RuntimeError("Regulatory Radar package is unavailable")
        package_name = "_viridis_the402_regulatory_radar"
        if package_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                package_name,
                init_file,
                submodule_search_locations=[str(source_dir)],
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Regulatory Radar package cannot be loaded")
            module = importlib.util.module_from_spec(spec)
            sys.modules[package_name] = module
            spec.loader.exec_module(module)
        core_module = importlib.import_module(f"{package_name}.core")
        self.core = core_module.RegulatoryRadarCore()

    async def health(self) -> dict:
        return await self.core.health()

    async def scan(self, brief: Mapping[str, str]) -> dict:
        result = await self.core.process({"action": "scan", **dict(brief)})
        if not isinstance(result, dict) or result.get("status") == "error":
            raise AdapterError("Regulatory Radar refused the submitted brief")
        return {
            "service": "Viridis Regulatory Radar",
            "request": dict(brief),
            "regulatory_scan": result,
            "quickstart": "https://mcp.viridisconservation.com/quickstart",
            "source": "https://github.com/jdhart81/viridis-agent-fleet",
            "claim_boundary": (
                "Regulatory screening, not legal, tax, or filing advice."
            ),
        }


def validate_callback_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(str(url or ""))
    if (
        parsed.scheme != "https"
        or parsed.hostname != THE402_API_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or not CALLBACK_PATH_RE.fullmatch(parsed.path)
        or parsed.query
        or parsed.fragment
    ):
        raise CallbackError("callback URL is outside the allowed the402 API")
    return urllib.parse.urlunsplit(
        ("https", THE402_API_HOST, parsed.path, "", "")
    )


class PlatformClient:
    def __init__(self, config: Config):
        self.api_key = config.api_key
        self.api_base = config.api_base.rstrip("/")
        self.timeout = config.request_timeout_seconds
        parsed = urllib.parse.urlsplit(self.api_base)
        if parsed.scheme != "https" or parsed.hostname != THE402_API_HOST:
            raise RuntimeError("THE402_API_BASE must be the official HTTPS API")

    async def _post(self, url: str, payload: Mapping[str, Any]) -> dict:
        safe_url = validate_callback_url(url)
        data = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")

        def send() -> dict:
            request = urllib.request.Request(
                safe_url,
                data=data,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": self.api_key,
                    "User-Agent": "Viridis-the402-adapter/1.0",
                },
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout
                ) as response:
                    raw = response.read(1024 * 1024)
            except (urllib.error.URLError, TimeoutError) as exc:
                raise CallbackError("the402 callback failed") from exc
            if not raw:
                return {}
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            return value if isinstance(value, dict) else {}

        return await asyncio.to_thread(send)

    async def complete_job(self, event: Mapping[str, Any], result: dict) -> dict:
        callback_url = validate_callback_url(str(event.get("callback_url", "")))
        return await self._post(
            callback_url,
            {
                "status": "completed",
                "deliverables": result,
                "notes": (
                    "Deterministic Viridis Regulatory Radar scan completed."
                ),
            },
        )

    async def fail_job(self, event: Mapping[str, Any], reason: str) -> dict:
        callback_url = validate_callback_url(str(event.get("callback_url", "")))
        return await self._post(
            callback_url,
            {
                "status": "failed",
                "notes": str(reason)[:300],
            },
        )

    async def reply_to_inquiry(self, thread_id: str) -> dict:
        safe_thread = _safe_event_id(thread_id, "thread_id")
        url = f"{self.api_base}/v1/threads/{safe_thread}/messages"
        return await self._post(
            url,
            {
                "message": (
                    "Thanks for contacting Viridis Regulatory Radar. The "
                    "listed service price is $0.25; the402 displays any "
                    "applicable platform fee. The scan accepts three fields: "
                    "jurisdiction, sector, "
                    "and the compliance question. It returns deterministic "
                    "regulatory screening with source links and clearly "
                    "separates binding requirements from voluntary frameworks. "
                    "It is screening, not legal or filing advice. Quickstart: "
                    "https://mcp.viridisconservation.com/quickstart"
                )
            },
        )


class WebhookService:
    def __init__(
        self,
        config: Config,
        ledger: EventLedger,
        runner: Any,
        platform: Any,
        *,
        now: Callable[[], float] = time.time,
    ):
        self.config = config
        self.ledger = ledger
        self.runner = runner
        self.platform = platform
        self.now = now

    def _authenticate(self, raw_body: bytes, headers: Mapping[str, str]) -> None:
        if not self.config.configured:
            raise AuthenticationError("adapter credentials are not configured")
        platform_secret = headers.get("x-platform-secret", "")
        if not hmac.compare_digest(platform_secret, self.config.api_key):
            raise AuthenticationError("invalid platform secret")
        if not verify_webhook(
            raw_body,
            headers.get("x-webhook-signature", ""),
            headers.get("x-webhook-timestamp", ""),
            self.config.webhook_secret,
            now=self.now(),
        ):
            raise AuthenticationError("invalid or stale webhook signature")

    def _validate_service(self, event: Mapping[str, Any]) -> None:
        if not self.config.service_id:
            return
        if str(event.get("service_id", "")).strip() != self.config.service_id:
            raise InputError("event service_id is not the configured service")

    async def handle(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> tuple[int, dict]:
        self._authenticate(raw_body, headers)
        try:
            event = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise InputError("webhook body must be valid JSON") from exc
        if not isinstance(event, dict):
            raise InputError("webhook body must be a JSON object")
        key = event_key(event)
        body_sha = hashlib.sha256(raw_body).hexdigest()
        reservation, prior = self.ledger.reserve(key, body_sha)
        if reservation == "conflict":
            return 409, {"status": "error", "error": "idempotency conflict"}
        if reservation == "replay":
            return 200, {**(prior or {}), "idempotent_replay": True}
        if reservation == "processing":
            return 202, {"status": "processing", "idempotent": True}

        event_type = str(event.get("type", "")).strip()
        try:
            if event_type == "job_dispatch":
                self._validate_service(event)
                brief = validate_brief(event.get("brief"))
                result = await self.runner.scan(brief)
                await self.platform.complete_job(event, result)
                response = {
                    "status": "completed",
                    "event": event_type,
                    "job_id": str(event.get("job_id")),
                }
            elif event_type == "thread_inquiry":
                self._validate_service(event)
                thread_id = _safe_event_id(event.get("thread_id"), "thread_id")
                if self.config.auto_reply:
                    await self.platform.reply_to_inquiry(thread_id)
                response = {
                    "status": "accepted",
                    "event": event_type,
                    "thread_id": thread_id,
                    "replied": self.config.auto_reply,
                }
            elif event_type == "request.created":
                response = {
                    "status": "ignored",
                    "event": event_type,
                    "reason": "automatic bidding is disabled",
                }
            else:
                response = {
                    "status": "ignored",
                    "event": event_type or "unknown",
                    "reason": "unsupported signed event",
                }
            self.ledger.complete(key, response)
            return 200, response
        except InputError as exc:
            if event_type == "job_dispatch":
                try:
                    await self.platform.fail_job(event, str(exc))
                except CallbackError:
                    self.ledger.fail(key, "callback_error")
                    raise
            response = {
                "status": "failed",
                "event": event_type,
                "reason": str(exc),
            }
            self.ledger.complete(key, response)
            return 200, response
        except CallbackError:
            self.ledger.fail(key, "callback_error")
            raise
        except Exception as exc:
            self.ledger.fail(key, type(exc).__name__)
            raise AdapterError("webhook processing failed") from exc


def create_app(
    config: Optional[Config] = None,
    *,
    ledger: Optional[EventLedger] = None,
    runner: Any = None,
    platform: Any = None,
) -> Starlette:
    settings = config or Config.from_env()
    event_ledger = ledger or EventLedger(settings.state_db)
    radar_runner = runner or RadarRunner(settings.radar_package_root)
    platform_client = platform or PlatformClient(settings)
    service = WebhookService(
        settings, event_ledger, radar_runner, platform_client
    )

    async def health(_: Request) -> JSONResponse:
        radar_health: dict[str, Any]
        try:
            radar_health = await radar_runner.health()
        except Exception:
            radar_health = {"status": "error"}
        ready = settings.configured and radar_health.get("status") == "ok"
        return JSONResponse(
            {
                "status": "ok" if ready else "degraded",
                "service": "viridis-the402-regulatory-radar-adapter",
                "configured": settings.configured,
                "radar": radar_health.get("status", "error"),
                "automatic_bidding": False,
                "money_movement": False,
            }
        )

    async def webhook(request: Request) -> JSONResponse:
        raw_body = await request.body()
        if len(raw_body) > MAX_BODY_BYTES:
            return JSONResponse(
                {"status": "error", "error": "body too large"},
                status_code=413,
            )
        headers = {key.lower(): value for key, value in request.headers.items()}
        try:
            status_code, payload = await service.handle(raw_body, headers)
        except AuthenticationError as exc:
            code = 503 if not settings.configured else 401
            return JSONResponse(
                {"status": "error", "error": str(exc)}, status_code=code
            )
        except InputError as exc:
            return JSONResponse(
                {"status": "error", "error": str(exc)}, status_code=400
            )
        except CallbackError as exc:
            return JSONResponse(
                {"status": "error", "error": str(exc)}, status_code=502
            )
        except AdapterError as exc:
            return JSONResponse(
                {"status": "error", "error": str(exc)}, status_code=500
            )
        return JSONResponse(payload, status_code=status_code)

    return Starlette(
        routes=[
            Route("/integrations/the402/healthz", health, methods=["GET"]),
            Route(
                "/integrations/the402/webhook", webhook, methods=["POST"]
            ),
        ]
    )


app = create_app()
