import unittest
from delivery_queue import select_turn_messages, attention_reply_messages


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
