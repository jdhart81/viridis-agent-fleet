"""Regression tests for the 2026-11-11 independent review (R1-R9).

Each test fails on the pre-review build. All balances are simulated.
"""
from __future__ import annotations

import logging
from pathlib import Path
import sys

import pytest

AGENT = Path(__file__).resolve().parents[1]
for directory in (AGENT.parent, AGENT, AGENT / 'tests'):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from fleet_utils.orc import verify as verify_orc
from test_vcx_exchange import Harness
from vcx.exchange import ComputeExchange, digest
from vcx.identity import MarketIdentity
from vcx.ledger import LedgerError


@pytest.fixture
def h(tmp_path):
    item = Harness(tmp_path)
    yield item
    item.close()


def budget(h, actor):
    return h.exchange.ledger.budget(actor)


def verified(h):
    job = h.submitted()
    return h.call('verify_compute_result', body={'job_id': job['job_id']})


# R1 - accepted work is paid ------------------------------------------------

@pytest.mark.parametrize('stage', ['submitted', 'verified'])
def test_r1_buyer_cannot_cancel_delivered_work(h, stage):
    h.register()
    job = h.submitted() if stage == 'submitted' else verified(h)
    h.reject('cancel_compute', body={'job_id': job['job_id']})
    assert budget(h, 'buyer-one')['held_minor'] == 200
    assert h.exchange.reconcile()['status'] == 'ok'


def test_r1_buyer_stalling_past_the_lease_does_not_avoid_payment(h):
    h.register()
    job = verified(h)
    h.clock.value += 3600  # far past every lease
    settled = h.call('settle_compute', 'seller-one', {'job_id': job['job_id']})
    assert settled['state'] == 'SETTLED'
    assert budget(h, 'seller-one')['pending_earnings_minor'] == 190
    assert budget(h, 'buyer-one')['available_minor'] == 800


def test_r1_recovery_settles_lapsed_delivered_work(h):
    h.register(capacity=2)
    first = verified(h)
    second = h.submitted('buyer-two')
    h.clock.value += 600
    states = {x['job_id']: x['state'] for x in h.exchange.recover()['recovered']}
    assert states == {first['job_id']: 'SETTLED', second['job_id']: 'SETTLED'}
    assert budget(h, 'seller-one')['pending_earnings_minor'] == 380
    assert h.exchange.reconcile()['status'] == 'ok'


def test_r1_delivery_is_disclosed_only_after_settlement(h):
    h.register()
    job = h.submitted()
    assert 'output' not in job and job['output_withheld_until_settlement'] is True
    assert job['output_sha256']
    done = h.call('verify_compute_result', body={'job_id': job['job_id']})
    assert 'output' not in done
    assert 'output' not in h.call('get_compute_job', body={'job_id': job['job_id']})
    settled = h.call('settle_compute', body={'job_id': job['job_id']})
    assert settled['output'] == {'count': 3, 'sum': 11}
    assert digest(settled['output']) == job['output_sha256']


def test_r1_dispute_freezes_and_needs_a_third_party_decision(h):
    h.register()
    job = verified(h)
    h.call('dispute_compute', body={'job_id': job['job_id']})
    h.reject('refund_compute', body={'job_id': job['job_id']})         # buyer cannot self-refund
    h.clock.value += 3600
    assert h.exchange.recover()['recovered'] == []                     # no automatic release
    assert budget(h, 'buyer-one')['held_minor'] == 200
    with pytest.raises(ValueError):
        h.exchange.resolve_dispute(job['job_id'], 'payout', 'case-1')
    settled = h.exchange.resolve_dispute(job['job_id'], 'settle', 'case-1')
    assert settled['state'] == 'SETTLED' and settled['dispute_resolution']['resolver_ref'] == 'case-1'
    assert h.exchange.resolve_dispute(job['job_id'], 'settle', 'case-1')['state'] == 'SETTLED'
    with pytest.raises(ValueError):
        h.exchange.resolve_dispute(job['job_id'], 'refund', 'case-2')
    assert budget(h, 'seller-one')['pending_earnings_minor'] == 190
    assert h.exchange.reconcile()['status'] == 'ok'


