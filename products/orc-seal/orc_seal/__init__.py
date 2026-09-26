"""orc-seal: Outcome Receipts (ORC v0.1) for any MCP server. Apache-2.0."""
from .sealer import (META_KEY, RegistryClient, Sealer, normalize, sealed,  # noqa: F401
                     verify)

__version__ = "0.1.0"
