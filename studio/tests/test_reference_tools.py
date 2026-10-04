import math
import hashlib
import shutil
import subprocess
import wave
from array import array
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import h3_models, lora_guidance, loras
from lib.media_trim import validate_range, trim_reference
from lib.frames import _probe_duration


class ReferenceToolsTests(unittest.TestCase):
    def test_bad_ranges_rejected(self):
        for start, end in [(None, 1), (0, None), (-1, 2), (1, 1), (0, 16), (0, 30), (math.nan, 3), (0, math.inf)]:
            with self.assertRaises(ValueError):
                validate_range(start, end, 20)
        self.assertEqual(validate_range(2, 5, 20), (2, 5))

    def test_active_guidance_and_edited_triggers_persist(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(lora_guidance, 'STORE', Path(temp)/'guides.json'):
                spec = next(s for s in loras.CATALOG if s.get('file'))
                lora_guidance.save_guidance(spec['file'], 'Use slow motion, keep cast.', 'ABC, DEF')
                block = lora_guidance.guidance_block([spec['file']])
                self.assertIn('Use slow motion', block)
                self.assertIn('Never override', block)
                self.assertEqual(lora_guidance.guidance_block([]), '')
                self.assertEqual(loras.apply_trigger('ABC, a person walks.', spec), 'DEF, ABC, a person walks.')

    def test_all_selected_lora_triggers_are_added_once(self):
        specs={'style.safetensors':{'trigger':'DY'}, 'motion.safetensors':{}, 'actor.safetensors':{'trigger':'chr_nea'}}
        with patch.object(loras,'find_spec',side_effect=lambda **kw:specs.get(kw.get('file'))):
            names='style.safetensors|motion.safetensors|actor.safetensors'
            prompt=loras.apply_selected_triggers('NEA walks.',lora_id='style',file=names)
            self.assertIn('DY',prompt)
            self.assertIn('chr_nea',prompt)
            self.assertEqual(loras.apply_selected_triggers(prompt,file=names),prompt)

    def test_path_traversal_guides_rejected(self):
        for name in ['../outside.safetensors', 'C:\\private.txt', 'unknown.safetensors']:
            with self.assertRaises(ValueError):
                lora_guidance.guidance(name)

    def test_auto_vae_only_for_int8_and_installed_decoder(self):
        with patch.object(h3_models, 'load', return_value={'vae':h3_models.AUTO_INT8_VAE}), patch.object(h3_models, '_list_dir', return_value=[h3_models.INT8_VIDEO_VAE]):
            self.assertEqual(h3_models.resolve()['vae'], h3_models.INT8_VIDEO_VAE)
            self.assertEqual(h3_models.resolve(overrides={'unet':'other_bf16.safetensors'})['vae'], h3_models.DEFAULT_MODELS['vae'])
        with patch.object(h3_models, 'load', return_value={'vae':h3_models.AUTO_INT8_VAE}), patch.object(h3_models, '_list_dir', return_value=[]):
            self.assertEqual(h3_models.resolve()['vae'], h3_models.DEFAULT_MODELS['vae'])

    def test_manual_vae_override_wins(self):
        with patch.object(h3_models, 'load', return_value={'vae':'user.safetensors'}):
            self.assertEqual(h3_models.resolve()['vae'], 'user.safetensors')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg not on PATH')
    def test_real_audio_excerpt_preserves_source_and_selects_requested_segment(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp)/'original.wav', Path(temp)/'trim.wav'
            rate=32000
            samples=array('h',(int(12000*math.sin(2*math.pi*(440 if i<rate else 880)*i/rate)) for i in range(rate*3)))
            with wave.open(str(source),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate);f.writeframes(samples.tobytes())
            before=hashlib.sha256(source.read_bytes()).digest()
            trim_reference(source,output,'audio',1.2,1.7)
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),before)
            with wave.open(str(output),'rb') as f:
                self.assertEqual(f.getnchannels(),2)
                self.assertAlmostEqual(f.getnframes()/f.getframerate(),0.5,places=2)
                signal=array('h',f.readframes(f.getnframes()))[::2]
            crossings=sum(a<=0<b for a,b in zip(signal,signal[1:]))
            self.assertAlmostEqual(crossings/0.5,880,delta=5)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg not on PATH')
    def test_real_video_excerpt_has_requested_duration(self):
        ffmpeg=shutil.which('ffmpeg')
        with tempfile.TemporaryDirectory() as temp:
            source, output=Path(temp)/'original.mp4',Path(temp)/'trim.mp4'
            subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','lavfi','-i',
                'testsrc=size=128x72:rate=24','-t','3','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True,timeout=30)
            before=hashlib.sha256(source.read_bytes()).digest()
            trim_reference(source,output,'video',0.75,2.25)
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),before)
            self.assertAlmostEqual(_probe_duration(ffmpeg,output),1.5,delta=0.08)


if __name__ == '__main__':
    unittest.main()
