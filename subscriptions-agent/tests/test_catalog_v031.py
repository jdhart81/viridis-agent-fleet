"""Truth and conservation gates for the approved v0.3.1 seat catalog."""

import asyncio
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))
for module_name in [name for name in list(sys.modules)
                    if name == "src" or name.startswith("src.")]:
    del sys.modules[module_name]

from src.core import AgentConfig, build  # noqa: E402


DATA = AGENT_ROOT / "data"
OLD_PATH = DATA / "plan_catalog.v0.3.0.json"
NEW_PATH = DATA / "plan_catalog.v0.3.1.json"
EXPECTED = {
    "energy-seat": ("price_1TtW3EDTpwaqE8SsY84gwMZm", 24900),
    "taxcredit-seat": ("price_1TtW3FDTpwaqE8Ss1dJNWrrG", 14900),
    "climate-seat": ("price_1TtW3FDTpwaqE8Ss6CicwvSe", 14900),
    "compliance-seat": ("price_1TtW3GDTpwaqE8SsIbqgzS6T", 14900),
    "ghg-seat": ("price_1TtW3GDTpwaqE8SsEapXz1an", 9900),
}


def load(path):
    return json.loads(path.read_text())


def test_v031_preserves_every_commercial_term_and_changes_only_truth_copy():
    old = load(OLD_PATH)
    new = load(NEW_PATH)

    old_root = deepcopy(old)
    new_root = deepcopy(new)
    for catalog in (old_root, new_root):
        catalog.pop("pack_version")
        catalog.pop("effective_as_of")
        catalog.pop("configuration_notice")
        catalog.pop("sources")
        for plan in catalog["plans"]:
            plan.pop("coverage_note")
    assert old_root == new_root
    assert new["pack_version"] == "0.3.1"
    assert new["effective_as_of"] == "2026-07-27"
    assert new["sources"][:-1] == old["sources"]
    assert new["sources"][-1]["id"] == \
        "stripe-live-catalog-readback-2026-07-27"


def test_v031_exact_live_contract_is_internally_consistent():
    catalog = load(NEW_PATH)
    plans = {plan["id"]: plan for plan in catalog["plans"]}
    assert set(plans) == set(EXPECTED)
    assert catalog["default_included_calls_per_month"] == 1000
    assert "remain intentionally null" not in catalog["configuration_notice"]
    assert "remains draft" not in catalog["configuration_notice"]
    for plan_id, (price_id, amount) in EXPECTED.items():
        plan = plans[plan_id]
        assert plan["stripe_price_id"] == price_id
        assert plan["price_minor"] == amount
        assert plan["interval"] == "month"
        assert plan["included_calls_per_month"] == 1000
        assert plan["approval_status"] == "approved"
        assert plan["checkout_enabled"] is True
        assert plan["coverage_ready"] is True
        assert "remain required" not in plan["coverage_note"]


def test_v031_core_reports_five_ready_plans_without_creating_checkout():
    raw = NEW_PATH.read_bytes()
    catalog = json.loads(raw)
    provider = object()
    core = build(AgentConfig(
        catalog=catalog,
        catalog_sha256=hashlib.sha256(raw).hexdigest(),
        stripe_provider=provider,
    ))
    listed = core.list_plans()
    assert listed["pack_version"] == "0.3.1"
    assert len(listed["plans"]) == 5
    assert all(plan["checkout_status"] == "ready"
               and plan["configuration_required"] is False
               for plan in listed["plans"])
    health = asyncio.run(core.health())
    assert health["checks"]["checkout_ready_plans"] == 5
    assert core.frontdoor_summary()["checkouts_started"] == 0
