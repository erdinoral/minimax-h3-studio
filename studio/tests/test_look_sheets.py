import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from lib import cinema, look_sheets
from lib.comfy import build_ref2va_prompt


class LookSheetsTests(unittest.TestCase):
    def test_real_frame_batch_and_sheet_outputs_are_separate(self):
        for kind, count in [('character', 5), ('vehicle', 4), ('location', 4)]:
            graph = build_ref2va_prompt(text=look_sheets.prompt(kind), ref_image_names=['source.png'], silent_audio=True)
            look_sheets.add_nodes(graph, kind, 'test')
            self.assertEqual(graph['look_frames']['inputs']['saved_frame_count'], count)
            self.assertEqual(graph['look_frames']['inputs']['images'], ['10', 0])
            self.assertEqual(graph['look_save_views']['inputs']['images'], ['look_frames', 0])
            self.assertEqual(graph['look_save_sheet']['inputs']['images'], ['look_sheet', 0])
            self.assertIn('rear, right side, left side', look_sheets.prompt('vehicle'))

    def test_identity_and_clothing_references_have_distinct_roles(self):
        prompt = look_sheets.prompt('character', outfit=True)
        self.assertIn('<Picture 1>', prompt)
        self.assertIn('<Picture 2> defines clothing only', prompt)
        asset = cinema._clean_asset({'name':'Ada', 'source_ref':'source.png', 'sheet_overview':'sheet.png'}, 'character')
        self.assertEqual(asset['source_ref'], 'source.png')
        self.assertEqual(asset['sheet_overview'], 'sheet.png')


class LookSheetsEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_views_attach_without_cropping_and_deleted_cards_stay_deleted(self):
        import server
        actor = {'id':'a', 'kind':'character', 'name':'Ada', 'source_ref':'source.png', 'images':[]}
        outputs = [{'filename':f'view{i}.png'} for i in range(5)]
        job = {'sheet_view_outputs':outputs, 'sheet_overview_outputs':[{'filename':'sheet.png'}]}
        async def download(filename, subfolder, kind, dest):
            dest.write_bytes(b'image')
        async def upload(dest, filename):
            return filename
        with tempfile.TemporaryDirectory() as temp, patch.object(server, 'REFS', Path(temp)), patch.object(server.cinema, 'load', return_value={'characters':[copy.deepcopy(actor)]}), patch.object(server.cinema, 'update_asset', return_value=actor) as update, patch.object(server.comfy, 'download_view', AsyncMock(side_effect=download)), patch.object(server.comfy, 'upload_image', AsyncMock(side_effect=upload)), patch.object(server.cinema, 'split_tripanel_still') as split:
            await server._attach_look_sheet_views(job, 'character', 'a')
        split.assert_not_called()
        fields = update.call_args.args[2]
        self.assertEqual(len(fields['images']), 5)
        self.assertEqual(fields['source_ref'], 'source.png')
        self.assertTrue(job['sheet_attached'])
        with patch.object(server.cinema, 'load', return_value={}), patch.object(server.cinema, 'update_asset') as update:
            with self.assertRaisesRegex(ValueError, 'deleted'):
                await server._attach_look_sheet_views(job, 'character', 'a')
        update.assert_not_called()

    async def test_manual_images_are_not_silently_discarded(self):
        import server
        job = {'sheet_view_outputs':[{'filename':f'v{i}.png'} for i in range(5)]}
        actor = {'id':'a', 'kind':'character', 'images':[{'file':'manual.png'}]}
        with patch.object(server.cinema, 'load', return_value={'characters':[actor]}), patch.object(server.comfy, 'download_view', AsyncMock()) as download:
            with self.assertRaisesRegex(ValueError, 'image slots'):
                await server._attach_look_sheet_views(job, 'character', 'a')
        download.assert_not_called()
