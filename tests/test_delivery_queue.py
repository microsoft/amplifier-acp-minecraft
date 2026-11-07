import unittest
from delivery_queue import select_turn_messages


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
