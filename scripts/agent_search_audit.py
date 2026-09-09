#!/usr/bin/env python3
"""Bounded, no-payment agent discovery audit. Search success is not buyer demand."""
import concurrent.futures
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = 'https://mcp.viridisconservation.com'
MERCHANT = 'https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant?payTo=0xfEf2e570b645EB720Ee6c589d27450810982f329'
ROOT = Path(__file__).resolve().parents[1]


def fetch(url, body=None):
    if url not in (BASE+'/x402/catalog', BASE+'/openapi.json', BASE+'/adopt', MERCHANT):
        raise ValueError('Unconfigured discovery destination')
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json', 'User-Agent':'Viridis-agent-search-audit/1.0',
                 'X-Viridis-Acquisition-Source':'internal'})
    with urllib.request.urlopen(request, timeout=4) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000: raise ValueError('Discovery response exceeds limit')
        return json.loads(raw)


def check_case(case):
    try:
        reply = fetch(BASE+'/adopt', {'objective':case['query']})
        selected = reply.get('route_decision', {}).get('selected') or {}
        actual = selected.get('route')
        safe = all(reply.get(k) is False for k in ('money_moved','payment_authorized','tool_executed','state_persisted'))
        expected = case['expected_route']
        matched = (actual == expected and (expected is not None or reply.get('decision') == 'NO_MATCH'))
        return {**case, 'actual_route':actual, 'decision':reply.get('decision'),
                'status':'pass' if matched and safe else 'fail', 'read_only_verified':safe}
    except Exception as exc:
        return {**case, 'status':'unavailable', 'error':type(exc).__name__}


def contracts(catalog, api):
    rows, seen = [], set()
    for row in catalog['routes']:
        key = row['agent']+'/'+row['tool']; issues=[]
        if key in seen: raise ValueError('Duplicate catalog route')
        seen.add(key)
        endpoint = BASE+'/x402/'+key
        if row.get('endpoint') != endpoint: issues.append('endpoint_mismatch')
        if not row.get('description'): issues.append('missing_description')
        if type(row.get('price_minor')) is not int or row['price_minor'] < 0: issues.append('invalid_price')
        elif str(row['price_minor']*10000) != row.get('amount_atomic_usdc'): issues.append('price_units_mismatch')
        value = row.get('value_decision', {})
        for field in ('job_to_be_done','expected_outcome','not_for'):
            if not value.get(field): issues.append('missing_'+field)
        operation = api.get('paths',{}).get('/x402/'+key,{}).get('post',{})
        schema = operation.get('requestBody',{}).get('content',{}).get('application/json',{}).get('schema')
        if not schema: issues.append('missing_input_schema')
        if '402' not in operation.get('responses',{}): issues.append('missing_quote_response')
        rows.append({'route':key,'issues':issues,'status':'pass' if not issues else 'fail'})
    return rows


def inventory(merchant, expected):
    resources = merchant['resources']; total = merchant['pagination']['total']
    if type(total) is not int or total != len(resources):
        return {'status':'unavailable','reason':'incomplete_merchant_pagination'}
    present = {r.get('resource') for r in resources}
    missing = sorted(key for key in expected if BASE+'/x402/'+key not in present)
    return {'status':'gap' if missing else 'pass','expected_count':len(expected),
            'indexed_count':len(expected)-len(missing),'missing_routes':missing,
            'indexing_is_ranking_or_demand':False}


def audit(cases):
    if not 1 <= len(cases) <= 30 or len({c['query'] for c in cases}) != len(cases):
        raise ValueError('Require 1–30 unique bounded test queries')
    if any(not isinstance(c['query'],str) or not 3 <= len(c['query']) <= 1000 for c in cases):
        raise ValueError('Invalid query')
    sources = {}
    def read(name, url):
        try: return name, fetch(url)
        except Exception as exc: return name, {'error':type(exc).__name__}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for name,data in pool.map(lambda pair:read(*pair), [('catalog',BASE+'/x402/catalog'),('api',BASE+'/openapi.json'),('merchant',MERCHANT)]):
            sources[name]=data
        results=list(pool.map(check_case,cases))
    try:
        contract = contracts(sources['catalog'], sources['api'])
        keys = {r['route'] for r in contract}
        tested = {c['expected_route'] for c in cases if c['expected_route']}
        coverage = {'untested_routes':sorted(keys-tested),'retired_expectations':sorted(tested-keys)}
    except (KeyError,TypeError,ValueError):
        contract=[]; keys=set(); coverage={'status':'unavailable'}
    try:
        indexed = inventory(sources['merchant'],keys) if keys else {'status':'unavailable'}
    except (KeyError,TypeError,ValueError): indexed={'status':'unavailable'}
    ok = (bool(contract) and all(r['status']=='pass' for r in contract+results) and
          not coverage.get('untested_routes') and not coverage.get('retired_expectations') and indexed['status']=='pass')
    report={'status':'ok' if ok else 'attention','classification':'bounded_agent_search_audit',
        'contracts':contract,'intent_cases':results,'coverage':coverage,'merchant_index':indexed,
        'summary':{'queries':len(results),'passed':sum(r['status']=='pass' for r in results),
                   'failed':sum(r['status']=='fail' for r in results),'unavailable':sum(r['status']=='unavailable' for r in results)},
        'boundaries':{'payments':0,'model_calls':0,'messages':0,'self_purchase_to_boost_rank':False,
                      'local_selection_is_external_search_rank':False,'search_visibility_is_revenue':False}}
    report['decision_sha256']=hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest()
    report['checked_at']=datetime.now(timezone.utc).isoformat()
    return report


if __name__ == '__main__':
    print(json.dumps(audit(json.loads((ROOT/'config/agent_search_cases.json').read_text())['cases']),indent=2))
