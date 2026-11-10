import unittest
from unittest.mock import AsyncMock, patch
from lib import qwen_still


class AssetMethodTests(unittest.IsolatedAsyncioTestCase):
    async def test_h3_draws_from_a_video_and_other_methods_with_h3_image(self):
        import server
        for method, provider, target in (('h3', 'image_studio', '_queue_cinema_sheet_job'),
                                         (None, 'minimax', '_queue_cinema_sheet_job'),
                                         ('qwen', 'minimax', '_queue_cinema_qwen_sheet_job'),
                                         ('sheet', 'minimax', '_queue_cinema_qwen_sheet_job'),
                                         (None, 'image_studio', '_queue_cinema_qwen_sheet_job')):
            queue = AsyncMock(return_value={'job':{'id':'test'}})
            with patch.object(server.comfy, 'healthy', AsyncMock(return_value=True)), patch.object(server, target, queue):
                await server.cinema_generate_sheet(server.CinemaSheetBody(name='Lara', ref_image='source.png', production_method=method, image_provider=provider))
            self.assertEqual(queue.call_args.kwargs['ref_image'], 'source.png', (method, provider))

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
