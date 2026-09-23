"""Paid, bounded policy rehearsal; never claims to activate protection."""
import hashlib
import json
import math
import os
import time


BOUNDARY = ("A policy rehearsal and local SHA-256 microbenchmark, not deployed protection, "
            "an energy measurement, an audit, or an availability guarantee. Client timings "
            "are modeled from buyer-supplied throughput; SHA-256 permits hardware acceleration.")
FIELDS = {
    "client_hashes_per_second": (100, 1000000000),
    "client_p95_budget_ms": (1, 2000),
    "backend_cost_ms": (1, 3600000),
    "peak_requests_per_second": (1, 100000),
}


class MaxwellDefenseCore:
    KNOWN_ACTIONS = frozenset({"rehearse_defense"})
    READ_ACTIONS = frozenset()

    def _paid_preflight(self, payload):
        if os.environ.get("MAXWELL_FLEET_ENABLED") != "1":
            return {"status": "error", "error_type": "ServiceUnavailable",
                    "message": "Maxwell paid rehearsal is disabled"}
        if not isinstance(payload, dict) or payload.get("action") != "rehearse_defense":
            return {"status": "error", "error_type": "ValidationError", "message": "Unknown action"}
        if set(payload) != {"action", *FIELDS}:
            return {"status": "error", "error_type": "ValidationError", "message": "Supply exactly the four workload limits"}
        for name, (low, high) in FIELDS.items():
            value = payload[name]
            if type(value) is not int or not low <= value <= high:
                return {"status": "error", "error_type": "ValidationError",
                        "message": f"{name} must be an integer from {low} to {high}"}
        return None

    async def process(self, payload):
        error = self._paid_preflight(payload)
        if error:
            return error
        inputs = {field: payload[field] for field in FIELDS}
        # Fixed amount of local work independent of the buyer's chosen rate.
        started = time.perf_counter_ns()
        for i in range(8192):
            hashlib.sha256(b"maxwell-rehearsal-v1:" + i.to_bytes(4, "big")).digest()
        elapsed_ns = max(1, time.perf_counter_ns() - started)
        hash_us = elapsed_ns / 8192 / 1000
        budget_attempts = inputs["client_hashes_per_second"] * inputs["client_p95_budget_ms"] / 1000
        # Reference solver hard-caps at 1,048,576 attempts; 18 bits is the
        # highest difficulty whose modeled p95 fits inside that attempt cap.
        candidates = [b for b in range(1, 19)
                      if math.ceil(math.log(0.05) / math.log1p(-2 ** -b)) <= budget_attempts]
        bits = max(candidates) if candidates else None
        p95_attempts = (math.ceil(math.log(0.05) / math.log1p(-2 ** -bits))
                        if bits else None)
        return {
            "status": "ok", "service": "maxwell-defense", "version": "0.1.0",
            "decision": "SHADOW_TRIAL_RECOMMENDED" if bits else "CLIENT_BUDGET_TOO_LOW",
            "input_sha256": hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
            "policy": {"scheme": "maxwell-sha256-v1", "difficulty_bits": bits,
                       "ttl_seconds": 60, "max_body_bytes": 65536,
                       "enforcement_enabled": False,
                       "client_max_attempts": 1048576,
                       "client_max_seconds": inputs["client_p95_budget_ms"] / 1000,
                       "placement": "after authenticated identity and quotas, before costly tool work",
                       "bypass": "only server-verified entitlement with independent quota; never a client trust header",
                       "replay_capacity_required_at_declared_peak": inputs["peak_requests_per_second"] * 60,
                       "single_host_reference_capacity_max": 100000,
                       "shared_store_required": inputs["peak_requests_per_second"] * 60 > 100000},
            "modeled_client": {"expected_hash_attempts": 2 ** bits if bits else None,
                               "p95_hash_attempts": p95_attempts,
                               "p95_ms": p95_attempts / inputs["client_hashes_per_second"] * 1000 if bits else None,
                               "basis": "buyer-declared hashes/second; independent uniform hash model"},
            "measured_local": {"sha256_samples": 8192, "mean_hash_microseconds": round(hash_us, 4),
                               "scope": "hash microbenchmark only; excludes network, HMAC, body hashing and replay database"},
            "declared_backend": {"cost_ms": inputs["backend_cost_ms"],
                                 "peak_requests_per_second": inputs["peak_requests_per_second"]},
            "acceptance_checks": ["Measure full verify p95 including shared replay storage",
                                  "Measure supported clients and respect their solve budgets",
                                  "Confirm legitimate completion and latency under controlled load",
                                  "Confirm invalid, expired, cross-request and replay proofs never reach expensive work",
                                  "Verify edge connection, body, issuance and rate limits",
                                  "Measure net backend work avoided before claiming savings"],
            "protection_activated": False, "energy_savings_measured": False,
            "claim_boundary": BOUNDARY,
        }

    def describe(self):
        return {"name": "maxwell-defense-agent", "version": "0.1.0",
                "capabilities": ["bounded-defense-policy-rehearsal"],
                "claim_boundary": BOUNDARY, "price_minor": 100,
                "enabled": os.environ.get("MAXWELL_FLEET_ENABLED") == "1"}

    def health(self):
        return {"status": "ok", "version": "0.1.0",
                "enabled": os.environ.get("MAXWELL_FLEET_ENABLED") == "1",
                "runtime_protection_enabled": False}
