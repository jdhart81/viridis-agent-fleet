#!/usr/bin/env python3
"""Reproduce two synthetic static-check examples offline; no receipt or payment."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "security-preflight-agent/src/core.py"
spec = importlib.util.spec_from_file_location("preflight_sample_core", CORE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def build_report():
    before = json.loads((ROOT / "examples/security-preflight-inputs.json").read_text())
    before["manifest"]["tools"][0]["name"] = "delete_records"
    before["manifest"]["tools"][0]["input_schema"]["additionalProperties"] = True
    before["policy"] = {"allowed_tools": ["delete_records"]}
    after = copy.deepcopy(before)
    after["manifest"]["tools"][0]["input_schema"]["additionalProperties"] = False
    after["policy"]["approval_required_tools"] = ["delete_records"]
    cases = []
    for label, payload in (("before", before), ("after", after)):
        checked = module.SecurityPreflightCore._validate_scan(payload)
        checks = module.SecurityPreflightCore._checks(checked)
        cases.append({"case": label, "synthetic_input": payload,
                      "counts": module.SecurityPreflightCore._counts(checks), "checks": checks})
    return {"kind": "unsigned_local_synthetic_example", "payment_attempted": False,
            "runtime_tested": False, "customer_evidence": False,
            "scanner_version": module.VERSION,
            "core_sha256": hashlib.sha256(CORE.read_bytes()).hexdigest(),
            "claim_boundary": module.CLAIM_BOUNDARY, "cases": cases}


if __name__ == "__main__":
    print(json.dumps(build_report(), indent=2))
