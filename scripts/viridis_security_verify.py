#!/usr/bin/env python3
"""Offline verification of manifest preflight evidence; never authorizes tools.

Requires cryptography. Trust policy must be provisioned by the operator through
an authenticated channel, independently of the result being verified.
"""
import argparse
import base64
import hashlib
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class VerificationError(ValueError):
    pass


def canonical(value):
    # This is the issuer's v1 serialization, not RFC 8785/JCS.
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def decode(value):
    if not isinstance(value, str):
        raise VerificationError("Invalid encoded key or signature")
    return base64.b64decode(value + "=" * (-len(value) % 4),
                            altchars=b"-_", validate=True)


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def verify(result, inputs, trust, *, now=None):
    """Return authenticated assessment, not payment proof or runtime safety.

    trust: {public_key_b64, scanner: {name, version, canon_digest}}.
    Caller must treat any exception as a stop/review, never as a pass.
    """
    try:
        return _verify(result, inputs, trust, now=now)
    except VerificationError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, InvalidSignature) as exc:
        raise VerificationError("Invalid or unauthenticated preflight evidence") from exc


def _verify(result, inputs, trust, *, now):
    require(isinstance(result, dict) and isinstance(inputs, dict)
            and isinstance(trust, dict), "Expected JSON objects")
    receipt, evidence = result["receipt"], result["evidence"]
    key = decode(trust["public_key_b64"])
    Ed25519PublicKey.from_public_bytes(key).verify(
        decode(result["signature_b64"]), canonical(receipt))
    require(receipt["protocol"] == "viridis-security-receipt-v1"
            and receipt["issuer_id"] == "viridis-security-preflight",
            "Unsupported receipt protocol or issuer")
    require(evidence["protocol"] == "viridis-security-preflight-evidence-v1",
            "Only manifest preflight evidence is supported")
    require(digest(evidence) == receipt["evidence_sha256"], "Evidence digest mismatch")
    unsigned = {k: v for k, v in receipt.items()
                if k not in ("receipt_id", "evidence_url")}
    require(receipt["receipt_id"] == "vsr_" + digest(unsigned)[:24],
            "Receipt identity mismatch")
    scanner = trust["scanner"]
    require(isinstance(scanner, dict) and set(scanner) == {"name", "version", "canon_digest"}
            and all(isinstance(v, str) and v for v in scanner.values()),
            "Operator must pin a scanner name, version and rules digest")
    require(receipt["scanner"] == scanner, "Scanner is not approved by operator")
    for field in ("subject_agent_id", "scanner", "result_counts", "coverage",
                  "claim_boundary", "posture"):
        require(receipt[field] == evidence[field], "Receipt and evidence disagree")
    current = now or datetime.now(timezone.utc)
    issued = datetime.fromisoformat(receipt["issued_at"])
    expires = datetime.fromisoformat(receipt["expires_at"])
    require(issued.tzinfo is not None and expires.tzinfo is not None,
            "Receipt timestamps must include timezone")
    require(issued <= current < expires and issued < expires
            and expires - issued <= timedelta(days=30), "Receipt is stale or not yet valid")
    require(inputs.get("action", "scan") == "scan", "Wrong action for this verifier")
    require(isinstance(inputs["agent_id"], str) and isinstance(inputs["manifest"], dict),
            "Invalid local inputs")
    policy = inputs.get("policy")
    policy = {} if policy is None else policy
    samples = inputs.get("sample_inputs")
    samples = [] if samples is None else samples
    require(isinstance(policy, dict) and isinstance(samples, list)
            and all(isinstance(v, str) for v in samples), "Invalid policy or samples")
    profile = str(inputs.get("subject_profile_sha256") or "").strip().lower() or None
    binding = evidence["subject_binding"]
    expected = {
        "agent_id": inputs["agent_id"], "manifest_sha256": digest(inputs["manifest"]),
        "policy_sha256": digest(policy), "sample_inputs_sha256": digest(samples),
        "profile_sha256": profile, "sample_input_count": len(samples),
        "artifact_sha256": digest({"manifest": inputs["manifest"], "policy": policy}),
    }
    require(all(binding.get(k) == v for k, v in expected.items()),
            "Receipt does not cover the exact local inputs")
    require(receipt["subject_agent_id"] == inputs["agent_id"], "Wrong agent identity")
    require(evidence["posture"] == "SCANNED" and evidence["runtime_tested"] is False
            and evidence["input_redacted"] is True, "Unsupported assessment boundary")
    counts = evidence["result_counts"]
    require(set(counts) == {"checks", "passed", "warnings", "findings", "errors"}
            and all(type(v) is int and v >= 0 for v in counts.values()),
            "Invalid assessment counts")
    verdict = evidence["verdict"]
    require(verdict in ("pass", "review", "fail"), "Unknown verdict")
    # An unsigned top-level verdict cannot change the authenticated assessment.
    passes = (verdict == "pass" and counts["findings"] == 0
              and counts["warnings"] == 0 and counts["errors"] == 0
              and counts["checks"] > 0 and counts["passed"] == counts["checks"])
    return {"status": "VERIFIED", "assessment": verdict,
            "decision": "PREFLIGHT_PASS" if passes else "REVIEW_REQUIRED",
            "receipt_id": receipt["receipt_id"], "expires_at": receipt["expires_at"],
            "public_key_sha256": hashlib.sha256(key).hexdigest(),
            "runtime_tested": False, "tool_execution_authorized": False,
            "claim_boundary": evidence["claim_boundary"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("result", "inputs", "trust"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        outcome = verify(*(json.loads(p.read_text()) for p in
                           (args.result, args.inputs, args.trust)))
        print(json.dumps(outcome, indent=2))
        return 0 if outcome["decision"] == "PREFLIGHT_PASS" else 2
    except (VerificationError, OSError, ValueError):
        print(json.dumps({"status": "STOPPED", "decision": "REVIEW_REQUIRED",
                          "message": "Evidence verification failed; do not execute or automatically repurchase."}),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
