#!/usr/bin/env python3
"""Autonomous, auditable fleet distribution with isolated credentials.

FA-B1..B6:
- Reads current route/pricing/conversion facts from the live gateway health.
- Generates content from that snapshot instead of carrying price copy.
- Writes an immutable outbound attempt before any posting API call.
- Enforces target policy clearance and per-target cooldowns.
- Appends conversion observations and reweights future target selection.
- Defaults OFF and never reads payment-gateway credential names.

This process is a separate deploy unit. It has no import path to the payment
gateway and no adapter capable of moving money.
"""
from __future__ import annotations

import hashlib
import base64
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional


DEFAULT_HEALTH_URL = "https://mcp.viridisconservation.com/healthz"
DEFAULT_MARKET_CATALOG_URL = (
    "https://mcp.viridisconservation.com/network/catalog")
DEFAULT_COOLDOWN_DAYS = 14
DEFAULT_FEEDBACK_WINDOW_DAYS = 7
DEFAULT_OPENAI_MODEL = "gpt-5.6-terra"
DEFAULT_OPENAI_MONTHLY_BUDGET_USD = Decimal("20.00")
DEFAULT_OPENAI_CALL_RESERVE_USD = Decimal("0.05")
DEFAULT_OPENAI_MAX_OUTPUT_TOKENS = 700
MAX_OPENAI_PROMPT_CHARS = 12_000
TRUTHY = frozenset({"1", "true", "yes", "on"})

# FA-I6: posting adapters receive only these credentials. The model key is
# isolated from adapters just as the entire process is isolated from money.
POSTING_CREDENTIAL_ENV = frozenset({
    "GROWTH_DISCORD_BOT_TOKEN",
    "GROWTH_GITHUB_APP_ID",
    "GROWTH_GITHUB_INSTALLATION_ID",
    "GROWTH_GITHUB_PRIVATE_KEY_PATH",
    "GROWTH_SMITHERY_API_KEY",
})
MODEL_CREDENTIAL_ENV = frozenset({"GROWTH_OPENAI_API_KEY"})
ALLOWED_CREDENTIAL_ENV = POSTING_CREDENTIAL_ENV
ALLOWED_GROWTH_CREDENTIAL_ENV = (
    POSTING_CREDENTIAL_ENV | MODEL_CREDENTIAL_ENV
)

# Official GPT-5.6 Terra rates on 2026-07-20, expressed per 1M tokens.
# The harness refuses a different model so its hard budget remains honest.
TERRA_INPUT_USD_PER_M = Decimal("2.50")
TERRA_CACHED_INPUT_USD_PER_M = Decimal("0.25")
TERRA_OUTPUT_USD_PER_M = Decimal("15.00")

