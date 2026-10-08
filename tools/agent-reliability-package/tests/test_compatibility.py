"""Check real package wiring against the adapter and mock MCP wire exchanges."""
import ast
import asyncio
import importlib.util
import json
import tomllib
import httpx
from pathlib import Path

import pytest

TOOLS=Path(__file__).resolve().parents[1]
REPO=TOOLS.parents[1]
ROOT=REPO/"plugins/viridis-agent-reliability"
spec=importlib.util.spec_from_file_location('viridis_mcp_check', TOOLS/'scripts/check_mcp.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
CONTRACT=json.loads((ROOT/'TOOL_CONTRACT.json').read_text())
HOSTED_NAMES=set(CONTRACT['priced_tools_excluded_from_diagnostic'])
LEGACY_READ={'describe_agent','get_security_receipt'}
NAMES=HOSTED_NAMES|LEGACY_READ

def test_manifests_connect_real_mcp_and_exclude_payment_endpoint():
    catalog=json.loads((REPO/'.agents/plugins/marketplace.json').read_text())
    assert len(catalog['plugins'])==1
    candidate=catalog['plugins'][0]
    assert (REPO/candidate['source']['path']).resolve()==ROOT.resolve()
    assert candidate['policy']['installation']=='AVAILABLE'
    for path in ('mcp.json','.mcp.json'):
        config=json.loads((ROOT/path).read_text())
        servers=config['mcpServers']
        assert len(servers)==1
        server=next(iter(servers.values()))
        assert server['url']==CONTRACT['endpoint']
        assert server['type']==('streamable-http' if path=='mcp.json' else 'http')
        assert 'headers' not in server and 'oauth' not in server
    for path in ('plugin.json','.codex-plugin/plugin.json','.claude-plugin/plugin.json'):
        manifest=json.loads((ROOT/path).read_text())
        assert manifest['name']=='viridis-agent-reliability' and manifest['version']=='0.1.4'
        assert 'reliability-sprint' not in json.dumps(manifest)
    assert json.loads((ROOT/'.codex-plugin/plugin.json').read_text())['mcpServers']=='./.mcp.json'

def test_tool_contract_matches_decorated_adapter_without_running_scanner():
    tree=ast.parse((REPO/'security-preflight-agent/adapters/mcp_server.py').read_text())
    exposed={node.name for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
             and any(isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr=='tool' for d in node.decorator_list)}
    assert exposed==NAMES
    assert set(CONTRACT['diagnostic_tools'])==set()
    assert HOSTED_NAMES=={'security_preflight','scan_source','screen_injection'}
    assert CONTRACT['discovery_stage'].endswith('authorization and execution blocked')
    skill=(ROOT/'skills/agent-reliability-check/SKILL.md').read_text()
    assert 'reliability-sprint' not in skill
    assert all('`'+name+'`' in skill for name in NAMES)

def test_real_adapter_sdk_advertises_read_and_priced_tools_truthfully(monkeypatch):
    monkeypatch.setenv('SECURITY_PREFLIGHT_RECEIPT_DB_PATH',':memory:')
    import sys
    adapter=REPO/'security-preflight-agent/adapters/mcp_server.py'
    saved=list(sys.path)
    try:
        specification=importlib.util.spec_from_file_location('onboarding_preflight_adapter',adapter)
        module=importlib.util.module_from_spec(specification);specification.loader.exec_module(module)
        try:
            tools=asyncio.run(module.mcp.list_tools())
            assert {t.name for t in tools}==NAMES
            assert all(t.title for t in tools)
            for tool in tools:
                assert tool.annotations.readOnlyHint is (tool.name in LEGACY_READ)
                assert tool.annotations.idempotentHint is (tool.name in LEGACY_READ)
                assert tool.annotations.destructiveHint is False
                assert tool.annotations.openWorldHint is False
        finally:
            module.agent.close()
    finally:
        sys.path[:]=saved

def test_adapter_public_receipt_filters_private_stored_fields(monkeypatch):
    import sys
    adapter=REPO/'security-preflight-agent/adapters/mcp_server.py'
    monkeypatch.syspath_prepend(str(adapter.parents[1]))
    specification=importlib.util.spec_from_file_location('privacy_preflight_adapter',adapter)
    module=importlib.util.module_from_spec(specification);specification.loader.exec_module(module)
    stored={'status':'ok','receipt':{'receipt_id':'vsr_'+'a'*24,
        'subject_agent_id':'PRIVATE_FIXTURE','result_counts':{'checks':1}},
        'evidence':{'checks':['PRIVATE_FIXTURE']},'signature_b64':'PRIVATE_FIXTURE'}
    async def process(payload): return stored
    monkeypatch.setattr(module.agent,'process',process)
    try:
        view=json.loads(asyncio.run(module.get_security_receipt('vsr_'+'a'*24)))
        assert view['public_view_protocol']=='viridis-security-public-view-v1'
        assert 'PRIVATE_FIXTURE' not in json.dumps(view)
        invalid=asyncio.run(module.get_security_receipt('PRIVATE_FIXTURE'))
        assert 'PRIVATE_FIXTURE' not in invalid
    finally:
        module.agent.close()

@pytest.mark.parametrize('sse,paginated,wrong_tool',[(False,False,False),(True,True,False),(False,False,True)])
def test_sdk_wire_discovery_and_description_only(sse,paginated,wrong_tool):
    calls=[]
    required={'security_preflight':['agent_id','manifest'],'scan_source':['agent_id','source'],
              'screen_injection':['agent_id','texts'],'get_security_receipt':['receipt_id'],'describe_agent':[]}
    tools=[{'name':name,'inputSchema':{'type':'object','properties':{},'required':required[name]}} for name in sorted(NAMES)]
    if wrong_tool:tools[0]['name']='invented_quote_tool'
    def handler(request):
        if request.method!='POST':return httpx.Response(405)
        body=json.loads(request.content)
        method=body['method'];calls.append((method,body.get('params',{})))
        if 'id' not in body:return httpx.Response(202)
        if method=='initialize':result={'protocolVersion':body['params']['protocolVersion'],'capabilities':{'tools':{}},'serverInfo':{'name':'test-preflight','version':'1'}}
        elif method=='tools/list':
            second=body.get('params',{}).get('cursor')=='second'
            result={'tools':tools[2:] if second else tools[:2] if paginated else tools}
            if paginated and not second:result['nextCursor']='second'
        elif method=='tools/call' and body['params']['name']=='describe_agent':result={'content':[{'type':'text','text':json.dumps({'name':'security-preflight-agent','version':'fixture'})}]}
        else:raise AssertionError('Business tool invoked by smoke test')
        message=json.dumps({'jsonrpc':'2.0','id':body['id'],'result':result})
        data=('event: message\ndata: '+message+'\n\n' if sse else message).encode()
        return httpx.Response(200,content=data,headers={'content-type':'text/event-stream' if sse else 'application/json'})
    def factory(headers=None,timeout=None,auth=None):
        return httpx.AsyncClient(headers=headers,timeout=timeout,auth=auth,transport=httpx.MockTransport(handler))
    if wrong_tool:
        with pytest.raises(Exception) as failure:asyncio.run(probe.check('https://fixture.invalid/mcp',httpx_client_factory=factory))
        assert 'adapter tool contract mismatch' in repr(failure.value)
    else:
        result=asyncio.run(probe.check('https://fixture.invalid/mcp',httpx_client_factory=factory))
        assert result['status']=='pass' and not result['paid_tools_called']
    invoked=[params['name'] for method,params in calls if method=='tools/call']
    assert invoked==([] if wrong_tool else ['describe_agent'])


def test_claude_marketplace_resolves_same_plugin():
    catalog=json.loads((REPO/'.claude-plugin/marketplace.json').read_text())
    assert catalog['name']=='viridis-agent-fleet'
    assert len(catalog['plugins'])==1
    entry=catalog['plugins'][0]
    assert entry['name']=='viridis-agent-reliability'
    assert (REPO/entry['source']).resolve()==ROOT.resolve()


def test_submission_archive_excludes_checkout_and_untracked_files(tmp_path):
    import shutil
    import zipfile
    specification=importlib.util.spec_from_file_location('package_builder',TOOLS/'scripts/build_package.py')
    builder=importlib.util.module_from_spec(specification);specification.loader.exec_module(builder)
    copied=tmp_path/'plugin';shutil.copytree(ROOT,copied)
    (copied/'unknown-private-file.txt').write_text('invented test marker')
    first=tmp_path/'first.zip';second=tmp_path/'second.zip'
    a=builder.build(first,root=copied);b=builder.build(second,root=copied)
    assert a['sha256']==b['sha256'] and not a['submitted']
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist())==set(builder.FILES)
        assert not any('examples/' in name or 'unknown-private' in name for name in archive.namelist())
        assert json.loads(archive.read('plugin.json'))['version']=='0.1.4'
        assert 'LICENSE' in archive.namelist()


