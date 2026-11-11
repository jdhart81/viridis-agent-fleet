"""Run the complete VCX vertical slice without network access or real money.

From agent-market-network-agent: ``python3 -m vcx.demo``. The default state is
an automatically cleaned temporary directory; --state-dir must name a fresh
state directory. Caller signing keys remain ephemeral in process memory.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import time
import uuid

# Support both ``python -m vcx.demo`` and direct execution from a checkout.
AGENT = Path(__file__).resolve().parents[1]
FLEET = AGENT.parent
for path in (AGENT, FLEET):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from client import AgentMarketSigner
from src.core import MarketNetworkCore
from vcx.exchange import ComputeExchange
from vcx.providers import SUM_SERVICE, TAKEOFF_SERVICE


class DemoClock:
    def __init__(self):
        self.value = int(time.time())

    def __call__(self):
        return self.value

    def utc(self):
        return datetime.fromtimestamp(self.value, timezone.utc)

    def advance(self, seconds):
        self.value += seconds


def _require(result):
    if result.get("status") != "ok":
        raise RuntimeError("VCX demonstration step failed: " + json.dumps(result))
    return result["data"]


def _profile(market, actor, signer, clock, capabilities):
    # These public URLs are example metadata only. VCX never calls them.
    body = {
        "name": "VCX simulation " + actor,
        "description": "Ephemeral participant in the local VCX demonstration.",
        "capabilities": capabilities,
        "representative_queries": ["local simulated computation"],
        "endpoint": "https://vcx.example.com/" + actor + "/mcp",
        "public_key_b64": signer.public_key_b64,
        "payment": {},
        "ttl_days": 1,
        "idempotency_key": actor + "-profile",
    }
    request = {"action": "publish_profile", "agent_id": actor, **body,
               "auth": signer.auth("publish_profile", actor, body,
                                   signed_at=clock.utc().isoformat())}
    return _require(asyncio.run(market.process(request)))


class DemoClient:
    def __init__(self, exchange, signers, clock):
        self.exchange, self.signers, self.clock = exchange, signers, clock

    def call(self, action, actor, body=None):
        body = dict(body or {})
        if action not in {"get_compute_job", "get_compute_budget", "get_compute_earnings"}:
            body.setdefault("idempotency_key", "demo-" + uuid.uuid4().hex)
        request = {"action": action, "actor_id": actor, "body": body,
                   "auth": self.signers[actor].auth(
                       self.exchange.signed_action(action), actor, body,
                       signed_at=self.clock.utc().isoformat())}
        return _require(self.exchange.process(request))

    def quote(self, actor, label, max_price=300, *, minimum_reliability=0):
        job = self.call("request_compute", actor, {
            "request_id": label, "service_id": SUM_SERVICE,
            "payload": {"values": [7, 11, 24]},
            "max_price_minor": max_price,
            "required_capabilities": ["integer-sum"],
            "deadline": self.clock.value + 600,
            "max_latency_seconds": 100,
            "min_reliability_bps": minimum_reliability,
            "prefer_energy": True,
        })
        quotes = self.call("get_compute_quotes", actor, {"job_id": job["job_id"]})
        if not quotes["quotes"]:
            raise RuntimeError("VCX demonstration found no matching simulated capacity")
        return job, quotes["quotes"]

    def reserve(self, actor, job, quotes):
        return self.call("reserve_compute", actor, {
            "job_id": job["job_id"], "quote_id": quotes[0]["quote_id"]})

    def complete(self, actor, job, quotes):
        current = self.reserve(actor, job, quotes)
        for action in ("authorize_compute", "execute_compute_job",
                       "verify_compute_result", "settle_compute"):
            current = self.call(action, actor, {"job_id": current["job_id"]})
        if current["state"] != "SETTLED":
            raise RuntimeError("VCX demonstration did not reach verified simulated settlement")
        return current


def run_demo(state_dir):
    """Produce a JSON-safe report; every balance is explicitly simulated."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    if any(state_dir.iterdir()):
        raise ValueError("demo state directory must be empty to protect existing identities")
    clock = DemoClock()
    market = MarketNetworkCore(db_path=str(state_dir / "market.sqlite3"), now_fn=clock.utc)
    exchange = ComputeExchange(market, state_dir / "vcx.sqlite3", now_fn=clock,
                               reservation_seconds=60, execution_seconds=30)
    actors = ["seller-accurate", "seller-economy", "seller-specialist", "buyer-alpha", "buyer-beta"]
    signers = {actor: AgentMarketSigner.generate_ephemeral() for actor in actors}
    client = DemoClient(exchange, signers, clock)
    capabilities = {
        "seller-accurate": ["integer-sum", "data-processing"],
        "seller-economy": ["integer-sum"],
        "seller-specialist": ["integer-sum", "quantity-takeoff", "construction-estimation"],
        "buyer-alpha": ["compute-buyer"], "buyer-beta": ["compute-buyer"],
    }
    try:
        profiles = [_profile(market, actor, signers[actor], clock, capabilities[actor]) for actor in actors]
        for actor in actors:
            exchange.seed_account(actor, 1000 if actor == "buyer-alpha" else 300 if actor == "buyer-beta" else 0,
                                  {"max_spend_minor": 1000, "reserve_minor": 0,
                                   "max_exposure_minor": 500, "reinvest_bps": 8000})
        services = {item["service_id"]: item for item in exchange.providers.services()}
        listings = []
        for seller, price, reliability, latency, energy, capacity in (
            ("seller-accurate", 200, 9900, 3, 500, 2),
            ("seller-economy", 100, 6000, 20, 900, 1),
            ("seller-specialist", 300, 10000, 30, 250, 1),
        ):
            listings.append(client.call("register_capacity", seller, {
                "listing_id": seller + "-sum", "service_id": SUM_SERVICE,
                "description": services[SUM_SERVICE]["description"],
                "capabilities": ["integer-sum"], "price_minor": price, "currency": "USD",
                "available_from": clock.value - 1, "expires_at": clock.value + 3600,
                "latency_seconds": latency, "reliability_bps": reliability,
                "energy_millijoules": energy, "max_concurrent_jobs": capacity,
                "authorized_capacity": True,
            }))
        listings.append(client.call("register_capacity", "seller-specialist", {
            "listing_id": "seller-specialist-takeoff", "service_id": TAKEOFF_SERVICE,
            "description": services[TAKEOFF_SERVICE]["description"],
            "capabilities": ["quantity-takeoff", "construction-estimation"],
            "price_minor": 250, "currency": "USD", "available_from": clock.value - 1,
            "expires_at": clock.value + 3600, "latency_seconds": 10,
            "reliability_bps": 9800, "energy_millijoules": 600,
            "max_concurrent_jobs": 1, "authorized_capacity": True,
        }))
        job, quotes = client.quote("buyer-alpha", "first-revenue")
        first = client.complete("buyer-alpha", job, quotes)
        earning_seller = first["seller_id"]
        earnings_before = client.call("get_compute_earnings", earning_seller)
        budget_before = client.call("get_compute_budget", earning_seller)
        reinvest_amount = min(150, budget_before["allowed_reinvestment_minor"])
        if reinvest_amount < 100:
            raise RuntimeError("demo seller did not earn enough authorized simulated reinvestment")
        reinvestment = client.call("reinvest_compute", earning_seller, {"amount_minor": reinvest_amount})
        followup_job, followup_quotes = client.quote(earning_seller, "earnings-funded-compute", max_price=100)
        second = client.complete(earning_seller, followup_job, followup_quotes)

        # Failure case 1: held budget returns in full on pre-settlement cancellation.
        cancel_job, cancel_quotes = client.quote("buyer-beta", "cancelled-request", max_price=100)
        reserved = client.reserve("buyer-beta", cancel_job, cancel_quotes)
        cancelled = client.call("cancel_compute", "buyer-beta", {"job_id": reserved["job_id"]})
        # Failure case 2: expired authorization is recovered without execution.
        expired_job, expired_quotes = client.quote("buyer-beta", "expired-authorization", max_price=100)
        held = client.reserve("buyer-beta", expired_job, expired_quotes)
        client.call("authorize_compute", "buyer-beta", {"job_id": held["job_id"]})
        clock.advance(61)
        recovered = client.call("recover_compute_jobs", "buyer-beta")
        # Exercise a real, allowlisted Fleet service through the same financial lifecycle.
        takeoff_job = client.call("request_compute", "buyer-beta", {
            "request_id": "fleet-takeoff", "service_id": TAKEOFF_SERVICE,
            "payload": {"items": [{
                "assembly": "concrete_slab", "unit_system": "imperial",
                "dimensions": {
                    "length": {"value": "20", "unit": "ft"},
                    "width": {"value": "30", "unit": "ft"},
                    "thickness": {"value": "4", "unit": "in"},
                },
            }]},
            "max_price_minor": 250,
            "required_capabilities": ["quantity-takeoff"],
            "deadline": clock.value + 600, "max_latency_seconds": 100,
        })
        takeoff_quotes = client.call("get_compute_quotes", "buyer-beta", {"job_id": takeoff_job["job_id"]})
        fleet_takeoff = client.complete("buyer-beta", takeoff_job, takeoff_quotes["quotes"])
        if fleet_takeoff["output"]["line_items"][0]["net_qty"] != "7.407":
            raise RuntimeError("Fleet takeoff failed its deterministic acceptance contract")
        budgets = {actor: client.call("get_compute_budget", actor) for actor in actors}
        earnings = {actor: client.call("get_compute_earnings", actor) for actor in actors[:3]}
        reconciliation = exchange.reconcile()
        if not reconciliation.get("conserved", False):
            raise RuntimeError("VCX simulation ledger failed reconciliation")
        return {
            "name": "Viridis Compute Exchange v0.1 local demonstration",
            "mode": "simulation", "actual_revenue_minor": 0,
            "live_charges": 0, "live_payouts": 0, "redeemable": False,
            "participants": {"sellers": 3, "buyers": 2,
                             "identity": "ephemeral Ed25519 key possession in existing Market Network"},
            "registered_capacity": listings,
            "discovery_count": len(exchange.list_capacity()["capacity"]),
            "first_job": first,
            "ranking": {"quotes": quotes, "lowest_price_seller": "seller-economy",
                        "selected_seller": earning_seller},
            "earnings_before_reinvestment": earnings_before,
            "reinvestment": reinvestment,
            "earnings_funded_job": second,
            "fleet_takeoff_job": fleet_takeoff,
            "failure_simulations": {"cancelled": cancelled, "expired_authorization": recovered},
            "budgets": budgets, "seller_earnings": earnings,
            "reconciliation": reconciliation,
            "claim_boundary": "Simulation demonstrates accounting and deterministic acceptance; it establishes no actual revenue, payout eligibility or research truth.",
        }
    finally:
        exchange.close()
        market.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, help="Fresh directory for durable simulated state; ephemeral keys are not saved.")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path as well as stdout.")
    args = parser.parse_args(argv)
    if args.state_dir:
        report = run_demo(args.state_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="viridis-vcx-demo-") as state_dir:
            report = run_demo(state_dir)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
