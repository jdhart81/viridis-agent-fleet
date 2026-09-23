import pytest

from scripts import agentfeeds_viridis_unsigned_workflow as workflow


def _plan(**overrides):
    args = {
        "address": "0x1111111111111111111111111111111111111111",
        "jurisdiction": "US",
        "sector": "energy",
        "query": "climate disclosure requirements",
        "framework": "ifrs-s2",
        "company_facts": {
            "company_name": "Buyer Supplied Example",
            "reporting_period": "2026",
        },
    }
    args.update(overrides)
    return workflow.build_plan(**args)


def test_plan_is_offline_unsigned_and_never_auto_follows():
    plan = _plan()
    assert plan["state"] == "local_draft_not_published"
    assert plan["execution"] == {
        "network_requests_performed": 0,
        "wallet_loaded": False,
        "payment_authorized": False,
        "paid_retry_allowed": False,
        "automatic_follow_on_allowed": False,
    }
    assert plan["publication_gate"]["ready"] is False
    assert [step["sequence"] for step in plan["steps"]] == [1, 2, 3]
    assert all(
        "advertised_price_usdc_non_authoritative" in step
        for step in plan["steps"]
    )


def test_plan_preserves_buyer_inputs_and_fresh_authorization_boundaries():
    plan = _plan(jurisdiction="california")
    sanctions, radar, disclosure = plan["steps"]
    assert sanctions["request"]["query"]["address"].startswith("0x1111")
    assert radar["request"]["json"]["jurisdiction"] == "US-CA"
    assert "a separate buyer route-and-amount authorization" in \
        radar["requires"]
    assert disclosure["request"]["json"]["company_facts"]["company_name"] == \
        "Buyer Supplied Example"
    assert "a separate buyer route-and-amount authorization" in \
        disclosure["requires"]


def test_invalid_or_empty_buyer_inputs_fail_closed():
    with pytest.raises(ValueError, match="20-100"):
        _plan(address="short")
    with pytest.raises(ValueError, match="non-empty"):
        _plan(company_facts={})
    with pytest.raises(ValueError, match="jurisdiction"):
        _plan(jurisdiction="MARS")
