import asyncio
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import server
from lib import cinema, continuum, h3_models, optional_models, h3_acceleration


class CancellationReliability(unittest.IsolatedAsyncioTestCase):
    async def test_retry_preserves_explicit_first_frame_and_clears_old_cancel_provenance(self):
        job = {'id':'retry','status':'cancelled','first_frame_name':'opening.png','cancel_requested_at':1,'cancel_source':'job_stop'}
        with patch.object(server, '_lock', asyncio.Lock()), patch.object(server, '_jobs', [job]), patch.object(server, '_save_jobs'), patch.object(server.comfy, 'healthy', new_callable=AsyncMock, return_value=True), patch.object(server, '_free_llm_for_production', new_callable=AsyncMock):
            result = await server.retry_job('retry')
        self.assertEqual(result['first_frame_name'],'opening.png')
        self.assertEqual(result['status'],'queued')
        self.assertNotIn('cancel_requested_at',result)

    async def test_retry_refreshes_last_frame_handoff_but_preserves_native_prefix_guide(self):
        for native_resume in [False,True]:
            job = {'id':'retry','status':'error','continue_from':'parent','continuum_resume':native_resume,'first_frame_name':'guide.png'}
            parent = {'id':'parent','status':'done'}
            with patch.object(server, '_lock', asyncio.Lock()), patch.object(server, '_jobs', [parent,job]), patch.object(server, '_save_jobs'), patch.object(server.comfy, 'healthy', new_callable=AsyncMock, return_value=True), patch.object(server, '_free_llm_for_production', new_callable=AsyncMock):
                result = await server.retry_job('retry')
            self.assertEqual(result['first_frame_name'],'guide.png' if native_resume else None)

    async def test_stop_keeps_queue_locked_and_does_not_cancel_completed_job(self):
        current = {'id': 'current', 'status': 'running'}
        next_job = {'id': 'next', 'status': 'queued'}
        async def finish_during_stop():
            self.assertTrue(server._lock.locked())
            current['status'] = 'done'
        with patch.object(server, '_lock', asyncio.Lock()), patch.object(server, '_jobs', [current, next_job]), patch.object(server, '_save_jobs'), patch.object(server.comfy, 'interrupt', side_effect=finish_during_stop):
            result = await server.interrupt()
        self.assertEqual(result['cancelled'], [])
        self.assertEqual(current['status'], 'done')
        self.assertEqual(next_job['status'], 'queued')

    async def test_single_stop_completion_wins_during_engine_request(self):
        current = {'id': 'current', 'status': 'running'}
        async def finish():
            self.assertTrue(server._lock.locked())
            current['status'] = 'done'
        with patch.object(server, '_lock', asyncio.Lock()), patch.object(server, '_jobs', [current]), patch.object(server, '_save_jobs'), patch.object(server.comfy, 'interrupt', side_effect=finish):
            result = await server.cancel_job('current')
        self.assertEqual(result['status'], 'done')
        self.assertNotIn('cancel_requested_at', current)

    async def test_stop_without_active_studio_job_does_not_interrupt_engine(self):
        pending = {'id': 'pending', 'status': 'queued'}
        with patch.object(server, '_lock', asyncio.Lock()), patch.object(server, '_jobs', [pending]), patch.object(server, '_save_jobs'), patch.object(server.comfy, 'interrupt', new_callable=AsyncMock) as stop:
            await server.interrupt(cancel_queued=True)
        stop.assert_not_awaited()
        self.assertEqual(pending['status'], 'cancelled')
        self.assertEqual(pending['cancel_source'], 'queue_stop')
        self.assertGreater(pending['cancel_requested_at'], 0)

    async def test_explicit_cancel_is_never_recovered(self):
        job = {'id': 'x', 'status': 'cancelled', 'prompt_id': 'p', 'cancel_requested_at': 1}
        with patch.object(server.comfy, 'history', new_callable=AsyncMock) as history:
            self.assertFalse(await server._reattach_completed_legacy_cancel(job))
        history.assert_not_awaited()

    async def test_legacy_cancel_requires_completed_success_and_video(self):
        for status, video in [({'completed': False, 'status_str': 'success'}, {'filename': 'x.mp4'}),
                              ({'completed': True, 'status_str': 'error'}, {'filename': 'x.mp4'}),
                              ({'completed': True, 'status_str': 'success'}, None)]:
            job = {'id': 'x', 'status': 'cancelled', 'prompt_id': 'p', 'error': 'old'}
            original = copy.deepcopy(job)
            with patch.object(server.comfy, 'history', new_callable=AsyncMock, return_value={'p': {'status': status, 'outputs': {}}}), patch.object(server.comfy, 'extract_video_meta', return_value=video):
                self.assertFalse(await server._reattach_completed_legacy_cancel(job))
            self.assertEqual(job, original)
        job = {'id': 'x', 'status': 'cancelled', 'prompt_id': 'p'}
        with patch.object(server.comfy, 'history', new_callable=AsyncMock, return_value={'p': {'status': {'completed': True, 'status_str': 'success'}, 'outputs': {}}}), patch.object(server.comfy, 'extract_video_meta', return_value={'filename': 'x.mp4'}):
            self.assertTrue(await server._reattach_completed_legacy_cancel(job))
        self.assertTrue(job['_reattach'])
        self.assertEqual(job['prompt_id'], 'p')
        self.assertEqual(job['status'], 'queued')  # download still needs to succeed

    async def test_failed_history_lookup_preserves_legacy_status(self):
        job = {'id': 'x', 'status': 'cancelled', 'prompt_id': 'p'}
        with patch.object(server.comfy, 'history', new_callable=AsyncMock, side_effect=OSError('offline')):
            self.assertFalse(await server._reattach_completed_legacy_cancel(job))
        self.assertEqual(job['status'], 'cancelled')

    async def test_pause_capability_does_not_claim_mid_render_resume(self):
        with patch.object(server, '_lock', asyncio.Lock()), patch.object(server, '_queue_paused', False):
            result = await server.pause_queue(server.QueuePauseBody(paused=True))
        self.assertTrue(result['after_current'])
        self.assertFalse(result['mid_render_pause'])