CHAIN_ORDER = (
    "quantity-takeoff/calculate_takeoff",
    "ghg-ledger/calculate_inventory",
    "disclosure-compiler/compile_disclosure",
    "taxcredit-engine/calculate_tax_credit",
    "regulatory-radar/scan_regulations",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _enabled(value: Any) -> bool:
    return str(value or "").strip().lower() in TRUTHY


class GrowthError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class GeneratedCopy:
    content: str
    strategy: str
    usage: ModelUsage
    model: str


@dataclass(frozen=True)
class FleetSnapshot:
    routes: tuple[dict, ...]
    metrics: dict
    route_metrics: dict
    intro_enabled: bool
    agents_url: str
    quickstart_url: str
    captured_at: str
    market_url: str = ""
    open_work: tuple[dict, ...] = ()

    @classmethod
    def from_health(cls, health: dict, *, captured_at: str) -> "FleetSnapshot":
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise GrowthError("live fleet health is not ok")
        payment_gate = health.get("payment_gate")
        x402 = payment_gate.get("x402") if isinstance(payment_gate, dict) else None
        if not isinstance(x402, dict) or x402.get("enabled") is not True:
            raise GrowthError("live x402 rail is not enabled")
        raw_routes = x402.get("http_front_door")
        telemetry = x402.get("http_settlement_telemetry")
        total = telemetry.get("total") if isinstance(telemetry, dict) else None
        per_route = (telemetry.get("per_route")
                     if isinstance(telemetry, dict) else None)
        if not isinstance(raw_routes, list) or not raw_routes:
            raise GrowthError("live x402 route inventory is missing")
        required_metrics = {
            "settlements_total", "external_settlements",
            "distinct_external_payers", "external_revenue_atomic",
            "first_external_settlement",
        }
        if not isinstance(total, dict) or not required_metrics.issubset(total):
            raise GrowthError("live x402 conversion metrics are incomplete")
        if not isinstance(per_route, dict):
            raise GrowthError("live x402 route conversion metrics are missing")
        routes = []
        for item in raw_routes:
            if not isinstance(item, dict):
                raise GrowthError("invalid route inventory entry")
            required = {"agent", "tool", "endpoint", "price_minor",
                        "amount_atomic_usdc", "description"}
            if not required.issubset(item):
                raise GrowthError("route inventory entry is incomplete")
            if (isinstance(item["price_minor"], bool)
                    or not isinstance(item["price_minor"], int)
                    or item["price_minor"] < 0):
                raise GrowthError("route price is invalid")
            routes.append(dict(item))
        order = {name: idx for idx, name in enumerate(CHAIN_ORDER)}
        routes.sort(key=lambda r: order.get(
            f"{r['agent']}/{r['tool']}", len(order)))
        surfaces = health.get("human_surfaces") or {}
        return cls(
            routes=tuple(routes), metrics=dict(total),
            route_metrics={str(key): dict(value)
                           for key, value in per_route.items()
                           if isinstance(value, dict)},
            intro_enabled=bool((x402.get("intro_pricing") or {}).get("enabled")),
            agents_url=str(surfaces.get("agents") or
                           "https://mcp.viridisconservation.com/agents"),
            quickstart_url=str(surfaces.get("quickstart") or
                               "https://mcp.viridisconservation.com/quickstart"),
            captured_at=captured_at,
        )

    def signature(self) -> str:
        body = json.dumps({"routes": self.routes, "metrics": self.metrics,
                           "route_metrics": self.route_metrics,
                           "intro": self.intro_enabled,
                           "market_url": self.market_url,
                           "open_work": self.open_work}, sort_keys=True,
                          separators=(",", ":"))
        return hashlib.sha256(body.encode()).hexdigest()


class LiveFleetClient:
    def __init__(self, health_url: str = DEFAULT_HEALTH_URL,
                 market_catalog_url: str = "",
                 opener: Callable[..., Any] = urllib.request.urlopen):
        self.health_url = str(health_url)
        self.market_catalog_url = str(market_catalog_url or "")
        self.opener = opener

    def _read_json(self, url: str, *, label: str) -> dict:
        request = urllib.request.Request(
            url, headers={"Accept": "application/json",
                          "User-Agent": "viridis-growth-agent/1"})
        try:
            with self.opener(request, timeout=10) as response:
                status = int(getattr(response, "status", 200))
                payload = response.read(2_000_000)
        except Exception as exc:
            raise GrowthError(f"live {label} read failed: {type(exc).__name__}") \
                from exc
        if status != 200:
            raise GrowthError(f"live {label} returned HTTP {status}")
        try:
            result = json.loads(payload)
        except (TypeError, ValueError) as exc:
            raise GrowthError(f"live {label} is not JSON") from exc
        if not isinstance(result, dict):
            raise GrowthError(f"live {label} is not an object")
        return result

    def fetch(self, *, now: datetime) -> FleetSnapshot:
        separator = "&" if "?" in self.health_url else "?"
        url = f"{self.health_url}{separator}growth_ts={int(now.timestamp())}"
        health = self._read_json(url, label="fleet health")
        snapshot = FleetSnapshot.from_health(health, captured_at=_iso(now))
        if not self.market_catalog_url:
            return snapshot
        market_url = self.market_catalog_url
        try:
            separator = "&" if "?" in market_url else "?"
            market = self._read_json(
                f"{market_url}{separator}growth_ts={int(now.timestamp())}",
                label="agent market catalog")
            raw_work = market.get("open_work") or []
            jobs = []
            for item in raw_work:
                if not isinstance(item, dict):
                    continue
                required = {"work_id", "title", "budget_minor", "currency"}
                if not required.issubset(item):
                    continue
                budget = int(item["budget_minor"])
                if budget <= 0 or str(item["currency"]).upper() != "USD":
                    continue
                jobs.append({key: item.get(key) for key in (
                    "work_id", "title", "description", "budget_minor",
                    "currency", "required_capabilities", "delivery_deadline")})
            jobs.sort(key=lambda item: (-int(item["budget_minor"]),
                                        str(item["work_id"])))
            return FleetSnapshot(
                routes=snapshot.routes, metrics=snapshot.metrics,
                route_metrics=snapshot.route_metrics,
                intro_enabled=snapshot.intro_enabled,
                agents_url=snapshot.agents_url,
                quickstart_url=snapshot.quickstart_url,
                captured_at=snapshot.captured_at,
                market_url=market_url.split("?", 1)[0],
                open_work=tuple(jobs[:10]))
        except GrowthError:
            # Route promotion remains safe and live if the independent market
            # process is temporarily unavailable. No stale jobs are claimed.
            return snapshot


class OutboundLog:
    """SQLite append-only event log; UPDATE and DELETE are denied by trigger."""

    def __init__(self, path: str):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS outbound_log (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            event_type TEXT NOT NULL,
            attempt_id TEXT,
            target_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            content TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS outbound_log_no_update
        BEFORE UPDATE ON outbound_log BEGIN
            SELECT RAISE(ABORT, 'outbound_log is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS outbound_log_no_delete
        BEFORE DELETE ON outbound_log BEGIN
            SELECT RAISE(ABORT, 'outbound_log is append-only');
        END;
        """)
        self.conn.commit()

    def append(self, event_type: str, target: dict, content: str,
               payload: dict, *, occurred_at: datetime,
               attempt_id: str = "") -> str:
        event_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO outbound_log(event_id,event_type,attempt_id,target_id,"
            "channel,content,occurred_at,payload_json) VALUES(?,?,?,?,?,?,?,?)",
            (event_id, event_type, attempt_id, str(target["id"]),
             str(target.get("channel") or target.get("target") or ""),
             str(content), _iso(occurred_at),
             json.dumps(payload, sort_keys=True, separators=(",", ":"))))
        self.conn.commit()
        return event_id

    def entries(self, event_type: str = "") -> list[dict]:
        query = "SELECT * FROM outbound_log"
        args: tuple = ()
        if event_type:
            query += " WHERE event_type=?"
            args = (event_type,)
        query += " ORDER BY seq"
        rows = self.conn.execute(query, args).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            out.append(item)
        return out

    def observed_attempt_ids(self) -> set[str]:
        return {str(row["attempt_id"]) for row in
                self.entries("outcome_observation") if row.get("attempt_id")}

    def last_success_at(self, target_id: str) -> Optional[datetime]:
        rows = [row for row in self.entries("send_result")
                if row["target_id"] == target_id
                and row["payload"].get("success") is True]
        return _parse_iso(rows[-1]["occurred_at"]) if rows else None

    def monthly_llm_cost_microusd(self, now: datetime) -> int:
        month = now.astimezone(timezone.utc).strftime("%Y-%m")
        return sum(
            max(int(row["payload"].get("cost_microusd") or 0), 0)
            for row in self.entries("llm_result")
            if str(row["occurred_at"]).startswith(month)
        )


def load_targets(path: str) -> list[dict]:
    try:
        payload = json.loads(Path(path).read_text())
    except Exception as exc:
        raise GrowthError(f"target configuration unavailable: {type(exc).__name__}") \
            from exc
    if not isinstance(payload, list) or not payload:
        raise GrowthError("target configuration must be a non-empty list")
    ids = set()
    targets = []
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise GrowthError("invalid target entry")
        if item["id"] in ids:
            raise GrowthError(f"duplicate target id: {item['id']}")
        ids.add(item["id"])
        target = dict(item)
        target.setdefault("cooldown_days", DEFAULT_COOLDOWN_DAYS)
        target.setdefault("base_weight", 1.0)
        targets.append(target)
    return targets


def _money(price_minor: int) -> str:
    return f"${price_minor / 100:.2f}"


def render_content(snapshot: FleetSnapshot) -> str:
    # When paid work is available, reserve the finite posting budget for the
    # exact job ids/budgets agents need in order to act. Route descriptions are
    # still sourced and validated elsewhere, but repeating five long product
    # descriptions alongside three jobs can exceed Discord's safe limit.
    compact_routes = bool(snapshot.open_work and snapshot.market_url)
    lines = [
        "Live x402 carbon + compliance agent workflow on Base:",
        "measure → account → disclose → claim → scan", "",
    ]
    for route in snapshot.routes:
        route_line = f"• {route['agent']} — {_money(route['price_minor'])}"
        if not compact_routes:
            route_line += f": {route['description']}"
        lines.append(route_line)
    lines.extend(["", "No signup or API key. A caller receives HTTP 402, "
                  "settles Base USDC, and gets the deterministic result."])
    if snapshot.intro_enabled:
        lines.append("First paid call from a new wallet is $0.01.")
    external = int(snapshot.metrics.get("external_settlements") or 0)
    payers = int(snapshot.metrics.get("distinct_external_payers") or 0)
    if external:
        lines.append(f"Live external proof: {external} settlement(s) from "
                     f"{payers} distinct payer(s).")
    if snapshot.open_work and snapshot.market_url:
        lines.extend(["", "Open paid work for outside agents:"])
        for job in snapshot.open_work[:3]:
            title = str(job["title"]).strip()
            if len(title) > 96:
                title = title[:93].rstrip() + "..."
            lines.append(
                f"• {_money(int(job['budget_minor']))} — {title} "
                f"({job['work_id']})")
        lines.append(f"Discover and bid: {snapshot.market_url}")
    lines.extend(["", f"Free dry-run: {snapshot.quickstart_url}",
                  f"Agent suite: {snapshot.agents_url}"])
    content = "\n".join(lines)
    if len(content) > 1900:
        raise GrowthError("generated content exceeds safe Discord length")
    return content


def metrics_for_target(snapshot: FleetSnapshot, target: dict) -> tuple[str, dict]:
    """Return the narrowest live conversion bucket a target can influence.

    Owned listings point at one x402 route. Suite-wide surfaces intentionally
    use `*` and observe the total. Unknown route declarations fail closed
    instead of quietly crediting unrelated fleet revenue.
    """
    scope = str(target.get("route") or "").strip()
    if scope == "*":
        return scope, dict(snapshot.metrics)
    if not scope:
        raise GrowthError("target is missing an attribution route")
    metrics = snapshot.route_metrics.get(scope)
    if not isinstance(metrics, dict):
        raise GrowthError(f"target attribution route is not live: {scope}")
    return scope, dict(metrics)


def _usd_to_microusd(value: Any, *, default: Decimal) -> int:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        parsed = default
    if parsed < 0:
        raise GrowthError("growth model budget values cannot be negative")
    return int((parsed * Decimal("1000000")).to_integral_value(
        rounding=ROUND_CEILING))


def _usage_cost_microusd(usage: ModelUsage) -> int:
    cached = min(max(int(usage.cached_input_tokens), 0),
                 max(int(usage.input_tokens), 0))
    uncached = max(int(usage.input_tokens), 0) - cached
    cost = (
        Decimal(uncached) * TERRA_INPUT_USD_PER_M
        + Decimal(cached) * TERRA_CACHED_INPUT_USD_PER_M
        + Decimal(max(int(usage.output_tokens), 0)) * TERRA_OUTPUT_USD_PER_M
    )
    # Per-million token pricing converts directly to micro-USD per token.
    return int(cost.to_integral_value(rounding=ROUND_CEILING))


def validate_generated_content(content: str, snapshot: FleetSnapshot) -> str:
    candidate = str(content or "").strip()
    if not candidate or len(candidate) > 1900:
        raise GrowthError("model copy is empty or exceeds the posting limit")
    required_prices = set()
    for route in snapshot.routes:
        price = _money(int(route["price_minor"]))
        required_prices.add(price)
        if str(route["agent"]) not in candidate or price not in candidate:
            raise GrowthError("model copy omitted a route or exact live price")
    for url in (snapshot.quickstart_url, snapshot.agents_url):
        if url not in candidate:
            raise GrowthError("model copy omitted a required live URL")
    if snapshot.open_work and snapshot.market_url:
        if snapshot.market_url not in candidate:
            raise GrowthError("model copy omitted the live agent market URL")
        for job in snapshot.open_work[:3]:
            price = _money(int(job["budget_minor"]))
            required_prices.add(price)
            if str(job["work_id"]) not in candidate or price not in candidate:
                raise GrowthError("model copy altered or omitted an open job")
    intro_line = "First paid call from a new wallet is $0.01."
    if snapshot.intro_enabled:
        required_prices.add("$0.01")
        if intro_line not in candidate:
            raise GrowthError("model copy omitted the active intro offer")
    elif "$0.01" in candidate or "first paid call" in candidate.lower():
        raise GrowthError("model copy invented an inactive intro offer")
    external = int(snapshot.metrics.get("external_settlements") or 0)
    payers = int(snapshot.metrics.get("distinct_external_payers") or 0)
    if external:
        proof = (f"Live external proof: {external} settlement(s) from "
                 f"{payers} distinct payer(s).")
        if proof not in candidate:
            raise GrowthError("model copy altered live conversion proof")
    found_prices = set(re.findall(r"\$[0-9]+\.[0-9]{2}", candidate))
    if found_prices != required_prices:
        raise GrowthError("model copy introduced or omitted a dollar amount")
    forbidden = (
        "guaranteed compliance", "guarantees compliance",
        "certified compliant", "legal advice", "investment advice",
    )
    lowered = candidate.lower()
    if any(phrase in lowered for phrase in forbidden):
        raise GrowthError("model copy introduced a prohibited claim")
    if "x402" not in lowered or "base" not in lowered or "usdc" not in lowered:
        raise GrowthError("model copy omitted the payment rail")
    return candidate


class OpenAIGrowthHarness:
    """One grounded OpenAI agent for copy framing, never for side effects."""

    def __init__(self, *, environ: Optional[dict] = None):
        self.environ = dict(os.environ if environ is None else environ)

    @property
    def model(self) -> str:
        model = str(self.environ.get("GROWTH_OPENAI_MODEL") or
                    DEFAULT_OPENAI_MODEL).strip()
        if model != DEFAULT_OPENAI_MODEL:
            raise GrowthError(
                "growth harness only permits gpt-5.6-terra under this budget")
        return model

    def generate(self, snapshot: FleetSnapshot, target: dict,
                 deterministic_content: str) -> GeneratedCopy:
        api_key = str(self.environ.get("GROWTH_OPENAI_API_KEY") or "")
        if not api_key:
            raise GrowthError("growth OpenAI credential is missing")
        try:
            from agents import (
                Agent, ModelRetrySettings, ModelSettings, OpenAIProvider,
                RunConfig, Runner,
            )
            from openai.types.shared import Reasoning
            from pydantic import BaseModel, Field
        except ImportError as exc:
            raise GrowthError("OpenAI Agents SDK is unavailable") from exc

        class GrowthCopyOutput(BaseModel):
            content: str = Field(min_length=1, max_length=1900)
            strategy: str = Field(min_length=1, max_length=280)

        facts = {
            "target": {
                "id": target.get("id"),
                "platform": target.get("platform"),
                "channel": target.get("channel"),
            },
            "routes": list(snapshot.routes),
            "conversion_metrics": snapshot.metrics,
            "intro_enabled": snapshot.intro_enabled,
            "agents_url": snapshot.agents_url,
            "quickstart_url": snapshot.quickstart_url,
            "market_url": snapshot.market_url,
            "open_work": list(snapshot.open_work),
            "required_factual_copy": deterministic_content,
        }
        prompt = json.dumps(facts, sort_keys=True, separators=(",", ":"))
        if len(prompt) > MAX_OPENAI_PROMPT_CHARS:
            raise GrowthError("growth model prompt exceeds the hard input cap")
        instructions = (
            "You are the Viridis autonomous growth operator. Improve the "
            "framing of the supplied required_factual_copy for the supplied "
            "policy-cleared target. Preserve every route name, exact dollar "
            "amount, open-job ID and budget, live proof sentence, URL, "
            "x402/Base/USDC claim, and intro "
            "offer exactly. Do not invent results, customers, certifications, "
            "discounts, deadlines, compliance guarantees, or legal claims. "
            "Return one concise post plus a short strategy note. You have no "
            "authority to post, move money, change prices, or add targets."
        )
        max_tokens = max(200, min(int(self.environ.get(
            "GROWTH_OPENAI_MAX_OUTPUT_TOKENS",
            DEFAULT_OPENAI_MAX_OUTPUT_TOKENS)), 900))
        agent = Agent(
            name="Viridis Growth Operator",
            instructions=instructions,
            model=self.model,
            model_settings=ModelSettings(
                reasoning=Reasoning(effort="none"),
                verbosity="low",
                max_tokens=max_tokens,
                store=False,
                retry=ModelRetrySettings(max_retries=0),
            ),
            output_type=GrowthCopyOutput,
        )
        provider = OpenAIProvider(
            api_key=api_key,
            use_responses=True,
            strict_feature_validation=True,
        )
        result = Runner.run_sync(
            agent,
            prompt,
            max_turns=1,
            run_config=RunConfig(
                model_provider=provider,
                tracing_disabled=True,
                workflow_name="Viridis Growth Operator",
            ),
        )
        output = result.final_output
        usage = result.context_wrapper.usage
        details = getattr(usage, "input_tokens_details", None)
        return GeneratedCopy(
            content=str(output.content),
            strategy=str(output.strategy),
            usage=ModelUsage(
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                cached_input_tokens=int(
                    getattr(details, "cached_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            ),
            model=self.model,
        )


class DiscordBotAdapter:
    def __init__(self, opener: Callable[..., Any] = urllib.request.urlopen):
        self.opener = opener

    def send(self, target: dict, content: str, credentials: dict) -> dict:
        token = credentials.get("GROWTH_DISCORD_BOT_TOKEN", "")
        channel_id = str(target.get("channel_id", ""))
        if not token:
            raise GrowthError("Discord bot credential is missing")
        if not re.fullmatch(r"[0-9]{10,24}", channel_id):
            raise GrowthError("Discord channel id is invalid")
        request = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            data=json.dumps({"content": content}).encode(), method="POST",
            headers={"Authorization": f"Bot {token}",
                     "Content-Type": "application/json",
                     "User-Agent": "viridis-growth-agent/1"})
        with self.opener(request, timeout=15) as response:
            status = int(getattr(response, "status", 0))
            body = json.loads(response.read(1_000_000) or b"{}")
        if status not in (200, 201):
            raise GrowthError(f"Discord returned HTTP {status}")
        return {"platform": "discord", "message_id": body.get("id"),
                "channel_id": channel_id}


class GitHubAppTokenProvider:
    """Mint short-lived installation tokens from one repository GitHub App.

    The long-lived private key is read from a read-only mounted file. It is
    never returned, logged, or passed to a posting adapter. Installation
    tokens are cached only in memory and refreshed five minutes before their
    one-hour expiry.
    """

    def __init__(self, opener: Callable[..., Any] = urllib.request.urlopen,
                 now_fn: Callable[[], datetime] = _utcnow):
        self.opener = opener
        self.now_fn = now_fn
        self._lock = threading.Lock()
        self._token = ""
        self._expires_at: Optional[datetime] = None

    @staticmethod
    def _b64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    def _jwt(self, app_id: str, key_path: str) -> str:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as exc:
            raise GrowthError("GitHub App signing dependency is unavailable") \
                from exc
        path = Path(key_path)
        try:
            private_key = serialization.load_pem_private_key(
                path.read_bytes(), password=None)
        except Exception as exc:
            raise GrowthError("GitHub App private key is unavailable") from exc
        now = int(self.now_fn().timestamp())
        header = self._b64url(json.dumps(
            {"alg": "RS256", "typ": "JWT"}, separators=(",", ":"),
            sort_keys=True).encode())
        claims = self._b64url(json.dumps(
            {"iat": now - 60, "exp": now + 540, "iss": app_id},
            separators=(",", ":"), sort_keys=True).encode())
        signing_input = f"{header}.{claims}".encode()
        signature = private_key.sign(
            signing_input, padding.PKCS1v15(), hashes.SHA256())
        return f"{header}.{claims}.{self._b64url(signature)}"

    def token(self, credentials: dict) -> str:
        app_id = str(credentials.get("GROWTH_GITHUB_APP_ID") or "").strip()
        installation_id = str(credentials.get(
            "GROWTH_GITHUB_INSTALLATION_ID") or "").strip()
        key_path = str(credentials.get(
            "GROWTH_GITHUB_PRIVATE_KEY_PATH") or "").strip()
        if not (app_id.isdigit() and installation_id.isdigit() and key_path):
            raise GrowthError("GitHub App credentials are incomplete")
        with self._lock:
            now = self.now_fn()
            if (self._token and self._expires_at
                    and self._expires_at - now > timedelta(minutes=5)):
                return self._token
            jwt = self._jwt(app_id, key_path)
            request = urllib.request.Request(
                "https://api.github.com/app/installations/"
                f"{installation_id}/access_tokens",
                data=json.dumps({
                    "repositories": ["viridis-agent-fleet"],
                    "permissions": {"contents": "write"},
                }).encode(), method="POST",
                headers={
                    "Authorization": f"Bearer {jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2026-03-10",
                    "Content-Type": "application/json",
                    "User-Agent": "viridis-growth-agent/1",
                })
            try:
                with self.opener(request, timeout=15) as response:
                    status = int(getattr(response, "status", 0))
                    body = json.loads(response.read(1_000_000) or b"{}")
            except Exception as exc:
                raise GrowthError(
                    "GitHub App installation token request failed") from exc
            token = str(body.get("token") or "")
            expires_at = _parse_iso(str(body.get("expires_at") or ""))
            if status != 201 or not token or expires_at is None:
                raise GrowthError(
                    f"GitHub App token endpoint returned HTTP {status}")
            self._token = token
            self._expires_at = expires_at
            return token


class GitHubOwnedContentAdapter:
    """Update one factual discovery file in the owned public repository.

    GitHub's policy permits project-related promotional text in an owner's
    repository, while unsolicited issue promotion is not allowed. The adapter
    is therefore hard-limited to jdhart81/viridis-agent-fleet and one
    non-workflow documentation path. It never creates issues, PRs, follows,
    stars, or content in third-party accounts.
    """

    REPO = "jdhart81/viridis-agent-fleet"
    PATH = "docs/LIVE_AGENT_SUITE.md"

    def __init__(self, opener: Callable[..., Any] = urllib.request.urlopen,
                 token_provider: Optional[GitHubAppTokenProvider] = None):
        self.opener = opener
        self.token_provider = token_provider or GitHubAppTokenProvider(
            opener=opener)

    @staticmethod
    def _headers(token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "Content-Type": "application/json",
            "User-Agent": "viridis-growth-agent/1",
        }

    def send(self, target: dict, content: str, credentials: dict) -> dict:
        repo = str(target.get("repo", ""))
        path = str(target.get("path", ""))
        branch = str(target.get("branch") or "main")
        if repo != self.REPO or path != self.PATH:
            raise GrowthError(
                "GitHub content adapter is restricted to the owned live-suite file")
        if branch != "main":
            raise GrowthError("GitHub content adapter is restricted to main")
        token = self.token_provider.token(credentials)
        encoded_path = urllib.parse.quote(path, safe="/")
        endpoint = f"https://api.github.com/repos/{repo}/contents/{encoded_path}"
        sha = ""
        get_request = urllib.request.Request(
            f"{endpoint}?ref={urllib.parse.quote(branch, safe='')}",
            headers=self._headers(token))
        try:
            with self.opener(get_request, timeout=15) as response:
                status = int(getattr(response, "status", 0))
                body = json.loads(response.read(1_000_000) or b"{}")
            if status != 200:
                raise GrowthError(f"GitHub content read returned HTTP {status}")
            sha = str(body.get("sha") or "")
        except urllib.error.HTTPError as exc:
            if int(getattr(exc, "code", 0)) != 404:
                raise GrowthError(
                    f"GitHub content read returned HTTP {getattr(exc, 'code', 0)}") \
                    from exc
        document = (
            "# Live Viridis x402 agent suite\n\n"
            "This file is maintained by the isolated Viridis growth worker "
            "from live public route, price, and settlement telemetry.\n\n"
            + content.strip() + "\n")
        payload = {
            "message": "docs: refresh live x402 agent suite",
            "content": base64.b64encode(document.encode()).decode(),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        put_request = urllib.request.Request(
            endpoint, data=json.dumps(payload).encode(), method="PUT",
            headers=self._headers(token))
        with self.opener(put_request, timeout=15) as response:
            status = int(getattr(response, "status", 0))
            body = json.loads(response.read(1_000_000) or b"{}")
        if status not in (200, 201):
            raise GrowthError(f"GitHub content update returned HTTP {status}")
        commit = body.get("commit") if isinstance(body, dict) else {}
        item = body.get("content") if isinstance(body, dict) else {}
        return {
            "platform": "github_owned_content",
            "repo": repo,
            "path": path,
            "content_url": (item or {}).get("html_url"),
            "commit_sha": (commit or {}).get("sha"),
            "updated": bool(sha),
        }


class SmitheryMetadataAdapter:
    """Official API updates for listings owned by the credential holder."""

    def __init__(self, opener: Callable[..., Any] = urllib.request.urlopen):
        self.opener = opener

    def send(self, target: dict, content: str, credentials: dict) -> dict:
        token = credentials.get("GROWTH_SMITHERY_API_KEY", "")
        qualified_name = str(target.get("qualified_name", ""))
        if not token:
            raise GrowthError("Smithery API credential is missing")
        if not re.fullmatch(r"hartjustin6/[A-Za-z0-9_.-]+", qualified_name):
            raise GrowthError(
                "Smithery adapter is restricted to hartjustin6 listings")
        encoded = urllib.parse.quote(qualified_name, safe="")
        request = urllib.request.Request(
            f"https://api.smithery.ai/servers/{encoded}",
            data=json.dumps({
                "description": content,
                "homepage": "https://mcp.viridisconservation.com/agents",
                "unlisted": False,
            }).encode(), method="PATCH",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json",
                     "User-Agent": "viridis-growth-agent/1"})
        with self.opener(request, timeout=15) as response:
            status = int(getattr(response, "status", 0))
            body = json.loads(response.read(1_000_000) or b"{}")
        if status != 200 or body.get("success") is not True:
            raise GrowthError(f"Smithery returned HTTP {status}")
        return {"platform": "smithery", "qualified_name": qualified_name,
                "updated": True}


class GrowthAgent:
    def __init__(self, *, client: LiveFleetClient, log: OutboundLog,
                 targets: Iterable[dict], adapters: Optional[Dict[str, Any]] = None,
                 copywriter: Optional[Any] = None,
                 environ: Optional[dict] = None,
                 now_fn: Callable[[], datetime] = _utcnow):
        self.client = client
        self.log = log
        self.targets = [dict(item) for item in targets]
        self.adapters = adapters or {
            "discord": DiscordBotAdapter(),
            "github_owned_content": GitHubOwnedContentAdapter(),
            "smithery": SmitheryMetadataAdapter(),
        }
        self.environ = dict(os.environ if environ is None else environ)
        self.copywriter = copywriter
        self.now_fn = now_fn

    @property
    def enabled(self) -> bool:
        return _enabled(self.environ.get("GROWTH_AGENT_ENABLED", "0"))

    def credentials(self) -> dict:
        return {name: self.environ.get(name, "")
                for name in POSTING_CREDENTIAL_ENV}

    @property
    def openai_enabled(self) -> bool:
        return _enabled(self.environ.get("GROWTH_OPENAI_ENABLED", "0"))

    def _render_for_target(self, snapshot: FleetSnapshot, target: dict,
                           *, now: datetime) -> tuple[str, dict]:
        deterministic = render_content(snapshot)
        if not self.openai_enabled:
            return deterministic, {"mode": "deterministic", "reason": "disabled"}
        cap = _usd_to_microusd(
            self.environ.get("GROWTH_OPENAI_MONTHLY_BUDGET_USD"),
            default=DEFAULT_OPENAI_MONTHLY_BUDGET_USD)
        reserve = _usd_to_microusd(
            self.environ.get("GROWTH_OPENAI_MAX_CALL_RESERVE_USD"),
            default=DEFAULT_OPENAI_CALL_RESERVE_USD)
        spent = self.log.monthly_llm_cost_microusd(now)
        if spent + reserve > cap:
            self.log.append(
                "llm_result", target, deterministic,
                {"success": False, "fallback": True,
                 "reason": "monthly_budget_hard_stop",
                 "cost_microusd": 0, "month_spend_microusd": spent,
                 "monthly_cap_microusd": cap},
                occurred_at=now)
            return deterministic, {
                "mode": "deterministic_fallback",
                "reason": "monthly_budget_hard_stop",
                "month_spend_microusd": spent,
                "monthly_cap_microusd": cap,
            }
        if not str(self.environ.get("GROWTH_OPENAI_API_KEY") or ""):
            self.log.append(
                "llm_result", target, deterministic,
                {"success": False, "fallback": True,
                 "reason": "credential_missing", "cost_microusd": 0,
                 "month_spend_microusd": spent},
                occurred_at=now)
            return deterministic, {
                "mode": "deterministic_fallback",
                "reason": "credential_missing",
                "month_spend_microusd": spent,
            }
        harness = self.copywriter or OpenAIGrowthHarness(environ=self.environ)
        generated: Optional[GeneratedCopy] = None
        try:
            generated = harness.generate(snapshot, target, deterministic)
            content = validate_generated_content(generated.content, snapshot)
            cost = _usage_cost_microusd(generated.usage)
            self.log.append(
                "llm_result", target, content,
                {"success": True, "fallback": False,
                 "model": generated.model, "strategy": generated.strategy,
                 "input_tokens": generated.usage.input_tokens,
                 "cached_input_tokens": generated.usage.cached_input_tokens,
                 "output_tokens": generated.usage.output_tokens,
                 "cost_microusd": cost,
                 "month_spend_microusd": spent + cost,
                 "monthly_cap_microusd": cap},
                occurred_at=now)
            return content, {
                "mode": "openai",
                "model": generated.model,
                "strategy": generated.strategy,
                "cost_microusd": cost,
                "month_spend_microusd": spent + cost,
                "monthly_cap_microusd": cap,
            }
        except Exception as exc:
            # If a call may have reached the API but usage is unavailable,
            # reserve the maximum configured call cost so the cap fails safe.
            cost = (_usage_cost_microusd(generated.usage)
                    if generated is not None else reserve)
            bad_content = (generated.content if generated is not None
                           else deterministic)
            self.log.append(
                "llm_result", target, bad_content,
                {"success": False, "fallback": True,
                 "error_type": type(exc).__name__,
                 "message": str(exc)[:300], "cost_microusd": cost,
                 "cost_estimated": generated is None,
                 "month_spend_microusd": spent + cost,
                 "monthly_cap_microusd": cap},
                occurred_at=now)
            return deterministic, {
                "mode": "deterministic_fallback",
                "reason": type(exc).__name__,
                "cost_microusd": cost,
                "month_spend_microusd": spent + cost,
                "monthly_cap_microusd": cap,
            }

    def _score(self, target: dict) -> float:
        score = float(target.get("base_weight", 1.0))
        for row in self.log.entries("outcome_observation"):
            if row["target_id"] != target["id"]:
                continue
            if row["payload"].get("conversion") is True:
                score += 2.0 + min(
                    float(row["payload"].get("distinct_payer_delta", 0)), 3.0)
            else:
                score -= 0.5
        return score

    def plan_targets(self, *, now: datetime) -> list[dict]:
        planned = []
        for target in self.targets:
            if target.get("enabled") is not True:
                reason = "target_disabled"
                eligible = False
            elif target.get("policy_cleared") is not True:
                reason = "policy_not_cleared"
                eligible = False
            elif (target.get("credential_env")
                  and not str(self.environ.get(
                      str(target["credential_env"])) or "")):
                reason = "credential_missing"
                eligible = False
            elif (target.get("credential_envs")
                  and any(not str(self.environ.get(str(name)) or "")
                          for name in target["credential_envs"])):
                reason = "credential_missing"
                eligible = False
            else:
                last = self.log.last_success_at(str(target["id"]))
                cooldown = timedelta(days=int(target.get(
                    "cooldown_days", DEFAULT_COOLDOWN_DAYS)))
                eligible = last is None or now - last >= cooldown
                reason = "eligible" if eligible else "cooldown_active"
            planned.append({**target, "score": self._score(target),
                            "eligible": eligible, "reason": reason})
        planned.sort(key=lambda item: (-item["score"], str(item["id"])))
        return planned

    def observe_outcomes(self, snapshot: FleetSnapshot, *, now: datetime) -> int:
        observed = self.log.observed_attempt_ids()
        attempts = {row["attempt_id"] or row["event_id"]: row
                    for row in self.log.entries("send_attempt")}
        successes = [row for row in self.log.entries("send_result")
                     if row["payload"].get("success") is True]
        # One settlement count can be correlated to at most one attempt for a
        # given route scope. Persisted high-water marks prevent an older post
        # from claiming the same later settlement on a subsequent worker run.
        attributed_highwater: dict[str, int] = {}
        for row in self.log.entries("outcome_observation"):
            payload = row["payload"]
            scope = str(payload.get("attribution_scope") or "")
            if not scope or payload.get("conversion") is not True:
                continue
            attributed_highwater[scope] = max(
                attributed_highwater.get(scope, 0),
                int(payload.get("external_settlements_after") or 0))
        appended = 0
        target_map = {str(item["id"]): item for item in self.targets}
        # Newest successful action gets first claim on an unattributed signal.
        for result in reversed(successes):
            attempt_id = str(result.get("attempt_id") or "")
            if not attempt_id or attempt_id in observed or attempt_id not in attempts:
                continue
            attempt = attempts[attempt_id]
            target = target_map.get(result["target_id"], {
                "id": result["target_id"], "channel": result["channel"],
                "route": attempt["payload"].get("attribution_scope")})
            try:
                scope, current = metrics_for_target(snapshot, target)
            except GrowthError:
                continue
            before = attempt["payload"].get("metrics_before") or {}
            current_settlements = int(
                current.get("external_settlements") or 0)
            baseline = max(
                int(before.get("external_settlements") or 0),
                attributed_highwater.get(scope, 0))
            settlement_delta = max(current_settlements - baseline, 0)
            payer_delta = max(
                int(current.get("distinct_external_payers") or 0)
                - int(before.get("distinct_external_payers") or 0), 0)
            revenue_delta = max(
                int(current.get("external_revenue_atomic") or 0)
                - int(before.get("external_revenue_atomic") or 0), 0)
            result_at = _parse_iso(result["occurred_at"])
            matured = bool(result_at and now - result_at >= timedelta(
                days=int(self.environ.get("GROWTH_FEEDBACK_WINDOW_DAYS",
                                          DEFAULT_FEEDBACK_WINDOW_DAYS))))
            if settlement_delta <= 0 and not matured:
                continue
            conversion = settlement_delta > 0
            if conversion:
                attributed_highwater[scope] = current_settlements
            self.log.append(
                "outcome_observation", target, "",
                {"conversion": conversion,
                 "attribution_scope": scope,
                 "settlement_delta": settlement_delta,
                 "distinct_payer_delta": payer_delta,
                 "external_revenue_atomic_delta": revenue_delta,
                 "external_settlements_after": current_settlements,
                 "first_external_settlement_before": before.get(
                     "first_external_settlement"),
                 "first_external_settlement_after": current.get(
                     "first_external_settlement"),
                 "snapshot_signature": snapshot.signature(),
                 "note": "correlation signal, not causal attribution"},
                occurred_at=now, attempt_id=attempt_id)
            appended += 1
        return appended

    def run_once(self, *, dry_run: bool = False) -> dict:
        now = self.now_fn()
        if not dry_run and not self.enabled:
            return {"status": "disabled", "enabled": False,
                    "message": "GROWTH_AGENT_ENABLED is off; no network or send"}
        snapshot = self.client.fetch(now=now)
        if not dry_run:
            self.observe_outcomes(snapshot, now=now)
        plan = self.plan_targets(now=now)
        selected = next((item for item in plan if item["eligible"]), None)
        preview_target = selected or (plan[0] if plan else None)
        target_for_content = preview_target or {
            "id": "no-target", "channel": "no eligible target"}
        if selected is None and not dry_run:
            content = render_content(snapshot)
            model_result = {"mode": "deterministic",
                            "reason": "no_eligible_target"}
        else:
            content, model_result = self._render_for_target(
                snapshot, target_for_content, now=now)
        if dry_run:
            return {"status": "dry_run", "enabled": self.enabled,
                    "target": preview_target, "content": content,
                    "model": model_result,
                    "snapshot_signature": snapshot.signature(),
                    "send_attempted": False}
        if selected is None:
            return {"status": "no_cleared_target", "content": content,
                    "targets": plan, "send_attempted": False}
        attribution_scope, metrics_before = metrics_for_target(
            snapshot, selected)
        platform = str(selected.get("platform", ""))
        adapter = self.adapters.get(platform)
        if adapter is None:
            return {"status": "unsupported_platform", "target": selected,
                    "send_attempted": False}
        attempt_id = str(uuid.uuid4())
        self.log.append(
            "send_attempt", selected, content,
            {"metrics_before": metrics_before,
             "attribution_scope": attribution_scope,
             "snapshot_signature": snapshot.signature(),
             "policy_cleared": True,
             "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
             "model": model_result},
            occurred_at=now, attempt_id=attempt_id)   # FA-I7: BEFORE send
        try:
            receipt = adapter.send(selected, content, self.credentials())
        except Exception as exc:
            self.log.append(
                "send_result", selected, content,
                {"success": False, "error_type": type(exc).__name__,
                 "message": str(exc)[:300]},
                occurred_at=self.now_fn(), attempt_id=attempt_id)
            return {"status": "send_failed", "attempt_id": attempt_id,
                    "error_type": type(exc).__name__}
        self.log.append(
            "send_result", selected, content,
            {"success": True, "receipt": receipt},
            occurred_at=self.now_fn(), attempt_id=attempt_id)
        return {"status": "sent", "attempt_id": attempt_id,
                "target": selected["id"], "receipt": receipt,
                "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                "model": model_result}


def build_default() -> GrowthAgent:
    here = Path(__file__).resolve().parent
    targets_path = os.environ.get("GROWTH_TARGETS_PATH",
                                  str(here / "targets.json"))
    db_path = os.environ.get("GROWTH_STATE_DB",
                             "/state/viridis_growth.sqlite3")
    client = LiveFleetClient(
        os.environ.get("GROWTH_FLEET_HEALTH_URL", DEFAULT_HEALTH_URL),
        os.environ.get("GROWTH_MARKET_CATALOG_URL",
                       DEFAULT_MARKET_CATALOG_URL))
    return GrowthAgent(client=client, log=OutboundLog(db_path),
                       targets=load_targets(targets_path),
                       copywriter=OpenAIGrowthHarness(environ=os.environ))
