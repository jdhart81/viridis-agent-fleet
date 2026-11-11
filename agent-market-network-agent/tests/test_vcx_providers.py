"""VCX trusted-provider boundaries and deterministic acceptance checks."""
from copy import deepcopy

import pytest

from vcx.providers import MAX_VALUES, ProviderRegistry, SUM_SERVICE, TAKEOFF_SERVICE


def slab_payload():
    return {"items": [{
        "assembly": "concrete_slab", "unit_system": "imperial",
        "dimensions": {
            "length": {"value": "20", "unit": "ft"},
            "width": {"value": "30", "unit": "ft"},
            "thickness": {"value": "4", "unit": "in"},
        },
    }]}


def test_fixed_services_and_no_runtime_registration():
    registry = ProviderRegistry()
    assert {s["service_id"] for s in registry.services()} == {SUM_SERVICE, TAKEOFF_SERVICE}
    assert not hasattr(registry, "register")
    with pytest.raises(ValueError, match="allowlisted"):
        registry.execute("https://untrusted.example/run", {"values": [1]})


def test_integer_sum_acceptance_and_tampering():
    registry = ProviderRegistry()
    payload = {"values": [-10, 20, 5]}
    original = deepcopy(payload)
    output = registry.execute(SUM_SERVICE, payload)
    assert output == {"sum": 15, "count": 3}
    assert payload == original
    assert registry.verify(SUM_SERVICE, payload, output)
    assert not registry.verify(SUM_SERVICE, {"values": [1]}, output)
    assert not registry.verify(SUM_SERVICE, payload, {"sum": 15, "count": 3, "extra": 1})
    assert not registry.verify(SUM_SERVICE, payload, {"sum": 15.0, "count": 3})


@pytest.mark.parametrize("payload", [
    {"values": []}, {"values": [True]}, {"values": [1.0]},
    {"values": [10**10]}, {"values": [1] * (MAX_VALUES + 1)},
    {"values": [1], "api_key": "hidden"},
    {"values": [1], "callback_url": "https://example.test"},
    {"values": ["Bearer secret"]}, {"values": ["sk_test_example"]},
    {"values": [[[[[[[[[[[[[[1]]]]]]]]]]]]]]},
])
def test_provider_rejects_unsafe_payloads_without_echo(payload):
    with pytest.raises(ValueError) as exc:
        ProviderRegistry().execute(SUM_SERVICE, payload)
    assert "hidden" not in str(exc.value)
    assert "https://" not in str(exc.value)
    assert "Bearer secret" not in str(exc.value)
    assert "sk_test_example" not in str(exc.value)


def test_real_fleet_takeoff_is_reproducible_and_bound_to_inputs():
    registry = ProviderRegistry()
    payload = slab_payload()
    output = registry.execute(TAKEOFF_SERVICE, payload)
    assert output["line_items"][0]["net_qty"] == "7.407"
    assert output["material_pack"]["sha256"]
    assert registry.execute(TAKEOFF_SERVICE, payload) == output
    assert registry.verify(TAKEOFF_SERVICE, payload, output)
    output["line_items"][0]["net_qty"] = "0"
    assert not registry.verify(TAKEOFF_SERVICE, payload, output)


@pytest.mark.parametrize("change", [
    lambda p: p["items"][0].update({"path": "/etc/passwd"}),
    lambda p: p["items"][0].update({"assembly": "unsupported"}),
    lambda p: p["items"][0]["dimensions"]["width"].update({"value": "1e999999"}),
    lambda p: p["items"][0]["dimensions"]["width"].update({"value": "0"}),
    lambda p: p["items"][0]["dimensions"]["width"].update({"unit": ["ft"]}),
    lambda p: p.update({"options": {"private_key": "secret"}}),
    lambda p: p.update({"items": p["items"] * 26}),
])
def test_takeoff_strict_schema_and_resource_limits(change):
    payload = slab_payload()
    change(payload)
    with pytest.raises(ValueError):
        ProviderRegistry().execute(TAKEOFF_SERVICE, payload)
