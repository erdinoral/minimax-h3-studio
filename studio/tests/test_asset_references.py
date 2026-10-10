import ast
import copy
import sys
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import asset_references, cinema
from lib.comfy import enhance_ref_prompt, build_ref2va_prompt, add_h3_first_frame_guide
from studio.tests import test_continuation as continuation_test


def film():
    return {'film_id':'film', **{key:[{'id':key,'kind':key[:-1], 'name':name,
        'images':[{'file':key+'.png'}]}] for key,name in [('characters','Ada'),('vehicles','Car'),('creatures','Dragon'),('locations','Road')]}}


class ReferencePlanTests(unittest.TestCase):
    def plan(self, bindings, **kw):
        return asset_references.resolve('A different description.',bindings,film(),lambda f: True,**kw)

    def test_all_asset_types_work_without_name_mentions(self):
        bindings=[{'asset_id':key} for key in ('vehicles','characters','creatures','locations')]
        plan=self.plan(bindings)
        self.assertEqual(plan['ref_images'],['vehicles.png','characters.png','creatures.png','locations.png'])
        prompt=asset_references.prompt(plan['prompt'],plan['rows'],start_index=1)
        for number,name in enumerate(['Car','Ada','Dragon','Road'],2):
            self.assertIn(f'<Picture {number}>',prompt)
            self.assertIn(name,prompt)
        self.assertNotIn('<Picture 1>',prompt)

    def test_explicit_empty_never_matches_names(self):
        plan=asset_references.resolve('Car and Ada',[],film(),lambda f: True)
        self.assertEqual(plan['ref_images'],[])

    def test_uploaded_reference_order_and_deduplication(self):
        plan=self.plan([{'asset_id':'vehicles'}],existing=['uploaded.png','vehicles.png'])
        self.assertEqual(plan['ref_images'],['uploaded.png','vehicles.png'])
        prompt=asset_references.prompt('Move.',plan['rows'])
        self.assertIn('<Picture 2> is Car',prompt)

    def test_authored_picture_tags_shift_with_the_continuation_frame(self):
        plan=self.plan([{'asset_id':'vehicles'}],continuation=True)
        prompt=asset_references.prompt('Preserve the wheels of <Picture 1>.',plan['rows'],1)
        self.assertIn('wheels of <Picture 2>',prompt)
        self.assertNotIn('<Picture 1>',prompt)

    def test_unknown_picture_tag_fails_before_queue(self):
        with self.assertRaisesRegex(ValueError,'Picture'):
            asset_references.resolve('Use <Picture 2>',[{'asset_id':'vehicles'}],film(),lambda f:True)

    def test_missing_asset_file_or_selected_angle_fails(self):
        for bindings,exists in [([{'asset_id':'deleted'}],lambda f:True),
            ([{'asset_id':'vehicles'}],lambda f:False),
            ([{'asset_id':'vehicles','files':['wrong.png']}],lambda f:True)]:
            with self.assertRaises(ValueError):
                asset_references.resolve('Move',bindings,film(),exists)

    def test_continue_reserves_one_image_slot_and_does_not_truncate(self):
        with self.assertRaisesRegex(ValueError,'8'):
            self.plan([],existing=[f'{i}.png' for i in range(9)],continuation=True)

    def crowded_film(self):
        lib = film()
        for key, count in [('characters', 5), ('creatures', 3), ('locations', 1)]:
            lib[key][0]['images'] = [{'file': f'{key}_{i}.png'} for i in range(count)]
        bindings = [{'asset_id': key} for key in ('characters', 'creatures', 'locations')]
        return lib, bindings

    def test_continue_balances_default_angles_and_keeps_every_asset(self):
        lib, bindings = self.crowded_film()
        plan = asset_references.resolve('Move', bindings, lib, lambda f: True, continuation=True)
        self.assertEqual(len(plan['ref_images']), 8)
        self.assertEqual({r['asset']['id'] for r in plan['rows']},
                         {'characters', 'creatures', 'locations'})
        self.assertIn('characters_0.png', plan['ref_images'])
        self.assertIn('creatures_0.png', plan['ref_images'])
        self.assertEqual(len(lib['characters'][0]['images']), 5)

    def test_auto_angles_over_nine_reach_shared_budget(self):
        lib, bindings = self.crowded_film()
        lib['locations'][0]['images'].append({'file': 'road_second.png'})
        plan = asset_references.resolve('Move', bindings, lib, lambda f: True)
        self.assertEqual(len(plan['ref_images']), 9)

    def test_explicit_angles_and_picture_indices_are_never_truncated(self):
        lib, bindings = self.crowded_film()
        for b in bindings:
            b['files'] = [im['file'] for im in lib[b['asset_id']][0]['images']]
        with self.assertRaisesRegex(ValueError, '8'):
            asset_references.resolve('Move', bindings, lib, lambda f: True, continuation=True)
        for b in bindings:
            del b['files']
        with self.assertRaisesRegex(ValueError, '8'):
            asset_references.resolve('Use <Picture 9>', bindings, lib, lambda f: True, continuation=True)

    def test_uploaded_references_stay_first_when_auto_angles_are_reduced(self):
        lib, bindings = self.crowded_film()
        plan = asset_references.resolve('Move', bindings, lib, lambda f: True,
                                        existing=['uploaded.png'], continuation=True)
        self.assertEqual(len(plan['ref_images']), 8)
        self.assertEqual(plan['ref_images'][0], 'uploaded.png')
        self.assertEqual({r['asset']['id'] for r in plan['rows'] if 'asset' in r},
                         {'characters', 'creatures', 'locations'})

    def test_graph_has_last_frame_first_and_all_assets_in_exact_order(self):
        plan=self.plan([{'asset_id':'vehicles'},{'asset_id':'locations'}],continuation=True)
        prompt=enhance_ref_prompt(asset_references.prompt('Move',plan['rows'],1),n_images=3,role='asset_continue')
        graph=add_h3_first_frame_guide(build_ref2va_prompt(text=prompt,
            ref_image_names=['last.png',*plan['ref_images']]),'last.png')
        for index,file in enumerate(['last.png','vehicles.png','locations.png']):
            link=graph['104']['inputs'][f'ref_images.ref_image_{index}']
            self.assertEqual(graph[link[0]]['inputs']['image'],file)
        self.assertIn('not opening frames',prompt)
        self.assertIn('vehicle geometry',prompt)

    def test_new_scene_starts_with_scene_instruction_not_reference_catalogue(self):
        plan = self.plan([{'asset_id': 'characters'}, {'asset_id': 'creatures'}, {'asset_id': 'locations'}])
        legacy = enhance_ref_prompt('Ada lies beside the stream while Dragon drinks.',
                                     n_images=3, role='general')
        text = asset_references.prompt(legacy, plan['rows'], new_scene=True)
        self.assertTrue(text.startswith('SCENE FROM FRAME ZERO:'))
        self.assertIn('At 0.00 seconds', text)
        self.assertIn('Do not display, animate or transition out of', text)
        self.assertLess(text.index('Ada lies beside'), text.index('<Picture 1> is'))
        self.assertNotIn('as visual reference(s) for style', text)
        graph = build_ref2va_prompt(text=text, ref_image_names=plan['ref_images'])
        self.assertEqual(graph['104']['inputs']['prompt'], text)
        self.assertNotIn('451', graph)
        self.assertNotIn('first_frame', graph['104']['inputs'])

    def test_frame_zero_instruction_is_idempotent_and_continuation_stays_distinct(self):
        text = enhance_ref_prompt('Rest beside the stream.', n_images=2, role='asset_new')
        self.assertEqual(enhance_ref_prompt(text, n_images=2, role='asset_new'), text)
        plan = self.plan([{'asset_id': 'characters'}])
        continued = enhance_ref_prompt(asset_references.prompt('Continue resting.', plan['rows'], 1),
                                       n_images=2, role='asset_continue')
        self.assertIn('exact final frame of the previous clip', continued)
        self.assertNotIn('SCENE FROM FRAME ZERO:', continued)


class SharedQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_canonical_sources_are_uploaded_in_manifest_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); refs=root/'refs'; inputs=root/'input'; refs.mkdir();inputs.mkdir()
            for file in ['car.png','road.png']:(refs/file).write_bytes(b'canonical')
            calls=[]
            async def upload(path,name):
                calls.append((name,path.read_bytes()))
                return 'loaded_'+name
            rows=[{'file':'car.png'},{'file':'road.png'}]
            result=await asset_references.materialize(rows,refs,inputs,upload)
            self.assertEqual([r['file'] for r in result],['loaded_car.png','loaded_road.png'])
            self.assertEqual(calls,[('car.png',b'canonical'),('road.png',b'canonical')])
            self.assertEqual(rows,[{'file':'car.png'},{'file':'road.png'}])

    def body(self, **kw):
        return continuation_test.ContinuationTests().body(**kw)

    def env(self):
        env=continuation_test.ContinuationTests().env()
        lib=film()
        env['cinema']=cinema
        env['_asset_plan']=lambda text,bindings,lib,*a,**kw: asset_references.resolve(text,bindings,lib,lambda f:True,*a,continuation=kw.get('continuation',False))
        env['cinema']=NS(load=lambda:lib, bound_character_portraits=cinema.bound_character_portraits)
        tree=ast.parse((Path(__file__).resolve().parents[1]/'server.py').read_text(encoding='utf-8'))
        classes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in ('GenerateBody','BatchBody')]
        env.update(BaseModel=BaseModel,Field=Field,field_validator=field_validator,Optional=Optional,Any=Any)
        exec(compile(ast.Module(body=classes,type_ignores=[]),'request-models','exec'),env)
        generate=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='generate')
        generate.decorator_list=[]
        env.update(ASPECT_PRESETS={'16:9':(16,9)}, REF2VA_MODELS={}, REFS=Path('/not-used'),COMFY_INPUT=Path('/not-used'))
        env['slog'].info_job=lambda *a,**kw:None
        exec(compile(ast.Module(body=[generate],type_ignores=[]),'generate-handler','exec'),env)
        return env

    async def test_scene_single_new_and_continue_share_the_same_manifest(self):
        env=self.env()
        selection=[{'asset_id':'vehicles'},{'asset_id':'locations'}]
        for mode,parent in [('t2v',None),('continue','source')]:
            body=env['GenerateBody'](prompt='Move',mode=mode,continue_from_job_id=parent,
                asset_bindings=selection,quality='736',lane='scene')
            job=await env['generate'](body)
            self.assertEqual(job['ref_images'],['vehicles.png','locations.png'])
            self.assertEqual(job['continue_from'],parent)
            self.assertEqual(job['mode'],'ref' if mode=='t2v' else 'face_continue')
            self.assertEqual([r['asset']['name'] for r in job['reference_manifest']],['Car','Road'])

    async def test_director_selected_vehicle_reaches_continue_queue(self):
        env=self.env();body=self.body(shot_bindings=[[{'asset_id':'vehicles'}]])
        job=(await env['batch'](body))['jobs'][0]
        self.assertEqual(job['ref_images'],['vehicles.png'])
        self.assertEqual(job['reference_manifest'][0]['asset']['id'],'vehicles')
        self.assertEqual(job['mode'],'face_continue')
        self.assertEqual(job['continue_from'],'source')

    async def test_scene_batch_uses_same_selected_assets(self):
        env=self.env();body=self.body(lane='scene',cinema_batch=None,asset_bindings=[{'asset_id':'creatures'}])
        job=(await env['batch'](body))['jobs'][0]
        self.assertEqual(job['ref_images'],['creatures.png'])
        self.assertEqual(job['lane'],'scene')

    async def test_director_chapter_with_nine_default_refs_queues_all_six_shots(self):
        env = self.env()
        lib, selection = ReferencePlanTests().crowded_film()
        env['cinema'].load = lambda: lib
        modes = ['t2v', 'continue', 't2v', 'continue', 'continue', 'continue']
        body = self.body(prompts=['Move'] * 6, modes=modes, continue_from_job_id=None,
                         shot_bindings=[selection] * 6)
        jobs = (await env['batch'](body))['jobs']
        self.assertEqual(len(jobs), 6)
        for index, job in enumerate(jobs):
            self.assertEqual(len(job['ref_images']), 8 if modes[index] == 'continue' else 9)
            self.assertEqual({r['asset']['id'] for r in job['reference_manifest']},
                             {'characters', 'creatures', 'locations'})
            if modes[index] == 'continue':
                self.assertEqual(job['continue_from'], jobs[index - 1]['id'])

    async def test_batch_validates_all_selections_before_queuing_any(self):
        env=self.env();body=self.body(prompts=['A','B'],modes=['t2v','continue'],continue_from_job_id=None,
            shot_bindings=[[{'asset_id':'vehicles'}],[{'asset_id':'missing'}]])
        with self.assertRaises(ValueError):await env['batch'](body)
        self.assertEqual(len(env['_jobs']),1)


if __name__=='__main__':unittest.main()
