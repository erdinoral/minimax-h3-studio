import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import h3_enhancements, h3_models, flow_refine


class OptionalExtrasTests(unittest.TestCase):
    def test_flow_bypasses_spectrum_without_dropping_lora_or_changing_ordinary_graph(self):
        original = {
            'lora': {'class_type':'LoraLoaderModelOnly','inputs':{'model':['base',0]}},
            'spectrum': {'class_type':'SpectrumApplyMiniMaxH3','inputs':{'model':['lora',0]}},
            '16': {'class_type':'BasicGuider','inputs':{'model':['spectrum',0]}},
            '9': {'class_type':'BasicScheduler','inputs':{'model':['spectrum',0]}},
        }
        graph = flow_refine.without_spectrum(copy.deepcopy(original))
        self.assertNotIn('spectrum', graph)
        self.assertEqual(graph['16']['inputs']['model'], ['lora',0])
        self.assertEqual(graph['9']['inputs']['model'], ['lora',0])
        self.assertIn('spectrum', original)

    def graph(self):
        return {
            'encode': {'class_type': 'MiniMaxH3ReferenceToVideo', 'inputs': {'vae': ['base', 0]}},
            'decode': {'class_type': 'VAEDecode', 'inputs': {'vae': ['base', 0]}},
            'audio': {'class_type': 'VAEDecodeAudio', 'inputs': {'vae': ['audio_vae', 0]}},
            'tiny': {'class_type': 'H3TAEDecode', 'inputs': {'tae_name': 'tiny'}},
        }

    def test_decoder_changes_video_decode_only(self):
        graph = self.graph()
        h3_enhancements.patch_graph(graph, {'h3_models': {'video_decoder': 'lightvae.safetensors'}})
        self.assertEqual(graph['decode']['inputs']['vae'], ['studio_video_decoder', 0])
        self.assertEqual(graph['encode']['inputs']['vae'], ['base', 0])
        self.assertEqual(graph['audio']['inputs']['vae'], ['audio_vae', 0])
        self.assertEqual(graph['tiny']['inputs']['tae_name'], 'tiny')

    def test_default_graph_is_identical(self):
        graph = self.graph()
        before = copy.deepcopy(graph)
        self.assertEqual(h3_enhancements.patch_graph(graph, {}), before)

    def test_minimax_asset_sheet_forces_full_spectrum_per_job(self):
        graph = {
            'unet': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'minimax_h3_test.safetensors'}},
            'guider': {'class_type': 'BasicGuider', 'inputs': {'model': ['unet', 0]}},
            'scheduler': {'class_type': 'BasicScheduler', 'inputs': {'model': ['unet', 0]}},
        }
        h3_enhancements.patch_graph(graph, {'sheet_job': True, 'sheet_spectrum_full': True})
        spectrum = next(node for node in graph.values() if node['class_type'] == 'SpectrumApplyMiniMaxH3')
        self.assertIs(spectrum['inputs']['enabled'], True)
        self.assertEqual(spectrum['inputs']['blend_weight'], 1.0)

    def test_minimax_asset_override_updates_existing_spectrum_without_adding_another(self):
        graph = {
            'unet': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'minimax_h3_test.safetensors'}},
            'spectrum': {'class_type': 'SpectrumApplyMiniMaxH3', 'inputs': {'model': ['unet', 0], 'enabled': True, 'blend_weight': 0.75}},
            'guider': {'class_type': 'BasicGuider', 'inputs': {'model': ['spectrum', 0]}},
            'scheduler': {'class_type': 'BasicScheduler', 'inputs': {'model': ['spectrum', 0]}},
        }
        h3_enhancements.patch_graph(graph, {'sheet_job': True, 'sheet_spectrum_full': True})
        spectrum_nodes = [node for node in graph.values() if node['class_type'] == 'SpectrumApplyMiniMaxH3']
        self.assertEqual(len(spectrum_nodes), 1)
        self.assertEqual(spectrum_nodes[0]['inputs']['blend_weight'], 1.0)

    def test_decoder_is_recorded_separately_from_encoder(self):
        with patch.object(h3_models, 'load', return_value={'video_decoder': 'lightvae.safetensors'}):
            for mode in ('fl2va', 'ref2va'):
                models = h3_models.resolve(mode)
                self.assertEqual(models['vae'], h3_models.DEFAULT_MODELS['vae'])
                self.assertEqual(models['video_decoder'], 'lightvae.safetensors')

    def test_continuum_final_decode_uses_light_decoder_without_changing_context(self):
        graph = {
            'c_sample': {'class_type': 'H3ContinuumSampler', 'inputs': {'video_vae': ['base', 0]}},
            'c_video': {'class_type': 'VAEDecode', 'inputs': {'vae': ['base', 0]}},
        }
        h3_enhancements.patch_graph(graph, {'h3_models': {'video_decoder': 'lightvae.safetensors'}})
        self.assertEqual(graph['c_sample']['inputs']['video_vae'], ['base', 0])
        self.assertEqual(graph['c_video']['inputs']['vae'], ['studio_video_decoder', 0])

    def test_decoder_catalog_excludes_audio_and_encoder_only_weights(self):
        with patch.object(h3_models, '_list_dir', return_value=[
            'minimax_h3_audio_vae.safetensors', 'minimax_h3_lightvae_encoder.safetensors',
            'minimax_h3_lightvae_lite_vae.safetensors', 'qwen_image_vae.safetensors']):
            self.assertEqual(h3_models.list_catalog()['options']['video_decoder'],
                             ['minimax_h3_lightvae_lite_vae.safetensors'])


if __name__ == '__main__':
    unittest.main()
