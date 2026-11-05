import json
from pathlib import Path
import sys
import unittest

from acp_client import Client, ProtocolError


class Revisions(unittest.IsolatedAsyncioTestCase):
    async def result(self, mode, *, replay=False, observed=None, chunks=None, receipts=False):
        observed = observed if observed is not None else []
        client = Client({'command': [sys.executable, str(Path(__file__).with_name('output_fixture.py')), mode],
                         'cwd': '/tmp'}, lambda kind, **data: observed.append((kind, data)))
        try:
            await client.start()
            await client.open_session('output-test' if replay else None)
            async def on_chunk(text):
                if chunks is not None:
                    chunks.append(text)
            result = await client.prompt('Existing work', 5, on_chunk=on_chunk)
            if receipts:
                result['receipts'] = await client.request('_session/input_receipts', {'sessionId': client.session})
            return result
        finally:
            await client.close()

    async def test_latest_created_answer_wins_despite_interleaved_older_chunks_and_commentary(self):
        result = await self.result('revision')
        self.assertEqual(result['final_text'], 'Sticks already delivered.')
        self.assertIn('Need sticks.', result['text'])
        self.assertIn(' Please send some.', result['text'])

    async def test_empty_new_message_does_not_withdraw_latest_nonempty_answer(self):
        self.assertEqual((await self.result('empty'))['final_text'], 'Sticks already delivered.')

    async def test_nonempty_pass_revision_is_not_concatenated_with_old_speak_or_late_tail(self):
        result = await self.result('pass')
        self.assertEqual(json.loads(result['final_text']), {'decision': 'pass', 'reason': 'peer answered'})

    async def test_unidentified_acp_text_keeps_legacy_append_behavior(self):
        self.assertEqual((await self.result('legacy'))['final_text'], 'One plain answer.')

    async def test_unidentified_text_survives_tool_and_media_interleaving(self):
        result = await self.result('legacy_tools')
        self.assertEqual(result['final_text'], 'Before.\n\nAfter tools.')
        self.assertEqual(result['unsettled_tools'], [])

    async def test_message_identity_does_not_finish_tools_or_erase_text_with_media(self):
        observed = []
        result = await self.result('additive', observed=observed)
        self.assertEqual(result['final_text'], 'Current answer.')
        self.assertEqual(result['unsettled_tools'], ['inspect'])
        self.assertEqual(sum(kind == 'tool_update' for kind, _ in observed), 1)
        self.assertIn('Before.', result['text'])
        self.assertIn(' late tail.', result['text'])

    async def test_optional_phase_still_selects_by_first_observed_id(self):
        self.assertEqual((await self.result('optional_phase'))['final_text'], 'Current answer.')

    async def test_commentary_only_and_empty_final_have_no_answer(self):
        self.assertEqual((await self.result('commentary_only'))['final_text'], '')

    async def test_empty_envelope_does_not_reserve_message_order_before_real_text(self):
        self.assertEqual((await self.result('empty_first'))['final_text'], 'Late old text.')

    async def test_mixed_unidentified_old_tail_does_not_promote_it(self):
        self.assertEqual((await self.result('mixed'))['final_text'], 'Current.')

    async def test_unknown_optional_metadata_does_not_break_plain_acp(self):
        self.assertEqual((await self.result('metadata'))['final_text'], 'Current answer.')

    async def test_recognized_phase_change_does_not_change_message_order(self):
        self.assertEqual((await self.result('phase_change'))['final_text'], 'Current answer.')

    async def test_saved_replay_does_not_contaminate_next_prompt_with_same_ids(self):
        result = await self.result('revision', replay=True)
        self.assertEqual(result['final_text'], 'Sticks already delivered.')
        self.assertNotIn('Saved history.', result['text'])

    async def test_nonempty_message_id_count_is_bounded(self):
        with self.assertRaisesRegex(ProtocolError, 'message identity exceeds'):
            await self.result('identity_limit')

    async def test_receipt_without_id_does_not_reserve_legacy_answer_order(self):
        self.assertEqual((await self.result('receipt_before_legacy'))['final_text'], 'Current answer.')

    async def test_empty_receipt_or_old_chunk_preserves_latest_identified_answer(self):
        for mode in ('receipt_after_identified', 'empty_old_after_identified'):
            with self.subTest(mode=mode):
                chunks = []
                result = await self.result(mode, chunks=chunks)
                self.assertEqual(result['final_text'], 'Supplies received.')
                self.assertEqual(chunks, ['Need supplies.', 'Supplies received.'])

    async def test_receipt_after_tool_does_not_modify_selected_text(self):
        self.assertEqual((await self.result('receipt_after_tool'))['final_text'], 'Answer.')

    async def test_receipt_does_not_consume_legacy_tool_separator(self):
        self.assertEqual((await self.result('receipt_before_tail'))['final_text'], 'Before.\n\nAfter.')

    async def test_empty_envelope_does_not_change_existing_message_phase(self):
        self.assertEqual((await self.result('empty_phase'))['final_text'], 'Current.')

    async def test_empty_metadata_does_not_consume_assistant_message_count(self):
        self.assertEqual((await self.result('empty_flood'))['final_text'], 'Current.')

    async def test_receipt_only_turn_has_no_text_callbacks_but_receipts_are_retrievable(self):
        chunks = []
        result = await self.result('receipt_only', chunks=chunks, receipts=True)
        self.assertEqual(result['final_text'], '')
        self.assertEqual(result['text'], '')
        self.assertEqual(chunks, [])
        self.assertEqual(result['receipts']['inputReceipts'][0]['state'], 'incorporated')
        self.assertEqual(result['receipts']['inputReceipts'][0]['inputId'], 'source-update')
