"""Agent package — public API surface and lazy-import boundary.

This `__init__.py` is the canonical fleet pattern for managing the boundary
between an agent's *core surface* (cheap, dependency-light) and its
*heavyweight optional capabilities* (scipy, xarray, pandas, torch, etc.).

The pattern was first established in `bioacoustic-agent/src/__init__.py`
during Nightkeeper Night 26 (2026-04-25, cross-pollination queue #9),
validated through Nights 27 and 28, and promoted into the agent template
on Night 28 (2026-04-27) so every new agent inherits modular-isolation
defaults. See NIGHTKEEPER_LOG.md entries for those nights for full
rationale.

WHY THIS MATTERS
----------------
Most adapters (Cloudflare Workers, MCP servers, fleet orchestration via
Mycelium IQ) only need the agent's `process()`, `health()`, and
`describe()` interface — not its scientific-computation toolkit. A
flat `from . import *` style `__init__.py` forces every consumer to
load every dependency, which:

  * Slows cold-start on Workers and serverless (scipy ~80-200ms even cold).
  * Forces tests of the `process/health/describe` core to install scipy.
  * Couples the deploy-anywhere fleet pattern to one of the heaviest deps.

PEP 562's module-level `__getattr__` (Python 3.7+) lets us advertise
heavyweight symbols in `__all__` while deferring their import until
first access. After first access, the resolved value is cached as a real
module attribute, so subsequent lookups bypass `__getattr__` entirely.

USAGE — STARTING A NEW AGENT
----------------------------
This template has no heavyweight deps yet, so `_LAZY_EXPORTS` is empty
and `__getattr__` is a no-op (it just raises AttributeError as Python
would have done anyway). When you add a submodule that pulls in scipy /
xarray / pandas / torch / etc., follow these steps:

  1. Add the public class names to `__all__` below.
  2. Add an entry to `_LAZY_EXPORTS` mapping each name to
     `(".submodule_name", "AttrName")`.
  3. Do NOT add `from .submodule_name import AttrName` at the top — that
     would defeat the lazy boundary by eagerly loading the submodule.

Worked example (from bioacoustic-agent, where scipy is the heavy dep)::

    from .core import AgentCore, AgentConfig    # eager — scipy-free

    __all__ = [
        "AgentCore",
        "AgentConfig",
        "AcousticIndices",      # scipy-gated, lazy
        "SpectralAnalyzer",     # scipy-gated, lazy
    ]

    _LAZY_EXPORTS = {
        "AcousticIndices":  (".acoustic_indices", "AcousticIndices"),
        "SpectralAnalyzer": (".spectral",         "SpectralAnalyzer"),
    }

INVARIANTS PRESERVED
--------------------
  * `from src import AgentCore` works without loading any lazy submodule.
  * `from src import HeavyThing` (when registered) loads its submodule
    on first access; raises `ModuleNotFoundError` (NOT `AttributeError`)
    if the underlying dep is missing — that's the correct signal for
    "the lazy table is wired up but the dep isn't installed."
  * `dir(src)` exposes both eager and lazy names for IDE / REPL discovery.
  * Direct submodule imports (`from src.heavy_submod import X`) still
    work and still load the heavy dep — this pattern only governs
    package-level access.
  * `__all__` is the single source of truth for public surface;
    `_LAZY_EXPORTS` is a subset of it (lazy symbols only).
"""

# ─────────────────────────────────────────────────────────────────────────────
# EAGER IMPORTS — keep this section dependency-light.
# Nothing imported here should pull in scipy, xarray, pandas, torch, etc.
# ─────────────────────────────────────────────────────────────────────────────
from .core import AgentCore, AgentConfig


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API — single source of truth for `from src import *` semantics.
# Add lazy-loaded symbol names here as you grow the agent (see _LAZY_EXPORTS).
# ─────────────────────────────────────────────────────────────────────────────
__all__ = [
    "AgentCore",
    "AgentConfig",
]


# ─────────────────────────────────────────────────────────────────────────────
# LAZY IMPORTS — populate as you add heavyweight-dep submodules.
# Maps `public_name -> (".relative_submodule_path", "attribute_name")`.
# Empty by default; the `__getattr__` below is a no-op while empty.
# ─────────────────────────────────────────────────────────────────────────────
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    # Example (uncomment and adapt when adding scipy-gated capabilities):
    # "AcousticIndices":  (".acoustic_indices", "AcousticIndices"),
    # "SpectralAnalyzer": (".spectral",         "SpectralAnalyzer"),
}


def __getattr__(name: str):
    """PEP 562 module-level lazy attribute resolution.

    Triggered only when `name` is NOT already a module attribute, which
    means each lazy symbol is materialized at most once: after first
    access, normal attribute lookup hits the cached value and bypasses
    this function. No re-import overhead per call.

    Behavior:
      * Name in `_LAZY_EXPORTS` → import submodule, cache value on package,
        return value. If the submodule's heavy dep is missing, this raises
        `ModuleNotFoundError` (the correct signal — the lazy table is
        wired up, but the underlying dep isn't installed).
      * Name not in `_LAZY_EXPORTS` → raise `AttributeError`, matching
        Python's default behavior for unknown module attributes.
    """
    if name in _LAZY_EXPORTS:
        from importlib import import_module

        submod_path, attr = _LAZY_EXPORTS[name]
        submod = import_module(submod_path, package=__name__)
        value = getattr(submod, attr)
        # Cache on the package so subsequent attribute lookups are fast.
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """Expose lazy symbols to dir() / IDE completion alongside eager ones."""
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
