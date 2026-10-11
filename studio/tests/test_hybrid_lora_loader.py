import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).parents[1] / 'comfy_nodes/h3_studio_enhancements/__init__.py'
with patch.dict(sys.modules, {'folder_paths': types.SimpleNamespace()}):
    spec = importlib.util.spec_from_file_location('hybrid_loader_test', SOURCE)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)

NAME = 'lightx2v_hybrid-4to8step-Turbo_r48.safetensors'
GOOD = f'adaLN: curve (input dim 8)\n{NAME} @ 1: 160 merged, 150 branched, adaLN ported x51 (basis fit 1.7e-03)'


class VerifiedLoader(unittest.TestCase):
    def run_loader(self, report):
        class Loader:
            def apply(self, **kwargs):
                return 'patched', report
        with patch.dict(sys.modules, {'nodes': types.SimpleNamespace(NODE_CLASS_MAPPINGS={'H3PowerLoraStack': Loader})}):
            return bridge.H3StudioHybridLora().apply('base', NAME)

    def test_accepts_full_port(self):
        self.assertEqual(self.run_loader(GOOD), ('patched', GOOD))

    def test_zero_strength_disables_adapter(self):
        self.assertEqual(bridge.H3StudioHybridLora().apply('base', NAME, 0)[0], 'base')

    def test_rejects_partial_or_failed_adapter(self):
        for report in (GOOD.replace('x51', 'x50'), GOOD + ', 1 skipped',
                       GOOD + ', adaLN dropped x1', 'stack failed; model unchanged',
                       GOOD + '\nadaLN port failed; pairs left as-is'):
            with self.subTest(report=report), self.assertRaises(RuntimeError):
                self.run_loader(report)

    def test_missing_loader_is_actionable(self):
        with patch.dict(sys.modules, {'nodes': types.SimpleNamespace(NODE_CLASS_MAPPINGS={})}):
            with self.assertRaisesRegex(RuntimeError, 'restart ComfyUI'):
                bridge.H3StudioHybridLora().apply('base', NAME)
