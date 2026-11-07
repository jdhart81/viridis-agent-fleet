"""Receipts (verification hook) and the read-only VergeCommon binding."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from conftest import clone

from viridis_eco_funding import make_receipt, receipt_text, verify_receipt
from viridis_eco_funding.canonical import sha256_hex, to_canonical_data, to_plain_json
from viridis_eco_funding.vergecommon import (
    MAX_RESPONSE_BYTES,
    ReadOnlyVergeCommonClient,
    VergeCommonError,
    bind_project,
    fetch_and_bind,
)


class _Resp(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_for(payload, status=200):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return lambda request, timeout: _Resp(body, status)


def test_receipt_round_trip_through_plain_json(woodland_site):
    receipt = make_receipt(woodland_site)
    over_the_wire = json.loads(json.dumps(to_plain_json(receipt)))  # floats, as an agent sees it
    report = verify_receipt(over_the_wire)
    assert report["valid"], report["checks"]
    assert {c["check"] for c in report["checks"]} >= {"inputs_sha256", "result_reproduced", "seal"}


@pytest.mark.parametrize("path, value", [
    (("result", "quantities", "complexity_score", "value"), 99),
    (("result", "explanation"), "edited"),
    (("inputs", "habitat", "patches", 0, "area_ha"), 70),
    (("inputs_sha256",), "0" * 64),
    (("seal", "digest"), "f" * 64),
    (("method_version",), "vef-method/9.9.9"),
])
def test_tampering_is_detected(woodland_site, path, value):
    receipt = to_plain_json(make_receipt(woodland_site))
    target = receipt
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert verify_receipt(receipt)["valid"] is False


def test_source_tampering_breaks_seal(woodland_site, synthetic_record):
    source = bind_project(synthetic_record, "proj-woodland-01", "https://vergecommon.com/api/network?id=x")
    receipt = to_plain_json(make_receipt(woodland_site, source=source))
    assert verify_receipt(receipt)["valid"]
    receipt["source"]["project_name"] = "Something else"
    report = verify_receipt(receipt)
    assert not report["valid"] and any(c["check"] == "seal" and not c["ok"] for c in report["checks"])


def test_malformed_receipts_are_reported_not_raised():
    assert verify_receipt([1, 2])["valid"] is False
    assert verify_receipt({"receipt_version": "x"})["valid"] is False
    assert verify_receipt({"a": object()})["valid"] is False
    bad_inputs = {"receipt_version": "vef-receipt/0.1", "method_version": "vef-method/0.1.0",
                  "inputs": {"site_id": "x"}, "inputs_sha256": "", "result": {}, "result_sha256": "",
                  "source": None, "explanation": "", "seal": {}}
    report = verify_receipt(bad_inputs)
    assert report["valid"] is False and report["checks"][-1]["check"] == "inputs_valid"


def test_source_record_comparison(woodland_site, synthetic_record):
    source = bind_project(synthetic_record, "proj-woodland-01", "u")
    receipt = make_receipt(woodland_site, source=source)
    assert verify_receipt(receipt, source_record=synthetic_record)["valid"]
    edited = clone(synthetic_record)
    edited["coop"]["summary"] = "edited later"
    report = verify_receipt(receipt, source_record=edited)
    assert report["valid"] is False
    assert "legitimately edited" in report["checks"][-1]["detail"]


def test_binding_hashes_canonical_record(synthetic_record):
    source = bind_project(synthetic_record, "proj-woodland-01", "u", observed_at="2026-10-31")
    assert source["record_sha256"] == sha256_hex(to_canonical_data(synthetic_record))
    assert source["project_kind"] == "woodland" and source["observed_at"] == "2026-10-31"
    assert "never instructions" in source["trust"]
    with pytest.raises(VergeCommonError, match="not public"):
        bind_project(synthetic_record, "missing-project", "u")
    with pytest.raises(VergeCommonError, match="coop"):
        bind_project({"coops": []}, "x", "u")


def test_receipt_with_binding_is_deterministic(woodland_site, synthetic_record):
    client = ReadOnlyVergeCommonClient(opener=opener_for(synthetic_record))
    a = receipt_text(make_receipt(woodland_site, source=fetch_and_bind(woodland_site, client)))
    b = receipt_text(make_receipt(woodland_site, source=fetch_and_bind(woodland_site, client)))
    assert a == b


@pytest.mark.parametrize("payload, status, message", [
    ({"error": "nope"}, 200, "no 'coop'"),
    (b"not json", 200, "invalid JSON"),
    (b"x" * (MAX_RESPONSE_BYTES + 10), 200, "too large"),
    ({"coop": {}}, 500, "HTTP 500"),
])
def test_client_errors(payload, status, message):
    client = ReadOnlyVergeCommonClient(opener=opener_for(payload, status))
    with pytest.raises(VergeCommonError, match=message):
        client.get_public_coop("5b0e2c1a-7d4f-4e8a-9c3b-2f6a1d8e4b70")


def test_client_network_errors_are_wrapped():
    def http_error(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    def url_error(request, timeout):
        raise urllib.error.URLError("offline")

    for opener, message in ((http_error, "HTTP 404"), (url_error, "could not reach")):
        with pytest.raises(VergeCommonError, match=message):
            ReadOnlyVergeCommonClient(opener=opener).get_public_coop("5b0e2c1a-7d4f-4e8a-9c3b-2f6a1d8e4b70")


def test_client_input_validation(woodland_site):
    client = ReadOnlyVergeCommonClient(opener=opener_for({"coops": []}))
    with pytest.raises(VergeCommonError, match="UUID"):
        client.get_public_coop("../../admin")
    with pytest.raises(VergeCommonError, match="limit"):
        client.list_public_coops(0)
    assert client.list_public_coops(1)["record"] == {"coops": []}
    site = clone(woodland_site)
    del site["vergecommon"]
    with pytest.raises(VergeCommonError, match="binding"):
        fetch_and_bind(site, client)
    with pytest.raises(VergeCommonError, match="coops"):
        ReadOnlyVergeCommonClient(opener=opener_for({"coop": {}})).list_public_coops(3)


@pytest.mark.network
def test_live_public_directory_is_readable():
    import os
    if os.environ.get("VEF_LIVE_NETWORK") != "1":
        pytest.skip("set VEF_LIVE_NETWORK=1 to read the live public directory")
    out = ReadOnlyVergeCommonClient().list_public_coops(5)
    assert isinstance(out["record"]["coops"], list)


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(extra_claim="certified"),
    lambda r: r["seal"].update(kind="identity signature by a registry"),
    lambda r: r["seal"].update(extra=1),
    lambda r: r.update(explanation="edited"),
    lambda r: r.pop("explanation"),
])
def test_receipt_shape_is_exact(woodland_site, mutate):
    receipt = to_plain_json(make_receipt(woodland_site))
    mutate(receipt)
    assert verify_receipt(receipt)["valid"] is False
