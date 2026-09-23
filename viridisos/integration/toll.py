"""U-4 One toll. Single source of truth for the Viridis protocol take.

Mirrors gateway/escrow_custody.py (EC10, 2026-07-19): pass-through card cost + earned margin
bps, floor 50 bps over rail cost. Both the ViridisOS settlement path and the fleet path call
this so they never diverge.

IMPLEMENT ME — see BUILD_SPEC.md §"integration/toll.py".
"""

from __future__ import annotations

CARD_RAIL_COST_BPS = 290                                   # pass-through, not Viridis revenue
MARGIN_BPS = {"new": 200, "connect_onboarded": 150, "connect_verified": 100}  # the Viridis take
MIN_MARGIN_OVER_RAIL_BPS = 50


def _ceil_bps(amount_minor: int, bps: int) -> int:
    """Ceil rounding of amount*bps/10000 — identical to escrow_custody._ceil_bps."""
    return -(-amount_minor * bps // 10000)


def compute_toll(amount_minor: int, payee_tier: str) -> dict:
    """Return {protocol_margin_minor, protocol_margin_bps, card_rail_cost_minor, total_fee_minor}.

    protocol_margin_bps = max(MARGIN_BPS[tier], MIN_MARGIN_OVER_RAIL_BPS).
    Protocol margin is applied exactly once. Unknown tier -> raise ValueError.
    """
    if not isinstance(amount_minor, int) or amount_minor < 0:
        raise ValueError("amount_minor must be a non-negative integer")
    try:
        tier_margin_bps = MARGIN_BPS[payee_tier]
    except KeyError:
        raise ValueError(f"unknown payee tier: {payee_tier}") from None

    protocol_margin_bps = max(tier_margin_bps, MIN_MARGIN_OVER_RAIL_BPS)
    protocol_margin_minor = _ceil_bps(amount_minor, protocol_margin_bps)
    card_rail_cost_minor = _ceil_bps(amount_minor, CARD_RAIL_COST_BPS)

    return {
        "protocol_margin_minor": protocol_margin_minor,
        "protocol_margin_bps": protocol_margin_bps,
        "card_rail_cost_minor": card_rail_cost_minor,
        "total_fee_minor": protocol_margin_minor + card_rail_cost_minor,
    }
