import json
import unittest
from planner_prompt import planner_prompt, INSTRUCTIONS

class PlannerPrompt(unittest.TestCase):
    def test_fresh_authority_and_uncertain_evidence_are_not_rewritten_or_dropped(self):
        world={'task':{'id':'same','deadline':123,'max_turns':135,'turns':120},
               'receipts':[{'id':'unknown','confirmed':False}], 'conversation':{'revision':'fresh'}}
        messages=[{'id':'request','source':'human','text':'Accepted existing work'}]
        text=planner_prompt(messages,world,{'action':'hold'},[{'wake':True}])
        facts=json.loads(text[len(INSTRUCTIONS):])
        self.assertEqual(facts['world'],world);self.assertEqual(facts['messages'],messages)
        self.assertEqual(facts['attention_notifications'],[{'wake':True}])
        self.assertLess(len(INSTRUCTIONS.encode()),5200)
        self.assertNotIn('220 seconds',text)

    def test_chat_only_does_not_promise_capacity_retry(self):
        text=planner_prompt([],{'conversation_only':True,'incoming_chat_only':True,'task_capabilities':{'mode':'chat_only'}})
        self.assertIn('More capacity or repeating the request cannot clear',text)
        self.assertNotIn('a fresh request through ordinary capacity is needed',text)

    def test_intake_reply_exposes_only_metadata_transition_not_world_effects(self):
        text=planner_prompt([],{'conversation_only':True,'task_capabilities':{'mode':'human_requests','task_intake_enabled':True}})
        self.assertIn('world work waits for an ordinary admitted turn',text)
        self.assertIn('Do not claim acceptance',text)

    def test_capacity_reserve_guidance_differs_from_installation_mode(self):
        text=planner_prompt([],{'conversation_only':True,'incoming_chat_only':False})
        self.assertIn('temporary human-reply reserve',text)
        self.assertNotIn('Installation chat-only mode blocks',text)
