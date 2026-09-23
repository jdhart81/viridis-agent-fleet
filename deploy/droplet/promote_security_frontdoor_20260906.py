#!/usr/bin/env python3
"""Add the Security Preflight front door without changing existing services.

All backups and rehearsal files stay on the Security host. No customer
assessment or payment is performed. The original Caddyfile is preserved.
"""
import argparse, base64, hashlib, json, os, shutil, subprocess, time
from pathlib import Path
import urllib.request, urllib.error

ROOT = Path('/opt/viridis/releases/security-frontdoor-20260906')
LANDING = Path('/opt/viridis/landing')
CONFIG = Path('/opt/viridis/deploy/Caddyfile')
CADDY = 'deploy-caddy-1'
IMAGE = 'sha256:834468128c7696cec0ceea6172f7d692daf645ae51983ca76e39da54a97c570d'
NETWORK = 'deploy_viridis'
TRIAL = 'viridis-security-frontdoor-rehearsal'
SECURITY = 'https://mcp.viridis-security.com'
LOCAL = 'http://127.0.0.1:18409'
FIXTURE = {'agent_id':'release-rehearsal-only', 'manifest':{'endpoint':'https://example.invalid/mcp','auth':'bearer','tools':[{'name':'read_status','input_schema':{'type':'object','properties':{},'additionalProperties':False}}]},'policy':{'allowed_tools':['read_status']},'sample_inputs':['ordinary fixture']}


def run(*args, timeout=120):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        (ROOT/'last-command-error.log').write_text(p.stdout+p.stderr)
        raise RuntimeError('Command failed: '+args[0]+' '+args[1])
    return p.stdout.strip()


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(name, value): (ROOT/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def inspect(name=CADDY): return json.loads(run('docker','inspect',name))[0]


def request(base,path,payload=None,headers=None):
    h={'accept':'application/json, text/event-stream','content-type':'application/json','user-agent':'viridis-domain-verification/1.0','x-viridis-acquisition-source':'internal'}
    h.update(headers or {})
    req=urllib.request.Request(base+path,headers=h,data=json.dumps(payload).encode() if payload is not None else None)
    try:r=urllib.request.urlopen(req,timeout=25)
    except urllib.error.HTTPError as e:r=e
    with r:
        raw=r.read().decode()
        try:body=json.loads(raw)
        except ValueError:body=raw
        return r.code,dict(r.headers),body


def health():
    value={}
    for name in [CADDY,'deploy-injection-detector-1','viridis-security-web','viridis-security-worker-1','deploy-canon-scanner-1','deploy-maxwell-1','deploy-envelope-registry-1']:
        item=inspect(name)
        assert item['State']['Running']
        if 'Health' in item['State']:assert item['State']['Health']['Status']=='healthy',name
        value[name]={'image':item['Image'],'running':True,'health':item['State'].get('Health',{}).get('Status')}
    assert value[CADDY]['image']==IMAGE
    return value


def parse_rpc(body):
    if isinstance(body,str):
        data=[line[5:].strip() for line in body.splitlines() if line.startswith('data:')]
        assert data,'Missing MCP message'
        return json.loads(data[-1])
    return body


def mcp(base,path):
    status,headers,body=request(base,path,{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'viridis-domain-verification','version':'1.0'}}})
    assert status==200,(path,status)
    initialized=parse_rpc(body)
    assert 'result' in initialized,initialized
    h={'mcp-protocol-version':initialized['result']['protocolVersion']}
    sid=next((v for k,v in headers.items() if k.lower()=='mcp-session-id'),None)
    if sid:h['mcp-session-id']=sid
    status,_,_=request(base,path,{'jsonrpc':'2.0','method':'notifications/initialized'},h)
    assert status in (200,202,204)
    status,_,body=request(base,path,{'jsonrpc':'2.0','id':2,'method':'tools/list'},h)
    assert status==200
    listed=parse_rpc(body)
    tools=[t['name'] for t in listed['result']['tools']]
    assert tools
    return {'server':initialized['result']['serverInfo'],'tools':tools}


