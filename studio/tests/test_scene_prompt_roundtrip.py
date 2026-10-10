import unittest
from lib import cinema, director_identity


class ScenePromptRoundtripTests(unittest.TestCase):
    def test_cast_composition_and_dialogue_do_not_merge_after_roundtrip(self):
        fields={'title':'Ainz presence','location':'Throne Room','character':'Ainz Ooal Gown',
                'opening_frame':'Ainz sits on the throne.','action':'Ainz rests his chin on his hand.',
                'beats':'0s: Ainz sits; 2s: His eyes glow.','camera':'Close-up, static.',
                'ending_frame':'Ainz tilts his head.','dialogue':'Seni dinliyorum, Albedo.',
                'dialogue_lang':'Turkish','important':'Keep his skeletal face unchanged.',
                'audio':'Low magical hum.','music':'N/A'}
        compiled=cinema.compose_h3_prompt(fields)
        parsed=cinema.parse_h3_prompt(compiled)
        for key,value in fields.items():
            self.assertEqual(parsed[key],value,key)
        shot=cinema._clean_shot({'text':compiled,'mode':'t2v'})
        self.assertEqual(shot['structured']['character'],'Ainz Ooal Gown')
        self.assertEqual(shot['text'].count('Opening composition:'),1)
        lib={'characters':[{'id':'ainz','name':'Ainz Ooal Gown'},{'id':'albedo','name':'Albedo'}]}
        self.assertEqual(director_identity.prepare_shot(shot,lib)['bindings'],[{'asset_id':'ainz'}])

    def test_legacy_camera_followed_by_dialogue_still_parses(self):
        text='integrated_multimodal_description: [Shot 1] Live-action Location: Hall Main character: Mara Action: Mara smiles. Camera: Close-up. Mara (S1) says: <d>[English] Hello.</d> Constraints: No cuts.\n\noverall_soundscape: Room tone.\n\nnon_diegetic_music: N/A'
        parsed=cinema.parse_h3_prompt(text)
        self.assertEqual(parsed['character'],'Mara')
        self.assertEqual(parsed['camera'],'Close-up.')
        self.assertEqual(parsed['dialogue'],'Hello.')
