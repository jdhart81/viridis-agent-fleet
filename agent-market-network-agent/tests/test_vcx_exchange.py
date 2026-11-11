"""Signed, durable VCX vertical-slice and failure-injection tests.

No real funds, network services, credentials or arbitrary workloads are used.
The tests exercise real Market signatures and cross-connection SQLite writes.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
import uuid

import pytest

AGENT = Path(__file__).resolve().parents[1]
ROOT = AGENT.parent
for directory in (ROOT, AGENT):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from client import AgentMarketSigner
from src.core import MarketNetworkCore
from fleet_utils.orc import verify as verify_orc
from vcx.exchange import ComputeExchange
from vcx.providers import SUM_SERVICE


class Clock:
    def __init__(self):
        self.value = int(datetime(2026, 11, 10, 20, tzinfo=timezone.utc).timestamp())

    def epoch(self):
        return self.value

    def utc(self):
        return datetime.fromtimestamp(self.value, timezone.utc)


class Harness:
    def __init__(self, path):
        self.path = path
        self.clock = Clock()
        self.market = MarketNetworkCore(db_path=str(path / 'market.sqlite3'), now_fn=self.clock.utc)
        self.signers = {}
        for actor in ['buyer-one', 'buyer-two', 'seller-one', 'seller-two', 'seller-three']:
            self.enroll(actor)
        self.exchange = self.open_exchange()
        for actor in self.signers:
            amount = 1000 if actor.startswith('buyer') else 0
            self.exchange.seed_account(actor, amount, {
                'max_spend_minor': 2000, 'reserve_minor': 0,
                'max_exposure_minor': 1000, 'reinvest_bps': 5000,
            })

    def open_exchange(self, **kwargs):
        return ComputeExchange(self.market, self.path / 'vcx.sqlite3',
                               now_fn=self.clock.epoch, **kwargs)

    def enroll(self, actor):
        signer = AgentMarketSigner.generate_ephemeral()
        self.signers[actor] = signer
        body = {
            'name': actor, 'description': 'Synthetic deterministic simulation participant.',
            'capabilities': ['integer-sum', 'data-processing'],
            'representative_queries': ['sum integer data'],
            'endpoint': 'https://vcx-example.test/' + actor + '/mcp',
            'public_key_b64': signer.public_key_b64,
            'payment': {'x402_endpoint': 'https://vcx-example.test/' + actor + '/x402/run',
                        'network': 'eip155:8453', 'asset': 'USDC',
                        'price_minor': 100, 'currency': 'USD'},
            'ttl_days': 90, 'idempotency_key': 'profile-' + actor,
        }
        auth = signer.auth('publish_profile', actor, body, signed_at=self.clock.utc().isoformat())
        result = asyncio.run(self.market.process({'action': 'publish_profile', 'agent_id': actor,
                                                 **body, 'auth': auth}))
        assert result['status'] == 'ok', result

    def request(self, action, actor='buyer-one', body=None, *, idem=None, signer=None):
        body = deepcopy(body or {})
        if action not in {'get_compute_job', 'get_compute_budget', 'get_compute_earnings'}:
            body.setdefault('idempotency_key', idem or 'idem-' + uuid.uuid4().hex)
        auth = (signer or self.signers[actor]).auth(
            self.exchange.signed_action(action), actor, body, signed_at=self.clock.utc().isoformat())
        return {'action': action, 'actor_id': actor, 'body': body, 'auth': auth}

    def call(self, action, actor='buyer-one', body=None, *, exchange=None, **kwargs):
        result = (exchange or self.exchange).process(self.request(action, actor, body, **kwargs))
        assert result['status'] == 'ok', result
        return result['data']

    def reject(self, action, actor='buyer-one', body=None, **kwargs):
        result = self.exchange.process(self.request(action, actor, body, **kwargs))
        assert result['status'] == 'error', result
        return result

    def listing_body(self, listing='listing-one', price=200, capacity=1, **overrides):
        service = self.exchange.providers.services()[0]
        body = {
            'listing_id': listing, 'service_id': SUM_SERVICE,
            'description': service['description'], 'capabilities': ['integer-sum'],
            'price_minor': price, 'currency': 'USD',
            'available_from': self.clock.value - 1, 'expires_at': self.clock.value + 3600,
            'latency_seconds': 1, 'reliability_bps': 9500, 'energy_millijoules': 50,
            'max_concurrent_jobs': capacity, 'authorized_capacity': True,
        }
        body.update(overrides)
        return body

    def register(self, actor='seller-one', **kwargs):
        return self.call('register_capacity', actor, self.listing_body(**kwargs))

    def create(self, actor='buyer-one', **overrides):
        body = {
            'request_id': 'request-' + uuid.uuid4().hex,
            'service_id': SUM_SERVICE, 'payload': {'values': [4, -2, 9]},
            'max_price_minor': 500, 'required_capabilities': ['integer-sum'],
            'deadline': self.clock.value + 1800,
        }
        body.update(overrides)
        return self.call('request_compute', actor, body)

    def quote(self, job, actor='buyer-one', **kwargs):
        return self.call('get_compute_quotes', actor, {'job_id': job['job_id'], **kwargs})['quotes']

    def reserve(self, job, actor='buyer-one', quote=None, **kwargs):
        quote = quote or self.quote(job, actor)[0]
        return self.call('reserve_compute', actor, {'job_id': job['job_id'], 'quote_id': quote['quote_id']}, **kwargs)

    def authorized(self, actor='buyer-one'):
        job = self.create(actor)
        job = self.reserve(job, actor)
        return self.call('authorize_compute', actor, {'job_id': job['job_id']})

    def submitted(self, actor='buyer-one'):
        job = self.authorized(actor)
        return self.call('execute_compute_job', actor, {'job_id': job['job_id']})

    def settled(self, actor='buyer-one'):
        job = self.submitted(actor)
        job = self.call('verify_compute_result', actor, {'job_id': job['job_id']})
        return self.call('settle_compute', actor, {'job_id': job['job_id']})

    def close(self):
        self.exchange.close()
        self.market.close()


@pytest.fixture
def h(tmp_path):
    item = Harness(tmp_path)
    yield item
    item.close()


def test_signed_success_settlement_receipt_and_conservation(h):
    h.register(price=200)
    job = h.settled()
    assert job['state'] == 'SETTLED'
    assert job['output'] == {'sum': 11, 'count': 3}
    assert job['settlement']['fee_minor'] == 10
    assert job['settlement']['seller_net_minor'] == 190
    assert job['receipt']['output']['mode'] == 'simulation'
    assert job['receipt']['output']['settlement_state'] == 'SETTLED'
    assert verify_orc(job['receipt'])['level'] == 1
    assert h.exchange.ledger.budget('buyer-one')['spent_minor'] == 200
    earnings = h.exchange.ledger.earnings('seller-one')
    assert earnings['pending_earnings_minor'] == 190
    assert earnings['actual_revenue_minor'] == 0
    report = h.exchange.ledger.reconcile()
    assert report['conserved'] and report['journal_net_minor'] == 0
    assert report['marketplace_fees_minor'] == 10
    assert report['external_payment_settlement_minor'] == 0
    # A second settlement authorization cannot double-pay.
    assert h.call('settle_compute', body={'job_id': job['job_id']})['state'] == 'SETTLED'
    assert h.exchange.ledger.reconcile()['marketplace_fees_minor'] == 10


def test_available_budget_and_owner_reserve_cannot_be_exceeded(h):
    h.register(price=200)
    h.enroll('limited-buyer')
    h.exchange.seed_account('limited-buyer', 250, {
        'max_spend_minor': 1000, 'reserve_minor': 100,
        'max_exposure_minor': 1000, 'reinvest_bps': 0,
    })
    job = h.create('limited-buyer')
    quote = h.quote(job, 'limited-buyer')[0]
    h.reject('reserve_compute', 'limited-buyer', {'job_id': job['job_id'], 'quote_id': quote['quote_id']})
    assert h.exchange.ledger.budget('limited-buyer')['held_minor'] == 0
    assert h.exchange.ledger.reconcile()['conserved']


def test_duplicate_request_and_changed_replay_parameters(h):
    body = {'request_id': 'stable-request', 'service_id': SUM_SERVICE,
            'payload': {'values': [1]}, 'max_price_minor': 100,
            'required_capabilities': [], 'deadline': h.clock.value + 100}
    request = h.request('request_compute', body=body, idem='stable-idem')
    first = h.exchange.process(request)
    assert first['status'] == 'ok'
    assert h.exchange.process(request) == first
    same_request_new_key = h.call('request_compute', body=body)
    assert same_request_new_key['job_id'] == first['data']['job_id']
    changed = {**body, 'payload': {'values': [2]}}
    h.reject('request_compute', body=changed, idem='stable-idem')
    h.reject('request_compute', body=changed)
    assert h.exchange.conn.execute('SELECT count(*) FROM vcx_jobs').fetchone()[0] == 1


def test_duplicate_and_conflicting_simulated_payment_notices(h):
    h.register()
    job = h.authorized()
    first = h.exchange.confirm_simulated_payment(job['job_id'], 'notice-one', 200)
    assert first == {'mode': 'simulation', 'replayed': False}
    assert h.exchange.confirm_simulated_payment(job['job_id'], 'notice-one', 200)['replayed']
    with pytest.raises(ValueError):
        h.exchange.confirm_simulated_payment(job['job_id'], 'notice-one', 201)
    assert h.exchange.conn.execute('SELECT count(*) FROM vcx_payment_notices').fetchone()[0] == 1
    assert h.exchange.ledger.budget('buyer-one')['held_minor'] == 200
    h.reject('confirm_simulated_payment', body={'job_id': job['job_id'], 'event_id': 'not-public', 'amount_minor': 200})


def test_cross_connection_concurrent_capacity_reservations(h):
    h.register(capacity=1)
    one, two = h.create(), h.create('buyer-two')
    q1, q2 = h.quote(one)[0], h.quote(two, 'buyer-two')[0]
    second = h.open_exchange()
    try:
        requests = [h.request('reserve_compute', body={'job_id': one['job_id'], 'quote_id': q1['quote_id']}),
                    h.request('reserve_compute', 'buyer-two', {'job_id': two['job_id'], 'quote_id': q2['quote_id']})]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(exchange.process, req) for exchange, req in zip([h.exchange, second], requests)]
            results = [f.result() for f in futures]
        assert sorted(r['status'] for r in results) == ['error', 'ok']
        assert h.exchange.ledger.reconcile()['held_minor'] == 200
        assert h.exchange.ledger.reconcile()['conserved']
    finally:
        second.close()


def test_cross_connection_concurrent_buyer_budget_reservations(h):
    h.register(price=500, capacity=2)
    one, two, three = h.create(), h.create(), h.create()
    quotes = [h.quote(job)[0] for job in (one, two, three)]
    exchanges = [h.exchange, h.open_exchange(), h.open_exchange()]
    try:
        reqs = [h.request('reserve_compute', body={'job_id': job['job_id'], 'quote_id': quote['quote_id']})
                for job, quote in zip((one, two, three), quotes)]
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(ex.process, req) for ex, req in zip(exchanges, reqs)]
            results = [f.result() for f in futures]
        assert sum(r['status'] == 'ok' for r in results) == 2
        assert h.exchange.ledger.budget('buyer-one')['held_minor'] == 1000
        assert h.exchange.ledger.reconcile()['conserved']
    finally:
        for ex in exchanges[1:]:
            ex.close()


def test_execution_timeout_releases_hold_and_reassigns(h, monkeypatch):
    h.register(price=100)
    h.register('seller-two', listing='listing-two', price=150)
    job = h.authorized()
    first_listing, first_hold = job['listing_id'], job['hold_id']
    def delayed(service, payload):
        h.clock.value += 31
        return {'sum': 11, 'count': 3}
    monkeypatch.setattr(h.exchange.providers, 'execute', delayed)
    failed = h.call('execute_compute_job', body={'job_id': job['job_id']})
    assert failed['state'] == 'EXECUTION_FAILED'
    assert h.exchange.ledger.budget('buyer-one')['held_minor'] == 0
    # v0.1 executes in the exchange process, so a timeout is the host's fault:
    # the seller's listing stays eligible and its observed record is untouched.
    assert failed['fault'] == 'exchange' and failed['excluded_listings'] == []
    quotes = h.quote(failed, reassign=True)
    assert quotes and first_listing in {x['listing_id'] for x in quotes}
    retry = h.reserve(failed, quote=quotes[0])
    assert retry['hold_id'] != first_hold
    assert h.exchange.ledger.reconcile()['conserved']


def test_cancel_is_durable_and_repeated_cancel_does_not_double_refund(h):
    h.register()
    job = h.authorized()
    cancelled = h.call('cancel_compute', body={'job_id': job['job_id']})
    assert cancelled['state'] == 'CANCELLED'
    assert h.call('cancel_compute', body={'job_id': job['job_id']})['state'] == 'CANCELLED'
    assert h.exchange.ledger.budget('buyer-one')['available_minor'] == 1000
    assert h.exchange.ledger.reconcile()['simulation_released_minor'] == 200
    h.reject('execute_compute_job', body={'job_id': job['job_id']})


def test_verification_failure_is_unpaid_and_releases_all_budget(h, monkeypatch):
    h.register()
    monkeypatch.setattr(h.exchange.providers, 'execute', lambda service, payload: {'sum': 999, 'count': 3})
    submitted = h.submitted()
    monkeypatch.undo()
    failed = h.call('verify_compute_result', body={'job_id': submitted['job_id']})
    assert failed['state'] == 'VERIFICATION_FAILED'
    assert failed['verification']['accepted'] is False
    assert h.exchange.ledger.earnings('seller-one')['pending_earnings_minor'] == 0
    assert h.exchange.ledger.reconcile()['simulation_released_minor'] == 200
    h.reject('settle_compute', body={'job_id': submitted['job_id']})


def test_disputed_job_refund_is_terminal_and_idempotent(h):
    h.register()
    job = h.submitted()
    disputed = h.call('dispute_compute', body={'job_id': job['job_id']})
    assert disputed['state'] == 'DISPUTED'
    h.reject('settle_compute', body={'job_id': job['job_id']})
    # The buyer cannot grant its own refund; only the seller may concede.
    h.reject('refund_compute', body={'job_id': job['job_id']})
    refunded = h.call('refund_compute', 'seller-one', {'job_id': job['job_id']})
    assert refunded['state'] == 'REFUNDED'
    assert h.call('refund_compute', 'seller-one', {'job_id': job['job_id']})['state'] == 'REFUNDED'
    assert h.exchange.ledger.budget('buyer-one')['available_minor'] == 1000
    assert h.exchange.ledger.reconcile()['marketplace_fees_minor'] == 0


def test_restart_recovers_interrupted_running_job_without_reexecution(h, monkeypatch):
    h.register()
    job = h.authorized()
    def simulated_crash(service, payload):
        raise SystemExit('synthetic worker interruption')
    monkeypatch.setattr(h.exchange.providers, 'execute', simulated_crash)
    with pytest.raises(SystemExit):
        h.exchange.process(h.request('execute_compute_job', body={'job_id': job['job_id']}))
    assert h.exchange._load_job(job['job_id'])['state'] == 'RUNNING'
    h.exchange.close()
    h.clock.value += 31
    h.exchange = h.open_exchange()
    recovered = h.exchange.recover()
    assert recovered['recovered'][0]['state'] == 'EXECUTION_FAILED'
    assert h.exchange.ledger.budget('buyer-one')['available_minor'] == 1000
    assert h.exchange.recover()['recovered'] == []
    assert h.exchange.ledger.reconcile()['conserved']


def test_cancel_fences_late_worker_submission(h, monkeypatch):
    h.register()
    job = h.authorized()
    started, finish = threading.Event(), threading.Event()
    def blocked(service, payload):
        started.set()
        assert finish.wait(5)
        return {'sum': 11, 'count': 3}
    monkeypatch.setattr(h.exchange.providers, 'execute', blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(h.exchange.process, h.request('execute_compute_job', body={'job_id': job['job_id']}))
        assert started.wait(5)
        try:
            h.call('cancel_compute', body={'job_id': job['job_id']})
        finally:
            finish.set()
        assert future.result()['status'] == 'error'
    current = h.exchange._load_job(job['job_id'])
    assert current['state'] == 'CANCELLED'
    assert 'output' not in current
    assert h.exchange.ledger.budget('buyer-one')['available_minor'] == 1000


@pytest.mark.parametrize('overrides', [
    {'expires_at': 1}, {'price_minor': True}, {'price_minor': 1.5},
    {'currency': 'CREDIT'}, {'authorized_capacity': False},
    {'max_concurrent_jobs': 0}, {'service_id': 'remote.shell.v1'},
    {'capabilities': ['undeclared-capability']},
])
def test_invalid_listing_rejected_without_persisting(h, overrides):
    h.reject('register_capacity', 'seller-one', h.listing_body(**overrides))
    assert h.exchange.list_capacity()['capacity'] == []


def test_listing_and_quote_expiry_enforced(h):
    h.register(expires_at=h.clock.value + 10)
    job = h.create()
    quote = h.quote(job)[0]
    h.clock.value += 11
    h.reject('reserve_compute', body={'job_id': job['job_id'], 'quote_id': quote['quote_id']})
    assert h.exchange.list_capacity()['capacity'] == []
    assert h.exchange.ledger.budget('buyer-one')['held_minor'] == 0


def test_listing_capability_and_latency_constraints_are_hard_filters(h):
    h.register(latency_seconds=30)
    assert h.quote(h.create(max_latency_seconds=10)) == []
    assert h.quote(h.create(required_capabilities=['unknown-capability'])) == []
    assert h.quote(h.create(min_reliability_bps=9999)) == []


def test_matching_score_is_transparent_and_can_choose_quality_over_price(h):
    h.register(price=100, reliability_bps=2000)
    h.register('seller-two', listing='listing-two', price=150, reliability_bps=9900)
    job = h.create()
    quotes = h.quote(job)
    assert quotes[0]['seller_id'] == 'seller-two'
    assert quotes[0]['score'] == sum(quotes[0]['score_components_bps'][key] * weight
                                     for key, weight in quotes[0]['score_weights'].items())


def test_frozen_quote_fee_survives_exchange_restart_configuration(h):
    h.register(price=200)
    job = h.create()
    quote = h.quote(job)[0]
    assert quote['fee_bps'] == 500
    h.exchange.close()
    h.exchange = h.open_exchange(fee_bps=900)
    h.reserve(job, quote=quote)
    for action in ['authorize_compute', 'execute_compute_job', 'verify_compute_result', 'settle_compute']:
        result = h.call(action, body={'job_id': job['job_id']})
    assert result['fee_bps'] == 500
    assert result['settlement']['fee_minor'] == 10


def test_invalid_signatures_nonces_and_cross_actor_reads_are_rejected(h):
    h.register()
    request = h.request('request_compute', body={
        'request_id': 'spoofed', 'service_id': SUM_SERVICE, 'payload': {'values': [1]},
        'max_price_minor': 100, 'required_capabilities': [], 'deadline': h.clock.value + 100,
    }, signer=h.signers['buyer-two'])
    assert h.exchange.process(request)['status'] == 'error'
    job = h.create()
    h.reject('get_compute_job', 'buyer-two', {'job_id': job['job_id']})
    h.reject('cancel_compute', 'buyer-two', {'job_id': job['job_id']})
    h.reject('seed_account', body={'amount_minor': 9999999})
    stale = h.request('get_compute_budget')
    h.clock.value += 301
    assert h.exchange.process(stale)['status'] == 'error'


def test_expired_identity_cannot_authorize_compute(h):
    h.register()
    job = h.reserve(h.create())
    with h.market._lock:
        h.market._conn.execute("UPDATE profiles SET expires_at=? WHERE agent_id='seller-one'",
                               (h.clock.utc().isoformat(),))
    h.reject('authorize_compute', body={'job_id': job['job_id']})
    assert h.exchange.ledger.budget('buyer-one')['held_minor'] == 200


@pytest.mark.parametrize('location', ['payload', 'metadata', 'description'])
def test_credential_canary_is_not_echoed_or_persisted(h, location):
    canary = 'Bearer VCX-SECRET-CANARY-DO-NOT-PERSIST'
    if location == 'description':
        response = h.reject('register_capacity', 'seller-one', h.listing_body(description=canary))
    else:
        body = {'request_id': 'secret-test', 'service_id': SUM_SERVICE,
                'payload': {'values': [1]}, 'max_price_minor': 100,
                'required_capabilities': [], 'deadline': h.clock.value + 100}
        if location == 'payload':
            body['payload']['values'] = [canary]
        else:
            body['metadata'] = {'api_key': canary}
        response = h.reject('request_compute', body=body)
    assert canary not in json.dumps(response)
    assert canary not in '\n'.join(h.exchange.conn.iterdump())
    assert h.exchange.conn.execute('SELECT count(*) FROM vcx_jobs').fetchone()[0] == 0


def test_reinvestment_limits_and_earn_then_purchase(h):
    h.register(price=200)
    earned_job = h.settled()
    earnings = h.call('get_compute_earnings', 'seller-one')
    assert earnings['pending_earnings_minor'] == 190
    assert earnings['allowed_reinvestment_minor'] == 95
    h.reject('reinvest_compute', 'seller-one', {'amount_minor': 96})
    h.call('reinvest_compute', 'seller-one', {'amount_minor': 95})
    h.reject('reinvest_compute', 'seller-one', {'amount_minor': 1})
    h.register('seller-two', listing='listing-two', price=50)
    funded_job = h.settled('seller-one')
    assert funded_job['seller_id'] == 'seller-two'
    assert h.exchange.ledger.budget('seller-one')['spent_minor'] == 50
    assert h.exchange.ledger.budget('seller-one')['available_minor'] == 45
    assert h.exchange.ledger.earnings('seller-one')['actual_revenue_minor'] == 0
    assert h.exchange.ledger.reconcile()['conserved']


def test_recovery_is_actor_scoped_and_atomic(h):
    h.register(capacity=2)
    one, two = h.authorized(), h.authorized('buyer-two')
    h.clock.value += 61
    recovered = h.call('recover_compute_jobs')
    assert {job['job_id'] for job in recovered['recovered']} == {one['job_id']}
    assert h.exchange._load_job(two['job_id'])['state'] == 'AUTHORIZED'
    h.exchange.recover()
    assert h.exchange.ledger.reconcile()['held_minor'] == 0
    assert h.exchange.ledger.reconcile()['conserved']


def test_concurrent_settlement_workers_have_one_authoritative_financial_outcome(h):
    h.register(price=200)
    job = h.submitted()
    h.call('verify_compute_result', body={'job_id': job['job_id']})
    second = h.open_exchange()
    try:
        reqs = [h.request('settle_compute', body={'job_id': job['job_id']}) for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(ex.process, req) for ex, req in zip([h.exchange, second], reqs)]
            results = [f.result() for f in futures]
        assert all(result['status'] == 'ok' for result in results)
        assert h.exchange.ledger.earnings('seller-one')['pending_earnings_minor'] == 190
        assert h.exchange.ledger.budget('buyer-one')['spent_minor'] == 200
        assert h.exchange.conn.execute("SELECT count(*) FROM vcx_capital_operations WHERE kind='settle'").fetchone()[0] == 1
        assert h.exchange.ledger.reconcile()['conserved']
    finally:
        second.close()


def test_failed_durable_settlement_rolls_back_money_state_and_authorization(h, monkeypatch):
    import sqlite3
    h.register()
    job = h.submitted()
    h.call('verify_compute_result', body={'job_id': job['job_id']})
    before = h.exchange.ledger.reconcile()
    request = h.request('settle_compute', body={'job_id': job['job_id']})
    original = h.exchange._save
    def failed_write(job, state=None, event=None):
        if job['state'] == 'SETTLED':
            raise sqlite3.OperationalError('synthetic disk persistence failure')
        return original(job, state, event)
    monkeypatch.setattr(h.exchange, '_save', failed_write)
    assert h.exchange.process(request)['status'] == 'error'
    assert h.exchange._load_job(job['job_id'])['state'] == 'VERIFIED'
    assert h.exchange.ledger.reconcile() == before
    monkeypatch.setattr(h.exchange, '_save', original)
    # A rolled-back write did not consume the nonce or idempotency key.
    assert h.exchange.process(request)['status'] == 'ok'
    assert h.exchange.ledger.earnings('seller-one')['pending_earnings_minor'] == 190


def test_security_requirement_uses_current_market_evidence(h):
    h.register()
    job = h.create(security_posture='SCANNED')
    # A signed profile and seller reliability claims are not security evidence.
    assert h.quote(job) == []
    assert h.exchange.ledger.budget('buyer-one')['held_minor'] == 0


def test_receipt_signature_binds_exact_orc_to_configured_issuer(h):
    import base64
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from src.core import canonical_action
    h.exchange.close()
    issuer = AgentMarketSigner.generate_ephemeral()
    h.exchange = h.open_exchange(receipt_signer=issuer)
    h.register()
    job = h.settled()
    envelope = job['receipt']
    assert envelope['public_key_b64'] == issuer.public_key_b64
    auth, receipt = envelope['signature'], envelope['receipt']
    decode = lambda s: base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))
    key = Ed25519PublicKey.from_public_bytes(decode(issuer.public_key_b64))
    key.verify(decode(auth['signature']), canonical_action(
        'vcx.receipt', 'vcx-local-simulation', auth['nonce'], auth['signed_at'], receipt).encode())
    assert verify_orc(receipt)['level'] == 1
    assert 'private_key' not in json.dumps(envelope)


def test_interrupted_execution_freezes_idempotency_terms_before_worker_side_effect(h, monkeypatch):
    """A crash cannot free an execution key for a different authorized job."""
    h.register(capacity=2)
    first, second = h.authorized(), h.authorized()
    calls = []
    def interrupted(service, payload):
        calls.append((service, deepcopy(payload)))
        raise SystemExit('synthetic crash after durable execution claim')
    monkeypatch.setattr(h.exchange.providers, 'execute', interrupted)
    request = h.request('execute_compute_job', body={'job_id': first['job_id']}, idem='crash-bound-key')
    with pytest.raises(SystemExit):
        h.exchange.process(request)
    assert len(calls) == 1
    assert h.exchange._load_job(first['job_id'])['state'] == 'RUNNING'

    # A fresh signature does not let the buyer bind the pending key to another job.
    h.reject('execute_compute_job', body={'job_id': second['job_id']}, idem='crash-bound-key')
    assert h.exchange._load_job(second['job_id'])['state'] == 'AUTHORIZED'
    assert len(calls) == 1
    # Exact replay and newly signed same-terms replay both return durable state.
    assert h.exchange.process(request)['data']['state'] == 'RUNNING'
    same_terms = h.call('execute_compute_job', body={'job_id': first['job_id']}, idem='crash-bound-key')
    assert same_terms['state'] == 'RUNNING'
    assert len(calls) == 1

    h.exchange.close()
    h.clock.value += 31
    h.exchange = h.open_exchange()
    def must_not_execute(service, payload):
        calls.append((service, deepcopy(payload)))
        raise AssertionError('replayed interrupted execution must never run again')
    monkeypatch.setattr(h.exchange.providers, 'execute', must_not_execute)
    h.exchange.recover()
    assert h.exchange.process(request)['data']['state'] == 'EXECUTION_FAILED'
    assert h.call('execute_compute_job', body={'job_id': first['job_id']}, idem='crash-bound-key')['state'] == 'EXECUTION_FAILED'
    h.reject('execute_compute_job', body={'job_id': second['job_id']}, idem='crash-bound-key')
    assert len(calls) == 1
    assert h.exchange.ledger.budget('buyer-one')['held_minor'] == 200
    assert h.exchange.reconcile()['conserved']


def test_exchange_reconciliation_detects_job_hold_disagreement(h):
    """A balanced financial journal alone cannot establish correct job settlement."""
    h.register()
    job = h.authorized()
    assert h.exchange.reconcile()['conserved']
    # Synthetic state corruption: ledger still has HELD funds, job claims settlement.
    with h.exchange.tx():
        h.exchange._save(h.exchange._load_job(job['job_id']), 'SETTLED')
    assert h.exchange.ledger.reconcile()['conserved']
    audited = h.exchange.reconcile()
    assert audited['status'] == 'error' and not audited['conserved']
    assert 'job_hold_mismatch:' + job['job_id'] in audited['errors']


def test_signed_seller_requires_owner_authorized_simulation_account(h):
    h.enroll('unfunded-seller')
    h.reject('register_capacity', 'unfunded-seller', h.listing_body())
    assert h.exchange.list_capacity()['capacity'] == []
    # Zero initial money is valid for a seller only after trusted owner setup.
    h.exchange.seed_account('unfunded-seller', 0, {
        'max_spend_minor': 100, 'reserve_minor': 0,
        'max_exposure_minor': 100, 'reinvest_bps': 5000,
    })
    listing = h.call('register_capacity', 'unfunded-seller', h.listing_body())
    assert listing['seller_id'] == 'unfunded-seller'
    assert h.exchange.ledger.budget('unfunded-seller')['available_budget_minor'] == 0


def test_security_eligibility_is_targeted_and_rechecked_after_quote(h, monkeypatch):
    h.register()
    current_postures = ['SCANNED']
    checked = []
    def targeted(actor):
        checked.append(actor)
        assert actor == 'seller-one'
        return {'postures': list(current_postures)}
    def forbidden_discovery(*args, **kwargs):
        raise AssertionError('eligibility must not depend on paginated discovery')
    monkeypatch.setattr(h.exchange.identity, 'security_posture', targeted)
    monkeypatch.setattr(h.market, 'search_agents', forbidden_discovery)
    job = h.create(security_posture='SCANNED')
    quote = h.quote(job)[0]
    assert quote['seller_id'] == 'seller-one'
    assert checked == ['seller-one']
    # Evidence expired/withdrawn after quoting must prevent reservation.
    current_postures.clear()
    h.reject('reserve_compute', body={'job_id': job['job_id'], 'quote_id': quote['quote_id']})
    assert checked == ['seller-one', 'seller-one']
    assert h.exchange.ledger.budget('buyer-one')['held_minor'] == 0
    assert h.exchange._load_job(job['job_id'])['state'] == 'QUOTED'


@pytest.mark.parametrize('action', ['register_capacity', 'execute_compute_job'])
def test_authorization_rechecked_after_transaction_acquisition(h, monkeypatch, action):
    if action == 'register_capacity':
        actor, body = 'seller-one', h.listing_body()
        job = None
    else:
        h.register()
        job = h.authorized()
        actor, body = 'buyer-one', {'job_id': job['job_id']}
    request = h.request(action, actor, body)
    original = h.exchange.identity.verify
    checked = []
    def revoke_after_initial_check(action_name, actor_id, signed_body, auth, now):
        result = original(action_name, actor_id, signed_body, auth, now)
        checked.append(actor_id)
        if len(checked) == 1:
            # Model identity revocation while the writer waits for its DB lock.
            h.market._conn.execute('UPDATE profiles SET status=? WHERE agent_id=?', ('REVOKED', actor_id))
        return result
    monkeypatch.setattr(h.exchange.identity, 'verify', revoke_after_initial_check)
    before_actions = h.exchange.conn.execute('SELECT count(*) FROM vcx_actions').fetchone()[0]
    before_nonces = h.exchange.conn.execute('SELECT count(*) FROM vcx_nonces').fetchone()[0]
    before_capital = h.exchange.ledger.reconcile()
    rejected = h.exchange.process(request)
    assert rejected['status'] == 'error'
    assert len(checked) == 1  # second original verify rejected the revoked identity
    assert h.exchange.conn.execute('SELECT count(*) FROM vcx_actions').fetchone()[0] == before_actions
    assert h.exchange.conn.execute('SELECT count(*) FROM vcx_nonces').fetchone()[0] == before_nonces
    assert h.exchange.ledger.reconcile() == before_capital
    if job:
        assert h.exchange._load_job(job['job_id'])['state'] == 'AUTHORIZED'
    else:
        assert h.exchange.list_capacity()['capacity'] == []
    # The rejected queued write consumed no nonce/idempotency authorization.
    h.market._conn.execute('UPDATE profiles SET status=? WHERE agent_id=?', ('ACTIVE', actor))
    monkeypatch.setattr(h.exchange.identity, 'verify', original)
    accepted = h.exchange.process(request)
    assert accepted['status'] == 'ok'
