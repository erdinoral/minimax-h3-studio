"""Queue regressions without starting servers or touching user data."""
import ast
import asyncio
import sys
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import cinema
from lib.comfy import add_h3_first_frame_guide, build_ref2va_prompt, build_t2v_prompt, enhance_ref_prompt


class ContinuationTests(unittest.IsolatedAsyncioTestCase):
    def env(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'server.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'batch')
        fn.decorator_list = []
        jobs = [{'id':'source','status':'done','width':864,'height':480,'aspect':'16:9'}]
        env = dict(h3_enhancements=NS(settings=lambda:{"refmod_enabled":False}), BatchBody=object, HTTPException=RuntimeError, ALLOWED_DURATIONS=[5], QUALITY_SHORT_EDGE={'736':736},
            _asset_plan=lambda text, bindings, lib, *a, **kw: {'prompt':text,'rows':[{'file':'portrait.png'}],
                'hits':[1],'ref_images':['portrait.png'],'has_character':True,'has_location':False},
            comfy=NS(healthy=AsyncMock(return_value=True)), _free_llm_for_production=AsyncMock(),
            _lora_fields=lambda _: {}, apply_audio_policy=lambda p,_:p, _chain_tip=lambda:None,
            _clip_record=lambda jid:next((j for j in jobs if j['id']==jid),None),
            resolve_size=lambda *_:(480,864), _lookup_face_lock=lambda _: ([], 'max'),
            _lock=asyncio.Lock(), _lora_src_for_shot=lambda b,bd,m:(b,'fl2va' if m=='continue' else 'ref2va'),
            _with_lora_preset=lambda b,st,sa,sc,**kw:(st,sa,sc), normalize_quality=lambda q:q,
            _sage_mode=lambda _:'disabled', _normalize_post_pass=lambda _:'', uuid=uuid,time=time,
            h3_models=NS(resolve=lambda g:{'graph':g},graph_for_mode=lambda m:'fl2va' if m=='continue' else 'ref2va'),
            enhance_ref_prompt=lambda p,**kw:p, _jobs=jobs,_save_jobs=lambda:None,
            slog=NS(info=lambda *a,**kw:None), apply_trigger=lambda p,_:p,find_spec=lambda **kw:None,
            apply_selected_triggers=lambda p,**kw:p,
            cinema=NS(load=lambda:{},bind_prompt=lambda *a,**kw:{'prompt':'reference composition','hits':[1],'ref_images':['portrait.png'],'has_character':True,'has_location':False},
                      bound_character_portraits=lambda *a:['portrait.png'],bound_vehicle_stills=lambda *a:[],
                      mentioned_character_lock=lambda *a:''))
        binding = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_scene_asset_bindings')
        exec(compile(ast.Module(body=[binding, fn],type_ignores=[]),'batch-test','exec'),env)
        return env

    def body(self, **kw):
        return NS(**dict(dict(prompts=['Walk'], modes=['continue'], continue_from_job_id='source',parent_job_ids=None,
            shot_bindings=None, asset_bindings=None, asset_auto_match=False, asset_film_id=None, first_frame_names=None,
            duration=5,quality='736',aspect='9:16',purpose='short_film',silent_audio=False,music_id=None,
            prompt_rewriter_enabled=False,link_continue=False,append_to_chain=False,steps=18,sampler='s',scheduler='s',
            face_lock=True,ref_images=None,seed=7,lane='director',cinema_batch='film',score_id=None),**kw))

    async def test_first_explicit_continue_keeps_parent_and_canvas(self):
        env=self.env(); job=(await env['batch'](self.body()))['jobs'][0]
        self.assertEqual(job['continue_from'],'source')
        self.assertEqual(job['mode'],'face_continue')
        self.assertEqual(job['ref_images'],['portrait.png'])
        self.assertEqual(job['prompt'],'Walk')
        self.assertEqual((job['width'],job['height']),(864,480))
        self.assertEqual(job['h3_models']['graph'],'ref2va')

    async def test_missing_parent_rejected_without_jobs(self):
        env=self.env()
        with self.assertRaises(RuntimeError):await env['batch'](self.body(continue_from_job_id=None))
        self.assertEqual(len(env['_jobs']),1)

    async def test_new_continue_new_chain(self):
        env=self.env();jobs=(await env['batch'](self.body(prompts=['A','B','C'],modes=['t2v','continue','t2v'],continue_from_job_id=None)))['jobs']
        self.assertIsNone(jobs[0]['continue_from'])
        self.assertEqual(jobs[1]['continue_from'],jobs[0]['id'])
        self.assertIsNone(jobs[2]['continue_from'])

    async def test_non_per_shot_batch_uses_resolved_manifest(self):
        env=self.env()
        jobs=(await env['batch'](self.body(prompts=['A','B'], modes=None, continue_from_job_id=None)))['jobs']
        self.assertEqual(jobs[0]['ref_images'], ['portrait.png'])
        self.assertEqual(jobs[1]['ref_images'], ['portrait.png'])
        self.assertEqual(jobs[1]['continue_from'], jobs[0]['id'])

    async def test_later_lora_error_does_not_leave_partial_batch(self):
        env=self.env()
        calls=[]
        def select(body, bound, mode):
            calls.append(mode)
            if len(calls) == 2:
                raise ValueError('LoRA stack exceeds limit')
            return body, 'ref2va'
        env['_lora_src_for_shot']=select
        with self.assertRaisesRegex(ValueError,'LoRA stack'):
            await env['batch'](self.body(prompts=['A','B'], modes=['t2v','continue'], continue_from_job_id=None))
        self.assertEqual(len(env['_jobs']),1)

    async def test_skipped_completed_shot_can_be_explicit_parent(self):
        env=self.env();jobs=(await env['batch'](self.body(prompts=['A','B'],modes=['t2v','continue'],continue_from_job_id=None,parent_job_ids=[None,'source'])))['jobs']
        self.assertEqual(jobs[1]['continue_from'],'source')

    def test_card_mode_survives_batch_boundary(self):
        self.assertEqual(cinema.apply_reentry_modes([{'id':'s','text':'Walk','mode':'continue'}])[0]['mode'],'continue')

    def test_actual_graph_wires_first_frame(self):
        g=build_t2v_prompt(text='Walk',first_frame_name='source_last.png')
        self.assertEqual(g['104']['inputs']['first_frame'],['200',0])
        self.assertEqual(g['200']['inputs']['image'],'source_last.png')
        self.assertFalse(any('ref_images' in k for k in g['104']['inputs']))

    def test_hybrid_graph_keeps_portrait_and_anchors_first_frame(self):
        g=add_h3_first_frame_guide(
            build_ref2va_prompt(text=enhance_ref_prompt('Cassian continues walking.',n_images=2,role='face_continue',n_face=1),ref_image_names=['previous_last.png','portrait.png']),
            'previous_last.png',
        )
        self.assertEqual(g['104']['inputs']['ref_images.ref_image_0'],['200',0])
        self.assertEqual(g['200']['inputs']['image'],'previous_last.png')
        self.assertEqual(g['104']['inputs']['ref_images.ref_image_1'],['201',0])
        self.assertEqual(g['201']['inputs']['image'],'portrait.png')
        self.assertIn('<Picture 1> is the exact final frame',g['104']['inputs']['prompt'])
        self.assertIn('Never animate a portrait',g['104']['inputs']['prompt'])
        self.assertEqual(g['450']['inputs']['image'],'previous_last.png')
        self.assertEqual(g['451']['inputs']['frame_idx'],0)
        self.assertEqual(g['451']['inputs']['latent'],['104',1])
        self.assertEqual(g['16']['inputs']['conditioning'],['451',0])

    def test_previous_clip_survives_gallery_archive(self):
        tree=ast.parse((Path(__file__).resolve().parents[1] / 'server.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='_cinema_previous_clip')
        env={'Optional':__import__('typing').Optional,'_jobs':[],
             '_gallery':[{'id':'archived','shot_id':'first','created_at':1}]}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'clip-test','exec'),env)
        shots=[{'id':'first','text':'Opening'}, {'id':'second','text':'Continue'}]
        self.assertEqual(env['_cinema_previous_clip'](shots,'second'),'archived')
        env['_jobs'].append({'id':'archived','shot_id':'first','status':'error','created_at':2})
        self.assertIsNone(env['_cinema_previous_clip'](shots,'second'))

if __name__ == '__main__': unittest.main()
