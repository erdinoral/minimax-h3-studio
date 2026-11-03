import asyncio
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import server
from lib import shot_reproduce, h3_acceleration


def recorded(**changes):
    changes.setdefault('mode', 'ref')
    return dict(id='old', film_id='film', shot_id='shot', status='done', prompt='Original dialogue',
                duration=5, width=1280, height=736, seed=42, steps=18, sampler='res_multistep',
                scheduler='simple', h3_models={'unet':'original.safetensors','clip':'text','vae':'video','audio_vae':'audio'},
                acceleration_settings={'spectrum_enabled':True,'spectrum_blend_weight':.5,'sparse_enabled':True},
                ref_images=['face.png'], first_frame_name='opening.png', local_path='old.mp4',
                output={'url':'old.mp4'}, done_at=12, created_at=1, **changes)


class SameRender(unittest.TestCase):
    def test_clone_keeps_inputs_and_old_video_but_not_output_state(self):
        source=recorded()
        before=copy.deepcopy(source)
        job=shot_reproduce.clone(source)
        self.assertNotEqual(job['id'],source['id'])
        for key in ('prompt','duration','width','height','seed','steps','sampler','scheduler','h3_models','ref_images','first_frame_name','acceleration_settings'):
            self.assertEqual(job[key],source[key])
        self.assertIsNone(job['output'])
        self.assertNotIn('local_path',job)
        self.assertNotIn('done_at',job)
        job['ref_images'].append('new.png')
        self.assertEqual(source,before)

    def test_continuum_repeats_only_one_section_with_original_parent(self):
        source=recorded(mode='continuum',continue_from='original-parent',director_root_id='root',
                        director_parent_id='root',director_chain_role='continue',continuum_prompts=['one section'],
                        continuum_scene_ids=['shot'],continuum_run='old-run',continuation_state_key='old-tail',
                        continuation_source_key='parent-tail')
        job=shot_reproduce.clone(source)
        self.assertEqual(job['continue_from'],'original-parent')
        self.assertEqual(job['continuum_prompts'],['one section'])
        self.assertEqual(job['continuation_source_key'],'parent-tail')
        self.assertNotIn('continuation_state_key',job)
        self.assertNotEqual(job['continuum_run'],'old-run')

    def test_completed_output_last_frame_is_not_reused_as_an_input_guide(self):
        source=recorded()
        source['reproduction_snapshot']=shot_reproduce.snapshot(source)
        source['last_frame_name']='h3_studio_old_last.png'
        self.assertNotIn('last_frame_name',shot_reproduce.clone(source))
        legacy=shot_reproduce.recover_settings(source,{'x':{'class_type':'UNETLoader','inputs':{}}})
        self.assertIsNone(legacy['last_frame_name'])

    def test_rejects_packed_scenes_missing_records_and_active_source(self):
        for fields in ({'continuum_scene_ids':['one','two']},{'acceleration_settings':None},{'status':'running'}):
            source=recorded(); source.update(fields)
            with self.assertRaises(ValueError): shot_reproduce.clone(source)

    def test_legacy_settings_come_from_graph_instead_of_global_choices(self):
        source=recorded();source.pop('acceleration_settings');source['h3_models']=None
        graph={'6':{'class_type':'UNETLoader','inputs':{'unet_name':'old-model'}},
               '13':{'class_type':'CLIPLoader','inputs':{'clip_name':'old-text'}},
               '11':{'class_type':'VAELoader','inputs':{'vae_name':'old-vae'}},
               '24':{'class_type':'VAELoader','inputs':{'vae_name':'old-audio'}},
               's':{'class_type':'SpectrumApplyMiniMaxH3','inputs':{'enabled':True,'blend_weight':.25}}}
        result=shot_reproduce.recover_settings(source,graph)
        self.assertEqual(result['h3_models']['unet'],'old-model')
        self.assertEqual(result['acceleration_settings']['spectrum_blend_weight'],.25)
        self.assertFalse(result['acceleration_settings']['sparse_enabled'])
        self.assertIsNotNone(shot_reproduce.clone(result))

    def test_acceleration_override_is_local_and_restored_after_exception(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'acceleration.json'
            h3_acceleration.save_settings({'spectrum_enabled':False},path)
            with patch.object(h3_acceleration,'SETTINGS_PATH',path):
                with self.assertRaises(RuntimeError):
                    with h3_acceleration.render_settings({'spectrum_enabled':True,'spectrum_blend_weight':.25}):
                        self.assertTrue(h3_acceleration.load_settings()['spectrum_enabled'])
                        self.assertFalse(h3_acceleration.load_settings(path)['spectrum_enabled'])
                        raise RuntimeError('test')
                self.assertFalse(h3_acceleration.load_settings()['spectrum_enabled'])


class SceneEndpoint(unittest.IsolatedAsyncioTestCase):
    async def test_archive_replay_ignores_edited_scene_and_deduplicates_requests(self):
        source=recorded(mode='ref'); source['reproduction_snapshot']=shot_reproduce.snapshot(source)
        jobs=[]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'face.png').touch();(root/'opening.png').touch()
            with patch.object(server,'_lock',asyncio.Lock()),patch.object(server,'_jobs',jobs),patch.object(server,'_gallery',[source]),patch.object(server,'REFS',root),patch.object(server,'COMFY_INPUT',root),patch.object(server,'_save_jobs'),patch.object(server.cinema,'load',return_value={'film_id':'film','shots':[{'id':'shot','text':'edited prompt'}]}),patch.object(server.comfy,'healthy',new_callable=AsyncMock,return_value=True):
                body=server.CinemaReproduceBody(shot_id='shot',expected_film_id='film',source_job_id='old')
                result=await server.cinema_reproduce_one(body)
                second=await server.cinema_reproduce_one(body)
        self.assertEqual(len(jobs),1)
        self.assertTrue(second['already_queued'])
        self.assertEqual(result['job']['prompt'],'Original dialogue')
        self.assertEqual(source['output'],{'url':'old.mp4'})

    async def test_missing_reference_wrong_film_and_unfinished_parent_do_not_queue(self):
        for case in ('missing-reference','wrong-film','unfinished-parent'):
            source=recorded(mode='continuum' if case=='unfinished-parent' else 'ref')
            if case=='unfinished-parent': source['continue_from']='parent'
            jobs=[]
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                if case!='missing-reference':
                    (root/'face.png').touch();(root/'opening.png').touch()
                with patch.object(server,'_lock',asyncio.Lock()),patch.object(server,'_jobs',jobs),patch.object(server,'_gallery',[source]),patch.object(server,'REFS',root),patch.object(server,'COMFY_INPUT',root),patch.object(server,'_save_jobs'),patch.object(server,'_clip_record',return_value={'status':'running'}),patch.object(server.cinema,'load',return_value={'film_id':'film','shots':[{'id':'shot'}]}),patch.object(server.comfy,'healthy',new_callable=AsyncMock,return_value=True):
                    with self.assertRaises(server.HTTPException):
                        await server.cinema_reproduce_one(server.CinemaReproduceBody(shot_id='shot',expected_film_id='other' if case=='wrong-film' else 'film'))
            self.assertEqual(jobs,[])


if __name__=='__main__': unittest.main()
