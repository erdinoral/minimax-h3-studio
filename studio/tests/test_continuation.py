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
from lib.comfy import build_t2v_prompt


class ContinuationTests(unittest.IsolatedAsyncioTestCase):
    def env(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'server.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'batch')
        fn.decorator_list = []
        jobs = [{'id':'source','status':'done','width':864,'height':480,'aspect':'16:9'}]
        env = dict(BatchBody=object, HTTPException=RuntimeError, ALLOWED_DURATIONS=[5], QUALITY_SHORT_EDGE={'736':736},
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
            cinema=NS(load=lambda:{},bind_prompt=lambda *a,**kw:{'prompt':'reference composition','hits':[1],'ref_images':['portrait.png'],'has_character':True,'has_location':False},
                      bound_character_portraits=lambda *a:['portrait.png'],bound_vehicle_stills=lambda *a:[]))
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'batch-test','exec'),env)
        return env

    def body(self, **kw):
        return NS(**dict(dict(prompts=['Walk'], modes=['continue'], continue_from_job_id='source',parent_job_ids=None,
            duration=5,quality='736',aspect='9:16',purpose='short_film',silent_audio=False,music_id=None,
            prompt_rewriter_enabled=False,link_continue=False,append_to_chain=False,steps=18,sampler='s',scheduler='s',
            face_lock=True,ref_images=None,seed=7,lane='director',cinema_batch='film',score_id=None),**kw))

    async def test_first_explicit_continue_keeps_parent_and_canvas(self):
        env=self.env(); job=(await env['batch'](self.body()))['jobs'][0]
        self.assertEqual(job['continue_from'],'source')
        self.assertEqual(job['mode'],'continue')
        self.assertEqual(job['ref_images'],[])
        self.assertEqual(job['prompt'],'Walk')
        self.assertEqual((job['width'],job['height']),(864,480))
        self.assertEqual(job['h3_models']['graph'],'fl2va')

    async def test_missing_parent_rejected_without_jobs(self):
        env=self.env()
        with self.assertRaises(RuntimeError):await env['batch'](self.body(continue_from_job_id=None))
        self.assertEqual(len(env['_jobs']),1)

    async def test_new_continue_new_chain(self):
        env=self.env();jobs=(await env['batch'](self.body(prompts=['A','B','C'],modes=['t2v','continue','t2v'],continue_from_job_id=None)))['jobs']
        self.assertIsNone(jobs[0]['continue_from'])
        self.assertEqual(jobs[1]['continue_from'],jobs[0]['id'])
        self.assertIsNone(jobs[2]['continue_from'])

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
