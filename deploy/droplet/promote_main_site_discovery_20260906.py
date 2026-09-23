#!/usr/bin/env python3
"""Build, rehearse, and promote the scoped public agent-service links."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

ROOT = Path('/home/deploy/releases/926cd1a7a55b-agent-discovery')
COMMIT = '926cd1a7a55b873756ae41cd40fa257491ee564e'
OLD_COMMIT = 'ed20587d67d708ebf19396a86239c12d455b7542'
BASE = 'sha256:88ae30fdce63f1b58611b796f6866d36da49e59d2a8107d2404f75ad1d51a126'
LIVE = 'viridis-app'
ENV = Path('/home/deploy/viridis-conservation/.env.local')
TAG = 'viridis-conservation:release-926cd1a7a55b'
ROLLBACK = 'viridis-conservation:rollback-ed20587d67d7-agent-discovery'
TRIAL = 'viridis-agent-discovery-rehearsal'
LINK = 'https://mcp.viridisconservation.com/security-preflight'


def run(*args, timeout=180, env=None):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
    if p.returncode:
        (ROOT/'last-command-error.log').write_text(p.stdout+p.stderr)
        raise RuntimeError('Command failed: '+args[0]+' '+args[1])
    return p.stdout.strip()


def save(name, obj):
    (ROOT/name).write_text(json.dumps(obj, indent=2, sort_keys=True)+'\n')


def info(name=LIVE):
    return json.loads(run('docker','inspect',name))[0]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def base_check():
    i=info()
    assert i['Image']==BASE and i['State']['Health']['Status']=='healthy'
    assert i['Mounts']==[]
    assert i['HostConfig']['PortBindings']=={'3000/tcp':[{'HostIp':'127.0.0.1','HostPort':'3000'}]}
    assert i['HostConfig']['RestartPolicy']['Name']=='unless-stopped'
    assert ENV.stat().st_mode & 0o777 == 0o600
    return i


def healthy(name, image):
    for _ in range(60):
        i=info(name)
        if i['Image']==image and i['State']['Health']['Status']=='healthy':return
        time.sleep(2)
    raise RuntimeError('Candidate did not become healthy')


def get(base, path):
    with urllib.request.urlopen(base+path, timeout=30) as r:
        assert r.status==200
        return r.read().decode()


def verify(base, commit):
    health=json.loads(get(base,'/healthz'))
    assert health['status']=='ok' and health['commit']==commit
    for path in ['/', '/developers']:
        page=get(base,path)
        assert LINK in page and 'Agent services' in page
        if path=='/developers':
            assert 'Security Preflight' in page and 'https://mcp.viridisconservation.com/x402/catalog' in page
    services=json.loads(get(base,'/api/viridisos/decision-services'))
    assert services['stats']['runnablePreviews']==17
    assert any(k['id']=='thermodynamic-economic-allocation' for k in services['kernels'])
    return {'health':health,'agent_links_verified':True,'existing_kernel_catalog_verified':True}


def start(name, image, port, commit, restart='no'):
    run('docker','run','-d','--name',name,'--restart',restart,
        '-p',f'127.0.0.1:{port}:3000','--env-file',str(ENV),
        '--env','GIT_COMMIT_SHA='+commit,image)


def prepare():
    assert not (ROOT/'prepared.json').exists()
    base_check()
    env_hash=digest(ENV)
    shutil.copy2(ENV,ROOT/'rollback.env.pre-release')
    # Copy only the five existing browser-visible values into build arguments.
    # Runtime secrets never enter the build or leave the host.
    values=dict(e.split('=',1) for e in info()['Config']['Env'])
    keys=['NEXT_PUBLIC_SUPABASE_URL','NEXT_PUBLIC_SUPABASE_ANON_KEY',
          'NEXT_PUBLIC_MT_CADASTRAL','NEXT_PUBLIC_MAPBOX_TOKEN','NEXT_PUBLIC_SITE_URL']
    build_env=dict(os.environ)
    args=['docker','build','--pull=false','--build-arg','GIT_COMMIT_SHA='+COMMIT]
    for key in keys:
        build_env[key]=values.get(key,'')
        args+=['--build-arg',key]
    output=run(*args,'-t',TAG,str(ROOT/'source'),timeout=900,env=build_env)
    (ROOT/'build.log').write_text(output)
    image=run('docker','image','inspect','--format','{{.Id}}',TAG)
    assert digest(ENV)==env_hash
    save('prepared.json',{'commit':COMMIT,'base_image':BASE,'image':image,
                         'source_archive_sha256':digest(ROOT/'source.tar.gz'),
                         'environment_sha256':env_hash})


def rehearse():
    base_check()
    prepared=json.loads((ROOT/'prepared.json').read_text())
    try:
        start(TRIAL,prepared['image'],13066,COMMIT)
        healthy(TRIAL,prepared['image'])
        first=verify('http://127.0.0.1:13066',COMMIT)
        run('docker','restart',TRIAL)
        healthy(TRIAL,prepared['image'])
        restarted=verify('http://127.0.0.1:13066',COMMIT)
        assert digest(ENV)==prepared['environment_sha256']
        save('rehearsed.json',{'status':'REHEARSAL_PASSED','image':prepared['image'],
                              'first_boot':first,'restart':restarted})
    finally:
        subprocess.run(['docker','rm','-f',TRIAL],capture_output=True)


def promote():
    base_check()
    p=json.loads((ROOT/'prepared.json').read_text())
    r=json.loads((ROOT/'rehearsed.json').read_text())
    assert r['status']=='REHEARSAL_PASSED' and r['image']==p['image']
    assert digest(ENV)==p['environment_sha256']
    # Require the target product page to be live before adding referral links.
    assert 'MCP Security Preflight' in get('https://mcp.viridisconservation.com','/security-preflight')
    run('docker','tag',BASE,ROLLBACK)
    try:
        run('docker','rm','-f',LIVE)
        start(LIVE,p['image'],3000,COMMIT,'unless-stopped')
        healthy(LIVE,p['image'])
        first=verify('https://viridisconservation.com',COMMIT)
        run('docker','restart',LIVE)
        healthy(LIVE,p['image'])
        restarted=verify('https://viridisconservation.com',COMMIT)
        assert digest(ENV)==p['environment_sha256']
        save('promoted.json',{'status':'PROMOTED_RESTART_VERIFIED','commit':COMMIT,
                             'image':p['image'],'rollback_image':BASE,'rollback_tag':ROLLBACK,
                             'first_boot':first,'restart':restarted,'environment_unchanged':True})
    except BaseException:
        subprocess.run(['docker','rm','-f',LIVE],capture_output=True)
        start(LIVE,BASE,3000,OLD_COMMIT,'unless-stopped')
        healthy(LIVE,BASE)
        health=json.loads(get('http://127.0.0.1:3000','/healthz'))
        assert health['commit']==OLD_COMMIT
        save('rollback.json',{'status':'ROLLED_BACK','image':BASE,'health':health})
        raise


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['prepare','rehearse','promote'])
    phase=parser.parse_args().phase
    globals()[phase]()
    print(json.dumps({'phase':phase,'status':'ok','release_dir':str(ROOT)}))
