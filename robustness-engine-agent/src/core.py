"""Transport-independent core for the Viridis robustness agent service."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


AGENT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_kernel_root() -> Path:
    configured = os.environ.get("ROBUSTNESS_ENGINE_BUNDLE_ROOT")
    candidates = [Path(configured)] if configured else []
    candidates.append(AGENT_ROOT / "vendor")
    candidates.extend(parent / "src" for parent in AGENT_ROOT.parents)
    for candidate in candidates:
        if (candidate / "robustness_engine" / "engine.py").is_file():
            return candidate.resolve()
    raise RuntimeError("No bundled robustness_engine package is available")


KERNEL_ROOT = _resolve_kernel_root()
if str(KERNEL_ROOT) not in sys.path:
    sys.path.insert(0, str(KERNEL_ROOT))

from robustness_engine.engine import ENGINE_VERSION, evaluate_case  # noqa: E402


SERVICE_VERSION = "0.6.0"
FINAL_RELEASE_STATE = "FINAL_LEAN_PROVEN_FLEET_DEPLOYED"
FORMAL_STATE = "ARISTOTLE_AUDITED_VERIFIED_ZERO_SORRY"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OCI_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class RobustnessAgentConfig:
    max_request_bytes: int = 2 * 1024 * 1024
    release_mode: str = "prototype"


class RobustnessAgent:
    """Evaluate complete decision bundles without executing their decisions."""

    def __init__(self, config: RobustnessAgentConfig | None = None):
        self.config = config or RobustnessAgentConfig(
            release_mode=os.environ.get(
                "ROBUSTNESS_SERVICE_RELEASE_MODE",
                "prototype",
            )
        )

    def _request_size(self, payload: dict[str, Any]) -> int:
        try:
            rendered = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("Request must be finite canonical JSON data") from exc
        return len(rendered)

    def _release_manifest_status(self) -> dict[str, Any]:
        manifest_path = Path(os.environ.get(
            "ROBUSTNESS_RELEASE_MANIFEST_PATH",
            str(AGENT_ROOT / "RELEASE_MANIFEST.json"),
        ))
        if not manifest_path.is_file():
            return {
                "present": False,
                "valid_for_final": False,
                "state": "NOT_PRESENT",
                "sha256": None,
            }
        try:
            raw = manifest_path.read_bytes()
            manifest = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return {
                "present": True,
                "valid_for_final": False,
                "state": "INVALID",
                "sha256": None,
            }
        hash_fields = (
            "paper_pdf_sha256",
            "paper_manifest_sha256",
            "lean_source_sha256",
            "aristotle_audit_sha256",
            "formal_receipt_sha256",
            "engine_receipt_sha256",
            "canon_candidate_sha256",
            "service_source_sha256",
            "rollback_plan_sha256",
        )
        hashes_valid = all(
            isinstance(manifest.get(field), str)
            and SHA256_RE.fullmatch(manifest[field]) is not None
            for field in hash_fields
        )
        deployed_digest = os.environ.get("ROBUSTNESS_DEPLOYED_ARTIFACT_DIGEST")
        manifest_digest = manifest.get("deployment_artifact_digest")
        digest_valid = (
            isinstance(deployed_digest, str)
            and OCI_DIGEST_RE.fullmatch(deployed_digest) is not None
            and deployed_digest == manifest_digest
        )
        checks = {
            "schema_version": manifest.get("schema_version") == "2.0",
            "release_state": manifest.get("state") == FINAL_RELEASE_STATE,
            "engine_version": manifest.get("engine_version") == ENGINE_VERSION,
            "service_version": manifest.get("service_version") == SERVICE_VERSION,
            "formal_state": (
                manifest.get("formal_state") == FORMAL_STATE
            ),
            "paper_reconciled": manifest.get("paper_reconciled") is True,
            "canon_candidate_reconciled": (
                manifest.get("canon_candidate_reconciled") is True
            ),
            "production_deployed": manifest.get("production_deployed") is True,
            "artifact_hashes": hashes_valid,
            "running_artifact_digest": digest_valid,
        }
        valid = all(checks.values())
        return {
            "present": True,
            "valid_for_final": bool(valid),
            "state": manifest.get("state", "INVALID"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "checks": checks,
        }

    async def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Request must be a JSON object")
        if self._request_size(payload) > self.config.max_request_bytes:
            raise ValueError("Request exceeds the configured size limit")
        allowed = {"operation", "case", "outcomes", "request_id"}
        extra = sorted(set(payload) - allowed)
        if extra:
            raise ValueError(f"Unknown request fields: {', '.join(extra)}")
        if payload.get("operation") != "evaluate":
            raise ValueError("operation must be 'evaluate'")
        case = payload.get("case")
        outcomes = payload.get("outcomes")
        if not isinstance(case, dict) or not isinstance(outcomes, dict):
            raise ValueError("case and outcomes must be JSON objects")
        request_id = payload.get("request_id")
        if request_id is not None and (
            not isinstance(request_id, str)
            or not request_id
            or len(request_id.encode("utf-8")) > 128
        ):
            raise ValueError("request_id must be a non-empty UTF-8 string of at most 128 bytes")

        record = evaluate_case(case, outcomes)
        if record["action_boundary"]["executed"] is not False:
            raise RuntimeError("Kernel violated the non-execution service boundary")
        return {
            "status": "ok",
            "service": "robustness-engine-agent",
            "service_version": SERVICE_VERSION,
            "engine_version": ENGINE_VERSION,
            "request_id": request_id,
            "decision_record": record,
        }

    async def health(self) -> dict[str, Any]:
        release = self._release_manifest_status()
        engine_match = ENGINE_VERSION == SERVICE_VERSION
        final_mode_ready = (
            self.config.release_mode != "final" or release["valid_for_final"]
        )
        healthy = engine_match and final_mode_ready
        return {
            "status": "ok" if healthy else "degraded",
            "agent": "robustness-engine-agent",
            "service_version": SERVICE_VERSION,
            "engine_version": ENGINE_VERSION,
            "release_mode": self.config.release_mode,
            "checks": {
                "engine_version_match": engine_match,
                "release_manifest": release,
                "decision_execution": "DISABLED",
                "network_dependency": "NONE",
            },
        }

    def describe(self) -> dict[str, Any]:
        release = self._release_manifest_status()
        return {
            "name": "robustness-engine-agent",
            "version": SERVICE_VERSION,
            "description": (
                "Evaluates governed robustness cases with viability, lineage, "
                "uncertainty, trajectory, dominance, and authority gates."
            ),
            "capabilities": [
                "evaluate_robustness_case",
                "classify_fail_closed_hold",
                "report_nonexecuting_action_boundary",
            ],
            "inputs": {
                "operation": "literal 'evaluate'",
                "case": "decision-case object",
                "outcomes": "outcome-bundle object",
                "request_id": "optional caller correlation identifier",
            },
            "outputs": {
                "decision_record": "hash-bound deterministic decision record",
                "execution": "always disabled",
            },
            "formal_state": FORMAL_STATE,
            "production_state": (
                FINAL_RELEASE_STATE
                if release["valid_for_final"]
                else "NOT_FINAL_NOT_PRODUCTION_DEPLOYED"
            ),
        }
