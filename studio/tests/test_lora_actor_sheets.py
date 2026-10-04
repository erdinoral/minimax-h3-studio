import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any, Optional
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1]))
from lib import cinema, asset_references

class LoraOnlyActors(unittest.IsolatedAsyncioTestCase):
    def actor(self):
        return dict(id='actor',kind='character',name='NEA',trigger='chr_nea',use_lora=True,lora_id='nea',notes='OLD DESCRIPTION',images=[{'file':'old.png'}])
    def plan(self, bindings=None):
        actor=self.actor()
        spec={'id':'nea','file':'nea.safetensors'}
        with patch('lib.loras.find_spec',return_value=spec),patch('lib.loras.spec_ready',return_value=True),patch('lib.lora_guidance.guidance',return_value={'triggers':'chr_nea'}):
            return asset_references.resolve('NEA walks.',bindings,{'characters':[actor]},lambda f:False)
    def test_lora_identity_without_images_or_description(self):
        plan=self.plan()
        self.assertEqual(plan['ref_images'],[])
        self.assertEqual(plan['lora_id'],'nea')
        self.assertIn('chr_nea',plan['prompt'])
        self.assertNotIn('OLD DESCRIPTION',plan['prompt'])
    def test_explicit_binding_ignores_old_snapshot_images(self):
        plan=self.plan([{'asset_id':'actor','snapshot':self.actor(),'files':['old.png']}])
        self.assertEqual(plan['ref_images'],[])
        self.assertEqual(plan['lora_id'],'nea')
    async def test_no_sheet_even_when_force_enabled(self):
        tree=ast.parse((Path(__file__).parents[1]/'server.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_asset_needs_sheet')
        env=dict(Any=Any,cinema=cinema)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'sheet-check','exec'),env)
        self.assertFalse(env['_asset_needs_sheet'](self.actor(),force=True))
    async def test_manual_sheet_rejected_in_lora_mode(self):
        tree=ast.parse((Path(__file__).parents[1]/'server.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_queue_cinema_sheet_job')
        env=dict(Any=Any,Optional=Optional,cinema=NS(asset_kind_key=lambda k:(k,'characters'),load=lambda:{'characters':[self.actor()]},uses_lora=cinema.uses_lora))
        exec(compile(ast.Module(body=[node],type_ignores=[]),'sheet','exec'),env)
        with self.assertRaisesRegex(ValueError,'üretilmez'):
            await env['_queue_cinema_sheet_job'](kind='character',name='NEA',asset_id='actor')
    def test_enabled_without_selection_never_falls_back_to_old_photos(self):
        actor=self.actor(); actor['lora_id']=''
        with patch('lib.loras.find_spec',return_value=None):
            with self.assertRaisesRegex(ValueError,'LoRA dosyası seçilmeli'):
                asset_references.resolve('NEA walks.',None,{'characters':[actor]},lambda f:True)

    def test_switch_off_restores_normal_asset_mode(self):
        actor=self.actor();actor['use_lora']=False
        self.assertFalse(cinema.uses_lora(actor))
        clean=cinema._clean_asset(actor,'character')
        self.assertFalse(clean['use_lora'])
        self.assertEqual(clean['lora_id'],'nea')

if __name__=='__main__': unittest.main()

class SceneAssetIsolation(unittest.TestCase):
    def test_scene_default_and_explicit_opt_in(self):
        tree=ast.parse((Path(__file__).parents[1]/'server.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_scene_asset_bindings')
        env={}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'scene-assets','exec'),env)
        select=env['_scene_asset_bindings']
        body=NS(asset_bindings=None,lane='scene',asset_auto_match=False)
        self.assertEqual(select(body),[])
        body.asset_auto_match=True
        self.assertIsNone(select(body))
        body.asset_auto_match=False
        body.lane='director'
        self.assertIsNone(select(body))
        body.asset_bindings=[{'asset_id':'nea'}]
        self.assertEqual(select(body),body.asset_bindings)
