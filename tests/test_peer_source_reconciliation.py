"""Actual SDK receipts through the controller; no provider or game effects."""
import asyncio
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import adapter
from acp_client import Client


class PeerSourceReconciliation(unittest.IsolatedAsyncioTestCase):
    async def test_retained_delivery_refuses_prompt_without_reconnect_or_public_notice(self):
        for kind,state,incorporated in [('steering','unknown',False),('steering','submitted',False),
                                         ('steering','incorporated',True),('ordinary','notAccepted',False)]:
            with self.subTest(kind=kind,state=state), tempfile.TemporaryDirectory() as tmp:
                home=Path(tmp)
                source={'id':'original-peer','revision':'exact-revision','occurredAt':1794808300000}
                key='original-input'
                host_row={'kind':kind,'sources':[source],'state':state,'incorporated':incorporated}
                host=home/'host.json'
                host.write_text(json.dumps({'prompts':[],'queries':[],'rows':{key:host_row}}))
                cfg={'control_port':1,'token':'fixture','incoming_chat_only':True,
                     'human_task_intake':{'enabled':True,'delegation':{'enabled':True}}}
                endpoint={'command':[sys.executable,str(Path(__file__).with_name('ordinary_source_fixture.py')),str(host),'supported'],'cwd':tmp}
                bound={**endpoint,'mcp_servers':[{'type':'http','name':'minecraft','url':'http://127.0.0.1:1/mcp',
                       'headers':[{'name':'Authorization','value':'Bearer fixture'}]}]}
                binding=hashlib.sha256(json.dumps(bound,sort_keys=True).encode()).hexdigest()
                session={'binding':binding,'session':'original-session'}
                receipt={'input_id':key,'session_id':'original-session','binding':binding,
                         'sources':[source],'source_ids':[source['id']],'state':'unknown'}
                if kind=='ordinary':receipt['kind']='ordinary'
                for name,value in [('config',cfg),('endpoint',endpoint),('session',session),('awareness-receipts',[receipt])]:
                    (home/(name+'.json')).write_text(json.dumps(value))
                message={'id':source['id'],'source':'agent','message':'Original peer report'}
                conversation={'revision':source['id'],'messages':[{'id':source['id'],'source_fact':source}]}
                task={'id':'retained-task','status':'blocked','turns':23}
                original_task=json.dumps(task,sort_keys=True)
                world={'ready':True,'busy':False,'generation':1,'task':task,'conversation_only':True,
                       'peer_proposal':True,'conversation':conversation,'action_lease':{'version':1,'renewable':False}}
                paths=[];finished=False;active=False;starts=[];closes=[];closes_before_next_state=[]
                class ObservedClient(Client):
                    async def start(self):
                        starts.append(True)
                        return await super().start()
                    async def close(self):
                        closes.append(True)
                        return await super().close()
                def control(config,path,payload=None):
                    nonlocal finished,active
                    paths.append((path,payload))
                    if path=='/state' and finished:
                        closes_before_next_state.extend(closes)
                        raise asyncio.CancelledError()
                    if path in ('/state','/status','/observation'):
                        return {**world,'turn_active':active,'pending_messages':1}
                    if path=='/conversation/admission':return {'version':1,'unmetered':True,'eligible_ids':[source['id']]}
                    if path=='/inbox/peek':return [message]
                    if path=='/turn':active=True;return {}
                    if path=='/conversation':return conversation
                    if path=='/operator-inputs':return {'revision':'empty','messages':[]}
                    if path=='/finish':active=False;finished=True;return {}
                    if path in ('/recover','/inbox/retire-expired'):return {}
                    raise AssertionError(path)
                output=io.StringIO()
                with patch.object(adapter,'control',control),patch.object(adapter,'Client',ObservedClient),contextlib.redirect_stdout(output):
                    with self.assertRaises(asyncio.CancelledError):
                        await asyncio.wait_for(adapter.run(home),10)
                rows=json.loads(host.read_text())
                self.assertEqual(rows['prompts'],[])
                self.assertEqual(len(rows['queries']),1)
                self.assertEqual(rows['rows'][key],host_row)
                self.assertEqual(starts,[True]);self.assertEqual(closes,[True]) # Test cancellation only.
                self.assertEqual(closes_before_next_state,[], 'A no-replay decision must not tear down a healthy connection')
                self.assertEqual([v for k,v in paths if k=='/finish'],[{'error':True}])
                self.assertFalse(any(k in ('/reply','/notice','/wake','/action','/turn/renew') for k,v in paths))
                self.assertEqual(json.loads((home/'session.json').read_text()),session)
                self.assertEqual(json.dumps(task,sort_keys=True),original_task)
                retained=json.loads((home/'awareness-receipts.json').read_text())[0]
                for field in ('input_id','session_id','binding','sources','source_ids','state'):
                    self.assertEqual(retained[field],receipt[field])
                self.assertEqual(retained['source_delivery'][0]['completion'],'not_established')
                events=[json.loads(line) for line in output.getvalue().splitlines()]
                self.assertFalse(any(e['kind']=='adapter_error' for e in events))
                suppressed=[e for e in events if e['kind']=='source_prompt_suppressed']
                self.assertEqual(len(suppressed),1)
                self.assertFalse(suppressed[0]['new_prompt_sent'])


if __name__=='__main__':unittest.main()