def base_check():
    manifest=json.loads((ROOT/'manifest.json').read_text())
    assert sha(CONFIG)==manifest['base_caddy_sha256'],'Caddyfile drifted'
    for rel,digest in manifest['base_landing'].items():assert sha(LANDING/rel)==digest,rel
    assert health()==json.loads((ROOT/'prepared.json').read_text())['services'] if (ROOT/'prepared.json').exists() else True
    return manifest


def prepare():
    manifest=base_check()
    services=health()
    candidate=ROOT/'Caddyfile.candidate'
    assert sha(candidate)==manifest['candidate_caddy_sha256']
    # The entire existing root-domain app/browser configuration stays byte-identical.
    marker='\nviridis-security.com {'
    assert CONFIG.read_text().split(marker,1)[1]==candidate.read_text().split(marker,1)[1]
    backup=ROOT/'backup'
    backup.mkdir(mode=0o700,exist_ok=True)
    shutil.copy2(CONFIG,backup/'Caddyfile')
    records={}
    for item in manifest['files']:
        rel=item['path'];source=ROOT/'landing'/rel
        assert not Path(rel).is_absolute() and '..' not in Path(rel).parts
        assert sha(source)==item['sha256']
        current=LANDING/rel
        records[rel]=sha(current) if current.exists() else None
        if current.exists():
            dst=backup/'landing'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(current,dst)
    save('backup/manifest.json',{'caddy_sha256':sha(CONFIG),'landing':records})
    # Validate with the current gateway's existing environment, without printing it.
    run('docker','cp',str(candidate),CADDY+':/tmp/security-frontdoor-candidate.caddy')
    run('docker','exec',CADDY,'caddy','validate','--config','/tmp/security-frontdoor-candidate.caddy','--adapter','caddyfile')
    save('prepared.json',{'status':'PREPARED','services':services,'candidate_caddy_sha256':sha(candidate),'files':manifest['files']})


def verify(base, *, require_preflight=True):
    status,_,value=request(base,'/health')
    assert status==200 and value['ok'] is True
    result={'injection_health':value,'injection_mcp':mcp(base,'/mcp')}
    for path in ['/','/llms.txt','/sitemap.xml','/security-preflight','/security-preflight/quickstart']:
        status,headers,body=request(base,path)
        assert status==200 and 'security-preflight' in body,path
        if path.startswith('/security-preflight'):
            assert 'rel="canonical" href="'+SECURITY+path+'"' in body
            assert 'noindex' not in headers.get('X-Robots-Tag','').lower()
    status,_,service=request(base,'/security-preflight/service.json')
    assert status==200 and service['mcp']['url']==SECURITY+'/security-preflight/mcp'
    status,_,spec=request(base,'/security-preflight/openapi.json')
    assert status==200 and spec['servers'][0]['url']==SECURITY
    if require_preflight:
        result['preflight_mcp']=mcp(base,'/security-preflight/mcp')
        assert 'security_preflight' in result['preflight_mcp']['tools']
        status,_,watch=request(base,'/security-preflight/watch',{'inputs':FIXTURE})
        assert status==200 and watch['decision']=='BASELINE_REQUIRED'
        assert watch['quote_request']['url']==SECURITY+'/x402/security-preflight/security_preflight'
        assert watch['payment_authorized'] is False and watch['state_persisted'] is False
        status,headers,_=request(base,'/x402/security-preflight/security_preflight',FIXTURE)
        assert status==402
        encoded=next(v for k,v in headers.items() if k.lower()=='payment-required')
        terms=json.loads(base64.b64decode(encoded))
        assert terms['resource']['url']==SECURITY+'/x402/security-preflight/security_preflight'
        assert terms['x402Version']==2 and terms['accepts'][0]['network']=='eip155:8453'
        assert terms['accepts'][0]['amount']=='10000'
        status,_,_=request(base,'/x402/security-preflight/security_preflight',{})
        assert status==400
        status,_,_=request(base,'/security-preflight/receipts/vsr_'+'0'*24)
        assert status==404
        result.update({'watch':watch,'quote_terms':terms,'payment_attempted':False})
    return result


