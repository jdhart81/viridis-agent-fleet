"""G1: SmartScale keeps working after the MCP gateway evicts `src*` modules.

The gateway loads ~30 agents into one process. Each agent's code lives in a
package named `src`, so between loads the gateway deletes every `src*` entry
from sys.modules and puts the next agent's root first on sys.path. Any
relative import that runs at call time instead of import time then resolves
against the LAST agent's `src` package and fails with ModuleNotFoundError.

G1  After loading the SmartScale core, evicting `src*` and putting a different
    `src` package first on sys.path, the paths behind the public MCP tools
    (measure_from_credit_card, measure, describe) still return results.
G2  The same holds for the natural-language "measure" route in
    src/agent/orchestrator.py: handle_message reaches the measurement service
    instead of raising ModuleNotFoundError on a call-time `.dsl` import.
G3  No module under smartscale-agent/src runs a relative or `src.` import
    inside a function body (static guard for G1/G2 regressions).
"""
import ast
import importlib
import sys
import types
from pathlib import Path

import pytest

AGENT_ROOT = Path(__file__).resolve().parents[1]


def _evict_src():
    for name in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
        del sys.modules[name]


@pytest.fixture
def gateway_like(tmp_path, monkeypatch):
    """Load SmartScale's `src`, then swap in another agent's `src` like the gateway."""
    other_root = tmp_path / "other-agent"
    (other_root / "src").mkdir(parents=True)
    (other_root / "src" / "__init__.py").write_text("")
    (other_root / "src" / "core.py").write_text("OTHER = True\n")

    saved = {m: sys.modules[m] for m in list(sys.modules)
             if m == "src" or m.startswith("src.")}
    _evict_src()
    monkeypatch.syspath_prepend(str(AGENT_ROOT))

    def switch_to_other_agent():
        # What the gateway does before loading the next agent.
        _evict_src()
        monkeypatch.syspath_prepend(str(other_root))
        importlib.import_module("src.core")
        assert sys.modules["src"].__file__.startswith(str(other_root))

    try:
        yield switch_to_other_agent
    finally:
        _evict_src()
        sys.modules.update(saved)


def test_G1_public_tool_paths_survive_src_eviction(gateway_like):
    core = importlib.import_module("src.core").SmartScaleCore()
    gateway_like()

    out = core.process({
        "action": "measure_from_credit_card",
        "image_id": "gateway-isolation",
        "credit_card_pixel_width": 856.0,
        "credit_card_pixel_height": 540.0,
        "objects": [{"label": "box", "pixel_width": 428.0, "pixel_height": 270.0}],
    })
    assert out.get("status") == "ok", out

    out = core.process({"action": "measure", "image_id": "gateway-isolation",
                        "detected_edges": []})
    assert out.get("status") == "ok", out

    out = core.process({"action": "describe"})
    assert out.get("status") == "ok", out


def test_G2_nl_measure_route_survives_src_eviction(gateway_like, monkeypatch):
    # The NL route's CV stack needs opencv and Pillow, which the gateway image
    # and this test environment do not ship. Stub just enough to import it;
    # the assertion is about import binding, not about computer vision.
    cv2 = types.ModuleType("cv2")
    cv2.aruco = types.SimpleNamespace(DICT_4X4_50=0, DICT_5X5_100=1, DICT_6X6_100=2)
    pil = types.ModuleType("PIL")
    pil.Image = types.SimpleNamespace(open=None)
    for name, mod in (("cv2", cv2), ("PIL", pil), ("PIL.Image", pil.Image)):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, mod)
    pytest.importorskip("pydantic")

    orch_mod = importlib.import_module("src.agent.orchestrator")
    dsl = importlib.import_module("src.agent.dsl")
    orch = orch_mod.Orchestrator()
    seen = {}

    def fake_measure(image_b64, options):
        seen["options"] = options
        return dsl.MeasureResult(ok=True, value_mm=10.0, method="stub")

    monkeypatch.setattr(orch.tools.measure, "measure_image_b64", fake_measure)
    gateway_like()

    out = orch.handle_message("measure this", "aGVsbG8=", {})
    assert out["type"] == "measure"
    assert out["result"]["ok"] is True
    assert isinstance(seen["options"], dsl.MeasureOptions)


def _call_time_internal_imports(path: Path):
    tree = ast.parse(path.read_text(), filename=str(path))
    hits = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if node.level > 0 or mod == "src" or mod.startswith("src."):
                    hits.append(f"{path.relative_to(AGENT_ROOT)}:{node.lineno}")
            elif isinstance(node, ast.Import):
                if any(a.name == "src" or a.name.startswith("src.") for a in node.names):
                    hits.append(f"{path.relative_to(AGENT_ROOT)}:{node.lineno}")
    return hits


def test_G3_no_call_time_internal_imports():
    hits = []
    for path in sorted((AGENT_ROOT / "src").rglob("*.py")):
        hits.extend(_call_time_internal_imports(path))
    assert hits == [], "call-time imports break under the gateway: " + ", ".join(hits)
