import asyncio
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from lib import motionbricks


class MirrorTest(unittest.TestCase):
    def test_only_runtime_files_are_served(self):
        self.assertIn("js/main.js", motionbricks.FILES)
        for path in ("models/mmm_v6_g1_fp16.onnx", "media/demo.mp4", "../server.py", "README.md"):
            with self.assertRaises(FileNotFoundError):
                asyncio.run(motionbricks.ensure_file(path, Path(tempfile.gettempdir())))

    def test_cached_files_are_reused_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            cached = Path(tmp) / motionbricks.REVISION / "js" / "main.js"
            cached.parent.mkdir(parents=True)
            cached.write_text("// cached", encoding="utf-8")
            self.assertEqual(asyncio.run(motionbricks.ensure_file("js/main.js", Path(tmp))), cached)

    def test_module_scripts_get_a_javascript_type(self):
        self.assertTrue(motionbricks.media_type("js/main.js").startswith("text/javascript"))
        self.assertEqual(motionbricks.media_type("assets/g1.glb"), "model/gltf-binary")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class EncodeTakeTest(unittest.TestCase):
    def test_jpeg_stream_becomes_an_exact_24fps_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            stills = tmp / "frames"
            stills.mkdir()
            subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24",
                            "-frames:v", "100", str(stills / "%04d.jpg")], check=True)
            stream = tmp / "take.mjpeg"
            stream.write_bytes(b"".join(p.read_bytes() for p in sorted(stills.glob("*.jpg"))))
            seconds = motionbricks.encode_take(stream, tmp / "take.mp4")
            self.assertEqual(motionbricks.frame_count(tmp / "take.mp4"), 100)
            self.assertAlmostEqual(seconds, 100 / 24)


if __name__ == "__main__":
    unittest.main()
