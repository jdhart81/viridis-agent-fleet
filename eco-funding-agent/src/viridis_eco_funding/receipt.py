"""Reproducible valuation receipts (``vef-receipt/0.1``).

A receipt embeds the normalized inputs, the method version and the result, plus SHA-256
digests over their canonical JSON bytes, and a seal digest over all of it. Anyone can
re-run ``verify_receipt`` offline: it re-normalizes the inputs, recomputes the valuation
and checks every digest. Same inputs and method version give a byte-identical receipt
(Invariant 1); the receipt never contains a wall-clock time unless the caller supplies
``observed_at`` as an input.

What the seal is and is not: it is a content digest that makes any change detectable and
lets a third party reproduce the result. It is not an identity signature: it does not
prove *who* produced the receipt. Identity signatures need a signing key, which v0.1
deliberately does not handle (Invariant 5); see LIMITS.md.
"""

from __future__ import annotations

from typing import Any

from ._decimal import pinned
from .canonical import canonical_dumps, sha256_hex, to_canonical_data
from .constants import CONJECTURE_LABEL, METHOD_VERSION, RECEIPT_VERSION
from .inputs import SiteInputError, normalize_site_inputs
from .valuation import evaluate

SUPPORTED_METHODS = frozenset({METHOD_VERSION})
SEAL_KIND = "content digest (not an identity signature)"
RECEIPT_FIELDS = frozenset({"receipt_version", "method_version", "inputs", "inputs_sha256", "result",
                            "result_sha256", "source", "explanation", "seal"})


def _seal_body(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "receipt_version": receipt["receipt_version"],
        "method_version": receipt["method_version"],
        "inputs_sha256": receipt["inputs_sha256"],
        "result_sha256": receipt["result_sha256"],
        "source": receipt["source"],
    }


@pinned
def make_receipt(raw_inputs: Any, source: dict[str, Any] | None = None) -> dict[str, Any]:
    """Value a site and return a sealed receipt (canonical data, Decimals inside)."""
    inputs = normalize_site_inputs(raw_inputs)
    result = evaluate(inputs)
    receipt = {
        "receipt_version": RECEIPT_VERSION,
        "method_version": METHOD_VERSION,
        "inputs": inputs,
        "inputs_sha256": sha256_hex(inputs),
        "result": result,
        "result_sha256": sha256_hex(result),
        "source": to_canonical_data(source) if source is not None else None,
        "explanation": result["explanation"],
    }
    receipt["seal"] = {"algorithm": "sha256", "digest": sha256_hex(_seal_body(receipt)),
                       "kind": SEAL_KIND}
    return receipt


def receipt_text(receipt: dict[str, Any]) -> str:
    """Canonical JSON text of a receipt (the byte form that Invariant 1 compares)."""
    return canonical_dumps(to_canonical_data(receipt))


def _claims_bound(data: Any) -> bool:
    """Whether a (possibly invalid) receipt claims a result that uses the bound."""
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        return False
    quantities = result.get("quantities")
    return bool(result.get("uses_intelligence_bound")) or (isinstance(quantities, dict) and any(
        isinstance(q, dict) and q.get("status") == CONJECTURE_LABEL for q in quantities.values()))


@pinned
def verify_receipt(receipt: Any, source_record: Any | None = None) -> dict[str, Any]:
    """Re-run a receipt and check every digest. Never raises on a bad receipt; reports it.

    ``source_record`` (optional) is a freshly fetched VergeCommon public record; if given,
    its canonical digest is compared with the one bound into the receipt.
    """
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        checks.append({"check": name, "ok": ok, "detail": detail})
        return ok

    try:
        data = to_canonical_data(receipt)
    except (TypeError, ValueError) as exc:
        data = None
        check("parse", False, str(exc))
    if not isinstance(data, dict):
        if data is not None:
            check("parse", False, "receipt must be a JSON object")
        return _report(False, checks, False)

    claims = _claims_bound(data)
    missing = sorted(RECEIPT_FIELDS - set(data))
    extra = sorted(set(data) - RECEIPT_FIELDS)
    detail = "; ".join(filter(None, [f"missing {missing}" if missing else "",
                                     f"unexpected {extra}" if extra else ""])) or "exactly the receipt fields"
    if not check("fields", not missing and not extra, detail):
        return _report(False, checks, claims)

    check("receipt_version", data["receipt_version"] == RECEIPT_VERSION,
          f"{data['receipt_version']} (supported: {RECEIPT_VERSION})")
    if not check("method_version", data["method_version"] in SUPPORTED_METHODS,
                 f"{data['method_version']} (supported: {sorted(SUPPORTED_METHODS)})"):
        return _report(False, checks, claims)

    try:
        inputs = normalize_site_inputs(data["inputs"])
    except SiteInputError as exc:
        check("inputs_valid", False, str(exc))
        return _report(False, checks, claims)
    check("inputs_canonical", canonical_dumps(inputs) == canonical_dumps(data["inputs"]),
          "embedded inputs are in normalized form")
    check("inputs_sha256", sha256_hex(inputs) == data["inputs_sha256"])

    recomputed = evaluate(inputs)
    check("result_reproduced", canonical_dumps(recomputed) == canonical_dumps(data["result"]),
          "re-running the method on the inputs gives byte-identical output")
    check("result_sha256", sha256_hex(recomputed) == data["result_sha256"])
    check("explanation", data["explanation"] == recomputed["explanation"],
          "top-level explanation matches the recomputed result")

    seal = data["seal"] if isinstance(data["seal"], dict) else {}
    expected_seal = sha256_hex(_seal_body({**data, "inputs_sha256": sha256_hex(inputs),
                                           "result_sha256": sha256_hex(recomputed)}))
    check("seal", seal == {"algorithm": "sha256", "digest": expected_seal, "kind": SEAL_KIND},
          "seal digest, algorithm and kind match exactly")

    if source_record is not None:
        bound = (data["source"] or {}).get("record_sha256")
        fresh = sha256_hex(to_canonical_data(source_record))
        check("source_record", bound == fresh,
              "public record unchanged since the receipt" if bound == fresh else
              "public record differs from the one bound into the receipt (it may have been "
              "legitimately edited since)")

    ok = all(item["ok"] for item in checks)
    return _report(ok, checks, claims or bool(recomputed.get("uses_intelligence_bound")))


def _report(ok: bool, checks: list[dict[str, Any]], uses_bound: bool) -> dict[str, Any]:
    explanation = ("Receipt verified: the result was reproduced byte for byte from the embedded "
                   "inputs and every digest matches." if ok else
                   "Receipt NOT verified: " + "; ".join(
                       f"{c['check']} failed" + (f" ({c['detail']})" if c["detail"] else "")
                       for c in checks if not c["ok"]) + ".")
    if uses_bound:
        explanation += (" The valuation includes (or claims) the intelligence-bound "
                        "complexity-capacity term, which is a conjecture.")
    explanation += (" Verification shows reproducibility, not that the inputs are true, and the "
                    "seal is a content digest, not an identity signature.")
    return {
        "valid": ok,
        "checks": checks,
        "uses_intelligence_bound": uses_bound,
        "labels": {"intelligence_bound": CONJECTURE_LABEL if uses_bound else "not used"},
        "explanation": explanation,
    }
