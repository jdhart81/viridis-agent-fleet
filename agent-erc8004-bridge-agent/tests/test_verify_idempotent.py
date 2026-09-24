"""Idempotency/purity pin for verify (strengthens B4).

B4's existing test (test_b4_export_verifies_and_tamper_is_detected) covers
tamper-detection but not that verify is a PURE, repeatable read -- the
"idempotency on verify_audit-style actions" signal queued in N63/N64, closed
across the A2A verify_* family tonight (mirrors metering's verify_chain pin).
verify recomputes a hash from the supplied payload and touches no stored
state, so repeated calls must be byte-identical and the registry must be
unaffected. Additive; B1-B8 untouched.
"""
import asyncio

from src.core import build


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


REG = {"action": "import_registration", "chain_id": 1, "token_id": 4242,
       "agent_uri": "https://agents.example/4242.json",
       "owner": "0xAbC0000000000000000000000000000000000001"}


def _import(agent, **over):
    return run(agent.process({**REG, **over}))


def test_b4_verify_is_idempotent_and_pure():
    a = build()
    _import(a)
    exp = run(a.process({"action": "export_attestation", "chain_id": 1,
                         "token_id": 4242}))["data"]

    before = run(a.process({"action": "list"}))
    v1 = run(a.process({"action": "verify", "payload": exp}))
    v2 = run(a.process({"action": "verify", "payload": exp}))
    after = run(a.process({"action": "list"}))

    assert v1["data"]["valid"] is True
    assert v1["data"] == v2["data"]
    assert before["data"] == after["data"]  # verify does not touch the registry


def test_b4_verify_idempotent_on_tampered_payload():
    a = build()
    _import(a)
    exp = run(a.process({"action": "export_attestation", "chain_id": 1,
                         "token_id": 4242}))["data"]
    tampered = dict(exp, score=0.999999)

    v1 = run(a.process({"action": "verify", "payload": tampered}))
    v2 = run(a.process({"action": "verify", "payload": tampered}))
    assert v1["data"]["valid"] is False
    assert v1["data"] == v2["data"]
