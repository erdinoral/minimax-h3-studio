import copy
import ast
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lib import h3_enhancements as enhancements, loras
from lib.comfy import build_ref2va_prompt, build_t2v_prompt, add_h3_first_frame_guide


class Enhancements(unittest.TestCase):
    def test_erosmax_catalog_download_and_manual_steps(self):
        spec = loras.find_spec(lora_id='erosmax-beta1-fl2v-4step')
        self.assertIn('v1.0_768p_10ErosMax_beta1', spec['file'])
        self.assertEqual(spec['expected_bytes'], 1956194370)
        self.assertEqual(len(spec['sha256']), 64)
        self.assertTrue(spec['url'].startswith('https://huggingface.co/t8star/'))
        self.assertEqual(enhancements.preset(spec['file'], 4, 'euler', 'normal', 'fl2va'), (4, 'er_sde', 'simple'))
        self.assertEqual(enhancements.preset(spec['file'], 8, 'euler', 'normal', 'fl2va'), (8, 'er_sde', 'simple'))
        self.assertEqual(enhancements.preset(spec['file'], 20, 'euler', 'normal', 'ref2va'), (20, 'euler', 'normal'))

    def test_hyperflow_installer_digest_compatibility_and_idempotence(self):
        installer = Path(__file__).resolve().parents[1] / 'tools' / 'install_film_workflows.py'
        tree = ast.parse(installer.read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'patch_hyperflow_python310')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'custom_nodes/ComfyUI-HyperFlow-H3/hyperflow_h3/curve.py'
            target.parent.mkdir(parents=True)
            target.write_text('import hashlib\ndef check(handle):\n    return hashlib.file_digest(handle, "sha256").hexdigest()\n')
            namespace = {'APP': Path(directory)}
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(installer), 'exec'), namespace)
            namespace['patch_hyperflow_python310']()
            changed = target.read_text()
            namespace['patch_hyperflow_python310']()
            self.assertEqual(target.read_text(), changed)
            compat = {}
            exec(changed, compat)
            content = b'hyperflow' * 200000
            self.assertEqual(compat['check'](io.BytesIO(content)), hashlib.sha256(content).hexdigest())

    def test_installer_ships_hybrid_lora_loader_and_verified_grid(self):
        root = Path(__file__).resolve().parents[2]
        installer = root / 'studio' / 'tools' / 'install_film_workflows.py'
        tree = ast.parse(installer.read_text(encoding='utf-8'))
        constants = {t.id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                     for t in n.targets if isinstance(t, ast.Name) and t.id in ('WORKFLOW_PACKS', 'HYBRID_GRID')}
        docs = (root / 'docs' / 'hybrid-h3.md').read_text(encoding='utf-8')
        pack = next(p for p in constants['WORKFLOW_PACKS'] if p[0] == 'ComfyUI-H3-PowerLoraStack')
        self.assertIn(pack[2], docs)
        self.assertIn(constants['HYBRID_GRID'][3], docs)
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'install_hybrid_grid')
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / 'download.safetensors'
            namespace = {'APP': Path(directory), 'Path': Path, 'hashlib': hashlib,
                         'shutil': __import__('shutil'), 'HYBRID_GRID': ('repo', 'loras/grid.safetensors', 3, 'bad')}
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(installer), 'exec'), namespace)

            def download(*_args, **_kwargs):
                fake.write_bytes(b'abc')
                return str(fake)
            with patch('huggingface_hub.hf_hub_download', download):
                with self.assertRaisesRegex(RuntimeError, 'checksum'):
                    namespace['install_hybrid_grid']()
            self.assertFalse((Path(directory) / 'models/h3_adaln/grid.safetensors').exists())
            namespace['HYBRID_GRID'] = ('repo', 'loras/grid.safetensors', 3, hashlib.sha256(b'abc').hexdigest())
            with patch('huggingface_hub.hf_hub_download', download):
                namespace['install_hybrid_grid']()
            self.assertEqual((Path(directory) / 'models/h3_adaln/grid.safetensors').read_bytes(), b'abc')

    def test_setup_errors_tell_users_what_to_do(self):
        studio = Path(__file__).resolve().parents[1]
        node = (studio / 'comfy_nodes/h3_studio_enhancements/__init__.py').read_text(encoding='utf-8')
        self.assertIn('Run Update in Pinokio', node)
        server = (studio / 'server.py').read_text(encoding='utf-8')
        self.assertIn('rendered with Spectrum on', server)
        self.assertNotIn('older Continuum run used Spectrum', server)

    def test_refmod_replaces_encoder_and_rewires_conditioning_only(self):
        graph = build_ref2va_prompt(text='Actor walks', ref_image_names=['actor.png'], width=864, height=480,
                                   length=121, sage_attention='disabled')
        graph = add_h3_first_frame_guide(graph, 'last.png')
        snapshot = copy.deepcopy(graph)
        result = enhancements.patch_graph(graph, {'refmod_enabled': True})
        self.assertEqual(result['104']['class_type'], 'SkebaCachedMiniMaxH3ReferenceToVideo')
        self.assertEqual(result['104']['inputs']['ref_images.ref_image_0'], ['200', 0])
        self.assertEqual(result['14']['inputs']['latent_image'], snapshot['14']['inputs']['latent_image'])
        for nid, node in snapshot.items():
            for key, value in node.get('inputs', {}).items():
                if value == ['104', 0]:
                    self.assertEqual(result[nid]['inputs'][key], ['studio_refmods_104', 0])
        self.assertEqual(result['studio_refmods_104']['inputs']['conditioning'], ['104', 0])

    def test_disabled_and_asset_generation_graphs_are_unchanged(self):
        for job in [{'refmod_enabled': False}, {'refmod_enabled': True, 'sheet_job': True}]:
            graph = build_ref2va_prompt(text='Actor', ref_image_names=['actor.png'], width=864, height=480,
                                       length=121, sage_attention='disabled')
            snapshot = copy.deepcopy(graph)
            self.assertEqual(enhancements.patch_graph(graph, job), snapshot)

    def test_presets_apply_to_speed_adapter_even_after_character_adapter(self):
        speed = loras.find_spec(lora_id='lightx2v-fl2v-4step-v12')
        self.assertEqual(enhancements.preset('unknown-character.safetensors|' + speed['file'],
                                           20, 'res_multistep', 'simple', 'fl2va'), (4, 'er_sde', 'simple'))
        self.assertEqual(enhancements.preset(speed['file'], 20, 'res_multistep', 'simple', 'ref2va'),
                         (20, 'res_multistep', 'simple'))

    def test_speed_adapters_cannot_be_stacked(self):
        names = '|'.join(loras.find_spec(lora_id=id)['file'] for id in
                         ['lightx2v-fl2v-4step-v12', 'hyperflow-8step'])
        with self.assertRaisesRegex(ValueError, 'one speed'):
            enhancements.preset(names, 20, 'euler', 'simple', 'fl2va')

    def test_hyperflow_uses_patch_and_trained_sigmas_instead_of_plain_lora(self):
        spec = loras.find_spec(lora_id='hyperflow-8step')
        with patch('lib.comfy.apply_spectrum', side_effect=lambda g, **kwargs:g):
            graph = build_t2v_prompt(text='A cloud', width=864, height=480, length=121,
                                    lora_name=spec['file'], lora_strength=1.0, sage_attention='disabled')
        self.assertEqual(graph['7']['class_type'], 'ApplyHyperFlowH3')
        self.assertEqual(graph['14']['inputs']['sigmas'], ['7', 1])
        self.assertEqual(graph['17']['inputs']['sampler_name'], 'euler')
        self.assertEqual(graph['16']['inputs']['model'], ['7', 0])
        self.assertTrue(graph['7']['inputs']['experimental_curve_refit'])

    def test_settings_persist_and_missing_file_defaults_off(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(enhancements, 'STORE', Path(tmp)/'settings.json'):
            self.assertFalse(enhancements.settings()['refmod_enabled'])
            enhancements.save_settings(True)
            self.assertTrue(enhancements.settings()['refmod_enabled'])
            enhancements.save_settings(False)
            self.assertFalse(enhancements.settings()['refmod_enabled'])