def test_submission_archive_rejects_symlink(tmp_path):
    import shutil
    specification=importlib.util.spec_from_file_location('package_builder_links',TOOLS/'scripts/build_package.py')
    builder=importlib.util.module_from_spec(specification);specification.loader.exec_module(builder)
    copied=tmp_path/'plugin';shutil.copytree(ROOT,copied)
    outside=tmp_path/'outside.txt';outside.write_text('invented marker')
    (copied/'README.md').unlink();(copied/'README.md').symlink_to(outside)
    with pytest.raises(ValueError,match='symlink'):
        builder.build(tmp_path/'unsafe.zip',root=copied)

@pytest.mark.parametrize('wrong_resource',[False,True])
def test_hosted_discovery_requires_exact_resource_and_never_calls_tools(wrong_resource):
    endpoint=CONTRACT['endpoint'];origin='https://mcp.viridisconservation.com';resource=origin+'/.well-known/oauth-protected-resource/hosted-entitlements/mcp'
    requests=[]
    def handler(request):
        requests.append((request.method,str(request.url)))
        if request.method=='POST':
            assert json.loads(request.content)['method']=='initialize'
            return httpx.Response(401,headers={'www-authenticate':'Bearer resource_metadata="'+resource+'"'})
        if str(request.url)==resource:
            return httpx.Response(200,json={'resource':endpoint if not wrong_resource else 'https://other.invalid/mcp','authorization_servers':[origin+'/hosted-entitlements']})
        assert str(request.url)==origin+'/.well-known/oauth-authorization-server/hosted-entitlements'
        return httpx.Response(200,json={'issuer':origin+'/hosted-entitlements','scopes_supported':['security-preflight:assess']})
    call=probe.check_hosted_discovery(transport=httpx.MockTransport(handler))
    if wrong_resource:
        with pytest.raises(ValueError,match='resource binding'):asyncio.run(call)
    else:
        result=asyncio.run(call)
        assert result['status']=='discovery_only' and not result['paid_tools_called']
    assert all(not url.endswith(('/authorize','/token','/register')) for _,url in requests)
