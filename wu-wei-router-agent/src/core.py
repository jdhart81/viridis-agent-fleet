"""Deterministic, caller-evidence-based workload planning. No provider execution."""
import contextlib
import contextvars
import copy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import hashlib
import json
import math
import os
import re

BOUNDARY = ('Planning estimates from caller-supplied evaluation and price data; not independently verified savings, '
            'a quality guarantee, energy measurement, or autonomous execution. Wilson bounds assume representative independent trials.')
PROFILE_FIELDS = {'id', 'task_class', 'cost_microusd', 'p95_latency_ms', 'successes', 'trials', 'evidence_age_seconds', 'local', 'approved'}
TASK_FIELDS = {'id', 'task_class', 'count', 'baseline_profile', 'min_success_bps', 'max_p95_latency_ms', 'requires_local'}
ID = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$')
FEE = 1000000


def lower_bound(successes, trials):
    z = 1.959963984540054
    p = successes / trials
    return (p + z*z/(2*trials) - z*math.sqrt(p*(1-p)/trials + z*z/(4*trials*trials))) / (1+z*z/trials)


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != {'action','profiles','tasks'} or payload['action'] != 'plan_workload':
        raise ValueError('Supply exactly profiles and tasks for plan_workload')
    if not isinstance(payload['profiles'], list) or not 1 <= len(payload['profiles']) <= 20:
        raise ValueError('Supply 1 to 20 profiles')
    if not isinstance(payload['tasks'], list) or not 1 <= len(payload['tasks']) <= 50:
        raise ValueError('Supply 1 to 50 workload groups')
    def integer(row,key,lo,hi):
        if type(row[key]) is not int or not lo <= row[key] <= hi: raise ValueError(f'{key} must be an integer in [{lo},{hi}]')
    for rows,fields in [(payload['profiles'],PROFILE_FIELDS),(payload['tasks'],TASK_FIELDS)]:
        ids=set()
        for row in rows:
            if not isinstance(row,dict) or set(row)!=fields: raise ValueError('Fields must match the published schema exactly')
            for key in ['id','task_class']:
                if not isinstance(row[key],str) or not ID.fullmatch(row[key]): raise ValueError('Invalid identifier')
            if row['id'] in ids: raise ValueError('Duplicate identifier')
            ids.add(row['id'])
    for p in payload['profiles']:
        integer(p,'cost_microusd',0,1000000000);integer(p,'p95_latency_ms',1,3600000)
        integer(p,'trials',30,1000000);integer(p,'successes',0,p['trials'])
        integer(p,'evidence_age_seconds',0,604800)
        if type(p['local']) is not bool or type(p['approved']) is not bool: raise ValueError('local and approved must be booleans')
    by_id={p['id']:p for p in payload['profiles']}
    for t in payload['tasks']:
        integer(t,'count',1,1000000);integer(t,'min_success_bps',1,9999);integer(t,'max_p95_latency_ms',1,3600000)
        if type(t['requires_local']) is not bool: raise ValueError('requires_local must be boolean')
        if not isinstance(t['baseline_profile'],str) or t['baseline_profile'] not in by_id: raise ValueError('Unknown baseline profile')
        if not eligible(by_id[t['baseline_profile']],t): raise ValueError('Baseline must meet the same eligibility constraints; use representative evaluation data')
    return payload


def eligible(p,t):
    return (p['approved'] and p['task_class']==t['task_class'] and (not t['requires_local'] or p['local'])
            and p['p95_latency_ms']<=t['max_p95_latency_ms']
            and lower_bound(p['successes'],p['trials']) >= t['min_success_bps']/10000)


