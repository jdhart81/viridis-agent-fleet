"""Full-result determinism pin for the PAID path (N64 idiom, propagated N68).

SmartScale's revenue model bills $0.50 per "deterministic scaling call".
That claim was previously enforced only indirectly (unit math tests).
These tests pin it mechanically: the ENTIRE data payload of
measure_from_credit_card is byte-identical across FRESH core instances.
The envelope timestamp is live by design (same as green-router, N67),
so comparison strips exactly TWO live fields: the top-level envelope
timestamp and result["timestamp"] (scale_from_credit_card stamps its own
envelope). Every measurement datum must be byte-stable.

Also pins the ValidationError gate on non-finite paid-path inputs
(inf/NaN in credit_card_pixel_width / object geometry), the input-bounds
class flagged in the 2026-07-23 adversarial review.
"""

import json

import pytest

from src.core import SmartScaleCore


PAID_INPUT = {
    "action": "measure_from_credit_card",
    "image_id": "det-pin-001",
    "credit_card_pixel_width": 856.0,
    "credit_card_pixel_height": 540.0,
    "objects": [
        {"object_id": "obj-a", "pixel_width": 428.0, "pixel_height": 270.0,
         "pixel_area": 115560.0},
        {"object_id": "obj-b", "pixel_width": 107.0, "pixel_height": 67.5},
    ],
}

DIVERGENT_INPUT = {
    **PAID_INPUT,
    # Half the reference scale on BOTH axes (aspect preserved so the CR80
    # distortion refusal does not fire) -> object mm dimensions double.
    "credit_card_pixel_width": 428.0,
    "credit_card_pixel_height": 270.0,
}


def _data_payload(envelope: dict) -> str:
    """Canonical JSON minus the two live-by-design timestamp fields
    (outer envelope + inner result envelope). Nothing else is stripped."""
    assert envelope.get("status") == "ok", envelope
    stripped = {k: v for k, v in envelope.items() if k != "timestamp"}
    result = stripped.get("result")
    if isinstance(result, dict):
        stripped["result"] = {k: v for k, v in result.items() if k != "timestamp"}
    return json.dumps(stripped, sort_keys=True, default=str)


def test_paid_result_byte_identical_across_fresh_cores():
    """Same input, fresh core instances -> byte-identical data payload."""
    payloads = []
    for _ in range(3):
        core = SmartScaleCore()
        out = core.process(json.loads(json.dumps(PAID_INPUT)))
        payloads.append(_data_payload(out))
    assert payloads[0] == payloads[1] == payloads[2]


def test_paid_result_repeat_within_one_core_is_pure():
    """Repeated identical calls on ONE core do not drift (no hidden state
    leaks into the paid result)."""
    core = SmartScaleCore()
    first = _data_payload(core.process(dict(PAID_INPUT)))
    second = _data_payload(core.process(dict(PAID_INPUT)))
    assert first == second


def test_non_triviality_divergent_input_diverges():
    """Guard against a vacuous pin: a different reference width must
    produce a DIFFERENT payload (so byte-equality above is meaningful)."""
    core_a = SmartScaleCore()
    core_b = SmartScaleCore()
    a = _data_payload(core_a.process(dict(PAID_INPUT)))
    b = _data_payload(core_b.process(dict(DIVERGENT_INPUT)))
    assert a != b


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_paid_gate_rejects_non_finite_reference_width(bad):
    """Input-bounds pin (2026-07-23 review class): non-finite card width
    must be refused at the validation gate, never priced or computed."""
    core = SmartScaleCore()
    payload = dict(PAID_INPUT)
    payload["credit_card_pixel_width"] = bad
    out = core.process(payload)
    assert out.get("status") == "error"
    assert out.get("error_type") == "ValidationError"


@pytest.mark.parametrize("bad", [float("inf"), float("nan")])
def test_paid_gate_rejects_non_finite_object_geometry(bad):
    """Non-finite object pixel geometry is refused, not scaled."""
    core = SmartScaleCore()
    payload = json.loads(json.dumps(PAID_INPUT))
    payload["objects"][0]["pixel_width"] = bad
    out = core.process(payload)
    assert out.get("status") == "error"
    assert out.get("error_type") == "ValidationError"
