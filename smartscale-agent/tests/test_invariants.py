"""Spec-invariance tests for smartscale-agent (S1-S6). One test per invariant."""
import pytest
from src.core import SmartScaleCore, CR80_CREDIT_CARD_WIDTH_MM


@pytest.fixture
def core():
    return SmartScaleCore()


def test_S1_never_raises_error_envelope(core):
    r = core.process({"action": "measure_from_credit_card"})  # missing fields
    assert r["status"] == "error"
    assert "error_type" in r and "message" in r and "timestamp" in r


def test_S2_unknown_action_rejected(core):
    r = core.process({"action": "__nope__"})
    assert r["status"] == "error"
    assert r["error_type"] == "ValidationError"
    assert "measure_from_credit_card" in r["message"]


def test_S3_cr80_linear_scaling_deterministic(core):
    payload = {
        "action": "measure_from_credit_card",
        "image_id": "img-s3",
        "credit_card_pixel_width": 856.0,
        "objects": [{"name": "box", "pixel_width": 1712.0, "pixel_height": 856.0}],
    }
    r1 = core.process(payload)
    assert r1["status"] == "ok"
    cal = r1["result"]["calibration"]
    assert cal["pixels_per_mm"] == pytest.approx(856.0 / CR80_CREDIT_CARD_WIDTH_MM)
    obj = r1["result"]["objects"][0]
    assert obj["dimensions_mm"]["width"] == pytest.approx(171.2)
    assert obj["dimensions_mm"]["height"] == pytest.approx(85.6)
    r2 = core.process(payload)
    assert r2["result"]["objects"][0]["dimensions_mm"] == obj["dimensions_mm"]


def test_S4_describe_health_consistent(core):
    d = core.describe()
    h = core.health()
    assert d["name"] == h["agent"]
    assert d["capabilities"], "capabilities must be non-empty"


def test_S5_unknown_report_id_error_envelope(core):
    r = core.process({"action": "get_report", "report_id": "does-not-exist"})
    assert r["status"] == "error"
    assert "timestamp" in r


def test_S6_valid_measure_returns_dimensions(core):
    r = core.process({
        "action": "measure_from_credit_card",
        "image_id": "img-s6",
        "credit_card_pixel_width": 428.0,
        "objects": [{"name": "part", "pixel_width": 428.0, "pixel_height": 214.0}],
    })
    assert r["status"] == "ok"
    for obj in r["result"]["objects"]:
        assert "dimensions_mm" in obj and obj["dimensions_mm"]["width"] > 0
