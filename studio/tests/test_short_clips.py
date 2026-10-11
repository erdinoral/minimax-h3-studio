import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from lib.frames import duration_to_length, trim_short_clip


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class ShortClipTests(unittest.TestCase):
    def test_short_inserts_keep_four_second_generation_grid(self):
        self.assertEqual(duration_to_length(2), duration_to_length(4))
        self.assertEqual(duration_to_length(3), duration_to_length(4))
        self.assertEqual(duration_to_length(5), 124)

    def test_exact_duration_and_optional_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            for seconds, audio in ((2, False), (3, True)):
                with self.subTest(seconds=seconds, audio=audio):
                    path = Path(directory) / f"clip-{seconds}.mp4"
                    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                           "testsrc2=size=160x96:rate=24:duration=4.5"]
                    if audio:
                        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=4.5"]
                    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
                    subprocess.run(cmd, check=True, capture_output=True)
                    trim_short_clip(path, seconds)
                    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams",
                                             "-show_format", "-of", "json", str(path)],
                                            check=True, capture_output=True, text=True)
                    data = json.loads(result.stdout)
                    self.assertAlmostEqual(float(data["format"]["duration"]), seconds, places=2)
                    video = next(s for s in data["streams"] if s["codec_type"] == "video")
                    self.assertEqual(int(video["nb_frames"]), seconds * 24)
                    self.assertEqual(any(s["codec_type"] == "audio" for s in data["streams"]), audio)
                    self.assertEqual((video["width"], video["height"]), (160, 96))


if __name__ == "__main__":
    unittest.main()
