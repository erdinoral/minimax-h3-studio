import asyncio
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib import cinema, video_labels
from lib.director import ALLOWED_PURPOSES, normalize_purpose

SKILLS = Path(__file__).resolve().parents[1] / "skills"
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def make_clip(path: Path, seconds: int = 2) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=24", "-f", "lavfi",
                    "-i", "sine=frequency=440", "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(path)], check=True)


class CleanLabelsTests(unittest.TestCase):
    def test_rows_are_trimmed_clamped_and_defaulted(self):
        rows = video_labels.clean_labels([
            {"text": "  Krank   mili  ", "start": -2, "x": 4, "y": "0.3", "pointer": 1},
            {"text": "", "start": 0, "end": 2},
            {"text": "x" * 90, "start": 1, "end": 9},
            {"text": "backwards", "start": 3, "end": 1},
            "junk",
        ], duration=4)
        self.assertEqual([r["text"] for r in rows], ["Krank mili", "x" * video_labels.MAX_CHARS])
        first, second = rows
        self.assertEqual((first["start"], first["end"], first["x"], first["y"], first["pointer"]), (0.0, 3.0, 1.0, 0.3, True))
        self.assertEqual(second["end"], 4)

    def test_no_usable_label_is_rejected_and_count_is_capped(self):
        with self.assertRaises(ValueError):
            video_labels.clean_labels([{"text": "  "}])
        with self.assertRaises(ValueError):
            video_labels.clean_labels("nope")
        many = [{"text": f"L{i}", "start": 0, "end": 1} for i in range(30)]
        self.assertEqual(len(video_labels.clean_labels(many)), video_labels.MAX_LABELS)

    def test_layout_keeps_boxes_inside_the_frame_and_offsets_pointers(self):
        plain = {"x": 0.5, "y": 0.5, "pointer": False}
        self.assertEqual(video_labels.layout(plain, 1000, 500, 200, 40), (400, 230))
        corner = {"x": 1.0, "y": 1.0, "pointer": False}
        left, top = video_labels.layout(corner, 1000, 500, 200, 40)
        self.assertLessEqual(left + 200, 1000 - 15)
        self.assertLessEqual(top + 40, 500 - 15)
        pointer = {"x": 0.2, "y": 0.2, "pointer": True}
        left, top = video_labels.layout(pointer, 1000, 500, 200, 40)
        self.assertGreater(left, 200)
        self.assertGreater(top, 100)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is required")
class BurnTests(unittest.TestCase):
    def test_burn_keeps_size_and_audio_and_only_changes_labelled_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "src.mp4", Path(tmp) / "out.mp4"
            make_clip(src)
            info = video_labels.burn(src, out, [{"text": "Piston · Silindir", "start": 1, "end": 2, "x": 0.3, "y": 0.6, "pointer": True}])
            self.assertEqual((info["width"], info["height"]), (320, 240))
            self.assertEqual(len(info["labels"]), 1)
            streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
                                     capture_output=True, text=True, check=True).stdout.split()
            self.assertEqual(sorted(streams), ["audio", "video"])
            self.assertFalse(out.with_name("out.part.mp4").exists())

            def frame(path, at):
                return subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(path), "-frames:v", "1", "-f", "rawvideo",
                                       "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout

            def diff(a, b):
                return sum(abs(x - y) for x, y in zip(a, b)) / len(a)

            self.assertLess(diff(frame(src, 0.3), frame(out, 0.3)), 3)
            self.assertGreater(diff(frame(src, 1.5), frame(out, 1.5)), 3)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is required")
