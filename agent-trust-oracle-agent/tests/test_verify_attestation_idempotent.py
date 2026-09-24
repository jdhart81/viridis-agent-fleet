"""verify_attestation purity/idempotency pin — strengthens T6 (recomputes the
hash and validates the chain link). Mirrors the fleet-wide verify_* idiom
(metering verify_chain N64; arbitration/surety/provenance/erc8004/covenant
N65; escrow verify_audit N66): auditing must be a PURE, repeatable read that
never mutates the subject it inspects, and tamper detection must be
deterministic across repeats. Named in the N65 cross-pollination queue.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import AgentConfig, build


@pytest.fixture
def agent():
    return build(AgentConfig(name="agent-trust-oracle-agent", debug=True, half_life_days=30))


class TestVerifyAttestationIdempotent:
    @pytest.mark.asyncio
    async def test_verify_attestation_is_pure_and_repeatable(self, agent):
        await agent.process({"action": "record_outcome", "agent_id": "h", "kind": "success"})
        att = (await agent.process({"action": "attest", "agent_id": "h", "claim": "kyc"}))["data"]

        before = await agent.process({"action": "history", "agent_id": "h"})
        first = await agent.process({"action": "verify_attestation", "agent_id": "h",
                                     "attestation_id": att["attestation_id"]})
        second = await agent.process({"action": "verify_attestation", "agent_id": "h",
                                      "attestation_id": att["attestation_id"]})
        after = await agent.process({"action": "history", "agent_id": "h"})

        assert first["status"] == second["status"] == "ok"
        assert first["data"] == second["data"] == {
            "valid": True, "subject": "h", "tier": att["tier"], "score": att["score"],
        }
        # verifying never mutates the subject's outcome/attestation history
        assert before["data"] == after["data"]

    @pytest.mark.asyncio
    async def test_verify_attestation_tamper_detection_is_deterministic(self, agent):
        await agent.process({"action": "record_outcome", "agent_id": "i", "kind": "success"})
        att = (await agent.process({"action": "attest", "agent_id": "i", "claim": "kyc"}))["data"]
        core = agent
        subj = core._subjects["i"]
        pristine_len = len(subj.attestations)

        # tamper with the stored attestation's tier post-issuance (breaks its own hash)
        subj.attestations[0].tier = "TRUSTED-FORGED"

        first = await agent.process({"action": "verify_attestation", "agent_id": "i",
                                     "attestation_id": att["attestation_id"]})
        second = await agent.process({"action": "verify_attestation", "agent_id": "i",
                                      "attestation_id": att["attestation_id"]})

        assert first["data"] == second["data"] == {
            "valid": False, "subject": "i", "tier": "TRUSTED-FORGED", "score": att["score"],
        }
        # the read itself does not repair, append, or drop attestations
        assert len(subj.attestations) == pristine_len
