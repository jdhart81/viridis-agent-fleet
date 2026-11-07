"""viridis-eco-funding: value, verify and model pooled funding for ecosystem complexity.

Read-only and deterministic. No money movement: no payments, wallets, keys or tokens.
The intelligence-bound term is a conjecture and is labelled as such in every output.
"""

from .constants import CONJECTURE_LABEL, METHOD_VERSION, RECEIPT_VERSION
from .explain import describe_method, explain_valuation
from .inputs import SiteInputError, normalize_site_inputs
from .pool import LEGAL_NOTICE, PoolSpecError, simulate_pool
from .receipt import make_receipt, receipt_text, verify_receipt
from .valuation import value_site

__version__ = "0.1.0"

__all__ = [
    "CONJECTURE_LABEL",
    "LEGAL_NOTICE",
    "METHOD_VERSION",
    "RECEIPT_VERSION",
    "PoolSpecError",
    "SiteInputError",
    "__version__",
    "describe_method",
    "explain_valuation",
    "make_receipt",
    "normalize_site_inputs",
    "receipt_text",
    "simulate_pool",
    "value_site",
    "verify_receipt",
]
