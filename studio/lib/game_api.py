"""Oyun / Sprites API.

Each requested animation becomes one ordinary H3 reference job (shared generate path,
reference upload, backdrop and queue) tagged with ``lane: "game"`` and a ``game`` record.
Sprite processing reads the finished clip and never touches it, so it can be rerun with
new settings without another H3 render.
"""
from __future__ import annotations

import asyncio
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field

from lib import game_sprites as gs

LANE = "game"
QUALITIES = ("352", "480", "608", "736")
# No speed LoRA on sprite clips, so step counts stay at base-model levels.
RENDER_PRESETS = {
    "fast": {"quality": "480", "steps": 16},
    "balanced": {"quality": "608", "steps": 20},
    "quality": {"quality": "736", "steps": 24},
}
DEFAULT_PRESET = "balanced"
DEFAULT_STEPS = 20
KEEP_RUNS = 3
_OWNER = re.compile(r"^(set-[0-9a-f]{12}|[0-9a-f-]{8,40})$")
_RUN = re.compile(r"^(\d{10,16}|previews)$")
_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}$")
_SET = re.compile(r"^[0-9a-f]{12}$")
_MEDIA = {".png": "image/png", ".json": "application/json", ".zip": "application/zip"}


class AnimationsBody(BaseModel):
    ref: str = Field(..., min_length=1, max_length=200)
    animations: list[str] = Field(..., min_length=1, max_length=len(gs.ANIMATIONS))
    backdrop: str = "green"
    description: str = Field("", max_length=400)
    # A preset sets both resolution and steps; `quality` alone keeps the default step count.
    preset: str | None = None
    quality: str = "480"
    seed: int = -1
    sprite: dict[str, Any] = Field(default_factory=dict)


class RefBody(BaseModel):
    ref: str = Field(..., min_length=1, max_length=200)


class SpriteBody(BaseModel):
    sprite: dict[str, Any] = Field(default_factory=dict)


def _fail(status: int, code: str, detail: str = "") -> HTTPException:
    return HTTPException(status, {"code": code, "detail": detail})


def _run_id() -> str:
    return str(int(time.time() * 1000))


def _prune(folder: Path, keep: int, protect: str = "") -> None:
    if not folder.is_dir():
        return
    runs = sorted((p for p in folder.iterdir() if p.is_dir() and p.name.isdigit()), key=lambda p: p.name)
    for old in runs[:-keep]:
        if old.name != protect:
            shutil.rmtree(old, ignore_errors=True)


def summary(job: dict) -> dict:
    game = job.get("game") or {}
    return {
        "id": job.get("id"),
        "set_id": game.get("set_id"),
        "animation": game.get("animation"),
        "status": job.get("status"),
        "progress": job.get("progress"),
        "error": job.get("error"),
        "video_url": (job.get("output") or {}).get("url"),
        "settings": game.get("settings"),
        "render": game.get("render"),
        "result": game.get("result"),
        "created_at": job.get("created_at"),
    }


