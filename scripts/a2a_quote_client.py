#!/usr/bin/env python3
"""Discover Viridis through the official A2A Python SDK.

Install and run without writing seller state:

  uv run --no-project --with "a2a-sdk==1.1.2" \
    python scripts/a2a_quote_client.py

Add ``--request-quote`` to create exactly one durable, unpaid A2A task and
print its x402 requirements. This client never loads a wallet, signs a payment,
submits a payment payload, or retries a paid request.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from typing import Any


DEFAULT_BASE_URL = "https://mcp.viridisconservation.com"
EXTENSION_URI = "https://github.com/google-a2a/a2a-x402/v0.1"
DEFAULT_SKILL = "regulatory-radar.scan_regulations"
REQUIRED_SKILL_IDS = frozenset({
    "quantity-takeoff.calculate_takeoff",
    "ghg-ledger.calculate_inventory",
    "disclosure-compiler.compile_disclosure",
    "taxcredit-engine.calculate_tax_credit",
    "regulatory-radar.scan_regulations",
    "hive.solve",
})
DEFAULT_INPUT = {
    "jurisdiction": "US",
    "sector": "energy",
    "query": "45V clean energy tax credit emissions disclosure",
}


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _extension(card: Any) -> Any:
    capabilities = getattr(card, "capabilities", None)
    for extension in getattr(capabilities, "extensions", ()):
        if getattr(extension, "uri", "") == EXTENSION_URI:
            return extension
    return None


def _interface(card: Any) -> Any:
    for interface in getattr(card, "supported_interfaces", ()):
        if getattr(interface, "protocol_binding", "") == "HTTP+JSON":
            return interface
    return None


def _skill_ids(card: Any) -> set[str]:
    return {
        skill_id
        for skill in getattr(card, "skills", ())
        if (skill_id := getattr(skill, "id", ""))
    }


def _quote_summary(event: dict) -> dict:
    task = _dict(event.get("task"))
    status = _dict(task.get("status"))
    message = _dict(status.get("message"))
    metadata = _dict(message.get("metadata"))
    required = _dict(metadata.get("x402.payment.required"))
    accepts = required.get("accepts")
    accepted = _dict(accepts[0]) if isinstance(accepts, list) and accepts else {}
    return {
        "task_id": task.get("id"),
        "state": status.get("state"),
        "payment_status": metadata.get("x402.payment.status"),
        "x402_version": required.get("x402Version"),
        "scheme": accepted.get("scheme"),
        "network": accepted.get("network"),
        "asset": accepted.get("asset"),
        "amount_atomic_usdc": accepted.get("amount"),
        "pay_to": accepted.get("payTo"),
        "resource": _dict(required.get("resource")).get("url"),
    }


async def _run(args: argparse.Namespace) -> int:
    try:
        import httpx
        from a2a.client import (
            A2ACardResolver,
            ClientCallContext,
            ClientConfig,
            ClientFactory,
        )
        from a2a.types import Message, Part, Role, SendMessageRequest
        from google.protobuf.json_format import MessageToDict, ParseDict
    except ImportError:
        print(
            'Install the released client with: pip install "a2a-sdk==1.1.2"',
            file=sys.stderr,
        )
        return 2

    base_url = args.base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=args.timeout) as http:
        card = await A2ACardResolver(http, base_url).get_agent_card()
        interface = _interface(card)
        extension = _extension(card)
        if interface is None:
            raise RuntimeError("Agent Card has no HTTP+JSON interface")
        if getattr(interface, "protocol_version", "") != "1.0":
            raise RuntimeError("Agent Card does not advertise A2A 1.0")
        if extension is None or not getattr(extension, "required", False):
            raise RuntimeError("Agent Card does not require the canonical x402 extension")
        skill_ids = _skill_ids(card)
        missing_skills = REQUIRED_SKILL_IDS - skill_ids
        if missing_skills:
            raise RuntimeError(
                "Agent Card is missing required Viridis skills: "
                + ", ".join(sorted(missing_skills))
            )
        if args.request_quote and args.skill not in skill_ids:
            raise RuntimeError(f"requested skill is not advertised: {args.skill}")

        discovery = {
            "agent": getattr(card, "name", ""),
            "interface": getattr(interface, "url", ""),
            "protocol": getattr(interface, "protocol_binding", ""),
            "protocol_version": getattr(interface, "protocol_version", ""),
            "skills": len(skill_ids),
            "required_extension": getattr(extension, "uri", ""),
            "mode": "discovery_only" if not args.request_quote else "unpaid_quote",
        }
        print(json.dumps(discovery, indent=2, sort_keys=True))
        if not args.request_quote:
            return 0

        client = ClientFactory(
            ClientConfig(
                streaming=False,
                httpx_client=http,
                supported_protocol_bindings=["HTTP+JSON"],
            )
        ).create(card)
        part = ParseDict(
            {"data": {"skillId": args.skill, "input": args.input}},
            Part(),
        )
        request = SendMessageRequest(
            message=Message(
                role=Role.ROLE_USER,
                message_id=str(uuid.uuid4()),
                parts=[part],
            )
        )
        context = ClientCallContext(
            service_parameters={"A2A-Extensions": EXTENSION_URI}
        )
        events = []
        async for event in client.send_message(request, context=context):
            events.append(MessageToDict(event))
        if len(events) != 1:
            raise RuntimeError(f"expected one non-streaming event, received {len(events)}")
        quote = _quote_summary(events[0])
        if quote["state"] != "TASK_STATE_INPUT_REQUIRED":
            raise RuntimeError(f"unexpected task state: {quote['state']}")
        if quote["payment_status"] != "payment-required":
            raise RuntimeError(
                f"unexpected payment state: {quote['payment_status']}"
            )
        print(json.dumps(quote, indent=2, sort_keys=True))
        print(
            "No wallet was loaded; no signature was created; no payment was submitted."
        )
        return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover Viridis with the official A2A SDK; optionally request "
            "one unpaid x402 quote."
        )
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--skill", default=DEFAULT_SKILL)
    parser.add_argument(
        "--input-json",
        dest="input",
        type=json.loads,
        default=DEFAULT_INPUT,
        help="JSON object passed as the selected skill input",
    )
    parser.add_argument(
        "--request-quote",
        action="store_true",
        help="create one durable unpaid task; never signs or pays",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not isinstance(args.input, dict):
        print("--input-json must decode to an object", file=sys.stderr)
        return 2
    try:
        return asyncio.run(_run(args))
    except Exception as exc:
        print(f"A2A probe failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