def test_r1_arbitrated_refund_releases_once_without_disclosing_output(h):
    h.register()
    job = h.submitted()
    h.call('dispute_compute', body={'job_id': job['job_id']})
    refunded = h.exchange.resolve_dispute(job['job_id'], 'refund', 'case-9')
    assert refunded['state'] == 'REFUNDED' and 'output' not in refunded
    assert budget(h, 'buyer-one') ['available_minor'] == 1000
    assert h.exchange.reconcile()['marketplace_fees_minor'] == 0
    assert 'resolve_dispute' not in str(h.exchange.process(
        h.request('resolve_dispute', 'buyer-one', {'job_id': job['job_id']})))


# R2 - expired leases do not consume capacity --------------------------------

def test_r2_abandoned_reservation_frees_capacity_without_a_scheduler(h):
    h.register(capacity=1)
    job = h.create()
    h.reserve(job)
    h.clock.value += 600                      # buyer-one walks away; nobody runs recover()
    other = h.create('buyer-two')
    quotes = h.quote(other, 'buyer-two')
    assert len(quotes) == 1
    assert budget(h, 'buyer-one')['held_minor'] == 0     # the stale hold was released
    h.reserve(other, 'buyer-two', quote=quotes[0])
    assert h.exchange.reconcile()['status'] == 'ok'


def test_r2_delivered_or_disputed_work_does_not_occupy_a_slot(h):
    h.register(capacity=1)
    job = h.submitted()
    h.call('dispute_compute', body={'job_id': job['job_id']})
    assert len(h.quote(h.create('buyer-two'), 'buyer-two')) == 1


# R3 - a signature is valid for one exchange ----------------------------------

def test_r3_signed_envelope_is_rejected_by_another_exchange(h, tmp_path):
    other = ComputeExchange(h.market, tmp_path / 'other.sqlite3', now_fn=h.clock.epoch)
    try:
        other.seed_account('buyer-one', 5, None)
        assert other.exchange_id != h.exchange.exchange_id
        request = h.request('get_compute_budget', 'buyer-one')
        assert other.process(request)['status'] == 'error'
        assert h.exchange.process(request)['status'] == 'ok'
    finally:
        other.close()


def test_r3_exchange_id_is_durable_and_cannot_be_reassigned(h):
    again = h.open_exchange()
    try:
        assert again.exchange_id == h.exchange.exchange_id
        assert h.exchange.list_capacity()['exchange_id'] == again.exchange_id
    finally:
        again.close()
    with pytest.raises(ValueError):
        h.open_exchange(exchange_id='sim-someoneelse')
    with pytest.raises(ValueError):
        ComputeExchange(h.market, h.path / 'bad.sqlite3', exchange_id='live-1')


# R4 - reads are not replayable; authorizations leave evidence -----------------

def test_r4_signed_read_cannot_be_replayed(h):
    request = h.request('get_compute_budget', 'buyer-one')
    assert h.exchange.process(request)['status'] == 'ok'
    assert h.exchange.process(request)['status'] == 'error'


def test_r4_signed_envelope_is_stored_with_the_outcome(h):
    h.register()
    job = h.create()
    quote = h.quote(job)[0]
    request = h.request('reserve_compute', 'buyer-one',
                        {'job_id': job['job_id'], 'quote_id': quote['quote_id']}, idem='reserve-evidence')
    assert h.exchange.process(request)['status'] == 'ok'
    row = h.exchange.conn.execute(
        "SELECT auth FROM vcx_actions WHERE actor='buyer-one' AND action='reserve_compute' "
        "AND idem='reserve-evidence'").fetchone()
    assert request['auth']['signature'] in row[0] and request['auth']['nonce'] in row[0]
    assert h.exchange.exchange_id in row[0]


# R5 - the owner can change and revoke ----------------------------------------

