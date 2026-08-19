"""H3 Studio — FastAPI front for MiniMax H3 ComfyUI (does not modify Comfy)."""
from __future__ import annotations

import asyncio
import atexit
import contextvars
import json
import math
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
import psutil  # Moved from _acquire_single_instance for consistency
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

# Optional progress sink for /api/director/chat/stream (thinking deltas)
_director_progress: contextvars.ContextVar = contextvars.ContextVar(
    "director_progress", default=None
)

from lib.comfy import (
    ComfyClient,
    build_t2v_prompt,
    build_ref2va_prompt,
    build_multishot_prompt,
    detect_sage_mode,
    detect_multishot_pack,
    enhance_ref_prompt,
    MULTISHOT_MAX_SHOTS,
)
from lib.loras import (
    LORAS_DIR,
    dest_for,
    file_ready,
    filename_from_url,
    find_spec,
    is_h3_lora_name,
    public_list,
    spec_ready,
)
from lib.director import (
    apply_audio_policy,
    apply_shot_patches,
    ensure_shot_count_sync,
    expand_shots_user_prompt,
    extract_json_object,
    fallback_director_reply,
    format_brief_board,
    format_cinema_board,
    infer_duration_and_shots,
    opening_message,
    PLAN_MODE_ADDENDUM,
    CINEMA_STUDIO_ADDENDUM,
    ready_shots_reply,
    skeleton_brief_from_text,
    system_prompt,
    ui_lang_addendum,
    normalize_ui_lang,
    validate_brief,
    _clean_shot,
    force_continue_chain,
    expected_shot_count,
)
from lib.frames import duration_to_length, extract_last_frame, resize_image, strip_audio
from lib.music import (
    build_song_director_seed,
    concat_and_mux,
    concat_keep_audio,
    concat_keep_audio_mix_score,
    load_meta,
    probe_energy_timeline,
    save_upload,
    stamp_shots_with_timeline,
    suggested_sections,
    update_meta,
)
from lib.llm import LlmRouter
from lib.notify import NotifyService
from lib.ollama import OllamaClient
from lib import slog
from lib import cinema

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CLIPS = DATA / "clips"
FRAMES = DATA / "frames"
GALLERY = DATA / "gallery"
REFS = DATA / "refs"
REF_VIDEOS = DATA / "ref_videos"
MUSIC = DATA / "music"
CINEMA_FINALS = DATA / "cinema_finals"
COMFY_ROOT = ROOT.parent / "app"
COMFY_OUTPUT = COMFY_ROOT / "output"
COMFY_INPUT = COMFY_ROOT / "input"
ALLOWED_DURATIONS = (4, 5, 6, 8, 10, 15)
LOGS = ROOT / "logs"
JOBS_FILE = DATA / "jobs.json"
GALLERY_FILE = DATA / "gallery.json"
SESSIONS_FILE = DATA / "director_sessions.json"
LLM_SETTINGS_FILE = DATA / "llm_settings.json"
NOTIFY_SETTINGS_FILE = DATA / "notify_settings.json"
PRODUCTION_FILE = DATA / "production.json"
CINEMA_FILE = DATA / "cinema.json"
STATIC = ROOT / "static"

def _normalize_http_url(raw: str, default: str) -> str:
    u = (raw or "").strip() or default
    if not u.startswith(("http://", "https://")):
        u = "http://" + u.lstrip("/")
    return u.rstrip("/")


COMFY_URL = _normalize_http_url(os.environ.get("COMFY_URL") or "", "http://127.0.0.1:8188")
OLLAMA_URL = _normalize_http_url(os.environ.get("OLLAMA_URL") or "", "http://127.0.0.1:11434")
HOST = os.environ.get("STUDIO_HOST", "127.0.0.1")
PORT = int(os.environ.get("STUDIO_PORT", "8787"))
# One Studio process per installation — shared jobs.json must not have two queue loops.
LOCK_FILE = DATA / "studio.lock"
_lock_fh = None


_lock_sock = None


def _acquire_single_instance() -> None:
    """Bind a lock socket so only one queue loop can own jobs.json."""
    global _lock_fh, _lock_sock
    import socket

    DATA.mkdir(parents=True, exist_ok=True)
    # Dedicated lock port derived from Studio port (does not conflict with uvicorn)
    lock_port = 20000 + (int(PORT) % 20000)

    def _release():
        global _lock_fh, _lock_sock
        try:
            if _lock_sock:
                _lock_sock.close()
                _lock_sock = None
        except Exception:
            pass
        try:
            if _lock_fh:
                _lock_fh.close()
                _lock_fh = None
            if LOCK_FILE.exists():
                try:
                    if LOCK_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
                        LOCK_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception:
            pass

    atexit.register(_release)

    # Drop stale lock file from a crashed previous process
    if LOCK_FILE.exists():
        try:
            old = LOCK_FILE.read_text(encoding="utf-8").strip()
            alive = False
            if old.isdigit():
                alive = psutil.pid_exists(int(old))
            if not alive:
                LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Exclusive bind — second Studio on same PORT exits immediately
        sock.bind(("127.0.0.1", lock_port))
        sock.listen(1)
        _lock_sock = sock
    except OSError:
        sock.close()
        print(
            f"H3 Studio zaten açık (lock :{lock_port} / port {PORT}). "
            "İkinci örnek çıkıyor — çift kuyruk continue zincirini bozuyordu.",
            flush=True,
        )
        sys.exit(0)

    try:
        _lock_fh = open(LOCK_FILE, "w", encoding="utf-8")
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
    except Exception:
        pass
    print(f"Studio tek örnek kilit: pid={os.getpid()} lock_port={lock_port}", flush=True)

# Base sizes at ~1080p short-edge reference; quality scales short edge.
# H3 requires width/height multiples of 32 (see workflow Resolution Selector).
ASPECT_PRESETS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "21:9": (2560, 1080),
    "4:3": (1440, 1080),
}

# Official Comfy MiniMax H3 table (multiple=32).
# Keys stay 480/720/1080 for API compat; pixels are real H3 sizes (736 / 1088).
H3_QUALITY_SIZES = {
    "16:9": {"480": (864, 480), "720": (1280, 736), "1080": (1920, 1088)},
    "9:16": {"480": (480, 864), "720": (736, 1280), "1080": (1088, 1920)},
    "1:1": {"480": (480, 480), "720": (736, 736), "1080": (1088, 1088)},
    "21:9": {"480": (1024, 448), "720": (1536, 672), "1080": (2176, 960)},
    "4:3": {"480": (640, 480), "720": (960, 736), "1080": (1440, 1088)},
}

# Marketing tier → H3 short-edge (×32), not literal 720/1080
QUALITY_SHORT_EDGE = {
    "480": 480,
    "720": 736,
    "1080": 1088,
}


def snap32(v: float) -> int:
    """Nearest multiple of 32 (half-up). 720 → 736, matching H3 table."""
    return max(32, int(math.floor(float(v) / 32.0 + 0.5) * 32))


def snap_h3_size(width: int, height: int) -> tuple[int, int]:
    return snap32(width), snap32(height)


def resolve_size(aspect: str, quality: str = "720") -> tuple[int, int]:
    q = str(quality)
    preset = H3_QUALITY_SIZES.get(aspect, {}).get(q)
    if preset:
        return preset
    base_w, base_h = ASPECT_PRESETS.get(aspect, (1920, 1080))
    target = QUALITY_SHORT_EDGE.get(q, 736)
    short = min(base_w, base_h) or 1
    scale = target / short
    return snap32(base_w * scale), snap32(base_h * scale)


def _lora_fields(body: Any) -> dict[str, Any]:
    spec = find_spec(
        lora_id=getattr(body, "lora_id", None) or "",
        file=getattr(body, "lora_name", None) or "",
    )
    name = (getattr(body, "lora_name", None) or "").strip()
    if spec and spec.get("file"):
        name = spec["file"]
    elif spec and not spec.get("file"):
        name = ""
    strength = getattr(body, "lora_strength", None)
    if strength is None and spec:
        strength = spec.get("strength")
    if not name:
        return {"lora_id": "", "lora_name": "", "lora_strength": None}
    return {
        "lora_id": (spec or {}).get("id") or (getattr(body, "lora_id", None) or ""),
        "lora_name": name,
        "lora_strength": float(strength) if strength is not None else 0.75,
    }


def _sage_mode(src: Any = None) -> str:
    return "disabled"


def _with_lora_preset(
    body: Any,
    steps: int,
    sampler: str,
    scheduler: str,
    graph: str = "fl2va",
) -> tuple[int, str, str]:
    """Steps / sampler / scheduler come from the request. LoRA does not override them."""
    return steps, sampler, scheduler


def _graph_for_mode(mode: str) -> str:
    return (
        "ref2va"
        if (mode or "").lower() in ("ref", "face", "v2v", "face_continue")
        else "fl2va"
    )


def _lora_src_for_shot(body: Any, bound: Optional[dict[str, Any]], mode: str):
    """Pick a LoRA that actually applies on this shot's graph.

    Character LoRA wins on Ref2VA when the global pick is FL2VA-only turbo.
    """
    graph = _graph_for_mode(mode)

    class LoraSrc:
        lora_id = ""
        lora_name = None
        lora_strength = None

    def _ok(spec: Optional[dict[str, Any]]) -> bool:
        if not spec or not spec.get("file"):
            return False
        graphs = spec.get("graphs") or ["fl2va", "ref2va"]
        return graph in graphs

    char_id = ""
    char_strength = None
    for h in (bound or {}).get("hits") or []:
        if h.get("kind") == "character" and h.get("lora_id"):
            char_id = str(h["lora_id"]).strip()
            char_strength = h.get("lora_strength")
            break
    char_spec = find_spec(lora_id=char_id) if char_id else None
    glob_spec = find_spec(
        lora_id=getattr(body, "lora_id", None) or "",
        file=getattr(body, "lora_name", None) or "",
    )
    src = LoraSrc()
    if _ok(char_spec):
        src.lora_id = char_id
        src.lora_name = char_spec.get("file")
        src.lora_strength = char_strength if char_strength is not None else char_spec.get("strength")
    elif _ok(glob_spec):
        src.lora_id = getattr(body, "lora_id", None) or glob_spec.get("id") or ""
        src.lora_name = getattr(body, "lora_name", None) or glob_spec.get("file")
        src.lora_strength = getattr(body, "lora_strength", None)
    return src, graph


def _lora_for_graph(job: dict) -> tuple[Optional[str], float]:
    name = (job.get("lora_name") or "").strip()
    if not name:
        return None, 1.0
    spec = find_spec(lora_id=job.get("lora_id") or "", file=name)
    graphs = (spec or {}).get("graphs") or ["fl2va", "ref2va"]
    mode = (job.get("mode") or "t2v").lower()
    graph = "ref2va" if mode in ("ref", "face", "v2v", "face_continue") else "fl2va"
    if graph not in graphs:
        slog.info("lora skipped", lora=name, mode=mode, graph=graph)
        return None, 1.0
    st = job.get("lora_strength")
    if st is None:
        st = (spec or {}).get("strength") or 0.8
    return name, float(st)


app = FastAPI(title="H3 Studio")
comfy = ComfyClient(COMFY_URL)
ollama = OllamaClient(OLLAMA_URL)
llm = LlmRouter(LLM_SETTINGS_FILE, ollama=ollama)
notifier = NotifyService(NOTIFY_SETTINGS_FILE)

# job queue state
_jobs: list[dict] = []
_gallery: list[dict] = []
_sessions: dict[str, dict] = {}
_queue_task: Optional[asyncio.Task] = None
_queue_supervisor: Optional[asyncio.Task] = None
_lora_dl_lock = asyncio.Lock()
_lora_dl_status: dict[str, Any] = {"id": "", "busy": False, "error": None}
_running = False
_lock = asyncio.Lock()
_director_model: Optional[str] = None
_last_llm_free_at = 0.0
_last_comfy_free_at = 0.0
_last_progress_save_at = 0.0


def _ensure_dirs():
    for p in (DATA, CLIPS, FRAMES, GALLERY, REFS, MUSIC, CINEMA_FINALS, STATIC, LOGS):
        p.mkdir(parents=True, exist_ok=True)


def _save_jobs():
    """Atomic write — avoid corrupt jobs.json if process dies mid-save."""
    JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = JOBS_FILE.with_suffix(".tmp")
    data = json.dumps(_jobs, indent=2, ensure_ascii=False)
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(JOBS_FILE)


def _save_jobs_if_known(job: dict) -> None:
    """Persist last-frame fields on a queue job; gallery-only copies stay in gallery."""
    jid = str((job or {}).get("id") or "")
    if not jid:
        return
    known = next((j for j in _jobs if j.get("id") == jid), None)
    if known is not None:
        if known is not job:
            for key in (
                "local_path",
                "last_frame_path",
                "last_frame_url",
                "last_frame_name",
                "last_frame_upload_error",
            ):
                if job.get(key) is not None:
                    known[key] = job[key]
        _save_jobs()
        return
    gal = next((g for g in _gallery if g.get("id") == jid), None)
    if gal is None:
        return
    for key in ("local_path", "last_frame_path", "last_frame_url", "last_frame_name"):
        if job.get(key) is not None:
            gal[key] = job[key]
    _save_gallery()


def _save_gallery():
    """Atomic write for permanent gallery index (survives wipe/clear jobs)."""
    GALLERY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = GALLERY_FILE.with_suffix(".tmp")
    data = json.dumps(_gallery, indent=2, ensure_ascii=False)
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(GALLERY_FILE)


def _load_gallery():
    global _gallery
    if GALLERY_FILE.exists():
        try:
            raw = json.loads(GALLERY_FILE.read_text(encoding="utf-8"))
            _gallery = raw if isinstance(raw, list) else []
        except Exception:
            _gallery = []
    else:
        _gallery = []

    GALLERY.mkdir(parents=True, exist_ok=True)
    by_id: dict[str, dict] = {}
    for g in _gallery:
        gid = g.get("id")
        if gid:
            by_id[gid] = g

    dirty = False
    # Drop entries whose files are gone; refresh paths/urls
    cleaned: dict[str, dict] = {}
    for gid, g in by_id.items():
        path = Path(g.get("local_path") or "") if g.get("local_path") else GALLERY / f"{gid}.mp4"
        if not path.exists():
            path = GALLERY / f"{gid}.mp4"
        if not path.exists():
            dirty = True
            continue
        if g.get("local_path") != str(path) or g.get("url") != f"/api/gallery/{gid}/video":
            dirty = True
        g["local_path"] = str(path)
        g["url"] = f"/api/gallery/{gid}/video"
        cleaned[gid] = g

    _gallery = list(cleaned.values())
    if dirty or len(_gallery) != len(by_id):
        _save_gallery()


def _unlink_retry(path: Path, attempts: int = 8) -> bool:
    """Delete a file; retry because Windows often locks the gallery <video> source."""
    if not path or str(path) in ("", ".", "None"):
        return True
    try:
        if not path.exists() or not path.is_file():
            return True
    except OSError:
        return True
    last: Exception | None = None
    for i in range(attempts):
        try:
            path.unlink()
            return True
        except Exception as e:
            last = e
            time.sleep(0.12 * (i + 1))
    slog.warn("silinemedi", path=str(path), err=last)
    return False


def _keep_media_ids() -> set[str]:
    keep = {str(g.get("id") or "") for g in _gallery if g.get("id")}
    for j in _jobs:
        jid = str(j.get("id") or "")
        if jid and j.get("status") in ("queued", "running"):
            keep.add(jid)
    keep.discard("")
    return keep


def _purge_id_files(item_id: str, extra: Optional[list[Path]] = None) -> None:
    """Remove gallery clip plus Comfy/studio copies for one job id."""
    jid = (item_id or "").strip()
    if not jid:
        return
    paths: list[Path] = [
        GALLERY / f"{jid}.mp4",
        CLIPS / f"{jid}.mp4",
        FRAMES / f"{jid}_last.png",
        FRAMES / f"{jid}_first.png",
        COMFY_INPUT / f"h3_studio_{jid}_last.png",
        COMFY_INPUT / f"h3_studio_{jid}_first.png",
    ]
    if extra:
        paths.extend([p for p in extra if p])
    prefix = jid[:8]
    for folder in (
        COMFY_OUTPUT / "video" / "H3_Studio",
        COMFY_OUTPUT / "video" / "H3_Studio_Ref",
    ):
        if not folder.is_dir():
            continue
        try:
            for p in folder.glob(f"{prefix}*"):
                if p.is_file():
                    paths.append(p)
        except OSError:
            pass
    seen: set[str] = set()
    for p in paths:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        _unlink_retry(p)


def _sweep_orphaned_media() -> dict[str, int]:
    """Drop Comfy/studio leftovers whose gallery item was already deleted."""
    keep = _keep_media_ids()
    keep_prefix = {k[:8] for k in keep if len(k) >= 8}
    removed = {"comfy_out": 0, "comfy_in": 0, "gallery_orphan": 0, "mux_tmp": 0}
    for folder_name in ("H3_Studio", "H3_Studio_Ref"):
        folder = COMFY_OUTPUT / "video" / folder_name
        if not folder.is_dir():
            continue
        for p in list(folder.iterdir()):
            if not p.is_file():
                continue
            pref = p.name.split("_", 1)[0]
            if pref not in keep_prefix and _unlink_retry(p):
                removed["comfy_out"] += 1
    if COMFY_INPUT.is_dir():
        for p in list(COMFY_INPUT.iterdir()):
            if not p.is_file():
                continue
            m = re.match(r"h3_studio_([0-9a-f-]{36})_", p.name, re.I)
            if m and m.group(1) not in keep and _unlink_retry(p):
                removed["comfy_in"] += 1
    if GALLERY.is_dir():
        for p in list(GALLERY.glob("*.mp4")):
            if p.stem not in keep and _unlink_retry(p):
                removed["gallery_orphan"] += 1
    for parent in (MUSIC, CINEMA_FINALS):
        if not parent.is_dir():
            continue
        for p in list(parent.iterdir()):
            if p.is_dir() and (
                p.name.startswith("_mux_") or p.name.startswith("_cinema_mux_")
            ):
                try:
                    shutil.rmtree(p, ignore_errors=True)
                    removed["mux_tmp"] += 1
                except Exception as e:
                    slog.warn("mux tmp silinemedi", path=str(p), err=e)
    slog.info("orphan media sweep", **removed)
    return removed