class WuWeiRouterCore:
    @property
    def KNOWN_ACTIONS(self):
        return frozenset({"plan_workload"}) | V2_TOOLS if self.v2_enabled else frozenset({"plan_workload"})

    @property
    def READ_ACTIONS(self):
        return V2_READ_ACTIONS if self.v2_enabled else frozenset()

    def _paid_preflight(self,payload):
        if os.environ.get('WU_WEI_FLEET_ENABLED')!='1':
            return {'status':'error','error_type':'ServiceUnavailable','message':'Wu Wei workload planning is disabled'}
        if self.v2_enabled and isinstance(payload, dict) and payload.get("action") != "plan_workload":
            try:
                self._validate_v2(payload)
            except (ValueError, TypeError, KeyError, InvalidOperation) as e:
                return {"status": "error", "error_type": "ValidationError", "message": str(e)}
            return None
        try: validate(payload)
        except (ValueError,TypeError,KeyError) as e:
            return {'status':'error','error_type':'ValidationError','message':str(e)}
        return None

    async def _plan_workload(self,payload):
        error=self._paid_preflight(payload)
        if error: return error
        profiles=payload['profiles'];by_id={p['id']:p for p in profiles};rows=[];baseline=0;planned=0
        for t in payload['tasks']:
            candidates=[p for p in profiles if eligible(p,t)]
            best=min(candidates,key=lambda p:(p['cost_microusd'],p['p95_latency_ms'],p['id']))
            before=by_id[t['baseline_profile']]['cost_microusd']*t['count'];after=best['cost_microusd']*t['count']
            baseline+=before;planned+=after
            rows.append({'task_id':t['id'],'profile_id':best['id'],'count':t['count'],
                         'eligible_alternatives':sorted(p['id'] for p in candidates),
                         'success_lower_95_bound':lower_bound(best['successes'],best['trials']),
                         'baseline_cost_microusd':before,'planned_cost_microusd':after,
                         'reason':'Lowest declared cost among approved, task-matched profiles meeting conservative evaluation, locality and latency constraints'})
        gross=baseline-planned
        doc={'status':'ok','service':'wu-wei-router','version':'0.1.0','decision':'SHADOW_TRIAL_RECOMMENDED' if gross>FEE else 'NO_NET_SAVINGS_AT_THIS_VOLUME',
             'routes':rows,'economics':{'currency':'USD','unit':'microdollars','baseline_cost':baseline,'planned_cost':planned,
             'service_fee':FEE,'modeled_gross_savings':gross,'modeled_net_savings_after_fee':gross-FEE,
             'excluded_costs':['buyer integration','retries not included in supplied costs','verification overhead','payment network fees'],
             'basis':'Caller-supplied total cost per task, volume and evaluation results; no bill reconciliation'},
             'execution_authorized':False,'policy_learning_enabled':False,'energy_savings_measured':False,
             'input_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
             'claim_boundary':BOUNDARY,
             'acceptance_checks':['Replay representative held-out tasks against baseline','Include failures, retries and router overhead in cost per successful task','Confirm agreed quality and latency before switching traffic']}
        doc['report_sha256']=hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return doc

    def describe(self):
        if self.v2_enabled:
            return {**self._legacy_describe(), "policy_version": POLICY,
                    "tools": sorted(V2_TOOLS), "eligibility": "wilson-lower-bound",
                    "execution_authorized": False, "energy_savings_measured": False}
        return self._legacy_describe()

    def _legacy_describe(self):
        return {'name':'wu-wei-router-agent','version':'0.1.0','price_minor':100,'capabilities':['bounded-workload-routing-plan'],
                'claim_boundary':BOUNDARY,'enabled':os.environ.get('WU_WEI_FLEET_ENABLED')=='1'}

    def health(self):
        if self.v2_enabled:
            return {**self._legacy_health(), "policy_version": POLICY}
        return self._legacy_health()

    def _legacy_health(self):
        return {'status':'ok','version':'0.1.0','enabled':os.environ.get('WU_WEI_FLEET_ENABLED')=='1'}



    @property
    def v2_enabled(self):
        return os.environ.get("WU_WEI_V2_ENABLED") == "1"

    @contextlib.contextmanager
    def admitted_request(self):
        """Host-only admission hook. Billing/transport wiring stays outside OSS.

        Never exposed as an MCP tool or accepted from a request payload.
        The hosted gate enters this context only after admitting a call.
        """
        context = self._admission_context()
        token = context.set(True)
        try:
            yield
        finally:
            context.reset(token)

    def _admission_context(self):
        # A per-core ContextVar prevents cross-core or cross-task authorization.
        # Not persisted; rebuild lazily after restores.
        if not hasattr(self, "_wu_wei_admission"):
            self._wu_wei_admission = contextvars.ContextVar("wu_wei_admission", default=False)
        return self._wu_wei_admission

    def _router_state(self):
        return getattr(self, "_wu_wei_state", {"profiles": {}, "events": [], "outcomes": [], "seq": 0})

    def _validate_v2(self, payload):
        action = payload.get("action")
        if action not in V2_TOOLS:
            raise ValueError("Unknown Wu Wei action")
        if action in V2_READ_ACTIONS:
            _strict_keys(payload, {"action"})
            return None
        if action == "register_compute_profile":
            _strict_keys(payload, {"action", "profile"})
            profile = _normalized_profile(payload["profile"])
            if len(self._router_state()["profiles"]) >= 20 and profile["id"] not in self._router_state()["profiles"]:
                raise ValueError("Supply at most 20 registered profiles")
            return profile
        if action == "route_task":
            _strict_keys(payload, {"action", "task"}, {"profiles"})
            if "profiles" in payload:
                if not isinstance(payload["profiles"], list):
                    raise ValueError("profiles must be a list")
                profiles = [_normalized_profile(p) for p in payload["profiles"]]
            else:
                profiles = list(copy.deepcopy(self._router_state()["profiles"]).values())
            validate({"action": "plan_workload", "profiles": [{k: p[k] for k in PROFILE_FIELDS} for p in profiles],
                      "tasks": [payload["task"]]})
            if len(self._router_state()["events"]) >= MAX_EVENTS:
                raise ValueError("Route audit-event capacity reached; export state before further routing")
            return profiles, copy.deepcopy(payload["task"])
        if action == "record_route_outcome":
            _strict_keys(payload, {"action", "decision_id", "successes", "trials"}, {"duration_ms", "cost_microusd"})
            _integer(payload["trials"], 1, 1000000, "trials")
            _integer(payload["successes"], 0, payload["trials"], "successes")
            for key in ("duration_ms", "cost_microusd"):
                if key in payload:
                    _integer(payload[key], 0, 1000000000000000, key)
            event = next((e for e in self._router_state()["events"] if e["decision_id"] == payload["decision_id"]), None)
            if event is None:
                raise ValueError("Unknown decision_id")
            if any(o["decision_id"] == payload["decision_id"] for o in self._router_state()["outcomes"]):
                raise ValueError("An outcome is already recorded for this decision_id")
            return copy.deepcopy(event)
        if action == "import_state":
            _strict_keys(payload, {"action", "state"})
            state = copy.deepcopy(payload["state"])
            _strict_keys(state, {"policy_version", "profiles", "events", "outcomes", "seq"})
            if state["policy_version"] != POLICY:
                raise ValueError("State policy mismatch")
            _integer(state["seq"], 0, 1000000000000000, "seq")
            if not isinstance(state["profiles"], dict) or len(state["profiles"]) > 20:
                raise ValueError("Invalid profile state")
            for key, profile in state["profiles"].items():
                if _source_profile(profile)["id"] != key:
                    raise ValueError("Profile state key mismatch")
            if not isinstance(state["events"], list) or len(state["events"]) > MAX_EVENTS:
                raise ValueError("Invalid audit-event state")
            if not isinstance(state["outcomes"], list) or len(state["outcomes"]) > len(state["events"]):
                raise ValueError("Invalid outcome state")
            ids = set()
            for event in state["events"]:
                _strict_keys(event, {"decision_id", "at", "decision_sha256", "decision_record"})
                if event["decision_id"] in ids or not isinstance(event["at"], str):
                    raise ValueError("Invalid audit-event identity")
                seq = event["decision_id"]
                if not isinstance(seq, str) or not re.fullmatch(r"wwr_[0-9]{16}", seq) or not 1 <= int(seq[4:]) <= state["seq"]:
                    raise ValueError("Invalid audit-event sequence")
                ids.add(seq)
                record = event["decision_record"]
                profiles = [_source_profile(p) for p in record["profiles"]]
                if len(record["tasks"]) != 1:
                    raise ValueError("Invalid decision task state")
                task = record["tasks"][0]
                validate({"action": "plan_workload", "profiles": [{k: p[k] for k in PROFILE_FIELDS} for p in profiles], "tasks": [task]})
                if _decision_record(profiles, task, legacy_cost_selection="selection_objective" not in record) != record or decision_digest(record) != event["decision_sha256"]:
                    raise ValueError("Decision state does not recompute")
            outcome_ids = set()
            for outcome in state["outcomes"]:
                _strict_keys(outcome, {"decision_id", "decision_sha256", "at", "successes", "trials", "source", "energy_savings_measured", "execution_authorized"}, {"duration_ms", "cost_microusd"})
                if outcome["decision_id"] not in ids or outcome["decision_id"] in outcome_ids:
                    raise ValueError("Invalid outcome decision identity")
                original = next(e for e in state["events"] if e["decision_id"] == outcome["decision_id"])
                if outcome["decision_sha256"] != original["decision_sha256"] or outcome["source"] != "caller-reported" or outcome["energy_savings_measured"] is not False or outcome["execution_authorized"] is not False or not isinstance(outcome["at"], str):
                    raise ValueError("Invalid outcome boundary")
                _integer(outcome["trials"], 1, 1000000, "trials")
                _integer(outcome["successes"], 0, outcome["trials"], "successes")
                for key in ("duration_ms", "cost_microusd"):
                    if key in outcome:
                        _integer(outcome[key], 0, 1000000000000000, key)
                outcome_ids.add(outcome["decision_id"])
            current = self._router_state()
            if state["seq"] < current["seq"] or state["events"][:len(current["events"])] != current["events"] or state["outcomes"][:len(current["outcomes"])] != current["outcomes"]:
                raise ValueError("Import cannot erase or rewrite existing routing audit history")
            canonical_decision(state)
            return {key: state[key] for key in ("profiles", "events", "outcomes", "seq")}

    def quote_route(self, payload, *, fee_microusd=1000000):
        """Host-only, read-only quote; absent from MCP actions and admission."""
        if not self.v2_enabled or os.environ.get("WU_WEI_FLEET_ENABLED") != "1":
            raise ValueError("Wu Wei v2 is disabled")
        if payload.get("action") != "route_task":
            raise ValueError("Quote requires route_task")
        _integer(fee_microusd, 0, 1000000, "fee_microusd")
        record = _decision_record(*self._validate_v2(payload))
        gross = record["baseline_cost_microusd"] - record["planned_cost_microusd"]
        return {"decision": record["decision"], "chosen_profile": record["chosen_profile"],
                "decision_sha256": decision_digest(record), "thermo": copy.deepcopy(record["thermo"]),
                "selection_objective": record["selection_objective"],
                "service_fee": fee_microusd, "modeled_gross_savings": gross,
                "modeled_net_savings_after_fee": gross - fee_microusd,
                "fee_exceeds_modeled_savings": gross < fee_microusd,
                "execution_authorized": False, "energy_savings_measured": False,
                "preview_only": True, "claim_boundary": BOUNDARY}

    async def process(self, payload):
        if not self.v2_enabled:
            return await self._plan_workload(payload)
        error = self._paid_preflight(payload)
        if error:
            return error
        action = payload["action"]
        if action == "describe_agent":
            return self.describe()
        if action == "export_state":
            return {"status": "ok", "state": {"policy_version": POLICY, **copy.deepcopy(self._router_state())}, "claim_boundary": BOUNDARY}
        if action == "compute_efficiency_report":
            state = self._router_state()
            return {"status": "ok", "policy_version": POLICY, "routing_events": len(state["events"]),
                    "caller_reported_outcomes": len(state["outcomes"]), "events": copy.deepcopy(state["events"]),
                    "outcomes": copy.deepcopy(state["outcomes"]), "execution_authorized": False,
                    "energy_savings_measured": False, "claim_boundary": BOUNDARY}
        if not self._admission_context().get():
            return {"status": "error", "error_type": "payment_required", "message": "Use the hosted admission gate"}
        if action == "plan_workload":
            return await self._plan_workload(payload)
        prepared = self._validate_v2(payload)
        state = copy.deepcopy(self._router_state())
        if action == "register_compute_profile":
            state["profiles"][prepared["id"]] = prepared
            result = {"status": "ok", "profile_id": prepared["id"], "registered_profiles": len(state["profiles"])}
        elif action == "route_task":
            record = _decision_record(*prepared)
            state["seq"] += 1
            event = {"decision_id": f"wwr_{state['seq']:016d}", "at": datetime.now(timezone.utc).isoformat(),
                     "decision_sha256": decision_digest(record), "decision_record": record}
            state["events"].append(event)
            gross = record["baseline_cost_microusd"] - record["planned_cost_microusd"]
            result = {"status": "ok", **copy.deepcopy(event), "decision": record["decision"],
                      "chosen_profile": record["chosen_profile"], "baseline_profile": record["baseline_profile"],
                      "thermo": copy.deepcopy(record["thermo"]), "eligibility": "wilson-lower-bound",
                      "reason": "baseline optimal / no change" if record["decision"] == "BASELINE_OPTIMAL_NO_CHANGE" else (
                          "Lowest modeled energy among Wilson-eligible routes within baseline cost; shadow trial recommended"
                          if record["selection_objective"] == "least_energy_within_baseline_cost" else
                          record["selection_objective"] + "; cheapest Wilson-eligible route; shadow trial recommended"),
                      "economics": {"currency": "USD", "unit": "microdollars", "service_fee": FEE,
                                    "modeled_gross_savings": gross, "modeled_net_savings_after_fee": gross - FEE},
                      "execution_authorized": False, "energy_savings_measured": False}
        elif action == "record_route_outcome":
            outcome = {key: copy.deepcopy(value) for key, value in payload.items() if key != "action"}
            outcome.update(decision_sha256=prepared["decision_sha256"], at=datetime.now(timezone.utc).isoformat(),
                           source="caller-reported", energy_savings_measured=False, execution_authorized=False)
            state["outcomes"].append(outcome)
            result = {"status": "ok", "outcome": copy.deepcopy(outcome)}
        else:
            state = prepared
            result = {"status": "ok", "policy_version": POLICY, "imported": True}
        self._wu_wei_state = state
        return {**result, "claim_boundary": BOUNDARY}


