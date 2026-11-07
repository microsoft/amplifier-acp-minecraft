"""Exercise final delivery through the controller with no provider or world."""
import asyncio
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import adapter


class SilentFinalTurn(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, *, human=False, changed=None, useful=False):
        paths=[]
        active=False
        message={'id':'source', 'source':'human' if human else 'agent', 'message':'A fresh observation.'}
        text='The barrel is ready.' if useful else 'No response needed — that update is directed at another player.'
        conversation={'revision':'original', 'messages':[]}
        world={'ready':True, 'busy':False, 'generation':1, 'task':None,
               'conversation_only':True, 'peer_proposal':not human, 'conversation':conversation}

        def control(cfg,path,payload=None):
            nonlocal active
            paths.append((path,payload))
            if path in ('/state','/observation'):
                return {**world,'turn_active':active,'pending_messages':1}
            if path=='/conversation/admission':
                return {'version':1,'unmetered':True,'eligible_ids':['source']}
            if path=='/inbox/peek':return [message]
            if path=='/turn':
                self.assertTrue(payload['conversation_only'])
                self.assertEqual(payload['peer_only'],not human)
                active=True
                return {'active':True}
            if path=='/status':return {**world,'turn_active':active}
            if path=='/conversation':return conversation
            if path=='/operator-inputs':return {'revision':'operator-original','messages':[]}
            if path=='/finish':raise asyncio.CancelledError()
            if path in ('/recover','/inbox/retire-expired','/reply'):return {}
            raise AssertionError(path)

        class Client:
            info={'agentCapabilities':{'mcpCapabilities':{'http':True}}}
            session='saved'
            lifecycle=None
            async def start(self):pass
            async def open_session(self,previous):outer.assertEqual(previous,'saved')
            def transport_closed(self):return False
            async def close(self):pass
            async def prompt(self,*args,**kwargs):
                return {'text':text,'final_text':text,'stop_reason':'end_turn','unsettled_tools':[]}

        class Awareness:
            def __init__(self,home,client,initial,observe,*,audience='public'):
                self.initial_revision=initial['revision']
                self.cursor='new-input' if changed==audience else self.initial_revision
            async def finish(self):pass
            def final_revision(self,snapshot):return snapshot['revision']

        outer=self
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            cfg={'control_port':1,'token':'fixture','incoming_chat_only':True,
                 'human_task_intake':{'enabled':True,'delegation':{'enabled':True}}}
            endpoint={'command':['unused'],'cwd':tmp}
            bound={**endpoint,'mcp_servers':[{'type':'http','name':'minecraft','url':'http://127.0.0.1:1/mcp',
                   'headers':[{'name':'Authorization','value':'Bearer fixture'}]}]}
            binding=hashlib.sha256(json.dumps(bound,sort_keys=True).encode()).hexdigest()
            for name,value in [('config',cfg),('endpoint',endpoint),('calls',[]),
                               ('session',{'binding':binding,'session':'saved'})]:
                (home/(name+'.json')).write_text(json.dumps(value))
            output=io.StringIO()
            with patch.object(adapter,'control',control),patch.object(adapter,'Client',lambda *a:Client()),\
                 patch.object(adapter,'Awareness',Awareness),contextlib.redirect_stdout(output):
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(adapter.run(home),2)
            self.assertEqual(json.loads((home/'calls.json').read_text()),[])
            self.assertEqual(len(json.loads((home/'reply-calls.json').read_text())),1)
            self.assertEqual(json.loads((home/'session.json').read_text()),{'binding':binding,'session':'saved'})
        events=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(next(e for e in events if e['kind']=='turn_completed')['disposition'],'complete')
        self.assertEqual([p for p in paths if p[0]=='/finish'],[('/finish',{'error':False,'budget_limited':False})])
        self.assertFalse(any(p in ('/wake','/turn/renew','/task') for p,_ in paths))
        return [payload['text'] for path,payload in paths if path=='/reply'],events

    async def test_silent_peer_finishes_normally_without_public_reply(self):
        replies,events=await self.exercise()
        self.assertEqual(replies,[])
        self.assertTrue(any(e.get('reason')=='explicit_no_reply_final' for e in events))

    async def test_direct_human_and_fresh_steering_answers_remain_deliverable(self):
        for kwargs in ({'human':True},{'changed':'public'},{'changed':'operator'},{'useful':True}):
            with self.subTest(kwargs=kwargs):
                replies,events=await self.exercise(**kwargs)
                self.assertEqual(len(replies),1)
                self.assertFalse(any(e.get('reason')=='explicit_no_reply_final' for e in events))


if __name__=='__main__':unittest.main()