def _archive_job_to_gallery(job: dict) -> None:
    """Copy finished clip into permanent gallery. Survives wipe / clear jobs."""
    global _gallery
    jid = job.get("id")
    if not jid or job.get("status") != "done":
        return
    src = Path(job["local_path"]) if job.get("local_path") else CLIPS / f"{jid}.mp4"
    if not src.exists():
        alt = CLIPS / f"{jid}.mp4"
        if alt.exists():
            src = alt
        else:
            return
    GALLERY.mkdir(parents=True, exist_ok=True)
    dest = GALLERY / f"{jid}.mp4"
    try:
        if not dest.exists() or dest.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dest)
    except Exception as e:
        slog.warn("gallery archive copy failed", job=jid[:8], err=e)
        return
    done_at = float(job.get("done_at") or time.time())
    started = job.get("started_at") or job.get("created_at")
    render_sec = None
    try:
        if started is not None:
            render_sec = max(0, int(round(done_at - float(started))))
    except (TypeError, ValueError):
        render_sec = None
    entry = {
        "id": jid,
        "prompt": job.get("prompt") or "",
        "duration": job.get("duration"),
        "width": job.get("width"),
        "height": job.get("height"),
        "mode": job.get("mode") or "t2v",
        "seed": job.get("seed"),
        "aspect": job.get("aspect"),
        "quality": job.get("quality"),
        "batch_index": job.get("batch_index"),
        "batch_total": job.get("batch_total"),
        "music_id": job.get("music_id"),
        "cinema_batch": job.get("cinema_batch"),
        "score_id": job.get("score_id"),
        "purpose": job.get("purpose"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "done_at": done_at,
        "render_sec": render_sec,
        "url": f"/api/gallery/{jid}/video",
        "local_path": str(dest),
    }
    _gallery = [g for g in _gallery if g.get("id") != jid]
    _gallery.append(entry)
    _save_gallery()
    slog.info("gallery archived", job=jid[:8], path=str(dest))


def _save_jobs_throttled(min_interval: float = 1.0) -> None:
    global _last_progress_save_at
    now = time.time()
    if now - _last_progress_save_at < min_interval:
        return
    _last_progress_save_at = now
    _save_jobs()


def _ensure_queue_loop() -> None:
    """Restart queue worker if it died (CancelledError leak, crash, etc.)."""
    global _queue_task
    if _queue_task is not None and not _queue_task.done():
        return
    reason = "ilk start"
    if _queue_task is not None and _queue_task.done():
        exc = _queue_task.exception() if not _queue_task.cancelled() else "cancelled"
        reason = f"ölü worker ({exc})"
    slog.info("queue loop başlatılıyor", reason=reason)
    _queue_task = asyncio.create_task(_queue_loop(), name="h3-queue-loop")


async def _queue_supervisor_loop() -> None:
    """Keep the queue worker alive for the whole Studio lifetime."""
    while True:
        try:
            _ensure_queue_loop()
        except Exception as e:
            slog.exception("queue supervisor hata", e)
        await asyncio.sleep(3)


def _wipe_production_files() -> dict[str, int]:
    """Delete working clips/frames and empty the job list.

    Permanent gallery (data/gallery) is NEVER wiped here — Galeri is the
    long-term archive of every finished video.
    """
    global _jobs
    # Ensure finished clips are in gallery before wiping working copies
    for j in _jobs:
        if j.get("status") == "done":
            try:
                _archive_job_to_gallery(j)
            except Exception as e:
                slog.warn("wipe archive before purge", job=str(j.get("id", ""))[:8], err=e)
    removed = {"clips": 0, "frames": 0, "jobs": len(_jobs)}
    for folder, key in ((CLIPS, "clips"), (FRAMES, "frames")):
        folder.mkdir(parents=True, exist_ok=True)
        for p in folder.iterdir():
            try:
                if p.is_file():
                    p.unlink()
                    removed[key] += 1
            except Exception as e:
                slog.warn("wipe silinemedi", path=str(p), err=e)
    _jobs = []
    _save_jobs()
    slog.warn("production sıfırlandı (galeri korundu)", **removed)
    return removed


def _load_jobs():
    global _jobs
    if JOBS_FILE.exists():
        try:
            _jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        except Exception:
            _jobs = []


def _save_sessions():
    SESSIONS_FILE.write_text(json.dumps(_sessions, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_sessions():
    global _sessions
    if SESSIONS_FILE.exists():
        try:
            _sessions = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            _sessions = {}


class GenerateBody(BaseModel):
    prompt: str = Field(..., min_length=1)
    duration: int = Field(5, description="4 | 5 | 6 | 8 | 10 | 15")
    aspect: str = "16:9"
    quality: str = Field("720", description="480 | 720 | 1080")
    seed: int = -1
    steps: int = 20
    sampler: str = "res_multistep"
    scheduler: str = "simple"
    continue_from_job_id: Optional[str] = None
    first_frame_name: Optional[str] = None
    last_frame_name: Optional[str] = None
    # "t2v" | "continue" | "ref" | "face" | "v2v"
    mode: Optional[str] = None
    # Ref2VA: Comfy upload names (after /api/refs/upload)
    ref_images: Optional[list[str]] = None
    # Ref2VA video names (after /api/refs/upload-video)
    ref_videos: Optional[list[str]] = None
    include_video_audio: bool = True
    # match = scale to gen area; max = best identity (face default)
    ref_image_size: Optional[str] = None
    # music video: strip generated audio after download
    silent_audio: bool = False
    purpose: Optional[str] = None
    lora_id: Optional[str] = None
    lora_name: Optional[str] = None
    lora_strength: Optional[float] = None
    sage_attention: Optional[str] = "auto"

    @field_validator("seed", "steps", mode="before")
    @classmethod
    def _coerce_int(cls, v):
        if v is None or v == "" or (isinstance(v, float) and v != v):  # NaN
            return -1
        try:
            return int(v)
        except Exception:
            return -1

    @field_validator("ref_images", "ref_videos", mode="before")
    @classmethod
    def _coerce_refs(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(x) for x in v if x]
        return None


class BatchBody(BaseModel):
    prompts: list[str]
    duration: int = 5
    aspect: str = "16:9"
    quality: str = "720"
    steps: int = 20
    link_continue: bool = True
    # True: first prompt continues from last queued/running/done (append chain)
    append_to_chain: bool = True
    seed: int = -1
    music_id: Optional[str] = None
    silent_audio: bool = False
    purpose: Optional[str] = None
    # Face lock across chain (Ref2VA portraits reused on continue)
    ref_images: Optional[list[str]] = None
    ref_image_size: Optional[str] = None
    ref_role: Optional[str] = None  # "face"
    face_lock: bool = True
    sampler: str = "res_multistep"
    scheduler: str = "simple"
    lora_id: Optional[str] = None
    lora_name: Optional[str] = None
    lora_strength: Optional[float] = None
    sage_attention: Optional[str] = "auto"
    # Parallel to prompts: "t2v" | "continue". When set, first/continue is per shot.
    modes: Optional[list[str]] = None
    # Cinema film score is mixed later — do NOT set music_id (that silences dialogue).
    cinema_batch: Optional[str] = None
    score_id: Optional[str] = None


class CinemaProduceBody(BaseModel):
    shots: Optional[list[Any]] = None
    script: Optional[str] = None
    shot_modes: Optional[list[str]] = None
    setup: Optional[dict[str, Any]] = None
    duration: int = 5
    aspect: str = "16:9"
    quality: str = "720"
    steps: int = 20
    seed: int = -1
    silent_audio: bool = False
    purpose: Optional[str] = None
    sampler: str = "res_multistep"
    scheduler: str = "simple"
    lora_id: Optional[str] = None
    lora_name: Optional[str] = None
    lora_strength: Optional[float] = None
    sage_attention: Optional[str] = "auto"
    link_continue: bool = True
    audio: Optional[dict[str, Any]] = None
    seamless: bool = False

    @field_validator("seed", "steps", mode="before")
    @classmethod
    def _coerce_int(cls, v):
        if v is None or v == "" or (isinstance(v, float) and v != v):
            return -1
        try:
            return int(v)
        except Exception:
            return -1


class StoryboardBody(BaseModel):
    """N keyframe images → N-1 FL2VA clips (img_i first, img_{i+1} last)."""
    image_names: list[str] = Field(..., min_length=2)
    prompts: Optional[list[str]] = None
    shared_prompt: str = ""
    duration: int = 5
    aspect: str = "16:9"
    quality: str = "720"
    steps: int = 20
    seed: int = -1
    silent_audio: bool = False
    purpose: Optional[str] = None
    sampler: str = "res_multistep"
    scheduler: str = "simple"
    lora_id: Optional[str] = None
    lora_name: Optional[str] = None
    lora_strength: Optional[float] = None

    @field_validator("seed", "steps", mode="before")
    @classmethod
    def _coerce_int(cls, v):
        if v is None or v == "" or (isinstance(v, float) and v != v):
            return -1
        try:
            return int(v)
        except Exception:
            return -1

    @field_validator("image_names", "prompts", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        if v is None or v == "":
            return None if v == "" else v
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(x) for x in v if x]
        return None


class DirectorChatBody(BaseModel):
    session_id: Optional[str] = None
    message: str = ""
    model: Optional[str] = None
    purpose: Optional[str] = None
    visual_style: Optional[str] = None
    silent_audio: Optional[bool] = None
    clip_duration: Optional[int] = None
    cinema_studio: Optional[bool] = None


class DirectorCommitBody(BaseModel):
    session_id: str
    queue: bool = False
    link_continue: Optional[bool] = None
    append_to_chain: bool = True
    quality: str = "720"
    aspect: Optional[str] = None
    silent_audio: Optional[bool] = None
    purpose: Optional[str] = None
    clip_duration: Optional[int] = None
    steps: Optional[int] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    lora_id: Optional[str] = None
    lora_name: Optional[str] = None
    lora_strength: Optional[float] = None


def _looks_like_finished_plan(text: str) -> bool:
    """Heuristic: model wrote a plan / truncated ready JSON but chat didn't mark ready."""
    if not text:
        return False
    t = text.lower()
    keys = (
        "expectedshotcount",
        '"ready": true',
        '"ready":true',
        "scene-style",
        "h3prompt",
        "shot 1",
        "shot akışı",
        "proje onay",
        "continue zinciri",
        "robotic angel",
    )
    hits = sum(1 for k in keys if k in t)
    return hits >= 2 or ("expectedshotcount" in t and "characters" in t)


async def _brief_from_director_text(
    content: str,
    *,
    model: str,
    sess: dict,
    expand: bool = True,
) -> Optional[dict]:
    """Parse / salvage / skeleton + expand shots from a director reply."""
    parsed = extract_json_object(content)
    brief_src = None
    if parsed:
        if isinstance(parsed.get("brief"), dict):
            brief_src = parsed["brief"]
        elif isinstance(parsed.get("shots"), list) or parsed.get("expectedShotCount"):
            brief_src = parsed
    if not isinstance(brief_src, dict) or (
        not (brief_src.get("shots") or [])
        and not brief_src.get("expectedShotCount")
        and not brief_src.get("characters")
    ):
        brief_src = skeleton_brief_from_text(content)
    if not isinstance(brief_src, dict):
        return None
    if sess.get("clip_duration") in ALLOWED_DURATIONS:
        brief_src["clipDurationSec"] = int(sess["clip_duration"])
    if sess.get("purpose"):
        brief_src["purpose"] = sess["purpose"]
    if sess.get("visual_style"):
        brief_src["visualStyle"] = sess["visual_style"]
    if sess.get("silent_audio") or (brief_src.get("purpose") or "").lower() in (
        "music_video",
        "music-video",
    ):
        brief_src["silentAudio"] = True
    brief = _apply_session_timing(validate_brief(brief_src), sess)
    need = brief.get("expectedShotCount") or 0
    have = len(brief.get("shots") or [])
    if expand and need and have < need:
        brief = await _expand_brief_shots(brief, model)
    else:
        brief = ensure_shot_count_sync(brief)
    return brief if brief.get("shots") else None


def _apply_session_timing(brief: dict, sess: Optional[dict] = None) -> dict:
    """Lock expectedShotCount from duration / user text ('12 shot', '1 dakika')."""
    brief = dict(brief)
    clip = int(
        (sess or {}).get("clip_duration")
        or brief.get("clipDurationSec")
        or 5
    )
    if clip not in ALLOWED_DURATIONS:
        clip = 5
    brief["clipDurationSec"] = clip
    brief = validate_brief(brief)
    # Only user chat — last_raw JSON contains aspect "16:9" which used to become 969s.
    blob_parts: list[str] = []
    if sess:
        for m in sess.get("messages") or []:
            if m.get("role") == "user" and m.get("content"):
                blob_parts.append(str(m["content"]))
    blob = "\n".join(blob_parts)
    total_inf, need_inf = infer_duration_and_shots(
        blob,
        clip_sec=clip,
        default_total=None,
    )
    if total_inf:
        brief["totalDurationSec"] = int(total_inf)
        # UI clip is law: 10sn chip + 10sn istek = 1 shot, not 2×5.
        brief["expectedShotCount"] = expected_shot_count(int(total_inf), clip)
    elif need_inf:
        brief["expectedShotCount"] = int(need_inf)
        if not brief.get("totalDurationSec"):
            brief["totalDurationSec"] = int(need_inf) * clip
    elif brief.get("totalDurationSec"):
        brief["expectedShotCount"] = expected_shot_count(
            int(brief["totalDurationSec"]), clip
        )
    return validate_brief(brief)


async def _expand_brief_shots(brief: dict, model: str) -> dict:
    """Fill shots to expectedShotCount via Ollama chunks, then placeholder pad."""
    brief = validate_brief(brief)
    need = brief.get("expectedShotCount")
    shots = list(brief.get("shots") or [])
    if not need:
        return ensure_shot_count_sync(brief)
    if len(shots) >= need:
        return ensure_shot_count_sync(brief)

    dur = int(brief.get("clipDurationSec") or 5)
    chunk = 4
    stagnant = 0
    while len(shots) < need and stagnant < 3:
        start = len(shots) + 1
        end = min(need, len(shots) + chunk)
        before = len(shots)
        messages = [
            {
                "role": "system",
                "content": system_prompt()
                + "\n\nŞu an sadece eksik shot JSON üret. Sohbet etme. "
                f"Tam olarak {end - start + 1} shot döndür.",
            },
            {"role": "user", "content": expand_shots_user_prompt(brief, start, end, need)},
        ]
        try:
            content = await llm.chat(
                model, messages, temperature=0.55, format_json=True
            )
        except Exception as e:
            print(f"shot expand fail: {e}", flush=True)
            break
        parsed = extract_json_object(content) or {}
        batch = parsed.get("shots") if isinstance(parsed, dict) else None
        if not isinstance(batch, list) or not batch:
            stagnant += 1
            continue
        for s in batch:
            c = _clean_shot(s, len(shots), dur, brief=brief, total_shots=need)
            if c:
                shots.append(c)
        brief["shots"] = shots
        if len(shots) <= before:
            stagnant += 1
        else:
            stagnant = 0

    brief["shots"] = force_continue_chain(shots[:need])
    brief["expectedShotCount"] = need
    # Always pad remaining slots so commit never queues only 1 shot
    return ensure_shot_count_sync(brief)


@app.on_event("startup")
async def startup():
    _acquire_single_instance()
    _ensure_dirs()
    slog.setup(LOGS)
    # Bare http:// line FIRST — Pinokio start.js captures /(http:\/\/[0-9.:]+)/
    # Do NOT log COMFY_URL as http://… in this process (would steal the capture).
    print(f"http://{HOST}:{PORT}", flush=True)
    print(f"H3 Studio http://{HOST}:{PORT}", flush=True)
    slog.info(
        "studio startup",
        host=HOST,
        port=PORT,
        comfy=COMFY_URL.replace("https://", "").replace("http://", ""),
        pid=os.getpid(),
    )
    _load_jobs()
    _load_gallery()
    _load_sessions()
    # Backfill: any done job with a local file → permanent gallery
    for j in _jobs:
        if j.get("status") == "done":
            try:
                _archive_job_to_gallery(j)
            except Exception as e:
                slog.warn("startup gallery backfill", job=str(j.get("id", ""))[:8], err=e)
    try:
        _sweep_orphaned_media()
    except Exception as e:
        slog.warn("orphan media sweep failed", err=e)
    # Resume: keep prompt_id if Comfy still has it; otherwise re-queue cleanly.
    live_pids: set[str] = set()
    try:
        q = await comfy.queue_status()
        for item in (q.get("queue_running") or []) + (q.get("queue_pending") or []):
            if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[1], str):
                live_pids.add(item[1])
        slog.info("comfy queue peek", running=len(q.get("queue_running") or []), pending=len(q.get("queue_pending") or []))
    except Exception as e:
        slog.exception("startup Comfy queue peek failed", e)
    for j in _jobs:
        pid = j.get("prompt_id")
        if pid and pid in live_pids:
            # Orphaned watch — Studio died/false-error while Comfy still generating
            j["status"] = "queued"
            j["progress_label"] = "Comfy’de sürüyor — yeniden bağlanılacak"
            j["error"] = None
            j["_reattach"] = True
            slog.info_job(j, "startup reattach", prompt=str(pid)[:8])
        elif j.get("status") in ("queued", "running"):
            j["status"] = "queued"
            j["progress_label"] = "sırada (yeniden)"
            j.pop("prompt_id", None)
            j.pop("_reattach", None)
            slog.info_job(j, "startup requeue")
    _save_jobs()
    slog.info("jobs loaded", count=len(_jobs))
    global _queue_task, _queue_supervisor, _director_model
    try:
        probe = await llm.probe()
        _director_model = probe.get("default_model")
        slog.info(
            "llm ok",
            provider=probe.get("provider"),
            model=_director_model,
            online=probe.get("online"),
            detail=probe.get("detail"),
        )
    except Exception as e:
        _director_model = None
        slog.warn("llm probe fail", err=e)
    _ensure_queue_loop()
    if _queue_supervisor is None or _queue_supervisor.done():
        _queue_supervisor = asyncio.create_task(
            _queue_supervisor_loop(), name="h3-queue-supervisor"
        )
    slog.info("studio ready", url=f"{HOST}:{PORT}")


@app.get("/api/health")
async def health():
    _ensure_queue_loop()
    ok = await comfy.healthy()
    q_alive = _queue_task is not None and not _queue_task.done()
    return {
        "studio": True,
        "comfy": ok,
        "comfy_url": COMFY_URL,
        "queue_alive": q_alive,
        "queue_busy": _running,
        "logs_dir": str(LOGS),
    }


@app.get("/api/logs")
async def get_logs(which: str = "latest", lines: int = 200):
    """Tail studio logs for diagnostics. which: latest | studio | errors"""
    name = (which or "latest").strip().lower()
    mapping = {
        "latest": LOGS / "latest.log",
        "studio": LOGS / "studio.log",
        "errors": LOGS / "errors.log",
    }
    path = mapping.get(name)
    if not path:
        raise HTTPException(400, "which: latest | studio | errors")
    n = max(20, min(int(lines or 200), 2000))
    return {
        "file": str(path),
        "which": name,
        "lines": n,
        "text": slog.tail(path, n),
    }


@app.post("/api/logs/clear")
async def clear_logs():
    LOGS.mkdir(parents=True, exist_ok=True)
    for name in ("latest.log", "studio.log", "errors.log"):
        p = LOGS / name
        try:
            p.write_text("", encoding="utf-8")
        except Exception:
            pass
    slog.info("log dosyaları temizlendi")
    return {"ok": True}


class ResetBody(BaseModel):
    # production = jobs+clips+frames; logs optional
    wipe_logs: bool = False


@app.post("/api/reset-production")
async def reset_production(body: ResetBody = ResetBody()):
    """Clean slate for a new batch — jobs, working clips, frames.

    Permanent Galeri archive is kept. Director chat is kept.
    """
    if _running:
        raise HTTPException(400, "üretim sürerken sıfırlanamaz — önce Durdur")
    async with _lock:
        if any(j.get("status") in ("running", "queued") for j in _jobs):
            # Allow wipe anyway if user wants clean restart — cancel first
            for j in _jobs:
                if j.get("status") in ("running", "queued"):
                    j["status"] = "cancelled"
                    j["error"] = "reset"
            try:
                await comfy.interrupt()
            except Exception:
                pass
        removed = _wipe_production_files()
    await _free_comfy_if_idle(reason="reset production")
    if body.wipe_logs:
        await clear_logs()
        removed["logs_wiped"] = True
    removed["gallery_kept"] = len(_gallery)
    return {"ok": True, "removed": removed}


@app.get("/api/system")
async def system_stats():
    """Horizontal status bar metrics (CPU / RAM / GPU / VRAM / disk).

    VRAM must come from nvidia-smi (board-level). Comfy's system_stats
    often reports torch pool free/used and looks almost idle while the GPU
    is actually full — that confused the sysbar.
    """
    vm = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.15)
    disk = psutil.disk_usage(str(ROOT.anchor or ROOT))
    out: dict[str, Any] = {
        "cpu_percent": round(cpu, 1),
        "ram_used_gb": round(vm.used / (1024**3), 2),
        "ram_total_gb": round(vm.total / (1024**3), 2),
        "ram_percent": round(vm.percent, 1),
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "gpu_name": None,
        "gpu_util": None,
        "vram_used_gb": None,
        "vram_total_gb": None,
        "vram_percent": None,
        "comfy_online": False,
        "sage_mode": detect_sage_mode(COMFY_ROOT),
        "multishot": detect_multishot_pack(COMFY_ROOT),
    }
    # 1) Accurate board VRAM + util
    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-gpu=name,memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        line = stdout.decode("utf-8", errors="ignore").strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4:
            out["gpu_name"] = parts[0]
            used = float(parts[1]) / 1024.0
            total = float(parts[2]) / 1024.0
            out["vram_used_gb"] = round(used, 2)
            out["vram_total_gb"] = round(total, 2)
            out["vram_percent"] = round(100.0 * used / total, 1) if total else 0
            out["gpu_util"] = float(parts[3])
    except Exception:
        pass
    # 2) Comfy online + name fallback only (do NOT trust its VRAM numbers)
    try:
        stats = await comfy.system_stats()
        out["comfy_online"] = True
        devices = stats.get("devices") or []
        if devices and not out.get("gpu_name"):
            out["gpu_name"] = (devices[0].get("name") or "").replace("cuda:0 ", "")
        if out.get("vram_used_gb") is None and devices:
            d0 = devices[0]
            total = d0.get("vram_total") or 0
            free = d0.get("vram_free") or 0
            used = max(0, total - free)
            out["vram_total_gb"] = round(total / (1024**3), 2)
            out["vram_used_gb"] = round(used / (1024**3), 2)
            out["vram_percent"] = round(100.0 * used / total, 1) if total else 0
    except Exception:
        pass
    return out


@app.get("/api/jobs")
async def list_jobs():
    _ensure_queue_loop()
    return {"jobs": list(reversed(_jobs[-200:]))}


@app.get("/api/gallery")
async def list_gallery():
    """All finished videos ever produced (permanent archive, not session jobs)."""
    items = sorted(
        _gallery,
        key=lambda g: float(g.get("done_at") or g.get("created_at") or 0),
        reverse=True,
    )
    return {"items": items, "count": len(items)}


@app.get("/api/gallery/{item_id}/video")
async def gallery_video(item_id: str):
    path = GALLERY / f"{item_id}.mp4"
    if not path.exists():
        entry = next((g for g in _gallery if g.get("id") == item_id), None)
        if entry and entry.get("local_path") and Path(entry["local_path"]).exists():
            path = Path(entry["local_path"])
        else:
            raise HTTPException(404, "galeri videosu yok")
    return FileResponse(path, media_type="video/mp4", filename=f"h3_{item_id[:8]}.mp4")


@app.delete("/api/gallery/{item_id}")
async def delete_gallery_item(item_id: str):
    """Remove one item from the permanent gallery and delete its files."""
    global _gallery
    entry = next((g for g in _gallery if g.get("id") == item_id), None)
    if not entry:
        raise HTTPException(404, "galeri kaydı yok")
    extra = []
    lp = entry.get("local_path")
    if lp:
        extra.append(Path(lp))
    _purge_id_files(item_id, extra)
    _gallery = [g for g in _gallery if g.get("id") != item_id]
    _save_gallery()
    slog.info("gallery deleted", job=item_id[:8])
    return {"ok": True, "id": item_id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    for j in _jobs:
        if j["id"] == job_id:
            return j
    raise HTTPException(404, "job yok")


async def _free_llm_for_production() -> list[str]:
    """Unload local Ollama models so VRAM is free for Comfy/H3 (cloud LLM = no-op)."""
    global _last_llm_free_at
    if llm.provider() != "ollama":
        return []
    # Avoid unloading on every continue clip in a batch (wastes 10–30s each)
    if time.time() - _last_llm_free_at < 120:
        return []
    try:
        freed = await llm.unload_for_production()
        if _director_model and _director_model not in freed:
            try:
                await ollama.unload(_director_model)
                freed.append(_director_model)
            except Exception:
                pass
        _last_llm_free_at = time.time()
        if freed:
            slog.info("ollama unloaded for production", models=freed)
        return freed
    except Exception as e:
        slog.warn("ollama unload skip", err=e)
        return []


async def _free_comfy_if_idle(*, reason: str) -> None:
    """Unload Comfy/H3 models after the last queued clip — not between continue shots."""
    global _last_comfy_free_at
    async with _lock:
        busy = any(j.get("status") in ("queued", "running") for j in _jobs)
    if busy:
        return
    if time.time() - _last_comfy_free_at < 3:
        return
    try:
        ok = await comfy.free_memory()
        _last_comfy_free_at = time.time()
        slog.info("comfy vram emptied after production", ok=ok, reason=reason)
    except Exception as e:
        slog.warn("comfy vram empty skip", err=e, reason=reason)


@app.post("/api/generate")
async def generate(body: GenerateBody):
    if body.duration not in ALLOWED_DURATIONS:
        raise HTTPException(400, f"duration must be one of {ALLOWED_DURATIONS}")
    if str(body.quality) not in QUALITY_SHORT_EDGE:
        raise HTTPException(400, "quality must be 480, 720, or 1080")
    if not await comfy.healthy():
        raise HTTPException(503, "ComfyUI kapalı — Pinokio'dan Start ile Comfy'yi aç")

    mode = (body.mode or "").strip().lower()
    continue_from = body.continue_from_job_id
    first_frame = body.first_frame_name
    last_frame = body.last_frame_name
    ref_images = list(body.ref_images or [])
    ref_videos = list(body.ref_videos or [])
    ref_image_size = (body.ref_image_size or "").strip().lower() or None

    # Explicit "t2v" / "new" ignores accidental continue state from UI.
    # Keep first/last frames — that is I2VA / FL2VA, not continue.
    if mode in ("t2v", "new", "yeni"):
        continue_from = None
        ref_images = []
        ref_videos = []
        mode = "t2v"
    elif mode in ("v2v", "video", "video_ref", "motion"):
        mode = "v2v"
        continue_from = None
        first_frame = None
        last_frame = None
        if not ref_videos and not ref_images:
            raise HTTPException(400, "V2V için en az 1 video veya görsel referans yükle")
        if len(ref_videos) > 3:
            raise HTTPException(400, "En fazla 3 referans video")
        if len(ref_images) > 9:
            raise HTTPException(400, "En fazla 9 referans görsel")
        ref_image_size = ref_image_size or "match"
    elif mode in ("face", "yüz", "yuz", "identity"):
        mode = "face"
        continue_from = None
        first_frame = None
        last_frame = None
        ref_videos = []
        if not ref_images:
            raise HTTPException(400, "Yüz referansı için en az 1 portre / yüz fotoğrafı yükle")
        if len(ref_images) > 9:
            raise HTTPException(400, "En fazla 9 referans görsel")
        ref_image_size = ref_image_size or "max"
    elif mode in ("ref", "reference", "ref2va", "referans"):
        mode = "ref"
        continue_from = None
        first_frame = None
        last_frame = None
        if not ref_images and not ref_videos:
            raise HTTPException(400, "Referans için en az 1 görsel veya video yükle")
        if len(ref_images) > 9:
            raise HTTPException(400, "En fazla 9 referans görsel")
        if len(ref_videos) > 3:
            raise HTTPException(400, "En fazla 3 referans video")
        ref_image_size = ref_image_size or "match"
    elif mode in ("continue", "devam") or continue_from:
        mode = "continue"
        last_frame = None
        ref_videos = []
        # Keep explicit face refs for face-lock continue; else clear generic refs
        keep_face = bool(ref_images) and (
            (body.ref_image_size or "").lower() == "max"
            or len(ref_images) <= 3
        )
        if not keep_face:
            ref_images = []
        # No explicit parent → append after chain tip (queued/running/done)
        if not continue_from and not first_frame:
            tip = _chain_tip()
            if tip:
                continue_from = tip["id"]
            else:
                raise HTTPException(
                    400, "Devam için kaynak yok — bitmiş/sıradaki bir video seç veya önce üret"
                )
        if continue_from:
            parent = _clip_record(continue_from)
            if not parent:
                raise HTTPException(400, "Devam kaynağı bulunamadı")
            st = parent.get("status")
            if st in ("error", "cancelled"):
                raise HTTPException(400, "Devam kaynağı başarısız — başka video seç")
            # Inherit face lock from parent chain when client didn't send portraits
            if not ref_images:
                inh, inh_sz = _lookup_face_lock(continue_from)
                if inh:
                    ref_images = inh
                    ref_image_size = inh_sz or "max"
            # done / running / queued OK — queue waits until parent finishes
    else:
        mode = "t2v"
        continue_from = None
        ref_images = []
        ref_videos = []

    cinema_bound = cinema.bind_prompt(
        body.prompt,
        existing_refs=ref_images,
        lora_id=getattr(body, "lora_id", None) or "",
    )
    # I2V / FL2VA (first/last frame) stay on those graphs; otherwise named
    # cinema assets become Ref2VA pictures when the prompt mentions them.
    # Continue must stay last-frame I2V — character names must not steal Ref2VA.
    skip_cinema_images = (
        (bool(first_frame or last_frame) and mode == "t2v")
        or mode in ("continue", "face_continue")
    )
    if cinema_bound["hits"] and not skip_cinema_images:
        ref_images = cinema_bound["ref_images"]
        if mode == "t2v" and ref_images:
            mode = (
                "face"
                if cinema_bound["has_character"] and not cinema_bound["has_location"]
                else "ref"
            )
            continue_from = None

    ref_role = None
    if mode == "face":
        ref_role = "face"
        ref_image_size = "max" if (ref_image_size or "max") == "max" else "match"
    elif mode in ("ref", "v2v"):
        ref_role = "motion" if mode == "v2v" else "general"
        ref_image_size = "max" if ref_image_size == "max" else "match"
    elif mode == "continue" and ref_images:
        ref_role = "face"
        ref_image_size = ref_image_size or "max"
        mode = "face_continue"

    await _free_llm_for_production()
    w, h = resolve_size(body.aspect, body.quality)
    seed = body.seed if body.seed >= 0 else int(time.time() * 1000) % (2**53)
    steps = body.steps if body.steps and body.steps > 0 else 20
    sampler = body.sampler or "res_multistep"
    scheduler = body.scheduler or "simple"
    lora_src, graph = _lora_src_for_shot(body, cinema_bound, mode)
    steps, sampler, scheduler = _with_lora_preset(
        lora_src, steps, sampler, scheduler, graph=graph
    )
    purpose = (body.purpose or "").strip() or None
    silent = bool(body.silent_audio)
    prompt_txt = cinema_bound["prompt"] if cinema_bound.get("hits") else body.prompt
    if mode == "face":
        prompt_txt = enhance_ref_prompt(
            prompt_txt, n_images=len(ref_images), role="face"
        )
    elif mode in ("ref", "v2v"):
        prompt_txt = enhance_ref_prompt(
            prompt_txt,
            n_images=len(ref_images),
            role="general",
        )
        if ref_videos:
            vids = ", ".join(f"Video {i}" for i in range(1, len(ref_videos) + 1))
            if "Video 1" not in prompt_txt and "video 1" not in prompt_txt.lower():
                prompt_txt = (
                    f"{vids} provide motion / timing / camera reference. "
                    f"Image refs (if any) lock appearance. Transform / restyle as described.\n\n"
                    f"{prompt_txt}"
                ).strip()
    # face_continue: enhance at run time (needs last-frame picture count)
    # Silent → lock; otherwise upgrade bare [English] lines to <d>…</d>
    prompt_txt = apply_audio_policy(
        prompt_txt,
        {
            "purpose": purpose or ("music_video" if silent else "short_film"),
            "silentAudio": silent,
        },
    )
    job = {
        "id": str(uuid.uuid4()),
        "status": "queued",
        "prompt": prompt_txt,
        "duration": body.duration,
        "aspect": body.aspect,
        "quality": str(body.quality),
        "width": w,
        "height": h,
        "seed": seed,
        "steps": steps,
        "sampler": sampler,
        "scheduler": scheduler,
        "continue_from": continue_from,
        "first_frame_name": first_frame,
        "last_frame_name": last_frame,
        "ref_images": ref_images,
        "ref_videos": ref_videos,
        "include_video_audio": bool(body.include_video_audio),
        "ref_image_size": ref_image_size,
        "ref_role": ref_role,
        "progress": 0,
        "progress_label": "sırada",
        "error": None,
        "output": None,
        "created_at": time.time(),
        "mode": mode,
        "silent_audio": silent,
        "purpose": purpose,
        "sage_attention": _sage_mode(body),
        **_lora_fields(lora_src),
    }
    async with _lock:
        _jobs.append(job)
        _save_jobs()
    slog.info_job(
        job,
        "generate queued",
        size=f"{w}x{h}",
        silent=silent,
        refs=len(ref_images),
        videos=len(ref_videos),
    )
    return job


@app.post("/api/batch")
async def batch(body: BatchBody):
    if body.duration not in ALLOWED_DURATIONS:
        raise HTTPException(400, f"duration must be one of {ALLOWED_DURATIONS}")
    if str(body.quality) not in QUALITY_SHORT_EDGE:
        raise HTTPException(400, "quality must be 480, 720, or 1080")
    if not await comfy.healthy():
        raise HTTPException(503, "ComfyUI kapalı")
    await _free_llm_for_production()
    purpose = (body.purpose or "").strip() or None
    silent = bool(body.silent_audio) or bool(body.music_id)
    prompts = [p.strip() for p in body.prompts if p.strip()]
    if not prompts:
        raise HTTPException(400, "prompt yok")
    shot_modes = [str(m or "").strip().lower() for m in (body.modes or [])]
    use_per_shot = bool(shot_modes)
    # Chain: 2+ always; 1+ append_to_chain when tip exists; else link_continue flag
    link_continue = True if len(prompts) > 1 else bool(body.link_continue)
    tip = _chain_tip() if (link_continue or body.append_to_chain) else None
    # Later adds → continue from tip; empty queue → 1st t2v then continue
    if tip and body.append_to_chain:
        link_continue = True
    if use_per_shot:
        # Mixed New Video / Continue: do not auto-continue from the global chain tip
        tip = None
        link_continue = True
    policy = {
        "purpose": purpose or ("music_video" if silent else "short_film"),
        "silentAudio": silent,
    }
    prompts = [apply_audio_policy(p, policy) for p in prompts]
    w, h = resolve_size(body.aspect, body.quality)
    steps = body.steps if body.steps and body.steps > 0 else 20
    sampler = body.sampler or "res_multistep"
    scheduler = body.scheduler or "simple"
    base_steps, base_sampler, base_scheduler = steps, sampler, scheduler
    # Face lock: body refs, else inherit from tip chain
    face_refs: list[str] = []
    face_sz = "max"
    if body.face_lock:
        if body.ref_images and (body.ref_role or "face") == "face":
            face_refs = [str(x) for x in body.ref_images if x][:9]
            face_sz = body.ref_image_size or "max"
        else:
            inh, inh_sz = _lookup_face_lock(tip["id"] if tip else None)
            if inh:
                face_refs = inh
                face_sz = inh_sz or "max"
    created = []
    parent: Optional[str] = tip["id"] if (tip and link_continue) else None
    start_from_tip = bool(parent)
    async with _lock:
        for i, text in enumerate(prompts):
            seed = body.seed if body.seed >= 0 else (int(time.time() * 1000) + i) % (2**53)
            want_continue = False
            if use_per_shot:
                m = shot_modes[i] if i < len(shot_modes) else "t2v"
                want_continue = m in ("continue", "devam", "i2v", "last_frame")
            elif link_continue and (i > 0 or start_from_tip):
                want_continue = True
            if want_continue:
                if not parent:
                    extra_tip = _chain_tip()
                    parent = extra_tip["id"] if extra_tip else None
                if parent:
                    cont_from = parent
                    mode = "face_continue" if face_refs else "continue"
                else:
                    cont_from = None
                    mode = "face" if face_refs else "t2v"
            else:
                cont_from = None
                # First shot with face lock → Ref2VA face; else plain t2v
                mode = "face" if face_refs else "t2v"
            bound = cinema.bind_prompt(
                text,
                existing_refs=list(face_refs) if face_refs else [],
                lora_id=getattr(body, "lora_id", None) or "",
            )
            shot_text = bound["prompt"] if bound.get("hits") else text
            if mode in ("continue", "face_continue"):
                # Last-frame I2V: identity stays in the prompt text, not as extra stills
                shot_refs = list(face_refs) if face_refs else []
            else:
                shot_refs = bound["ref_images"] or (list(face_refs) if face_refs else [])
            if bound.get("hits") and shot_refs and mode == "t2v":
                mode = (
                    "face"
                    if bound["has_character"] and not bound["has_location"]
                    else "ref"
                )
            lora_src, graph = _lora_src_for_shot(body, bound, mode)
            shot_steps, shot_sampler, shot_scheduler = _with_lora_preset(
                lora_src, base_steps, base_sampler, base_scheduler, graph=graph
            )
            job = {
                "id": str(uuid.uuid4()),
                "status": "queued",
                "prompt": shot_text,
                "duration": body.duration,
                "aspect": body.aspect,
                "quality": str(body.quality),
                "width": w,
                "height": h,
                "seed": seed,
                "steps": shot_steps,
                "sampler": shot_sampler,
                "scheduler": shot_scheduler,
                "progress_label": "sırada",
                "continue_from": cont_from,
                "first_frame_name": None,
                "ref_images": shot_refs,
                "ref_image_size": "max" if shot_refs else None,
                "ref_role": (
                    "face"
                    if mode in ("face", "face_continue")
                    else ("general" if shot_refs else None)
                ),
                "progress": 0,
                "error": None,
                "output": None,
                "created_at": time.time(),
                "mode": mode,
                "batch_index": i + 1,
                "batch_total": len(prompts),
                "_batch_link_next": True,
                "silent_audio": silent,
                "purpose": purpose,
                "sage_attention": _sage_mode(body),
                **_lora_fields(lora_src),
            }
            if mode == "face" and shot_refs:
                job["prompt"] = enhance_ref_prompt(
                    shot_text, n_images=len(shot_refs), role="face"
                )
                job["prompt"] = apply_audio_policy(job["prompt"], policy)
            elif mode == "ref" and shot_refs:
                job["prompt"] = enhance_ref_prompt(
                    shot_text, n_images=len(shot_refs), role="general"
                )
                job["prompt"] = apply_audio_policy(job["prompt"], policy)
            if body.music_id:
                job["music_id"] = body.music_id
            if body.cinema_batch:
                job["cinema_batch"] = body.cinema_batch
                job["batch_id"] = body.cinema_batch
            if body.score_id:
                job["score_id"] = body.score_id
            _jobs.append(job)
            created.append(job)
            if link_continue:
                parent = job["id"]
        _save_jobs()
    slog.info(
        "batch queued",
        count=len(created),
        link_continue=link_continue,
        append_tip=(tip or {}).get("id", "")[:8] if tip else "",
        face_lock=len(face_refs),
        size=f"{w}x{h}",
        duration=body.duration,
        music_id=body.music_id or "",
        silent=silent,
    )
    return {"jobs": created, "count": len(created)}


@app.post("/api/jobs/{job_id}/continue")
async def continue_job(job_id: str, body: GenerateBody):
    body.continue_from_job_id = job_id
    return await generate(body)


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    """Re-queue a failed/cancelled job with the same settings."""
    if not await comfy.healthy():
        raise HTTPException(503, "ComfyUI kapalı")
    async with _lock:
        job = next((j for j in _jobs if j["id"] == job_id), None)
        if not job:
            raise HTTPException(404, "job yok")
        if job["status"] not in ("error", "cancelled"):
            raise HTTPException(400, "sadece error / cancelled tekrar denenir")
        parent_id = job.get("continue_from")
        if parent_id:
            parent = next((j for j in _jobs if j["id"] == parent_id), None)
            if not parent or parent.get("status") != "done":
                raise HTTPException(
                    400,
                    "önce önceki klip done olmalı — önce onu tekrar dene",
                )
        job["status"] = "queued"
        job["progress"] = 0
        job["progress_label"] = "tekrar sırada"
        job["error"] = None
        job["output"] = None
        job["prompt_id"] = None
        job["local_path"] = None
        job["first_frame_name"] = None
        job["retried_at"] = time.time()
        job["retry_count"] = int(job.get("retry_count") or 0) + 1
        _save_jobs()
    await _free_llm_for_production()
    return job


@app.post("/api/jobs/retry-errors")
async def retry_all_errors():
    """Re-queue every error/cancelled job (parents before children)."""
    if not await comfy.healthy():
        raise HTTPException(503, "ComfyUI kapalı")
    queued = []
    async with _lock:
        failed = [j for j in _jobs if j["status"] in ("error", "cancelled")]
        # parents (no continue_from) first, then continues
        failed.sort(key=lambda j: (1 if j.get("continue_from") else 0, j.get("created_at") or 0))
        for job in failed:
            parent_id = job.get("continue_from")
            if parent_id:
                parent = next((j for j in _jobs if j["id"] == parent_id), None)
                # parent may itself be getting re-queued in this pass
                if parent and parent.get("status") not in ("done", "queued", "running"):
                    continue
            job["status"] = "queued"
            job["progress"] = 0
            job["progress_label"] = "tekrar sırada"
            job["error"] = None
            job["output"] = None
            job["prompt_id"] = None
            job["local_path"] = None
            job["first_frame_name"] = None
            job["retried_at"] = time.time()
            job["retry_count"] = int(job.get("retry_count") or 0) + 1
            queued.append(job["id"])
        _save_jobs()
    if queued:
        await _free_llm_for_production()
    return {"count": len(queued), "ids": queued}


def _purge_job_files(job: dict) -> None:
    """Best-effort delete local clip + last-frame for a removed job."""
    for key in ("local_path", "last_frame_path"):
        p = job.get(key)
        if p:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
    jid = job.get("id")
    if jid:
        for p in (CLIPS / f"{jid}.mp4", FRAMES / f"{jid}_last.png"):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str, delete_files: bool = True):
    """Remove one job from history (not while running). Gallery archive kept."""
    global _jobs
    async with _lock:
        job = next((j for j in _jobs if j["id"] == job_id), None)
        if not job:
            raise HTTPException(404, "job yok")
        if job.get("status") in ("running", "queued"):
            raise HTTPException(400, "çalışan / sıradaki iş silinmez — önce Durdur")
        if job.get("status") == "done":
            try:
                _archive_job_to_gallery(job)
            except Exception as e:
                slog.warn("delete archive before purge", job=job_id[:8], err=e)
        if delete_files:
            _purge_job_files(job)
        _jobs = [j for j in _jobs if j["id"] != job_id]
        _save_jobs()
    return {"ok": True, "id": job_id}


class ClearJobsBody(BaseModel):
    # errors | done | finished | all
    # finished = error+cancelled+done; all = everything except running/queued
    scope: str = "errors"
    delete_files: bool = True


@app.post("/api/jobs/clear")
async def clear_jobs(body: ClearJobsBody):
    """Clear past job records so the list doesn't keep old failures forever."""
    global _jobs
    scope = (body.scope or "errors").strip().lower()
    if scope not in ("errors", "done", "finished", "all"):
        raise HTTPException(400, "scope: errors | done | finished | all")

    def _match(j: dict) -> bool:
        st = j.get("status")
        if st in ("running", "queued"):
            return False
        if scope == "errors":
            return st in ("error", "cancelled")
        if scope == "done":
            return st == "done"
        if scope == "finished":
            return st in ("error", "cancelled", "done")
        # all finished (same as finished — never wipe active)
        return st in ("error", "cancelled", "done")

    removed_ids: list[str] = []
    async with _lock:
        keep = []
        for j in _jobs:
            if _match(j):
                if j.get("status") == "done":
                    try:
                        _archive_job_to_gallery(j)
                    except Exception as e:
                        slog.warn("clear archive before purge", job=str(j.get("id", ""))[:8], err=e)
                if body.delete_files:
                    _purge_job_files(j)
                removed_ids.append(j["id"])
            else:
                keep.append(j)
        _jobs = keep
        _save_jobs()
    return {"removed": len(removed_ids), "ids": removed_ids, "scope": scope}


@app.post("/api/interrupt")
async def interrupt(cancel_queued: bool = False):
    """Stop the running Comfy job. Queued batch stays unless cancel_queued=true."""
    try:
        await comfy.interrupt()
    except Exception as e:
        raise HTTPException(500, str(e))
    cancelled = []
    async with _lock:
        for j in _jobs:
            if j["status"] == "running":
                j["status"] = "cancelled"
                j["error"] = "iptal"
                j["progress_label"] = "iptal"
                cancelled.append(j["id"])
            elif cancel_queued and j["status"] == "queued":
                j["status"] = "cancelled"
                j["error"] = "iptal"
                j["progress_label"] = "iptal"
                cancelled.append(j["id"])
        _save_jobs()
    return {"ok": True, "cancelled": cancelled, "cancel_queued": cancel_queued}


@app.get("/api/clips/{job_id}/video")
async def clip_video(job_id: str):
    for j in _jobs:
        if j["id"] == job_id and j.get("local_path"):
            p = Path(j["local_path"])
            if p.exists():
                return FileResponse(p, media_type="video/mp4")
    # Fall back to permanent gallery if working clip was wiped
    gal = GALLERY / f"{job_id}.mp4"
    if gal.exists():
        return FileResponse(gal, media_type="video/mp4")
    raise HTTPException(404, "video yok")


@app.post("/api/refs/upload")
async def upload_ref(file: UploadFile = File(...)):
    """Upload a reference image to Studio + Comfy input folder."""
    if not await comfy.healthy():
        raise HTTPException(503, "ComfyUI kapalı — referans yüklenemez")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "boş dosya")
    if len(raw) > 40 * 1024 * 1024:
        raise HTTPException(400, "dosya çok büyük (max 40MB)")
    orig = Path(file.filename or "ref.png").name
    ext = orig.rsplit(".", 1)[-1].lower() if "." in orig else "png"
    if ext not in ("png", "jpg", "jpeg", "webp", "bmp"):
        ext = "png"
    rid = str(uuid.uuid4())[:12]
    local_name = f"h3_ref_{rid}.{ext}"
    REFS.mkdir(parents=True, exist_ok=True)
    dest = REFS / local_name
    dest.write_bytes(raw)
    try:
        comfy_name = await comfy.upload_image(dest, local_name)
    except Exception as e:
        raise HTTPException(502, f"Comfy upload hata: {e}") from e
    return {
        "id": rid,
        "name": comfy_name,
        "filename": local_name,
        "url": f"/api/refs/{local_name}",
        "bytes": len(raw),
    }


