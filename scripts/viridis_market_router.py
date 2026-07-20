#!/usr/bin/env python3
"""Bounded x402 buyer SDK and market router for autonomous agents.

The SDK ranks sellers from machine-readable catalogs, enforces an AP2-style
spend mandate, and completes HTTP x402 v2 calls only through a caller-injected
signer callback. It has no wallet implementation, private-key field, seed
phrase support, or ambient authority to spend.
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import ipaddress
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

PAYMENT_REQUIRED = "PAYMENT-REQUIRED"
PAYMENT_SIGNATURE = "PAYMENT-SIGNATURE"
PAYMENT_RESPONSE = "PAYMENT-RESPONSE"
MAX_CATALOG_BYTES = 2_000_000
TOKEN_RE = re.compile(r"[a-z0-9]+")


class RouterError(RuntimeError):
    pass


def _now_ts() -> int:
    return int(time.time())


def _tokens(value: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(str(value).lower())
            if len(token) > 2}


def _safe_https_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username:
        raise RouterError("seller and catalog URLs must be public HTTPS URLs")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        raise RouterError("local seller URLs are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or
                    address.is_link_local or address.is_reserved or
                    address.is_multicast):
        raise RouterError("private-network seller URLs are not allowed")
    return urllib.parse.urlunsplit(parsed)


@dataclasses.dataclass(frozen=True)
class SellerResource:
    id: str
    url: str
    description: str
    amount_atomic: int
    network: str
    pay_to: str
    trust_score: float = 0.5
    latency_ms: int = 1000
    source: str = "unknown"
    input_schema: Optional[dict] = None

    @classmethod
    def from_x402(cls, item: dict, *, source: str = "catalog"):
        accepts = item.get("accepts") if isinstance(item, dict) else None
        accepted = accepts[0] if isinstance(accepts, list) and accepts else {}
        resource = item.get("resource") if isinstance(item, dict) else {}
        if not isinstance(resource, dict):
            resource = {}
        url = str(resource.get("url") or item.get("url") or "")
        amount = accepted.get("amount", item.get("amountAtomicUsdc"))
        try:
            amount_int = int(str(amount))
        except (TypeError, ValueError) as exc:
            raise RouterError("catalog resource amount is invalid") from exc
        if amount_int < 0:
            raise RouterError("catalog resource amount cannot be negative")
        normalized_url = _safe_https_url(url)
        return cls(
            id=str(item.get("id") or normalized_url),
            url=normalized_url,
            description=str(resource.get("description") or
                            item.get("description") or "")[:1000],
            amount_atomic=amount_int,
            network=str(accepted.get("network") or item.get("network") or ""),
            pay_to=str(accepted.get("payTo") or item.get("payTo") or ""),
            trust_score=max(0.0, min(float(item.get("trustScore", 0.5)), 1.0)),
            latency_ms=max(0, int(item.get("latencyMs", 1000))),
            source=source,
            input_schema=item.get("inputSchema") if isinstance(
                item.get("inputSchema"), dict) else None,
        )


@dataclasses.dataclass(frozen=True)
class SpendMandate:
    """Caller-signed policy envelope; AP2-style, not an AP2 credential."""
    mandate_id: str
    purpose: str
    max_total_atomic: int
    max_per_call_atomic: int
    allowed_networks: tuple[str, ...]
    allowed_payees: tuple[str, ...]
    allowed_resource_prefixes: tuple[str, ...]
    expires_at_epoch: int
    max_latency_ms: int = 10_000
    min_trust_score: float = 0.0

    @classmethod
    def create(cls, *, purpose: str, max_total_atomic: int,
               max_per_call_atomic: int, allowed_networks: Iterable[str],
               allowed_payees: Iterable[str],
               allowed_resource_prefixes: Iterable[str],
               expires_at_epoch: int, max_latency_ms: int = 10_000,
               min_trust_score: float = 0.0):
        return cls(
            mandate_id=str(uuid.uuid4()), purpose=str(purpose)[:500],
            max_total_atomic=int(max_total_atomic),
            max_per_call_atomic=int(max_per_call_atomic),
            allowed_networks=tuple(str(v) for v in allowed_networks),
            allowed_payees=tuple(str(v).lower() for v in allowed_payees),
            allowed_resource_prefixes=tuple(
                _safe_https_url(str(v)) for v in allowed_resource_prefixes),
            expires_at_epoch=int(expires_at_epoch),
            max_latency_ms=int(max_latency_ms),
            min_trust_score=float(min_trust_score),
        )

    def refusal(self, resource: SellerResource, *, spent_atomic: int = 0,
                now_epoch: Optional[int] = None) -> str:
        now = _now_ts() if now_epoch is None else int(now_epoch)
        if now >= self.expires_at_epoch:
            return "mandate_expired"
        if resource.network not in self.allowed_networks:
            return "network_not_allowed"
        if resource.pay_to.lower() not in self.allowed_payees:
            return "payee_not_allowed"
        if not any(resource.url.startswith(prefix)
                   for prefix in self.allowed_resource_prefixes):
            return "resource_not_allowed"
        if resource.amount_atomic > self.max_per_call_atomic:
            return "per_call_cap_exceeded"
        if spent_atomic + resource.amount_atomic > self.max_total_atomic:
            return "total_cap_exceeded"
        if resource.latency_ms > self.max_latency_ms:
            return "latency_cap_exceeded"
        if resource.trust_score < self.min_trust_score:
            return "trust_floor_not_met"
        return ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class MarketRouter:
    def __init__(self, resources: Iterable[SellerResource]):
        self.resources = tuple(resources)

    def rank(self, intent: str, mandate: SpendMandate,
             *, spent_atomic: int = 0, now_epoch: Optional[int] = None) -> list[dict]:
        intent_tokens = _tokens(intent)
        ranked = []
        for resource in self.resources:
            refusal = mandate.refusal(resource, spent_atomic=spent_atomic,
                                       now_epoch=now_epoch)
            overlap = len(intent_tokens & _tokens(
                resource.id + " " + resource.description))
            relevance = overlap / max(len(intent_tokens), 1)
            affordability = 1.0 - min(
                resource.amount_atomic / max(mandate.max_per_call_atomic, 1), 1.0)
            latency = 1.0 - min(
                resource.latency_ms / max(mandate.max_latency_ms, 1), 1.0)
            score = (0.55 * relevance + 0.25 * resource.trust_score +
                     0.10 * affordability + 0.10 * latency)
            ranked.append({"resource": resource, "eligible": not refusal,
                           "refusal_reason": refusal,
                           "score": round(score, 6)})
        return sorted(ranked, key=lambda row: (
            not row["eligible"], -row["score"],
            row["resource"].amount_atomic, row["resource"].id))


def load_catalog(url: str, *, opener: Callable[..., Any] = urllib.request.urlopen,
                 timeout: int = 10) -> list[SellerResource]:
    safe = _safe_https_url(url)
    request = urllib.request.Request(
        safe, headers={"Accept": "application/json",
                       "User-Agent": "viridis-market-router/1"})
    with opener(request, timeout=timeout) as response:
        raw = response.read(MAX_CATALOG_BYTES + 1)
    if len(raw) > MAX_CATALOG_BYTES:
        raise RouterError("catalog exceeds the response size limit")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RouterError("catalog is not valid JSON") from exc
    items = (payload.get("resources") or payload.get("items") or
             payload.get("routes")) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise RouterError("catalog does not contain a resource list")
    resources = []
    for item in items[:500]:
        if isinstance(item, dict):
            resources.append(SellerResource.from_x402(item, source=safe))
    return resources


def _decode_header(value: str) -> dict:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.b64decode(padded)
        result = json.loads(decoded)
    except Exception as exc:
        raise RouterError("payment header is malformed") from exc
    if not isinstance(result, dict):
        raise RouterError("payment header must decode to an object")
    return result


class X402Buyer:
    def __init__(self, mandate: SpendMandate, *,
                 opener: Callable[..., Any] = urllib.request.urlopen):
        self.mandate = mandate
        self.opener = opener
        self.spent_atomic = 0

    def quote(self, resource: SellerResource, input_data: dict) -> dict:
        """Fetch the 402 challenge. This method cannot pay."""
        request = urllib.request.Request(
            resource.url, data=json.dumps(input_data).encode(), method="POST",
            headers={"Content-Type": "application/json",
                     "Accept": "application/json",
                     "User-Agent": "viridis-market-router/1"})
        try:
            with self.opener(request, timeout=15) as response:
                status = int(getattr(response, "status", 200))
                response.read(MAX_CATALOG_BYTES)
                if status != 402:
                    raise RouterError("seller executed without a 402 challenge")
                header = response.headers.get(PAYMENT_REQUIRED)
        except urllib.error.HTTPError as exc:
            if exc.code != 402:
                raise RouterError(f"seller quote returned HTTP {exc.code}") from exc
            header = exc.headers.get(PAYMENT_REQUIRED)
        if not header:
            raise RouterError("seller omitted PAYMENT-REQUIRED")
        required = _decode_header(header)
        accepted = (required.get("accepts") or [{}])[0]
        quoted = SellerResource.from_x402({
            "id": resource.id, "resource": required.get("resource"),
            "accepts": [accepted], "trustScore": resource.trust_score,
            "latencyMs": resource.latency_ms,
        }, source=resource.source)
        if quoted.url != resource.url:
            raise RouterError("seller changed the quoted resource URL")
        refusal = self.mandate.refusal(
            quoted, spent_atomic=self.spent_atomic)
        return {"eligible": not refusal, "refusal_reason": refusal,
                "payment_required": required, "resource": quoted}

    def execute(self, resource: SellerResource, input_data: dict, *,
                signer: Optional[Callable[[dict, SpendMandate], str]]) -> dict:
        """Pay once through a caller signer. No signer means no purchase."""
        quote = self.quote(resource, input_data)
        if not quote["eligible"]:
            raise RouterError(f"mandate refused purchase: {quote['refusal_reason']}")
        if signer is None:
            raise RouterError("signer_required")
        signature = signer(quote["payment_required"], self.mandate)
        if not isinstance(signature, str) or not signature.strip():
            raise RouterError("signer returned no payment authorization")
        request = urllib.request.Request(
            resource.url, data=json.dumps(input_data).encode(), method="POST",
            headers={"Content-Type": "application/json",
                     "Accept": "application/json",
                     PAYMENT_SIGNATURE: signature,
                     "User-Agent": "viridis-market-router/1"})
        try:
            with self.opener(request, timeout=30) as response:
                status = int(getattr(response, "status", 0))
                raw = response.read(MAX_CATALOG_BYTES + 1)
                receipt_header = response.headers.get(PAYMENT_RESPONSE)
        except urllib.error.HTTPError as exc:
            raise RouterError(f"paid request returned HTTP {exc.code}") from exc
        if status < 200 or status >= 300 or len(raw) > MAX_CATALOG_BYTES:
            raise RouterError("paid request did not return a bounded success")
        if not receipt_header:
            raise RouterError("seller omitted PAYMENT-RESPONSE receipt")
        receipt = _decode_header(receipt_header)
        result = json.loads(raw)
        self.spent_atomic += quote["resource"].amount_atomic
        return {"result": result, "receipt": receipt,
                "spent_atomic": self.spent_atomic,
                "mandate_id": self.mandate.mandate_id}


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Rank x402 sellers without holding a wallet key")
    parser.add_argument("catalog", help="public HTTPS x402 catalog")
    parser.add_argument("--intent", required=True)
    parser.add_argument("--max-atomic", type=int, required=True)
    parser.add_argument("--network", default="eip155:8453")
    parser.add_argument("--pay-to", action="append", required=True)
    args = parser.parse_args()
    resources = load_catalog(args.catalog)
    mandate = SpendMandate.create(
        purpose=args.intent, max_total_atomic=args.max_atomic,
        max_per_call_atomic=args.max_atomic,
        allowed_networks=[args.network], allowed_payees=args.pay_to,
        allowed_resource_prefixes=[args.catalog.rsplit("/", 1)[0] + "/"],
        expires_at_epoch=_now_ts() + 900)
    rows = MarketRouter(resources).rank(args.intent, mandate)
    print(json.dumps([{**{k: v for k, v in row.items() if k != "resource"},
                       "resource": dataclasses.asdict(row["resource"])}
                      for row in rows], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
