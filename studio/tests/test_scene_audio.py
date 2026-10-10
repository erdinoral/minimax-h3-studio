import sys
import tempfile
import unittest
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import scene_audio
from studio.tests import test_asset_references as reference_tests


class SceneAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_clip_audio_routes_to_reference_model_or_original_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            name = 'h3_voice_test_trim.wav'
            (Path(tmp) / name).write_bytes(b'audio')
            for mode in ['reference', 'original']:
                env = reference_tests.SharedQueueTests().env()
                env['REF_AUDIOS'] = Path(tmp)
                body = env['GenerateBody'](prompt='A woman talks.', mode='t2v',
                    scene_audio_file=name, scene_audio_mode=mode, silent_audio=True)
                job = await env['generate'](body)
                self.assertEqual(job['scene_audio_file'], name)
                self.assertEqual(job['scene_audio_mode'], mode)
                self.assertEqual(job['silent_audio'], mode == 'original')

    def test_only_owned_existing_uploads_and_known_modes_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, mode in [('../secret.wav', 'original'), ('missing.wav', 'reference'),
                               ('h3_voice_test.wav', 'invalid')]:
                with self.assertRaises(ValueError):
                    scene_audio.validate_source(name, mode, tmp)

    def test_original_audio_is_padded_instead_of_shortening_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'clip.mp4'; video.write_bytes(b'video')
            def run(command, **kwargs):
                self.assertIn('apad', command)
                Path(command[-1]).write_bytes(b'with audio')
                return type('Result', (), {'returncode': 0})()
            with patch('lib.music._ffmpeg', return_value='ffmpeg'), patch('subprocess.run', side_effect=run):
                scene_audio.replace_audio(video, Path(tmp) / 'voice.wav')
            self.assertEqual(video.read_bytes(), b'with audio')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg is required')
    def test_real_short_audio_keeps_video_duration_and_creates_audio_stream(self):
        from lib.music import probe_duration_sec
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'clip.mp4'; source = Path(tmp) / 'voice.wav'
            for arguments in [
                ['-f','lavfi','-i','color=c=blue:s=64x64:r=24:d=2','-c:v','libx264',str(video)],
                ['-f','lavfi','-i','sine=frequency=440:duration=0.5',str(source)],
            ]:
                subprocess.run([shutil.which('ffmpeg'), '-y', '-loglevel', 'error', *arguments], check=True)
            scene_audio.replace_audio(video, source)
            self.assertAlmostEqual(probe_duration_sec(video), 2, delta=0.15)
            result = subprocess.run([shutil.which('ffprobe'), '-v','error','-select_streams','a:0',
                '-show_entries','stream=codec_type','-of','csv=p=0',str(video)], capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), 'audio')
