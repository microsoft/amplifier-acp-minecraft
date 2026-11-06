import asyncio
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from adapter import minecraft_reply_lines, deliver_final_reply


class ChatDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def test_packetization_prefers_complete_sentences_without_dropping_text(self):
        text='First complete thought. A second sentence needs another packet.'
        lines,shortened=minecraft_reply_lines(text,width=40)
        self.assertEqual(lines[0],'First complete thought.')
        self.assertEqual(' '.join(lines),text)
        self.assertFalse(shortened)

    def test_tour_keeps_ending_limitations_after_three_chunks(self):
        text=('Visit the market, inn, garden and dock. '*29+
              'Important: one loaf only. The vessel is a display; the chime sound is unverified.')
        lines,shortened=minecraft_reply_lines(text)
        self.assertGreater(len(lines),3)
        self.assertLessEqual(len(lines),8)
        self.assertFalse(shortened)
        self.assertEqual(' '.join(lines),text)
        self.assertTrue(lines[-1].endswith('chime sound is unverified.'))

    def test_bounded_long_reply_has_visible_shortening_notice(self):
        lines,shortened=minecraft_reply_lines('Route and caveat. '*500)
        self.assertTrue(shortened)
        self.assertEqual(len(lines),8)
        self.assertTrue(lines[-1].endswith('[Message shortened.]'))
        self.assertTrue(all(len(x.encode('utf-16-le'))//2<=230 for x in lines))

    def test_non_bmp_characters_fit_body_length_validation(self):
        text='🌾'*150+' ready'
        lines,shortened=minecraft_reply_lines(text)
        self.assertFalse(shortened)
        self.assertTrue(all(len(x.encode('utf-16-le'))//2<=230 for x in lines))
        self.assertEqual(''.join(lines).replace(' ',''),text.replace(' ',''))

    async def test_delivery_sends_complete_tour_with_pacing(self):
        text='Inspect the inn and check the pantry. '*30+'One loaf, not a full larder.'
        sent=[];events=[];delays=[]
        async def request(path,payload):
            self.assertEqual(path,'/reply');self.assertEqual(payload['conversation_revision'],'known')
            sent.append(payload['text']);return {'sent':payload['text']}
        async def sleep(delay):delays.append(delay)
        await deliver_final_reply(text,'known',request,lambda k,**d:events.append((k,d)),sleep=sleep)
        self.assertEqual(' '.join(sent),text)
        self.assertEqual(delays,[.8]*(len(sent)-1))
        self.assertTrue(events[-1][1]['all_chunks_sent'])

    async def test_new_context_stops_unsent_tail_without_retry(self):
        calls=[];events=[]
        async def request(path,payload):
            calls.append(payload);return {'sent':len(calls)==1}
        async def sleep(delay):pass
        await deliver_final_reply('PRIVATE_PAYLOAD '*90,'old',request,lambda k,**d:events.append((k,d)),sleep=sleep)
        self.assertEqual(len(calls),2)
        self.assertEqual(events[-1][1]['sent_chunks'],1)
        self.assertFalse(events[-1][1]['all_chunks_sent'])
        self.assertNotIn('PRIVATE_PAYLOAD',repr(events))

    async def test_lost_reply_is_not_replayed(self):
        calls=[]
        async def request(path,payload):
            calls.append(payload);raise ConnectionError('reply lost after acceptance')
        with self.assertRaises(ConnectionError):
            await deliver_final_reply('Ready to visit.','known',request,lambda *a,**k:None)
        self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
