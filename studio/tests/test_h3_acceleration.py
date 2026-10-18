import ast
import asyncio
import math
import tempfile
import sys
import unittest
from pathlib import Path
from typing import Optional, Literal
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError
from lib import h3_acceleration
from lib.comfy import build_t2v_prompt


class AccelerationSettingsTests(unittest.TestCase):
    def test_legacy_file_keeps_the_existing_default(self):
        self.assertEqual(h3_acceleration.clean_settings({'spectrum_enabled': True}),
                         dict(spectrum_enabled=True, spectrum_preset='balanced', spectrum_blend_weight=0.5))

    def test_presets_manual_values_and_toggle_preserve_each_other(self):
        settings = h3_acceleration.update_settings({}, {'spectrum_enabled': True, 'spectrum_preset': 'strong'})
        self.assertEqual(settings['spectrum_blend_weight'], 0.75)
        settings = h3_acceleration.update_settings(settings, {'spectrum_blend_weight': 0.37})
        self.assertEqual(settings['spectrum_preset'], 'custom')
        settings = h3_acceleration.update_settings(settings, {'spectrum_enabled': False})
        self.assertEqual(settings['spectrum_blend_weight'], 0.37)
        settings = h3_acceleration.update_settings(settings, {'spectrum_preset': 'light'})
        self.assertEqual(settings['spectrum_blend_weight'], 0.25)
        self.assertFalse(settings['spectrum_enabled'])

    def test_invalid_persisted_weights_use_a_finite_default(self):
        for value in (-1, 2, math.inf, math.nan, None, True, 'bad'):
            with self.subTest(value=value):
                settings = h3_acceleration.clean_settings({'spectrum_enabled': True, 'spectrum_blend_weight': value})
                self.assertEqual(settings['spectrum_blend_weight'], 0.5)

    def test_disk_roundtrip_and_malformed_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'settings.json'
            h3_acceleration.save_settings(dict(spectrum_enabled=True, spectrum_preset='custom', spectrum_blend_weight=0), path)
            self.assertEqual(h3_acceleration.load_settings(path)['spectrum_blend_weight'], 0)
            path.write_text('null', encoding='utf8')
            self.assertFalse(h3_acceleration.load_settings(path)['spectrum_enabled'])

    def test_custom_weight_reaches_the_native_graph_without_changing_audio_or_schedule(self):
        for weight in (0, 0.37, 1):
            with patch.object(Path, 'read_text', return_value='{"spectrum_enabled":true,"spectrum_blend_weight":%s}' % weight):
                graph = build_t2v_prompt(text='test')
            node = next(n for n in graph.values() if n['class_type'] == 'SpectrumApplyMiniMaxH3')
            self.assertEqual(node['inputs']['blend_weight'], weight)
            self.assertEqual(node['inputs']['audio_blend_weight'], 0)
            self.assertEqual(node['inputs']['window_size'], 2)
            self.assertTrue(node['inputs']['offline_smoothing_replay'])


class AccelerationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        source = ast.parse((Path(__file__).resolve().parents[1] / 'server.py').read_text(encoding='utf8'))
        names = {'H3AccelerationBody', 'get_h3_acceleration', 'set_h3_acceleration'}
        nodes = [node for node in source.body if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef)) and node.name in names]
        for node in nodes:
            node.decorator_list = []
        self.ns = dict(BaseModel=BaseModel, Field=Field, Optional=Optional, Literal=Literal,
                       DATA=self.data, COMFY_ROOT=self.data, COMFY_URL='http://comfy',
                       h3_acceleration=h3_acceleration, HTTPException=HTTPException)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'acceleration_api', 'exec'), self.ns)

    def test_api_rejects_out_of_range_nan_and_unknown_presets(self):
        for value in (-0.1, 1.01, math.nan, math.inf):
            with self.assertRaises(ValidationError):
                self.ns['H3AccelerationBody'](spectrum_blend_weight=value)
        with self.assertRaises(ValidationError):
            self.ns['H3AccelerationBody'](spectrum_preset='fastest')

    def test_partial_api_updates_keep_enabled_state_and_custom_value(self):
        async def run():
            Model = self.ns['H3AccelerationBody']
            first = await self.ns['set_h3_acceleration'](Model(spectrum_blend_weight=0.41))
            self.assertFalse(first['spectrum_enabled'])
            self.assertEqual(first['spectrum_preset'], 'custom')
            second = await self.ns['set_h3_acceleration'](Model(spectrum_enabled=False))
            self.assertEqual(second['spectrum_blend_weight'], 0.41)
            third = await self.ns['set_h3_acceleration'](Model(spectrum_preset='balanced'))
            self.assertEqual(third['spectrum_blend_weight'], 0.5)
            self.assertEqual(len(third['spectrum_presets']), 3)
        asyncio.run(run())

    def test_missing_spectrum_node_does_not_save_enabled_settings(self):
        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def get(self, url):
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {})
        self.ns['httpx'] = SimpleNamespace(AsyncClient=Client)
        async def run():
            with self.assertRaises(HTTPException) as error:
                await self.ns['set_h3_acceleration'](self.ns['H3AccelerationBody'](spectrum_enabled=True))
            self.assertEqual(error.exception.status_code, 409)
            self.assertFalse((self.data / 'h3_acceleration.json').exists())
        asyncio.run(run())
