"""Update public Security discovery files and two existing paid proxy routes."""
import argparse, base64, hashlib, json, os, shutil, subprocess, time, urllib.request, urllib.error, zlib
from pathlib import Path

ROOT=Path('/opt/viridis/releases/agent-security-discovery-20260917')
LANDING=Path('/opt/viridis/landing')
CONFIG=Path('/opt/viridis/deploy/Caddyfile')
LIVE='deploy-caddy-1'
TRIAL='viridis-agent-security-discovery-rehearsal'
BASE_CONFIG='b4df142bcdd45948af28d1e740c5a5584eb10dde99e8daaccf7e94faa3477e27'
PUBLIC='https://mcp.viridis-security.com'
PAYLOAD='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'

def run(*args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=90)
    if p.returncode:
        (ROOT/'last-error.log').write_text(p.stdout+p.stderr)
        raise RuntimeError('Command failed: '+args[0])
    return p.stdout.strip()

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(name,data):(ROOT/name).write_text(json.dumps(data,indent=2)+'\n')
def get(base,path,data=None):
    req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream','X-Viridis-Acquisition-Source':'internal'})
    try:r=urllib.request.urlopen(req,timeout=25)
    except urllib.error.HTTPError as e:r=e
    with r:return r.code,dict(r.headers),r.read()

def verify(base):
    for path,rel in [('/','index.html'),('/llms.txt','llms.txt'),('/security-preflight','security-preflight.html'),('/security-preflight/quickstart','security-preflight/quickstart.html')]:
        status,_,body=get(base,path)
        assert status==200 and hashlib.sha256(body).hexdigest()==sha(ROOT/'candidate'/rel),path
    for tool,data in [('scan_source',{'agent_id':'release-only','source':'const x = 1;'}),('screen_injection',{'agent_id':'release-only','texts':['ordinary sample']}),('security_preflight',{'agent_id':'release-only','manifest':{'tools':[]}})]:
        status,headers,body=get(base,'/x402/security-preflight/'+tool,data)
        assert status==402,(tool,status)
        encoded=next(v for k,v in headers.items() if k.lower()=='payment-required')
        terms=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
        assert terms['resource']['url']==PUBLIC+'/x402/security-preflight/'+tool
        if tool!='security_preflight':assert terms['accepts'][0]['amount']=='1000000'
    status,_,body=get(base,'/security-preflight/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}})
    assert status==200 and b'scan_source' in body and b'screen_injection' in body
    return {'status':'PASS','payment_attempted':False,'public_files':4,'security_quotes':3}

def prepare():
    assert not (ROOT/'prepared.json').exists()
    payload=json.loads(zlib.decompress(base64.b64decode(PAYLOAD)))
    assert sha(CONFIG)==BASE_CONFIG
    for rel,item in payload.items():assert sha(LANDING/rel)==item['old_sha256'],rel
    info=json.loads(run('docker','inspect',LIVE))[0]
    backup=ROOT/'backup';backup.mkdir(mode=0o700)
    shutil.copy2(CONFIG,backup/'Caddyfile')
    candidate=ROOT/'candidate';shutil.copytree(LANDING,candidate)
    for rel,item in payload.items():
        dst=backup/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(LANDING/rel,dst)
        (candidate/rel).write_text(item['content'])
    config=CONFIG.read_text()
    old='/x402/security-preflight/security_preflight /x402/feedback'
    assert config.count(old)==1
    config=config.replace(old,'/x402/security-preflight/security_preflight /x402/security-preflight/scan_source /x402/security-preflight/screen_injection /x402/feedback')
    (ROOT/'Caddyfile.candidate').write_text(config)
    run('docker','cp',str(ROOT/'Caddyfile.candidate'),LIVE+':/tmp/agent-security-candidate.caddy')
    run('docker','exec',LIVE,'caddy','validate','--config','/tmp/agent-security-candidate.caddy','--adapter','caddyfile')
    trial=config[config.index('mcp.viridis-security.com {'):].split('\nviridis-security.com {',1)[0]
    trial='{\n admin off\n auto_https off\n}\n'+trial.replace('mcp.viridis-security.com {','http://:8080 {',1)
    (ROOT/'Caddyfile.rehearsal').write_text(trial)
    try:
        run('docker','run','-d','--name',TRIAL,'--network','deploy_viridis','-p','127.0.0.1:18429:8080','-v',str(candidate)+':/srv/landing:ro','-v',str(ROOT/'Caddyfile.rehearsal')+':/etc/caddy/Caddyfile:ro',info['Image'])
        time.sleep(2);first=verify('http://127.0.0.1:18429')
        run('docker','restart',TRIAL);time.sleep(2);second=verify('http://127.0.0.1:18429')
    finally:subprocess.run(['docker','rm','-f',TRIAL],capture_output=True)
    save('prepared.json',{'status':'REHEARSAL_PASSED','image':info['Image'],'files':{rel:sha(candidate/rel) for rel in payload},'base_files':{rel:item['old_sha256'] for rel,item in payload.items()},'candidate_config':sha(ROOT/'Caddyfile.candidate'),'first':first,'restart':second})

def promote():
    p=json.loads((ROOT/'prepared.json').read_text())
    assert not (ROOT/'promoted.json').exists()
    assert p['status']=='REHEARSAL_PASSED' and sha(CONFIG)==BASE_CONFIG
    assert run('docker','inspect','--format','{{.Image}}',LIVE)==p['image']
    for rel,h in p['base_files'].items():assert sha(LANDING/rel)==h
    for rel,h in p['files'].items():assert sha(ROOT/'candidate'/rel)==h
    assert sha(ROOT/'Caddyfile.candidate')==p['candidate_config']
    try:
        for rel in p['files']:(LANDING/rel).write_bytes((ROOT/'candidate'/rel).read_bytes())
        CONFIG.write_bytes((ROOT/'Caddyfile.candidate').read_bytes())
        run('docker','exec',LIVE,'caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile')
        result=verify(PUBLIC)
        save('promoted.json',{'status':'PROMOTED_VERIFIED','verification':result,'caddy_image_unchanged':p['image'],'files':p['files'],'config':sha(CONFIG),'rollback':str(ROOT/'backup')})
    except BaseException:
        for rel in p['files']:(LANDING/rel).write_bytes((ROOT/'backup'/rel).read_bytes())
        CONFIG.write_bytes((ROOT/'backup/Caddyfile').read_bytes())
        run('docker','exec',LIVE,'caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile')
        save('rollback.json',{'status':'ROLLED_BACK'})
        raise

if __name__=='__main__':
    os.umask(0o077);ROOT.mkdir(parents=True,exist_ok=True)
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['prepare','promote']);args=parser.parse_args()
    {'prepare':prepare,'promote':promote}[args.phase]()
    print(json.dumps({'status':'PASS','phase':args.phase}))