@app.post("/api/refs/upload-video")
async def upload_ref_video(file: UploadFile = File(...)):
    """Upload a reference video to Studio + Comfy input/ for LoadVideo."""
    if not await comfy.healthy():
        raise HTTPException(503, "ComfyUI kapalı — video yüklenemez")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "boş dosya")
    if len(raw) > 200 * 1024 * 1024:
        raise HTTPException(400, "video çok büyük (max 200MB)")
    orig = Path(file.filename or "ref.mp4").name
    ext = orig.rsplit(".", 1)[-1].lower() if "." in orig else "mp4"
    if ext not in ("mp4", "webm", "mov", "mkv"):
        ext = "mp4"
    rid = str(uuid.uuid4())[:12]
    local_name = f"h3_vid_{rid}.{ext}"
    REF_VIDEOS.mkdir(parents=True, exist_ok=True)
    dest = REF_VIDEOS / local_name
    dest.write_bytes(raw)
    try:
        comfy_name = await comfy.upload_video(dest, local_name)
    except Exception as e:
        raise HTTPException(502, f"Comfy video upload hata: {e}") from e
    return {
        "id": rid,
        "name": comfy_name,
        "filename": local_name,
        "url": f"/api/ref-videos/{local_name}",
        "bytes": len(raw),
        "kind": "video",
    }


