"""Bounded MCP SDK smoke: discovery and description only; no auth or purchases."""
import asyncio
import json
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROOT = Path(__file__).resolve().parents[1]

async def check(url=None, *, httpx_client_factory=None):
    contract=json.loads((ROOT/'TOOL_CONTRACT.json').read_text())
    expected=set(contract['diagnostic_tools']+contract['priced_tools_excluded_from_diagnostic'])
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

if __name__=='__main__':
    print(json.dumps(asyncio.run(check()),indent=2))
