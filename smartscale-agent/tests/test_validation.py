"""
Validation tests for SmartScaleCore — pins the process() input contract.

Covers validate_process_input: action gating, per-action required fields,
image_data byte-range guards, detected_edges shape, reference_type, report_id,
and limit clamping. Added by Nightkeeper (2026-06-15, Night 56) as the C2
test-coverage rollout for the near-deploy stage.

Run with: python -m pytest smartscale-agent/tests/test_validation.py
"""

import pytest

from src.validation import (
    validate_process_input,
    ValidationError,
    VALID_ACTIONS,
    LIST_LIMIT_MAX,
    LIST_LIMIT_DEFAULT,
    CREDIT_CARD_OBJECTS_MAX,
    OBJECT_LABEL_MAX,
)


def _measure(**over):
    base = {"action": "measure", "image_id": "img1", "image_data": b"\x01",
            "detected_edges": []}
    base.update(over)
    return base


# --- action gating ---------------------------------------------------------

def test_non_dict_input_raises():
    with pytest.raises(ValidationError):
        validate_process_input("not a dict")


def test_all_valid_actions_accepted():
    # Every member of VALID_ACTIONS must dispatch without error given minimal valid payload.
    payloads = {
        "measure": _measure(),
        "measure_from_credit_card": {
            "action": "measure_from_credit_card", "image_id": "i1",
            "credit_card_pixel_width": 200.0,
            "objects": [{"pixel_width": 10, "pixel_height": 20}],
        },
        "get_report": {"action": "get_report", "report_id": "r1"},
        "list_reports": {"action": "list_reports", "limit": 10},
        "get_stats": {"action": "get_stats"},
        "describe": {"action": "describe"},
    }
    # Guard against a member being whitelisted but having no validation branch wired.
    assert set(payloads) == set(VALID_ACTIONS)
    for action, payload in payloads.items():
        out = validate_process_input(payload)
        assert out["action"] == action


def test_unknown_action_raises():
    with pytest.raises(ValidationError):
        validate_process_input({"action": "teleport"})


def test_empty_action_raises():
    with pytest.raises(ValidationError):
        validate_process_input({"action": ""})


def test_action_defaults_to_measure_requires_image_id():
    # Omitting action defaults to "measure"; image_id then becomes required.
    with pytest.raises(ValidationError):
        validate_process_input({"image_data": b""})


# --- image_id --------------------------------------------------------------

def test_missing_image_id_for_measure_raises():
    with pytest.raises(ValidationError):
        validate_process_input({"action": "measure", "image_data": b""})


def test_empty_image_id_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_measure(image_id=""))


def test_image_id_too_long_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_measure(image_id="x" * 513))


def test_image_id_is_stripped():
    out = validate_process_input(_measure(image_id="  cam1  "))
    assert out["image_id"] == "cam1"


# --- image_data ------------------------------------------------------------

def test_image_data_bytes_ok():
    out = validate_process_input(_measure(image_data=b"\x00\xff"))
    assert out["image_data"] == b"\x00\xff"


def test_image_data_list_of_ints_ok():
    out = validate_process_input(_measure(image_data=[0, 128, 255]))
    assert out["image_data"] == [0, 128, 255]


def test_image_data_list_float_element_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_measure(image_data=[0, 1.5, 255]))


def test_image_data_list_out_of_range_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_measure(image_data=[0, 300, 255]))


def test_image_data_wrong_type_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_measure(image_data="jpeg"))


# --- detected_edges --------------------------------------------------------

def test_detected_edges_valid():
    out = validate_process_input(_measure(detected_edges=[{"area": 100}, {"area": 5}]))
    assert len(out["detected_edges"]) == 2


def test_detected_edges_not_list_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_measure(detected_edges="none"))


def test_detected_edges_element_not_dict_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_measure(detected_edges=["bad"]))


# --- reference_type --------------------------------------------------------

def test_reference_type_known_ok():
    out = validate_process_input(_measure(reference_type="us_penny"))
    assert out["reference_type"] == "us_penny"


def test_reference_type_unknown_warns_not_raises():
    # Unknown reference type is advisory only — must not raise.
    out = validate_process_input(_measure(reference_type="custom_chip"))
    assert out["reference_type"] == "custom_chip"


def test_reference_type_non_string_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_measure(reference_type=42))


# --- credit-card path ------------------------------------------------------

def test_credit_card_missing_objects_raises():
    with pytest.raises(ValidationError):
        validate_process_input({
            "action": "measure_from_credit_card", "image_id": "i1",
            "credit_card_pixel_width": 200.0, "objects": [],
        })


def test_credit_card_bad_pixel_width_raises():
    with pytest.raises(ValidationError):
        validate_process_input({
            "action": "measure_from_credit_card", "image_id": "i1",
            "credit_card_pixel_width": 200.0,
            "objects": [{"pixel_width": -1, "pixel_height": 20}],
        })


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_credit_card_non_finite_reference_width_raises(value):
    with pytest.raises(ValidationError):
        validate_process_input({
            "action": "measure_from_credit_card", "image_id": "i1",
            "credit_card_pixel_width": value,
            "objects": [{"pixel_width": 10, "pixel_height": 20}],
        })


@pytest.mark.parametrize("field", ["pixel_width", "pixel_height",
                                    "pixel_area", "pixel_perimeter",
                                    "confidence"])
def test_credit_card_non_finite_object_number_raises(field):
    obj = {"pixel_width": 10, "pixel_height": 20, field: float("inf")}
    with pytest.raises(ValidationError):
        validate_process_input({
            "action": "measure_from_credit_card", "image_id": "i1",
            "credit_card_pixel_width": 200.0, "objects": [obj],
        })


def test_credit_card_object_count_is_bounded():
    objects = [
        {"pixel_width": 10, "pixel_height": 20}
        for _ in range(CREDIT_CARD_OBJECTS_MAX + 1)
    ]
    with pytest.raises(ValidationError):
        validate_process_input({
            "action": "measure_from_credit_card", "image_id": "i1",
            "credit_card_pixel_width": 200.0, "objects": objects,
        })


def test_credit_card_validates_every_object_not_only_prefix():
    objects = [
        {"pixel_width": 10, "pixel_height": 20}
        for _ in range(CREDIT_CARD_OBJECTS_MAX)
    ]
    objects[-1]["pixel_width"] = -1
    with pytest.raises(ValidationError):
        validate_process_input({
            "action": "measure_from_credit_card", "image_id": "i1",
            "credit_card_pixel_width": 200.0, "objects": objects,
        })


def test_credit_card_label_length_is_bounded():
    with pytest.raises(ValidationError):
        validate_process_input({
            "action": "measure_from_credit_card", "image_id": "i1",
            "credit_card_pixel_width": 200.0,
            "objects": [{
                "label": "x" * (OBJECT_LABEL_MAX + 1),
                "pixel_width": 10,
                "pixel_height": 20,
            }],
        })


# --- report_id / limit -----------------------------------------------------

def test_missing_report_id_raises():
    with pytest.raises(ValidationError):
        validate_process_input({"action": "get_report"})


def test_limit_zero_raises():
    with pytest.raises(ValidationError):
        validate_process_input({"action": "list_reports", "limit": 0})


def test_limit_clamped_to_max():
    out = validate_process_input({"action": "list_reports", "limit": 99999})
    assert out["limit"] == LIST_LIMIT_MAX


def test_non_int_limit_defaults():
    out = validate_process_input({"action": "list_reports", "limit": "all"})
    assert out["limit"] == LIST_LIMIT_DEFAULT