@app.get("/api/ref-videos/{filename}")
async def get_ref_video(filename: str):
    name = Path(filename).name
    path = REF_VIDEOS / name
    if not path.exists():
        raise HTTPException(404, "video yok")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/cinema")
async def cinema_get():
    return cinema.load()


@app.put("/api/cinema")
async def cinema_put(body: dict[str, Any]):
    return cinema.save(body or {})


class CinemaIngestBody(BaseModel):
    text: str = ""
    model: Optional[str] = None
    duration: Optional[int] = None


@app.post("/api/cinema/ingest")
async def cinema_ingest(body: CinemaIngestBody):
    """Paste a role/screenplay → LLM fills cinema characters, locations, shots."""
    raw = (body.text or "").strip()
    if len(raw) < 40:
        raise HTTPException(400, "Rol metni çok kısa — sahne / karakter içeren senaryo yapıştır")
    if not await llm.healthy():
        raise HTTPException(503, "Yönetmen LLM hazır değil — sağ üst Ayarlar’dan key ekle")
    model = await llm.resolve_model(body.model or _director_model)
    clip = int(body.duration or cinema.load().get("duration") or 5)
    if clip not in (4, 5, 6, 8, 10, 15):
        clip = 5
    sys_msg = (
        "You turn a pasted screenplay / role text into a production bible for MiniMax H3. "
        "Reply with JSON only. Schema:\n"
        '{"title":"","logline":"","characters":[{"name":"","notes":"look/wardrobe","voice":"speaking voice"}],'
        '"locations":[{"name":"","notes":"set/time/light"}],'
        '"shots":[{"text":"cinematic SCENE paragraph naming characters and locations","mode":"t2v"|"continue"}]}\n'
        "Rules: keep character names short and unique (Arthur, not The Young Knight). "
        f"Each shot is one {clip}s H3 clip. First shot mode t2v, later shots continue. "
        "Shot text must mention character and location names exactly as in characters[]. "
        "20–40 shots max. No markdown."
    )
    user_msg = f"Rol metni / senaryo:\n\n{raw[:24000]}"
    try:
        reply = await llm.chat(
            model,
            [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.4,
            format_json=True,
            num_predict=8192,
        )
    except Exception as e:
        raise HTTPException(502, f"Yönetmen LLM hata ({llm.provider()}): {e}") from e
    parsed = extract_json_object(reply) or {}
    brief = parsed.get("brief") if isinstance(parsed.get("brief"), dict) else parsed
    if not isinstance(brief, dict):
        brief = {}
    if not brief.get("shots") and not brief.get("characters"):
        brief = {
            "title": "",
            "characters": [],
            "locations": [],
            "shots": [{"text": t, "mode": "t2v" if i == 0 else "continue"} for i, t in enumerate(cinema.split_shots(raw))],
        }
    out = cinema.apply_ingest(brief, raw)
    slog.info(
        "cinema ingest",
        chars=len(out.get("characters") or []),
        locs=len(out.get("locations") or []),
        shots=len(out.get("shots") or []),
    )
    return {"ok": True, "cinema": out}


@app.post("/api/cinema/character")
async def cinema_add_character(body: dict[str, Any]):
    return cinema.upsert_asset("character", body or {})


@app.patch("/api/cinema/character/{asset_id}")
async def cinema_patch_character(asset_id: str, body: dict[str, Any]):
    data = cinema.load()
    found = next((x for x in data["characters"] if x.get("id") == asset_id), None)
    if not found:
        raise HTTPException(404, "karakter yok")
    found.update(body or {})
    found["id"] = asset_id
    return cinema.upsert_asset("character", found)


@app.delete("/api/cinema/character/{asset_id}")
async def cinema_del_character(asset_id: str):
    if not cinema.delete_asset("character", asset_id):
        raise HTTPException(404, "karakter yok")
    return {"ok": True, "id": asset_id}


@app.post("/api/cinema/location")
async def cinema_add_location(body: dict[str, Any]):
    return cinema.upsert_asset("location", body or {})


@app.patch("/api/cinema/location/{asset_id}")
async def cinema_patch_location(asset_id: str, body: dict[str, Any]):
    data = cinema.load()
    found = next((x for x in data["locations"] if x.get("id") == asset_id), None)
    if not found:
        raise HTTPException(404, "mekan yok")
    found.update(body or {})
    found["id"] = asset_id
    return cinema.upsert_asset("location", found)


@app.delete("/api/cinema/location/{asset_id}")
async def cinema_del_location(asset_id: str):
    if not cinema.delete_asset("location", asset_id):
        raise HTTPException(404, "mekan yok")
    return {"ok": True, "id": asset_id}


class CinemaMuxBody(BaseModel):
    batch_id: Optional[str] = None
    score_id: Optional[str] = None
    score_volume: Optional[float] = None


def _cinema_batch_items(batch_id: str) -> list[dict]:
    bid = (batch_id or "").strip()
    if not bid:
        return []
    seen: set[str] = set()
    items: list[dict] = []
    for src in (_jobs, _gallery):
        for j in src:
            jid = str(j.get("id") or "")
            if not jid or jid in seen:
                continue
            if str(j.get("cinema_batch") or "") != bid:
                continue
            seen.add(jid)
            items.append(j)
    items.sort(
        key=lambda j: (
            int(j.get("batch_index") or 0),
            float(j.get("created_at") or j.get("done_at") or 0),
        )
    )
    return items


async def _cinema_clip_paths(batch_id: str) -> list[Path]:
    items = _cinema_batch_items(batch_id)
    if not items:
        raise HTTPException(404, "bu filme ait klip yok")
    pending = [j for j in items if j.get("status") in ("queued", "running")]
    if pending:
        raise HTTPException(
            400, f"{len(pending)} shot hâlâ üretiliyor — bitince birleştir"
        )
    paths: list[Path] = []
    for j in items:
        if j.get("status") in ("error", "cancelled", "queued", "running"):
            continue
        jid = str(j.get("id") or "")
        rec = _clip_record(jid) or dict(j)
        rec["id"] = jid
        try:
            paths.append(await _ensure_job_video(rec))
        except Exception:
            gal = GALLERY / f"{jid}.mp4"
            if not gal.exists():
                raise HTTPException(400, f"klip videosu yok: {jid[:8]}")
            paths.append(gal)
    if not paths:
        raise HTTPException(400, "birleştirilecek bitmiş klip yok")
    return paths


async def _mix_cinema_batch(batch_id: str, score_id: str, score_volume: float = 0.16) -> dict:
    try:
        meta = load_meta(MUSIC, score_id)
    except FileNotFoundError:
        raise HTTPException(404, "film müziği dosyası yok — yeniden yükle")
    audio_path = Path(meta.get("path") or "")
    if not audio_path.exists():
        raise HTTPException(404, "film müziği dosyası yok — yeniden yükle")
    paths = await _cinema_clip_paths(batch_id)
    CINEMA_FINALS.mkdir(parents=True, exist_ok=True)
    out = CINEMA_FINALS / f"{batch_id}_final.mp4"
    concat_keep_audio_mix_score(
        video_paths=paths,
        audio_path=audio_path,
        out_path=out,
        score_volume=score_volume,
    )
    return {
        "ok": True,
        "batch_id": batch_id,
        "clips": len(paths),
        "final_url": f"/api/cinema/final/{batch_id}",
    }


async def _maybe_auto_mux_cinema(job: dict) -> None:
    bid = str(job.get("cinema_batch") or "").strip()
    if not bid:
        return
    items = _cinema_batch_items(bid)
    if not items or any(j.get("status") in ("queued", "running") for j in items):
        return
    if not any(j.get("status") == "done" for j in items):
        return
    lib = cinema.load()
    audio = cinema._clean_audio(lib.get("audio"))
    if str(audio.get("auto_muxed") or "") == bid:
        return
    score = str(audio.get("score_id") or job.get("score_id") or "").strip()
    if not score:
        return
    result = await _mix_cinema_batch(bid, score)
    audio["auto_muxed"] = bid
    audio["last_batch"] = bid
    lib["audio"] = audio
    cinema.save(lib)
    slog.info("cinema auto mux", batch=bid, clips=result.get("clips"))


async def _queue_cinema_seamless(
    *,
    body: CinemaProduceBody,
    parsed: list[dict],
    prompts: list[str],
    lib: dict,
    audio: dict,
    cinema_batch: str,
    silent: bool,
    purpose: str,
) -> dict:
    """One H3MultishotSampler job: script blocks joined with --- (pack max 8 shots)."""
    if not detect_multishot_pack(COMFY_ROOT):
        raise HTTPException(
            400,
            "H3 Multishot paketi yok — Pinokio: Download Models → H3 Multishot, sonra Stop → Start",
        )
    if len(parsed) > MULTISHOT_MAX_SHOTS:
        raise HTTPException(
            400,
            f"Kesintisiz zincir en fazla {MULTISHOT_MAX_SHOTS} shot (pack limiti). "
            "Fazlası için kutuyu kapatıp Continue zincirini kullan.",
        )
    w, h = resolve_size(body.aspect, body.quality)
    steps = body.steps if body.steps and body.steps > 0 else 20
    sampler = body.sampler or "res_multistep"
    scheduler = body.scheduler or "simple"
    texts: list[str] = []
    bound_hits: list[dict] = []
    for text in prompts:
        bound = cinema.bind_prompt(
            text,
            existing_refs=[],
            lora_id=getattr(body, "lora_id", None) or "",
        )
        texts.append(bound["prompt"] if bound.get("hits") else text)
        bound_hits.append(bound)
    merged_hits = {"hits": []}
    for b in bound_hits:
        merged_hits["hits"].extend(b.get("hits") or [])
    lora_src, _graph = _lora_src_for_shot(body, merged_hits, "t2v")
    steps, sampler, scheduler = _with_lora_preset(
        lora_src, steps, sampler, scheduler, graph="fl2va"
    )
    script = "\n---\n".join(texts)
    seed = body.seed if body.seed >= 0 else int(time.time() * 1000) % (2**53)
    job = {
        "id": str(uuid.uuid4()),
        "status": "queued",
        "prompt": script,
        "script": script,
        "duration": body.duration,
        "aspect": body.aspect,
        "quality": str(body.quality),
        "width": w,
        "height": h,
        "seed": seed,
        "steps": steps,
        "sampler": sampler,
        "scheduler": scheduler,
        "progress_label": "sırada · kesintisiz zincir",
        "continue_from": None,
        "first_frame_name": None,
        "ref_images": [],
        "progress": 0,
        "error": None,
        "output": None,
        "created_at": time.time(),
        "mode": "multishot",
        "batch_index": 1,
        "batch_total": 1,
        "shot_count": len(parsed),
        "silent_audio": silent,
        "purpose": purpose,
        "sage_attention": _sage_mode(body),
        "cinema_batch": cinema_batch,
        "batch_id": cinema_batch,
        **_lora_fields(lora_src),
    }
    if audio.get("score_id"):
        job["score_id"] = audio.get("score_id")
    async with _lock:
        _jobs.append(job)
        _save_jobs()
    slog.info(
        "cinema seamless queued",
        shots=len(parsed),
        batch=cinema_batch,
        size=f"{w}x{h}",
        duration=body.duration,
    )
    return {"jobs": [job], "count": 1}


@app.post("/api/cinema/produce")
async def cinema_produce(body: CinemaProduceBody):
    """Queue cinema shots; each shot is New Video (t2v) or Continue (last-frame)."""
    parsed = cinema.normalize_produce_shots(body.shots, body.script or "", body.shot_modes)
    if not parsed:
        raise HTTPException(400, "Senaryo / shot yok")
    if len(parsed) > 80:
        raise HTTPException(400, "En fazla 80 shot")
    lib = cinema.load()
    if body.setup:
        lib["setup"] = cinema._clean_setup(body.setup)
    audio = cinema._clean_audio(body.audio if body.audio is not None else lib.get("audio"))
    lib["audio"] = audio
    lib["shots"] = parsed
    lib["script"] = "\n\n---\n\n".join(s["text"] for s in parsed)
    lib["duration"] = body.duration
    lib["quality"] = str(body.quality)
    lib["steps"] = body.steps if body.steps and body.steps > 0 else 20
    look = cinema.setup_preamble(lib.get("setup") or {})
    purpose = (body.purpose or "").strip()
    setup_purpose = str((lib.get("setup") or {}).get("purpose") or "").strip()
    if setup_purpose and setup_purpose not in ("auto", ""):
        purpose = setup_purpose
    silent = audio.get("mode") == "silent" or bool(body.silent_audio)
    if audio.get("mode") == "film":
        silent = False
    elif audio.get("mode") == "silent":
        silent = True
    cinema_batch = str(uuid.uuid4())[:8]
    lib["audio"] = audio
    cinema.save(lib)
    head = "\n\n".join(
        x
        for x in (
            look,
            "" if silent else cinema.film_audio_preamble(audio),
            "" if silent else cinema.cast_voice_bible(lib),
        )
        if x
    )
    prompts = [cinema.apply_look(s["text"], head) for s in parsed]
    modes = [s["mode"] for s in parsed]
    still_lock = any(
        (cinema.bind_prompt(p, lib=lib).get("ref_images") or []) for p in prompts
    )
    want_seamless = bool(body.seamless)
    if want_seamless and still_lock:
        want_seamless = False
    if want_seamless:
        queued = await _queue_cinema_seamless(
            body=body,
            parsed=parsed,
            prompts=prompts,
            lib=lib,
            audio=audio,
            cinema_batch=cinema_batch,
            silent=silent,
            purpose=purpose or "short_film",
        )
    else:
        bb = BatchBody(
            prompts=prompts,
            modes=modes,
            duration=body.duration,
            aspect=body.aspect,
            quality=body.quality,
            steps=body.steps if body.steps and body.steps > 0 else 20,
            sampler=body.sampler,
            scheduler=body.scheduler,
            link_continue=False,
            append_to_chain=False,
            seed=body.seed,
            silent_audio=silent,
            purpose=purpose or "short_film",
            face_lock=True,
            lora_id=body.lora_id,
            lora_name=body.lora_name,
            lora_strength=body.lora_strength,
            sage_attention=_sage_mode(body),
            cinema_batch=cinema_batch,
            score_id=audio.get("score_id") or None,
        )
        queued = await batch(bb)
    for i, job in enumerate(queued.get("jobs") or []):
        if i < len(parsed):
            job["shot_id"] = parsed[i].get("id")
            job["shot_index"] = i + 1
    if queued.get("jobs"):
        _save_jobs()
    audio["last_batch"] = cinema_batch
    lib["audio"] = audio
    cinema.save(lib)
    queued["cinema_batch"] = cinema_batch
    queued["score_id"] = audio.get("score_id") or ""
    queued["seamless"] = bool(want_seamless)
    queued["still_lock"] = still_lock
    queued["preview"] = cinema.produce_preview(lib)
    slog.info(
        "cinema produce",
        shots=len(parsed),
        count=queued.get("count"),
        batch=cinema_batch,
        seamless=bool(want_seamless),
        still_lock=still_lock,
    )
    return queued


@app.post("/api/cinema/mux")
async def cinema_mux(body: CinemaMuxBody):
    """Keep per-shot dialogue/SFX and mix one uploaded film score underneath."""
    lib = cinema.load()
    audio = cinema._clean_audio(lib.get("audio"))
    batch_id = (body.batch_id or audio.get("last_batch") or "").strip()
    if not batch_id:
        raise HTTPException(400, "film serisi yok — önce kuyruğa al")
    score_id = (body.score_id or audio.get("score_id") or "").strip()
    if not score_id:
        raise HTTPException(400, "film müziği yok — bir kez yükle")
    vol = 0.16 if body.score_volume is None else float(body.score_volume)
    try:
        result = await _mix_cinema_batch(batch_id, score_id, vol)
    except HTTPException:
        raise
    except Exception as e:
        slog.error("cinema mux failed", err=e, batch=batch_id)
        raise HTTPException(500, str(e)[-400:])
    audio["last_batch"] = batch_id
    lib["audio"] = audio
    cinema.save(lib)
    slog.info("cinema mux ok", batch=batch_id, clips=result.get("clips"))
    return result


@app.post("/api/cinema/concat")
async def cinema_concat(body: CinemaMuxBody):
    """Join cinema-batch clips in shot order (keep dialogue)."""
    lib = cinema.load()
    audio = cinema._clean_audio(lib.get("audio"))
    batch_id = (body.batch_id or audio.get("last_batch") or "").strip()
    if not batch_id:
        raise HTTPException(400, "film serisi yok — önce kuyruğa al")
    paths = await _cinema_clip_paths(batch_id)
    CINEMA_FINALS.mkdir(parents=True, exist_ok=True)
    out = CINEMA_FINALS / f"{batch_id}_final.mp4"
    try:
        concat_keep_audio(video_paths=paths, out_path=out)
    except Exception as e:
        raise HTTPException(500, str(e)[-400:])
    audio["last_batch"] = batch_id
    lib["audio"] = audio
    cinema.save(lib)
    return {
        "ok": True,
        "batch_id": batch_id,
        "clips": len(paths),
        "final_url": f"/api/cinema/final/{batch_id}",
    }


@app.get("/api/cinema/films")
async def cinema_films():
    return {"films": cinema.list_films(), "active": cinema.load().get("film_id")}


class CinemaFilmBody(BaseModel):
    action: str = "new"
    id: Optional[str] = None


@app.post("/api/cinema/films")
async def cinema_films_post(body: CinemaFilmBody):
    act = (body.action or "").strip().lower()
    if act == "new":
        return cinema.new_film()
    if act == "switch":
        try:
            return cinema.switch_film(body.id or "")
        except FileNotFoundError:
            raise HTTPException(404, "film yok")
    if act == "delete":
        return cinema.delete_film(body.id or "")
    raise HTTPException(400, "action: new | switch | delete")


@app.get("/api/cinema/export")
async def cinema_export():
    data = cinema.export_zip()
    title = (cinema.load().get("title") or "film").strip() or "film"
    safe = re.sub(r"[^\w\-]+", "_", title)[:40] or "film"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe}.h3film.zip"'},
    )


