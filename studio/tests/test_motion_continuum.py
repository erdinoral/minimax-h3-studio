import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from lib import continuum
from lib.comfy import DEFAULT_MODELS

import server


def base_job(**extra):
    job = dict(id="mc", prompt="Dance", continuum_prompts=["Dance"] * 3, duration=5, width=864, height=480,
               steps=12, seed=7, h3_models=DEFAULT_MODELS, continuum_run="mc")
    job.update(extra)
    return job


class ContinuumVideoGraph(unittest.TestCase):
    def build(self, job):
        with patch("lib.comfy.apply_spectrum", side_effect=lambda g, **kwargs: g):
            return continuum.build(job)

    def test_reference_video_follows_the_timeline(self):
        graph = self.build(base_job(continuum_ref_video="mcont-a.mp4"))
        sample = graph["c_sample"]["inputs"]
        self.assertEqual(graph["c_video_in"], {"class_type": "LoadVideo", "inputs": {"file": "mcont-a.mp4"}})
        self.assertEqual(graph["c_video_frames"]["inputs"]["video"], ["c_video_in", 0])
        self.assertEqual(sample["reference_video_1"], ["c_video_frames", 0])
        self.assertEqual(sample["video_reference_mode"], "Follow Timeline")
        self.assertEqual(sample["video_reference_size"], "Match Output")

    def test_plain_continuum_has_no_video_input(self):
        graph = self.build(base_job())
        self.assertNotIn("c_video_in", graph)
        self.assertNotIn("reference_video_1", graph["c_sample"]["inputs"])


class MotionContinuumEndpoint(unittest.TestCase):
    def queue(self, seconds, **body):
        generate = AsyncMock(side_effect=lambda run: {"id": "job1", "continuum_prompts": ["x"] * run.continuum_chunks})
        slices = []
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(server, "REF_VIDEOS", Path(tmp)), \
                patch.object(server, "_ref_video_path", return_value=Path(tmp) / "src.mp4"), \
                patch.object(server.motion_long, "probe_seconds", return_value=seconds), \
                patch.object(server.video_labels, "probe", return_value={"width": 1080, "height": 1920}), \
                patch.object(server.motion_long, "slice_reference",
                             side_effect=lambda src, out, start, sec: slices.append((start, sec)) or out), \
                patch.object(server.comfy, "upload_video", new_callable=AsyncMock, return_value="mcont-up.mp4"), \
                patch.object(server, "generate", generate):
            result = asyncio.run(server.motion_transfer_long(server.MotionTransferLongBody(
                prompt="Dance", ref_videos=["src.mp4"], join_method="continuum", **body)))
        return result, generate.await_args.args[0], slices

    def test_one_native_run_with_five_second_chunks(self):
        result, run, slices = self.queue(15.0, v2v_role="face_swap", ref_images=["me.png"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["join_method"], "continuum")
        self.assertEqual((run.mode, run.continuation_method, run.duration, run.continuum_chunks),
                         ("v2v", "continuum", 5, 3))
        self.assertTrue(run.continuum_video_follow)
        self.assertEqual(run.ref_videos, ["mcont-up.mp4"])
        self.assertEqual(run.aspect, "9:16")
        self.assertEqual((run.v2v_role, run.ref_images, run.lane), ("face_swap", ["me.png"], "motion"))
        self.assertEqual(run._motion_original_audio, "src.mp4")
        self.assertEqual(slices, [(0.0, 15.0)])

    def test_generated_audio_is_kept_when_original_audio_is_disabled(self):
        _, run, _ = self.queue(15.0, include_video_audio=False)
        self.assertIsNone(run._motion_original_audio)

    def test_chunk_count_rounds_to_the_nearest_five_seconds(self):
        _, run, slices = self.queue(16.0)
        self.assertEqual(run.continuum_chunks, 3)
        self.assertEqual(slices, [(0.0, 15.0)])
        _, run, slices = self.queue(13.0)
        self.assertEqual(run.continuum_chunks, 3)
        self.assertEqual(slices, [(0.0, 13.0)])
        _, run, _ = self.queue(4.0)
        self.assertEqual(run.continuum_chunks, 1)

    def test_timed_actions_stay_in_one_prompt(self):
        _, run, _ = self.queue(10.0, beats=[{"start": 0, "text": "walks"}, {"start": 6, "text": "jumps"}])
        self.assertEqual(run.prompt, "Dance In this shot: walks. Then jumps.")
        self.assertIsNone(run.continuum_segment_prompts)

    def test_unknown_join_method_is_refused(self):
        with patch.object(server, "_ref_video_path", return_value=Path("src.mp4")), \
                patch.object(server.motion_long, "probe_seconds", return_value=10.0):
            with self.assertRaises(server.HTTPException):
                asyncio.run(server.motion_transfer_long(server.MotionTransferLongBody(
                    prompt="Dance", ref_videos=["src.mp4"], join_method="other")))


if __name__ == "__main__":
    unittest.main()
