#!/usr/bin/env python3
"""Apply the minimal paid-success seat bridge to the exact 2026-07-28 base."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


INPUT_SHA256 = (
    "3051b85c08f4932b5d29da6e1fdd8238332375d821195cc7a468705dcac7379f"
)
OUTPUT_SHA256 = (
    "33d0b79f19171f7f1ff89d92b41f4f0995a61592957720fb3a2c156628c2b980"
)

DOC_ANCHOR = """\
H402-13 EXTERNAL EVIDENCE POINTERS: the catalog may point to immutable fixture
       files in an external verifier's repository. The index is explicitly a
       seller-published pointer, never payment authority or independent proof
       by itself; buyers verify the external file, commit, and SHA-256.
"""

DOC_REPLACEMENT = DOC_ANCHOR + """\
H402-14 RECURRING-VALUE BRIDGE: a successful paid result may advertise the
       approved monthly seat that covers the current agent. The offer is
       machine-readable discovery metadata only: checkout remains a separate
       buyer action on the live Stripe-hosted seat surface, and no subscription
       is created, selected, or paid automatically.
"""

SEAT_OPTION = '''\

def seat_option(agent: str, public_base: str) -> dict | None:
    """Return the approved recurring plan covering an agent, if one exists."""
    from payment_gate import SEAT_PLANS
    plan = SEAT_PLANS.get(agent)
    if not isinstance(plan, dict):
        return None
    covered_agents = list(plan["covered_agents"])
    price_minor = int(plan["price_monthly_minor"])
    calls = int(plan["included_calls_per_month"])
    dollars = price_minor / 100
    return {
        "plan_id": plan["plan_id"],
        "price_monthly_minor": price_minor,
        "currency": "usd",
        "interval": "month",
        "included_calls_per_month": calls,
        "covered_agents": covered_agents,
        "checkout_url": public_base.rstrip("/") + "/seats",
        "checkout_status_authoritative_source": "live_plan_catalog",
        "auto_checkout": False,
        "buyer_action_required": True,
        "note": (
            f"{plan['plan_id']}: ${dollars:.0f}/mo covers {calls:,} calls "
            f"across {' + '.join(covered_agents)}"),
    }
'''

COMMERCE_TAIL = '''\
        "note": ("No repeat or follow-on payment was signed, initiated, or "
                 "executed. Every purchase requires new caller-owned inputs, "
                 "a fresh unpaid quote, and a separate x402 settlement."),
    }
    return enriched
'''

COMMERCE_TAIL_REPLACEMENT = '''\
        "note": ("No repeat or follow-on payment was signed, initiated, or "
                 "executed. Every purchase requires new caller-owned inputs, "
                 "a fresh unpaid quote, and a separate x402 settlement."),
    }
    recurring = seat_option(agent, public_base)
    if recurring is not None:
        commerce["seat_option"] = recurring
    enriched["viridis_commerce"] = commerce
    return enriched
'''


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def apply_overlay(path: Path) -> str:
    raw = path.read_bytes()
    observed = _sha256(raw)
    if observed != INPUT_SHA256:
        raise RuntimeError(
            f"input digest mismatch: expected {INPUT_SHA256}, found {observed}"
        )
    text = raw.decode("utf-8")
    if "H402-14 RECURRING-VALUE BRIDGE" in text or "def seat_option(" in text:
        raise RuntimeError("seat bridge is already present")

    text = _replace_once(
        text, DOC_ANCHOR, DOC_REPLACEMENT, "commerce doctrine"
    )
    text = _replace_once(
        text,
        "\n\ndef _with_commerce_metadata(",
        SEAT_OPTION + "\n\ndef _with_commerce_metadata(",
        "seat option insertion",
    )
    text = _replace_once(
        text,
        '    enriched["viridis_commerce"] = {\n',
        "    commerce = {\n",
        "commerce envelope assignment",
    )
    text = _replace_once(
        text,
        COMMERCE_TAIL,
        COMMERCE_TAIL_REPLACEMENT,
        "commerce envelope completion",
    )

    output = text.encode("utf-8")
    output_digest = _sha256(output)
    if output_digest != OUTPUT_SHA256:
        raise RuntimeError(
            "output digest mismatch: "
            f"expected {OUTPUT_SHA256}, found {output_digest}"
        )
    path.write_bytes(output)
    return output_digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("/fleet/deploy/gateway/x402_http.py"),
    )
    args = parser.parse_args()
    print(apply_overlay(args.path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