@app.post("/api/cinema/import")
async def cinema_import(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "boş zip")
    try:
        return cinema.import_zip(raw)
    except Exception as e:
        raise HTTPException(400, str(e)[:300])


@app.get("/api/cinema/preview")
async def cinema_preview():
    return cinema.produce_preview()


class CinemaStillBody(BaseModel):
    job_id: str
    asset_id: str
    kind: str = "character"


@app.post("/api/cinema/still-from-clip")
async def cinema_still_from_clip(body: CinemaStillBody):
    job = _clip_record(body.job_id) or next(
        (j for j in _gallery if str(j.get("id")) == body.job_id), None
    )
    if not job:
        raise HTTPException(404, "klip yok")
    try:
        await _prepare_last_frame(job, upload=True)
    except Exception as e:
        raise HTTPException(400, f"son kare yok: {e}")
    src = Path(job.get("last_frame_path") or "")
    if not src.is_file():
        raise HTTPException(400, "son kare dosyası yok")
    kind = "character" if (body.kind or "character") != "location" else "location"
    lib = cinema.load()
    key = "characters" if kind == "character" else "locations"
    found = next((x for x in lib.get(key) or [] if x.get("id") == body.asset_id), None)
    if not found:
        raise HTTPException(404, "kart yok")
    images = list(found.get("images") or [])
    if len(images) >= cinema.MAX_ASSET_IMAGES:
        raise HTTPException(400, "Bu kartta en fazla 5 görsel")
    rid = str(uuid.uuid4())[:12]
    dest = REFS / f"h3_ref_{rid}.png"
    REFS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    try:
        comfy_name = await comfy.upload_image(dest, dest.name)
    except Exception as e:
        raise HTTPException(502, f"Comfy upload hata: {e}") from e
    images.append({"file": comfy_name, "url": f"/api/refs/{comfy_name}"})
    found["images"] = images
    return cinema.upsert_asset(kind, found)


@app.get("/api/cinema/final/{batch_id}")
async def cinema_final(batch_id: str):
    bid = Path(batch_id).name
    path = CINEMA_FINALS / f"{bid}_final.mp4"
    if not path.exists():
        raise HTTPException(404, "final yok — önce filme karıştır")
    return FileResponse(path, media_type="video/mp4", filename=f"h3_film_{bid}.mp4")


@app.post("/api/storyboard")
async def storyboard(body: StoryboardBody):
    """Queue N-1 FL2VA jobs: first=img[i], last=img[i+1]."""
    if body.duration not in ALLOWED_DURATIONS:
        raise HTTPException(400, f"duration must be one of {ALLOWED_DURATIONS}")
    if str(body.quality) not in QUALITY_SHORT_EDGE:
        raise HTTPException(400, "quality must be 480, 720, or 1080")
    if not await comfy.healthy():
        raise HTTPException(503, "ComfyUI kapalı")
    images = [str(x) for x in (body.image_names or []) if x]
    if len(images) < 2:
        raise HTTPException(400, "En az 2 keyframe görsel gerekir")
    if len(images) > 40:
        raise HTTPException(400, "En fazla 40 keyframe")
    await _free_llm_for_production()
    purpose = (body.purpose or "").strip() or None
    silent = bool(body.silent_audio)
    w, h = resolve_size(body.aspect, body.quality)
    seed_base = body.seed if body.seed >= 0 else int(time.time() * 1000) % (2**53)
    steps = body.steps if body.steps and body.steps > 0 else 20
    sampler = body.sampler or "res_multistep"
    scheduler = body.scheduler or "simple"
    steps, sampler, scheduler = _with_lora_preset(body, steps, sampler, scheduler)
    n_clips = len(images) - 1
    prompts = list(body.prompts or [])
    shared = (body.shared_prompt or "").strip()
    created = []
    batch_id = str(uuid.uuid4())[:8]
    for i in range(n_clips):
        dur_s = float(body.duration)
        align = (
            f"How the reference pictures align with the target video — "
            f"Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; "
            f"Picture 2 (from Shot 1) aligns with the {dur_s:.2f}-second mark of the target video.\n\n"
        )
        piece = (prompts[i] if i < len(prompts) else "").strip() or shared
        if not piece:
            piece = (
                f"[Shot 1] Live-action or matching the style of the keyframes, "
                f"continuous single shot interpolating from Picture 1 to Picture 2. "
                f"One continuous shot, no cuts."
            )
        if "Picture 1" not in piece and "aligns with" not in piece.lower():
            piece = align + piece
        piece = apply_audio_policy(
            piece,
            {
                "purpose": purpose or ("music_video" if silent else "short_film"),
                "silentAudio": silent,
            },
        )
        job = {
            "id": str(uuid.uuid4()),
            "status": "queued",
            "prompt": piece,
            "duration": body.duration,
            "aspect": body.aspect,
            "quality": str(body.quality),
            "width": w,
            "height": h,
            "seed": (seed_base + i) % (2**53),
            "steps": steps,
            "sampler": sampler,
            "scheduler": scheduler,
            "continue_from": None,
            "first_frame_name": images[i],
            "last_frame_name": images[i + 1],
            "ref_images": [],
            "ref_videos": [],
            "progress": 0,
            "progress_label": "sırada",
            "error": None,
            "output": None,
            "created_at": time.time(),
            "mode": "t2v",
            "silent_audio": silent,
            "purpose": purpose,
            "sage_attention": _sage_mode(body),
            "batch_id": batch_id,
            "batch_index": i + 1,
            "batch_total": n_clips,
            "storyboard": True,
            **_lora_fields(body),
        }
        created.append(job)
    async with _lock:
        _jobs.extend(created)
        _save_jobs()
    slog.info(
        "storyboard queued",
        clips=n_clips,
        batch=batch_id,
        duration=body.duration,
    )
    return {"count": len(created), "batch_id": batch_id, "jobs": created}


@app.get("/api/refs/{filename}")
async def get_ref(filename: str):
    name = Path(filename).name
    path = REFS / name
    if not path.exists():
        raise HTTPException(404, "ref yok")
    media = "image/png"
    low = name.lower()
    if low.endswith((".jpg", ".jpeg")):
        media = "image/jpeg"
    elif low.endswith(".webp"):
        media = "image/webp"
    return FileResponse(path, media_type=media)


@app.get("/api/clips/{job_id}/last-frame")
async def clip_last_frame(job_id: str):
    job = _clip_record(job_id)
    if not job:
        raise HTTPException(404, "job yok")
    p = job.get("last_frame_path")
    if p and Path(p).exists():
        return FileResponse(p, media_type="image/png")
    # lazy build
    try:
        await _prepare_last_frame(job, upload=False)
    except Exception as e:
        raise HTTPException(404, f"last frame yok: {e}")
    p2 = job.get("last_frame_path")
    if p2 and Path(p2).exists():
        return FileResponse(p2, media_type="image/png")
    raise HTTPException(404, "last frame yok")


@app.post("/api/jobs/{job_id}/prepare-last-frame")
async def prepare_last_frame_api(job_id: str):
    job = _clip_record(job_id)
    if not job:
        raise HTTPException(404, "job yok")
    if job.get("status") != "done":
        raise HTTPException(400, "job done değil")
    try:
        await _prepare_last_frame(job, upload=True)
    except Exception as e:
        raise HTTPException(500, str(e))
    return {
        "id": job_id,
        "last_frame_url": job.get("last_frame_url"),
        "last_frame_name": job.get("last_frame_name"),
        "last_frame_path": job.get("last_frame_path"),
    }


@app.get("/api/proxy/view")
async def proxy_view(filename: str, subfolder: str = "", type: str = "output"):
    url = f"{COMFY_URL}/view"
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.get(url, params={"filename": filename, "subfolder": subfolder, "type": type})
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        from fastapi.responses import Response

        return Response(content=r.content, media_type=r.headers.get("content-type", "video/mp4"))


# ─── Director LLM (Ollama / OpenAI / Gemini / Grok / Claude) ───────


class LlmSettingsBody(BaseModel):
    provider: Optional[str] = None
    ollama_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    grok_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None
    ollama_model: Optional[str] = None
    openai_model: Optional[str] = None
    gemini_model: Optional[str] = None
    grok_model: Optional[str] = None
    claude_model: Optional[str] = None


@app.get("/api/production")
async def production_get():
    """Saved production-tab snapshot (settings + prompt list). Does not alter job queue."""
    if not PRODUCTION_FILE.exists():
        return {"ok": True, "saved": False, "production": None}
    try:
        raw = json.loads(PRODUCTION_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"ok": True, "saved": False, "production": None}
        return {"ok": True, "saved": True, "production": raw}
    except Exception as e:
        raise HTTPException(500, f"production okunamadı: {e}")


@app.post("/api/production")
async def production_save(body: dict[str, Any]):
    """Persist production-tab UI state. Never touches Comfy jobs / gallery."""
    if not isinstance(body, dict):
        raise HTTPException(400, "geçersiz gövde")
    snap = dict(body)
    snap["version"] = int(snap.get("version") or 1)
    snap["saved_at"] = time.time()
    # Strip huge / volatile fields
    snap.pop("jobs", None)
    PRODUCTION_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PRODUCTION_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PRODUCTION_FILE)
    slog.info(
        "production saved",
        prompts=len(snap.get("queueItems") or []),
        purpose=snap.get("projectPurpose") or "",
        duration=snap.get("duration"),
    )
    return {"ok": True, "saved": True, "saved_at": snap["saved_at"], "production": snap}


@app.get("/api/llm/settings")
async def llm_settings_get():
    return {"ok": True, **llm.public_settings()}


@app.post("/api/llm/settings")
async def llm_settings_set(body: LlmSettingsBody):
    global _director_model
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    cfg = llm.save(patch)
    probe = await llm.probe()
    _director_model = probe.get("default_model")
    slog.info(
        "llm settings saved",
        provider=cfg.get("provider"),
        online=probe.get("online"),
        model=_director_model,
    )
    return {
        "ok": True,
        **llm.public_settings(),
        "online": bool(probe.get("online")),
        "detail": probe.get("detail"),
        "models": probe.get("models") or [],
        "default_model": _director_model,
    }


class NotifySettingsBody(BaseModel):
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_bot_username: Optional[str] = None
    ntfy_server: Optional[str] = None
    ntfy_topic: Optional[str] = None
    on_batch_done: Optional[bool] = None
    on_each_clip: Optional[bool] = None
    on_error: Optional[bool] = None
    akifactory_path: Optional[str] = None


class NotifyImportBody(BaseModel):
    path: Optional[str] = None


class LoraDownloadBody(BaseModel):
    id: str = ""


class LoraImportBody(BaseModel):
    url: str = ""
    filename: Optional[str] = None


@app.get("/api/loras")
async def loras_get():
    return {"ok": True, "loras": public_list(), "download": dict(_lora_dl_status)}


@app.post("/api/loras/download")
async def loras_download(body: LoraDownloadBody):
    spec = find_spec(lora_id=body.id or "")
    if not spec or not spec.get("file") or not spec.get("url"):
        raise HTTPException(400, "bilinmeyen LoRA")
    if spec_ready(spec):
        return {"ok": True, "ready": True, "id": spec["id"], "file": spec["file"]}
    if _lora_dl_status.get("busy"):
        return {
            "ok": True,
            "ready": False,
            "busy": True,
            "id": _lora_dl_status.get("id"),
        }
    asyncio.create_task(_download_lora_file(spec))
    return {"ok": True, "ready": False, "busy": True, "id": spec["id"]}


@app.post("/api/loras/upload")
async def loras_upload(file: UploadFile = File(...)):
    orig = Path(file.filename or "lora.safetensors").name
    if not orig.lower().endswith(".safetensors"):
        raise HTTPException(400, "sadece .safetensors")
    if not is_h3_lora_name(orig):
        raise HTTPException(
            400, "SDXL / Pony / Wan / Flux / ClipProj dosyası H3 video LoRA değil"
        )
    LORAS_DIR.mkdir(parents=True, exist_ok=True)
    dest = LORAS_DIR / orig
    tmp = dest.with_suffix(dest.suffix + ".part")
    size = 0
    try:
        with tmp.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > 4 * 1024 * 1024 * 1024:
                    raise HTTPException(400, "LoRA çok büyük (max 4GB)")
                f.write(chunk)
        if size < 1024 * 1024:
            raise HTTPException(400, "dosya çok küçük / boş")
        tmp.replace(dest)
    except HTTPException:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(500, str(e)) from e
    slog.info("lora uploaded", file=orig, bytes=size)
    return {"ok": True, "file": orig, "id": f"file:{orig}", "loras": public_list()}


@app.post("/api/loras/import")
async def loras_import(body: LoraImportBody):
    """Download an H3 .safetensors LoRA from a direct HTTP(S) URL (HF resolve works)."""
    url = (body.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "http(s) URL gerekli")
    name = filename_from_url(url, body.filename or "")
    if not name:
        raise HTTPException(
            400,
            "Dosya adı .safetensors olmalı — Hugging Face resolve linki veya filename yaz",
        )
    if not is_h3_lora_name(name):
        raise HTTPException(
            400, "SDXL / Pony / Wan / Flux / ClipProj dosyası H3 video LoRA değil"
        )
    if file_ready(name):
        return {"ok": True, "ready": True, "id": f"file:{name}", "file": name, "loras": public_list()}
    if _lora_dl_status.get("busy"):
        return {
            "ok": True,
            "ready": False,
            "busy": True,
            "id": _lora_dl_status.get("id"),
        }
    spec = {
        "id": f"file:{name}",
        "file": name,
        "url": url,
    }
    asyncio.create_task(_download_lora_file(spec))
    return {"ok": True, "ready": False, "busy": True, "id": spec["id"], "file": name}


async def _download_lora_file(spec: dict) -> None:
    async with _lora_dl_lock:
        _lora_dl_status.update({"id": spec["id"], "busy": True, "error": None})
        dest = dest_for(spec)
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            async with httpx.AsyncClient(timeout=None, follow_redirects=True) as c:
                async with c.stream("GET", spec["url"]) as r:
                    r.raise_for_status()
                    with tmp.open("wb") as f:
                        async for chunk in r.aiter_bytes(1024 * 1024):
                            f.write(chunk)
            tmp.replace(dest)
            slog.info("lora downloaded", file=spec["file"], bytes=dest.stat().st_size)
        except Exception as e:
            _lora_dl_status["error"] = str(e)
            slog.warn("lora download failed", err=e)
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
        finally:
            _lora_dl_status["busy"] = False


@app.get("/api/notify/settings")
async def notify_settings_get():
    return {"ok": True, **notifier.public()}


@app.post("/api/notify/settings")
async def notify_settings_set(body: NotifySettingsBody):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    cfg = notifier.save(patch)
    slog.info(
        "notify settings saved",
        enabled=cfg.get("enabled"),
        provider=cfg.get("provider"),
        telegram=bool((cfg.get("telegram_bot_token") or "").strip()),
    )
    return {"ok": True, **notifier.public()}


@app.post("/api/notify/import-akifactory")
async def notify_import_akifactory(body: NotifyImportBody = NotifyImportBody()):
    try:
        notifier.import_akifactory((body.path or "").strip())
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"ok": True, **notifier.public()}


@app.post("/api/notify/test")
async def notify_test():
    pub = notifier.public()
    prov = (pub.get("provider") or "telegram").lower()
    if prov == "telegram" and not pub.get("telegram_configured"):
        raise HTTPException(
            400,
            "Telegram ayarlı değil — AkiFactory’den aktar veya bot token + chat id kaydet",
        )
    r = await notifier.send(
        "H3 Studio · test",
        "Telegram bildirimi çalışıyor. Üretim bitince böyle mesaj gelecek.",
        priority=4,
        tags="bell,white_check_mark",
        force=True,
    )
    if not r.get("ok"):
        raise HTTPException(502, r.get("detail") or "bildirim gönderilemedi")
    return {"ok": True, **pub, "detail": r.get("detail") or "test sent"}


async def _notify_job(job: dict, event: str) -> None:
    try:
        await notifier.notify_job_event(job, event, jobs=list(_jobs))
    except Exception as e:
        slog.warn("notify failed", err=e)


@app.get("/api/director/status")
async def director_status(lang: Optional[str] = None):
    global _director_model
    probe = await llm.probe()
    online = bool(probe.get("online"))
    models: list[str] = list(probe.get("models") or [])
    default = probe.get("default_model") or _director_model
    if online and default:
        _director_model = default
    detail = probe.get("detail") or ("ok" if online else "offline")
    pub = llm.public_settings()
    return {
        "online": online,
        "provider": probe.get("provider") or pub.get("provider") or "ollama",
        "ollama_url": OLLAMA_URL,
        "models": models,
        "default_model": default,
        "detail": detail,
        "opening": opening_message(lang),
        "llm": pub,
    }


@app.post("/api/director/session")
async def director_new_session(model: Optional[str] = None, lang: Optional[str] = None):
    sid = str(uuid.uuid4())
    ui = normalize_ui_lang(lang)
    sess = {
        "id": sid,
        "model": model or _director_model,
        "ui_lang": ui,
        "messages": [{"role": "assistant", "content": opening_message(ui)}],
        "brief": None,
        "ready": False,
        "created_at": time.time(),
    }
    _sessions[sid] = sess
    _save_sessions()
    return {**sess, "session_id": sid}


@app.get("/api/director/sessions")
async def director_list_sessions():
    """List persisted director sessions for the studio UI tabs."""
    items = []
    for sid, sess in sorted(
        _sessions.items(),
        key=lambda x: float(x[1].get("created_at") or 0),
    ):
        msgs = sess.get("messages") or []
        preview = ""
        for m in reversed(msgs):
            if m.get("role") == "user" and (m.get("content") or "").strip():
                preview = str(m["content"]).strip().replace("\n", " ")[:36]
                break
        items.append(
            {
                "id": sid,
                "session_id": sid,
                "title": preview or "Sohbet",
                "messages": msgs,
                "ready": bool(sess.get("ready")),
                "brief": sess.get("brief"),
                "created_at": sess.get("created_at"),
            }
        )
    return {"sessions": items}


@app.delete("/api/director/session/{session_id}")
async def director_delete_session(session_id: str):
    """Delete one director session completely (remove from memory + persist)."""
    global _sessions
    async with _lock:
        if session_id not in _sessions:
            raise HTTPException(404, "Oturum yok")
        # Best-effort: remove session and persist
        _sessions.pop(session_id, None)
        _save_sessions()
    slog.info("director session deleted", session=session_id[:8])
    return {"ok": True, "id": session_id}


@app.post("/api/director/chat")
async def director_chat(body: DirectorChatBody):
    return await _director_chat_impl(body)


class DirectorPlanBody(BaseModel):
    session_id: str
    brief: Optional[dict[str, Any]] = None
    shots: Optional[list[Any]] = None
    apply_cinema: bool = False


