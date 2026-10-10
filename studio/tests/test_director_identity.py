import unittest
import copy
from unittest.mock import AsyncMock, patch
from lib import director_identity


class DirectorIdentityTests(unittest.TestCase):
    def film(self):
        return {"characters":[
            {"id":"albedo","kind":"character","name":"Albedo","use_lora":True,"lora_id":"albedo-h3","voice":"soft melodic"},
            {"id":"ainz","kind":"character","name":"Ainz","voice":"deep resonant","images":[{"file":"ainz.png"}]}
        ],"locations":[{"id":"throne","name":"Throne Room","images":[{"file":"throne.png"}]}]}

    def test_six_shots_keep_cast_separate_and_modes_intact(self):
        lib=self.film()
        for i,name in enumerate(['Albedo','Albedo','Ainz','Ainz','Albedo','Ainz, Albedo']):
            raw={"id":str(i),"text":f'Main character: {name} Opening composition: Throne Room.',
                 "structured":{"character":name},"mode":"continue" if i in (1,3) else "t2v"}
            prepared=director_identity.prepare_shot(raw,lib)
            ids={b['asset_id'] for b in prepared['bindings']}
            self.assertEqual('albedo' in ids,'Albedo' in name)
            self.assertEqual('ainz' in ids,'Ainz' in name)
            self.assertIn('throne',ids)
            self.assertEqual(raw['mode'],prepared['mode'])
            prompt=director_identity.prompt_for_shot(prepared,lib)
            self.assertEqual('soft melodic' in prompt,'Albedo' in name)
            self.assertEqual('deep resonant' in prompt,'Ainz' in name)

    def test_old_offscreen_binding_removed_but_selected_image_preserved(self):
        raw={"text":"Ainz sits.","structured":{"character":"Ainz"},
             "bindings":[{"asset_id":"albedo"},{"asset_id":"ainz","files":["ainz.png"]},{"asset_id":"throne"}]}
        original=copy.deepcopy(raw)
        prepared=director_identity.prepare_shot(raw,self.film())
        self.assertEqual(prepared['bindings'],raw['bindings'][1:])
        self.assertEqual(raw,original)

    def test_unknown_cast_rejected_and_free_text_selection_preserved(self):
        with self.assertRaisesRegex(ValueError,'Missing'):
            director_identity.prepare_shot({'text':'Move','structured':{'character':'Missing'}},self.film())
        raw={'text':'Albedo walks.','bindings':[{'asset_id':'albedo'}]}
        self.assertEqual(director_identity.prepare_shot(raw,self.film()),raw)

    def test_identity_record_excludes_other_actor_and_preserves_sources(self):
        actor=self.film()['characters'][1]
        rows=[{'asset':actor,'file':'ainz.png'}]
        self.assertEqual(director_identity.manifest({'hits':[actor],'rows':rows})[0]['reference_files'],['ainz.png'])


class DirectorIdentityEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_produce_one_sends_resolved_cast_and_scoped_voice_to_batch(self):
        import server
        lib=DirectorIdentityTests().film()
        lib['shots']=[{'id':'s1','text':'Main character: Albedo Opening composition: Albedo walks.',
                       'structured':{'character':'Albedo'},'mode':'t2v','bindings':[]}]
        enqueue=AsyncMock(return_value={'jobs':[]})
        with patch.object(server.cinema,'load',return_value=lib),patch.object(server,'batch',enqueue):
            await server.cinema_produce_one(server.CinemaSingleProduceBody(shot_id='s1'))
        body=enqueue.call_args.args[0]
        self.assertEqual(body.shot_bindings,[[{'asset_id':'albedo'}]])
        self.assertIn('soft melodic',body.prompts[0])
        self.assertNotIn('deep resonant',body.prompts[0])
