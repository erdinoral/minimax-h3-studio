import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from lib import local_quality, native_continuation, h3_acceleration, continuum
from lib.comfy import build_t2v_prompt, build_ref2va_prompt


class LocalQualityTest(unittest.TestCase):
    def job(self, **changes):
        return dict(id='test', width=1920, height=1088, seed=11, steps=20,
                    scheduler='simple', local_quality_version=1, **changes)

    def assert_acyclic(self, graph):
        visited, active = set(), set()

        def walk(key):
            self.assertNotIn(key, active)
            if key in visited:
                return
            active.add(key)
            for value in graph[key].get('inputs', {}).values():
                if isinstance(value, list) and len(value) == 2 and value[0] in graph:
                    walk(value[0])
            active.remove(key)
            visited.add(key)

        for key in graph:
            walk(key)

    def test_native_t2v_and_ref_keep_references_audio_and_final_size(self):
        for builder, args in ((build_t2v_prompt, {}),
                              (build_ref2va_prompt, dict(ref_image_names=['person.png']))):
            graph = builder(text='Original brief', width=1920, height=1088, **args)
            refs = copy.deepcopy(graph['104']['inputs'])
            job = self.job()
            with patch.object(Path, 'is_file', return_value=True):
                local_quality.apply(graph, job)
            self.assertEqual(graph['104']['inputs']['height'], 768)
            for key, value in refs.items():
                if key not in ('width', 'height'):
                    self.assertEqual(graph['104']['inputs'][key], value)
            refine = graph['studio_quality_refine']['inputs']
            self.assertEqual((refine['width'], refine['height']), (1920, 1088))
            self.assertTrue(refine['lock_audio'])
            self.assertTrue(refine['offload_after_upscale'])
            self.assertEqual(graph['10']['class_type'], 'VAEDecodeTiled')
            self.assertEqual(graph['23']['class_type'], 'VAEDecodeAudio')
            self.assert_acyclic(graph)

    def test_saved_tail_uses_refined_output_without_dependency_cycle(self):
        graph = build_t2v_prompt(text='Original brief')
        with patch.object(Path, 'is_file', return_value=True):
            local_quality.apply(graph, self.job())
        native_continuation.capture(graph, self.job(), 124)
        self.assertEqual(graph['studio_tail']['inputs']['samples'], ['studio_quality_refine', 0])
        self.assertEqual(graph['10']['inputs']['samples'], ['studio_tail', 0])
        self.assertEqual(graph['studio_quality_refine']['inputs']['latent'], ['14', 0])
        self.assert_acyclic(graph)

    def test_portrait_and_2k_targets_keep_requested_dimensions(self):
        for width, height in ((1088, 1920), (2048, 1152)):
            job = self.job()
            job.update(width=width, height=height)
            graph = build_t2v_prompt(text='Scene', width=width, height=height)
            with patch.object(Path, 'is_file', return_value=True):
                local_quality.apply(graph, job)
            refine = graph['studio_quality_refine']['inputs']
            self.assertEqual((refine['width'], refine['height']), (width, height))
            base = graph['104']['inputs']
            self.assertEqual(min(base['width'], base['height']), 768)
            self.assertEqual((job['width'], job['height']), (width, height))

    def test_continuum_keeps_context_audio_and_updates_assembly_plan(self):
        job = self.job(prompt='Scene', continuum_prompts=['One', 'Two'],
                       continuum_chunk_seconds=5, duration=5, continuum_run='test', h3_models={})
        graph = continuum.build(job)
        with patch.object(Path, 'is_file', return_value=True):
            local_quality.apply(graph, job)
        self.assertEqual(graph['c_sample']['inputs']['height'], 768)
        refine = graph['studio_quality_refine']['inputs']
        self.assertEqual(refine['refine_context'], ['c_sample', 5])
        self.assertEqual(refine['audio_latents'], ['c_sample', 1])
        self.assertEqual(graph['c_finish']['inputs']['assembly_plan'], ['studio_quality_refine', 2])
        self.assertEqual(graph['c_audio']['inputs']['samples'], ['studio_quality_refine', 1])
        self.assert_acyclic(graph)

    def test_legacy_draft_native_tail_and_custom_sampler_are_not_replanned(self):
        for changes in ({'local_quality_version': None}, {'fast_preview': True},
                        {'sheet_job': True}, {'height': 736}, {'continuation_source_key': 'tail'}):
            job = self.job()
            job.update(changes)
            graph = build_t2v_prompt(text='Scene')
            original = copy.deepcopy(graph)
            self.assertEqual(local_quality.apply(graph, job), original)
        graph = {'x': {'class_type': 'CustomSampler', 'inputs': {}}}
        self.assertEqual(local_quality.apply(copy.deepcopy(graph), self.job()), graph)

    def test_missing_model_fails_before_changing_graph_and_repeated_apply_is_safe(self):
        graph = build_t2v_prompt(text='Scene')
        original = copy.deepcopy(graph)
        with patch.object(Path, 'is_file', return_value=False):
            with self.assertRaisesRegex(RuntimeError, '3D latent upscaler'):
                local_quality.apply(graph, self.job())
        self.assertEqual(graph, original)
        with patch.object(Path, 'is_file', return_value=True):
            local_quality.apply(graph, self.job())
            original = copy.deepcopy(graph)
            self.assertEqual(local_quality.apply(graph, self.job()), original)

    def test_sparse_metadata_does_not_claim_unmeasured_execution(self):
        graph = build_t2v_prompt(text='Scene')
        report = h3_acceleration.sparse_graph_settings(graph)
        self.assertFalse(report['runtime_verified'])
        if report['configured']:
            self.assertTrue(report['diagnostics'])


if __name__ == '__main__':
    unittest.main()
