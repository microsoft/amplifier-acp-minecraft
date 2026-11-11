import json
import copy
import unittest
from planner_prompt import planner_prompt, working_world, INSTRUCTIONS

class PlannerPrompt(unittest.TestCase):
    def test_fresh_authority_and_uncertain_evidence_are_not_rewritten_or_dropped(self):
        world={'task':{'id':'same','deadline':123,'max_turns':135,'turns':120},
               'receipts':[{'id':'unknown','confirmed':False}], 'conversation':{'revision':'fresh'}}
        messages=[{'id':'request','source':'human','text':'Accepted existing work'}]
        text=planner_prompt(messages,world,{'action':'hold'},[{'wake':True}])
        facts=json.loads(text[len(INSTRUCTIONS):])
        self.assertEqual(facts['world'],world);self.assertEqual(facts['messages'],messages)
        self.assertEqual(facts['attention_notifications'],[{'wake':True}])
        self.assertLess(len(INSTRUCTIONS.encode()),5600)
        self.assertNotIn('220 seconds',text)

    def test_chat_only_does_not_promise_capacity_retry(self):
        text=planner_prompt([],{'conversation_only':True,'incoming_chat_only':True,'task_capabilities':{'mode':'chat_only'}})
        self.assertIn('More capacity or repeating the request cannot clear',text)
        self.assertNotIn('a fresh request through ordinary capacity is needed',text)

    def test_intake_reply_exposes_only_metadata_transition_not_world_effects(self):
        text=planner_prompt([],{'conversation_only':True,'task_capabilities':{'mode':'human_requests','task_intake_enabled':True}})
        self.assertIn('world work follows after this reply',text)
        self.assertIn('Do not claim acceptance',text)

    def test_capacity_reserve_guidance_differs_from_installation_mode(self):
        text=planner_prompt([],{'conversation_only':True,'incoming_chat_only':False})
        self.assertIn('temporary human-reply reserve',text)
        self.assertNotIn('Installation chat-only mode blocks',text)

    def test_peer_proposal_preserves_own_admission_and_original_human_evidence(self):
        text=planner_prompt([{'id':'peer','source':'agent'}],{'conversation_only':True,'peer_proposal':True,'task_capabilities':{'task_intake_enabled':True}})
        self.assertIn('PEER MESSAGE',text)
        self.assertIn('not a human command or a requirement to accept work',text)
        self.assertIn('original locally observed delegation_sources',text)
        self.assertIn('A copied quote from the peer is insufficient',text)
        self.assertIn('No physical effects until a subsequent authorized work turn',text)
        self.assertNotIn('CONVERSATION-ONLY TURN: Reply to fresh human input',text)

class ExistingWorkPrompt(unittest.TestCase):
    def test_existing_authority_does_not_instruct_the_agent_to_refuse_movement(self):
        text=planner_prompt([],{'conversation_only':True,'reply_work_allowed':True})
        self.assertIn('including movement',text)
        self.assertNotIn('No movement, building',text)
        self.assertIn('no new scope or limits',text)

class TaskOptionalPrompt(unittest.TestCase):
    def test_task_optional_prompt_does_not_restore_task_gate_and_fresh_input_is_first(self):
        messages=[{'id':'current','source':'human','message':'Help with the path'}]
        world={'conversation_only':True,'peer_proposal':True,'task_capabilities':{'task_optional':True},'task':{'status':'blocked'}}
        text=planner_prompt(messages,world)
        self.assertIn('without a task record',text)
        self.assertNotIn('Only a human request authorizes continuing work',text)
        self.assertNotIn('No physical effects until a subsequent authorized work turn',text)
        self.assertLess(text.index('"messages":'),text.index('"world":'))

class CurrentInputProjection(unittest.TestCase):
    def fixture(self):
        source={'revision':'original','actor':{'id':'human'},'audience':{'id':'private'},'occurred_at':'original-time'}
        message={'id':'current','username':'Companion','source':'human','message':'Walk from the current position',
                 'reply_scope':'installation:current','installation_source':source}
        event={**message,'kind':'chat','time':'original-time','received_at':'received-time','provenance':'operator_control','accepted':True}
        world={'events':[{'kind':'chat','id':'old','message':'Old unfinished obligation','time':'old-time'},event,
                         {'kind':'action_failed','id':'unknown','operation_settled':False}],
               'task':{'id':'expired','deadline':1,'turns':8},'receipts':[{'unknown':True}]}
        return [message],world

    def test_only_exact_current_text_is_referenced_and_sources_are_not_mutated(self):
        messages,world=self.fixture();before=copy.deepcopy([messages,world]);view=working_world(messages,world)
        self.assertEqual([messages,world],before)
        self.assertEqual(view['events'][0],world['events'][0]);self.assertEqual(view['events'][2],world['events'][2])
        self.assertEqual(view['task'],world['task']);self.assertEqual(view['receipts'],world['receipts'])
        self.assertNotIn('message',view['events'][1]);self.assertEqual(view['events'][1]['admitted_message_id'],'current')
        self.assertEqual(view['events'][1]['installation_source'],world['events'][1]['installation_source'])
        self.assertEqual(view['events'][1]['time'],'original-time');self.assertEqual(view['events'][1]['received_at'],'received-time')
        facts=json.loads(planner_prompt(messages,world)[len(INSTRUCTIONS):]);self.assertEqual(list(facts)[0],'messages')
        self.assertEqual(facts['messages'],messages)

    def test_changed_or_ambiguous_identity_keeps_the_complete_event(self):
        for changed in ['text','revision','audience','actor','time','author','source','scope','id','duplicate','missing_source']:
            with self.subTest(changed=changed):
                messages,world=self.fixture();messages=copy.deepcopy(messages)
                if changed=='text': messages[0]['message']='Different request'
                elif changed in ['revision','audience','actor','time']:
                    key={'time':'occurred_at'}.get(changed,changed);messages[0]['installation_source'][key]='different'
                elif changed=='author': messages[0]['username']='Other'
                elif changed=='source': messages[0]['source']='agent'
                elif changed=='scope': messages[0]['reply_scope']='game'
                elif changed=='id': messages[0]['id']='other'
                elif changed=='duplicate': messages.append(copy.deepcopy(messages[0]))
                elif changed=='missing_source': messages[0].pop('installation_source')
                self.assertEqual(working_world(messages,world),world)