# Native Wilson routing extension. The original planner remains unchanged above.
POLICY = "wu-wei-router-v2"
V2_TOOLS = frozenset({"register_compute_profile", "route_task", "record_route_outcome",
                      "compute_efficiency_report", "describe_agent", "export_state", "import_state"})
V2_READ_ACTIONS = frozenset({"compute_efficiency_report", "describe_agent", "export_state"})
MAX_EVENTS = 1000


def canonical_decision(document):
    """Integer-only canonical JSON, matching ORC's sorted compact UTF-8 encoding."""
    def check(value):
        if value is None or type(value) in (str, int, bool):
            return
        if isinstance(value, list):
            for item in value:
                check(item)
            return
        if isinstance(value, dict) and all(type(k) is str for k in value):
            for item in value.values():
                check(item)
            return
        raise ValueError("Decision records accept only JSON integers, booleans, strings and null")
    check(document)
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def decision_digest(document):
    return hashlib.sha256(canonical_decision(document)).hexdigest()


def _strict_keys(document, required, optional=()):
    if not isinstance(document, dict) or not set(required) <= set(document) <= set(required) | set(optional):
        raise ValueError("Fields must match the published v2 schema exactly")


def _integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum},{maximum}]")


def _normalized_profile(profile):
    _strict_keys(profile, PROFILE_FIELDS, {"power_w"})
    result = {key: copy.deepcopy(profile[key]) for key in PROFILE_FIELDS}
    for key in ("id", "task_class"):
        if not isinstance(result[key], str) or not ID.fullmatch(result[key]):
            raise ValueError("Invalid identifier")
    for key, lo, hi in (("cost_microusd", 0, 1000000000), ("p95_latency_ms", 1, 3600000),
                        ("trials", 30, 1000000), ("evidence_age_seconds", 0, 604800)):
        _integer(result[key], lo, hi, key)
    _integer(result["successes"], 0, result["trials"], "successes")
    if type(result["approved"]) is not bool or type(result["local"]) is not bool:
        raise ValueError("local and approved must be booleans")
    if "power_w" in profile:
        value = profile["power_w"]
        if type(value) not in (int, float):
            raise ValueError("power_w must be a finite non-negative number")
        watts = Decimal(str(value))
        if not watts.is_finite() or not 0 <= watts <= 1000000:
            raise ValueError("power_w must be a finite number in [0,1000000]")
        result["power_uw"] = int((watts * 1000000).to_integral_value(rounding=ROUND_FLOOR))
    return result


