"""Funding-pool design: schema and simulator. Modelling only; no money movement."""

from .schema import LEGAL_NOTICE, METRICS, PoolSpecError, normalize_pool
from .simulator import simulate_pool

__all__ = ["LEGAL_NOTICE", "METRICS", "PoolSpecError", "normalize_pool", "simulate_pool"]