def create_router(
    *,
    jobs: Callable[[], list[dict]],
    lock: Callable[[], asyncio.Lock],
    save_jobs: Callable[[], None],
    generate: Callable[[Any], Awaitable[dict]],
    body_cls: type,
    ensure_video: Callable[[dict], Awaitable[Path]],
    refs_dirs: Callable[[], list[Path]],
    out_root: Callable[[], Path],
) -> APIRouter:
    router = APIRouter(prefix="/api/game")
    busy: set[str] = set()

    def ref_path(name: str) -> Path:
        safe = Path(str(name or "")).name
        if not safe or safe != name:
            raise _fail(400, "game.badRef")
        for folder in refs_dirs():
            if (folder / safe).is_file():
                return folder / safe
        raise _fail(404, "game.badRef")

    def game_job(job_id: str) -> dict:
        job = next((j for j in jobs() if j.get("id") == job_id), None)
        if not job or not isinstance(job.get("game"), dict):
            raise _fail(404, "game.noJob")
        return job

    def settings(job: dict, raw: dict) -> gs.SpriteSettings:
        game = job["game"]
        try:
            return gs.settings_for(game["animation"], {**(game.get("settings") or {}), **(raw or {})})
        except gs.SpriteError as e:
            raise _fail(400, e.code, e.detail)

    async def source(job: dict) -> Path:
        if job.get("status") != "done":
            raise _fail(409, "game.notReady")
        try:
            path = await ensure_video(job)
        except Exception as e:
            raise _fail(409, "game.noSource", str(e))
        if not Path(path).is_file():
            raise _fail(409, "game.noSource")
        return Path(path)

    @router.get("/presets")
    async def presets():
        render = [{"id": key, **value, "default": key == DEFAULT_PRESET} for key, value in RENDER_PRESETS.items()]
        return {**gs.presets(), "render": render}

    @router.post("/backdrop")
    async def backdrop(body: RefBody):
        path = ref_path(body.ref)
        try:
            with Image.open(path) as im:
                im.thumbnail((512, 512))
                rgb = np.asarray(im.convert("RGB"))
        except Exception as e:
            raise _fail(400, "game.badRef", str(e))
        return gs.suggest_backdrop(rgb)

    @router.post("/animations")
    async def create_animations(body: AnimationsBody):
        ref_path(body.ref)
        names = list(dict.fromkeys(a.strip().lower() for a in body.animations))
        if not names or any(a not in gs.ANIMATIONS for a in names):
            raise _fail(400, "game.badAnimation")
        if body.backdrop not in gs.BACKDROPS:
            raise _fail(400, "game.badBackdrop")
        if body.preset is not None:
            if body.preset not in RENDER_PRESETS:
                raise _fail(400, "game.badSettings", "preset")
            render = {"preset": body.preset, **RENDER_PRESETS[body.preset]}
        elif str(body.quality) in QUALITIES:
            render = {"preset": None, "quality": str(body.quality), "steps": DEFAULT_STEPS}
        else:
            raise _fail(400, "game.badSettings", "quality")
        try:
            plans = {a: gs.settings_for(a, body.sprite) for a in names}
        except gs.SpriteError as e:
            raise _fail(400, e.code, e.detail)
        set_id = uuid.uuid4().hex[:12]
        created, failed = [], []
        for name in names:
            spec = gs.ANIMATIONS[name]
            request = body_cls(
                prompt=gs.build_prompt(name, body.description),
                mode="ref",
                ref_images=[body.ref],
                ref_image_size="max",
                backdrop=body.backdrop,
                lane=LANE,
                duration=spec["duration"],
                aspect="1:1",
                quality=render["quality"],
                steps=render["steps"],
                sage_attention="auto",
                seed=body.seed,
                silent_audio=True,
            )
            try:
                job = await generate(request)
            except HTTPException as e:
                failed.append({"animation": name, "detail": e.detail})
                continue
            async with lock():
                job["game"] = {
                    "set_id": set_id,
                    "animation": name,
                    "backdrop": body.backdrop,
                    "ref": body.ref,
                    "description": body.description.strip(),
                    "render": render,
                    "settings": plans[name].as_dict(),
                }
                save_jobs()
            created.append({"id": job["id"], "animation": name})
        if not created:
            first = failed[0]["detail"] if failed else ""
            raise HTTPException(503 if "Comfy" in str(first) else 400, first or {"code": "game.createFailed"})
        return {"set_id": set_id, "jobs": created, "failed": failed}

    @router.get("/sets")
    async def sets():
        out: dict[str, list] = {}
        for job in jobs():
            if isinstance(job.get("game"), dict):
                out.setdefault(job["game"].get("set_id") or "", []).append(summary(job))
        return {"sets": [{"set_id": k, "jobs": v} for k, v in out.items()]}

    @router.post("/jobs/{job_id}/preview")
    async def preview(job_id: str, body: SpriteBody):
        job = game_job(job_id)
        s = settings(job, body.sprite)
        video = await source(job)
        folder = out_root() / job_id / "previews"
        name = f"{_run_id()}.png"
        game = job["game"]
        try:
            result = await asyncio.to_thread(
                lambda: gs.preview(gs.VideoFrames(video), game["animation"], game["backdrop"], s, folder / name))
        except gs.SpriteError as e:
            raise _fail(400, e.code, e.detail)
        for old in sorted(folder.glob("*.png"))[:-KEEP_RUNS]:
            old.unlink(missing_ok=True)
        return {**result, "url": f"/api/game/files/{job_id}/previews/{name}"}

    @router.post("/jobs/{job_id}/process")
    async def process(job_id: str, body: SpriteBody):
        job = game_job(job_id)
        s = settings(job, body.sprite)
        video = await source(job)
        if job_id in busy:
            raise _fail(409, "game.busy")
        busy.add(job_id)
        run = _run_id()
        folder = out_root() / job_id / run
        game = job["game"]
        try:
            result = await asyncio.to_thread(
                lambda: gs.process(gs.VideoFrames(video), game["animation"], game["backdrop"], s, folder,
                                   {"job_id": job_id, "animation": game["animation"]}))
        except gs.SpriteError as e:
            shutil.rmtree(folder, ignore_errors=True)
            raise _fail(400, e.code, e.detail)
        except Exception as e:
            shutil.rmtree(folder, ignore_errors=True)
            raise _fail(500, "game.processFailed", str(e))
        finally:
            busy.discard(job_id)
        result = {**result, "run": run, "base_url": f"/api/game/files/{job_id}/{run}/", "processed_at": time.time()}
        async with lock():
            game["settings"] = s.as_dict()
            game["result"] = result
            save_jobs()
        _prune(out_root() / job_id, KEEP_RUNS, protect=run)
        return result

    @router.post("/sets/{set_id}/atlas")
    async def atlas(set_id: str):
        if not _SET.match(set_id):
            raise _fail(400, "game.noSet")
        order = list(gs.ANIMATIONS)
        members = [j for j in jobs() if (j.get("game") or {}).get("set_id") == set_id]
        if not members:
            raise _fail(404, "game.noSet")
        items = []
        for job in sorted(members, key=lambda j: order.index(j["game"]["animation"])):
            result = job["game"].get("result") or {}
            if result.get("ok"):
                items.append((out_root() / job["id"] / result["run"], result))
        try:
            run = _run_id()
            owner = f"set-{set_id}"
            info = await asyncio.to_thread(gs.build_atlas, items, out_root() / owner / run, "atlas")
        except gs.SpriteError as e:
            raise _fail(400, e.code, e.detail)
        _prune(out_root() / owner, KEEP_RUNS, protect=run)
        return {**info, "run": run, "base_url": f"/api/game/files/{owner}/{run}/"}

    @router.get("/files/{owner}/{run}/{path:path}")
    async def files(owner: str, run: str, path: str):
        parts = path.split("/")
        if (not _OWNER.match(owner) or not _RUN.match(run) or len(parts) > 2
                or not all(_PART.match(p) and ".." not in p for p in parts)):
            raise HTTPException(404)
        root = out_root().resolve()
        target = (root / owner / run / Path(*parts)).resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(404)
        media = _MEDIA.get(target.suffix.lower())
        if not media:
            raise HTTPException(404)
        if target.suffix.lower() == ".zip":
            return FileResponse(target, media_type=media, filename=f"{owner[:12]}_{target.name}")
        return FileResponse(target, media_type=media, headers={"Cache-Control": "no-store"})

    return router
