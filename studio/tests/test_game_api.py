import asyncio
import hashlib
import io
import json
import math
import shutil
import subprocess
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from lib.game_api import create_router
from test_game_sprites import backdrop, frame


def write_clip(path: Path, frames) -> bool:
    h, w = frames[0].shape[:2]
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", "24",
         "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(path)],
        input=b"".join(f.tobytes() for f in frames), capture_output=True)
    return proc.returncode == 0


class GameRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp())
        self.refs = self.temp / "refs"
        self.refs.mkdir()
        self.out = self.temp / "game"
        self.jobs = []
        self.requests = []
        self.saves = 0
        self.lock = asyncio.Lock()

        async def generate(body):
            self.requests.append(body)
            if body.prompt == "fail":
                raise HTTPException(503, "ComfyUI kapalı")
            job = {"id": str(uuid.uuid4()), "status": "queued", "lane": body.lane, "mode": body.mode}
            self.jobs.append(job)
            return job

        async def ensure_video(job):
            return Path(job["local_path"])

        def save():
            self.saves += 1

        app = FastAPI()
        app.include_router(create_router(
            jobs=lambda: self.jobs, lock=lambda: self.lock, save_jobs=save, generate=generate,
            body_cls=lambda **kw: SimpleNamespace(**kw), ensure_video=ensure_video,
            refs_dirs=lambda: [self.refs], out_root=lambda: self.out))
        self.client = TestClient(app)
        img = np.full((64, 64, 3), 255, np.uint8)
        img[16:48, 16:48] = (30, 180, 40)
        Image.fromarray(img).save(self.refs / "h3_ref_abc.png")

    def tearDown(self):
        self.client.close()
        shutil.rmtree(self.temp, ignore_errors=True)

    def done_job(self, frames, animation="jump", set_id="0123456789ab"):
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg missing")
        video = self.temp / f"{uuid.uuid4().hex}.mp4"
        if not write_clip(video, frames):
            self.skipTest("libx264 unavailable")
        job = {"id": str(uuid.uuid4()), "status": "done", "lane": "game", "local_path": str(video),
               "game": {"set_id": set_id, "animation": animation, "backdrop": "green", "settings": {}}}
        self.jobs.append(job)
        return job

    def test_creates_one_reference_job_per_animation(self):
        r = self.client.post("/api/game/animations", json={
            "ref": "h3_ref_abc.png", "animations": ["walk", "jump", "walk"], "backdrop": "blue",
            "description": "a knight", "quality": "480", "sprite": {"cell": 32}})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual([j["animation"] for j in data["jobs"]], ["walk", "jump"])
        for req, name in zip(self.requests, ("walk", "jump")):
            self.assertEqual((req.mode, req.lane, req.backdrop, req.aspect), ("ref", "game", "blue", "1:1"))
            self.assertEqual(req.ref_images, ["h3_ref_abc.png"])
            self.assertTrue(req.silent_audio)
            self.assertIn("a knight", req.prompt)
        self.assertEqual(self.requests[1].duration, 3)
        for job in self.jobs:
            self.assertEqual(job["game"]["set_id"], data["set_id"])
            self.assertEqual(job["game"]["settings"]["cell"], 32)
        self.assertEqual(self.saves, 2)
        sets = self.client.get("/api/game/sets").json()["sets"]
        self.assertEqual(len(sets[0]["jobs"]), 2)

    def test_render_presets_set_resolution_and_steps_without_lora(self):
        listed = {p["id"]: p for p in self.client.get("/api/game/presets").json()["render"]}
        self.assertEqual(set(listed), {"fast", "balanced", "quality"})
        self.assertEqual([k for k, p in listed.items() if p["default"]], ["balanced"])
        for preset, spec in listed.items():
            self.requests.clear()
            r = self.client.post("/api/game/animations", json={"ref": "h3_ref_abc.png", "animations": ["idle"], "preset": preset})
            self.assertEqual(r.status_code, 200, r.text)
            req = self.requests[0]
            self.assertEqual((req.quality, req.steps, req.sage_attention), (spec["quality"], spec["steps"], "auto"))
            self.assertFalse(any(k.startswith("lora") for k in vars(req)), vars(req))
            self.assertEqual(self.jobs[-1]["game"]["render"], {"preset": preset, "quality": spec["quality"], "steps": spec["steps"]})
        self.requests.clear()
        self.client.post("/api/game/animations", json={"ref": "h3_ref_abc.png", "animations": ["idle"], "quality": "736"})
        self.assertEqual((self.requests[0].quality, self.requests[0].steps), ("736", 20))

    def test_rejects_bad_requests_before_queueing(self):
        base = {"ref": "h3_ref_abc.png", "animations": ["walk"]}
        cases = [
            ({**base, "animations": ["moonwalk"]}, 400, "game.badAnimation"),
            ({**base, "ref": "../h3_ref_abc.png"}, 400, "game.badRef"),
            ({**base, "ref": "missing.png"}, 404, "game.badRef"),
            ({**base, "backdrop": "red"}, 400, "game.badBackdrop"),
            ({**base, "sprite": {"cell": 48}}, 400, "game.badSettings"),
            ({**base, "quality": "1088"}, 400, "game.badSettings"),
            ({**base, "preset": "ultra"}, 400, "game.badSettings"),
        ]
        for payload, status, code in cases:
            r = self.client.post("/api/game/animations", json=payload)
            self.assertEqual(r.status_code, status, payload)
            self.assertEqual(r.json()["detail"]["code"], code)
        self.assertEqual(self.requests, [])

    def test_backdrop_suggestion(self):
        r = self.client.post("/api/game/backdrop", json={"ref": "h3_ref_abc.png"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["suggested"], "blue")

    def test_process_reprocess_and_files(self):
        job = self.done_job([frame(dy=-int(round(30 * math.sin(math.pi * t / 23))), seed=t) for t in range(24)])
        before = hashlib.sha256(Path(job["local_path"]).read_bytes()).hexdigest()
        first = self.client.post(f"/api/game/jobs/{job['id']}/process", json={"sprite": {}})
        self.assertEqual(first.status_code, 200, first.text)
        result = first.json()
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(job["game"]["result"]["run"], result["run"])
        sheet = self.client.get(result["base_url"] + result["files"]["sheet"])
        self.assertEqual(sheet.status_code, 200)
        self.assertEqual(Image.open(io.BytesIO(sheet.content)).size, (8 * 64, 2 * 64))
        doc = self.client.get(result["base_url"] + result["files"]["json"]).json()
        self.assertEqual(doc["image"], result["files"]["sheet"])
        z = self.client.get(result["base_url"] + result["files"]["zip"])
        self.assertIn("attachment", z.headers["content-disposition"])
        self.assertIn("README.txt", zipfile.ZipFile(io.BytesIO(z.content)).namelist())
        frame0 = self.client.get(result["base_url"] + result["files"]["frames"][0])
        self.assertEqual(frame0.status_code, 200)

        second = self.client.post(f"/api/game/jobs/{job['id']}/process", json={"sprite": {"cell": 32, "palette": 16}})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertNotEqual(second.json()["run"], result["run"])
        self.assertEqual(job["game"]["settings"]["cell"], 32)
        self.assertEqual(hashlib.sha256(Path(job["local_path"]).read_bytes()).hexdigest(), before)
        for bad in (f"/api/game/files/{job['id']}/{result['run']}/..%2F..%2Fsecret.png",
                    f"/api/game/files/{job['id']}/{result['run']}/../x.png",
                    f"/api/game/files/..%2F/{result['run']}/jump.json",
                    f"/api/game/files/{job['id']}/notarun/jump.json",
                    f"/api/game/files/{job['id']}/{result['run']}/frames/a/b.png",
                    f"/api/game/files/{job['id']}/{result['run']}/mask_preview.txt"):
            self.assertEqual(self.client.get(bad).status_code, 404, bad)

    def test_unfinished_and_unknown_jobs(self):
        job = {"id": str(uuid.uuid4()), "status": "running", "game": {"animation": "walk", "backdrop": "green"}}
        self.jobs.append(job)
        r = self.client.post(f"/api/game/jobs/{job['id']}/process", json={})
        self.assertEqual((r.status_code, r.json()["detail"]["code"]), (409, "game.notReady"))
        self.jobs.append({"id": "plain", "status": "done"})
        self.assertEqual(self.client.post("/api/game/jobs/plain/process", json={}).status_code, 404)

    def test_empty_mask_result_is_not_ok(self):
        job = self.done_job([backdrop(t) for t in range(12)], animation="idle")
        r = self.client.post(f"/api/game/jobs/{job['id']}/process", json={})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["ok"])
        self.assertNotIn("sheet", r.json()["files"])
        self.assertFalse(job["game"]["result"]["ok"])

    def test_preview_and_atlas(self):
        a = self.done_job([frame(seed=t) for t in range(12)], animation="idle")
        b = self.done_job([frame(dy=-(t % 4) * 6, seed=t) for t in range(16)], animation="jump")
        p = self.client.post(f"/api/game/jobs/{a['id']}/preview", json={"sprite": {"tolerance": 25}})
        self.assertEqual(p.status_code, 200, p.text)
        self.assertEqual(self.client.get(p.json()["url"]).status_code, 200)
        for job in (b, a):
            self.assertEqual(self.client.post(f"/api/game/jobs/{job['id']}/process", json={}).status_code, 200)
        r = self.client.post("/api/game/sets/0123456789ab/atlas")
        self.assertEqual(r.status_code, 200, r.text)
        info = r.json()
        self.assertEqual(info["animations"], ["idle", "jump"])
        doc = self.client.get(info["base_url"] + info["json"]).json()
        self.assertEqual(doc["layout"]["rows"], 2)
        self.assertEqual(self.client.get(info["base_url"] + info["zip"]).status_code, 200)
        self.assertEqual(self.client.post("/api/game/sets/zzz/atlas").status_code, 400)


class LaneTests(unittest.TestCase):
    def test_game_lane_is_its_own_production_tab(self):
        import server
        self.assertIn("game", server.JOB_LANES)
        self.assertEqual(server._job_lane({"lane": "game", "mode": "ref"}), "game")
        self.assertEqual(server._job_lane({"lane": "scene", "mode": "ref"}), "scene")
        paths = set(server.app.openapi()["paths"])
        self.assertIn("/api/game/animations", paths)
        self.assertIn("/api/game/jobs/{job_id}/process", paths)


if __name__ == "__main__":
    unittest.main()
