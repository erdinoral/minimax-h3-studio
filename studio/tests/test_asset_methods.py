import unittest
from unittest.mock import AsyncMock, patch
from lib import qwen_still


class AssetMethodTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_method_never_switches_when_a_reference_is_present(self):
        import server
        for method in ('h3', 'qwen', 'sheet'):
            h3 = AsyncMock(return_value={'job':{'id':'test'}})
            qwen = AsyncMock(return_value={'job':{'id':'test'}})
            with patch.object(server.comfy, 'healthy', AsyncMock(return_value=True)), patch.object(server.cinema, 'load', return_value={}), patch.object(server, '_queue_cinema_sheet_job', h3), patch.object(server, '_queue_cinema_qwen_sheet_job', qwen):
                await server.cinema_generate_sheet(server.CinemaSheetBody(name='Lara', ref_image='source.png', production_method=method, image_provider='image_studio'))
            if method == 'qwen':
                h3.assert_not_called()
                self.assertEqual(qwen.call_args.kwargs['ref_image'], 'source.png')
            else:
                qwen.assert_not_called()
                self.assertEqual(h3.call_args.kwargs['sheet_method'], 'look_sheets' if method == 'sheet' else 'standard')

    def test_qwen_edit_generates_separate_views_from_the_original_source(self):
        for kind, count in [('character',5), ('vehicle',4), ('location',4)]:
            graph=qwen_still.build_reference_views(kind=kind,notes='same identity',style_line='realistic',source_image='source.png',steps=20,seed=8,width=480,height=864)
            self.assertEqual(graph['10']['inputs']['unet_name'],qwen_still.EDIT_MODEL)
            self.assertEqual(len([n for n in graph if n.startswith('70_')]),count)
            samplers=[node for node in graph.values() if node['class_type']=='KSampler']
            self.assertEqual(len(samplers),count)
            self.assertTrue(all(node['inputs']['denoise']==1.0 for node in samplers))
            self.assertFalse(any(node['class_type']=='ImageScale' for node in graph.values()))
            for index in range(count):
                self.assertEqual(graph[f'view_{index}_text']['class_type'],'TextEncodeQwenImageEditPlus')
                self.assertEqual(graph[f'view_{index}_text']['inputs']['image1'],['25',0])
                self.assertEqual(graph[f'70_{index}']['inputs']['images'],[f'view_{index}_decode',0])
