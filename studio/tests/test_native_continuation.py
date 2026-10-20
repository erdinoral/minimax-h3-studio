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
        self.assertEqual(graph['n0_104']['inputs']['prompt'], '<Picture 1> rises')
        self.assertNotIn('n0_201', graph)
        self.assertEqual(graph['n1_104']['inputs']['prompt'], '<Picture 2> greets <Picture 1>')

    def test_missing_or_incompatible_state_fails_closed(self):
        job = self.job()
        parent = dict(id=SOURCE, status='done', width=864, height=480,
                      h3_models=DEFAULT_MODELS, continuation_state_key=SOURCE)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): native_continuation.prepare(job, parent, folder)
            path = native_continuation.state_path(folder, SOURCE)
            path.parent.mkdir(parents=True); path.touch()
            self.assertTrue(native_continuation.prepare(job, parent, folder))
            job['width'] = 1312
            with self.assertRaises(ValueError): native_continuation.prepare(job, parent, folder)
            job['width'] = 864
            job['h3_models'] = {**DEFAULT_MODELS, 'audio_vae': 'another.safetensors'}
            with self.assertRaises(ValueError): native_continuation.prepare(job, parent, folder)
            self.assertFalse(native_continuation.prepare(self.job(), {'id': 'legacy'}, folder))
        with self.assertRaises(ValueError): native_continuation.state_path('.', '../escape')
