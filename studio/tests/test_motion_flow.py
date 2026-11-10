import asyncio
import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, UploadFile

import server


def sketch_job(**extra):
    job = {"id": "s1", "mode": "sketch_frame", "lane": "motion", "status": "done", "frame_name": "h3_sketch_a.png",
           "frame_url": "/api/refs/h3_sketch_a.png", "sketch_state": "awaiting_approval",
           "sketch_args": {"source": "board.png", "text": "a man", "style": "", "fidelity": "balanced",
                           "method": "edit", "aspect": "16:9"},
           "video_body": {"prompt": "walks", "duration": 5, "aspect": "16:9", "quality": "736", "mode": "i2v"}}
    job.update(extra)
    return job


class SketchApprovalTest(unittest.TestCase):
    def run_patched(self, jobs, coro_factory, **mocks):
        generate = mocks.get("generate") or AsyncMock(return_value={"id": "video1"})
        with patch.object(server, "_lock", asyncio.Lock()), patch.object(server, "_jobs", jobs), \
                patch.object(server, "_save_jobs"), patch.object(server, "generate", generate), \
                patch.object(server, "_ensure_queue_loop"), \
                patch.object(server, "_require_sketch_models", new_callable=AsyncMock), \
                patch.object(server.comfy, "healthy", new_callable=AsyncMock, return_value=True):
            return asyncio.run(coro_factory()), generate

    def test_repeated_approval_queues_one_video(self):
        job = sketch_job()
        jobs = [job]

        async def twice():
            first = await server.sketch_animate("s1", server.SketchAnimateBody(prompt="dances"))
            second = await server.sketch_animate("s1", server.SketchAnimateBody())
            return first, second

        (first, second), generate = self.run_patched(jobs, twice)
        self.assertEqual(generate.await_count, 1)
        body = generate.await_args.args[0]
        self.assertEqual(body.first_frame_name, "h3_sketch_a.png")
        self.assertEqual(body.prompt, "dances")
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(job["video_job_id"], "video1")
        self.assertEqual(job["sketch_state"], "approved")
        self.assertNotIn("sketch_animating", job)

    def test_approval_in_flight_or_unfinished_frame_is_refused(self):
        for job in (sketch_job(sketch_animating=True), sketch_job(status="running", frame_name=None)):
            with self.assertRaises(HTTPException) as ctx:
                self.run_patched([job], lambda: server.sketch_animate("s1", server.SketchAnimateBody()))
            self.assertEqual(ctx.exception.status_code, 409)

    def test_failed_queue_releases_the_approval(self):
        job = sketch_job()
        failing = AsyncMock(side_effect=HTTPException(503, "ComfyUI kapalı"))
        with self.assertRaises(HTTPException):
            self.run_patched([job], lambda: server.sketch_animate("s1", server.SketchAnimateBody()), generate=failing)
        self.assertNotIn("sketch_animating", job)
        self.assertNotIn("video_job_id", job)

    def test_regenerate_before_approval_reuses_the_card(self):
        job = sketch_job()
        jobs = [job]
        result, _ = self.run_patched(jobs, lambda: server.sketch_regenerate(
            "s1", server.SketchRegenerateBody(sketch_text="a woman", sketch_method="img2img")))
        self.assertIs(result, job)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["sketch_state"], "framing")
        self.assertEqual(job["sketch_frames"], ["/api/refs/h3_sketch_a.png"])
        self.assertNotIn("frame_name", job)
        self.assertEqual(job["sketch_args"]["text"], "a woman")
        self.assertEqual(job["sketch_args"]["method"], "edit")
        self.assertEqual(job["sketch_args"]["source"], "board.png")

    def test_regenerate_after_approval_adds_a_new_card(self):
        job = sketch_job(video_job_id="video1", sketch_state="approved")
        jobs = [job]
        result, _ = self.run_patched(jobs, lambda: server.sketch_regenerate("s1", server.SketchRegenerateBody()))
        self.assertEqual(len(jobs), 2)
        self.assertIsNot(result, job)
        self.assertEqual(result["status"], "queued")
        self.assertNotIn("video_job_id", result)
        self.assertEqual(job["frame_name"], "h3_sketch_a.png")

    def test_finished_frame_waits_for_approval_instead_of_queueing_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            still = Path(tmp) / "out.png"
            still.write_bytes(b"png")
            job = sketch_job(status="running", frame_name=None, frame_url=None, sketch_state="framing")
            generate = AsyncMock()
            with patch.object(server, "REFS", Path(tmp)), patch.object(server, "_save_jobs"), \
                    patch.object(server, "generate", generate), \
                    patch.object(server.comfy, "upload_image", new_callable=AsyncMock,
                                 side_effect=lambda path, name: name):
                asyncio.run(server._finish_sketch_frame(job, still))
        generate.assert_not_awaited()
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["sketch_state"], "awaiting_approval")
        self.assertTrue(job["frame_url"].startswith("/api/refs/h3_sketch_"))

    def test_restart_clears_in_flight_flags(self):
        jobs = [sketch_job(sketch_animating=True), {"id": "p1", "motion_long_merge": "running"}]
        server._recover_motion_flags(jobs)
        self.assertNotIn("sketch_animating", jobs[0])
        self.assertEqual(jobs[0]["sketch_state"], "awaiting_approval")
        self.assertEqual(jobs[1]["motion_long_merge"], "error")
        self.assertTrue(jobs[1]["motion_long_error"])


