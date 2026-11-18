import unittest
from delivery_queue import select_turn_messages, attention_reply_messages, due_follow_up


class FollowUpDelivery(unittest.IsolatedAsyncioTestCase):
    async def test_due_reminder_uses_existing_admission_and_never_mixes_human_authority(self):
        follow = {'id':'self','source':'follow_up','reply_scope':'follow_up:self'}
        human = {'id':'human','source':'human'}
        self.assertEqual(select_turn_messages([follow,human]),[follow])
        self.assertEqual(attention_reply_messages([follow],[]),[])
        self.assertEqual(attention_reply_messages([follow],['self']),[follow])
        for case in ('due','human','quota','blocked','busy'):
            queued=[human] if case=='human' else []
            paths=[]
            async def request(path,payload=None):
                paths.append(path)
                if path=='/inbox/peek':return queued
                if path=='/conversation/admission':return {'remaining':0 if case=='quota' else 1,'eligible_ids':['self'] if case!='blocked' else []}
                if path=='/conversation/follow-up/poll':queued.append(follow);return {}
                self.fail(path)
            result=await due_follow_up(request,{'follow_up_pending':True,'busy':case=='busy'})
            self.assertEqual(result,[follow] if case=='due' else [],case)
            self.assertEqual(paths.count('/conversation/follow-up/poll'),int(case in ('due','blocked')),case)


class DeliveryQueueTests(unittest.TestCase):
    def test_distinct_offers_do_not_deadlock_or_share_a_turn(self):
        a = {'id': 'a', 'attention_offer': {'id': 'oa', 'ticket': 'ta'}}
        b = {'id': 'b', 'attention_offer': {'id': 'ob', 'ticket': 'tb'}}
        other = {'id': 'c', 'attention_offer': dict(a['attention_offer'])}
        messages = [a, b, other]
        self.assertEqual(select_turn_messages(messages), [a, other])
        self.assertEqual(messages, [a, b, other])
        self.assertEqual(select_turn_messages([b]), [b])

    def test_direct_inputs_do_not_strip_or_absorb_an_offer(self):
        human = {'id': 'human', 'source': 'human'}
        offer = {'id': 'peer', 'attention_offer': {'id': 'o', 'ticket': 't'}}
        self.assertEqual(select_turn_messages([human, offer]), [human])
        self.assertEqual(select_turn_messages([offer, human]), [offer])
        self.assertEqual(select_turn_messages([]), [])


    def test_late_optional_offer_is_separate_reply_not_work(self):
        offer={'id':'peer','source':'agent','attention_offer':{'id':'offer','ticket':'ticket'}}
        self.assertEqual(attention_reply_messages([offer],['peer']),[offer])
        self.assertEqual(attention_reply_messages([offer],[]),[])
        self.assertEqual(offer['attention_offer']['ticket'],'ticket')

    def test_grouped_offer_must_be_wholly_eligible(self):
        a={'id':'a','attention_offer':{'id':'o','ticket':'t'}}
        b={'id':'b','attention_offer':dict(a['attention_offer'])}
        self.assertEqual(attention_reply_messages([a,b],['a']),[])
        self.assertEqual(attention_reply_messages([a,b],['a','b']),[a,b])
        self.assertIsNone(attention_reply_messages([{'id':'human','source':'human'}],[]))

class PrivateSourceQueue(unittest.TestCase):
    def test_distinct_private_sources_and_public_inputs_keep_original_separate_admissions(self):
        first={'id':'a','source':'human','reply_scope':'installation:a'}
        second={'id':'b','source':'human','reply_scope':'installation:b'}
        public={'id':'c','source':'human'}
        messages=[first,second,public]
        self.assertEqual(select_turn_messages(messages),[first])
        self.assertEqual(select_turn_messages([public,first,second]),[public])
        self.assertEqual(messages,[first,second,public])
