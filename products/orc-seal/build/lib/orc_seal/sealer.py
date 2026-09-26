"""orc-seal: attach an Outcome Receipt (ORC v0.1) to every MCP tool result.

Any MCP server becomes a receipt issuer without code changes. Each successful
`tools/call` result gets a receipt under
`result._meta["com.viridisconservation/orc"]`; a stranger can check it at L1
(INTACT) offline, and at L2 (ISSUED) when the seal was registered.

--- INVARIANTS ---
M1  Result preservation: sealing never changes the tool's result. It only adds
    one key under `_meta` (JSON-RPC mode) or wraps it in an envelope that the
    caller explicitly opted into (decorator mode).
M2  Every receipt produced here verifies at L1 with the reference verifier.
M3  Privacy: tool arguments never appear in a receipt (only `args_sha256`),
    and the registry client sends only commitment, digest, salt, profile,
    subject and issuer. The output and the arguments never leave the process.
M4  Fail-open: a registry, network or sealing failure never fails or blocks
    the tool call beyond the registry timeout. `issuer_proof` is attached only
    after a 2xx reply that echoes the same commitment and digest.
M5  Deterministic normalization: floats become shortest round-trip decimal
    strings, non-finite floats become "NaN"/"Infinity"/"-Infinity", tuples
    become lists, bytes become {"bytes_sha256": ...}, non-string keys become
    strings. normalize(normalize(x)) == normalize(x).
M6  Only successful results are sealed: JSON-RPC errors and results with
    isError=true pass through unchanged. Receipts are for delivered outcomes.
M7  Oversized results (canonical output > MAX_OUTPUT_BYTES) are not sealed;
    the result passes through with `_meta[...] = {"skipped": "too_large"}`.
"""
from __future__ import annotations

import functools
import hashlib
import inspect
import json
import math
import urllib.error
import urllib.request
from copy import deepcopy
from typing import Any, Callable, Optional

from . import orc

META_KEY = "com.viridisconservation/orc"
MAX_OUTPUT_BYTES = 262_144
DEFAULT_REGISTRY = "https://mcp.viridisconservation.com"


