#!/usr/bin/env python3
"""Promote three public Security buyer-guide files; leave services and state intact."""
import argparse, hashlib, json, os, re, shutil, subprocess, time, urllib.request
from pathlib import Path
ROOT = Path('/opt/viridis/releases/security-buyer-guide-20260908')
LANDING = Path('/opt/viridis/landing')
CADDY = 'deploy-caddy-1'
BASE = 'https://mcp.viridis-security.com'
TRIAL = 'viridis-security-buyer-guide-rehearsal'
FILES = {'security-preflight.html': {'url': '/security-preflight', 'base_sha256': '38998006d7264894852fd2e3842adab32a627edb25440d8511baab3b96041ac7', 'candidate_sha256': 'bd7f17f73b552ff83f2732b0e22cf90ae83d6ed1cc0507a7b049ee75efbe8bbb'}, 'security-preflight/quickstart.html': {'url': '/security-preflight/quickstart', 'base_sha256': 'c24b59322b17c2ca69365153e47a75835687709debb3a9e06817a19ca5fcdaa4', 'candidate_sha256': '28944e54387b33098e5ee491a96d31480ebfe12d46266c7460502fd2d29368a6'}, 'llms.txt': {'url': '/llms.txt', 'base_sha256': '4f30ba520906359fc577b8a65c7f4099ce42584713ade28d1dbcb37b53a24adc', 'candidate_sha256': 'c26c4626e6f72947a64be9e67e02bda5e499a1ad59a1fa40357c69829e4dc0bf'}}

def digest(data): return hashlib.sha256(data).hexdigest()
def sha(path): return digest(path.read_bytes())
def run(*args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=90)
 if p.returncode:raise RuntimeError('Command failed: '+args[0])
 return p.stdout.strip()
def info():return json.loads(run('docker','inspect',CADDY))[0]
def fetch(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'viridis-buyer-guide-release/1.0'}),timeout=25) as r:
  if r.status!=200:raise RuntimeError('Unexpected HTTP response')
  return r.read()
def save(name,value):
 (ROOT/name).write_text(json.dumps(value,indent=2)+'\n')
def check_files(base,field):
 for rel,meta in FILES.items():
  path=('/'+rel) if base.startswith('http://127.0.0.1') else meta['url']
  if digest(fetch(base+path))!=meta[field]:raise RuntimeError('HTTP file mismatch: '+rel)
def prepare(commit):
 if not re.fullmatch('[a-f0-9]{40}',commit):raise RuntimeError('Use an exact published commit')
 if (ROOT/'prepared.json').exists():raise RuntimeError('Release already prepared; reconcile before retrying')
 ROOT.mkdir(parents=True,exist_ok=True)
 state=info()
 if not state['State']['Running']:raise RuntimeError('Caddy is not running')
 for rel,meta in FILES.items():
  if sha(LANDING/rel)!=meta['base_sha256']:raise RuntimeError('Live source drift: '+rel)
  data=fetch('https://raw.githubusercontent.com/jdhart81/viridis-agent-fleet/'+commit+'/deploy/security-frontdoor/landing/'+rel)
  if digest(data)!=meta['candidate_sha256']:raise RuntimeError('Candidate hash mismatch: '+rel)
  candidate=ROOT/'candidate'/rel;candidate.parent.mkdir(parents=True,exist_ok=True);candidate.write_bytes(data)
  backup=ROOT/'backup'/rel;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(LANDING/rel,backup)
 config=Path('/opt/viridis/deploy/Caddyfile')
 metadata={'status':'PREPARED','commit':commit,'image':state['Image'],'config_sha256':sha(config),'files':FILES,'customer_state_touched':False}
 run('docker','run','-d','--rm','--name',TRIAL,'-p','127.0.0.1:18412:80','-v',str(ROOT/'candidate')+':/srv:ro','--entrypoint','caddy',state['Image'],'file-server','--root','/srv','--listen',':80')
 try:
  time.sleep(1)
  check_files('http://127.0.0.1:18412','candidate_sha256')
 finally:run('docker','stop',TRIAL)
 check_files(BASE,'base_sha256')
 metadata['copied_static_rehearsal']='PASS'
 save('prepared.json',metadata)
 print(json.dumps(metadata))
def replace(target,source):
 tmp=target.with_name(target.name+'.buyer-candidate')
 shutil.copy2(source,tmp)
 os.chmod(tmp,target.stat().st_mode & 0o777)
 os.replace(tmp,target)
def rollback():
 for rel,meta in FILES.items():
  source=ROOT/'backup'/rel
  if sha(source)!=meta['base_sha256']:raise RuntimeError('Rollback hash mismatch')
 for rel in FILES:replace(LANDING/rel,ROOT/'backup'/rel)
 check_files(BASE,'base_sha256')
 save('rolled-back.json',{'status':'ROLLED_BACK'})
def promote():
 prepared=json.loads((ROOT/'prepared.json').read_text())
 state=info()
 if state['Image']!=prepared['image'] or not state['State']['Running']:raise RuntimeError('Caddy drift')
 if sha(Path('/opt/viridis/deploy/Caddyfile'))!=prepared['config_sha256']:raise RuntimeError('Configuration drift')
 for rel,meta in FILES.items():
  if sha(LANDING/rel)!=meta['base_sha256'] or sha(ROOT/'candidate'/rel)!=meta['candidate_sha256']:raise RuntimeError('File drift')
 try:
  for rel in FILES:replace(LANDING/rel,ROOT/'candidate'/rel)
  check_files(BASE,'candidate_sha256')
  # Directory bind mount must expose the promoted bytes inside the current container.
  mounts=[m for m in state['Mounts'] if m['Source'].rstrip('/')==str(LANDING)]
  if len(mounts)!=1:raise RuntimeError('Landing mount missing or ambiguous')
  for rel,meta in FILES.items():
   actual=run('docker','exec',CADDY,'sha256sum',mounts[0]['Destination'].rstrip('/')+'/'+rel).split()[0]
   if actual!=meta['candidate_sha256']:raise RuntimeError('Container file mismatch')
  if json.loads(fetch(BASE+'/health')).get('ok') is not True:raise RuntimeError('Security health failed')
  contract=json.loads(fetch(BASE+'/security-preflight/service.json'))
  if contract['mcp']['url']!=BASE+'/security-preflight/mcp':raise RuntimeError('MCP contract changed')
  if info()['Image']!=prepared['image']:raise RuntimeError('Image changed')
  receipt={'status':'PROMOTED_STATIC_FILES_VERIFIED','commit':prepared['commit'],'image':prepared['image'],'config_unchanged':True,'customer_state_touched':False,'payment_attempted':False,'files':FILES,'rollback':str(ROOT/'backup')}
  save('promoted.json',receipt);print(json.dumps(receipt))
 except BaseException:
  rollback();raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','promote','rollback']);p.add_argument('--commit');a=p.parse_args()
 if a.phase=='prepare':prepare(a.commit or '')
 elif a.phase=='promote':promote()
 else:rollback()
