"""
agent-compute-ledger-agent — Core business logic.

A "compute is carbon" cost/energy ledger for agent work — the P-variable
accounting layer of the Intelligence Bound (dI/dt <= P*D / kB*T*ln2). Every
unit of agent cognition is physical work: this ledger records it, converts it
to energy (J) and carbon (gCO2e), benchmarks it against the Landauer limit,
and issues content-addressed attestations an auditor (or a CSRD/TNFD report,
via regulatory-radar-agent) can verify.

Physics constants: kB = 1.380649e-23 J/K; Landauer minimum per bit erased at
temperature T is kB*T*ln2 (~2.87e-21 J at 300 K). A declared workload whose
measured energy is BELOW its Landauer floor is physically impossible and is
rejected — thermodynamics as input validation.

Fleet-standard interface: async process(), async health(), sync describe().
process() dispatches on "action" and NEVER raises on bad input.

--- INVARIANTS (spec-invariance contract) ---
L1  The ledger is append-only and hash-chained: entries are immutable, each
    commits to the previous entry's hash, and verify_chain detects mutation.
L2  Energy accounting: energy_j = power_w * duration_s; power and duration
    must be positive and finite; recorded joules are always > 0.
L3  Carbon accounting is deterministic: carbon_g = (energy_j / 3.6e6) *
    grid_intensity_g_per_kwh. Same inputs -> same gCO2e, always.
L4  Landauer validation: with declared bit_ops, the floor is
    bit_ops * kB * T * ln2. energy_j < floor -> physically impossible ->
    rejected. Reported landauer_efficiency = floor / energy_j is in (0, 1].
L5  Attestations are content-addressed: attest() hashes the canonical entry
    JSON; verify_attestation recomputes and matches (tamper -> invalid).
L6  Aggregation is conservative: footprint totals equal the exact sum of the
    account's entries — energy, carbon, and cost never drift.
L7  Idempotency on entry_id: re-recording a seen entry_id returns the
    original entry and is never double-counted.
L8  Unknown account/entry -> error envelope, never a crash.

--- x402-C RECEIPT INVARIANTS (carbon_receipt; standard: docs/standards/X402C) ---
X1  carbon_receipt emits an x402c/0.1 `carbon` object whose g_co2e and
    energy_j are taken verbatim from the recorded entry (no re-derivation
    drift); method is "landauer-floor" iff the entry declared bit_ops, else
    "measured".
X2  C1 (physical floor) is guaranteed by construction: a landauer-floor
    receipt can only be emitted for an entry that already passed L4 at record
    time (energy_j >= bit_ops*kB*T*ln2), so landauer_efficiency is in (0,1].
X3  C2 (recomputable) is self-checked: the emitter refuses to produce a
    receipt whose g_co2e != (energy_j/3.6e6)*grid within a rounding epsilon.
X4  C3 (no detachment): attestation_hash binds the carbon object to the
    entry's hash-chain position (entry_hash); any party can recompute it.
X5  carbon_receipt is pure/read-only and never mutates the ledger; unknown
    entry_id -> error envelope.

--- INVENTORY DOMAIN INVARIANTS (separate from L1-L8) ---
I1  Inventory accounting is a separate namespace. Inventory mass never enters
    the physical-compute ledger or changes footprint() totals.
I2  mass_g is an exact, non-negative integer; floats and booleans are rejected.
I3  Every inventory commits to a SHA-256 content digest and factor-pack digest,
    plus the exact factor-pack version and canonical source-id set.
I4  Inventory records are append-only and hash-chained per agent; tampering is
    detected independently of the compute-work chain.
I5  inventory_id is globally idempotent only for an identical canonical
    integrity payload; conflicting reuse fails closed and is never counted.
I6  Unknown inventory/account and malformed lineage fail loud with an error
    envelope; the domain uses only built-in dict/list state for safe rollback.
"""

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KB = 1.380649e-23          # Boltzmann constant, J/K
LN2 = math.log(2)
J_PER_KWH = 3.6e6
DEFAULT_TEMP_K = 300.0
DEFAULT_GRID_G_PER_KWH = 400.0  # world-average-ish grid intensity default


