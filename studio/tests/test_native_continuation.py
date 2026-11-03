import copy
import tempfile
import unittest
from unittest.mock import patch
from lib import native_continuation
from lib.comfy import DEFAULT_MODELS, build_t2v_prompt

SOURCE = '11111111-1111-1111-1111-111111111111'
CHILD = '22222222-2222-2222-2222-222222222222'


class NativeContinuation(unittest.TestCase):
    def job(self):
        return dict(id=CHILD, continuation_source_key=SOURCE, width=864, height=480,
                    duration=5, seed=42, steps=18, h3_models=DEFAULT_MODELS,
                    continuum_prompts=['The knight rises', 'The knight walks'], silent_audio=False)

    def test_capture_does_not_change_sampling_or_enable_refine(self):
        with patch('lib.comfy.apply_spectrum', side_effect=lambda g, **kw: g):
            graph = build_t2v_prompt(text='Knight', length=124)
        before = copy.deepcopy(graph)
        job = {'id': SOURCE}
        native_continuation.capture(graph, job, 124)
        for key in ('14', '16', '104', '15', '9'):
            self.assertEqual(graph[key], before[key])
        self.assertEqual(graph['10']['inputs']['samples'], ['studio_tail', 0])
        self.assertEqual(graph['23']['inputs']['samples'], ['studio_tail', 0])
        self.assertEqual(job['continuation_state_frames'], 39)
        self.assertNotIn('prepare_refine', job)

    def test_each_section_carries_native_state_and_trims_overlap(self):
        job = self.job()
        with patch('lib.comfy.apply_spectrum', side_effect=lambda g, **kw: g):
            graph = native_continuation.build(job)
        self.assertEqual(graph['n0_join']['inputs']['previous_state'], ['tail_load', 0])
        self.assertEqual(graph['n1_join']['inputs']['previous_state'], ['n0_finish', 2])
        self.assertEqual(graph['n0_104']['inputs']['length'], ['n0_window', 0])
        self.assertEqual(graph['n0_14']['inputs']['latent_image'], ['n0_join', 2])
        self.assertEqual(graph['n0_finish']['inputs']['plan'], ['n0_join', 3])
        self.assertEqual(graph['n1_append']['inputs']['previous'], ['n0_append', 0])
        self.assertEqual(job['continuity_method'], 'native_latent_tail')
        visited, active = set(), set()
        def visit(key):
            self.assertNotIn(key, active, 'Graph cycle')
            if key in visited: return
            active.add(key)
            for link in graph[key]['inputs'].values():
                if isinstance(link, list) and len(link) == 2 and isinstance(link[1], int):
                    self.assertIn(str(link[0]), graph)
                    visit(str(link[0]))
            active.remove(key); visited.add(key)
        visit('92')
        self.assertEqual(len(visited), len(graph))

    def test_references_are_scoped_per_section(self):
        job = self.job()
        job.update(ref_images=['knight.png', 'queen.png'],
                   continuum_ref_assignments={'knight.png': [1, 2], 'queen.png': [2]},
                   continuum_prompts=['@R1 rises', '@R2 greets @R1'])
        with patch('lib.comfy.apply_spectrum', side_effect=lambda g, **kw: g):
            graph = native_continuation.build(job)
        self.assertTrue(graph['n0_104']['inputs']['prompt'].endswith('\n\n<Picture 1> rises'))
        self.assertNotIn('n0_201', graph)
        self.assertTrue(graph['n1_104']['inputs']['prompt'].endswith('\n\n<Picture 2> greets <Picture 1>'))

    def test_reference_sections_forbid_pasting_reference_photographs(self):
        job = self.job()
        job.update(ref_images=['boy.png'], continuum_prompts=['The boy stays seated'])
        with patch('lib.comfy.apply_spectrum', side_effect=lambda g, **kw: g):
            graph = native_continuation.build(job)
        prompt = graph['n0_104']['inputs']['prompt']
        self.assertTrue(prompt.startswith('NATIVE CONTINUATION:'))
        self.assertIn('<Picture 1> is an appearance reference only, not filmed frames', prompt)
        self.assertIn('no floating heads', prompt)
        self.assertNotIn('NATIVE CONTINUATION:', native_continuation.build(self.job())['n0_104']['inputs']['prompt'])

    def test_missing_or_incompatible_state_fails_closed(self):
        job = self.job()
        parent = dict(id=SOURCE, status='done', width=864, height=480,
                      h3_models=DEFAULT_MODELS, continuation_state_key=SOURCE)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): native_continuation.prepare(job, parent, folder)
            path = native_continuation.state_path(folder, SOURCE)
            path.parent.mkdir(parents=True); path.touch()
            self.assertTrue(native_continuation.prepare(job, parent, folder))
            self.assertEqual(job['continuation_context_frames'], 39)
            job['width'] = 1312
            with self.assertRaises(ValueError): native_continuation.prepare(job, parent, folder)
            job['width'] = 864
            job['h3_models'] = {**DEFAULT_MODELS, 'audio_vae': 'another.safetensors'}
            with self.assertRaises(ValueError): native_continuation.prepare(job, parent, folder)
            self.assertFalse(native_continuation.prepare(self.job(), {'id': 'legacy'}, folder))
        with self.assertRaises(ValueError): native_continuation.state_path('.', '../escape')

    def test_asset_ownership_is_annotated_for_each_active_reference_order(self):
        job = self.job()
        job.update(ref_images=['spider.png', 'wolverine.png'],
                   reference_manifest=[
                       {'file': 'spider.png', 'asset': {'id': 's', 'name': 'Spider-Man', 'kind': 'character', 'notes': 'Red and gold suit.'}},
                       {'file': 'wolverine.png', 'asset': {'id': 'w', 'name': 'Wolverine', 'kind': 'character', 'notes': 'Yellow and blue suit.'}}],
                   continuum_ref_assignments={'spider.png': [1], 'wolverine.png': [1, 2]})
        with patch('lib.comfy.apply_spectrum', side_effect=lambda g, **kw: g):
            graph = native_continuation.build(job)
        first = graph['n0_104']['inputs']['prompt']
        second = graph['n1_104']['inputs']['prompt']
        self.assertIn('<Picture 1> is Spider-Man', first)
        self.assertIn('<Picture 2> is Wolverine', first)
        self.assertIn('Red and gold suit.', first)
        self.assertIn('<Picture 1> is Wolverine', second)
        self.assertNotIn('Spider-Man', second)
        self.assertNotIn('<Picture 2>', second)

    def test_continuation_uses_resolved_lora_weights_including_zero(self):
        job = self.job()
        job.update(lora_name='raw.safetensors', lora_strength=0.6,
                   lora_strengths={'raw.safetensors': 0.6},
                   effective_lora_name='approved.safetensors',
                   effective_lora_strength={'approved.safetensors': 0.0})
        with patch('lib.native_continuation.build_t2v_prompt', wraps=build_t2v_prompt) as builder, \
             patch('lib.comfy.apply_spectrum', side_effect=lambda g, **kw: g):
            native_continuation.build(job)
        for call in builder.call_args_list:
            self.assertEqual(call.kwargs['lora_name'], 'approved.safetensors')
            self.assertEqual(call.kwargs['lora_strength'], {'approved.safetensors': 0.0})
