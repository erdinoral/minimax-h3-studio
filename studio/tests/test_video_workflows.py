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
        self.assertEqual(continuum.align_reference_labels('<Picture 1> is B; <Picture 2> is the set.', ['other.png','place.png'], refs), '@R3 is B; @R2 is the set.')
        self.assertEqual(assignments,{'actor.png':[1],'place.png':[1,2],'other.png':[2]})
        job=dict(id='refs',prompt='Test',continuum_prompts=['One','Two'],duration=5,width=864,height=480,steps=12,seed=7,h3_models=DEFAULT_MODELS,continuum_run='refs',ref_images=refs,continuum_ref_assignments=assignments)
        with patch('lib.comfy.apply_spectrum',side_effect=lambda g, **kwargs:g):
            graph=continuum.build(job)
        self.assertEqual(graph['c_refs']['inputs']['reference_use'],'Per chunk')
        self.assertEqual(graph['c_refs']['inputs']['reference_r1_chunks'],'1')
        self.assertEqual(graph['c_refs']['inputs']['reference_r2_chunks'],'1,2')
        self.assertEqual(graph['c_refs']['inputs']['reference_r3_chunks'],'2')
        self.assertEqual(graph['c_sample']['inputs']['reference_images'],['c_refs',0])
        self.assertEqual(graph['c_sample']['inputs']['reference_size'],'Match Output')
        job['continuum_reference_size']='Max Identity'
        self.assertEqual(continuum.build(job)['c_sample']['inputs']['reference_size'],'Max Identity')
        with self.assertRaises(ValueError): continuum.reference_plan([{'ref_images':[f'{i}.png' for i in range(10)]}])

    def test_continuum_preserves_spectrum_but_disables_unsafe_saved_prefix_reuse(self):
        job=dict(id='draft',prompt='Test',duration=5,width=864,height=480,
                 steps=12,seed=7,h3_models=DEFAULT_MODELS,continuum_run='draft')
        with patch.object(Path,'read_text',return_value='{"spectrum_enabled": true}'):
            graph=continuum.build(job)
        self.assertTrue(continuum.has_spectrum(graph))
        self.assertEqual(graph['c_sample']['inputs']['run_storage'],'Off')
        model_node=graph[graph['c_sample']['inputs']['model'][0]]
        self.assertEqual(model_node['class_type'],'SpectrumApplyMiniMaxH3')
        self.assertEqual(graph['9']['inputs']['model'],graph['c_sample']['inputs']['model'])
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
                 first_frame_name='portrait.png',
                 continuum_prompts=['Look at the mountain\n---\nKeep the same valley','Step onto the path'])
        with patch('lib.comfy.apply_spectrum',side_effect=lambda g, **kwargs:g):
            graph=continuum.build(job)
        self.assertEqual(broken_links(graph),[])
        self.assertEqual(graph['c_audio']['inputs']['vae'],['24',0])
        self.assertEqual(graph['c_first']['inputs']['image'],'portrait.png')
        self.assertEqual(graph['c_sample']['inputs']['run_storage'],'Save + Auto Resume')
        self.assertEqual(json.loads(graph['c_sample']['inputs']['sequence_prompt']),job['continuum_prompts'])
        self.assertEqual(graph['c_sample']['inputs']['chunks'],2)
        job['continuum_continuity']='strong'
        with patch('lib.comfy.apply_spectrum',side_effect=lambda g, **kwargs:g): strong=continuum.build(job)
        self.assertEqual(strong['c_sample']['inputs']['continuity'],'Strong — 39 frames (Experimental)')
        job['continuum_prompts']=['Scene']*17
        with self.assertRaises(ValueError): continuum.build(job)

    def test_refine_saves_original_graph_and_only_clones_conditioning_dependencies(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(flow_refine,'STORE',Path(directory)), patch('lib.comfy.apply_spectrum',side_effect=lambda g, **kwargs:g):
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
    def env(self):
        from typing import Optional
        async def capabilities(): return {'continuum_ready':True}
        tree=ast.parse((Path(__file__).parents[1]/'server.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_queue_cinema_seamless')
        queued=[]
        body=SimpleNamespace(seamless_backend='continuum',continuum_max_chunks=16,duration=5,quality='480',aspect='16:9',steps=12,seed=7,sampler='res_multistep',scheduler='simple')
        ns={'CinemaProduceBody':SimpleNamespace,'Optional':Optional,'HTTPException':HTTPException,'workflow_capabilities':capabilities,
            'continuum':continuum,'cinema':SimpleNamespace(group_seamless_takes=lambda parsed,prompts,pack:[(parsed,prompts)]),
            'resolve_size':lambda *a:(864,480),'normalize_quality':lambda q:q,'time':time,'uuid':uuid,
            '_lora_src_for_shot':lambda *a:({},None),'_with_lora_preset':lambda src,steps,sampler,scheduler,graph:(steps,sampler,scheduler),
            '_lora_fields':lambda src:{},'apply_selected_triggers':lambda text,**kw:text,
            'h3_models':SimpleNamespace(resolve=lambda mode:{'unet':mode}),'_sage_mode':lambda body:'disabled',
            '_normalize_post_pass':lambda x:'','_voice_refs_from_hits':lambda hits:[],
            '_lock':asyncio.Lock(),'_jobs':queued,'_save_jobs':lambda:None,'slog':SimpleNamespace(info=lambda *a,**kw:None)}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'director-queue','exec'),ns)
        return ns, body, queued

    async def test_resolved_scene_bindings_reach_director_job_and_reference_model(self):
        ns, body, queued = self.env()
        plans=[{'prompt':'Actor enters','ref_images':['actor.png'],'hits':[]},
               {'prompt':'Actor sits','ref_images':['actor.png','place.png'],'hits':[]}]
        result=await ns['_queue_cinema_seamless'](body=body,parsed=[{},{}],prompts=['one','two'],lib={'film_id':'test'},audio={},cinema_batch='test',silent=True,purpose='test',reference_plans=plans)
        job=result['jobs'][0]
        self.assertEqual(job['mode'],'continuum')
        self.assertEqual(job['lane'],'director')
        self.assertEqual(job['h3_models']['unet'],'ref2va')
        self.assertEqual(job['ref_images'],['actor.png','place.png'])
        self.assertEqual(job['continuum_ref_assignments'],{'actor.png':[1,2],'place.png':[2]})
        self.assertEqual(job['continuum_reference_size'],'Match Output')
        self.assertEqual(job['native_context_chunks'],2)
        self.assertEqual(len(queued),1)

    async def test_json_story_order_and_cross_take_handoff(self):
        ns, body, queued = self.env()
        shots = [dict(id='look',take_index=2,mode='t2v'),
                 dict(id='step',take_index=2,mode='continue'),
                 dict(id='climb',take_index=1,mode='continue'),
                 dict(id='cutaway',take_index=3,mode='t2v')]
        prompts = ['Look at the mountain','Step onto the path','Climb the same path','New view of the summit']
        plans = [dict(prompt=p, ref_images=['actor.png'], hits=[]) for p in prompts]
        result = await ns['_queue_cinema_seamless'](body=body,parsed=shots,prompts=prompts,
            lib={},audio={},cinema_batch='story',silent=True,purpose='test',reference_plans=plans)
        first, second, cut = result['jobs']
        self.assertEqual([p for j in result['jobs'] for p in j['continuum_prompts']], prompts)
        self.assertEqual(second['continue_from'],first['id'])
        self.assertEqual(second['continuity_method'],'last_frame_handoff')
        self.assertIsNone(cut['continue_from'])
        self.assertEqual(second['continuum_scene_ids'],['climb'])

    async def test_per_scene_references_reach_fixed_slots_with_a_starting_frame(self):
        ns, body, _ = self.env()
        body.continuum_reference_size = 'Max Identity'
        plans = [dict(prompt='<Picture 1> enters.', ref_images=['a.png'], hits=[{'id':'a'}]),
                 dict(prompt='@R1 stops beside <Picture 2>.', ref_images=['c.png','a.png'], hits=[{'id':'c'}])]
        result = await ns['_queue_cinema_seamless'](body=body,
            parsed=[dict(mode='t2v',first_frame_name='opening.png'),dict(mode='continue')],
            prompts=['one','two'],lib={},audio={},cinema_batch='refs',silent=True,purpose='test',reference_plans=plans)
        job = result['jobs'][0]
        self.assertEqual(job['ref_images'], ['a.png','c.png'])
        self.assertEqual(job['continuum_prompts'], ['@R1 enters.', '@R2 stops beside @R1.'])
        self.assertEqual(job['first_frame_name'], 'opening.png')
        self.assertEqual(job['continuum_reference_size'], 'Max Identity')

    async def test_single_continuation_uses_its_explicit_previous_scene(self):
        ns, body, _ = self.env()
        args = dict(body=body,parsed=[dict(id='climb',mode='continue')],prompts=['Climb'],
                    lib={},audio={},cinema_batch='story',silent=True,purpose='test',
                    reference_plans=[dict(prompt='Climb',ref_images=[],hits=[])])
        result = await ns['_queue_cinema_seamless'](**args,parent_job_ids=['previous-clip'])
        self.assertEqual(result['jobs'][0]['continue_from'],'previous-clip')
        with self.assertRaises(HTTPException):
            await ns['_queue_cinema_seamless'](**args)

    async def test_memory_limited_pack_preserves_starting_guide_and_parent(self):
        ns, body, _ = self.env()
        body.continuum_max_chunks = 1
        result = await ns['_queue_cinema_seamless'](body=body,
            parsed=[dict(id='start',mode='t2v',first_frame_name='armor.png'),dict(id='next',mode='continue')],
            prompts=['Start on terrace','Walk toward arch'],lib={},audio={},cinema_batch='hd',
            silent=False,purpose='test',reference_plans=[dict(prompt=p,ref_images=[],hits=[])
                for p in ['Start on terrace','Walk toward arch']])
        first, second = result['jobs']
        self.assertEqual(first['first_frame_name'],'armor.png')
        self.assertEqual(second['continue_from'],first['id'])
        self.assertEqual([j['continuum_scene_ids'] for j in result['jobs']],[['start'],['next']])

    async def test_handoff_resolves_last_frame_and_does_not_restart_without_it(self):
        from unittest.mock import AsyncMock
        resolve = AsyncMock(return_value='previous-last-frame.png')
        job = dict(mode='continuum',continue_from='previous')
        await continuum.prepare_director_handoff(job,resolve)
        self.assertEqual(job['first_frame_name'],'previous-last-frame.png')
        resolve.assert_awaited_once_with(job)
        await continuum.prepare_director_handoff(dict(mode='continuum'),resolve)
        self.assertEqual(resolve.await_count,1)
        resumed = dict(mode='continuum',continue_from='previous',continuum_resume=True,first_frame_name='original-guide.png')
        await continuum.prepare_director_handoff(resumed,resolve)
        self.assertEqual(resolve.await_count,1)
        self.assertEqual(resumed['first_frame_name'],'original-guide.png')
        prompt_only = dict(mode='continuum',continue_from='previous',continuum_resume=True)
        await continuum.prepare_director_handoff(prompt_only,resolve)
        self.assertEqual(resolve.await_count,1)
        self.assertNotIn('first_frame_name',prompt_only)
        with self.assertRaises(RuntimeError):
            await continuum.prepare_director_handoff(job,AsyncMock(return_value=None))

    def test_chunk_limit_does_not_repeat_or_reorder_story_beats(self):
        shots = [dict(id=str(i),mode='continue' if i else 't2v') for i in range(18)]
        prompts = [f'Action {i}' for i in range(18)]
        groups = continuum.director_takes(shots,prompts)
        self.assertEqual([len(s) for s,p in groups],[16,2])
        self.assertEqual([p for s,ps in groups for p in ps],prompts)
        with self.assertRaises(ValueError): continuum.director_takes(shots,prompts[:-1])

    async def test_chapter_sequence_keeps_six_distinct_prompts_and_only_first_starting_image(self):
        ns, body, _ = self.env()
        body.continuum_grouping = 'chapter'
        shots = [dict(id=str(i), chapter='Heaven', take_index=i+1, mode='t2v', first_frame_name=f'guide{i}.png') for i in range(6)]
        prompts = [f'Unique action {i}.' for i in range(6)]
        result = await ns['_queue_cinema_seamless'](body=body, parsed=shots, prompts=prompts,
            lib={}, audio={}, cinema_batch='chapter', silent=False, purpose='test',
            reference_plans=[dict(prompt=p,ref_images=[],hits=[]) for p in prompts])
        self.assertEqual(len(result['jobs']), 1)
        job = result['jobs'][0]
        self.assertEqual(job['planned_duration'], 30)
        self.assertEqual(job['native_context_chunks'], 6)
        self.assertEqual(job['first_frame_name'], 'guide0.png')
        self.assertEqual(job['continuum_ignored_guides'], ['1','2','3','4','5'])
        self.assertEqual(job['continuum_scene_ids'], [str(i) for i in range(6)])
        for i, prompt in enumerate(job['continuum_prompts']):
            self.assertIn(prompts[i], prompt)
        self.assertEqual(shots[5]['first_frame_name'], 'guide5.png')  # no saved-scene mutation

    def test_chapter_grouping_never_merges_chapters_and_keeps_sixteen_chunk_limit(self):
        shots = [dict(chapter='A',mode='t2v',take_index=i) for i in range(17)] + [dict(chapter='B',mode='t2v')]
        prompts = [f'Action {i}' for i in range(18)]
        groups = continuum.director_takes(shots, prompts, grouping='chapter')
        self.assertEqual([len(s) for s,p in groups], [16,1,1])
        self.assertEqual([p for s,ps in groups for p in ps], prompts)

    async def test_long_chapter_split_continues_previous_sequence_instead_of_restarting_from_another_guide(self):
        ns, body, _ = self.env()
        body.continuum_grouping = 'chapter'
        body.continuum_max_chunks = 2
        shots = [dict(id=str(i),chapter='A',mode='t2v',first_frame_name=f'guide{i}.png') for i in range(3)]
        prompts = ['first','second','third']
        result = await ns['_queue_cinema_seamless'](body=body,parsed=shots,prompts=prompts,
            lib={},audio={},cinema_batch='chapter-limit',silent=True,purpose='test',
            reference_plans=[dict(prompt=p,ref_images=[],hits=[]) for p in prompts])
        first,second = result['jobs']
        self.assertEqual(second['continue_from'],first['id'])
        self.assertIsNone(second['first_frame_name'])
        self.assertIn('2',second['continuum_ignored_guides'])
