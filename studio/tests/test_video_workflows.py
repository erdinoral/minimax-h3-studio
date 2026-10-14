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
    def test_director_references_are_scoped_to_their_own_sections(self):
        refs,assignments=continuum.reference_plan([{'ref_images':['actor.png','place.png']},{'ref_images':['place.png','other.png']}])
        self.assertEqual(refs,['actor.png','place.png','other.png'])
        self.assertEqual(continuum.align_reference_labels('<Picture 1> is B; <Picture 2> is the set.', ['other.png','place.png'], refs), '<Picture 2> is B; <Picture 1> is the set.')
        self.assertEqual(assignments,{'actor.png':[1],'place.png':[1,2],'other.png':[2]})
        job=dict(id='refs',prompt='Test',continuum_prompts=['One','Two'],duration=5,width=864,height=480,steps=12,seed=7,h3_models=DEFAULT_MODELS,continuum_run='refs',ref_images=refs,continuum_ref_assignments=assignments)
        graph=continuum.build(job)
        self.assertEqual(graph['c_refs']['inputs']['reference_use'],'Per chunk')
        self.assertEqual(graph['c_refs']['inputs']['reference_r1_chunks'],'1')
        self.assertEqual(graph['c_refs']['inputs']['reference_r2_chunks'],'1,2')
        self.assertEqual(graph['c_refs']['inputs']['reference_r3_chunks'],'2')
        self.assertEqual(graph['c_sample']['inputs']['reference_images'],['c_refs',0])
        with self.assertRaises(ValueError): continuum.reference_plan([{'ref_images':[f'{i}.png' for i in range(10)]}])

    def test_continuum_removes_spectrum_without_dropping_model_dependencies(self):
        job=dict(id='draft',prompt='Test',duration=5,width=864,height=480,
                 steps=12,seed=7,h3_models=DEFAULT_MODELS,continuum_run='draft')
        with patch.object(Path,'read_text',return_value='{"spectrum_enabled": true}'):
            graph=continuum.build(job)
        self.assertFalse(continuum.has_spectrum(graph))
        self.assertEqual(graph['c_sample']['inputs']['model'],['6',0])
        self.assertEqual(graph['9']['inputs']['model'],['6',0])
        job['continuum_base_graph']['legacy']={'class_type':'SpectrumApplyMiniMaxH3','inputs':{'model':['6',0]}}
        with self.assertRaises(ValueError): continuum.build(job)

    def test_section_context_does_not_rewrite_saved_prefix(self):
        previous=['Original saved prompt']
        result=continuum.extend_prompts(previous,['Blue enters','Both fight'],'Red remains on the left')
        self.assertEqual(result[0],previous[0])
        self.assertEqual(previous,['Original saved prompt'])
        self.assertEqual(result[1:],["Red remains on the left\n\nBlue enters","Red remains on the left\n\nBoth fight"])
        for additions in ([],['  '],['good',''],['one\n---\ntwo']):
            with self.assertRaises(ValueError): continuum.extend_prompts([],additions)
        with self.assertRaises(ValueError): continuum.extend_prompts(['old']*15,['one','two'])

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
        job['continuum_continuity']='strong'
        with patch('lib.comfy.apply_spectrum',side_effect=lambda g:g): strong=continuum.build(job)
        self.assertEqual(strong['c_sample']['inputs']['continuity'],'Strong — 39 frames (Experimental)')
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


class DirectorContinuumQueue(unittest.IsolatedAsyncioTestCase):
    async def test_resolved_scene_bindings_reach_director_job_and_reference_model(self):
        from typing import Optional
        async def capabilities(): return {'continuum_ready':True}
        tree=ast.parse((Path(__file__).parents[1]/'server.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_queue_cinema_seamless')
        queued=[]
        body=SimpleNamespace(seamless_backend='continuum',duration=5,quality='480',aspect='16:9',steps=12,seed=7,sampler='res_multistep',scheduler='simple')
        ns={'CinemaProduceBody':SimpleNamespace,'Optional':Optional,'HTTPException':HTTPException,'workflow_capabilities':capabilities,
            'continuum':continuum,'cinema':SimpleNamespace(group_seamless_takes=lambda parsed,prompts,pack:[(parsed,prompts)]),
            'resolve_size':lambda *a:(864,480),'normalize_quality':lambda q:q,'time':time,'uuid':uuid,
            '_lora_src_for_shot':lambda *a:({},None),'_with_lora_preset':lambda src,steps,sampler,scheduler,graph:(steps,sampler,scheduler),
            '_lora_fields':lambda src:{},'apply_selected_triggers':lambda text,**kw:text,
            'h3_models':SimpleNamespace(resolve=lambda mode:{'unet':mode}),'_sage_mode':lambda body:'disabled',
            '_normalize_post_pass':lambda x:'','_voice_refs_from_hits':lambda hits:[],
            '_lock':asyncio.Lock(),'_jobs':queued,'_save_jobs':lambda:None,'slog':SimpleNamespace(info=lambda *a,**kw:None)}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'director-queue','exec'),ns)
        plans=[{'prompt':'Actor enters','ref_images':['actor.png'],'hits':[]},
               {'prompt':'Actor sits','ref_images':['actor.png','place.png'],'hits':[]}]
        result=await ns['_queue_cinema_seamless'](body=body,parsed=[{},{}],prompts=['one','two'],lib={'film_id':'test'},audio={},cinema_batch='test',silent=True,purpose='test',reference_plans=plans)
        job=result['jobs'][0]
        self.assertEqual(job['mode'],'continuum')
        self.assertEqual(job['lane'],'director')
        self.assertEqual(job['h3_models']['unet'],'ref2va')
        self.assertEqual(job['ref_images'],['actor.png','place.png'])
        self.assertEqual(job['continuum_ref_assignments'],{'actor.png':[1,2],'place.png':[2]})
        self.assertEqual(len(queued),1)
