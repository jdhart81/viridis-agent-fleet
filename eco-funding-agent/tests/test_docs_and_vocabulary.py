"""Docs exist, carry the required notices, and never describe anything as an investment,
security, return or yield (the spec's vocabulary limit). Also pins the method version:
if valuation output for the reference site changes, METHOD_VERSION must change too."""

from __future__ import annotations

import json
import re

import pytest
from conftest import ROOT

from viridis_eco_funding import METHOD_VERSION, describe_method, make_receipt, value_site
from viridis_eco_funding.canonical import sha256_hex, to_plain_json

DOCS = ["README.md", "METHOD.md", "LIMITS.md", "AGENTS.md", "llms.txt", "NOTICE", "CHANGELOG.md",
        "docs/INVARIANTS.md", "agent.yaml", "deploy/fleet/MOUNT.md", "deploy/fleet/QUICKSTART_SNIPPET.md",
        "deploy/fleet/server.json", "deploy/fleet/tools.json"]
FORBIDDEN = [r"\binvest\w*", r"\bsecurit(?:y|ies)\b", r"\breturns?\b", r"\byields?\b", r"\bROI\b",
             r"\bdividends?\b", r"\bprofits?\b", r"\binterest rate", r"\bAPY\b", r"\bAPR\b",
             r"\bstaking\b"]


def user_facing_texts():
    for name in DOCS:
        yield name, (ROOT / name).read_text(encoding="utf-8")
    notebook = json.loads((ROOT / "examples" / "woodland_valuation.ipynb").read_text())
    for i, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "markdown":
            yield f"notebook cell {i}", "".join(cell["source"])
    yield "describe_method", json.dumps(to_plain_json(describe_method()))
    from viridis_eco_funding.fleet import build as _build_fleet
    yield "fleet describe", json.dumps(_build_fleet().describe())
    pytest.importorskip("mcp")
    import asyncio

    from viridis_eco_funding.fleet import INSTRUCTIONS
    yield "mcp instructions", INSTRUCTIONS
    try:
        from viridis_eco_funding.mcp_server import build_server
    except ImportError:  # mcp 1.x: only the fleet adapter is available
        build_server = None
    if build_server is not None:
        for tool in asyncio.run(build_server().list_tools()):
            yield f"tool {tool.name}", tool.description
    import importlib.util
    spec = importlib.util.spec_from_file_location("vocab_adapter", ROOT / "adapters" / "mcp_server.py")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    for tool in asyncio.run(adapter.mcp.list_tools()):
        yield f"adapter tool {tool.name}", tool.description


def test_docs_exist():
    for name in DOCS + ["LICENSE", "examples/woodland_valuation.ipynb", "CITATION.cff"]:
        assert (ROOT / name).is_file(), name


def test_vocabulary_limits():
    hits = []
    for name, text in user_facing_texts():
        for pattern in FORBIDDEN:
            for m in re.finditer(pattern, text, flags=re.IGNORECASE):
                hits.append(f"{name}: {m.group(0)!r} ...{text[max(0, m.start()-40):m.end()+40]!r}")
    assert not hits, "\n".join(hits)


def test_vocabulary_in_valuation_and_simulation_outputs(woodland_site, example_pool):
    from viridis_eco_funding import simulate_pool
    texts = [value_site(woodland_site)["explanation"],
             simulate_pool(example_pool, [{"period": 0, "receipt": make_receipt(woodland_site)}])["explanation"]]
    for text in texts:
        for pattern in FORBIDDEN:
            assert not re.search(pattern, text, flags=re.IGNORECASE), pattern


def test_readme_notice_and_license():
    readme = (ROOT / "README.md").read_text()
    assert "legal review before money moves" in readme
    assert "NOTICE" in readme
    assert "Apache License" in (ROOT / "LICENSE").read_text()
    assert "Version 2.0" in (ROOT / "LICENSE").read_text()


def test_method_doc_labels_conjecture_and_cites_sources():
    method = (ROOT / "METHOD.md").read_text()
    for needle in ("conjecture", "10.5281/zenodo.19543988", "Physical Review E", "Landauer",
                   "Saura", "Wolpert"):
        assert needle in method, needle


def test_agent_discovery_files():
    llms = (ROOT / "llms.txt").read_text()
    assert llms.startswith("# viridis-eco-funding")
    for tool in ("value_site", "explain_valuation", "verify_receipt", "simulate_pool", "describe_method"):
        assert tool in llms and tool in (ROOT / "AGENTS.md").read_text()


REFERENCE_DIGEST = "8f16346a9168e184570c06cdc7d68efaf712262b442df71b74fc063772c17b0d"


def test_method_version_pin(woodland_site):
    """Update REFERENCE_DIGEST *and* bump METHOD_VERSION together, never one alone."""
    digest = sha256_hex(value_site(woodland_site))
    assert METHOD_VERSION == "vef-method/0.1.0"
    assert digest == REFERENCE_DIGEST, f"valuation output changed: new digest {digest}"


def test_notebook_outputs_match_current_code(woodland_site, synthetic_record):
    """The executed notebook must show what the code produces today (re-run
    examples/build_notebook.py after any method change)."""
    from viridis_eco_funding.vergecommon import bind_project

    notebook = json.loads((ROOT / "examples" / "woodland_valuation.ipynb").read_text())
    text = "".join("".join(o.get("text", "")) for c in notebook["cells"] if c["cell_type"] == "code"
                   for o in c.get("outputs", []))
    assert "Traceback" not in text and "Error" not in text
    url = "https://vergecommon.com/api/network?id=" + synthetic_record["coop"]["id"]
    source = bind_project(synthetic_record, "proj-woodland-01", url, woodland_site["observed_at"])
    seal = make_receipt(woodland_site, source=source)["seal"]["digest"]
    assert f"seal digest: {seal}" in text
    assert "valid: True" in text and "tampered receipt valid: False" in text
    assert "'conservation': True" in text