@app.post("/api/director/plan")
async def director_save_plan(body: DirectorPlanBody):
    """Save edited shot board (Plan mode). Optionally copy prompts into cinema.json."""
    sess = _sessions.get(body.session_id)
    if not sess:
        raise HTTPException(400, "Oturum yok")
    brief = dict(sess.get("brief") or {})
    if isinstance(body.brief, dict):
        brief.update(body.brief)
    if body.shots is not None:
        cleaned = []
        clip = int(brief.get("clipDurationSec") or sess.get("clip_duration") or 5)
        raw_shots = list(body.shots)
        for i, raw in enumerate(raw_shots):
            if not isinstance(raw, dict):
                raw = {"h3Prompt": str(raw or "")}
            else:
                raw = dict(raw)
                if not (raw.get("h3Prompt") or "").strip() and (raw.get("text") or raw.get("prompt")):
                    raw["h3Prompt"] = str(raw.get("text") or raw.get("prompt") or "")
                if not (raw.get("action") or "").strip() and raw.get("h3Prompt"):
                    raw["action"] = str(raw.get("h3Prompt") or "")[:180]
            c = _clean_shot(raw, i, clip, brief=brief, total_shots=len(raw_shots))
            if c:
                cleaned.append(c)
        if cleaned:
            brief["shots"] = force_continue_chain(cleaned)
            brief["expectedShotCount"] = len(brief["shots"])
            if not brief.get("clipDurationSec"):
                brief["clipDurationSec"] = clip
            if not brief.get("totalDurationSec"):
                brief["totalDurationSec"] = clip * len(brief["shots"])
    sess["brief"] = brief
    sess["ready"] = bool(brief.get("shots"))
    cinema_out = None
    if body.apply_cinema and (brief.get("shots") or []):
        data = cinema.load()
        data["shots"] = [
            {
                "text": str(s.get("h3Prompt") or s.get("prompt") or s.get("text") or "").strip(),
                "mode": "t2v" if (s.get("linkToPrev") or ("standalone" if i == 0 else "continue")) == "standalone" else "continue",
            }
            for i, s in enumerate(brief["shots"])
        ]
        if brief.get("logline") and not (data.get("title") or "").strip():
            data["title"] = str(brief.get("logline"))[:80]
        cinema_out = cinema.save(data)
    _sessions[body.session_id] = sess
    _save_sessions()
    slog.info("director plan saved", session=body.session_id[:8], shots=len(brief.get("shots") or []), cinema=bool(cinema_out))
    return {
        "ok": True,
        "session_id": body.session_id,
        "ready": bool(sess.get("ready")),
        "brief": brief,
        "shot_count": len(brief.get("shots") or []),
        "cinema": cinema_out,
    }


class BibleGenerateBody(BaseModel):
    session_id: Optional[str] = None
    bible: dict[str, Any]
    clip_duration: Optional[int] = None
    purpose: Optional[str] = None
    visual_style: Optional[str] = None
    model: Optional[str] = None


@app.post("/api/director/bible/generate")
async def director_bible_generate(body: BibleGenerateBody):
    """Build a ProjectBible user turn and run director chat → ready brief."""
    b = body.bible or {}
    chars = b.get("characters") or []
    locs = b.get("locations") or []
    char_lines = []
    for c in chars:
        if isinstance(c, dict):
            char_lines.append(
                f"- {c.get('role') or 'character'}: {c.get('name') or ''} — {c.get('card') or ''}"
            )
        else:
            char_lines.append(f"- {c}")
    loc_lines = []
    for loc in locs:
        if isinstance(loc, dict):
            loc_lines.append(f"- {loc.get('name') or loc.get('card') or loc}")
        else:
            loc_lines.append(f"- {loc}")
    total = int(b.get("totalSeconds") or 30)
    clip = int(body.clip_duration or b.get("clipSeconds") or 5)
    if clip not in ALLOWED_DURATIONS:
        clip = 5
    genre = (body.purpose or b.get("genre") or "short_film").strip()
    style = (body.visual_style or b.get("visualStyle") or "realistic").strip()
    tone = ", ".join(b.get("tone") or []) if isinstance(b.get("tone"), list) else (b.get("tone") or "")
    forbidden = (
        ", ".join(b.get("forbidden") or [])
        if isinstance(b.get("forbidden"), list)
        else (b.get("forbidden") or "")
    )
    msg = (
        "Direktör modu ProjectBible — bundan brief üret (ready: true JSON).\n"
        f"Tür: {genre}\n"
        f"Görsel tarz: {style}\n"
        f"Toplam süre: {total} sn · klip: {clip} sn\n"
        f"Logline: {b.get('logline') or '(yok)'}\n"
        f"Ton: {tone or '(serbest)'}\n"
        f"Yasaklar: {forbidden or 'yok'}\n"
        "Karakterler (shot’lar arası kilitle):\n"
        + ("\n".join(char_lines) if char_lines else "- (belirtilmedi)")
        + "\nLokasyonlar:\n"
        + ("\n".join(loc_lines) if loc_lines else "- (belirtilmedi)")
        + "\n\nTüm shot’lar için sinematik SCENE h3Prompt yaz; "
        "karakter kartlarını birebir tekrarla. JSON brief ver."
    )
    chat_body = DirectorChatBody(
        session_id=body.session_id,
        message=msg,
        model=body.model,
        purpose=genre,
        visual_style=style,
        clip_duration=clip,
        silent_audio=genre in ("music_video", "music-video"),
        ui_lang=(_sessions.get(body.session_id) or {}).get("ui_lang"),
    )
    # stash bible on session after chat
    result = await _director_chat_impl(chat_body)
    sid = result.get("session_id") or body.session_id
    if sid and sid in _sessions:
        _sessions[sid]["bible"] = b
        _save_sessions()
    result["bible"] = b
    return result


@app.post("/api/director/chat/stream")
async def director_chat_stream(body: DirectorChatBody):
    """SSE: thinking/status heartbeats, then final result (same payload as /chat)."""
    q: asyncio.Queue = asyncio.Queue()

    def on_progress(ev: dict[str, Any]) -> None:
        try:
            q.put_nowait(ev if isinstance(ev, dict) else {"type": "status", "text": str(ev)})
        except Exception:
            pass

    async def produce() -> None:
        token = _director_progress.set(on_progress)
        try:
            result = await _director_chat_impl(body)
            await q.put({"type": "result", "data": result})
        except HTTPException as e:
            await q.put(
                {
                    "type": "error",
                    "detail": e.detail,
                    "status": e.status_code,
                }
            )
        except Exception as e:
            await q.put({"type": "error", "detail": str(e)})
        finally:
            _director_progress.reset(token)
            await q.put(None)

    async def event_gen():
        task = asyncio.create_task(produce())
        yield (
            "data: "
            + json.dumps(
                {"type": "status", "text": "Yönetmen düşünüyor…"},
                ensure_ascii=False,
            )
            + "\n\n"
        )
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                yield (
                    "data: "
                    + json.dumps({"type": "heartbeat", "t": int(time.time())})
                    + "\n\n"
                )
                if task.done():
                    # drain leftover
                    while not q.empty():
                        ev = q.get_nowait()
                        if ev is None:
                            break
                        yield "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"
                    break
                continue
            if ev is None:
                break
            yield "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"
        try:
            await task
        except Exception:
            pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _director_chat_impl(body: DirectorChatBody):
    if not await llm.healthy():
        prov = llm.provider()
        hints = {
            "openai": "OpenAI API key yok/geçersiz — Ayarlar’dan sk-… key ekle.",
            "gemini": "Gemini API key yok/geçersiz — aistudio.google.com/apikey",
            "grok": "Grok (xAI) API key yok/geçersiz — console.x.ai",
            "claude": "Claude API key yok/geçersiz — console.anthropic.com",
            "ollama": "Ollama kapalı — `ollama serve` veya Ayarlar’dan bulut LLM seç.",
        }
        raise HTTPException(503, hints.get(prov, "Yönetmen LLM hazır değil — Ayarlar’ı kontrol et."))
    sid = body.session_id
    if not sid or sid not in _sessions:
        created = await director_new_session(body.model, lang=body.ui_lang)
        sid = created["id"]
    sess = _sessions[sid]
    ui_lang = normalize_ui_lang(body.ui_lang or sess.get("ui_lang"))
    sess["ui_lang"] = ui_lang
    try:
        model = await llm.resolve_model(body.model or sess.get("model") or _director_model)
    except Exception as e:
        raise HTTPException(400, str(e))
    sess["model"] = model

    if body.purpose:
        sess["purpose"] = body.purpose
    if body.visual_style:
        sess["visual_style"] = body.visual_style
    if body.silent_audio is not None:
        sess["silent_audio"] = bool(body.silent_audio)
    elif (sess.get("purpose") or "").lower() in ("music_video", "music-video"):
        sess["silent_audio"] = True
    if body.clip_duration in ALLOWED_DURATIONS:
        sess["clip_duration"] = int(body.clip_duration)
    if body.cinema_studio is not None:
        sess["cinema_studio"] = bool(body.cinema_studio)

    user_msg = (body.message or "").strip()
    if user_msg:
        # Inject selected project mode so the model keeps purpose/audio policy
        purpose = sess.get("purpose")
        style = sess.get("visual_style")
        silent = bool(sess.get("silent_audio"))
        prefix_bits = []
        clip = sess.get("clip_duration")
        if clip in ALLOWED_DURATIONS:
            prefix_bits.append(
                f"clipDurationSec={clip} (her shot TAM {clip}sn; 5sn'ye bölme; "
                f"N=ceil(toplam/{clip}))"
            )
        if purpose:
            prefix_bits.append(f"purpose={purpose}")
        if style:
            prefix_bits.append(f"visualStyle={style}")
        if silent or (purpose or "").lower() in ("music_video", "music-video"):
            prefix_bits.append(
                "silentAudio=true (no dialogue/SFX/generated music — visuals only)"
            )
        if prefix_bits and not user_msg.startswith("[proje:"):
            user_msg = f"[proje: {', '.join(prefix_bits)}]\n{user_msg}"
        if sess.get("cinema_studio") and "[sinema stüdyosu]" not in user_msg.lower():
            user_msg = "[sinema stüdyosu] " + user_msg
        sess["messages"].append({"role": "user", "content": user_msg})

    # Short confirm after a finished plan → finalize previous assistant text (no new LLM wait)
    confirm = re.fullmatch(
        r"(üret(e|ime)?(\s*al)?|tamam|ok|başla|kuyru[gk]a?\s*al|go|start)",
        (body.message or "").strip(),
        flags=re.I,
    )
    plan_mode = bool(body.plan_mode)
    if confirm and not sess.get("ready") and not plan_mode:
        prev = (sess.get("last_raw") or "") + "\n"
        for m in reversed(sess.get("messages") or []):
            if m.get("role") == "assistant" and m.get("content"):
                prev += m["content"] + "\n"
                break
        if _looks_like_finished_plan(prev) or extract_json_object(prev):
            mid = "Senaryo kilitlendi — SCENE prompt’lar tamamlanıyor…"
            sess["messages"].append({"role": "assistant", "content": mid})
            _sessions[sid] = sess
            _save_sessions()
            brief = await _brief_from_director_text(
                prev, model=model, sess=sess, expand=True
            )
            if brief and brief.get("shots"):
                n = len(brief["shots"])
                need = brief.get("expectedShotCount") or n
                reply = ready_shots_reply(n, need, ui_lang)
                sess["brief"] = brief
                sess["ready"] = True
                sess["messages"].append({"role": "assistant", "content": reply})
                _sessions[sid] = sess
                _save_sessions()
                cinema_out = None
                if sess.get("cinema_studio"):
                    try:
                        role = str((cinema.load() or {}).get("role_script") or "")
                        cinema_out = cinema.ingest_from_director_brief(brief, role)
                    except Exception:
                        cinema_out = None
                return {
                    "session_id": sid,
                    "reply": reply,
                    "ready": True,
                    "brief": brief,
                    "shot_count": n,
                    "model": model,
                    "messages": sess["messages"],
                    "cinema": cinema_out,
                }

    # Ask model; empty answers are retried inside llm.chat, then local fallback
    sys = system_prompt()
    sys = (sys or "") + ui_lang_addendum(ui_lang)
    if plan_mode:
        sys = (sys or "") + "\n\n" + PLAN_MODE_ADDENDUM
        if ui_lang == "en":
            sys += "\nPlan-mode `reply` must be English (not Turkish)."
    if sess.get("cinema_studio"):
        sys = (sys or "") + "\n\n" + CINEMA_STUDIO_ADDENDUM
    board = format_brief_board(sess.get("brief"), full=plan_mode)
    try:
        cinema_board = format_cinema_board(cinema.load(), full=plan_mode)
    except Exception:
        cinema_board = ""
    extra_boards = "\n\n".join(x for x in (board, cinema_board) if x)
    if extra_boards:
        sys = (sys or "") + "\n\n---\n" + extra_boards
    history = [{"role": "system", "content": sys}] + sess["messages"][-24:]
    content = ""
    progress = _director_progress.get()
    try:
        content = await llm.chat(
            model,
            history,
            temperature=0.7,
            think=False,
            retries=3,
            num_predict=6144 if plan_mode else 4096,
            on_progress=progress,
        )
    except Exception as e:
        # One soft recovery with a shorter nudge history
        try:
            if progress:
                try:
                    progress({"type": "status", "text": "Yeniden deniyor…"})
                except Exception:
                    pass
            nudge = history + [
                {
                    "role": "user",
                    "content": (
                        "[system] Retry after error. Write a 2–4 sentence director reply in English; do not leave it empty."
                        if ui_lang == "en"
                        else (
                            "[sistem] Hata sonrası yeniden dene. "
                            "Türkçe 2–4 cümle yönetmen cevabı yaz; boş bırakma."
                        )
                    ),
                }
            ]
            content = await llm.chat(
                model,
                nudge,
                temperature=0.45,
                think=False,
                retries=2,
                num_predict=2048,
                on_progress=progress,
            )
        except Exception:
            raise HTTPException(502, f"Yönetmen LLM hata ({llm.provider()}): {e}")

    content = (content or "").strip()
    if not content:
        content = fallback_director_reply(sess, body.message or "")
        print(
            f"[director] empty LLM reply → fallback (model={model})",
            flush=True,
        )

    parsed = extract_json_object(content)
    brief = None
    ready = False
    reply = content
    if parsed and parsed.get("reply"):
        reply = str(parsed["reply"]).strip() or content
    if not (reply or "").strip():
        reply = fallback_director_reply(sess, body.message or "")

    # Auto-finalize only when JSON/brief is present — not on casual chat
    # (false positives were hanging on expand and returning empty to the UI)
    should_finalize = False
    if parsed:
        brief_cand = (
            parsed["brief"]
            if isinstance(parsed.get("brief"), dict)
            else parsed
            if isinstance(parsed.get("shots"), list)
            else None
        )
        if isinstance(brief_cand, dict) and (
            brief_cand.get("shots")
            or brief_cand.get("expectedShotCount")
            or brief_cand.get("characters")
            or parsed.get("ready") is True
        ):
            should_finalize = True
        elif parsed.get("ready") is True:
            should_finalize = True
    if not should_finalize and content and (
        re.search(r'"shots"\s*:\s*\[', content)
        and re.search(r'"expectedShotCount"\s*:\s*\d+', content)
    ):
        should_finalize = True

    has_patch = bool(
        parsed
        and (
            isinstance(parsed.get("patch"), dict)
            or (isinstance(parsed.get("patches"), list) and parsed.get("patches"))
        )
    )
    if has_patch and isinstance(sess.get("brief"), dict) and (sess["brief"].get("shots") or []):
        sess["brief"] = apply_shot_patches(sess["brief"], parsed)
        sess["ready"] = True
        ready = True
        brief = sess["brief"]
        n = len(brief.get("shots") or [])
        note = f"Plan güncellendi ({n} shot). Plan sekmesinden oku / düzelt."
        if parsed.get("reply"):
            reply = str(parsed["reply"]).strip() or reply
        if note not in (reply or ""):
            reply = ((reply or "").rstrip() + "\n\n" + note).strip()
    elif should_finalize:
        if _looks_like_finished_plan(content) and (
            not parsed
            or not (
                isinstance(parsed.get("brief"), dict)
                and (parsed["brief"].get("shots") or [])
            )
            and not (isinstance(parsed.get("shots"), list) and parsed.get("shots"))
        ):
            mid = (
                "Senaryo alındı — SCENE prompt’lar tamamlanıyor, biraz bekle…"
            )
            sess["messages"].append({"role": "assistant", "content": mid})
            _sessions[sid] = sess
            _save_sessions()
        brief = await _brief_from_director_text(
            content, model=model, sess=sess, expand=True
        )
        if brief and brief.get("shots"):
            n = len(brief["shots"])
            need = brief.get("expectedShotCount") or n
            total = brief.get("totalDurationSec")
            canned = (
                f"{n} shot hazır"
                + (f" / hedef {need}" if need and need != n else "")
                + (f" · {total}sn" if total else "")
            )
            if plan_mode:
                model_reply = str(parsed.get("reply") or "").strip() if parsed else ""
                reply = model_reply or (
                    canned + ".\n\nPlan hazır — shot’ları Plan sekmesinde düzenle; beğeninçe Üretime al."
                )
                if "Plan sekme" not in reply:
                    reply = reply.rstrip() + "\n\nPlan sekmesinden detaylı düzenle."
            else:
                reply = (
                    canned
                    + ".\n\n**Üretime al** — tüm shot’lar continue zinciriyle kuyruğa alınır."
                )
                if brief.get("silentAudio"):
                    reply += "\nSessiz müzik klibi: finalde şarkı mux."
                if brief.get("shotsIncomplete"):
                    reply += f"\nUyarı: {n}/{need} shot."
            ready = True
            sess["brief"] = brief
            sess["ready"] = True
            if brief.get("purpose") == "music_video":
                sess["purpose"] = "music_video"
                sess["silent_audio"] = True
        elif parsed and parsed.get("reply"):
            reply = str(parsed["reply"])

    sess["messages"].append({"role": "assistant", "content": reply})
    sess["last_raw"] = content
    _sessions[sid] = sess
    _save_sessions()
    out_brief = brief or sess.get("brief")
    out_shots = (out_brief or {}).get("shots") or []
    # Keep ready sticky after a finished brief so UI can show shot panel + Üretime al
    # while the user keeps chatting / revising.
    out_ready = bool(ready or (sess.get("ready") and out_shots))
    cinema_out = None
    if sess.get("cinema_studio") and out_ready and out_brief:
        try:
            role = str((cinema.load() or {}).get("role_script") or "")
            cinema_out = cinema.ingest_from_director_brief(out_brief, role)
        except Exception as e:
            slog.error("cinema studio ingest from director failed", err=e)
    return {
        "session_id": sid,
        "reply": reply,
        "ready": out_ready,
        "brief": out_brief,
        "shot_count": len(out_shots),
        "model": model,
        "messages": sess["messages"],
        "cinema": cinema_out,
    }


class DirectorRecoverBody(BaseModel):
    session_id: str
    text: Optional[str] = None
    expand: bool = True


@app.post("/api/director/recover")
async def director_recover(body: DirectorRecoverBody):
    """Parse brief from pasted/raw text or last model message — force ready for queue."""
    sess = _sessions.get(body.session_id)
    if not sess:
        raise HTTPException(400, "Oturum yok")
    raw = (body.text or "").strip() or (sess.get("last_raw") or "")
    if not raw:
        # fall back: stitch recent assistant messages (truncated JSON often spans one long reply)
        parts = []
        for m in reversed(sess.get("messages") or []):
            if m.get("role") == "assistant" and m.get("content"):
                parts.append(m["content"])
                if len(parts) >= 3:
                    break
        raw = "\n\n".join(reversed(parts))
    if not raw:
        raise HTTPException(400, "Ayrıştırılacak metin yok")
    parsed = extract_json_object(raw)
    brief_src = None
    if parsed:
        brief_src = (
            parsed["brief"] if isinstance(parsed.get("brief"), dict) else parsed
        )
    # Truncated "shots": [ … — rebuild skeleton then expand full SCENE prompts
    if not isinstance(brief_src, dict) or not (
        brief_src.get("shots") or brief_src.get("expectedShotCount") or brief_src.get("characters")
    ):
        brief_src = skeleton_brief_from_text(raw)
    if not isinstance(brief_src, dict):
        raise HTTPException(
            400,
            "JSON brief bulunamadı — yönetmen yanıtını veya JSON’u yapıştırıp tekrar dene",
        )
    if sess.get("clip_duration") in ALLOWED_DURATIONS:
        brief_src["clipDurationSec"] = int(sess["clip_duration"])
    if sess.get("purpose"):
        brief_src["purpose"] = sess["purpose"]
    if sess.get("silent_audio") or (brief_src.get("purpose") or "") == "music_video":
        brief_src["silentAudio"] = True
    brief = _apply_session_timing(validate_brief(brief_src), sess)
    model = sess.get("model") or _director_model or "qwen3:8b"
    need = brief.get("expectedShotCount") or 0
    have = len(brief.get("shots") or [])
    if body.expand and need and have < need:
        # Generate missing SCENE h3Prompts via Ollama (may take a few minutes)
        brief = await _expand_brief_shots(brief, model)
    else:
        brief = ensure_shot_count_sync(brief)
    if not brief.get("shots"):
        # Still empty — force expand from skeleton even if expected missing
        if not brief.get("expectedShotCount"):
            brief["expectedShotCount"] = 12
            brief["totalDurationSec"] = brief.get("totalDurationSec") or 60
            brief["clipDurationSec"] = brief.get("clipDurationSec") or 5
        if body.expand:
            brief = await _expand_brief_shots(brief, model)
        else:
            brief = ensure_shot_count_sync(brief)
    if not brief.get("shots"):
        raise HTTPException(
            400,
            "Shot listesi boş — Ollama shot üretemedi. Yönetmene yaz: "
            "“12 shot’luk ready:true JSON brief ver, her h3Prompt ≥900 karakter”.",
        )
    sess["brief"] = brief
    sess["ready"] = True
    sess["last_raw"] = raw
    if brief.get("purpose") == "music_video":
        sess["silent_audio"] = True
        sess["purpose"] = "music_video"
    n = len(brief["shots"])
    need = brief.get("expectedShotCount") or n
    reply = (
        f"Brief kurtarıldı: {n} shot"
        + (f" / hedef {need}" if need else "")
        + ". **Üretime al** butonuna bas."
    )
    if brief.get("shotsIncomplete"):
        reply += f"\n\nUyarı: hâlâ {n}/{need} — yine de üretime alabilirsin."
    sess["messages"].append({"role": "assistant", "content": reply})
    _sessions[body.session_id] = sess
    _save_sessions()
    return {
        "session_id": body.session_id,
        "ready": True,
        "reply": reply,
        "brief": brief,
        "shot_count": n,
    }


