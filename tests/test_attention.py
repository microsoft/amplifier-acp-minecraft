import unittest
from attention import fingerprint, ready
class AttentionTests(unittest.TestCase):
    def test_confidence_is_not_authority(self):
        self.assertFalse(ready({'answers':[{'name':'attention','choice':'ready','confidence':1}]}))
        self.assertFalse(ready({'answers':[{'name':'attention','choice':'ready','probabilities':{'ready':.4}}]}))
        self.assertTrue(ready({'answers':[{'name':'attention','choice':'ready','probabilities':{'ready':.9}}]}))
    def test_only_relevant_observations_change_signature(self):
        s={'username':'a','task':{'id':'one','wait_for':'wood'},'time':100,'events':[]}
        sig=fingerprint(s);s['time']=200;s['events']=[{'kind':'attention_wake'}]
        self.assertEqual(sig,fingerprint(s));s['inventory']=[{'name':'oak_log','count':1}]
        self.assertNotEqual(sig,fingerprint(s))