def _source_profile(profile):
    """Portable integer state uses microwatts; API input uses declared watts."""
    _strict_keys(profile, PROFILE_FIELDS, {"power_uw"})
    result = _normalized_profile({k: v for k, v in profile.items() if k != "power_uw"})
    if "power_uw" in profile:
        _integer(profile["power_uw"], 0, 1000000000000, "power_uw")
        result["power_uw"] = profile["power_uw"]
    return result


def _energy(profile, task):
    if "power_uw" not in profile:
        return None
    return profile["power_uw"] * profile["p95_latency_ms"] * task["count"] // 1000


def _decision_record(profiles, task, *, legacy_cost_selection=False):
    # Use the unchanged Wilson predicate; quantization is for the record only.
    by_id = {p["id"]: p for p in profiles}
    candidates = [p for p in profiles if eligible(p, task)]
    baseline = by_id[task["baseline_profile"]]
    capped = [p for p in candidates if p["cost_microusd"] <= baseline["cost_microusd"]]
    assert any(p["id"] == baseline["id"] for p in capped), "Budget cap must contain eligible baseline"
    if legacy_cost_selection:
        pool, objective = candidates, None  # validate historical audit records without rewriting them
    elif any("power_uw" not in p for p in capped):
        pool, objective = capped, "cost_fallback_missing_power"
    else:
        pool, objective = capped, "least_energy_within_baseline_cost"
    if objective == "least_energy_within_baseline_cost":
        chosen = min(pool, key=lambda p: (_energy(p, task), p["cost_microusd"], p["p95_latency_ms"], p["id"]))
    else:
        chosen = min(pool, key=lambda p: (p["cost_microusd"], p["p95_latency_ms"], p["id"]))
    chosen_energy, baseline_energy = _energy(chosen, task), _energy(baseline, task)
    thermo = {"method": "modeled-wallclock-v1", "energy_savings_measured": False}
    if chosen_energy is None or baseline_energy is None:
        thermo["status"] = "insufficient data for savings"
    else:
        thermo.update(chosen_energy_uj=chosen_energy, baseline_energy_uj=baseline_energy,
                      modeled_savings_uj=max(0, baseline_energy - chosen_energy),
                      chosen_energy_exceeds_baseline=chosen_energy > baseline_energy)
    return {**({"selection_objective": objective} if objective is not None else {}),
            "policy_version": POLICY, "profiles": sorted(copy.deepcopy(profiles), key=lambda p: p["id"]),
            "tasks": [copy.deepcopy(task)], "eligibility": "wilson-lower-bound",
            "eligibility_outcomes": [{"profile_id": p["id"], "eligible": eligible(p, task),
                "success_lower_95_bps": math.floor(lower_bound(p["successes"], p["trials"]) * 10000)}
                for p in sorted(profiles, key=lambda p: p["id"])],
            "decision": "BASELINE_OPTIMAL_NO_CHANGE" if chosen["id"] == baseline["id"] else "SHADOW_TRIAL_RECOMMENDED",
            "chosen_profile": chosen["id"], "baseline_profile": baseline["id"], "task_count": task["count"],
            "baseline_cost_microusd": baseline["cost_microusd"] * task["count"],
            "planned_cost_microusd": chosen["cost_microusd"] * task["count"],
            "thermo": thermo, "execution_authorized": False, "energy_savings_measured": False}