def test_r5_owner_can_lower_the_cap_but_not_below_commitments(h):
    h.register()
    h.settled()                                            # 200 spent
    job = h.create()
    h.reserve(job)                                         # 200 held
    with pytest.raises(LedgerError):
        h.exchange.update_policy('buyer-one', {'max_spend_minor': 399}, 'change-1')
    after = h.exchange.update_policy('buyer-one', {'max_spend_minor': 400}, 'change-2')
    assert after['available_budget_minor'] == 0 and after['policy']['max_spend_minor'] == 400
    assert h.exchange.update_policy('buyer-one', {'max_spend_minor': 400}, 'change-2')['duplicate'] is True
    h.reject('reserve_compute', body={'job_id': h.create()['job_id'], 'quote_id': 'none'})
    assert h.exchange.reconcile()['status'] == 'ok'


def test_r5_freeze_stops_new_spending_and_reinvestment_but_honours_holds(h):
    h.register(capacity=2)
    h.settled('buyer-two')                                 # seller-one earns 190
    job = h.authorized()
    h.exchange.freeze_account('buyer-one', True, 'freeze-1')
    h.exchange.freeze_account('seller-one', True, 'freeze-2')
    assert budget(h, 'buyer-one')['available_budget_minor'] == 0
    h.reject('reinvest_compute', 'seller-one', {'amount_minor': 1})
    blocked = h.create()
    assert h.exchange.process(h.request('reserve_compute', 'buyer-one', {
        'job_id': blocked['job_id'], 'quote_id': h.quote(blocked)[0]['quote_id']}))['status'] == 'error'
    job = h.call('execute_compute_job', body={'job_id': job['job_id']})
    h.call('verify_compute_result', body={'job_id': job['job_id']})
    assert h.call('settle_compute', body={'job_id': job['job_id']})['state'] == 'SETTLED'
    h.exchange.freeze_account('seller-one', False, 'thaw-1')
    assert h.call('reinvest_compute', 'seller-one', {'amount_minor': 1})['amount_minor'] == 1
    assert h.exchange.reconcile()['status'] == 'ok'


@pytest.mark.parametrize('action', ['update_policy', 'freeze_account', 'set_frozen', 'seed_account'])
def test_r5_owner_controls_are_not_agent_actions(h, action):
    result = h.exchange.process(h.request(action, 'buyer-one', {'max_spend_minor': 10**8}))
    assert result['status'] == 'error'


# R6 - fault attribution -------------------------------------------------------

def observed(h, listing='listing-one'):
    return next(x for x in h.exchange.list_capacity()['capacity']
                if x['listing_id'] == listing)['observed_reliability']


def test_r6_host_timeout_and_buyer_lapse_are_not_booked_against_the_seller(h, monkeypatch):
    h.register(capacity=2)
    original = h.exchange.providers.execute
    def slow(service, payload):
        h.clock.value += 40
        return original(service, payload)
    monkeypatch.setattr(h.exchange.providers, 'execute', slow)
    timed_out = h.call('execute_compute_job', body={'job_id': h.authorized()['job_id']})
    assert (timed_out['state'], timed_out['fault']) == ('EXECUTION_FAILED', 'exchange')
    lapsed = h.reserve(h.create('buyer-two'), 'buyer-two')
    h.clock.value += 600
    expired = h.exchange.recover()['recovered'][0]
    assert (expired['job_id'], expired['state'], expired['fault']) == (lapsed['job_id'], 'EXPIRED', 'buyer')
    assert timed_out['excluded_listings'] == [] and expired['excluded_listings'] == []
    assert observed(h)['failed_jobs'] == 0


def test_r6_provider_failure_is_booked_against_the_seller(h, monkeypatch):
    h.register()
    def broken(service, payload):
        raise RuntimeError('provider bug')
    monkeypatch.setattr(h.exchange.providers, 'execute', broken)
    failed = h.call('execute_compute_job', body={'job_id': h.authorized()['job_id']})
    assert failed['fault'] == 'seller' and failed['excluded_listings'] == ['listing-one']
    assert observed(h)['failed_jobs'] == 1


# R7 - the receipt is independently checkable ----------------------------------

