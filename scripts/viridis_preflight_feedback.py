#!/usr/bin/env python3
"""Preview buyer-chosen feedback; send once only with --submit and private output.

Uses the existing paid-result feedback contract. Never pays, subscribes, infers
usefulness, follows redirects, or prints the result's private bearer token.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from viridis_preflight_watch import baseline_from_paid_result

VERSION = "viridis-buyer-feedback-v1"
ENDPOINTS = frozenset({
    "https://mcp.viridis-security.com/x402/feedback",
    "https://mcp.viridisconservation.com/x402/feedback",
})
OUTCOMES = ("USEFUL", "PARTIALLY_USEFUL", "NOT_USEFUL")
REASONS = ("accurate", "actionable", "fresh", "missing_evidence",
           "not_actionable", "not_relevant", "other")


class FeedbackError(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def prepare(result, *, outcome, would_buy_again, reason=None):
    """Return a private request and a separate safe preview. Do not log request."""
    if outcome not in OUTCOMES or type(would_buy_again) is not bool or (
            reason is not None and reason not in REASONS):
        raise FeedbackError("Choose an outcome, yes/no repeat intent and a supported reason.")
    try:
        baseline_from_paid_result(result)
        delivery = result["viridis_delivery"]
        feedback = delivery["feedback"]
        endpoint = feedback["endpoint"]
        token = feedback["feedback_token"]
        if (feedback["version"] != VERSION or feedback["method"] != "POST"
                or endpoint not in ENDPOINTS or feedback.get("exactly_once") is not True
                or not isinstance(token, str) or not 32 <= len(token) <= 256):
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise FeedbackError("Saved result or its supported feedback contract did not validate.") from None
    # Same result and buyer choices produce the same server idempotency key,
    # including after a lost response. A different opinion cannot overwrite it.
    identity = {"receipt_sha256": delivery["receipt_sha256"], "outcome": outcome,
                "would_buy_again": would_buy_again, "reason_code": reason}
    payload = {"feedback_token": token, "outcome": outcome,
               "would_buy_again": would_buy_again, "reason_code": reason,
               "idempotency_key": "preflight-feedback-" + _digest(identity)[:32]}
    preview = {"status": "FEEDBACK_PREVIEW", "endpoint": endpoint,
               "outcome": outcome, "would_buy_again": would_buy_again,
               "reason_code": reason, "idempotency_key": payload["idempotency_key"],
               "feedback_recorded": False, "payment_attempted": False,
               "classification": "buyer_possession_feedback",
               "independently_verified": False, "revenue_signal": False}
    return payload, preview


def post(endpoint, payload, timeout):
    request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(),
        method="POST", headers={"Content-Type": "application/json",
                               "Accept": "application/json",
                               "User-Agent": "viridis-preflight-feedback/1.0"})
    try:
        response = urllib.request.build_opener(NoRedirect).open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read(65537)
        if len(raw) > 65536:
            raise FeedbackError("Feedback response exceeded the supported size.")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            body = None
        return response.code, body


def _save(handle, value):
    handle.seek(0)
    json.dump(value, handle, indent=2, allow_nan=False)
    handle.write("\n")
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def run(result, *, outcome, would_buy_again, reason=None, submit=False,
        output=None, timeout=20, transport=post):
    payload, preview = prepare(result, outcome=outcome,
                               would_buy_again=would_buy_again, reason=reason)
    if not submit:
        return preview
    if output is None:
        raise FeedbackError("Submission requires a new --output receipt file.")
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        raise FeedbackError("Use a new --output file in an existing writable directory.") from None
    with os.fdopen(fd, "w") as handle:
        pending = {**preview, "status": "FEEDBACK_OUTCOME_UNKNOWN", "feedback_recorded": None}
        _save(handle, pending)
        try:
            status, body = transport(preview["endpoint"], payload, timeout)
        except Exception:
            raise FeedbackError("Feedback outcome unknown. Keep the receipt; reconcile before retrying unchanged choices.") from None
        try:
            actual = body["feedback"]
            request_digest = _digest({**{k: payload[k] for k in
                ("outcome", "would_buy_again", "reason_code", "idempotency_key")},
                "note_sha256": None})
            recorded_at = datetime.fromisoformat(actual["recorded_at"])
            valid = (status in (200, 201) and body["version"] == VERSION
                     and body["status"] == "RECORDED" and body["feedback_recorded"] is True
                     and type(body.get("idempotent_replay")) is bool
                     and actual["version"] == VERSION
                     and actual["classification"] == "buyer_possession_feedback"
                     and actual["independently_verified"] is False
                     and actual["revenue_signal"] is False
                     and actual["useful"] is (outcome == "USEFUL")
                     and type(actual["would_buy_again"]) is bool
                     and actual["note_sha256"] is None
                     and actual["request_sha256"] == request_digest
                     and recorded_at.tzinfo is not None
                     and all(actual.get(k) == payload[k] for k in
                             ("outcome", "would_buy_again", "reason_code", "idempotency_key")))
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            # Do not print or persist arbitrary remote fields: they may echo the
            # private token or incorrectly claim a recorded outcome.
            _save(handle, {**pending, "http_status": status})
            raise FeedbackError("Feedback was not confirmed. Keep the receipt and reconcile; no automatic retry was made.")
        summary = {**preview, "status": "RECORDED", "feedback_recorded": True,
                   "idempotent_replay": body["idempotent_replay"],
                   "request_sha256": request_digest,
                   "recorded_at": recorded_at.isoformat()}
        _save(handle, summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paid-result", type=Path, required=True)
    parser.add_argument("--outcome", choices=OUTCOMES, required=True)
    parser.add_argument("--would-buy-again", choices=("yes", "no"), required=True)
    parser.add_argument("--reason", choices=REASONS)
    parser.add_argument("--submit", action="store_true", help="Send the buyer's explicit feedback once")
    parser.add_argument("--output", type=Path, help="New private local confirmation file")
    parser.add_argument("--timeout", type=int, default=20, choices=range(1, 121), metavar="SECONDS")
    args = parser.parse_args(argv)
    try:
        result = run(json.loads(args.paid_result.read_text()), outcome=args.outcome,
                     would_buy_again=args.would_buy_again == "yes", reason=args.reason,
                     submit=args.submit, output=args.output, timeout=args.timeout)
        print(json.dumps(result, indent=2))
        return 0
    except FeedbackError as exc:
        print(json.dumps({"status": "STOPPED", "feedback_recorded": None,
                          "message": str(exc), "payment_attempted": False}), file=sys.stderr)
        return 1
    except (ValueError, OSError, TypeError, KeyError, AttributeError):
        print(json.dumps({"status": "STOPPED", "feedback_recorded": None,
                          "message": "Feedback not confirmed. Check the private output if present; do not infer acceptance or retry automatically.",
                          "payment_attempted": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
