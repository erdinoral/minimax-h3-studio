import io
import uuid
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import server
from lib import cinema, optional_models, h3_models


class FilmLoraPersistence(unittest.TestCase):
    def test_saved_selection_and_zero_weight_survive_reload_and_unrelated_save(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(cinema,'CINEMA_FILE',Path(folder)/'cinema.json'), patch.object(cinema,'FILMS_DIR',Path(folder)/'films'):
            cinema.save({'title':'Test','shots':[], 'lora_selection':['a','b'], 'lora_weights':{'a.safetensors':0,'b.safetensors':0.6}})
            cinema.save({'title':'Renamed'})
            restored=cinema.load()
            self.assertEqual(restored['lora_selection'],['a','b'])
            self.assertEqual(restored['lora_weights'],{'a.safetensors':0,'b.safetensors':0.6})
            cinema.save({'title':'Cleared','lora_selection':[], 'lora_weights':{}})
            self.assertEqual(cinema.load()['lora_selection'],[])

    def test_hybrid_with_alternate_case_and_name_is_selectable_without_mutating_other_slots(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'diffusion_models').mkdir()
            name='MiniMax-H3-Hybrid_b25-49_INT8.safetensors'
            (root/'diffusion_models'/name).write_bytes(b'abc')
            with patch.object(optional_models,'MODELS_ROOT',root), patch.object(optional_models,'HYBRID_BYTES',3), patch.object(h3_models,'MODELS_ROOT',root), patch.object(h3_models,'SETTINGS_PATH',root/'settings.json'):
                h3_models.save({'clip':''})
                self.assertEqual(optional_models.select_engine('hybrid')['active'],'hybrid')
                self.assertEqual(h3_models.resolve('ref2va')['unet'],name)


class GalleryDownloads(unittest.IsolatedAsyncioTestCase):
    async def test_same_director_scene_can_be_queued_twice_with_distinct_jobs(self):
        film={'shots':[{'id':'scene','text':'A quiet mountain landscape.','mode':'t2v','structured':{'title':'Mountain'}}], 'audio':{'mode':'silent'}}
        async def queue(body):
            return {'jobs':[{'id':str(uuid.uuid4()),'status':'queued'}]}
        with patch.object(cinema,'load',return_value=film),patch.object(server,'batch',side_effect=queue),patch.object(server,'_save_jobs'):
            body=server.CinemaSingleProduceBody(shot_id='scene')
            first=await server.cinema_produce_one(body)
            second=await server.cinema_produce_one(body)
            self.assertNotEqual(first['jobs'][0]['id'],second['jobs'][0]['id'])
            self.assertEqual(first['jobs'][0]['scene_title'],'Mountain')
            self.assertEqual(second['jobs'][0]['shot_id'],'scene')

    async def test_selected_zip_contains_only_selected_files_and_unique_names(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ['a','b']:(root/f'{name}.mp4').write_bytes(name.encode())
            with patch.object(server,'GALLERY',root),patch.object(server,'_gallery',[{'id':'a','prompt':'Same'},{'id':'b','prompt':'Same'}]):
                response=server.gallery_download(server.GalleryDownloadBody(ids=['b']))
                payload=b''.join([part async for part in response.body_iterator])
                with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
                    self.assertEqual(len(bundle.namelist()),1)
                    self.assertTrue(bundle.namelist()[0].endswith('_b.mp4'))
                    self.assertEqual(bundle.read(bundle.namelist()[0]),b'b')
                with self.assertRaises(server.HTTPException):
                    server.gallery_download(server.GalleryDownloadBody(ids=['missing']))

    async def test_queue_pause_does_not_cancel_or_mutate_current_job(self):
        current={'id':'active','status':'running'}
        with patch.object(server,'_jobs',[current]),patch.object(server,'_queue_paused',False):
            result=await server.pause_queue(server.QueuePauseBody(paused=True))
            self.assertTrue(result['paused'])
            self.assertEqual(current['status'],'running')
            self.assertFalse((await server.pause_queue(server.QueuePauseBody(paused=False)))['paused'])
