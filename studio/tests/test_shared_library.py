import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lib import cinema


class SharedLibrary(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        self.root=root
        self.patches=[patch.object(cinema,'CINEMA_FILE',root/'current.json'),
                      patch.object(cinema,'FILMS_DIR',root/'films'),
                      patch.object(cinema,'LIBRARY_FILE',root/'library.json')]
        for p in self.patches: p.start()
        (root/'films').mkdir()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def film(self,fid,**assets):
        data={'film_id':fid,'title':fid,**assets}
        (self.root/'films'/f'{fid}.json').write_text(json.dumps(data),encoding='utf8')
        return data

    def test_all_films_share_one_pool_without_rewriting_films(self):
        a=self.film('a',characters=[{'id':'one','name':'Doom','image':'doom.png'}],vehicles=[{'id':'car','name':'Car','image':'car.png'}])
        b=self.film('b',characters=[{'id':'two','name':'Sue','image':'sue.png'}],locations=[{'id':'room','name':'Room','image':'room.png'}],creatures=[{'id':'dragon','name':'Dragon','image':'dragon.png'}])
        cinema.CINEMA_FILE.write_text(json.dumps(a),encoding='utf8')
        before={p:p.read_bytes() for p in [cinema.CINEMA_FILE,*cinema.FILMS_DIR.glob('*.json')]}
        result=cinema.sync_shared_library()
        self.assertEqual(result['imported'],5)
        self.assertEqual({c['name'] for c in result['library']['characters']},{'Doom','Sue'})
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        cinema.CINEMA_FILE.write_text(json.dumps(b),encoding='utf8')
        again=cinema.sync_shared_library()
        self.assertEqual(again['imported'],0)
        self.assertEqual({c['id'] for c in again['library']['characters']},{'one','two'})

    def test_same_asset_copy_and_exact_duplicates_do_not_create_extra_cards(self):
        self.film('a',characters=[{'id':'a','name':'Doom','image':'doom.png'}])
        self.film('b',characters=[{'id':'b','name':'Doom','image':'doom.png'}, {'id':'c','library_id':'a','name':'Doom','image':'doom.png'}])
        result=cinema.sync_shared_library()['library']
        self.assertEqual(len(result['characters']),1)
        self.assertEqual(cinema.sync_shared_library()['imported'],0)

    def test_same_name_different_reference_is_preserved(self):
        self.film('a',characters=[{'id':'a','name':'Doom','image':'green.png'}])
        self.film('b',characters=[{'id':'b','name':'Doom','image':'white.png'}])
        self.assertEqual(len(cinema.sync_shared_library()['library']['characters']),2)

    def test_deleted_global_card_does_not_reappear_from_a_film(self):
        self.film('a',characters=[{'id':'a','name':'Doom','image':'doom.png'}])
        self.film('b',characters=[{'id':'b','name':'Doom','image':'doom.png'}])
        asset=cinema.sync_shared_library()['library']['characters'][0]
        self.assertTrue(cinema.delete_library_asset('character',asset['id']))
        self.assertEqual(cinema.sync_shared_library()['library']['characters'],[])
        cinema.upsert_library_asset('character',asset)
        self.assertEqual(len(cinema.sync_shared_library()['library']['characters']),1)

    def test_imported_asset_picks_up_its_source_update_but_explicit_save_is_protected(self):
        self.film('a',characters=[{'id':'a','name':'Doom','image':'one.png'}])
        cinema.sync_shared_library()
        self.film('a',characters=[{'id':'a','name':'Doom','image':'two.png'}])
        self.assertEqual(cinema.sync_shared_library()['library']['characters'][0]['image'],'two.png')
        cinema.upsert_library_asset('character',{'id':'a','name':'Doom','image':'chosen.png'})
        self.assertEqual(cinema.sync_shared_library()['library']['characters'][0]['image'],'chosen.png')

    def test_second_sync_does_not_write_again(self):
        self.film('a',characters=[{'id':'a','name':'Doom','image':'one.png'}])
        cinema.sync_shared_library()
        before=cinema.LIBRARY_FILE.read_bytes()
        cinema.sync_shared_library()
        self.assertEqual(cinema.LIBRARY_FILE.read_bytes(),before)

    def test_pull_changes_only_active_film_and_keeps_shared_identity(self):
        self.film('a',characters=[{'id':'a','name':'Doom','image':'doom.png'}])
        cinema.CINEMA_FILE.write_text(json.dumps({'film_id':'b','characters':[]}),encoding='utf8')
        asset=cinema.sync_shared_library()['library']['characters'][0]
        cinema.pull_library_to_film('character',asset['id'])
        self.assertEqual(len(cinema.load()['characters']),1)
        self.assertEqual(cinema.load()['characters'][0]['library_id'],asset['id'])
        cinema.pull_library_to_film('character',asset['id'])
        self.assertEqual(len(cinema.load()['characters']),1)
        self.assertEqual(len(cinema.sync_shared_library()['library']['characters']),1)


if __name__=='__main__': unittest.main()