@app.post("/api/director/commit")
async def director_commit(body: DirectorCommitBody):
    sess = _sessions.get(body.session_id)
    if not sess or not sess.get("brief"):
        raise HTTPException(400, "Brief yok — önce yönetmenle konuşmayı bitir veya ‘Son yanıttan brief çıkar’")
    model = sess.get("model") or _director_model or "qwen3:8b"
    if body.clip_duration in ALLOWED_DURATIONS:
        sess["clip_duration"] = int(body.clip_duration)
    brief = _apply_session_timing(validate_brief(sess["brief"]), sess)
    # Always fill to N shots (LLM expand + placeholder pad) before queue
    if brief.get("expectedShotCount") and len(brief.get("shots") or []) < brief["expectedShotCount"]:
        brief = await _expand_brief_shots(brief, model)
    else:
        brief = ensure_shot_count_sync(brief)
    sess["brief"] = brief
    _save_sessions()
    shots = brief.get("shots") or []
    if not shots:
        raise HTTPException(400, "Shot listesi boş")

    # Narrative default: decide whether to link continue chain when queueing a film package
    link = body.link_continue
    if link is None:
        link = True
    # Propagate choice into brief so director.* helpers respect it (new: brief["force_continue"])
    brief["force_continue"] = bool(link)
    if body.purpose:
        brief["purpose"] = body.purpose
        sess["purpose"] = body.purpose
    if body.silent_audio is not None:
        brief["silentAudio"] = bool(body.silent_audio)
        sess["silent_audio"] = bool(body.silent_audio)
    elif sess.get("silent_audio") or (brief.get("purpose") or "").lower() in (
        "music_video",
        "music-video",
    ):
        brief["silentAudio"] = True
    brief = ensure_shot_count_sync(validate_brief(brief))
    # ensure_shot_count_sync will respect brief["force_continue"]; use resulting shots directly
    shots = brief.get("shots") or shots
    prompts = [s["h3Prompt"] for s in shots]

    dur = int(brief.get("clipDurationSec") or shots[0].get("durationSec") or 5)
    if dur not in ALLOWED_DURATIONS:
        dur = 5
    aspect = (body.aspect or "").strip() or brief.get("aspect") or "16:9"
    quality = str(body.quality or "720")
    silent = bool(brief.get("silentAudio")) or bool(sess.get("music_id"))
    steps = int(body.steps) if body.steps and int(body.steps) > 0 else 20
    sampler = (body.sampler or "res_multistep").strip() or "res_multistep"
    scheduler = (body.scheduler or "simple").strip() or "simple"
    steps, sampler, scheduler = _with_lora_preset(body, steps, sampler, scheduler)
    lora_bits = _lora_fields(body)

    applied = {
        "prompt": prompts[0],
        "batch_prompts": "\n\n---\n\n".join(prompts),
        "prompts": prompts,
        "duration": dur,
        "aspect": aspect,
        "quality": quality,
        "steps": steps,
        "sampler": sampler,
        "scheduler": scheduler,
        "purpose": brief.get("purpose"),
        "visualStyle": brief.get("visualStyle"),
        "logline": brief.get("logline"),
        "shot_count": len(shots),
        "expected_shot_count": brief.get("expectedShotCount") or len(shots),
        "total_duration_sec": brief.get("totalDurationSec"),
        "link_continue": bool(link),
        "silent_audio": silent,
    }

    music_id = sess.get("music_id")
    if music_id:
        applied["music_id"] = music_id

    queued = None
    if body.queue:
        bb = BatchBody(
            prompts=prompts,
            duration=applied["duration"],
            aspect=aspect,
            quality=quality,
            steps=steps,
            sampler=sampler,
            scheduler=scheduler,
            link_continue=bool(link),
            append_to_chain=bool(body.append_to_chain),
            music_id=music_id,
            silent_audio=silent,
            purpose=brief.get("purpose"),
            lora_id=lora_bits.get("lora_id") or None,
            lora_name=lora_bits.get("lora_name") or None,
            lora_strength=lora_bits.get("lora_strength"),
            sage_attention=_sage_mode(body),
        )
        queued = await batch(bb)

    return {"applied": applied, "brief": brief, "queued": queued}


# ─── Music (additive: upload → analyze → mux; does not alter generate core) ─


class MusicAnalyzeBody(BaseModel):
    music_id: str
    session_id: Optional[str] = None
    lyrics: Optional[str] = None
    concept: Optional[str] = None
    clip_duration: int = 5
    visual_style: str = "realistic"
    model: Optional[str] = None
    expand: bool = True


class MusicMuxBody(BaseModel):
    music_id: str
    job_ids: Optional[list[str]] = None


@app.get("/api/music/status")
async def music_status(music_id: Optional[str] = None):
    MUSIC.mkdir(parents=True, exist_ok=True)
    if not music_id:
        return {"ok": True, "music": None}
    try:
        meta = load_meta(MUSIC, music_id)
    except FileNotFoundError:
        raise HTTPException(404, "şarkı yok")
    final = MUSIC / f"{music_id}_final.mp4"
    clip_sec = int(meta.get("clipDurationSec") or 5)
    linked = [j for j in _jobs if j.get("music_id") == music_id]
    done_n = sum(1 for j in linked if j.get("status") == "done")
    pending_n = sum(1 for j in linked if j.get("status") in ("queued", "running"))
    return {
        "ok": True,
        "music": {
            "id": meta["id"],
            "filename": meta.get("filename"),
            "durationSec": meta.get("durationSec"),
            "lyrics": meta.get("lyrics") or "",
            "concept": meta.get("concept") or "",
            "sections": suggested_sections(float(meta.get("durationSec") or 0), clip_sec),
            "final_ready": final.exists(),
            "final_url": f"/api/music/{music_id}/final" if final.exists() else None,
            "linked_jobs": len(linked),
            "linked_done": done_n,
            "linked_pending": pending_n,
        },
    }


@app.post("/api/music/upload")
async def music_upload(file: UploadFile = File(...)):
    MUSIC.mkdir(parents=True, exist_ok=True)
    raw = await file.read()
    if not raw or len(raw) < 64:
        raise HTTPException(400, "boş dosya")
    if len(raw) > 80 * 1024 * 1024:
        raise HTTPException(400, "şarkı 80MB üstü olamaz")
    try:
        meta = save_upload(MUSIC, filename=file.filename or "track.mp3", data=raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"upload/probe hata: {e}")
    dur = float(meta["durationSec"])
    slog.info("music uploaded", id=meta["id"], dur=dur, name=meta.get("filename"))
    return {
        "music": {
            "id": meta["id"],
            "filename": meta.get("filename"),
            "durationSec": meta.get("durationSec"),
            "sections": suggested_sections(dur, 5),
            "suggestedShots5": max(1, math.ceil(dur / 5)),
            "suggestedShots10": max(1, math.ceil(dur / 10)),
        }
    }


@app.post("/api/music/analyze")
async def music_analyze(body: MusicAnalyzeBody):
    """Build SCENE brief from song duration (+ optional lyrics) via Director LLM → session brief."""
    if not await llm.healthy():
        raise HTTPException(
            503,
            "Yönetmen LLM hazır değil — Ayarlar’dan Gemini key veya Ollama kur.",
        )
    try:
        meta = load_meta(MUSIC, body.music_id)
    except FileNotFoundError:
        raise HTTPException(404, "şarkı yok — önce yükle")

    clip = body.clip_duration if body.clip_duration in ALLOWED_DURATIONS else 5
    lyrics = (body.lyrics or "").strip()
    concept = (body.concept or "").strip()
    update_meta(
        MUSIC,
        body.music_id,
        lyrics=lyrics,
        concept=concept,
        clipDurationSec=clip,
    )
    meta = load_meta(MUSIC, body.music_id)
    audio_path = Path(meta.get("path") or "")
    timeline: list = []
    if audio_path.exists():
        try:
            timeline = probe_energy_timeline(
                audio_path,
                duration_sec=float(meta.get("durationSec") or 0),
                clip_sec=clip,
            )
        except Exception as e:
            slog.warn("music energy probe failed", err=str(e))
            timeline = []
    if timeline:
        update_meta(MUSIC, body.music_id, energyTimeline=timeline)
        meta = load_meta(MUSIC, body.music_id)

    sid = body.session_id
    if not sid or sid not in _sessions:
        created = await director_new_session(body.model)
        sid = created["id"]
    sess = _sessions[sid]
    ui_lang = normalize_ui_lang(sess.get("ui_lang"))
    sess["ui_lang"] = ui_lang
    try:
        model = await llm.resolve_model(body.model or sess.get("model") or _director_model)
    except Exception as e:
        raise HTTPException(400, str(e))
    sess["model"] = model
    sess["music_id"] = body.music_id

    seed = build_song_director_seed(
        meta=meta,
        clip_sec=clip,
        lyrics=lyrics,
        concept=concept,
        visual_style=body.visual_style or "realistic",
        timeline=timeline,
    )
    sess["messages"].append({"role": "user", "content": seed})
    history = [{"role": "system", "content": (system_prompt() or "") + ui_lang_addendum(ui_lang)}] + sess["messages"][-24:]
    try:
        content = await llm.chat(
            model,
            history,
            temperature=0.5,
            think=False,
            retries=3,
            num_predict=4096,
        )
    except Exception as e:
        raise HTTPException(502, f"Yönetmen LLM hata ({llm.provider()}): {e}")

    content = (content or "").strip()
    if not content:
        content = fallback_director_reply(
            sess,
            "müzik analizi — süreye göre SCENE brief üret",
        )
        print(f"[director/music] empty LLM → fallback (model={model})", flush=True)

    parsed = extract_json_object(content)
    brief = None
    reply = content
    brief_src = None
    if parsed:
        brief_src = (
            parsed["brief"]
            if isinstance(parsed.get("brief"), dict)
            else parsed
            if isinstance(parsed.get("shots"), list)
            else None
        )
        if parsed.get("reply"):
            reply = str(parsed["reply"]).strip() or content
    if not (reply or "").strip():
        reply = fallback_director_reply(sess, "müzik analizi")
    if brief_src:
        brief = validate_brief(brief_src)
        # Force song timing onto brief
        dur_i = int(round(float(meta["durationSec"])))
        brief["purpose"] = "music_video"
        brief["silentAudio"] = True
        brief["visualStyle"] = body.visual_style or brief.get("visualStyle") or "realistic"
        brief["clipDurationSec"] = clip
        brief["totalDurationSec"] = dur_i
        brief["expectedShotCount"] = expected_shot_count(dur_i, clip)
        brief = validate_brief(brief)
        sess["purpose"] = "music_video"
        sess["silent_audio"] = True
        sess["visual_style"] = brief.get("visualStyle")
        if body.expand and brief.get("shotsIncomplete") and brief.get("expectedShotCount"):
            reply = (
                f"{reply}\n\nEksik shot’lar tamamlanıyor "
                f"({len(brief.get('shots') or [])}/{brief['expectedShotCount']})…"
            )
            sess["messages"].append({"role": "assistant", "content": reply})
            _sessions[sid] = sess
            _save_sessions()
            brief = await _expand_brief_shots(brief, model)
        else:
            brief = ensure_shot_count_sync(brief)

        if timeline:
            brief = stamp_shots_with_timeline(brief, timeline)
        brief["force_continue"] = True
        brief["silentAudio"] = True

    if not brief or not brief.get("shots"):
        sess["messages"].append({"role": "assistant", "content": reply})
        sess["last_raw"] = content
        _sessions[sid] = sess
        _save_sessions()
        raise HTTPException(
            422,
            "Şarkı analizi brief üretemedi — Yönetmen sohbetinden devam et veya ‘Son yanıttan brief çıkar’.",
        )

    n = len(brief["shots"])
    need = brief.get("expectedShotCount") or n
    reply = (
        f"Şarkı analizi hazır: {meta.get('filename')} · {meta.get('durationSec')}sn → "
        f"{n} shot (hedef {need}). Görüntü şarkı enerjisine göre yazıldı; lip-sync yok. "
        "**Üretime al** → bitince **Şarkılı final**."
    )
    if brief.get("shotsIncomplete"):
        reply += f"\n\nUyarı: {n}/{need} shot — yine de kuyruğa alabilirsin."
    sess["brief"] = brief
    sess["ready"] = True
    sess["messages"].append({"role": "assistant", "content": reply})
    sess["last_raw"] = content
    _sessions[sid] = sess
    _save_sessions()
    update_meta(MUSIC, body.music_id, lastSessionId=sid, lastShotCount=n)
    slog.info("music analyze ok", music_id=body.music_id, shots=n, need=need)
    return {
        "session_id": sid,
        "ready": True,
        "reply": reply,
        "brief": brief,
        "shot_count": n,
        "music_id": body.music_id,
        "model": model,
    }


@app.post("/api/music/mux")
async def music_mux(body: MusicMuxBody):
    """Concat done clips for this song and replace audio with the uploaded track."""
    try:
        meta = load_meta(MUSIC, body.music_id)
    except FileNotFoundError:
        raise HTTPException(404, "şarkı yok")
    audio = Path(meta["path"])
    if not audio.exists():
        raise HTTPException(404, "şarkı dosyası yok")

    jobs: list[dict] = []
    if body.job_ids:
        for jid in body.job_ids:
            j = next((x for x in _jobs if x["id"] == jid), None)
            if not j:
                raise HTTPException(400, f"job yok: {jid}")
            # Explicit ids must still belong to this song (never mix old batches)
            if j.get("music_id") and j.get("music_id") != body.music_id:
                raise HTTPException(
                    400,
                    f"job {jid[:8]} başka şarkıya ait — eski kelip birleştirilmez",
                )
            if not j.get("music_id"):
                raise HTTPException(
                    400,
                    f"job {jid[:8]} bu şarkıya bağlı değil — önce Şarkıdan brief → kuyruğa al",
                )
            jobs.append(j)
    else:
        # ONLY clips produced for this music_id — never fall back to older gallery jobs
        tagged = [
            j
            for j in _jobs
            if j.get("music_id") == body.music_id and j.get("status") == "done"
        ]
        tagged.sort(key=lambda j: (j.get("batch_index") or 0, j.get("created_at") or 0))
        jobs = tagged
    if not jobs:
        linked_any = [j for j in _jobs if j.get("music_id") == body.music_id]
        pending = [j for j in linked_any if j.get("status") in ("queued", "running")]
        if pending:
            raise HTTPException(
                400,
                f"Bu şarkı için {len(pending)} klip hâlâ üretiliyor — bitince Şarkılı final’e bas. "
                "Eski galeri klipleri birleştirilmez.",
            )
        if linked_any:
            raise HTTPException(
                400,
                "Bu şarkıya bağlı bitmiş klip yok (hata/iptal olabilir). "
                "Yeni senaryo → Üretime al ile yeniden üret.",
            )
        raise HTTPException(
            400,
            "Bu şarkı için henüz yeni sahne üretilmemiş. "
            "Sıra: senaryo bitince Üretime al → bitince Şarkılı final. "
            "Şarkılı final eski klipleri birleştirmez.",
        )
    not_done = [j["id"] for j in jobs if j.get("status") != "done"]
    if not_done:
        raise HTTPException(400, f"henüz bitmemiş: {', '.join(not_done[:5])}")

    paths: list[Path] = []
    for j in jobs:
        try:
            paths.append(await _ensure_job_video(j))
        except Exception as e:
            raise HTTPException(400, f"klip alınamadı ({j['id'][:8]}): {e}")

    out = MUSIC / f"{body.music_id}_final.mp4"
    try:
        concat_and_mux(video_paths=paths, audio_path=audio, out_path=out)
    except Exception as e:
        slog.error("music mux failed", err=e, music_id=body.music_id)
        raise HTTPException(500, f"mux hata: {e}")

    update_meta(MUSIC, body.music_id, finalPath=str(out), finalAt=time.time())
    slog.info("music mux ok", music_id=body.music_id, clips=len(paths), out=str(out))
    return {
        "ok": True,
        "music_id": body.music_id,
        "clip_count": len(paths),
        "final_url": f"/api/music/{body.music_id}/final",
        "duration_hint_sec": meta.get("durationSec"),
    }


@app.get("/api/music/{music_id}/final")
async def music_final(music_id: str):
    path = MUSIC / f"{music_id}_final.mp4"
    if not path.exists():
        raise HTTPException(404, "final yok — önce mux")
    return FileResponse(path, media_type="video/mp4", filename=f"h3_music_{music_id[:8]}.mp4")


async def _ensure_job_video(job: dict) -> Path:
    """Return local mp4 path for a job; gallery archive or re-download from Comfy."""
    local = job.get("local_path")
    if local and Path(local).exists():
        return Path(local)
    jid = str(job.get("id") or "")
    dest = CLIPS / f"{jid}.mp4"
    if dest.exists():
        job["local_path"] = str(dest)
        _save_jobs_if_known(job)
        return dest
    gal = GALLERY / f"{jid}.mp4"
    if gal.exists():
        job["local_path"] = str(gal)
        return gal
    entry = next((g for g in _gallery if g.get("id") == jid), None)
    if entry and entry.get("local_path") and Path(entry["local_path"]).exists():
        job["local_path"] = str(entry["local_path"])
        return Path(entry["local_path"])
    out = job.get("output") or {}
    filename = out.get("filename")
    if not filename:
        raise RuntimeError("önceki klip videosu yok — continue edilemez")
    await comfy.download_view(
        filename,
        out.get("subfolder") or "",
        out.get("type") or "output",
        dest,
    )
    job["local_path"] = str(dest)
    _save_jobs_if_known(job)
    return dest


async def _prepare_last_frame(job: dict, *, upload: bool = True) -> Path:
    """Extract last frame when a clip finishes (or on demand). Saves on job."""
    video_path = await _ensure_job_video(job)
    frame_path = FRAMES / f"{job['id']}_last.png"
    if not frame_path.exists() or frame_path.stat().st_size < 100:
        extract_last_frame(video_path, frame_path)
    job["last_frame_path"] = str(frame_path)
    job["last_frame_url"] = f"/api/clips/{job['id']}/last-frame"
    if upload:
        last_err = None
        for attempt in range(4):
            try:
                name = await comfy.upload_image(
                    frame_path, f"h3_studio_{job['id']}_last.png"
                )
                job["last_frame_name"] = name
                job.pop("last_frame_upload_error", None)
                last_err = None
                break
            except Exception as e:
                last_err = e
                await asyncio.sleep(1.2 * (attempt + 1))
        if last_err:
            job["last_frame_upload_error"] = str(last_err)[-240:]
    _save_jobs_if_known(job)
    return frame_path