# --------------------------------------------------------------------------- #
# Fleet-standard base (self-contained; each agent runs in its own PYTHONPATH)
# --------------------------------------------------------------------------- #
@dataclass
class AgentConfig:
    name: str
    version: str = "0.3.0"
    debug: bool = False


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentCore:
    """Minimal fleet-standard base. Subclasses override process()/describe()."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.logger = logging.getLogger(config.name)
        self.logger.setLevel(logging.DEBUG if config.debug else logging.INFO)

    async def process(self, input_data: dict) -> dict:
        raise NotImplementedError

    async def health(self) -> dict:
        return {
            "status": "ok",
            "agent": self.config.name,
            "version": self.config.version,
            "timestamp": _utcnow(),
            "checks": {},
        }

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "override me",
            "capabilities": [],
            "inputs": {},
            "outputs": {},
        }

    def _err(self, message: str, *, error_type: str = "Error",
             field: str = "", value: Any = None, constraint: str = "") -> dict:
        return {
            "status": "error",
            "error_type": error_type,
            "field": field,
            "value": value,
            "constraint": constraint,
            "message": message,
            "timestamp": _utcnow(),
        }

    def _ok(self, data: Any = None) -> dict:
        return {"status": "ok", "data": data, "error": None, "timestamp": _utcnow()}


class ValidationError(ValueError):
    def __init__(self, message, field="", value=None, constraint=""):
        super().__init__(message)
        self.field, self.value, self.constraint = field, value, constraint


# --------------------------------------------------------------------------- #
# Domain
# --------------------------------------------------------------------------- #
_GENESIS = "0" * 64


def _canonical(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"))


def _hash(payload: dict, prev: str) -> str:
    return hashlib.sha256((prev + _canonical(payload)).encode()).hexdigest()


def _pos_finite(data: dict, f: str) -> float:
    v = data.get(f)
    if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0 or not math.isfinite(v):
        raise ValidationError(f"'{f}' must be a positive finite number",
                              field=f, value=v, constraint="> 0, finite")
    return float(v)


def _sha256_hex(data: dict, field: str) -> str:
    """Return a bare lowercase SHA-256 digest or fail loud."""
    value = data.get(field)
    if not isinstance(value, str) or len(value) != 64 \
            or any(c not in "0123456789abcdef" for c in value):
        raise ValidationError(
            f"'{field}' must be a bare lowercase SHA-256 hex digest",
            field=field, value=value, constraint="64 lowercase hex characters")
    return value


class ComputeLedgerAgentCore(AgentCore):
    """Energy/carbon accounting for agent compute — the Intelligence-Bound P ledger."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="agent-compute-ledger-agent"))
        # account (agent_id) -> list of entries; entry_id -> (account, idx)
        self._ledgers: Dict[str, List[dict]] = {}
        self._entry_index: Dict[str, tuple] = {}
        # Separate inventory domain (I1). Built-ins only so an older image can
        # still unpickle a snapshot after rollback.
        self._inventories: Dict[str, List[dict]] = {}
        self._inventory_index: Dict[str, tuple] = {}

    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object", error_type="ValidationError",
                                 field="input", value=type(input_data).__name__, constraint="dict")
            action = input_data.get("action")
            handler = {
                "record_work": self._record_work,
                "footprint": self._footprint,
                "attest": self._attest,
                "verify_attestation": self._verify_attestation,
                "verify_chain": self._verify_chain,
                "list_entries": self._list_entries,
                "carbon_receipt": self._carbon_receipt,
                "record_inventory": self._record_inventory,
                "get_inventory": self._get_inventory,
                "list_inventories": self._list_inventories,
                "verify_inventory_chain": self._verify_inventory_chain,
            }.get(action)
            if handler is None:
                return self._err(f"unknown action '{action}'", error_type="ValidationError",
                                 field="action", value=action,
                                 constraint="one of: record_work, footprint, attest, "
                                            "verify_attestation, verify_chain, list_entries, "
                                            "carbon_receipt, "
                                            "record_inventory, get_inventory, list_inventories, "
                                            "verify_inventory_chain")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError", field=e.field,
                             value=e.value, constraint=e.constraint)
        except Exception as e:  # noqa: BLE001
            self.logger.exception("compute-ledger process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # ------------------------------------------------------------------ #
    def _ledger(self, data: dict) -> List[dict]:
        acct = data.get("agent_id")
        ledger = self._ledgers.get(acct)
        if ledger is None:  # L8
            raise ValidationError("unknown account", field="agent_id", value=acct,
                                  constraint="must exist (record work first)")
        return ledger

    def _record_work(self, data: dict) -> dict:
        acct = data.get("agent_id")
        if not acct or not isinstance(acct, str):
            raise ValidationError("missing 'agent_id'", field="agent_id",
                                  constraint="non-empty str")
        entry_id = data.get("entry_id")
        if not entry_id or not isinstance(entry_id, str):
            raise ValidationError("missing 'entry_id'", field="entry_id",
                                  constraint="non-empty str")
        if entry_id in self._entry_index:  # L7 idempotent
            a, i = self._entry_index[entry_id]
            return self._ok({**self._ledgers[a][i], "duplicate": True})

        power_w = _pos_finite(data, "power_w")          # L2
        duration_s = _pos_finite(data, "duration_s")    # L2
        energy_j = power_w * duration_s                 # L2

        temp_k = float(data.get("temperature_k", DEFAULT_TEMP_K))
        if temp_k <= 0 or not math.isfinite(temp_k):
            raise ValidationError("temperature_k must be positive", field="temperature_k",
                                  value=temp_k, constraint="> 0 K")
        grid = float(data.get("grid_intensity_g_per_kwh", DEFAULT_GRID_G_PER_KWH))
        if grid < 0 or not math.isfinite(grid):
            raise ValidationError("grid_intensity_g_per_kwh must be >= 0",
                                  field="grid_intensity_g_per_kwh", value=grid,
                                  constraint=">= 0, finite")

        landauer_floor_j = None
        landauer_efficiency = None
        bit_ops = data.get("bit_ops")
        if bit_ops is not None:
            if not isinstance(bit_ops, (int, float)) or isinstance(bit_ops, bool) \
                    or bit_ops <= 0 or not math.isfinite(bit_ops):
                raise ValidationError("bit_ops must be a positive finite number",
                                      field="bit_ops", value=bit_ops, constraint="> 0, finite")
            landauer_floor_j = float(bit_ops) * KB * temp_k * LN2
            if energy_j < landauer_floor_j:  # L4 physically impossible
                raise ValidationError(
                    "declared energy is below the Landauer floor for the declared "
                    "bit operations - physically impossible workload",
                    field="energy_j", value=energy_j,
                    constraint=f">= {landauer_floor_j:.3e} J (bit_ops * kB * T * ln2)")
            landauer_efficiency = landauer_floor_j / energy_j  # in (0, 1]

        carbon_g = (energy_j / J_PER_KWH) * grid  # L3
        cost_minor = None
        price = data.get("price_minor_per_kwh")
        if price is not None:
            if not isinstance(price, (int, float)) or isinstance(price, bool) or price < 0:
                raise ValidationError("price_minor_per_kwh must be >= 0",
                                      field="price_minor_per_kwh", value=price, constraint=">= 0")
            cost_minor = math.ceil((energy_j / J_PER_KWH) * float(price))

        ledger = self._ledgers.setdefault(acct, [])
        prev = ledger[-1]["entry_hash"] if ledger else _GENESIS
        body = {
            "entry_id": entry_id, "agent_id": acct,
            "task": data.get("task", ""),
            "power_w": power_w, "duration_s": duration_s, "energy_j": energy_j,
            "temperature_k": temp_k,
            "grid_intensity_g_per_kwh": grid, "carbon_g": carbon_g,
            "bit_ops": float(bit_ops) if bit_ops is not None else None,
            "landauer_floor_j": landauer_floor_j,
            "landauer_efficiency": landauer_efficiency,
            "cost_minor": cost_minor,
            "recorded_at": _utcnow(), "prev_hash": prev,
        }
        entry = {**body, "entry_hash": _hash(body, prev)}  # L1/L5
        ledger.append(entry)
        self._entry_index[entry_id] = (acct, len(ledger) - 1)
        return self._ok({**entry, "duplicate": False})

    def _footprint(self, data: dict) -> dict:  # L6 conservative aggregation
        ledger = self._ledger(data)
        energy = sum(e["energy_j"] for e in ledger)
        carbon = sum(e["carbon_g"] for e in ledger)
        cost = sum(e["cost_minor"] for e in ledger if e["cost_minor"] is not None)
        effs = [e["landauer_efficiency"] for e in ledger
                if e["landauer_efficiency"] is not None]
        return self._ok({
            "agent_id": data.get("agent_id"), "entry_count": len(ledger),
            "total_energy_j": energy, "total_energy_kwh": energy / J_PER_KWH,
            "total_carbon_g": carbon, "total_cost_minor": cost,
            "mean_landauer_efficiency": (sum(effs) / len(effs)) if effs else None,
        })

    def _attest(self, data: dict) -> dict:  # L5
        entry_id = data.get("entry_id")
        loc = self._entry_index.get(entry_id)
        if loc is None:  # L8
            raise ValidationError("unknown entry", field="entry_id", value=entry_id,
                                  constraint="must exist")
        entry = self._ledgers[loc[0]][loc[1]]
        att_hash = hashlib.sha256(_canonical(entry).encode()).hexdigest()
        return self._ok({
            "attestation": {
                "entry_id": entry_id, "agent_id": entry["agent_id"],
                "energy_j": entry["energy_j"], "carbon_g": entry["carbon_g"],
                "attestation_hash": att_hash, "attested_at": _utcnow(),
                "issuer": self.config.name,
            }
        })

    def _verify_attestation(self, data: dict) -> dict:  # L5
        att = data.get("attestation")
        if not isinstance(att, dict) or "entry_id" not in att or "attestation_hash" not in att:
            raise ValidationError("attestation must be a dict with entry_id + attestation_hash",
                                  field="attestation", value=att, constraint="dict")
        loc = self._entry_index.get(att["entry_id"])
        if loc is None:
            return self._ok({"valid": False, "reason": "unknown entry"})
        entry = self._ledgers[loc[0]][loc[1]]
        recomputed = hashlib.sha256(_canonical(entry).encode()).hexdigest()
        return self._ok({"valid": recomputed == att["attestation_hash"],
                         "entry_id": att["entry_id"]})

    def _verify_chain(self, data: dict) -> dict:  # L1
        ledger = self._ledger(data)
        prev = _GENESIS
        for i, e in enumerate(ledger):
            body = {k: v for k, v in e.items() if k != "entry_hash"}
            if e["prev_hash"] != prev or _hash(body, prev) != e["entry_hash"]:
                return self._ok({"agent_id": data.get("agent_id"), "valid": False,
                                 "broken_at_index": i})
            prev = e["entry_hash"]
        return self._ok({"agent_id": data.get("agent_id"), "valid": True,
                         "entry_count": len(ledger)})

    def _list_entries(self, data: dict) -> dict:
        ledger = self._ledger(data)
        return self._ok({"count": len(ledger), "entries": list(ledger)})

    def _carbon_receipt(self, data: dict) -> dict:  # X1-X5 (x402-C/0.1)
        """Emit an x402-C carbon receipt for a recorded work entry.

        This is what makes agent-compute-ledger the reference implementation
        of the x402-C standard (docs/standards/X402C_CARBON_RECEIPTS.md): the
        physically-grounded `carbon` object a machine-to-machine payment
        receipt can carry. Pure/read-only (L-series untouched).
        """
        entry_id = data.get("entry_id")
        loc = self._entry_index.get(entry_id)
        if loc is None:  # L8/X5
            raise ValidationError("unknown entry", field="entry_id",
                                  value=entry_id, constraint="must exist")
        entry = self._ledgers[loc[0]][loc[1]]

        has_bits = entry.get("bit_ops") is not None
        # X1: values come straight from the recorded entry — no re-derivation
        # drift. method is landauer-floor iff the workload declared bit_ops
        # (and thus passed the L4 physical-floor check at record time).
        carbon = {
            "version": "x402c/0.1",
            "g_co2e": round(entry["carbon_g"], 6),
            "energy_j": entry["energy_j"],
            "method": "landauer-floor" if has_bits else "measured",
            "method_ref": "doi:10.5281/zenodo.19317982",
            "grid_intensity_g_per_kwh": entry["grid_intensity_g_per_kwh"],
            "attestor": "viridis:compute-ledger",
            "entry_id": entry_id,
        }
        if has_bits:  # X2: C1 floor already enforced at record_work (L4)
            carbon["bit_ops"] = entry["bit_ops"]
            carbon["landauer_floor_j"] = entry["landauer_floor_j"]
            carbon["landauer_efficiency"] = entry["landauer_efficiency"]
        offset_ref = data.get("offset_ref")
        if offset_ref is not None:
            if not isinstance(offset_ref, str) or not offset_ref:
                raise ValidationError("offset_ref must be a non-empty string",
                                      field="offset_ref", value=offset_ref,
                                      constraint="resolvable retirement ref")
            carbon["offset_ref"] = offset_ref  # C4 pointer (verify externally)
        # X3 self-check: g_co2e must equal (energy_j/3.6e6)*grid (C2) within a
        # rounding epsilon — refuse to emit a receipt that fails its own spec.
        recomputed = (entry["energy_j"] / J_PER_KWH) * entry["grid_intensity_g_per_kwh"]
        if abs(recomputed - entry["carbon_g"]) > 1e-6:
            return self._err("carbon accounting inconsistent (C2)",
                             error_type="RuntimeError", field="carbon_g",
                             value=entry["carbon_g"], constraint=f"~{recomputed}")
        # X4/C3: bind the carbon object to the entry's hash-chain position so
        # it cannot be detached and reused; recomputable by any party.
        carbon["attestation_hash"] = hashlib.sha256(
            (_canonical(carbon) + entry["entry_hash"]).encode()).hexdigest()
        return self._ok({"carbon": carbon, "entry_hash": entry["entry_hash"],
                         "conformance": {"C1_landauer_floor": has_bits,
                                         "C2_recomputable": True,
                                         "C3_bound_to_entry": True}})

    # ------------------------------------------------------------------ #
    # Inventory domain (I1-I6) — deliberately separate from compute work.
    def _inventory_ledger(self, data: dict) -> List[dict]:
        acct = data.get("agent_id")
        ledger = self._inventories.get(acct)
        if ledger is None:  # I6
            raise ValidationError("unknown inventory account", field="agent_id",
                                  value=acct,
                                  constraint="must exist (record inventory first)")
        return ledger

    def _record_inventory(self, data: dict) -> dict:
        acct = data.get("agent_id")
        if not acct or not isinstance(acct, str):
            raise ValidationError("missing 'agent_id'", field="agent_id",
                                  constraint="non-empty str")
        inventory_id = data.get("inventory_id")
        if not inventory_id or not isinstance(inventory_id, str):
            raise ValidationError("missing 'inventory_id'", field="inventory_id",
                                  constraint="non-empty str")
        mass_g = data.get("mass_g")
        if not isinstance(mass_g, int) or isinstance(mass_g, bool) or mass_g < 0:
            raise ValidationError("'mass_g' must be a non-negative integer",
                                  field="mass_g", value=mass_g,
                                  constraint="integer >= 0")
        content_digest = _sha256_hex(data, "content_digest")
        factor_pack_digest = _sha256_hex(data, "factor_pack_digest")
        factor_pack_version = data.get("factor_pack_version")
        if not isinstance(factor_pack_version, str) or not factor_pack_version.strip():
            raise ValidationError("'factor_pack_version' must be a non-empty string",
                                  field="factor_pack_version",
                                  value=factor_pack_version,
                                  constraint="non-empty str")
        source_ids = data.get("source_ids", [])
        if not isinstance(source_ids, list) or any(
                not isinstance(source, str) or not source.strip()
                for source in source_ids):
            raise ValidationError("'source_ids' must be a list of non-empty strings",
                                  field="source_ids", value=source_ids,
                                  constraint="list[str]")
        canonical_sources = sorted(set(source.strip() for source in source_ids))
        factor_pack_version = factor_pack_version.strip()

        if inventory_id in self._inventory_index:  # I5 exact replay or conflict
            owner, index = self._inventory_index[inventory_id]
            existing = self._inventories[owner][index]
            submitted = {
                "agent_id": acct,
                "mass_g": mass_g,
                "content_digest": content_digest,
                "factor_pack_version": factor_pack_version,
                "factor_pack_digest": factor_pack_digest,
                "source_ids": canonical_sources,
            }
            conflicts = [field for field, value in submitted.items()
                         if existing.get(field) != value]
            if conflicts:
                return self._err(
                    f"inventory_id '{inventory_id}' already exists with conflicting "
                    f"integrity fields: {', '.join(conflicts)}",
                    error_type="ConflictError", field="inventory_id",
                    value=inventory_id,
                    constraint=("existing inventory_id requires identical agent_id, "
                                "mass_g, content_digest, factor_pack_version, "
                                "factor_pack_digest, and source_ids"))
            return self._ok({**existing, "duplicate": True})

        ledger = self._inventories.setdefault(acct, [])
        prev = ledger[-1]["inventory_hash"] if ledger else _GENESIS
        body = {
            "inventory_id": inventory_id,
            "agent_id": acct,
            "mass_g": mass_g,
            "content_digest": content_digest,
            "factor_pack_version": factor_pack_version,
            "factor_pack_digest": factor_pack_digest,
            "source_ids": canonical_sources,
            "recorded_at": _utcnow(),
            "prev_hash": prev,
        }
        entry = {**body, "inventory_hash": _hash(body, prev)}
        ledger.append(entry)
        self._inventory_index[inventory_id] = (acct, len(ledger) - 1)
        return self._ok({**entry, "duplicate": False})

    def _get_inventory(self, data: dict) -> dict:
        inventory_id = data.get("inventory_id")
        location = self._inventory_index.get(inventory_id)
        if location is None:  # I6
            raise ValidationError("unknown inventory", field="inventory_id",
                                  value=inventory_id, constraint="must exist")
        return self._ok(dict(self._inventories[location[0]][location[1]]))

    def _list_inventories(self, data: dict) -> dict:
        ledger = self._inventory_ledger(data)
        return self._ok({"agent_id": data.get("agent_id"),
                         "count": len(ledger), "inventories": list(ledger)})

    def _verify_inventory_chain(self, data: dict) -> dict:
        ledger = self._inventory_ledger(data)
        prev = _GENESIS
        for index, entry in enumerate(ledger):
            body = {k: v for k, v in entry.items() if k != "inventory_hash"}
            if entry.get("prev_hash") != prev \
                    or _hash(body, prev) != entry.get("inventory_hash"):
                return self._ok({"agent_id": data.get("agent_id"),
                                 "valid": False,
                                 "inventory_count": len(ledger),
                                 "broken_at_index": index})
            prev = entry["inventory_hash"]
        return self._ok({"agent_id": data.get("agent_id"), "valid": True,
                         "inventory_count": len(ledger)})

    # ------------------------------------------------------------------ #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {"accounts": len(self._ledgers),
                       "entries": sum(len(l) for l in self._ledgers.values()),
                       "inventory_accounts": len(self._inventories),
                       "inventories": sum(len(l) for l in self._inventories.values())}
        return h

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "Compute-is-carbon energy/carbon ledger for agent work "
                           "with Landauer-limit validation and verifiable attestations.",
            "capabilities": ["record_work", "footprint", "attest",
                             "verify_attestation", "verify_chain", "list_entries",
                             "carbon_receipt",
                             "record_inventory", "get_inventory", "list_inventories",
                             "verify_inventory_chain"],
            "inputs": {"action": "str", "agent_id": "str", "entry_id": "str",
                       "power_w": "number > 0", "duration_s": "number > 0",
                       "bit_ops": "number > 0 (optional)",
                       "temperature_k": "number > 0 (default 300)",
                       "grid_intensity_g_per_kwh": "number >= 0 (default 400)",
                       "price_minor_per_kwh": "number >= 0 (optional)",
                       "inventory_id": "str", "mass_g": "integer >= 0",
                       "content_digest": "sha256 hex",
                       "factor_pack_version": "str",
                       "factor_pack_digest": "sha256 hex",
                       "source_ids": "list[str]"},
            "outputs": {"status": "str (ok|error)", "data": "dict"},
            "a2a_role": "accounting",
        }


def build(config: Optional[AgentConfig] = None) -> ComputeLedgerAgentCore:
    return ComputeLedgerAgentCore(config)
