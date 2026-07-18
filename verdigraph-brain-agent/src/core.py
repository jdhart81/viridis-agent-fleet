"""
verdigraph-brain-agent — Core business logic.

VERIFIABLE COGNITION for the agent economy: compiles any agent file
(Verdigraph genome, Claude project export, OpenAI Assistant config, raw
prompt list) into a deterministic, content-addressed BRAIN — a cognitive
graph with a `brain_id` you can pin in git, cite in an audit, commit via
the fleet notary, or bind to a fleet DID. The certification layer the
rest of the trust stack was missing: identity says WHO an agent is,
receipts say WHAT it did, bonds say what happens IF it fails — this says
WHAT IT IS MADE OF.

Vendored engine: src/vg/brain.py (verdigraph-neurogenesis, stdlib-only,
DOI 10.5281/zenodo.20400274). The fleet mount wraps it; the engine is
canonical in its own repo.

Fleet-standard interface: async process(), async health(), sync describe().
process() dispatches on "action" and NEVER raises on bad input.

--- INVARIANTS (spec-invariance contract) ---
VB1 DETERMINISM: identical input bytes + format always produce identical
    brain_id, content_hash, and graph structure. No randomness, no
    timestamps in the hashed material, no network, no LLM in the serving
    path.
VB2 Every successful build carries the FULL invariant report (9 firing
    invariants + advisory), honestly: failed checks are reported as
    failed, never suppressed — a brain that fails invariants still
    returns ok with passed=false detail (the report IS the product).
VB3 verify recomputes from the submitted content and compares against
    the claimed identifiers — a mismatch is reported, never silently
    accepted (the certification is machine-checkable, A6/N-series
    idiom).
VB4 Unknown/undetectable formats return a structured error naming the
    supported formats (self-teaching, FT9/PB9 doctrine).
VB5 Every build result carries provenance: extractor id, engine
    version, input_bytes length, input_sha256.
VB6 process() never raises on bad input — structured error envelopes
    always (fleet C1 contract).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from src.vg.brain import (detect_format, extract, report_to_dict, to_dict,
                          verify_brain)

logger = logging.getLogger(__name__)

ENGINE = "verdigraph-neurogenesis (vendored brain.py)"
SUPPORTED_FORMATS = ("verdigraph_genome", "claude_project_export",
                     "openai_assistant", "prompt_list", "auto")


# --------------------------------------------------------------------------- #
# Fleet-standard base (self-contained; each agent runs in its own PYTHONPATH)
# --------------------------------------------------------------------------- #
@dataclass
class AgentConfig:
    name: str
    version: str = "0.1.0"
    debug: bool = False


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentCore:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.logger = logging.getLogger(config.name)

    async def health(self) -> dict:
        return {"status": "ok", "agent": self.config.name,
                "version": self.config.version, "timestamp": _utcnow(),
                "checks": {}}

    def _err(self, message: str, *, error_type: str = "Error",
             field: str = "", value: Any = None, constraint: str = "") -> dict:
        return {"status": "error", "error_type": error_type, "field": field,
                "value": value, "constraint": constraint, "message": message,
                "timestamp": _utcnow()}

    def _ok(self, data: Any = None) -> dict:
        return {"status": "ok", "data": data, "error": None,
                "timestamp": _utcnow()}


class ValidationError(ValueError):
    def __init__(self, message, field="", value=None, constraint=""):
        super().__init__(message)
        self.field, self.value, self.constraint = field, value, constraint


# --------------------------------------------------------------------------- #
class VerdigraphBrainCore(AgentCore):
    """Deterministic brain compilation + machine-checkable verification."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="verdigraph-brain-agent"))
        self._builds = 0
        self._verifications = 0

    async def process(self, input_data: Any) -> dict:
        try:
            if not isinstance(input_data, dict):                    # VB6/C1
                return self._err("input_data must be a dict",
                                 error_type="ValidationError",
                                 field="input_data",
                                 value=type(input_data).__name__,
                                 constraint="input_data must be a dict")
            action = input_data.get("action", "describe")
            handler = {"build": self._build, "verify": self._verify,
                       "detect_format": self._detect,
                       "describe": lambda _d: self._ok(self.describe()),
                       }.get(action)
            if handler is None:
                return self._err(
                    f"unknown action '{action}'",
                    error_type="ValidationError", field="action",
                    value=action,
                    constraint="one of: build, verify, detect_format, "
                               "describe")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError",
                             field=e.field, value=e.value,
                             constraint=e.constraint)
        except Exception as e:  # noqa: BLE001  (VB6: never raises)
            self.logger.exception("verdigraph-brain process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # ------------------------------------------------------------------ #
    @staticmethod
    def _content_bytes(data: dict) -> bytes:
        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValidationError(
                "content is required: the agent file to compile, as a "
                "string (genome JSON, Claude project export JSON, OpenAI "
                "assistant JSON, or newline-separated prompt list)",
                field="content", constraint="non-empty str")
        return content.encode("utf-8")

    def _resolve_format(self, data: dict, raw: bytes) -> str:
        fmt = str(data.get("format") or "auto").strip()
        if fmt not in SUPPORTED_FORMATS:                             # VB4
            raise ValidationError(
                f"unsupported format '{fmt}'",
                field="format", value=fmt,
                constraint=f"one of: {', '.join(SUPPORTED_FORMATS)}")
        if fmt == "auto":
            detected = detect_format(raw)
            if not detected:
                raise ValidationError(
                    "could not auto-detect the agent-file format; pass "
                    "format explicitly",
                    field="format", value="auto",
                    constraint=f"one of: {', '.join(SUPPORTED_FORMATS[:-1])}")
            fmt = detected
        return fmt

    def _build(self, data: dict) -> dict:
        raw = self._content_bytes(data)
        fmt = self._resolve_format(data, raw)
        brain = extract(fmt, raw)                                    # VB1
        report = report_to_dict(verify_brain(brain))                 # VB2
        self._builds += 1
        result = {
            "brain_id": brain.brain_id,
            "brain_uri": brain.brain_uri,
            "content_hash": brain.content_hash,
            "node_count": len(brain.nodes),
            "edge_count": len(brain.edges),
            "invariant_report": report,
            "provenance": {                                          # VB5
                "engine": ENGINE,
                "extractor": brain.provenance.extractor.id
                if hasattr(brain.provenance, "extractor")
                and hasattr(brain.provenance.extractor, "id")
                else fmt,
                "format": fmt,
                "input_bytes": len(raw),
                "input_sha256": hashlib.sha256(raw).hexdigest(),
            },
            "next_steps": {                                          # PB9 idiom
                "notarize": ("commit content_hash via the fleet notary "
                             "(/notary/mcp create_commitment) for a "
                             "tamper-evident cognition receipt"),
                "identity": ("bind brain_id to your fleet DID "
                             "(/identity/mcp) — constitutional identity"),
                "full_document": "pass include_document=true to get the "
                                 "complete brain graph",
            },
        }
        if data.get("include_document") is True:
            result["document"] = to_dict(brain)
        return self._ok(result)

    def _verify(self, data: dict) -> dict:
        """VB3: recompute from content, compare against claimed ids."""
        raw = self._content_bytes(data)
        fmt = self._resolve_format(data, raw)
        brain = extract(fmt, raw)
        report = report_to_dict(verify_brain(brain))
        claimed_id = data.get("brain_id")
        claimed_hash = data.get("content_hash")
        matches = {
            "brain_id": (claimed_id == brain.brain_id
                         if claimed_id is not None else None),
            "content_hash": (claimed_hash == brain.content_hash
                             if claimed_hash is not None else None),
        }
        self._verifications += 1
        valid = all(v for v in matches.values() if v is not None) \
            and any(v is not None for v in matches.values())
        return self._ok({
            "valid": bool(valid),
            "recomputed": {"brain_id": brain.brain_id,
                           "content_hash": brain.content_hash},
            "claimed": {"brain_id": claimed_id,
                        "content_hash": claimed_hash},
            "matches": matches,
            "invariant_report": report,
            "note": ("valid=true iff every claimed identifier matches the "
                     "deterministic recomputation from the submitted bytes "
                     "(VB3); pass brain_id and/or content_hash to verify")})

    def _detect(self, data: dict) -> dict:
        raw = self._content_bytes(data)
        detected = detect_format(raw)
        return self._ok({
            "format": detected,
            "confident": detected is not None,
            "supported_formats": list(SUPPORTED_FORMATS[:-1]),
            "note": None if detected else
            "no format matched — pass format explicitly on build"})

    # ------------------------------------------------------------------ #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {"builds": self._builds,
                       "verifications": self._verifications}
        return h

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": ("Deterministic, content-addressed brain "
                            "compilation for agent files — verifiable "
                            "cognition (brain_id) with a machine-checkable "
                            "invariant report."),
            "capabilities": ["build", "verify", "detect_format", "describe"],
            "inputs": {"action": "str", "content": "str", "format": "str",
                       "brain_id": "str?", "content_hash": "str?",
                       "include_document": "bool?"},
            "outputs": {"brain_id": "str", "content_hash": "str",
                        "invariant_report": "dict", "provenance": "dict"},
        }


def build(config: Optional[AgentConfig] = None) -> VerdigraphBrainCore:
    return VerdigraphBrainCore(config)
