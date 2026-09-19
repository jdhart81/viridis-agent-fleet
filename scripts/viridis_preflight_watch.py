#!/usr/bin/env python3
"""Buyer-owned change check suitable for a release pipeline or scheduler.

Reads the buyer's current JSON and optional saved paid result, checks its
delivery digest locally, then asks the free watch endpoint whether another
assessment is needed. Never signs, pays, records feedback, or scans a runtime.
Default mode reports changes. --ci additionally requires an operator-pinned
--trust file and --paid-result; exit 0 requires an unchanged, authenticated
passing assessment. Exit 2 needs review/recheck; exit 1 is unavailable or invalid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from viridis_adoption_client import _post

DEFAULT_BASE_URL = "https://mcp.viridis-security.com"


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def baseline_from_paid_result(result):
    if not isinstance(result, dict) or result.get("status") != "ok":
        raise ValueError("expected a successful saved paid result")
    delivery = result.get("viridis_delivery", {})
    if delivery.get("version") != "viridis-paid-delivery-v1":
        raise ValueError("missing supported delivery receipt")
    if delivery.get("route") != "security-preflight/security_preflight":
        raise ValueError("saved result belongs to another route")
    content = {k: v for k, v in result.items() if k != "viridis_delivery"}
    if _digest(content) != delivery.get("result_sha256"):
        raise ValueError("saved result digest mismatch")
    receipt = {k: v for k, v in delivery.items() if k != "receipt_sha256"}
    if _digest(receipt) != delivery.get("receipt_sha256"):
        raise ValueError("delivery receipt digest mismatch")
    if not delivery.get("settlement", {}).get("transaction"):
        raise ValueError("missing settlement reference")
    baseline = result.get("receipt", {}).get("receipt_id")
    if not isinstance(baseline, str):
        raise ValueError("missing security baseline receipt")
    # Hashes establish file consistency only; the server independently checks
    # its authentic stored assessment. Payment verification remains separate.
    return baseline


def check(base_url, inputs, baseline_receipt_id=None, timeout=20):
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base URL must be HTTPS without credentials, query, or fragment")
    response = _post(base_url.rstrip("/") + "/security-preflight/watch", {
        "inputs": inputs, "baseline_receipt_id": baseline_receipt_id,
    }, timeout)
    if response["status_code"] != 200:
        raise ValueError(f"watch returned HTTP {response['status_code']}")
    result = response["body"]
    if not isinstance(result, dict) or result.get("version") != "viridis-preflight-watch-v1" or result.get("decision") not in {
            "BASELINE_REQUIRED", "UNCHANGED", "RECHECK_REQUIRED"}:
        raise ValueError("unsupported watch response")
    if result.get("payment_authorized") is not False or result.get("tool_executed") is not False:
        raise ValueError("watch violated read-only contract")
    return result


def ci_gate(base_url, inputs, paid_result, trust, timeout=20):
    """Return (redacted summary, exit code); never turn change detection into permission.

    Fetch the free change decision first so expired/changed inputs can return an
    actionable recheck without trying to verify an old receipt against new inputs.
    Only the unchanged branch can pass, and it must verify the saved signed
    assessment locally against current inputs and the operator's trust pins.
    """
    from viridis_security_verify import verify

    baseline_id = baseline_from_paid_result(paid_result)
    result = check(base_url, inputs, baseline_id, timeout)
    if any(result.get(key) is not False for key in (
            "payment_authorized", "tool_executed", "state_persisted",
            "runtime_execution_authorized", "runtime_tested",
            "managed_subscription_active")):
        raise ValueError("watch violated read-only contract")
    decision = result["decision"]
    reasons = result.get("reasons")
    if (not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons)
            or len(reasons) != len(set(reasons))):
        raise ValueError("invalid watch reasons")
    baseline = result.get("baseline")
    changed = result.get("changed_fields", [])
    binding_fields = {"agent_id", "manifest_sha256", "policy_sha256",
                      "sample_inputs_sha256", "profile_sha256"}
    if (not isinstance(changed, list) or not all(isinstance(field, str) for field in changed)
            or len(changed) != len(set(changed)) or set(changed) - binding_fields):
        raise ValueError("invalid changed fields")
    if decision == "BASELINE_REQUIRED":
        if reasons != ["no_baseline"] or baseline is not None or changed:
            raise ValueError("contradictory baseline response")
    else:
        if (not isinstance(baseline, dict) or baseline.get("receipt_id") != baseline_id
                or baseline.get("verdict") not in {"pass", "review", "fail"}):
            raise ValueError("watch baseline does not match the saved assessment")
        if decision == "UNCHANGED":
            if (reasons or changed or result.get("quote_request") is not None
                    or result.get("next_action") != "reuse_assessment_with_existing_findings"):
                raise ValueError("contradictory unchanged response")
        elif (not reasons or set(reasons) - {"inputs_changed", "assessment_expired",
                "scanner_changed", "baseline_binding_upgrade_required"}
                or bool(changed) != bool(set(reasons) & {
                    "inputs_changed", "baseline_binding_upgrade_required"})):
            raise ValueError("contradictory recheck response")
    if decision != "UNCHANGED":
        quote = result.get("quote_request")
        if (result.get("next_action") != "fetch_unpaid_quote"
                or not isinstance(quote, dict) or quote.get("auto_pay") is not False
                or quote.get("operator_budget_required") is not True):
            raise ValueError("invalid read-only next action")
        return {"status": "REVIEW_REQUIRED", "watch_decision": decision,
                "reasons": reasons, "changed_fields": changed,
                "next_action": "review_changes_then_separately_authorize_a_quote_if_needed",
                "payment_attempted": False, "tool_execution_authorized": False}, 2

    authenticated = verify(paid_result, inputs, trust)
    evidence = paid_result["evidence"]
    receipt = paid_result["receipt"]
    expected_binding = {key: evidence["subject_binding"][key] for key in binding_fields}
    if (result.get("current_binding") != expected_binding
            or baseline.get("verdict") != authenticated["assessment"]
            or baseline.get("expires_at") != authenticated["expires_at"]
            or baseline.get("result_counts") != receipt["result_counts"]):
        raise ValueError("watch disagrees with authenticated evidence")
    passing = authenticated["decision"] == "PREFLIGHT_PASS"
    return {"status": "PREFLIGHT_PASS" if passing else "REVIEW_REQUIRED",
            "watch_decision": decision, "assessment": authenticated["assessment"],
            "receipt_id": authenticated["receipt_id"],
            "expires_at": authenticated["expires_at"],
            "next_action": "continue_remaining_checks" if passing else "review_existing_findings",
            "payment_attempted": False, "tool_execution_authorized": False}, 0 if passing else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True,
                        help="Current caller-owned assessment JSON")
    baseline = parser.add_mutually_exclusive_group()
    baseline.add_argument("--paid-result", type=Path, help="Saved complete paid response JSON")
    baseline.add_argument("--baseline-receipt-id")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--ci", action="store_true", help="Fail the gate unless the unchanged assessment verifies and passes locally")
    parser.add_argument("--trust", type=Path, help="Operator-pinned issuer key and scanner policy; required with --ci")
    args = parser.parse_args(argv)
    if args.ci and (args.paid_result is None or args.trust is None):
        parser.error("--ci requires --paid-result and --trust")
    if args.trust and not args.ci:
        parser.error("--trust requires --ci so verification cannot be silently skipped")
    try:
        inputs = json.loads(args.inputs.read_text())
        saved = json.loads(args.paid_result.read_text()) if args.paid_result else None
        if args.ci:
            result, code = ci_gate(args.base_url, inputs, saved,
                                   json.loads(args.trust.read_text()), args.timeout)
        else:
            baseline_id = baseline_from_paid_result(saved) if args.paid_result else args.baseline_receipt_id
            result = check(args.base_url, inputs, baseline_id, args.timeout)
            code = 0
        print(json.dumps(result, indent=2, sort_keys=True))
        return code
    except Exception as exc:
        # CI logs must not expose raw response bodies, input paths, or tokens,
        # including data carried inside a transport or validation exception.
        message = ("Change check or evidence verification unavailable or invalid; inspect locally, do not automatically repurchase."
                   if args.ci else str(exc))
        print(json.dumps({"status": "STOPPED" if args.ci else "error", "message": message,
                          "payment_attempted": False, "tool_execution_authorized": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
