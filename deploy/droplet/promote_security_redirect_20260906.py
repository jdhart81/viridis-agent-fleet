#!/usr/bin/env python3
"""Redirect only the legacy human Preflight page after the Security site is live."""
import hashlib,json,os,subprocess,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path('/root/viridis-candidates/security-redirect-20260906')
CONFIG=Path('/root/viridis-fleet/Caddyfile')
LIVE='viridis-fleet-caddy-1'
IMAGE='sha256:af5fdcd76f2db5e4e974ee92f96ee8c0fc3edb55bd4ba5032547cbf3f65e486d'
BASE='5650e4bf828bfbf6b9e5c533f6bf69387e0e32ecdbd91f878fa0fd20248dc185'
PUBLIC='https://mcp.viridisconservation.com'
SECURITY='https://mcp.viridis-security.com'
TRIAL='viridis-security-redirect-rehearsal'
ADDITION='\t@preflightHuman {\n\t\tpath /security-preflight /security-preflight/\n\t\tmethod GET HEAD\n\t}\n\tredir @preflightHuman https://mcp.viridis-security.com{uri} 308\n'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(*args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=120)
 if p.returncode:
  (ROOT/'last-command-error.log').write_text(p.stdout+p.stderr)
  raise RuntimeError('Command failed: '+args[0])
 return p.stdout.strip()
def save(name,obj):(ROOT/name).write_text(json.dumps(obj,indent=2)+'\n')
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args):return None

def check(base):
 for path in ['/security-preflight','/security-preflight/','/security-preflight?source=internal']:
  for method in ['GET','HEAD']:
   req=urllib.request.Request(base+path,method=method)
   try:r=urllib.request.build_opener(NoRedirect).open(req,timeout=25)
   except urllib.error.HTTPError as e:r=e
   with r:assert r.code==308 and r.headers['Location']==SECURITY+path
 with urllib.request.urlopen(base+'/healthz',timeout=25) as r:
  health=json.load(r);assert r.code==200 and health['status']=='ok' and len(health['agents'])==28
 # The exact MCP path remains the existing transport, not a redirect.
 req=urllib.request.Request(base+'/security-preflight/mcp',data=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'domain-redirect-verification','version':'1.0'}}}).encode(),headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream'})
 with urllib.request.build_opener(NoRedirect).open(req,timeout=25) as r:assert r.code==200
 return {'human_redirects':'PASS','legacy_mcp_initialization':'PASS','healthy_agents':28}

def main():
 os.umask(0o077);ROOT.mkdir(parents=True,exist_ok=True)
 assert not (ROOT/'promoted.json').exists()
 assert sha(CONFIG)==BASE
 assert run('docker','inspect','--format','{{.Image}}',LIVE)==IMAGE
 with urllib.request.urlopen(SECURITY+'/security-preflight',timeout=25) as r:
  assert r.code==200 and ('rel="canonical" href="'+SECURITY+'/security-preflight"') in r.read().decode()
 original=CONFIG.read_bytes();(ROOT/'Caddyfile.backup').write_bytes(original)
 candidate=ROOT/'Caddyfile.candidate';candidate.write_text(original.decode().replace('mcp.viridisconservation.com {\n','mcp.viridisconservation.com {\n'+ADDITION,1))
 run('docker','cp',str(candidate),LIVE+':/tmp/security-redirect.caddy')
 run('docker','exec',LIVE,'caddy','validate','--config','/tmp/security-redirect.caddy','--adapter','caddyfile')
 trial=ROOT/'Caddyfile.rehearsal';trial.write_text('{\n admin off\n auto_https off\n}\n'+candidate.read_text().replace('mcp.viridisconservation.com {','http://:8080 {',1))
 try:
  run('docker','run','-d','--name',TRIAL,'--network','viridis-fleet_default','-p','127.0.0.1:18410:8080','-v',str(trial)+':/etc/caddy/Caddyfile:ro',IMAGE)
  time.sleep(2);check('http://127.0.0.1:18410')
  run('docker','restart',TRIAL);time.sleep(2);check('http://127.0.0.1:18410')
 finally:subprocess.run(['docker','rm','-f',TRIAL],capture_output=True)
 save('rehearsed.json',{'status':'REHEARSAL_PASSED','candidate_sha256':sha(candidate)})
 assert sha(CONFIG)==BASE
 try:
  CONFIG.write_bytes(candidate.read_bytes())
  run('docker','exec',LIVE,'caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile')
  first=check(PUBLIC)
  run('docker','restart',LIVE);time.sleep(3);restarted=check(PUBLIC)
  save('promoted.json',{'status':'PROMOTED_RESTART_VERIFIED','base_caddy_sha256':BASE,'candidate_caddy_sha256':sha(CONFIG),'image_unchanged':IMAGE,'first_boot':first,'restart':restarted})
 except BaseException:
  CONFIG.write_bytes(original);run('docker','exec',LIVE,'caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile')
  save('rollback.json',{'status':'ROLLED_BACK','sha256':sha(CONFIG)});raise
 print(json.dumps({'status':'PROMOTED_RESTART_VERIFIED','release_dir':str(ROOT)}))
if __name__=='__main__':main()
