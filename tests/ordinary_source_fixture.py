"""Disposable official-SDK source-receipt peer; no model, server or work creation."""
import asyncio
import json
import os
from pathlib import Path
import sys
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent
from acp.schema import AgentCapabilities, LoadSessionResponse, McpCapabilities
from acp.exceptions import RequestError
META='com.microsoft.amplifier.source-delivery'
INSTANCE='io.github.bkrabach.agent-instance'
path=Path(sys.argv[1]); mode=sys.argv[2]
def load():return json.loads(path.read_text()) if path.exists() else {'prompts':[], 'queries':[], 'rows':{}}
def save(value):path.write_text(json.dumps(value))
class Peer(Agent):
    async def initialize(self, protocol_version, **kwargs):
        cap={'version':1,'metadata':META,'receiptsMethod':'_amplifier/source_receipts','ordinaryPrompts':True,'promptRetry':'inspectOnly','workReferences':True}
        if mode=='legacy':cap={}
        if mode=='steering-only':cap.pop('ordinaryPrompts')
        return InitializeResponse(protocol_version=protocol_version,agent_capabilities=AgentCapabilities(load_session=True,mcp_capabilities=McpCapabilities(http=True)),field_meta={INSTANCE:{'inputContinuity':{'sourceDelivery':cap}}})
    async def new_session(self, cwd, **kwargs):return NewSessionResponse(session_id='original-session')
    async def load_session(self, session_id, cwd, **kwargs):
        assert session_id=='original-session'
        return LoadSessionResponse()
    async def prompt(self, session_id, prompt, **kwargs):
        assert session_id=='original-session'
        d=load();meta=kwargs.get(META)
        d['prompts'].append({'session':session_id,'metadata':meta,'attention':kwargs.get('com.microsoft.amplifier.attention')})
        if meta:
            old=d['rows'].get(meta['inputId'])
            if old and (old['kind']=='ordinary' or old['state'] not in ('notAccepted','promptRequired') or old['incorporated']):raise RequestError(-32002,'inspect only')
            d['rows'][meta['inputId']]={**(old or {}),'kind':'ordinary','sources':meta['sources'],'state':'submitted','incorporated':False,'original_actor':(old or {}).get('original_actor','original-human')}
        save(d)
        if prompt[-1].text=='lost':os._exit(0)
        return PromptResponse(stop_reason='end_turn')
    async def ext_method(self, method, params):
        if method=='test/seed':
            d=load();d['rows'][params['id']]=params['row'];save(d);return {}
        if method!='amplifier/source_receipts':raise RequestError.method_not_found(method)
        assert params['sessionId']=='original-session'
        d=load();d['queries'].append(params);save(d);rows=[]
        if mode=='query-fails':raise RequestError(-32002,'receipt unavailable')
        for source in params['sources']:
            match=next(((key,row) for key,row in d['rows'].items() if source in row['sources']),None)
            if not match:continue
            key,row=match
            refs=[] if mode=='zero-work' else [{'id':'work-'+str(n),'ownerAgentId':'instance-owner','revision':n+1,'state':'proposed' if n==0 else 'accepted','inputId':key} for n in range(2)]
            item={'sourceId':source['id'],'revision':source['revision'],'occurredAt':source['occurredAt'],'inputId':key,'state':row['state'],'incorporated':row['incorporated'],'work':refs,'workCoverage':'partial' if mode=='partial' else 'retained_session_records'}
            if mode=='wrong-source':item['revision']='unrelated'
            if mode=='wrong-input':item['inputId']='another-input'
            if mode=='evicted-delivery':item.update(inputId=None,state='unknown',incorporated=False)
            if mode=='bad-work':item['work'][0]['revision']=True
            if mode=='missing-incorporation':item.pop('incorporated')
            rows.append(item)
        return {'version':1,'receipts':rows,'coverage':{'missing':'unknown'}}
asyncio.run(run_agent(Peer()))