class ProductionContracts(unittest.TestCase):
    def test_spectrum_provenance_is_taken_from_submitted_graph_not_current_settings(self):
        graph = {'s': {'class_type': 'SpectrumApplyMiniMaxH3', 'inputs': {
            'enabled': True, 'blend_weight': .6, 'audio_blend_weight': 0., 'offline_smoothing_replay': True}}}
        with patch.object(h3_acceleration, 'load_settings', side_effect=AssertionError('must not read current settings')):
            recorded = h3_acceleration.graph_settings(graph)
            self.assertEqual(recorded['video_blend_weight'], .6)
            self.assertTrue(recorded['enabled'])
            self.assertEqual(h3_acceleration.graph_settings({}), {'enabled': False})

    def test_native_reference_slots_do_not_shift_with_chunk_subsets_or_first_frame(self):
        refs = ['lucifer.png', 'god.png', 'azrail.png']
        text = '<Picture 1> is Azrail. @R2 is Lucifer. <Picture 9> is unspecified.'
        mapped = continuum.align_reference_labels(text, ['azrail.png', 'lucifer.png'], refs)
        self.assertEqual(mapped, '@R3 is Azrail. @R1 is Lucifer. <Picture 9> is unspecified.')
        # Native @R3 remains slot 3 even when only slots 1 and 3 are active;
        # first-frame offset belongs to the native sampler, not this mapping.
        self.assertEqual(continuum.align_reference_labels('<Picture 1> waits.', ['azrail.png'], refs), '@R3 waits.')

    def test_reference_size_is_validated_and_explicit_identity_choice_is_preserved(self):
        self.assertEqual(server.CinemaProduceBody().continuum_reference_size, 'Match Output')
        self.assertEqual(server.CinemaProduceBody(continuum_reference_size='Max Identity').continuum_reference_size, 'Max Identity')
        with self.assertRaises(ValueError):
            server.CinemaProduceBody(continuum_reference_size='unknown')

    def test_duplicate_action_is_not_repeated_but_distinct_beats_are_kept(self):
        with patch('lib.skills.enrich_structured_from_look', side_effect=lambda s, _: s):
            prompt = cinema.compose_h3_prompt({'action': 'He walks to the arch.', 'beats': 'He walks to the arch.'})
            self.assertEqual(prompt.count('He walks to the arch.'), 1)
            prompt = cinema.compose_h3_prompt({'action': 'He walks to the arch.', 'beats': 'He stops before the door.'})
        self.assertIn('Chronological action beats: He stops before the door.', prompt)

    def test_nested_hybrid_uses_loader_relative_path_in_both_graphs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root/'diffusion_models'/'video'
            nested.mkdir(parents=True)
            filename = 'MiniMax-H3-Hybrid_b25-49_INT8.safetensors'
            (nested/filename).write_bytes(b'abc')
            with patch.object(optional_models, 'MODELS_ROOT', root), patch.object(optional_models, 'HYBRID_BYTES', 3), patch.object(h3_models, 'MODELS_ROOT', root), patch.object(h3_models, 'SETTINGS_PATH', root/'settings.json'):
                (root/'text_encoders').mkdir()
                (root/'text_encoders'/'encoder.safetensors').write_bytes(b'encoder')
                h3_models.save({'clip': 'encoder.safetensors'})
                result = optional_models.select_engine('hybrid')
                self.assertEqual(result['active'], 'hybrid')
                self.assertEqual(result['hybrid_file'], 'video/'+filename)
                self.assertEqual(h3_models.resolve('ref2va')['unet'], 'video/'+filename)
                self.assertEqual(h3_models.resolve('fl2va')['unet'], 'video/'+filename)
                self.assertEqual(h3_models.load()['clip'], 'encoder.safetensors')
                self.assertTrue(optional_models.supports_long_reference(30, 'ref', 'video/'+filename))

    def test_partial_hybrid_never_becomes_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'unet').mkdir()
            (root/'unet'/optional_models.HYBRID_FILE).write_bytes(b'ab')
            with patch.object(optional_models, 'MODELS_ROOT', root), patch.object(optional_models, 'HYBRID_BYTES', 3):
                self.assertIsNone(optional_models.hybrid_installed())
