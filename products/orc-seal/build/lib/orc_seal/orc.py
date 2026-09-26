"""Outcome Receipt (ORC) v0.1 — reference implementation. Stdlib only.

An ORC is a portable, verifiable record that an agent produced a specific
output. It is rail-neutral: it can bind to an x402 settlement, a Stripe
charge, an AP2 mandate, or an ERC-8004 validation response, but it never
depends on any of them. Spec: docs/standards/OUTCOME_RECEIPT_v0.1.md

Verification levels (each implies the ones before it):
  L1 INTACT     digest recomputes from `output`, and the commitment binds it
  L2 ISSUED     the issuer proves it sealed this commitment (registry record
                or Ed25519 signature; checked by a caller-supplied resolver)
  L3 SETTLED    a payment binding is confirmed by its own rail (resolver)
  L4 VALIDATED  an independent validator attested the same commitment

--- INVARIANTS ---
R1  canonical() is byte-identical to the fleet engines' canonical form:
    json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True).
R2  seal() never mutates its input; the same output + excludes always give
    the same digest (salt only changes the commitment).
R3  verify() never raises; malformed input yields level 0 with reasons.
R4  L1 requires BOTH digest recomputation and commitment recomputation.
R5  Levels above L1 are granted only by an explicit resolver returning True;
    absent resolvers leave the level capped and say why (no silent upgrade).
R6  Floats are rejected in `output` at seal time (money and quantities must be
    integers or decimal strings), so any language can reproduce the digest.
R7  from_cliff_check() maps a Signed Cliff Check receipt losslessly: the ORC
    digest equals the engine's audit_sha256 and the commitment is unchanged.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Optional

ORC_VERSION = "0.1"
CANON_ID = "orc-canon/1"
COMMIT_SCHEME = "sha256(salt||digest)"
Resolver = Callable[[dict], bool]


def canonical(value: Any) -> str:                                        # R1
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _has_float(v: Any) -> bool:
    if isinstance(v, float):
        return True
    if isinstance(v, dict):
        return any(_has_float(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return any(_has_float(x) for x in v)
    return False


def _is_hex64(s: Any) -> bool:
    return isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def digest_of(output: dict, excludes: list[str]) -> str:
    content = {k: v for k, v in output.items() if k not in set(excludes)}
    return sha256_hex(canonical(content))


def seal(output: dict, *, issuer: dict, subject: dict, profile: str = "generic",
         excludes: Optional[list[str]] = None, bindings: Optional[dict] = None,
         salt: Optional[str] = None, issued_at: Optional[str] = None) -> dict:
    """Build an ORC receipt. Pure function except for the random salt."""
    if not isinstance(output, dict):
        raise ValueError("output must be a JSON object")
    if _has_float(output):                                               # R6
        raise ValueError("floats are not allowed in output; use integers or decimal strings")
    excludes = list(excludes or [])
    out = deepcopy(output)                                               # R2
    d = digest_of(out, excludes)
    salt = salt or secrets.token_hex(32)
    return {
        "orc": ORC_VERSION, "profile": profile,
        "issuer": deepcopy(issuer), "subject": deepcopy(subject),
        "output": out,
        "digest": {"alg": "sha256", "canonicalization": CANON_ID,
                   "excludes": excludes, "value": d},
        "commitment": {"scheme": COMMIT_SCHEME, "salt": salt,
                       "value": sha256_hex(salt + d)},
        "bindings": deepcopy(bindings or {}),
        "issued_at": issued_at or datetime.now(timezone.utc).isoformat(),
    }


def verify(receipt: Any, *, issuer_resolver: Optional[Resolver] = None,
           payment_resolver: Optional[Resolver] = None,
           validation_resolver: Optional[Resolver] = None) -> dict:
    """Return {level, checks, reasons}. Never raises (R3)."""
    reasons: list[str] = []
    checks = {"digest_recomputes": False, "commitment_binds": False,
              "issuer_proven": None, "payment_settled": None, "validated": None}

    def done(level: int) -> dict:
        return {"level": level, "label": ["NONE", "INTACT", "ISSUED", "SETTLED",
                                          "VALIDATED"][level],
                "checks": checks, "reasons": reasons}
    try:
        if not isinstance(receipt, dict) or receipt.get("orc") != ORC_VERSION:
            reasons.append("not an ORC v0.1 receipt"); return done(0)
        dg, cm, out = receipt.get("digest", {}), receipt.get("commitment", {}), receipt.get("output")
        if dg.get("canonicalization") != CANON_ID or dg.get("alg") != "sha256":
            reasons.append("unsupported digest algorithm or canonicalization"); return done(0)
        if cm.get("scheme") != COMMIT_SCHEME or not _is_hex64(cm.get("salt")):
            reasons.append("unsupported commitment scheme or bad salt"); return done(0)
        if not isinstance(out, dict):
            reasons.append("output must be an object"); return done(0)
        excl = dg.get("excludes", [])
        if not isinstance(excl, list) or not all(isinstance(x, str) for x in excl):
            reasons.append("digest.excludes must be a list of strings"); return done(0)
        computed = digest_of(out, excl)
        checks["digest_recomputes"] = computed == dg.get("value")
        checks["commitment_binds"] = sha256_hex(cm["salt"] + str(dg.get("value"))) == cm.get("value")
        if not (checks["digest_recomputes"] and checks["commitment_binds"]):     # R4
            if not checks["digest_recomputes"]:
                reasons.append("output was altered: digest does not recompute")
            if not checks["commitment_binds"]:
                reasons.append("commitment does not bind the digest")
            return done(0)
        level = 1
        for key, res, need in (("issuer_proven", issuer_resolver, "issuer"),
                               ("payment_settled", payment_resolver, "payment"),
                               ("validated", validation_resolver, "validation")):  # R5
            if res is None:
                reasons.append(f"no {need} resolver supplied; level capped at {level}")
                return done(level)
            ok = bool(res(receipt))
            checks[key] = ok
            if not ok:
                reasons.append(f"{need} check failed; level capped at {level}")
                return done(level)
            level += 1
        return done(level)
    except Exception as exc:  # R3: never raise
        reasons.append(f"malformed receipt: {type(exc).__name__}")
        return done(0)


CLIFF_EXCLUDES = ["audit_sha256", "notary_payload"]


def from_cliff_check(cc: dict) -> dict:                                  # R7
    """Map a Signed Cliff Check receipt (v0.1/v0.2) to ORC v0.1, losslessly."""
    res, sig = cc["result"], cc["signature"]
    orc = {
        "orc": ORC_VERSION, "profile": "viridis.cliff-check/" + cc["credit"],
        "issuer": {"id": "did:web:viridisconservation.com", "name": "Viridis LLC"},
        "subject": {"agent": "taxcredit-engine", "tool": "calculate_tax_credit",
                    "product": cc.get("product"), "product_version": cc.get("product_version"),
                    "client": cc.get("client"), "project": cc.get("project")},
        "output": deepcopy(res),
        "digest": {"alg": "sha256", "canonicalization": CANON_ID,
                   "excludes": list(CLIFF_EXCLUDES), "value": res["audit_sha256"]},
        "commitment": {"scheme": COMMIT_SCHEME, "salt": sig["salt"],
                       "value": sig["commit_hash"]},
        "bindings": {},
        "issued_at": cc.get("generated_at"),
    }
    if cc.get("verify", {}).get("page"):
        orc["verify"] = {"page": cc["verify"]["page"]}
    return orc


def erc8004_validation_response(receipt: dict, *, request_hash: str,
                                response_uri: str, passed: bool) -> dict:
    """Unsigned ERC-8004 Validation-Registry response fields for an ORC.

    Maps: responseHash = commitment.value, responseURI = where the ORC is
    published, response = 100 (pass) or 0 (fail), tag = "orc/0.1".
    The caller's own signer submits it; this function never touches a chain.
    """
    if not _is_hex64(request_hash):
        raise ValueError("request_hash must be 64 lowercase hex chars")
    return {"requestHash": "0x" + request_hash,
            "response": 100 if passed else 0,
            "responseURI": response_uri,
            "responseHash": "0x" + receipt["commitment"]["value"],
            "tag": "orc/" + ORC_VERSION}
