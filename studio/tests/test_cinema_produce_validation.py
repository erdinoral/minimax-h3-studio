import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from fastapi import HTTPException
from lib import cinema


class ProduceValidation(unittest.IsolatedAsyncioTestCase):
    def handler(self):
        tree = ast.parse((Path(__file__).parents[1] / 'server.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'cinema_produce')
        fn.decorator_list = []
        load = Mock(side_effect=RuntimeError('asset preparation reached'))
        scope = {'CinemaProduceBody': object, 'HTTPException': HTTPException,
                 'cinema': SimpleNamespace(normalize_produce_shots=cinema.normalize_produce_shots, load=load)}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<produce-validation>', 'exec'), scope)
        return scope['cinema_produce'], load

    async def test_oversized_request_rejected_before_asset_preparation(self):
        handler, load = self.handler()
        body = SimpleNamespace(shots=[{'text': f'Scene {i}', 'mode': 't2v'} for i in range(102)],
                               script='', shot_modes=None, prepare_sheets=True, seamless=False)
        with self.assertRaises(HTTPException) as caught:
            await handler(body)
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn('80', caught.exception.detail)
        load.assert_not_called()

    async def test_empty_request_rejected_before_asset_preparation(self):
        handler, load = self.handler()
        body = SimpleNamespace(shots=[], script='', shot_modes=None, prepare_sheets=True, seamless=False)
        with self.assertRaises(HTTPException):
            await handler(body)
        load.assert_not_called()

    async def test_51_scene_lyric_request_reaches_asset_preparation(self):
        handler, load = self.handler()
        body = SimpleNamespace(shots=[{'text': f'Lyric {i}', 'mode': 't2v'} for i in range(51)],
                               script='', shot_modes=None, prepare_sheets=True, seamless=False)
        with self.assertRaisesRegex(RuntimeError, 'asset preparation reached'):
            await handler(body)
        load.assert_called_once()
