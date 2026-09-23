"""Static contract tests for subscription capital visibility in the deck."""

from pathlib import Path


DECK = (Path(__file__).resolve().parent / "deck.html").read_text()


def test_deck_reads_only_top_level_aggregate_subscription_state():
    assert "function subscriptionMetrics(d)" in DECK
    assert "d.subscriptions" in DECK
    assert "active_subscriptions" in DECK
    assert "mrr_minor" in DECK
    assert "plan_mix" in DECK
    assert "summary.plan_mix ?? checks.plan_mix" in DECK
    assert "surface.frontdoor_funnel" in DECK
    assert "funnel.page_views" in DECK
    assert "funnel.checkouts_started" in DECK
    assert "funnel.seat_source_views" in DECK
    assert "funnel.seat_attributed_views" in DECK
    assert "funnel.seat_unattributed_views" in DECK
    assert "funnel.snapshot_page_views" in DECK
    assert "funnel.snapshot_checkouts_started" in DECK
    assert "funnel.snapshot_paid" in DECK


def test_deck_renders_capital_kpis_and_plan_mix():
    assert "Active B2B subscriptions" in DECK
    assert "Recurring MRR" in DECK
    assert "Subscription capital engine" in DECK
    assert "planMixText(subs.planMix)" in DECK
    assert "Seat page views" in DECK
    assert "Seat checkouts started" in DECK
    assert "Snapshot page views" in DECK
    assert "Snapshot checkouts started" in DECK
    assert "Snapshots paid" in DECK
    assert "Attributed seat sources" in DECK
    assert "sourceMixText(subs.seatSourceViews)" in DECK
    assert '"x402_success"' in DECK
    assert "aggregate telemetry, not unique buyers or revenue" in DECK


def test_deck_renders_the_full_seat_conversion_funnel_and_mrr_strip():
    assert 'aria-label="Seat conversion funnel"' in DECK
    for label in ("page views", "checkout starts", "active seats", "MRR"):
        assert f">{label}</span>" in DECK
    assert "subs.pageViews" in DECK
    assert "subs.checkoutsStarted" in DECK
    assert "subs.active" in DECK
    assert "subs.mrrMinor" in DECK


def test_deck_renders_the_compliance_snapshot_conversion_funnel():
    assert 'aria-label="Compliance snapshot conversion funnel"' in DECK
    for label in ("snapshot views", "snapshot checkout starts", "snapshots paid"):
        assert f">{label}</span>" in DECK
    assert "subs.snapshotPageViews" in DECK
    assert "subs.snapshotCheckoutsStarted" in DECK
    assert "subs.snapshotPaid" in DECK


def test_deck_never_requests_or_names_private_subscription_identifiers():
    # The health contract is aggregate-only.  Keeping these names out of the
    # deck prevents a future UI edit from accidentally depending on private
    # account, bearer, customer, or subscription records.
    for forbidden in (
        "account_key",
        "account_id",
        "stripe_customer_id",
        "subscription_id",
        "client_reference_id",
    ):
        assert forbidden not in DECK


def test_new_distribution_surfaces_remain_live_and_version_gated():
    assert "New surfaces publish only after their live health and version gates pass." in DECK
    assert "Distribution complete" not in DECK


def test_disclosure_compiler_has_compliance_role_and_two_dollar_price():
    assert '"disclosure-compiler":"revenue · compliance"' in DECK
    assert '"disclosure-compiler":200' in DECK
    assert '"disclosure-compiler": 200' in DECK
    assert "disclosure-compiler $2" in DECK