def rehearse(require_preflight=True):
    base_check()
    scratch=ROOT/'rehearsal-landing'
    assert not scratch.exists(),'Rehearsal directory already exists'
    shutil.copytree(LANDING,scratch)
    shutil.copytree(ROOT/'landing',scratch,dirs_exist_ok=True)
    text=(ROOT/'Caddyfile.candidate').read_text()
    block=text.split('mcp.viridis-security.com {',1)[1].split('\nviridis-security.com {',1)[0]
    trial=ROOT/'Caddyfile.rehearsal'
    trial.write_text('{\n admin off\n auto_https off\n}\nhttp://:8080 {'+block)
    try:
        run('docker','run','-d','--name',TRIAL,'--network',NETWORK,'-p','127.0.0.1:18409:8080','-v',str(trial)+':/etc/caddy/Caddyfile:ro','-v',str(scratch)+':/srv/landing:ro',IMAGE)
        time.sleep(2)
        first=verify(LOCAL,require_preflight=require_preflight)
        run('docker','restart',TRIAL)
        time.sleep(2)
        restarted=verify(LOCAL,require_preflight=require_preflight)
        save('rehearsed.json' if require_preflight else 'static-rehearsed.json',{'status':'REHEARSAL_PASSED' if require_preflight else 'STATIC_REHEARSAL_PASSED','first_boot':first,'restart':restarted,'candidate_caddy_sha256':sha(ROOT/'Caddyfile.candidate')})
    finally:
        subprocess.run(['docker','rm','-f',TRIAL],capture_output=True)
        shutil.rmtree(scratch)


def reload_config():
    # A prior atomic replacement can leave an existing file bind mount stale.
    # Rebind it before reload, and prove the container reads the intended bytes.
    mounted=run('docker','exec',CADDY,'sha256sum','/etc/caddy/Caddyfile').split()[0]
    if mounted!=sha(CONFIG):
        run('docker','restart',CADDY)
        time.sleep(3)
    assert run('docker','exec',CADDY,'sha256sum','/etc/caddy/Caddyfile').split()[0]==sha(CONFIG)
    run('docker','exec',CADDY,'caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile')


def promote():
    manifest=base_check()
    rehearsal=json.loads((ROOT/'rehearsed.json').read_text())
    assert rehearsal['status']=='REHEARSAL_PASSED' and rehearsal['candidate_caddy_sha256']==manifest['candidate_caddy_sha256']
    backup=json.loads((ROOT/'backup/manifest.json').read_text())
    try:
        for item in manifest['files']:
            target=LANDING/item['path'];target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/'landing'/item['path'],target)
            target.chmod(0o644)
        # Preserve the bind-mounted inode: replacing the host file atomically
        # would leave Caddy looking at the old inode until container recreation.
        CONFIG.write_bytes((ROOT/'Caddyfile.candidate').read_bytes())
        reload_config()
        first=verify(SECURITY)
        run('docker','restart',CADDY)
        time.sleep(3)
        restarted=verify(SECURITY)
        assert health()==json.loads((ROOT/'prepared.json').read_text())['services']
        assert sha(CONFIG)==manifest['candidate_caddy_sha256']
        status,_,root=request('https://viridis-security.com','/')
        assert status==200
        save('promoted.json',{'status':'PROMOTED_RESTART_VERIFIED','droplet_id':570189228,'host':'68.183.123.14','canonical_product':SECURITY+'/security-preflight','mcp':SECURITY+'/security-preflight/mcp','caddy_image':IMAGE,'first_boot':first,'restart':restarted,'existing_service_images_unchanged':True,'root_website_http':status,'payment_attempted':False})
    except BaseException:
        CONFIG.write_bytes((ROOT/'backup/Caddyfile').read_bytes())
        for rel,digest in backup['landing'].items():
            target=LANDING/rel
            if digest is None:target.unlink(missing_ok=True)
            else:shutil.copy2(ROOT/'backup/landing'/rel,target)
        reload_config()
        save('rollback.json',{'status':'ROLLED_BACK','caddy_sha256':sha(CONFIG),'services':health()})
        raise


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['prepare','rehearse','promote']);parser.add_argument('--static-only',action='store_true')
    args=parser.parse_args();phase=args.phase
    if args.static_only:
        assert phase=='rehearse'
        rehearse(require_preflight=False)
    else:globals()[phase]()
    print(json.dumps({'phase':phase,'status':'ok','release_dir':str(ROOT)}))