async def _resolve_first_frame(job: dict) -> Optional[str]:
    if job.get("first_frame_name"):
        return job["first_frame_name"]
    parent_id = job.get("continue_from")
    if not parent_id:
        return None
    parent = _clip_record(parent_id)
    if not parent or parent.get("status") != "done":
        raise RuntimeError("önceki klip bitmeden continue edilemez")

    # Ensure parent last frame file exists (extract if needed)
    try:
        await _prepare_last_frame(parent, upload=False)
    except Exception as e:
        raise RuntimeError(f"önceki klipten last frame alınamadı: {e}")

    src = Path(parent.get("last_frame_path") or FRAMES / f"{parent['id']}_last.png")
    if not src.exists():
        raise RuntimeError("önceki klip videosu yok — continue edilemez")

    # CRITICAL: H3 first_frame must match target width/height exactly or Comfy
    # throws latent shape errors (e.g. invalid for input of size 86400).
    tw, th = snap_h3_size(
        int(job.get("width") or parent.get("width") or 1280),
        int(job.get("height") or parent.get("height") or 736),
    )
    job["width"], job["height"] = tw, th
    sized = FRAMES / f"{job['id']}_first_{tw}x{th}.png"
    try:
        resize_image(src, sized, tw, th)
    except Exception as e:
        raise RuntimeError(f"first_frame {tw}x{th} ölçeklenemedi: {e}")

    last_err = None
    for attempt in range(4):
        try:
            name = await comfy.upload_image(sized, f"h3_studio_{job['id']}_first.png")
            job["first_frame_path"] = str(sized)
            return name
        except Exception as e:
            last_err = e
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"son kare Comfy'ye yüklenemedi: {last_err}")


def _queue_has_prompt(pid: str, items: list) -> bool:
    for item in items or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        # Comfy: [number, prompt_id, prompt, extra, outputs]
        if item[1] == pid:
            return True
        # Rare older shape: prompt_id nested
        if isinstance(item[1], dict) and item[1].get("prompt_id") == pid:
            return True
    return False


async def _run_job(job: dict):
    job["status"] = "running"
    job["error"] = None
    if not job.get("started_at"):
        job["started_at"] = time.time()
    reattach = bool(job.pop("_reattach", None) and job.get("prompt_id"))
    if reattach:
        job["progress"] = max(int(job.get("progress") or 0), 50)
        job["progress_label"] = "Comfy’ye yeniden bağlandı"
        _save_jobs()
        prompt_id = job["prompt_id"]
        slog.info_job(job, "reattach wait", prompt=str(prompt_id)[:8])
    else:
        job["progress"] = 2
        job["progress_label"] = "hazırlanıyor"
        _save_jobs()
        await _free_llm_for_production()
        job["progress"] = 5
        job["progress_label"] = "frame / graph"
        _save_jobs()
        first = None
        if (job.get("mode") or "").lower() != "multishot":
            first = await _resolve_first_frame(job)
            if job.get("mode") == "continue" or job.get("continue_from"):
                if not first:
                    raise RuntimeError(
                        "Devam için last frame yok — önce bitmiş videoda last frame hazırlanmalı"
                    )
                job["first_frame_name"] = first
        # H3 first_frame path hard-fails on non-×32 sizes (e.g. 1280×720).
        w, h = snap_h3_size(int(job.get("width") or 1280), int(job.get("height") or 736))
        if job.get("width") != w or job.get("height") != h:
            job["width"], job["height"] = w, h
            _save_jobs()
        length = duration_to_length(int(job["duration"]))
        silent = bool(job.get("silent_audio") or job.get("music_id"))
        mode = (job.get("mode") or "t2v").lower()
        face_refs = [
            str(x)
            for x in (job.get("ref_images") or [])
            if x and (job.get("ref_role") == "face" or mode in ("face", "face_continue"))
        ]
        last_frame = job.get("last_frame_name")
        ref_videos = [str(x) for x in (job.get("ref_videos") or []) if x]
        lora_name, lora_strength = _lora_for_graph(job)
        if mode == "multishot":
            script = (job.get("script") or job.get("prompt") or "").strip()
            if not script:
                raise RuntimeError("Kesintisiz zincir için script yok")
            prompt = build_multishot_prompt(
                script=script,
                width=w,
                height=h,
                frames_per_shot=length,
                seed=int(job["seed"]),
                steps=int(job["steps"]),
                sampler=job.get("sampler") or "res_multistep",
                scheduler=job.get("scheduler") or "simple",
                shot_count=0,
                filename_prefix=f"video/H3_Studio/{job['id'][:8]}",
                silent_audio=silent,
                lora_name=lora_name,
                lora_strength=lora_strength,
                sage_attention=_sage_mode(job),
            )
        elif mode in ("ref", "face", "v2v"):
            refs = [str(x) for x in (job.get("ref_images") or []) if x]
            if not refs and not ref_videos:
                raise RuntimeError("Referans görsel/video eksik")
            size_mode = job.get("ref_image_size") or ("max" if mode == "face" else "match")
            prompt = build_ref2va_prompt(
                text=job["prompt"],
                ref_image_names=refs,
                ref_video_names=ref_videos,
                width=w,
                height=h,
                length=length,
                seed=int(job["seed"]),
                steps=int(job["steps"]),
                sampler=job.get("sampler") or "res_multistep",
                scheduler=job.get("scheduler") or "simple",
                ref_image_size=size_mode,
                filename_prefix=f"video/H3_Studio/{job['id'][:8]}",
                silent_audio=silent,
                include_video_audio=bool(job.get("include_video_audio", True)),
                lora_name=lora_name,
                lora_strength=lora_strength,
                sage_attention=_sage_mode(job),
            )
        elif mode == "face_continue" or (
            (mode == "continue" or job.get("continue_from")) and face_refs
        ):
            # Face lock + last frame as extra Picture → Ref2VA identity across shots
            if not face_refs:
                raise RuntimeError("Yüz kilidi portreleri eksik")
            if not first:
                raise RuntimeError("Devam için last frame yok")
            n_face = len(face_refs)
            refs = list(face_refs) + [first]
            if len(refs) > 9:
                refs = face_refs[:8] + [first]
                n_face = len(refs) - 1
            text = enhance_ref_prompt(
                job["prompt"],
                n_images=len(refs),
                role="face_continue",
                n_face=n_face,
            )
            size_mode = job.get("ref_image_size") or "max"
            prompt = build_ref2va_prompt(
                text=text,
                ref_image_names=refs,
                width=w,
                height=h,
                length=length,
                seed=int(job["seed"]),
                steps=int(job["steps"]),
                sampler=job.get("sampler") or "res_multistep",
                scheduler=job.get("scheduler") or "simple",
                ref_image_size=size_mode,
                filename_prefix=f"video/H3_Studio/{job['id'][:8]}",
                silent_audio=silent,
                lora_name=lora_name,
                lora_strength=lora_strength,
                sage_attention=_sage_mode(job),
            )
            job["mode"] = "face_continue"
            job["ref_role"] = "face"
        else:
            prompt = build_t2v_prompt(
                text=job["prompt"],
                width=w,
                height=h,
                length=length,
                seed=int(job["seed"]),
                steps=int(job["steps"]),
                sampler=job.get("sampler") or "res_multistep",
                scheduler=job.get("scheduler") or "simple",
                first_frame_name=first,
                last_frame_name=last_frame,
                filename_prefix=f"video/H3_Studio/{job['id'][:8]}",
                silent_audio=silent,
                lora_name=lora_name,
                lora_strength=lora_strength,
                sage_attention=_sage_mode(job),
            )
        job["progress"] = 10
        job["progress_label"] = "Comfy kuyruğa"
        _save_jobs()
        prompt_id = await comfy.queue_prompt(prompt)
        job["prompt_id"] = prompt_id
        job["progress"] = 12
        job["progress_label"] = "Comfy çalışıyor"
        _save_jobs()
        slog.info_job(
            job,
            "comfy queued",
            prompt=str(prompt_id)[:8],
            size=f"{w}x{h}",
            length=length,
            first_frame=bool(first),
            mode=mode,
            refs=len(job.get("ref_images") or []),
        )

    stop_ws = asyncio.Event()
    saw_running = False
    absent_ticks = 0

    async def _on_prog(pct: int, label: str, meta: Optional[dict] = None):
        """Comfy WS progress — always win over soft/fake %."""
        if job["status"] == "cancelled":
            return
        meta = meta or {}
        job["progress"] = max(0, min(99, int(pct)))
        job["progress_label"] = label
        job["_ws_progress_at"] = time.time()
        if meta.get("comfy_step") is not None:
            job["comfy_step"] = int(meta["comfy_step"])
        if meta.get("comfy_step_max") is not None:
            job["comfy_step_max"] = int(meta["comfy_step_max"])
        if meta.get("source"):
            job["progress_source"] = meta["source"]
        _save_jobs_throttled(0.8)

    # Progress WS is best-effort only — NEVER cancel/await it in a way that
    # can raise CancelledError into the queue loop (that killed continue chains).
    ws_task = asyncio.create_task(
        comfy.watch_prompt(prompt_id, _on_prog, stop_event=stop_ws),
        name=f"comfy-ws-{str(prompt_id)[:8]}",
    )

    try:
        for tick in range(7200):  # up to ~2h for long H3 runs
            if job["status"] == "cancelled":
                return
            try:
                hist = await comfy.history(prompt_id)
            except Exception as e:
                if tick % 5 == 0:
                    job["progress_label"] = f"history bekleniyor ({e})"[:80]
                    _save_jobs_throttled(2.0)
                await asyncio.sleep(1)
                continue

            if prompt_id in hist:
                entry = hist[prompt_id]
                status = entry.get("status") or {}
                status_str = (status.get("status_str") or "").lower()
                if status_str == "error":
                    msgs = status.get("messages") or []
                    job["status"] = "error"
                    job["error"] = comfy.format_execution_error(msgs)
                    job["progress_label"] = "hata"
                    _save_jobs()
                    slog.error_job(job, "comfy execution error", err=job["error"])
                    await _notify_job(job, "error")
                    return
                outputs = entry.get("outputs") or {}
                video_meta = comfy.extract_video_meta(outputs)
                if not video_meta:
                    if status.get("completed") is True or status_str == "success":
                        job["status"] = "error"
                        job["error"] = "çıktı videosu yok (SaveVideo boş)"
                        job["progress_label"] = "hata"
                        _save_jobs()
                        slog.error_job(job, "no video output", status=status_str)
                        await _notify_job(job, "error")
                        return
                    cur = int(job.get("progress") or 0)
                    if cur < 90:
                        job["progress"] = max(cur, min(90, 20 + tick // 2))
                        job["progress_label"] = "üretiliyor…"
                        _save_jobs_throttled(2.0)
                    await asyncio.sleep(1)
                    continue

                job["progress"] = 96
                job["progress_label"] = "video indiriliyor"
                _save_jobs()
                dest = CLIPS / f"{job['id']}.mp4"
                await comfy.download_view(
                    video_meta["filename"],
                    video_meta.get("subfolder") or "",
                    video_meta.get("type") or "output",
                    dest,
                )
                # Silent graph already skipped AudioVAE decode; strip only if a track slipped in
                if (job.get("silent_audio") or job.get("music_id")) and not job.get(
                    "audio_stripped"
                ):
                    try:
                        strip_audio(dest)
                        job["audio_stripped"] = True
                    except Exception as e:
                        job["audio_strip_error"] = str(e)[-240:]
                        slog.warn_job(job, "strip audio failed", err=e)
                job["output"] = {
                    "filename": video_meta["filename"],
                    "subfolder": video_meta.get("subfolder") or "",
                    "type": video_meta.get("type") or "output",
                    "url": f"/api/clips/{job['id']}/video",
                }
                job["local_path"] = str(dest)
                job["progress"] = 98
                job["progress_label"] = "last frame çıkarılıyor"
                _save_jobs()
                try:
                    await _prepare_last_frame(job, upload=True)
                except Exception as e:
                    job["last_frame_error"] = str(e)[-300:]
                    slog.exception("last frame prep failed", e, job=job["id"][:8])
                job["status"] = "done"
                job["progress"] = 100
                job["progress_label"] = "bitti"
                job["done_at"] = time.time()
                job.pop("_reattach", None)
                _save_jobs()
                try:
                    _archive_job_to_gallery(job)
                except Exception as e:
                    slog.warn_job(job, "gallery archive failed", err=e)
                slog.info_job(job, "done", file=video_meta.get("filename"))
                await _notify_job(job, "done")
                try:
                    await _maybe_auto_mux_cinema(job)
                except Exception as e:
                    slog.warn("cinema auto mux skip", err=e)
                return

            # Not in history yet — soft progress by elapsed time
            cur = int(job.get("progress") or 0)
            in_running = False
            in_pending = False
            queue_peek_ok = False
            if tick % 3 == 0:
                try:
                    q = await comfy.queue_status()
                    in_running = _queue_has_prompt(prompt_id, q.get("queue_running") or [])
                    in_pending = _queue_has_prompt(prompt_id, q.get("queue_pending") or [])
                    queue_peek_ok = True
                except Exception:
                    queue_peek_ok = False

            mins, secs = divmod(tick, 60)
            clock = f"{mins}m{secs:02d}s" if mins else f"{secs}s"

            ws_fresh = (time.time() - float(job.get("_ws_progress_at") or 0)) < 8.0
            if in_running:
                saw_running = True
                absent_ticks = 0
                # Soft estimate only when Comfy WS is quiet — never invent fake 94%
                if not ws_fresh:
                    step = job.get("comfy_step")
                    step_max = job.get("comfy_step_max")
                    if step is not None and step_max:
                        job["progress_label"] = (
                            f"örnekleme {int(step)}/{int(step_max)} · {clock}"
                        )
                    else:
                        job["progress_label"] = f"Comfy örnekliyor · {clock}"
                    # Gentle clock-only bump, hard-cap 85 so real WS can always override
                    if cur < 85:
                        creep = min(85, max(cur, 10 + tick // 8))
                        if creep > cur:
                            job["progress"] = creep
                            job["progress_source"] = "soft"
                    _save_jobs_throttled(2.0)
            elif in_pending:
                absent_ticks = 0
                if not ws_fresh:
                    job["progress"] = max(cur, 8)
                    job["progress_label"] = f"Comfy kuyruğunda · {clock}"
                    job["progress_source"] = "soft"
                    _save_jobs_throttled(2.0)
            else:
                # Only count confirmed absence (peek OK). Peek failures ≠ dropped.
                if queue_peek_ok:
                    absent_ticks += 3
                if saw_running:
                    if not ws_fresh:
                        # Keep last real Comfy %; only refresh the clock in the label
                        base = job.get("progress_label") or "çıktı bekleniyor"
                        base = re.sub(r"\s·\s\d+m\d{2}s|\s·\s\d+s$", "", str(base))
                        if "örnekleme" not in base and "çıktı" not in base:
                            base = "çıktı bekleniyor"
                        job["progress_label"] = f"{base} · {clock}"
                        _save_jobs_throttled(2.0)
                    # ~3 min confirmed gone from queue with no history
                    if absent_ticks >= 180:
                        job["status"] = "error"
                        job["error"] = (
                            "Comfy kuyruğundan düştü ama çıktı gelmedi — "
                            "Comfy terminalini kontrol et / Tekrar dene"
                        )
                        job["progress_label"] = "hata"
                        _save_jobs()
                        slog.error_job(job, "dropped from comfy queue", clock=clock)
                        await _notify_job(job, "error")
                        return
                else:
                    creep = min(92, 12 + tick // 4)
                    if creep > cur:
                        job["progress"] = creep
                    job["progress_label"] = f"Comfy’ye iletildi · {clock}"
                    _save_jobs_throttled(2.0)
                    if queue_peek_ok and tick > 240 and absent_ticks >= 240:
                        job["status"] = "error"
                        job["error"] = (
                            "Comfy işi almıyor gibi (4dk) — ComfyUI açık mı / VRAM dolu mu?"
                        )
                        job["progress_label"] = "hata"
                        _save_jobs()
                        slog.error_job(job, "comfy never took job", clock=clock)
                        await _notify_job(job, "error")
                        return
            await asyncio.sleep(1)
        job["status"] = "error"
        job["error"] = "timeout — Comfy yanıt vermedi"
        job["progress_label"] = "timeout"
        _save_jobs()
        slog.error_job(job, "hard timeout")
        await _notify_job(job, "error")
    finally:
        # Detach WS quietly — do not cancel()/await (CancelledError killed the queue).
        stop_ws.set()
        if ws_task is not None and not ws_task.done():
            def _silent(_t: asyncio.Task) -> None:
                try:
                    _t.exception()
                except Exception:
                    pass

            ws_task.add_done_callback(_silent)


def _clip_record(job_id: Optional[str]) -> Optional[dict]:
    """Queue job, else a gallery archive of the same id (for continue / last-frame)."""
    jid = (job_id or "").strip()
    if not jid:
        return None
    job = next((j for j in _jobs if j.get("id") == jid), None)
    if job:
        return job
    gal = next((g for g in _gallery if g.get("id") == jid), None)
    if not gal:
        return None
    rec = dict(gal)
    rec["id"] = jid
    rec["status"] = "done"
    return rec


def _chain_tip() -> Optional[dict]:
    """Last job to append continue onto: newest queued/running, else newest done."""
    active = [j for j in _jobs if j.get("status") in ("queued", "running")]
    if active:
        active.sort(key=lambda j: float(j.get("created_at") or 0))
        return active[-1]
    done = [j for j in _jobs if j.get("status") == "done"]
    if done:
        done.sort(key=lambda j: float(j.get("created_at") or 0))
        return done[-1]
    gal = [g for g in _gallery if g.get("id")]
    if gal:
        gal.sort(key=lambda j: float(j.get("done_at") or j.get("created_at") or 0))
        return _clip_record(gal[-1].get("id"))
    return None


def _lookup_face_lock(start_job_id: Optional[str] = None) -> tuple[Optional[list], Optional[str]]:
    """Walk continue parents (or tip) for stored face ref images."""
    seen: set[str] = set()
    cur = start_job_id
    if not cur:
        tip = _chain_tip()
        cur = tip["id"] if tip else None
    while cur and cur not in seen:
        seen.add(cur)
        j = next((x for x in _jobs if x.get("id") == cur), None)
        if not j:
            break
        if (j.get("ref_role") == "face" or j.get("mode") in ("face", "face_continue")) and j.get(
            "ref_images"
        ):
            refs = [str(x) for x in (j.get("ref_images") or []) if x]
            if refs:
                return refs, j.get("ref_image_size") or "max"
        cur = j.get("continue_from")
    return None, None


def _pick_next_job() -> Optional[dict]:
    """FIFO queue: first runnable job; if head waits on parent, don't jump ahead."""
    dirty = False
    # Prefer reattach to a live Comfy prompt before starting anything new
    for j in _jobs:
        if j.get("status") == "queued" and j.get("_reattach") and j.get("prompt_id"):
            return j
    for j in _jobs:
        if j.get("status") != "queued":
            continue
        parent_id = j.get("continue_from")
        if not parent_id:
            return j
        parent = _clip_record(parent_id)
        if not parent:
            j["status"] = "error"
            j["error"] = "önceki klip bulunamadı — continue iptal"
            j["progress_label"] = "hata"
            dirty = True
            continue
        if parent.get("status") == "done":
            return j
        if parent.get("status") in ("error", "cancelled"):
            j["status"] = "error"
            j["error"] = "önceki klip başarısız — continue iptal"
            j["progress_label"] = "hata"
            dirty = True
            continue
        # Head of queue waits on parent — keep order, don't start later jobs
        if dirty:
            _save_jobs()
        return None
    if dirty:
        _save_jobs()
    return None


async def _queue_loop():
    global _running
    slog.info("queue loop aktif")
    while True:
        try:
            job = None
            async with _lock:
                job = _pick_next_job()
            if not job:
                await asyncio.sleep(0.4)
                continue

            _running = True
            slog.info_job(
                job,
                "queue → run",
                continue_from=(job.get("continue_from") or "")[:8] or "-",
            )
            try:
                await _run_job(job)
                slog.info_job(job, "queue ← finished")
            except asyncio.CancelledError:
                # Never let this kill the while-loop — continue chain depends on it
                slog.warn_job(job, "queue ← cancelled-signal")
                if job.get("status") == "running":
                    job["status"] = "queued"
                    job["progress_label"] = "kesildi — yeniden sırada"
                    _save_jobs()
            except Exception as e:
                if job.get("status") not in ("cancelled", "done"):
                    job["status"] = "error"
                    err = str(e).strip() or repr(e)
                    job["error"] = err[-800:]
                    job["progress_label"] = "hata"
                    _save_jobs()
                slog.exception("queue ← error", e, job=job.get("id", "")[:8])
            finally:
                _running = False
            await _free_comfy_if_idle(reason="queue idle after clip")
            # Tight turnaround so continue #2 starts immediately after #1
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            _running = False
            slog.warn("queue loop iptal (shutdown)")
            raise
        except Exception as e:
            _running = False
            slog.exception("queue loop hata", e)
            await asyncio.sleep(2)


@app.websocket("/ws/system")
async def ws_system(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await system_stats()
            await ws.send_json(data)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return


@app.get("/")
async def index():
    return FileResponse(
        STATIC / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


if __name__ == "__main__":
    import uvicorn

    print(f"http://{HOST}:{PORT}", flush=True)
    print(f"H3 Studio http://{HOST}:{PORT}", flush=True)
    uvicorn.run(app, host=HOST, port=PORT)
