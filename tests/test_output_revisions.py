import json
from pathlib import Path
import sys
import unittest

from acp_client import Client, ProtocolError


class Revisions(unittest.IsolatedAsyncioTestCase):
    async def result(self, mode, *, replay=False, observed=None):
        observed = observed if observed is not None else []
        client = Client({'command': [sys.executable, str(Path(__file__).with_name('output_fixture.py')), mode],
                         'cwd': '/tmp'}, lambda kind, **data: observed.append((kind, data)))
        try:
            await client.start()
            await client.open_session('output-test' if replay else None)
            return await client.prompt('Existing work', 5)
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

    async def test_late_content_for_initially_empty_older_id_does_not_promote_it(self):
        self.assertEqual((await self.result('empty_first'))['final_text'], 'Current.')

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

    async def test_empty_message_ids_are_bounded_even_without_text(self):
        with self.assertRaisesRegex(ProtocolError, 'message identity exceeds'):
            await self.result('identity_limit')
