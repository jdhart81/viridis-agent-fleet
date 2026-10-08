"""Bounded MCP SDK smoke: discovery and description only; no auth or purchases."""
import asyncio
import json
import httpx
from urllib.parse import urlsplit
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROOT = Path(__file__).resolve().parents[3] / "plugins/viridis-agent-reliability"

async def check(url=None, *, httpx_client_factory=None):
    contract=json.loads((ROOT/'TOOL_CONTRACT.json').read_text())
    if url is None and contract.get('discovery_stage'):
        return await check_hosted_discovery()
    # Explicit legacy probe remains separate from the attached hosted contract.
    expected={'describe_agent','get_security_receipt','security_preflight','scan_source','screen_injection'}
    kwargs={} if httpx_client_factory is None else {'httpx_client_factory':httpx_client_factory}
    async with streamablehttp_client(url or contract['endpoint'], timeout=20, sse_read_timeout=30, **kwargs) as (read,write,_):
        async with ClientSession(read,write) as session:
            initialized=await session.initialize()
            tools=[];cursor=None;seen=set()
            for _ in range(10):
                page=await session.list_tools(cursor=cursor)
                tools.extend(page.tools)
                if not page.nextCursor:break
                if page.nextCursor in seen:raise ValueError('repeated tools cursor')
                seen.add(page.nextCursor)
                cursor=page.nextCursor
                if len(tools)>100:raise ValueError('unbounded tool discovery')
            else:raise ValueError('unbounded tool discovery pages')
            if {tool.name for tool in tools} != expected:
                raise ValueError('adapter tool contract mismatch')
            required={'security_preflight':{'agent_id','manifest'}, 'scan_source':{'agent_id','source'},
                      'screen_injection':{'agent_id','texts'}, 'get_security_receipt':{'receipt_id'}, 'describe_agent':set()}
            for tool in tools:
                if set(tool.inputSchema.get('required',[])) != required[tool.name]:
                    raise ValueError('adapter input contract mismatch: '+tool.name)
            description=await session.call_tool('describe_agent',{})
            if description.isError:raise ValueError('description tool failed')
            data=json.loads(next(c.text for c in description.content if c.type=='text'))
            if data.get('name')!='security-preflight-agent':raise ValueError('service identity mismatch')
            return {'status':'pass','protocol':initialized.protocolVersion,
                    'server':initialized.serverInfo.name,'tools':sorted(expected),
                    'called_tools':['describe_agent'],'service_version':data.get('version'),
                    'credentials_used':False,'paid_tools_called':False,'payment_sessions_created':0}

async def check_hosted_discovery(*, transport=None):
    contract=json.loads((ROOT/'TOOL_CONTRACT.json').read_text())
    endpoint=contract['endpoint'];parts=urlsplit(endpoint)
    if endpoint!='https://mcp.viridisconservation.com/hosted-entitlements/mcp':
        raise ValueError('Exact reviewed hosted endpoint required')
    origin=parts.scheme+'://'+parts.netloc
    resource=origin+'/.well-known/oauth-protected-resource/hosted-entitlements/mcp'
    auth=origin+'/.well-known/oauth-authorization-server/hosted-entitlements'
    async with httpx.AsyncClient(transport=transport,timeout=20,trust_env=False,follow_redirects=False) as client:
        response=await client.post(endpoint,json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})
        if response.status_code!=401 or response.headers.get('www-authenticate')!='Bearer resource_metadata="'+resource+'"':
            raise ValueError('Expected exact hosted 401 discovery challenge')
        r=await client.get(resource);r.raise_for_status();metadata=r.json()
        if metadata.get('resource')!=endpoint or metadata.get('authorization_servers')!=[origin+'/hosted-entitlements']:
            raise ValueError('Hosted resource binding mismatch')
        a=await client.get(auth);a.raise_for_status();issuer=a.json()
        if issuer.get('issuer')!=origin+'/hosted-entitlements' or issuer.get('scopes_supported')!=['security-preflight:assess']:
            raise ValueError('Hosted authorization discovery mismatch')
    return {'status':'discovery_only','mcp_status':401,'credentials_used':False,
            'paid_tools_called':False,'payment_sessions_created':0,'authorization_tested':False}

if __name__=='__main__':
    print(json.dumps(asyncio.run(check()),indent=2))