def part(index, status, **extra):
    job = {"id": f"p{index}", "mode": "v2v", "lane": "motion", "status": status, "motion_long_id": "mlong-x",
           "motion_long_index": index, "motion_long_total": 3, "created_at": time.time(),
           "motion_long_window": {"skip": 0, "frames": 120}, "motion_long_source": "ref.mp4"}
    if index > 1:
        job["continue_from"] = f"p{index - 1}"
    job.update(extra)
    return job


class MotionLongTest(unittest.TestCase):
    def test_resume_requeues_only_failed_parts(self):
        jobs = [part(1, "done", output={"url": "/a"}), part(2, "error", error="oom"),
                part(3, "error", error="önceki klip başarısız")]
        with patch.object(server, "_lock", asyncio.Lock()), patch.object(server, "_jobs", jobs), \
                patch.object(server, "_save_jobs"), \
                patch.object(server, "_free_llm_for_production", new_callable=AsyncMock), \
                patch.object(server.comfy, "healthy", new_callable=AsyncMock, return_value=True):
            result = asyncio.run(server.motion_transfer_long_resume("mlong-x"))
            self.assertEqual(result["ids"], ["p2", "p3"])
            self.assertEqual([j["status"] for j in jobs], ["done", "queued", "queued"])
            self.assertEqual(jobs[0]["output"], {"url": "/a"})
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(server.motion_transfer_long_resume("mlong-x"))
            self.assertEqual(ctx.exception.status_code, 409)

    def test_concurrent_joins_produce_one_clip(self):
        jobs = [part(i, "done") for i in (1, 2, 3)]
        calls = []

        def slow_assemble(items, out, audio):
            calls.append(out)
            time.sleep(0.05)
            out.write_bytes(b"mp4")

        async def both():
            return await asyncio.gather(server._assemble_motion_long("mlong-x"),
                                        server._assemble_motion_long("mlong-x"))

        with tempfile.TemporaryDirectory() as tmp, patch.object(server, "_jobs", jobs), \
                patch.object(server, "_save_jobs"), patch.object(server, "CLIPS", Path(tmp)), \
                patch.object(server, "_motion_long_locks", {}), \
                patch.object(server, "_ensure_job_video", new_callable=AsyncMock, return_value=Path(tmp) / "p.mp4"), \
                patch.object(server, "_prepare_last_frame", new_callable=AsyncMock), \
                patch.object(server, "_archive_job_to_gallery"), \
                patch.object(server.motion_long, "assemble", side_effect=slow_assemble):
            first, second = asyncio.run(both())
        self.assertEqual(len(calls), 1)
        self.assertIs(first, second)
        self.assertEqual(sum(1 for j in jobs if j.get("mode") == "motion_long"), 1)
        self.assertTrue(all(j.get("motion_long_merge") == "done" for j in jobs if j.get("mode") == "v2v"))

    def test_failed_join_is_recorded_on_every_part(self):
        jobs = [part(i, "done") for i in (1, 2, 3)]
        with tempfile.TemporaryDirectory() as tmp, patch.object(server, "_jobs", jobs), \
                patch.object(server, "_save_jobs"), patch.object(server, "CLIPS", Path(tmp)), \
                patch.object(server, "_motion_long_locks", {}), \
                patch.object(server, "_ensure_job_video", new_callable=AsyncMock, return_value=Path(tmp) / "p.mp4"), \
                patch.object(server.motion_long, "assemble", side_effect=RuntimeError("ffmpeg failed")):
            with self.assertRaises(RuntimeError):
                asyncio.run(server._assemble_motion_long("mlong-x"))
        self.assertTrue(all(j["motion_long_merge"] == "error" for j in jobs))
        self.assertTrue(all("ffmpeg failed" in j["motion_long_error"] for j in jobs))


class RobotTakeTest(unittest.TestCase):
    def test_take_is_kept_when_comfy_is_closed(self):
        def encode(frames, dest):
            dest.write_bytes(b"mp4")
            return 5.0

        with tempfile.TemporaryDirectory() as tmp:
            refs, comfy_input = Path(tmp) / "refs", Path(tmp) / "input"
            refs.mkdir()
            upload = UploadFile(file=io.BytesIO(b"\xff\xd8jpeg\xff\xd9"), filename="robot_take.mjpeg")
            with patch.object(server, "REF_VIDEOS", refs), patch.object(server, "COMFY_INPUT", comfy_input), \
                    patch.object(server.comfy, "healthy", new_callable=AsyncMock, return_value=False), \
                    patch.object(server.comfy, "upload_video", new_callable=AsyncMock) as comfy_upload, \
                    patch.object(server.motionbricks, "encode_take", side_effect=encode):
                data = asyncio.run(server.motionbricks_take(upload))
            comfy_upload.assert_not_awaited()
            self.assertEqual(data["seconds"], 5.0)
            self.assertTrue((comfy_input / data["name"]).is_file())
            self.assertTrue((refs / data["filename"]).is_file())


if __name__ == "__main__":
    unittest.main()
