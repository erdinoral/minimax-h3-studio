import ast
from typing import Any
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lib import cinema


class LibraryCharacterReuse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch.object(cinema, 'CINEMA_FILE', root / 'film.json'),
                        patch.object(cinema, 'LIBRARY_FILE', root / 'library.json'),
                        patch.object(cinema, '_archive_film')]
        for p in self.patches:
            p.start()
        self.donor = cinema.upsert_library_asset('character', {
            'id': 'saved-lara', 'name': 'Lara', 'notes': 'Saved armor and face',
            'voice': 'Soft voice', 'images': [{'file': 'lara_front.png', 'name': 'lara1'}]})

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_json_uses_saved_actor_with_new_film_local_id(self):
        result = cinema.import_project_json({'characters': [{'name': ' lArA ', 'notes': 'Invented face'}],
                                             'sections': []}, new_film=True)
        actor = result['cinema']['characters'][0]
        self.assertEqual(actor['image'], 'lara_front.png')
        self.assertEqual(actor['library_id'], 'saved-lara')
        self.assertNotEqual(actor['id'], 'saved-lara')
        self.assertEqual(actor['notes'], 'Saved armor and face')
        tree = ast.parse((Path(__file__).parents[1] / 'server.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_asset_needs_sheet')
        scope = {'Any': Any, 'cinema': cinema}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<sheet-gate>', 'exec'), scope)
        self.assertFalse(scope['_asset_needs_sheet'](actor))
        self.assertTrue(scope['_asset_needs_sheet'](actor, force=True))
        self.assertEqual(self.donor, cinema.load_library()['characters'][0])

    def test_library_match_is_scoped_to_each_asset_kind(self):
        for kind, group in [('creature', 'creatures'), ('location', 'locations'), ('vehicle', 'vehicles')]:
            cinema.upsert_library_asset(kind, {'id': f'{kind}-saved', 'name': 'Shared Name',
                'images': [{'file': f'{kind}.png'}]})
        result = cinema.import_project_json({
            'creatures': [{'name': 'shared name'}], 'locations': [{'name': 'Shared Name'}],
            'vehicles': [{'name': 'Shared Name'}]}, new_film=True)
        for kind, group in [('creature', 'creatures'), ('location', 'locations'), ('vehicle', 'vehicles')]:
            actor = result['cinema'][group][0]
            self.assertEqual(actor['image'], f'{kind}.png')
            self.assertEqual(actor['library_id'], f'{kind}-saved')

    def test_redo_bypasses_library_and_unmatched_name_stays_new(self):
        for name, redo in [('Lara', True), ('Lara Knight', False)]:
            result = cinema.import_project_json({'characters': [{'name': name, 'notes': 'New look'}]},
                                                new_film=True, redo_characters=redo)
            actor = result['cinema']['characters'][0]
            self.assertFalse(actor['images'])
            self.assertNotIn('library_id', actor)

    def test_ai_ingest_reuses_lora_only_actor_without_generating_portrait(self):
        cinema.upsert_library_asset('character', {'id': 'nea-lib', 'name': 'NEA',
            'use_lora': True, 'lora_id': 'nea', 'lora_strength': 0.9})
        result = cinema.apply_ingest({'characters': [{'name': 'NEA'}]}, '')
        actor = result['characters'][0]
        self.assertTrue(cinema.uses_lora(actor))
        self.assertEqual(actor['lora_id'], 'nea')
        self.assertEqual(actor['lora_strength'], 0.9)
        self.assertEqual(actor['library_id'], 'nea-lib')

    def test_manual_add_reuses_but_removing_images_does_not_restore_them(self):
        actor = cinema.upsert_asset('character', {'name': 'Lara'})
        self.assertEqual(actor['image'], 'lara_front.png')
        cinema.update_asset('character', actor['id'], {'images': [], 'image': '', 'url': ''})
        result = cinema.apply_ingest({'characters': [{'name': 'Lara'}]}, '')
        self.assertFalse(result['characters'][0]['images'])
        self.assertEqual(cinema.load_library()['characters'][0]['image'], 'lara_front.png')


if __name__ == '__main__':
    unittest.main()