class LabelEndpointTests(unittest.TestCase):
    def test_labels_create_a_new_gallery_video_without_continuation_state(self):
        import server
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.mp4"
            make_clip(src)
            source = {"id": "src-1", "status": "done", "mode": "ref", "lane": "scene", "prompt": "engine cutaway",
                      "purpose": "explainer", "seed": 7, "local_path": str(src), "continuation_source_id": "older",
                      "continuum_run": True, "width": 320, "height": 240}
            archived = []

            async def ensure(_rec):
                return src

            with mock.patch.object(server, "CLIPS", Path(tmp)), \
                    mock.patch.object(server, "_jobs", []), \
                    mock.patch.object(server, "_lock", asyncio.Lock()), \
                    mock.patch.object(server, "_save_jobs", lambda: None), \
                    mock.patch.object(server, "_archive_job_to_gallery", archived.append), \
                    mock.patch.object(server, "_clip_record", lambda cid: source if cid == "src-1" else None), \
                    mock.patch.object(server, "_ensure_job_video", ensure):
                client = TestClient(server.app)
                self.assertEqual(client.post("/api/clips/missing/labels", json={"labels": [{"text": "a"}]}).status_code, 404)
                self.assertEqual(client.post("/api/clips/src-1/labels", json={"labels": [{"text": " "}]}).status_code, 400)
                r = client.post("/api/clips/src-1/labels", json={"labels": [{"text": "Piston", "start": 0, "end": 1}]})
                self.assertEqual(r.status_code, 200, r.text)
                job = r.json()
                self.assertNotEqual(job["id"], "src-1")
                self.assertEqual((job["status"], job["mode"], job["lane"], job["purpose"]), ("done", "ref", "scene", "explainer"))
                self.assertEqual(job["labels_source_id"], "src-1")
                self.assertEqual(job["overlay_labels"][0]["text"], "Piston")
                self.assertNotIn("continuation_source_id", job)
                self.assertNotIn("continuum_run", job)
                self.assertTrue((Path(tmp) / f"{job['id']}.mp4").is_file())
                self.assertEqual([j["id"] for j in server._jobs], [job["id"]])
                self.assertEqual(archived[0]["id"], job["id"])
                self.assertTrue(src.is_file())


class ExplainerPurposeTests(unittest.TestCase):
    def test_purpose_is_allowed_and_recognised_in_every_ui_language(self):
        self.assertIn("explainer", ALLOWED_PURPOSES)
        for raw in ("Nasıl çalışır videosu", "how it works", "Comment ça marche", "cómo funciona", "Wie funktioniert ein Motor"):
            self.assertEqual(normalize_purpose("", raw), "explainer", raw)
        self.assertEqual(normalize_purpose("explainer"), "explainer")
        self.assertEqual(normalize_purpose("", "belgesel"), "documentary")

    def test_explainer_looks_have_setup_hints_and_craft_packs(self):
        self.assertIn("explainer", cinema.SETUP_HINTS["purpose"])
        craft = json.loads((SKILLS / "packs" / "genre_craft.json").read_text(encoding="utf-8"))
        catalog = {p["id"] for p in json.loads((SKILLS / "catalog.json").read_text(encoding="utf-8"))["packs"]}
        for look in ("technical_cutaway", "xray", "blueprint"):
            self.assertIn(look, cinema.SETUP_HINTS["look"])
            self.assertEqual(craft[look]["setup"]["purpose"], "explainer")
            self.assertIn("spelled exactly", craft[look]["craft"])
            self.assertIn("misspelled", craft[look]["avoid"])
            self.assertIn(look, catalog)

    def test_director_writes_quoted_labels_into_explainer_prompts(self):
        prompt = (Path(__file__).resolve().parents[1] / "prompts" / "director_system.md").read_text(encoding="utf-8")
        self.assertIn("`explainer`", prompt)
        self.assertIn('label reading "PISTON"', prompt)
        self.assertIn("step", prompt)

    def test_explainer_opening_frame_allows_exact_labels_only(self):
        shot = {"structured": {"action": 'A cutaway engine with a label reading "PISTON".'}}
        plain = cinema.storyboard_frame_prompt(shot, [])
        labelled = cinema.storyboard_frame_prompt(shot, [], allow_text=True)
        self.assertIn("No text", plain)
        self.assertNotIn("No text", labelled)
        self.assertIn("spelled exactly", labelled)
        self.assertIn("text,", cinema.STORYBOARD_FRAME_NEGATIVE)
        self.assertNotIn(" text,", cinema.STORYBOARD_FRAME_NEGATIVE_LABELS.replace("misspelled text,", ""))
        self.assertIn("garbled letters", cinema.STORYBOARD_FRAME_NEGATIVE_LABELS)


if __name__ == "__main__":
    unittest.main()
