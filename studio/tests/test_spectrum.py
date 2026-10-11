import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.comfy import apply_sage_attention, apply_spectrum, build_t2v_prompt, build_ref2va_prompt, build_multishot_prompt


class SpectrumTests(unittest.TestCase):
    def test_disabled_missing_and_invalid_settings_leave_graph_unchanged(self):
        for value in ('{}', '{"spectrum_enabled": false}', 'null', 'broken', '{"spectrum_enabled": "true"}'):
            graph = {"6": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3.safetensors"}}}
            expected = copy.deepcopy(graph)
            with patch.object(Path, 'read_text', return_value=value):
                self.assertEqual(apply_sage_attention(graph), expected)
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError):
            self.assertEqual(apply_sage_attention({}), {})

    def test_all_native_builders_insert_one_patch_and_preserve_non_model_inputs(self):
        for builder, kwargs in ((build_t2v_prompt, {'text': 'test'}),
                                (build_ref2va_prompt, {'text': 'test', 'ref_image_names': ['portrait.png']})):
            with patch.object(Path, 'read_text', return_value='{}'):
                baseline = builder(**kwargs)
            with patch.object(Path, 'read_text', return_value='{"spectrum_enabled": true}'):
                accelerated = builder(**kwargs)
            nodes = [(key, node) for key, node in accelerated.items() if node['class_type'] == 'SpectrumApplyMiniMaxH3']
            self.assertEqual(len(nodes), 1)
            key, node = nodes[0]
            self.assertEqual(node['inputs']['audio_blend_weight'], 0.0)
            for old_key, old_node in baseline.items():
                current = copy.deepcopy(accelerated[old_key])
                if old_node['class_type'] in ('BasicGuider', 'BasicScheduler'):
                    self.assertEqual(current['inputs']['model'], [key, 0])
                    current['inputs']['model'] = old_node['inputs']['model']
                self.assertEqual(current, old_node)

    def test_multishot_custom_sampler_is_left_unchanged(self):
        with patch.object(Path, 'read_text', return_value='{}'):
            baseline = build_multishot_prompt(script='test')
        with patch.object(Path, 'read_text', return_value='{"spectrum_enabled": true}'):
            self.assertEqual(build_multishot_prompt(script='test'), baseline)

    def test_patch_follows_three_lora_chain(self):
        with patch.object(Path, 'read_text', return_value='{}'):
            graph = build_t2v_prompt(text='test', lora_name='a.safetensors|b.safetensors|c.safetensors')
        apply_spectrum(graph)
        node = next(n for n in graph.values() if n['class_type'] == 'SpectrumApplyMiniMaxH3')
        self.assertEqual(node['inputs']['model'], ['lora_stack_3', 0])

    def test_other_models_and_incomplete_graphs_are_unchanged(self):
        for graph in ({}, {'6': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'wan.safetensors'}}},
                      {'6': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'minimax_h3.safetensors'}}}):
            expected = copy.deepcopy(graph)
            self.assertEqual(apply_spectrum(graph), expected)
