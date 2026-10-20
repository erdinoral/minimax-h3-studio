import ast
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lib import video_refine
from lib.comfy import ComfyClient


class ExistingVideoRefineTests(unittest.TestCase):
    def test_saved_video_is_selected_instead_of_loader_input_preview(self):
        source={'filename':'source.mp4','type':'input'}
        result={'filename':'enhanced.mp4','type':'output'}
        self.assertEqual(ComfyClient.extract_video_meta({'load':{'images':[source]},'save':{'images':[result]}}),result)
        self.assertIsNone(ComfyClient.extract_video_meta({'load':{'images':[source]}}))
        self.assertIsNone(ComfyClient.extract_video_meta({'image':{'images':[{'filename':'still.png','type':'output'}]}}))

    def test_output_cannot_silently_drop_frames_or_audio(self):
        source={'frames':124,'fps':24,'audio':True}
        actual={'width':1088,'height':608,**source}
        with patch.object(video_refine,'probe',return_value=actual):
            video_refine.verify_output('output.mp4',source,1088,608)
        for change in ({'frames':120},{'fps':30},{'audio':False},{'width':864}):
            with patch.object(video_refine,'probe',return_value={**actual,**change}):
                with self.assertRaises(ValueError):
                    video_refine.verify_output('output.mp4',source,1088,608)

    def test_existing_mp4_graph_preserves_audio_fps_and_frame_count_without_sampling(self):
        graph = video_refine.build({'id':'test','width':1088,'height':608,
            'h3_models':{'vae':'original.safetensors'},'refine_source_meta':{'frames':124}},'source.mp4')
        self.assertEqual(graph['load']['inputs']['file'],'source.mp4')
        self.assertEqual(graph['trim']['inputs']['length'],124)
        self.assertEqual(graph['video']['inputs']['fps'],['parts',2])
        self.assertEqual(graph['video']['inputs']['audio'],['parts',1])
        self.assertEqual(graph['upscale']['inputs']['mode.width'],1088)
        self.assertEqual(graph['92']['inputs']['filename_prefix'],'video/H3_Studio/test')
        self.assertFalse(any('Sampler' in n['class_type'] or 'Flow' in n['class_type']
                             or 'UNET' in n['class_type'] for n in graph.values()))

    def test_generate_disables_capture_before_processing_stale_clients(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'server.py').read_text(encoding='utf-8'))
        generate=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='generate')
        first=generate.body[0]
        self.assertIsInstance(first,ast.Assign)
        self.assertEqual(ast.unparse(first.targets[0]),'body.prepare_refine')
        self.assertEqual(first.value.value,False)


if __name__=='__main__':unittest.main()
