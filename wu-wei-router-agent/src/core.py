"""Deterministic, caller-evidence-based workload planning. No provider execution."""
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
    KNOWN_ACTIONS=frozenset({'plan_workload'})
    READ_ACTIONS=frozenset()

    def _paid_preflight(self,payload):
        if os.environ.get('WU_WEI_FLEET_ENABLED')!='1':
            return {'status':'error','error_type':'ServiceUnavailable','message':'Wu Wei workload planning is disabled'}
        try: validate(payload)
        except (ValueError,TypeError,KeyError) as e:
            return {'status':'error','error_type':'ValidationError','message':str(e)}
        return None

    async def process(self,payload):
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
        return {'name':'wu-wei-router-agent','version':'0.1.0','price_minor':100,'capabilities':['bounded-workload-routing-plan'],
                'claim_boundary':BOUNDARY,'enabled':os.environ.get('WU_WEI_FLEET_ENABLED')=='1'}

    def health(self):
        return {'status':'ok','version':'0.1.0','enabled':os.environ.get('WU_WEI_FLEET_ENABLED')=='1'}