def test_r7_receipt_binds_input_terms_and_amounts(h):
    h.register()
    job = h.settled()
    out = job['receipt']['output']
    assert out['input_sha256'] == digest(job['payload'])
    assert out['output_sha256'] == digest(job['output'])
    assert (out['listing_id'], out['quote_id']) == ('listing-one', job['quote']['quote_id'])
    assert (out['price_minor'], out['fee_minor'], out['seller_net_minor']) == (200, 10, 190)
    assert out['service_version'] == h.exchange._listing('listing-one')['service_version']
    assert out['exchange_id'] == h.exchange.exchange_id
    assert out['settled_at'] == out['closed_at']
    assert verify_orc(job['receipt'])['checks']['digest_recomputes'] is True


def test_r7_unsettled_receipt_never_claims_a_settlement_time(h):
    h.register()
    cancelled = h.call('cancel_compute', body={'job_id': h.authorized()['job_id']})
    out = cancelled['receipt']['output']
    assert out['settled_at'] is None and out['closed_at'] and out['fee_minor'] is None
    assert (out['settlement_state'], out['fault']) == ('CANCELLED', 'buyer')


# R8 - internal faults are visible ---------------------------------------------

def test_r8_internal_fault_is_distinguished_and_logged(h, monkeypatch, caplog):
    def boom(actor, body):
        raise RuntimeError('secret path /should/not/leak')
    monkeypatch.setattr(h.exchange, '_register', boom)
    with caplog.at_level(logging.INFO, logger='viridis.vcx'):
        internal = h.exchange.process(h.request('register_capacity', 'seller-one', h.listing_body()))
        rejected = h.exchange.process(h.request('authorize_compute', 'buyer-one', {'job_id': 'vcx-missing'}))
    assert internal['error_type'] == 'ExchangeInternalError'
    assert rejected['error_type'] == 'ExchangeRejected'
    assert 'leak' not in str(internal) and 'leak' not in caplog.text
    assert 'internal fault action=register_capacity kind=RuntimeError' in caplog.text
    assert 'rejected action=authorize_compute' in caplog.text
    assert h.exchange.conn.in_transaction is False


# R9 - stable public identity interface ------------------------------------------

def test_r9_identity_adapter_uses_only_the_public_market_interface(h):
    calls = []

    class PublicOnly:
        def __init__(self, market):
            self._m = market
        def extension_profile(self, actor):
            calls.append('profile'); return self._m.extension_profile(actor)
        def verify_extension_action(self, *args, **kwargs):
            calls.append('verify'); return self._m.verify_extension_action(*args, **kwargs)
        def extension_security_posture(self, actor):
            calls.append('posture'); return self._m.extension_security_posture(actor)

    identity = MarketIdentity(PublicOnly(h.market))
    request = h.request('get_compute_budget', 'buyer-one')
    profile = identity.verify(h.exchange.signed_action('get_compute_budget'), 'buyer-one',
                              request['body'], request['auth'], h.clock.utc())
    assert set(profile) == {'agent_id', 'did', 'profile_sha256', 'capabilities', 'expires_at', 'public_key_b64'}
    assert identity.profile('buyer-one') == profile
    assert 'postures' in identity.security_posture('seller-one')
    assert calls == ['verify', 'profile', 'posture']


def test_r9_extension_verification_never_moves_market_state(h):
    def rows(table):
        return h.market._conn.execute('SELECT count(*) FROM ' + table).fetchone()[0]
    before = (rows('nonces'), rows('idempotency'), rows('events'))
    request = h.request('get_compute_budget', 'buyer-one')
    action = h.exchange.signed_action('get_compute_budget')
    for _ in range(2):
        h.market.verify_extension_action(action, 'buyer-one', request['body'], request['auth'],
                                         now=h.clock.utc())
    assert (rows('nonces'), rows('idempotency'), rows('events')) == before
    forged = dict(request['auth'], signature=request['auth']['signature'][::-1])
    for bad_action, bad_auth in [(action, forged), ('vcx.other.get_compute_budget', request['auth']),
                                 (action, dict(request['auth'], extra='x'))]:
        with pytest.raises(ValueError):
            h.market.verify_extension_action(bad_action, 'buyer-one', request['body'], bad_auth,
                                             now=h.clock.utc())
    h.clock.value += 301
    with pytest.raises(ValueError):
        h.market.verify_extension_action(action, 'buyer-one', request['body'], request['auth'],
                                         now=h.clock.utc())
