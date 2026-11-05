"""G1: the agent keeps working after the MCP gateway evicts `src*` modules.

The gateway loads ~30 agents into one process. Each agent's code lives in a
package named `src`, so between loads the gateway deletes every `src*` entry
from sys.modules and puts the next agent's root first on sys.path. Any
relative import that runs at call time instead of import time then resolves
against the LAST agent's `src` package and fails with ModuleNotFoundError.

G1  After loading the radar core, evicting `src*` and putting a different
    `src` package first on sys.path, assess_compliance (with and without
    entity_profile and revenue) still returns a result, never InternalError.
"""
import asyncio
import importlib
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]


def _evict_src():
    for name in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
        del sys.modules[name]


def test_G1_assess_survives_gateway_style_src_eviction(tmp_path, monkeypatch):
    other_root = tmp_path / "other-agent"
    (other_root / "src").mkdir(parents=True)
    (other_root / "src" / "__init__.py").write_text("")
    (other_root / "src" / "core.py").write_text("OTHER = True\n")

    saved = {m: sys.modules[m] for m in list(sys.modules)
             if m == "src" or m.startswith("src.")}
    try:
        _evict_src()
        monkeypatch.syspath_prepend(str(AGENT_ROOT))
        core_mod = importlib.import_module("src.core")
        core = core_mod.RegulatoryRadarCore()

        # What the gateway does before loading the next agent.
        _evict_src()
        monkeypatch.syspath_prepend(str(other_root))
        importlib.import_module("src.core")
        assert sys.modules["src"].__file__.startswith(str(other_root))

        base = {"action": "assess",
                "company_name": "Gateway Isolation Co", "sector": "manufacturing",
                "jurisdiction": "US",
                "disclosures": ["GHG Protocol", "Scope 1", "Scope 2"]}
        cases = [
            base,
            {**base, "annual_revenue_usd": 2e9, "prior_year_revenue_usd": 2e9,
             "entity_profile": {"entity_form": "corporation",
                                "formed_under_us_law": True,
                                "does_business_in_california": True,
                                "exemption": "none"}},
        ]
        for case in cases:
            out = asyncio.run(core.process(case))
            assert out.get("status") == "success", out
        levels = [asyncio.run(core.process(c))["result"]["overall_compliance_level"]
                  for c in cases]
        assert levels[0] == "undetermined"
    finally:
        _evict_src()
        sys.modules.update(saved)