def normalize(value: Any) -> Any:                                        # M5
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return repr(value)
    if isinstance(value, dict):
        return {str(k): normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return {"bytes_sha256": hashlib.sha256(bytes(value)).hexdigest()}
    return str(value)


def args_digest(args: Any) -> str:
    return orc.sha256_hex(orc.canonical(normalize(args if args is not None else {})))


class RegistryClient:
    """POST {base}/orc/v0/register. Sends no output and no arguments (M3)."""

    def __init__(self, base_url: str = DEFAULT_REGISTRY, api_key: str = "",
                 timeout: float = 3.0,
                 opener: Optional[Callable[..., Any]] = None):
        self.base = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._open = opener or urllib.request.urlopen
        self.last_error: Optional[str] = None

    @staticmethod
    def payload(receipt: dict) -> dict:
        return {"commitment": receipt["commitment"]["value"],
                "salt": receipt["commitment"]["salt"],
                "digest": receipt["digest"]["value"],
                "profile": receipt["profile"],
                "issuer": receipt["issuer"],
                "subject": {"agent": str(receipt["subject"].get("agent", "")),
                            "tool": str(receipt["subject"].get("tool", ""))},
                "issued_at": receipt["issued_at"]}

    def register(self, receipt: dict) -> Optional[dict]:
        """Return issuer_proof on success, else None (never raises; M4)."""
        self.last_error = None
        try:
            body = json.dumps(self.payload(receipt)).encode()
            req = urllib.request.Request(
                self.base + "/orc/v0/register", data=body, method="POST",
                headers={"content-type": "application/json",
                         "authorization": "Bearer " + self.api_key,
                         "user-agent": "orc-seal/0.1"})
            with self._open(req, timeout=self.timeout) as resp:
                status = getattr(resp, "status", 200)
                data = json.loads(resp.read().decode() or "{}")
            if not (200 <= status < 300):
                self.last_error = f"http {status}"
                return None
            if (data.get("commitment") != receipt["commitment"]["value"]
                    or data.get("digest") != receipt["digest"]["value"]):
                self.last_error = "registry echo mismatch"
                return None
            proof = data.get("issuer_proof") or {}
            if proof.get("method") != "registry" or not str(proof.get("url", "")).startswith("http"):
                self.last_error = "registry returned no proof url"
                return None
            return {"method": "registry", "url": proof["url"]}
        except urllib.error.HTTPError as exc:
            self.last_error = f"http {exc.code}"
        except Exception as exc:  # network, JSON, anything: fail open
            self.last_error = type(exc).__name__
        return None


class Sealer:
    def __init__(self, issuer: dict, *, agent: str = "",
                 registry: Optional[RegistryClient] = None,
                 profile: str = "generic", verify_base: Optional[str] = None):
        if not isinstance(issuer, dict) or not issuer.get("id"):
            raise ValueError("issuer must be a dict with an 'id' (e.g. did:web:example.com)")
        self.issuer = {"id": str(issuer["id"]), "name": str(issuer.get("name", issuer["id"]))}
        self.agent = agent
        self.registry = registry
        self.profile = profile
        self.verify_base = (verify_base or (registry.base if registry else DEFAULT_REGISTRY)).rstrip("/")

    def seal(self, tool: str, args: Any, result: Any,
             bindings: Optional[dict] = None) -> Optional[dict]:
        """Return a receipt, or None if the result is too large (M7)."""
        output = {"tool": str(tool), "args_sha256": args_digest(args),
                  "result": normalize(result)}
        if len(orc.canonical(output)) > MAX_OUTPUT_BYTES:
            return None
        receipt = orc.seal(output, issuer=self.issuer,
                           subject={"agent": self.agent, "tool": str(tool)},
                           profile=self.profile, bindings=bindings)
        c = receipt["commitment"]["value"]
        receipt["verify"] = {"page": f"{self.verify_base}/verify?c={c}"}
        if self.registry is not None:
            proof = self.registry.register(receipt)
            if proof:
                receipt["issuer_proof"] = proof
        return receipt

    # -- JSON-RPC (MCP wire) mode -------------------------------------------
    def seal_tools_call(self, request: dict, response: dict) -> dict:
        """Return `response` with a receipt in result._meta (M1, M6, M7)."""
        try:
            if request.get("method") != "tools/call" or "result" not in response:
                return response
            result = response["result"]
            if not isinstance(result, dict) or result.get("isError"):
                return response
            params = request.get("params") or {}
            sealed_part = {k: v for k, v in result.items() if k != "_meta"}
            receipt = self.seal(params.get("name", ""), params.get("arguments"), sealed_part)
            out = dict(response)
            new_result = dict(result)
            meta = dict(result.get("_meta") or {})
            meta[META_KEY] = receipt if receipt is not None else {"skipped": "too_large"}
            new_result["_meta"] = meta
            out["result"] = new_result
            return out
        except Exception:
            return response                                               # M4


def sealed(sealer: Sealer, tool: Optional[str] = None, key: str = "orc"):
    """Decorator for plain Python tools: returns {"result": r, key: receipt}.

    Opt-in envelope (M1). Works for sync and async functions.
    """
    def wrap(fn):
        name = tool or fn.__name__

        def envelope(result, args):
            try:
                receipt = sealer.seal(name, args, result)
            except Exception:
                receipt = None
            return {"result": result, key: receipt}

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def aw(*a, **kw):
                r = await fn(*a, **kw)
                return envelope(r, {"args": list(a), "kwargs": kw})
            return aw

        @functools.wraps(fn)
        def w(*a, **kw):
            r = fn(*a, **kw)
            return envelope(r, {"args": list(a), "kwargs": kw})
        return w
    return wrap


def verify(receipt: dict, *, registry_lookup: Optional[Callable[[str], Optional[dict]]] = None) -> dict:
    """L1 always; L2 if `registry_lookup(url) -> record` confirms the seal."""
    def issuer_ok(r: dict) -> bool:
        proof = r.get("issuer_proof") or {}
        if proof.get("method") != "registry" or registry_lookup is None:
            return False
        rec = registry_lookup(proof.get("url", "")) or {}
        return (rec.get("commitment") == r["commitment"]["value"]
                and rec.get("digest") == r["digest"]["value"])
    has_proof = bool(receipt.get("issuer_proof")) and registry_lookup is not None
    return orc.verify(deepcopy(receipt), issuer_resolver=issuer_ok if has_proof else None)
