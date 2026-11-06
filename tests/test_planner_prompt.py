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
