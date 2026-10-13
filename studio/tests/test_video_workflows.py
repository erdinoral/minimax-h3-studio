import json
import ast
import asyncio
import math
import tempfile
import unittest
import uuid
import time
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from lib import continuum, flow_refine
from lib.comfy import DEFAULT_MODELS, build_t2v_prompt


def broken_links(graph):
    return [(key,value[0]) for key,node in graph.items() for value in node['inputs'].values()
            if isinstance(value,list) and len(value)==2 and isinstance(value[1],int)
            and value[0] not in graph]


class WorkflowContracts(unittest.TestCase):
    def test_continuum_keeps_model_patch_dependencies_and_audio_vae(self):
        job=dict(id='12345678',prompt='A cloud',width=864,height=480,duration=5,
                 steps=10,seed=7,h3_models=DEFAULT_MODELS,continuum_run='test',
                 first_frame_name='portrait.png')
        with patch('lib.comfy.apply_spectrum',side_effect=lambda g:g):
            graph=continuum.build(job)
        self.assertEqual(broken_links(graph),[])
        self.assertEqual(graph['c_audio']['inputs']['vae'],['24',0])
        self.assertEqual(graph['c_first']['inputs']['image'],'portrait.png')
        self.assertEqual(graph['c_sample']['inputs']['run_storage'],'Save + Auto Resume')
        job['continuum_prompts']=['Scene']*17
        with self.assertRaises(ValueError): continuum.build(job)

    def test_refine_saves_original_graph_and_only_clones_conditioning_dependencies(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(flow_refine,'STORE',Path(directory)), patch('lib.comfy.apply_spectrum',side_effect=lambda g:g):
            graph=build_t2v_prompt(text='A cloud',width=864,height=480,length=124)
            job={'id':'11111111-1111-1111-1111-111111111111'}
            flow_refine.capture(graph,job)
            original=json.loads((Path(directory)/(job['id']+'.json')).read_text())
            self.assertNotIn('flow_capture',original)
            self.assertEqual(graph['10']['inputs']['samples'],['flow_save',0])
            target=flow_refine.build({'id':'new', 'refine_source_id':job['id'], 'width':1088,'height':608})
            self.assertEqual(broken_links(target),[])
            self.assertNotIn('src_92',target)
            self.assertEqual(target['14']['inputs']['latent_image'],['flow_load',1])
            self.assertEqual(target['104']['inputs']['height'],608)
            self.assertEqual(target['src_104']['inputs']['height'],480)
            self.assertEqual(target['92']['inputs']['filename_prefix'],'video/H3_Studio/new')


class RefineRequests(unittest.IsolatedAsyncioTestCase):
    async def test_refine_preserves_source_ratio_and_rejects_same_or_unknown_resolution(self):
        identifier='11111111-1111-1111-1111-111111111111'
        source=dict(id=identifier,prepare_refine=True,width=864,height=480,aspect='16:9',
                    prompt='Presenter',duration=5,steps=10,seed=7,h3_models=DEFAULT_MODELS)
        async def capabilities(): return {'refine_ready':True}
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            (folder/(identifier+'.json')).write_text('{}')
            states=folder/'output/H3_Studio_Flow';states.mkdir(parents=True)
            (states/(identifier+'.pt')).write_bytes(b'state')
            env=dict(RefineBody=SimpleNamespace,HTTPException=HTTPException,
                     _clip_record=lambda _:source,workflow_capabilities=capabilities,
                     flow_refine=SimpleNamespace(STORE=folder),COMFY_ROOT=folder,
                     QUALITY_SHORT_EDGE={'480':480,'608':608,'768':768},
                     normalize_quality=lambda q:q,math=math,uuid=uuid,time=time,
                     _lock=asyncio.Lock(),_jobs=[],_save_jobs=lambda:None)
            tree=ast.parse((Path(__file__).parents[1]/'server.py').read_text(encoding='utf-8'))
            functions=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
                       and n.name in ('snap32','snap_h3_size','refine_clip')]
            for function in functions: function.decorator_list=[]
            exec(compile(ast.Module(body=functions,type_ignores=[]),'server.py','exec'),env)
            job=await env['refine_clip'](identifier,SimpleNamespace(quality='608'))
            self.assertEqual((job['width'],job['height']),(1088,608))
            self.assertEqual(job['refine_source_id'],identifier)
            self.assertNotEqual(job['id'],identifier)
            self.assertEqual((source['width'],source['height']),(864,480))
            for quality in ('480','999'):
                with self.assertRaises(HTTPException) as rejected:
                    await env['refine_clip'](identifier,SimpleNamespace(quality=quality))
                self.assertEqual(rejected.exception.status_code,400)
            source['prepare_refine']=False
            with self.assertRaises(HTTPException) as rejected:
                await env['refine_clip'](identifier,SimpleNamespace(quality='608'))
            self.assertEqual(rejected.exception.status_code,409)
