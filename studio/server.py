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
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
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
    detect_vfi_model,
    enhance_ref_prompt,
    enhance_video_ref_prompt,
    MULTISHOT_MAX_SHOTS,
)
from lib import h3_models
from lib.loras import (
    LORAS_DIR,
    apply_trigger,
    dest_for,
    file_ready,
    filename_from_url,
    find_spec,
    is_h3_lora_name,
    is_still_lora,
    public_list,
    spec_ready,
    still_catalog_spec,
)
from lib.director import (
    normalize_style,
    style_craft_line,
    apply_audio_policy,
    apply_directives_to_outline,
    apply_shot_patches,
    build_scene_placeholder_shot,
    camera_for_outline_index,
    diversify_outline_cameras,
    ensure_dialogue_in_h3_prompt,
    ensure_camera_in_h3_prompt,
    ensure_shot_count_sync,
    extract_json_object,
    fallback_director_reply,
    format_brief_board,
    format_cinema_board,
    infer_duration_and_shots,
    is_thin_template_prompt,
    merge_session_directives,
    normalize_shot_outline,
    opening_message,
    outline_generation_user_prompt,
    PLAN_MODE_ADDENDUM,
    CINEMA_STUDIO_ADDENDUM,
    ready_shots_reply,
    score_h3_prompt,
    single_shot_user_prompt,
    skeleton_brief_from_text,
    system_prompt,
    ui_lang_addendum,
    normalize_ui_lang,
    validate_brief,
    _clean_shot,
    force_continue_chain,
    expected_shot_count,
    MIN_H3_PROMPT_CHARS,
)
from lib.frames import duration_to_length, extract_audio_tail, extract_last_frame, resize_image, strip_audio
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
from lib import donors as donor_roll

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CLIPS = DATA / "clips"
FRAMES = DATA / "frames"
GALLERY = DATA / "gallery"
REFS = DATA / "refs"
REF_VIDEOS = DATA / "ref_videos"
REF_AUDIOS = DATA / "ref_audio"
MUSIC = DATA / "music"
CINEMA_FINALS = DATA / "cinema_finals"
COMFY_ROOT = ROOT.parent / "app"
COMFY_OUTPUT = COMFY_ROOT / "output"
COMFY_INPUT = COMFY_ROOT / "input"
ALLOWED_DURATIONS = (4, 5, 6, 8, 10, 15)
LOGS = ROOT / "logs"
JOBS_FILE = DATA / "jobs.json"
GALLERY_FILE = DATA / "gallery.json"
REFS_META_FILE = DATA / "refs_meta.json"
SESSIONS_FILE = DATA / "director_sessions.json"
LLM_SETTINGS_FILE = DATA / "llm_settings.json"
NOTIFY_SETTINGS_FILE = DATA / "notify_settings.json"
PRODUCTION_FILE = DATA / "production.json"
CINEMA_FILE = DATA / "cinema.json"
STATIC = ROOT / "static"
# Image Studio deliberately keeps its own ComfyUI process.  This bridge only
# exchanges finished stills with it; the two backends must never render at once
# on the same GPU.
IMAGE_STUDIO_URL = os.getenv("H3_IMAGE_STUDIO_URL", "http://127.0.0.1:8790").rstrip("/")


def _slug_clip(text: str, *, max_len: int = 36) -> str:
    """ASCII-ish slug from prompt / title for download filenames."""
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s\-]+", "", t, flags=re.UNICODE)
    t = re.sub(r"[\s_]+", "-", t).strip("-")
    if not t:
        return "clip"
    return t[:max_len].rstrip("-") or "clip"


def video_download_name(meta: Optional[dict] = None, *, item_id: str = "") -> str:
    """Unique download filename — never generic 'video.mp4'."""
    m = meta if isinstance(meta, dict) else {}
    jid = str(m.get("id") or item_id or "").strip() or uuid.uuid4().hex[:8]
    short = jid.replace("-", "")[:8]
    prompt = str(m.get("prompt") or m.get("title") or m.get("logline") or "").strip()
    # Prefer first meaningful line / outline title vibe
    first = ""
    for line in prompt.splitlines():
        line = line.strip()
        if len(line) >= 8 and not line.lower().startswith("continue directly"):
            first = line
            break
    if not first:
        first = prompt[:80]
    slug = _slug_clip(first)
    bi = m.get("batch_index")
    shot = ""
    try:
        if bi is not None and int(bi) > 0:
            shot = f"_s{int(bi):02d}"
    except (TypeError, ValueError):
        shot = ""
    purpose = str(m.get("purpose") or "").strip().lower().replace(" ", "-")
    pur = f"_{purpose}" if purpose and purpose not in ("short_film", "auto", "") else ""
    return f"h3{pur}_{slug}{shot}_{short}.mp4"


def _video_file_response(
    path: Path,
    *,
    meta: Optional[dict] = None,
    item_id: str = "",
    download: bool = False,
) -> FileResponse:
    name = video_download_name(meta, item_id=item_id or (meta or {}).get("id") or "")
    if download:
        return FileResponse(
            path,
            media_type="video/mp4",
            filename=name,
            content_disposition_type="attachment",
        )
    # Inline for <video src> — still expose a real filename for Save As
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=name,
        content_disposition_type="inline",
    )


def _prompt_optimize_instruction(enabled: bool) -> str:
    """Extra system guidance when the user opts into LLM prompt polishing (not a LoRA)."""
    if not enabled:
        return ""
    return (
        "\n\nPROMPT OPTIMIZE: Edit the draft into H3 Studio author fields, then the "
        "official three-block H3 prompt: integrated_multimodal_description / "
        "overall_soundscape / non_diegetic_music. Keep names, wardrobe, location, "
        "camera, <d>[Lang]…</d> dialogue, and silent/audio intent. No commentary."
    )


def _seed_scene_structured(raw: str) -> dict[str, str]:
    parsed = cinema.parse_h3_prompt(raw)
    if cinema._has_author_fields(parsed):
        return parsed
    seeded = cinema._clean_structured({})
    seeded["action"] = (raw or "").strip()
    return seeded


def _structured_from_rewrite_payload(raw: Any, seed: dict[str, str]) -> dict[str, str]:
    src = raw if isinstance(raw, dict) else {}
    if isinstance(src.get("structured"), dict):
        src = src["structured"]
    merged = cinema._clean_structured(seed)
    for key in cinema._STRUCTURED_KEYS:
        val = src.get(key)
        if val is None:
            continue
        text = str(val).strip()
        if text:
            merged[key] = text
    return merged


async def _rewrite_scene_text(
    raw: str,
    *,
    enabled: bool,
    context: str = "",
    require: bool = False,
) -> str:
    """Polish a Sahne draft into H3 Studio fields, then compose the official 3-block prompt."""
    text = (raw or "").strip()
    if not text or not enabled:
        return text
    try:
        model = await llm.resolve_model(None)
    except Exception as e:
        if require:
            raise HTTPException(503, "Yönetmen LLM hazır değil — Ayarlar’dan model/key aç") from e
        return text
    seed = _seed_scene_structured(text)
    sys = (
        "You are the MiniMax H3 prompt editor for H3 Studio. "
        "Edit the user's draft into our author fields. Do not invent a new story. "
        "Keep character and location names exactly. Visual fields in English. "
        "Dialogue may stay in the spoken language; set dialogue_lang (auto|tr|en|ar|…). "
        "Return ONLY JSON with string fields: "
        "title, location, character, action, dialogue, dialogue_lang, camera, "
        "visual_style, audio, music, important. "
        "action = this clip only, present tense, visible. "
        "camera = shot size / move. "
        "visual_style = Live-action, cinematic unless the draft asks otherwise. "
        "audio = diegetic. music = N/A unless the user asked for score. "
        "important = must-lock constraints only. "
        "No markdown, no extra keys, no explanation."
        + _prompt_optimize_instruction(True)
    )
    if context.strip():
        sys += "\n\nCONTEXT:\n" + context.strip()[:2000]
    user = (
        "DRAFT:\n"
        + text[:8000]
        + "\n\nCURRENT FIELDS:\n"
        + json.dumps(seed, ensure_ascii=False)
    )
    try:
        out = await llm.chat(
            model,
            [
                {"role": "system", "content": sys},
                {"role": "user", "content": user},
            ],
            temperature=0.35,
            think=False,
            format_json=True,
            retries=2,
            num_predict=2048,
        )
        payload = extract_json_object(out) or {}
        merged = _structured_from_rewrite_payload(payload, seed)
        if not cinema._has_author_fields(merged) and cinema._looks_like_h3_prompt(out):
            merged = cinema.parse_h3_prompt(out)
        composed = cinema.compose_h3_prompt(merged)
        if composed:
            return composed
        if cinema._looks_like_h3_prompt(out or ""):
            recovered = cinema.compose_h3_prompt(cinema.parse_h3_prompt(out))
            if recovered:
                return recovered
        if require:
            raise HTTPException(502, "Rewrite H3 yapısına oturmadı — tekrar dene")
        return text
    except HTTPException:
        raise
    except Exception as e:
        slog.warn("prompt rewrite skipped", err=e)
        if require:
            raise HTTPException(502, f"Rewrite hata: {e}") from e
        return text

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


def _release_single_instance() -> None:
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


def _acquire_single_instance() -> None:
    """Bind a lock socket so only one queue loop can own jobs.json."""
    global _lock_fh, _lock_sock
    import socket

    DATA.mkdir(parents=True, exist_ok=True)
    # Dedicated lock port derived from Studio port (does not conflict with uvicorn)
    lock_port = 20000 + (int(PORT) % 20000)

    atexit.register(_release_single_instance)

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

# Official Comfy MiniMax H3 Size Settings Reference (ResolutionSelector, multiple=32).
# Six practical MP tiers; legacy 720/1080 alias to 736/1088.
# Sizes from: total=mp*1024², scale=sqrt(total/(wr*hr)), round to ×32.
H3_QUALITY_SIZES = {
    "16:9": {
        "352": (608, 352),
        "480": (864, 480),
        "608": (1056, 608),
        "736": (1280, 736),
        "768": (1344, 768),
        "1088": (1920, 1088),
    },
    "9:16": {
        "352": (352, 608),
        "480": (480, 864),
        "608": (608, 1056),
        "736": (736, 1280),
        "768": (768, 1344),
        "1088": (1088, 1920),
    },
    "1:1": {
        "352": (448, 448),
        "480": (640, 640),
        "608": (800, 800),
        "736": (960, 960),
        "768": (1024, 1024),
        "1088": (1440, 1440),
    },
    "21:9": {
        "352": (704, 288),
        "480": (992, 416),
        "608": (1216, 512),
        "736": (1472, 640),
        "768": (1536, 672),
        "1088": (2208, 960),
    },
    "4:3": {
        "352": (544, 384),
        "480": (736, 576),
        "608": (928, 672),
        "736": (1120, 832),
        "768": (1184, 864),
        "1088": (1664, 1248),
    },
}

QUALITY_ALIASES = {"720": "736", "1080": "1088"}
QUALITY_KEYS = ("352", "480", "608", "736", "768", "1088")

# Canonical key → short-edge label (16:9); used for fallback scaling
QUALITY_SHORT_EDGE = {
    "352": 352,
    "480": 480,
    "608": 608,
    "736": 736,
    "768": 768,
    "1088": 1088,
    # legacy
    "720": 736,
    "1080": 1088,
}


def normalize_quality(quality: str) -> str:
    q = str(quality or "736").strip()
    q = QUALITY_ALIASES.get(q, q)
    return q if q in QUALITY_KEYS else "736"


def snap32(v: float) -> int:
    """Nearest multiple of 32 (half-up). 720 → 736, matching H3 table."""
    return max(32, int(math.floor(float(v) / 32.0 + 0.5) * 32))


def snap_h3_size(width: int, height: int) -> tuple[int, int]:
    return snap32(width), snap32(height)


def resolve_size(aspect: str, quality: str = "736") -> tuple[int, int]:
    q = normalize_quality(quality)
    preset = H3_QUALITY_SIZES.get(aspect, {}).get(q)
    if preset:
        return preset
    # Legacy alias keys may still sit in the table under canonical form only
    preset = H3_QUALITY_SIZES.get(aspect, {}).get(QUALITY_ALIASES.get(str(quality), q))
    if preset:
        return preset
    base_w, base_h = ASPECT_PRESETS.get(aspect, (1920, 1080))
    target = QUALITY_SHORT_EDGE.get(q, 736)
    short = min(base_w, base_h) or 1
    scale = target / short
    return snap32(base_w * scale), snap32(base_h * scale)


def _normalize_post_pass(raw: Any) -> str:
    v = str(raw or "").strip().lower()
    return v if v in ("upscale", "vfi") else ""


def _lora_fields(body: Any) -> dict[str, Any]:
    raw_name = (getattr(body, "lora_name", None) or "").strip()
    primary_name = raw_name.split("|", 1)[0]
    spec = find_spec(
        lora_id=getattr(body, "lora_id", None) or "",
        file=primary_name,
    )
    if spec and is_still_lora(spec) and not getattr(body, "sheet_job", False):
        return {"lora_id": "", "lora_name": "", "lora_strength": None}
    name = raw_name
    if spec and spec.get("file") and "|" not in name:
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
        if (mode or "").lower() in ("ref", "face", "v2v", "face_continue", "audio_continue")
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
        if is_still_lora(spec) and not getattr(body, "sheet_job", False):
            return False
        graphs = spec.get("graphs") or ["fl2va", "ref2va"]
        if getattr(body, "sheet_job", False) and is_still_lora(spec):
            return True
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
    mode = (job.get("mode") or "t2v").lower()
    graph = "ref2va" if mode in ("ref", "face", "v2v", "face_continue", "audio_continue") else "fl2va"
    usable = []
    for item in name.split("|")[:3]:
        spec = find_spec(file=item)
        graphs = (spec or {}).get("graphs") or ["fl2va", "ref2va"]
        if job.get("sheet_job") and spec and is_still_lora(spec):
            usable.append(item)
        elif graph in graphs:
            usable.append(item)
        else:
            slog.info("lora skipped", lora=item, mode=mode, graph=graph)
    if not usable:
        return None, 1.0
    st = job.get("lora_strength")
    if st is None:
        st = (spec or {}).get("strength") or 0.8
    return "|".join(usable), float(st)


def _voice_refs_from_hits(hits: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for h in hits or []:
        if h.get("kind") != "character":
            continue
        va = str(h.get("voice_audio") or "").strip()
        if not va or va in seen:
            continue
        seen.add(va)
        out.append(va)
        if len(out) >= 3:
            break
    return out


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


def _load_ref_meta() -> dict[str, dict]:
    try:
        raw = json.loads(REFS_META_FILE.read_text(encoding="utf-8")) if REFS_META_FILE.exists() else {}
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_ref_meta(meta: dict[str, dict]) -> None:
    REFS_META_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = REFS_META_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(REFS_META_FILE)


def _set_ref_prompt(filename: str, prompt: str, source: str = "") -> None:
    name = Path(filename).name
    if not name or not prompt.strip():
        return
    meta = _load_ref_meta()
    meta[name] = {"prompt": prompt.strip(), "source": source, "saved_at": time.time()}
    _save_ref_meta(meta)


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
        # A timed-out Studio watcher can still have a completed (or live)
        # Comfy output. Preserve every job-linked output until the user
        # explicitly deletes that job; cleanup must never erase recovery data.
        if jid:
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


def _find_comfy_video_for_job(job_id: str) -> Optional[Path]:
    """Find a retained H3 output even after ComfyUI history was cleared."""
    prefix = str(job_id or "")[:8]
    if not prefix:
        return None
    matches: list[Path] = []
    for folder_name in ("H3_Studio", "H3_Studio_Ref"):
        folder = COMFY_OUTPUT / "video" / folder_name
        if folder.is_dir():
            matches.extend(p for p in folder.glob(f"{prefix}*.mp4") if p.is_file())
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


async def _recover_saved_comfy_video(job: dict, source: Path) -> None:
    """Adopt an existing Comfy output into the job and permanent gallery."""
    dest = CLIPS / f"{job['id']}.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)
    subfolder = "video/H3_Studio_Ref" if "H3_Studio_Ref" in source.parts else "video/H3_Studio"
    job["output"] = {
        "filename": source.name,
        "subfolder": subfolder,
        "type": "output",
        "url": f"/api/clips/{job['id']}/video",
    }
    job["local_path"] = str(dest)
    job["download_name"] = video_download_name(job, item_id=job["id"])
    job["status"] = "done"
    job["progress"] = 100
    job["progress_label"] = "bitti (Comfy çıktısı kurtarıldı)"
    job["error"] = None
    job["done_at"] = job.get("done_at") or time.time()
    job.pop("_reattach", None)
    try:
        await _prepare_last_frame(job, upload=True)
    except Exception as e:
        job["last_frame_error"] = str(e)[-300:]
        slog.warn_job(job, "recovered video last frame failed", err=e)
    _archive_job_to_gallery(job)
    slog.info_job(job, "saved Comfy output recovered", file=source.name)

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
        "download_name": video_download_name(job, item_id=jid),
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


def _session_removed_names(sess: Optional[dict]) -> set[str]:
    if not isinstance(sess, dict):
        return set()
    out: set[str] = set()
    for key in ("removed_characters", "removed_locations"):
        for raw in sess.get(key) or []:
            n = str(raw or "").strip().lower()
            if n:
                out.add(n)
    return out


def _scrub_brief_removed(brief: Optional[dict], sess: Optional[dict]) -> Optional[dict]:
    """Drop characters/locations the user removed so LLM cannot resurrect them via merge."""
    if not isinstance(brief, dict):
        return brief
    removed = _session_removed_names(sess)
    if not removed:
        return brief
    out = dict(brief)

    def _keep(item: Any) -> bool:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("role") or "").strip().lower()
        else:
            name = str(item or "").strip().lower()
        return bool(name) and name not in removed

    if isinstance(out.get("characters"), list):
        out["characters"] = [c for c in out["characters"] if _keep(c)]
    if isinstance(out.get("locations"), list):
        out["locations"] = [c for c in out["locations"] if _keep(c)]
    return out


def _remember_removed_asset(kind: str, name: str, asset_id: str = "") -> None:
    """Mark name as removed on all director sessions and strip it from briefs."""
    label = str(name or "").strip()
    if not label and not asset_id:
        return
    key = "removed_characters" if kind == "character" else "removed_locations"
    low = label.lower()
    changed = False
    for sess in _sessions.values():
        if not isinstance(sess, dict):
            continue
        bucket = list(sess.get(key) or [])
        if low and low not in {str(x).strip().lower() for x in bucket}:
            bucket.append(label)
            sess[key] = bucket
            changed = True
        if isinstance(sess.get("brief"), dict):
            before = json.dumps(sess["brief"], sort_keys=True, ensure_ascii=False)
            sess["brief"] = _scrub_brief_removed(sess["brief"], sess)
            after = json.dumps(sess["brief"] or {}, sort_keys=True, ensure_ascii=False)
            if before != after:
                changed = True
    if changed:
        _save_sessions()


class GenerateBody(BaseModel):
    prompt: str = Field(..., min_length=1)
    duration: int = Field(5, description="4 | 5 | 6 | 8 | 10 | 15")
    aspect: str = "16:9"
    quality: str = Field("736", description="352 | 480 | 608 | 736 | 768 | 1088 (aliases: 720->736, 1080->1088)")
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
    audio_continuity: bool = False
    # match = scale to gen area; max = best identity (face default)
    ref_image_size: Optional[str] = None
    # music video: strip generated audio after download
    silent_audio: bool = False
    purpose: Optional[str] = None
    prompt_rewriter_enabled: bool = False
    lane: Optional[str] = None
    lora_id: Optional[str] = None
    lora_name: Optional[str] = None
    lora_strength: Optional[float] = None
    sage_attention: Optional[str] = "auto"
    post_pass: Optional[str] = None
    sheet_job: bool = False

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


class ImageStudioReferenceBody(BaseModel):
    """A small, intentionally limited surface for the optional local bridge."""

    prompt: str = Field(..., min_length=1, max_length=6000)
    aspect: str = "16:9"
    steps: int = Field(30, ge=1, le=80)


class MotionTransferChainBody(GenerateBody):
    """Short, GPU-safe motion-transfer chain (first clip + continuations)."""

    segments: int = Field(3, ge=2, le=6)


class BatchBody(BaseModel):
    prompts: list[str]
    duration: int = 5
    aspect: str = "16:9"
    quality: str = "736"
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
    lane: Optional[str] = None
    prompt_rewriter_enabled: bool = False
    post_pass: Optional[str] = None


class CinemaProduceBody(BaseModel):
    shots: Optional[list[Any]] = None
    script: Optional[str] = None
    shot_modes: Optional[list[str]] = None
    setup: Optional[dict[str, Any]] = None
    duration: int = 5
    aspect: str = "16:9"
    quality: str = "736"
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
    append_to_chain: bool = False
    audio: Optional[dict[str, Any]] = None
    seamless: bool = False
    # First queue missing character/creature/location sheets; scenes start after they finish
    prepare_sheets: bool = True
    # If true, queue sheets even when the card already has a still
    force_sheets: bool = False
    post_pass: Optional[str] = None

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
    quality: str = "736"
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
    ui_lang: Optional[str] = None
    plan_mode: Optional[bool] = None
    prompt_rewriter_enabled: bool = False


class DirectorCommitBody(BaseModel):
    session_id: str
    queue: bool = False
    link_continue: Optional[bool] = None
    append_to_chain: bool = True
    quality: str = "736"
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
    post_pass: Optional[str] = None
    prompt_rewriter_enabled: bool = False
    sage_attention: Optional[str] = "auto"


class DirectorRewriteShotsBody(BaseModel):
    session_id: str
    force: bool = False


class PromptRewriteBody(BaseModel):
    prompt: str = Field(..., min_length=1)
    context: Optional[str] = None
    prompt_rewriter_enabled: bool = True


def _looks_like_finished_plan(text: str) -> bool:
    """Heuristic: model wrote a plan / truncated ready JSON but chat didn't mark ready."""
    if not text:
        return False
    t = text.lower()
    keys = (
        "expectedshotcount",
        '"ready": true',
        '"ready":true',
        '"phase": "outline"',
        '"phase":"outline"',
        "shotoutline",
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
            # Carry phase / outline flags from outer envelope
            if parsed.get("phase") and not brief_src.get("phase"):
                brief_src["phase"] = parsed.get("phase")
        elif isinstance(parsed.get("shots"), list) or parsed.get("expectedShotCount"):
            brief_src = parsed
        elif isinstance(parsed.get("shotOutline"), list):
            brief_src = parsed
    if not isinstance(brief_src, dict) or (
        not (brief_src.get("shots") or [])
        and not brief_src.get("expectedShotCount")
        and not brief_src.get("characters")
        and not (brief_src.get("shotOutline") or [])
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
    brief = merge_session_directives(brief, sess)
    need = brief.get("expectedShotCount") or 0
    have = len(brief.get("shots") or [])
    outline = normalize_shot_outline(brief)
    # FAZ A only (outline, no full shots yet) OR incomplete shots → FAZ B fill
    if expand and need and (have < need or (outline and have == 0)):
        brief = await _expand_brief_shots(brief, model)
    elif expand and need and have >= need:
        # Quality-upgrade thin shots still using outline when present
        thin = sum(
            1
            for s in (brief.get("shots") or [])
            if isinstance(s, dict)
            and len(str(s.get("h3Prompt") or "")) < MIN_H3_PROMPT_CHARS
        )
        if thin:
            brief = await _expand_brief_shots(brief, model)
        else:
            brief = ensure_shot_count_sync(brief)
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
    # Explicit shot count from user ("5 shotlık") beats ceil(total/clip).
    if need_inf:
        brief["expectedShotCount"] = int(need_inf)
        if total_inf:
            brief["totalDurationSec"] = max(int(total_inf), int(need_inf) * clip)
        else:
            brief["totalDurationSec"] = max(
                int(brief.get("totalDurationSec") or 0),
                int(need_inf) * clip,
            )
    elif total_inf:
        brief["totalDurationSec"] = int(total_inf)
        brief["expectedShotCount"] = expected_shot_count(int(total_inf), clip)
    elif brief.get("totalDurationSec"):
        brief["expectedShotCount"] = expected_shot_count(
            int(brief["totalDurationSec"]), clip
        )
    return validate_brief(brief)


def _emit_director_status(text: str) -> None:
    progress = _director_progress.get()
    if not progress:
        return
    try:
        progress({"type": "status", "text": text})
    except Exception:
        pass


async def _generate_shot_outline(brief: dict, model: str) -> dict:
    """FAZ A — ask LLM for title/beat list only (no h3Prompts)."""
    brief = validate_brief(brief)
    need = int(brief.get("expectedShotCount") or 0)
    if not need:
        return brief
    existing = normalize_shot_outline(brief)
    if len(existing) >= need:
        brief["shotOutline"] = existing[:need]
        return brief
    _emit_director_status(f"FAZ A — {need} shot başlığı yazılıyor…")
    messages = [
        {
            "role": "system",
            "content": system_prompt()
            + "\n\nFAZ A only: return shotOutline JSON. No h3Prompt. No chat.",
        },
        {"role": "user", "content": outline_generation_user_prompt(brief)},
    ]
    try:
        content = await asyncio.wait_for(
            llm.chat(
                model,
                messages,
                temperature=0.4,
                format_json=True,
                think=False,
                retries=1,
                num_predict=3072,
                on_progress=_director_progress.get(),
            ),
            timeout=60.0,
        )
    except Exception as e:
        print(f"outline generate fail: {e}", flush=True)
        brief["shotOutline"] = normalize_shot_outline(brief, pad=True)
        return brief
    parsed = extract_json_object(content) or {}
    src = parsed.get("brief") if isinstance(parsed.get("brief"), dict) else parsed
    if isinstance(src, dict):
        for key in ("logline", "characters", "locations", "purpose", "visualStyle"):
            if src.get(key) and not brief.get(key):
                brief[key] = src[key]
        if isinstance(src.get("shotOutline"), list) and src["shotOutline"]:
            brief["shotOutline"] = src["shotOutline"]
    brief = validate_brief(brief)
    outline = normalize_shot_outline(brief, pad=True)
    brief["shotOutline"] = outline
    return brief


async def _write_one_shot_from_outline(
    brief: dict,
    model: str,
    *,
    index: int,
    need: int,
    outline_row: dict,
    prev_shot: Optional[dict],
) -> Optional[dict]:
    """FAZ B — one GOLD STANDARD h3Prompt with quality retries (no thin templates)."""
    dur = int(brief.get("clipDurationSec") or 5)
    silent = bool(brief.get("silentAudio"))
    progress = _director_progress.get()
    feedback = ""
    # 2 attempts max — with Gemini thinking off this is enough; 3× hung streams = UI freeze
    for attempt in range(2):
        user = single_shot_user_prompt(
            brief,
            index=index,
            need=need,
            outline_row=outline_row,
            prev_shot=prev_shot,
        )
        if feedback:
            user += (
                f"\n\nPREVIOUS DRAFT FAILED QA: {feedback}. "
                "Rewrite as a FULL English cinematic SCENE screenplay "
                f"(≥{MIN_H3_PROMPT_CHARS} chars, 8+ short paragraphs). "
                "NO template lines like 'Across 0–5s', 'picture mood only', "
                "'body systems activate', or Turkish outside <d> tags. "
                "Describe concrete scales, scales/claws/wings/eyes, location, light, "
                "micro-actions and camera — not wardrobe boilerplate for creatures."
            )
        messages = [
            {
                "role": "system",
                "content": (
                    system_prompt()
                    + "\n\nFAZ B: write exactly ONE shot JSON. No chat. "
                    f"h3Prompt ≥{MIN_H3_PROMPT_CHARS} chars, English SCENE only. "
                    "Never use filler templates."
                ),
            },
            {"role": "user", "content": user},
        ]
        try:
            content = await asyncio.wait_for(
                llm.chat(
                    model,
                    messages,
                    temperature=0.55 if attempt == 0 else 0.35,
                    format_json=True,
                    think=False,
                    retries=1,
                    num_predict=4096,
                    on_progress=progress,
                ),
                timeout=70.0,
            )
        except asyncio.TimeoutError:
            print(f"shot {index + 1} write timeout attempt={attempt + 1}", flush=True)
            feedback = "llm_timeout"
            continue
        except Exception as e:
            print(f"shot {index + 1} write fail: {e}", flush=True)
            break
        parsed = extract_json_object(content) or {}
        raw_shot = None
        if isinstance(parsed.get("shot"), dict):
            raw_shot = parsed["shot"]
        elif isinstance(parsed.get("shots"), list) and parsed["shots"]:
            raw_shot = parsed["shots"][0]
        elif isinstance(parsed, dict) and parsed.get("h3Prompt"):
            raw_shot = parsed
        if not isinstance(raw_shot, dict):
            feedback = "missing shot object"
            continue
        raw_shot.setdefault("action", outline_row.get("beat") or outline_row.get("title"))
        raw_shot.setdefault("camera", outline_row.get("camera"))
        # Preserve an explicit LLM link. Missing links mean a new, independent shot.
        if index == 0 or not raw_shot.get("linkToPrev"):
            raw_shot["linkToPrev"] = "standalone"
        raw_shot.pop("_placeholder", None)
        raw_shot.pop("_thin_template", None)
        cleaned = _clean_shot(raw_shot, index, dur, brief=brief, total_shots=need)
        if not cleaned:
            feedback = "empty shot"
            continue
        # Re-apply without thin rebuild overwriting a good LLM body
        body = str(cleaned.get("h3Prompt") or "")
        if is_thin_template_prompt(body) or len(body) < MIN_H3_PROMPT_CHARS:
            # Keep raw LLM body if _clean_shot/build_rich degraded it
            raw_body = str(raw_shot.get("h3Prompt") or "")
            if len(raw_body) >= len(body):
                cleaned["h3Prompt"] = apply_audio_policy(
                    ensure_dialogue_in_h3_prompt(
                        raw_body,
                        cleaned.get("dialogue") or [],
                        silent=silent,
                    ),
                    brief,
                )
        score = score_h3_prompt(
            cleaned.get("h3Prompt") or "",
            index=index,
            silent=silent,
            shot=cleaned,
        )
        if score["ok"]:
            cleaned["_placeholder"] = False
            cleaned["_thin_template"] = False
            cam = str(cleaned.get("camera") or outline_row.get("camera") or "").strip()
            if cam:
                cleaned["h3Prompt"] = ensure_camera_in_h3_prompt(
                    cleaned.get("h3Prompt") or "",
                    cam,
                    force=True,
                )
            return cleaned
        feedback = ",".join(score.get("reasons") or ["weak"])
        print(
            f"shot {index + 1} QA fail attempt={attempt + 1}: {feedback}",
            flush=True,
        )
    return None  # do NOT return thin best — caller must retry or skip


async def _expand_brief_shots(brief: dict, model: str) -> dict:
    """FAZ A outline (if needed) → FAZ B write each shot one-by-one → pad leftovers."""
    brief = validate_brief(brief)
    need = brief.get("expectedShotCount")
    shots = list(brief.get("shots") or [])
    if not need:
        return ensure_shot_count_sync(brief)

    # Keep strong existing shots; rewrite only missing/thin slots
    strong: list[Optional[dict]] = [None] * int(need)
    for i, s in enumerate(shots[: int(need)]):
        if not isinstance(s, dict):
            continue
        body = str(s.get("h3Prompt") or "")
        sc = score_h3_prompt(
            body,
            index=i,
            silent=bool(brief.get("silentAudio")),
            shot=s,
        )
        if sc["ok"]:
            strong[i] = s

    if all(strong) and len(strong) >= int(need):
        brief["shots"] = [s for s in strong if s]
        brief["shotsIncomplete"] = False
        return brief

    outline = normalize_shot_outline(brief)
    directives = brief.get("directorDirectives")
    if outline:
        outline = apply_directives_to_outline(outline, directives, int(need))
        outline = diversify_outline_cameras(outline, directives)
        brief["shotOutline"] = outline
    if len(outline) < int(need):
        brief = await _generate_shot_outline(brief, model)
        outline = normalize_shot_outline(brief, pad=True)
    else:
        brief["shotOutline"] = outline
        outline = normalize_shot_outline(brief, pad=True)

    final: list[dict] = []
    failed = 0
    # Hard wall so chat never hangs forever (12 shots × retries was unbounded)
    deadline = time.monotonic() + max(90.0, min(360.0, float(need) * 25.0))
    for i in range(int(need)):
        if strong[i] is not None:
            final.append(strong[i])  # type: ignore[arg-type]
            continue
        if time.monotonic() > deadline:
            print(
                f"FAZ B deadline — filling remaining shots {i + 1}–{need} as placeholders",
                flush=True,
            )
            _emit_director_status(
                f"FAZ B süre doldu — kalan shot’lar placeholder ({i + 1}/{need})"
            )
            for j in range(i, int(need)):
                if strong[j] is not None:
                    final.append(strong[j])  # type: ignore[arg-type]
                else:
                    failed += 1
                    ph = build_scene_placeholder_shot(
                        index=j, total=int(need), brief=brief
                    )
                    ph["_placeholder"] = True
                    ph["_thin_template"] = True
                    final.append(ph)
            break
        row = outline[i] if i < len(outline) else {
            "index": i + 1,
            "title": f"Beat {i + 1}",
            "beat": brief.get("logline") or f"Shot {i + 1}",
            "camera": camera_for_outline_index(i, directives=directives),
        }
        _emit_director_status(
            f"FAZ B — shot {i + 1}/{need} SCENE yazılıyor… ({row.get('title') or ''})"
        )
        prev = final[-1] if final else None
        written = await _write_one_shot_from_outline(
            brief,
            model,
            index=i,
            need=int(need),
            outline_row=row,
            prev_shot=prev,
        )
        if written and score_h3_prompt(
            written.get("h3Prompt") or "",
            index=i,
            silent=bool(brief.get("silentAudio")),
            shot=written,
        )["ok"]:
            final.append(written)
        else:
            failed += 1
            # Last resort placeholder — marked thin so UI/cinema can reject
            ph = build_scene_placeholder_shot(index=i, total=int(need), brief=brief)
            ph["_placeholder"] = True
            ph["_thin_template"] = True
            final.append(ph)

    brief["shots"] = force_continue_chain(final[: int(need)], brief)
    brief["expectedShotCount"] = int(need)
    brief["shotOutline"] = outline[: int(need)]
    brief["shotsIncomplete"] = failed > 0
    brief["thinShotCount"] = failed
    # Do NOT run ensure_shot_count_sync here — it rebuilds thin templates over good SCENEs
    return validate_brief(brief)

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
        elif (
            pid
            and j.get("status") == "error"
            and str(j.get("error") or "").startswith("timeout")
        ):
            # An old watchdog can time out while Comfy keeps working. If the
            # result landed meanwhile, queue it once more only to download and
            # archive that existing output — never render it again.
            try:
                hist = await comfy.history(str(pid))
                entry = hist.get(str(pid)) or {}
                video_meta = comfy.extract_video_meta(entry.get("outputs") or {})
                if video_meta:
                    j["status"] = "queued"
                    j["progress_label"] = "Comfy çıktısı bulundu — galeriye alınıyor"
                    j["error"] = None
                    j["_reattach"] = True
                    slog.info_job(j, "startup recover completed timeout", prompt=str(pid)[:8])
            except Exception as e:
                slog.warn_job(j, "startup timeout recovery skipped", err=e)
            if j.get("status") == "error":
                # Comfy may clear its history after a restart. Its SaveVideo
                # file is still named with the Studio job id, so recover it
                # from disk instead of rendering the same clip again.
                saved = _find_comfy_video_for_job(str(j.get("id") or ""))
                if saved:
                    try:
                        await _recover_saved_comfy_video(j, saved)
                    except Exception as e:
                        slog.warn_job(j, "startup saved video recovery skipped", err=e)
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


@app.on_event("shutdown")
async def shutdown():
    global _queue_task, _queue_supervisor
    slog.info("studio shutdown", pid=os.getpid())
    for label, task in (("queue", _queue_task), ("supervisor", _queue_supervisor)):
        if task is None or task.done():
            continue
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            slog.warn("shutdown task", which=label, err=e)
    _release_single_instance()


@app.get("/api/donors")
async def get_donors():
    """Public thank-you roll. Empty names → UI hides the ticker."""
    return await donor_roll.list_donors()


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
        "vfi_model": detect_vfi_model(COMFY_ROOT) or "",
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
    jobs = []
    for j in reversed(_jobs[-200:]):
        row = dict(j)
        if row.get("status") == "done" and not row.get("download_name"):
            row["download_name"] = video_download_name(row, item_id=str(row.get("id") or ""))
        jobs.append(row)
    return {"jobs": jobs}


@app.get("/api/gallery")
async def list_gallery():
    """All finished videos ever produced (permanent archive, not session jobs)."""
    items = sorted(
        _gallery,
        key=lambda g: float(g.get("done_at") or g.get("created_at") or 0),
        reverse=True,
    )
    out = []
    for g in items:
        row = dict(g)
        if not row.get("download_name"):
            row["download_name"] = video_download_name(row, item_id=str(row.get("id") or ""))
        out.append(row)
    return {"items": out, "count": len(out)}


@app.get("/api/gallery/{item_id}/video")
async def gallery_video(item_id: str, dl: int = Query(0)):
    path = GALLERY / f"{item_id}.mp4"
    entry = next((g for g in _gallery if g.get("id") == item_id), None)
    if not path.exists():
        if entry and entry.get("local_path") and Path(entry["local_path"]).exists():
            path = Path(entry["local_path"])
        else:
            raise HTTPException(404, "galeri videosu yok")
    meta = entry or {"id": item_id}
    return _video_file_response(path, meta=meta, item_id=item_id, download=bool(dl))


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


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel one queued job, or stop the one job currently rendering."""
    async with _lock:
        job = next((j for j in _jobs if j["id"] == job_id), None)
        if not job:
            raise HTTPException(404, "job yok")
        status = job.get("status")
        if status not in ("queued", "running"):
            raise HTTPException(400, "yalnızca sıradaki veya üretilen iş durdurulabilir")
        # A queued job has not reached ComfyUI yet, so it can be cancelled alone.
        if status == "queued":
            job["status"] = "cancelled"
            job["error"] = "iptal"
            job["progress_label"] = "iptal"
            _save_jobs()
            slog.info_job(job, "queued job cancelled")
            return {"ok": True, "id": job_id, "status": "cancelled"}

    # Studio runs one active render at a time. Interrupting here leaves every
    # other queued job intact; the queue loop will continue with the next one.
    try:
        await comfy.interrupt()
    except Exception as e:
        raise HTTPException(500, str(e))
    async with _lock:
        job = next((j for j in _jobs if j["id"] == job_id), None)
        if not job or job.get("status") != "running":
            raise HTTPException(409, "iş artık üretimde değil")
        job["status"] = "cancelled"
        job["error"] = "iptal"
        job["progress_label"] = "iptal"
        _save_jobs()
    slog.info_job(job, "running job cancelled")
    return {"ok": True, "id": job_id, "status": "cancelled"}


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
        raise HTTPException(400, "quality must be 352, 480, 608, 736, 768, or 1088 (aliases: 720, 1080)")
    if not await comfy.healthy():
        raise HTTPException(503, "ComfyUI kapalı — Pinokio'dan Start ile Comfy'yi aç")

    lora_bits = _lora_fields(body)

    if body.prompt_rewriter_enabled:
        if not await llm.healthy():
            raise HTTPException(503, "Prompt düzenleme kapalı — Ayarlar’dan Yönetmen LLM aç")
        rewritten = await _rewrite_scene_text(
            body.prompt,
            enabled=True,
            context=f"mode={body.mode or 't2v'}",
            require=True,
        )
        if rewritten and rewritten.strip():
            body.prompt = rewritten.strip()

    mode = (body.mode or "").strip().lower()
    continue_from = body.continue_from_job_id
    first_frame = body.first_frame_name
    last_frame = body.last_frame_name
    ref_images = list(body.ref_images or [])
    ref_videos = list(body.ref_videos or [])
    ref_image_size = (body.ref_image_size or "").strip().lower() or None
    continue_aspect = None

    # Explicit T2V/I2V ignores accidental continue state from the UI. I2V uses
    # the same FL2VA graph, but requires a starting image by contract.
    if mode in ("t2v", "new", "yeni", "i2v", "image_to_video"):
        continue_from = None
        ref_images = []
        ref_videos = []
        if mode in ("i2v", "image_to_video") and not first_frame:
            raise HTTPException(400, "I2V için başlangıç görseli seç")
        mode = "t2v"
    elif mode in ("v2v", "video", "video_ref", "motion"):
        mode = "v2v"
        continue_from = None
        first_frame = None
        last_frame = None
        if not ref_videos:
            raise HTTPException(400, "Motion Transfer için en az 1 hareket referans videosu yükle")
        if len(ref_videos) > 3:
            raise HTTPException(400, "En fazla 3 referans video")
        if len(ref_images) > 9:
            raise HTTPException(400, "En fazla 9 referans görsel")
        # In V2V a supplied picture is the target look/identity, not a loose
        # style hint.  Keep its full reference resolution so motion video does
        # not overpower the requested character replacement.
        ref_image_size = "max" if ref_images else "match"
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
        # A continue is last-frame I2V.  Never carry a generic/style picture
        # into it: Ref2VA may otherwise literalize that picture as a poster,
        # background person, or picture-in-picture.  Only an explicitly tagged
        # identity reference is allowed to travel with a face-locked chain.
        keep_face = bool(ref_images) and (body.ref_role or "").strip().lower() == "face"
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
            # Continuations must use the source canvas.  Do this server-side too:
            # a stale browser or an API caller must not turn a portrait chain into
            # a landscape one.  Legacy records can be recovered from dimensions.
            saved_aspect = str(parent.get("aspect") or "").strip()
            if saved_aspect in ASPECT_PRESETS:
                continue_aspect = saved_aspect
            else:
                try:
                    parent_w = float(parent.get("width") or 0)
                    parent_h = float(parent.get("height") or 0)
                    if parent_w > 0 and parent_h > 0:
                        source_ratio = parent_w / parent_h
                        continue_aspect = min(
                            ASPECT_PRESETS,
                            key=lambda aspect: abs(
                                source_ratio
                                - ASPECT_PRESETS[aspect][0] / ASPECT_PRESETS[aspect][1]
                            ),
                        )
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
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
    elif mode == "continue" and bool(body.audio_continuity):
        # Ref2VA accepts an explicit <Audio 1> reference; plain FL2VA continue does not.
        mode = "audio_continue"

    await _free_llm_for_production()
    if continue_aspect:
        body.aspect = continue_aspect
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
    lora_applied = _lora_fields(lora_src)
    if mode == "face":
        prompt_txt = enhance_ref_prompt(
            prompt_txt, n_images=len(ref_images), role="face"
        )
    elif mode in ("ref", "v2v"):
        prompt_txt = enhance_ref_prompt(
            prompt_txt,
            n_images=len(ref_images),
            role="face" if mode == "v2v" and ref_images else "general",
        )
        if ref_videos:
            prompt_txt = enhance_video_ref_prompt(
                prompt_txt, n_videos=len(ref_videos)
            )
    # face_continue: enhance at run time (needs last-frame picture count)
    # Silent → lock; otherwise upgrade bare [English] lines to <d>…</d>
    prompt_txt = apply_audio_policy(
        prompt_txt,
        {
            "purpose": purpose or ("music_video" if silent else "short_film"),
            "silentAudio": silent,
        },
    )
    prompt_txt = apply_trigger(
        prompt_txt,
        find_spec(
            lora_id=lora_applied.get("lora_id") or "",
            file=lora_applied.get("lora_name") or "",
        ),
    )
    job = {
        "id": str(uuid.uuid4()),
        "status": "queued",
        "prompt": prompt_txt,
        "duration": body.duration,
        "aspect": body.aspect,
        "quality": normalize_quality(body.quality),
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
        "audio_continuity": bool(body.audio_continuity),
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
        "lane": "director" if (body.lane or "").strip().lower() == "director" else "scene",
        "prompt_rewritten": bool(body.prompt_rewriter_enabled),
        "h3_models": h3_models.resolve(h3_models.graph_for_mode(mode)),
        "post_pass": _normalize_post_pass(getattr(body, "post_pass", None)),
        "sheet_job": bool(getattr(body, "sheet_job", False)),
        **lora_applied,
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


@app.post("/api/motion-transfer/chain")
async def motion_transfer_chain(body: MotionTransferChainBody):
    """Queue a GPU-safe Motion Transfer sequence: first motion clip + continues.

    The first job receives the motion video. Its children preserve the target
    appearance and continue from the previous generated frame, avoiding a
    single expensive 15-second render.
    """
    if body.duration != 5:
        raise HTTPException(400, "15 sn Motion Transfer zinciri 3 × 5 sn olarak çalışır")
    if not body.ref_videos:
        raise HTTPException(400, "Motion Transfer zinciri için hareket referans videosu yükle")

    first_body = body.model_copy(deep=True)
    first_body.mode = "v2v"
    first_body.continue_from_job_id = None
    first = await generate(first_body)
    created = [first]
    parent_id = first["id"]
    for _ in range(int(body.segments) - 1):
        child_body = body.model_copy(deep=True)
        child_body.mode = "continue"
        child_body.continue_from_job_id = parent_id
        child_body.ref_videos = None
        # Keep target stills: the existing face-continue path combines them
        # with the parent last frame once it becomes available.
        child = await generate(child_body)
        created.append(child)
        parent_id = child["id"]

    chain_id = f"motion-{first['id'][:12]}"
    async with _lock:
        for index, created_job in enumerate(created, start=1):
            known = next((j for j in _jobs if j.get("id") == created_job["id"]), None)
            if known is not None:
                known.update(
                    {
                        "batch_id": chain_id,
                        "batch_index": index,
                        "batch_total": len(created),
                        "motion_transfer_chain": True,
                    }
                )
        _save_jobs()
    return {**created[0], "jobs": created, "count": len(created), "chain_id": chain_id}


@app.post("/api/batch")
async def batch(body: BatchBody):
    if body.duration not in ALLOWED_DURATIONS:
        raise HTTPException(400, f"duration must be one of {ALLOWED_DURATIONS}")
    if str(body.quality) not in QUALITY_SHORT_EDGE:
        raise HTTPException(400, "quality must be 352, 480, 608, 736, 768, or 1088 (aliases: 720, 1080)")
    if not await comfy.healthy():
        raise HTTPException(503, "ComfyUI kapalı")
    await _free_llm_for_production()
    purpose = (body.purpose or "").strip() or None
    lora_bits = _lora_fields(body)
    silent = bool(body.silent_audio) or bool(body.music_id)
    prompts = [p.strip() for p in body.prompts if p.strip()]
    if not prompts:
        raise HTTPException(400, "prompt yok")
    if body.prompt_rewriter_enabled:
        rewritten_prompts = []
        for i, p in enumerate(prompts):
            rp = await _rewrite_scene_text(
                p,
                enabled=True,
                context=f"batch shot {i + 1}/{len(prompts)}",
                require=True,
            )
            rewritten_prompts.append((rp or p).strip() or p)
        prompts = rewritten_prompts
    shot_modes = [str(m or "").strip().lower() for m in (body.modes or [])]
    use_per_shot = bool(shot_modes)
    # Global chain tip = optional; within-batch chain = shots 2+ continue from shot 1…N-1
    intra_batch = len(prompts) > 1
    append_global = bool(body.link_continue) and bool(body.append_to_chain)
    tip = _chain_tip() if append_global else None
    chain_next = intra_batch or append_global
    if use_per_shot:
        # Mixed New Video / Continue: do not auto-continue from the global chain tip
        tip = None
        append_global = False
        chain_next = True
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
    parent: Optional[str] = tip["id"] if tip else None
    start_from_tip = bool(parent)
    lib = cinema.load()
    async with _lock:
        for i, text in enumerate(prompts):
            seed = body.seed if body.seed >= 0 else (int(time.time() * 1000) + i) % (2**53)
            want_continue = False
            if use_per_shot:
                m = shot_modes[i] if i < len(shot_modes) else "t2v"
                want_continue = m in ("continue", "devam", "i2v", "last_frame")
            elif intra_batch and i > 0:
                want_continue = True
            elif append_global and i == 0 and start_from_tip:
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
            # A scene/location plate is useful for a new shot, but it must
            # never enter a continuation's identity pool.  Otherwise Ref2VA
            # can restart every clip from the same location still instead of
            # the previous video's final frame.
            character_refs = cinema.bound_character_portraits(text, lib)
            shot_text = bound["prompt"] if bound.get("hits") else text
            if mode in ("continue", "face_continue"):
                # Continue = parent last frame + optional character portraits only.
                # Never carry location/creature reference plates into this list.
                shot_refs = list(face_refs) if face_refs else []
                if body.face_lock and character_refs:
                    face_refs = list(dict.fromkeys([*face_refs, *character_refs]))[:9]
                    if face_refs:
                        shot_refs = list(face_refs)
                if face_refs:
                    mode = "face_continue"
            else:
                shot_refs = bound["ref_images"] or (list(face_refs) if face_refs else [])
            if bound.get("hits") and shot_refs and mode == "t2v":
                mode = (
                    "face"
                    if bound["has_character"] and not bound["has_location"]
                    else "ref"
                )
            # Accumulate character portraits only. `shot_refs` may also include
            # a location plate for an initial Ref2VA shot and must not leak into
            # later Continue jobs.
            if body.face_lock and character_refs:
                face_refs = list(dict.fromkeys([*face_refs, *character_refs]))[:9]
            lora_src, graph = _lora_src_for_shot(body, bound, mode)
            shot_steps, shot_sampler, shot_scheduler = _with_lora_preset(
                lora_src, base_steps, base_sampler, base_scheduler, graph=graph
            )
            shot_lora = _lora_fields(lora_src)
            shot_text = apply_trigger(
                shot_text,
                find_spec(
                    lora_id=shot_lora.get("lora_id") or "",
                    file=shot_lora.get("lora_name") or "",
                ),
            )
            job = {
                "id": str(uuid.uuid4()),
                "status": "queued",
                "prompt": shot_text,
                "duration": body.duration,
                "aspect": body.aspect,
                "quality": normalize_quality(body.quality),
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
                "lane": (
                    "director"
                    if (body.lane or "").strip().lower() == "director" or body.cinema_batch
                    else "scene"
                ),
                "h3_models": h3_models.resolve(h3_models.graph_for_mode(mode)),
                "post_pass": _normalize_post_pass(getattr(body, "post_pass", None)),
                **shot_lora,
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
            if chain_next or use_per_shot:
                parent = job["id"]
        _save_jobs()
    slog.info(
        "batch queued",
        count=len(created),
        append_global=append_global,
        intra_batch=intra_batch,
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
        job.pop("comfy_step", None)
        job.pop("comfy_step_max", None)
        job.pop("progress_source", None)
        job.pop("_ws_progress_at", None)
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
            job.pop("comfy_step", None)
            job.pop("comfy_step_max", None)
            job.pop("progress_source", None)
            job.pop("_ws_progress_at", None)
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
    # Optional: only clear jobs in this lane (scene | director)
    lane: Optional[str] = None


def _job_lane(job: dict) -> str:
    lane = str(job.get("lane") or "").strip().lower()
    if lane in ("scene", "director"):
        return lane
    if job.get("cinema_batch") or job.get("batch_id"):
        return "director"
    return "scene"


@app.post("/api/jobs/clear")
async def clear_jobs(body: ClearJobsBody):
    """Clear past job records so the list doesn't keep old failures forever."""
    global _jobs
    scope = (body.scope or "errors").strip().lower()
    if scope not in ("errors", "done", "finished", "all"):
        raise HTTPException(400, "scope: errors | done | finished | all")
    lane_filter = (body.lane or "").strip().lower()
    if lane_filter and lane_filter not in ("scene", "director"):
        raise HTTPException(400, "lane: scene | director")

    def _match(j: dict) -> bool:
        st = j.get("status")
        if st in ("running", "queued"):
            return False
        if lane_filter and _job_lane(j) != lane_filter:
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
async def clip_video(job_id: str, dl: int = Query(0)):
    for j in _jobs:
        if j["id"] == job_id and j.get("local_path"):
            p = Path(j["local_path"])
            if p.exists():
                return _video_file_response(p, meta=j, item_id=job_id, download=bool(dl))
    # Fall back to permanent gallery if working clip was wiped
    gal = GALLERY / f"{job_id}.mp4"
    if gal.exists():
        entry = next((g for g in _gallery if g.get("id") == job_id), None)
        return _video_file_response(
            gal, meta=entry or {"id": job_id}, item_id=job_id, download=bool(dl)
        )
    raise HTTPException(404, "video yok")


async def _import_reference_bytes(raw: bytes, filename: str = "ref.png") -> dict:
    """Put a trusted image into H3's reference store and Comfy input folder."""
    if not await comfy.healthy():
        raise HTTPException(503, "ComfyUI kapalı — referans yüklenemez")
    if not raw:
        raise HTTPException(400, "boş dosya")
    if len(raw) > 40 * 1024 * 1024:
        raise HTTPException(400, "dosya çok büyük (max 40MB)")
    orig = Path(filename or "ref.png").name
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


@app.post("/api/refs/upload")
async def upload_ref(file: UploadFile = File(...)):
    """Upload a reference image to Studio + Comfy input folder."""
    return await _import_reference_bytes(await file.read(), file.filename or "ref.png")


@app.get("/api/image-studio/status")
async def image_studio_status():
    """Availability plus a privacy-safe summary of Image Studio's live queue."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(4.0, connect=2.0)) as client:
            response = await client.get(f"{IMAGE_STUDIO_URL}/api/status")
            response.raise_for_status()
            data = response.json()
            jobs_response = await client.get(f"{IMAGE_STUDIO_URL}/api/jobs")
            jobs = jobs_response.json() if jobs_response.is_success else []
        active = [j for j in jobs if str(j.get("status") or "").lower() == "running"]
        queued = [j for j in jobs if str(j.get("status") or "").lower() == "queued"]
        return {
            "available": bool(data.get("ok")),
            "url": IMAGE_STUDIO_URL,
            "running": len(active),
            "queued": len(queued),
            "progress_label": str(active[0].get("progress_label") or "") if active else "",
        }
    except Exception:
        return {"available": False, "url": IMAGE_STUDIO_URL, "running": 0, "queued": 0}


@app.post("/api/image-studio/reference")
async def create_image_studio_reference(body: ImageStudioReferenceBody):
    """Generate one Qwen still locally, then add it as an H3 Ref2VA reference.

    Image Studio owns a separate ComfyUI process.  Refuse overlap instead of
    risking a VRAM crash on a single-GPU installation.
    """
    if _running or any(j.get("status") in ("queued", "running") for j in _jobs):
        raise HTTPException(409, "H3 üretimi/kuyruğu boş olmalı — Image Studio ayrı ComfyUI ve aynı VRAM'i kullanır")
    prompt = body.prompt.strip()
    request_body = {
        "prompt": prompt,
        "aspect": body.aspect,
        "steps": max(20, min(40, int(body.steps or 30))),
        "mode": "txt2img",
        "count": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=4.0)) as client:
            health_response = await client.get(f"{IMAGE_STUDIO_URL}/api/status")
            health_payload = health_response.json() if health_response.content else {}
            if health_response.is_error or not health_payload.get("ok"):
                raise HTTPException(503, "Image Studio veya kendi ComfyUI'si açık değil")
            image_comfy_url = str(health_payload.get("comfy_url") or "").rstrip("/")
            response = await client.post(f"{IMAGE_STUDIO_URL}/api/generate", json=request_body)
            payload = response.json() if response.content else {}
            if response.is_error:
                raise HTTPException(response.status_code, str(payload.get("detail") or "Image Studio üretimi başlatılamadı"))
            image_job_id = str(payload.get("id") or "")
            if not image_job_id:
                raise HTTPException(502, "Image Studio geçerli iş kimliği döndürmedi")

            # Image Studio exposes its own job progress, but the bridge returns
            # only once there is a durable image that H3 can safely import.
            deadline = time.monotonic() + (45 * 60)
            while time.monotonic() < deadline:
                await asyncio.sleep(1.5)
                status_response = await client.get(f"{IMAGE_STUDIO_URL}/api/jobs/{image_job_id}")
                status_payload = status_response.json() if status_response.content else {}
                if status_response.is_error:
                    raise HTTPException(502, "Image Studio işi okunamadı")
                status = str(status_payload.get("status") or "").lower()
                if status == "done" and status_payload.get("has_image"):
                    image_response = await client.get(f"{IMAGE_STUDIO_URL}/api/jobs/{image_job_id}/image")
                    if image_response.is_error or not image_response.content:
                        raise HTTPException(502, "Image Studio görseli indirilemedi")
                    # Qwen stays resident in Image Studio's separate ComfyUI by
                    # default. Free it before the next H3 render needs the GPU.
                    if image_comfy_url:
                        try:
                            await client.post(
                                f"{image_comfy_url}/free",
                                json={"unload_models": True, "free_memory": True},
                                timeout=10.0,
                            )
                        except httpx.HTTPError:
                            pass
                    result = await _import_reference_bytes(
                        image_response.content, f"image_studio_{image_job_id[:12]}.png"
                    )
                    _set_ref_prompt(result.get("filename") or "", prompt, "image-studio")
                    result.update({"source": "image-studio", "image_studio_job_id": image_job_id})
                    return result
                if status in ("error", "cancelled", "canceled"):
                    raise HTTPException(502, str(status_payload.get("error") or "Image Studio üretimi durdu"))
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(503, f"Image Studio ulaşılamıyor ({IMAGE_STUDIO_URL})") from exc
    raise HTTPException(504, "Image Studio görseli 45 dakika içinde tamamlanmadı")


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


@app.post("/api/refs/upload-audio")
async def upload_ref_audio(file: UploadFile = File(...)):
    """Upload a voice clip to Studio + Comfy input/ for LoadAudio / Multishot voice_ref."""
    if not await comfy.healthy():
        raise HTTPException(503, "ComfyUI kapalı — ses yüklenemez")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "boş dosya")
    if len(raw) > 40 * 1024 * 1024:
        raise HTTPException(400, "ses çok büyük (max 40MB)")
    orig = Path(file.filename or "voice.wav").name
    ext = orig.rsplit(".", 1)[-1].lower() if "." in orig else "wav"
    if ext not in ("wav", "mp3", "flac", "ogg", "m4a", "aac"):
        ext = "wav"
    rid = str(uuid.uuid4())[:12]
    local_name = f"h3_voice_{rid}.{ext}"
    REF_AUDIOS.mkdir(parents=True, exist_ok=True)
    dest = REF_AUDIOS / local_name
    dest.write_bytes(raw)
    try:
        comfy_name = await comfy.upload_audio(dest, local_name)
    except Exception as e:
        raise HTTPException(502, f"Comfy audio upload hata: {e}") from e
    return {
        "id": rid,
        "name": comfy_name,
        "filename": local_name,
        "url": f"/api/ref-audio/{local_name}",
        "bytes": len(raw),
        "kind": "audio",
    }


@app.get("/api/ref-audio/{filename}")
async def get_ref_audio(filename: str):
    name = Path(filename).name
    path = REF_AUDIOS / name
    if not path.exists():
        raise HTTPException(404, "ses yok")
    return FileResponse(path)


@app.get("/api/ref-videos/{filename}")
async def get_ref_video(filename: str):
    name = Path(filename).name
    path = REF_VIDEOS / name
    if not path.exists():
        raise HTTPException(404, "video yok")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/refs")
async def list_refs():
    """Images available to H3, newest first, for the photo gallery."""
    image_exts = {".png", ".jpg", ".jpeg", ".webp"}
    meta = _load_ref_meta()
    items = []
    for path in REFS.iterdir() if REFS.exists() else []:
        if not path.is_file() or path.suffix.lower() not in image_exts:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        items.append({
            "name": path.name,
            "url": f"/api/refs/{path.name}",
            "created_at": stat.st_mtime,
            "bytes": stat.st_size,
            "prompt": str((meta.get(path.name) or {}).get("prompt") or ""),
            "source": str((meta.get(path.name) or {}).get("source") or ""),
        })
    items.sort(key=lambda item: float(item["created_at"]), reverse=True)
    return {"items": items, "count": len(items)}


@app.delete("/api/refs/{filename}")
async def delete_ref(filename: str):
    """Delete an uploaded reference image from Studio and Comfy input."""
    name = Path(filename).name
    removed = False
    for path in (REFS / name, COMFY_INPUT / name):
        if path.exists():
            removed = _unlink_retry(path) or removed
    if not removed:
        raise HTTPException(404, "görsel yok")
    meta = _load_ref_meta()
    if meta.pop(name, None) is not None:
        _save_ref_meta(meta)
    slog.info("reference image deleted", filename=name)
    return {"ok": True, "filename": name}


@app.delete("/api/ref-videos/{filename}")
async def delete_ref_video(filename: str):
    """Delete an uploaded reference video from Studio and Comfy input."""
    name = Path(filename).name
    removed = False
    for path in (REF_VIDEOS / name, COMFY_INPUT / name):
        if path.exists():
            removed = _unlink_retry(path) or removed
    if not removed:
        raise HTTPException(404, "video yok")
    slog.info("reference video deleted", filename=name)
    return {"ok": True, "filename": name}


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
    prompt_rewriter_enabled: bool = False


@app.get("/api/prompt-rewriter/status")
async def prompt_rewriter_status():
    """Status for LLM prompt optimize (legacy path name kept for the UI)."""
    ok = False
    try:
        ok = bool(await llm.healthy())
    except Exception:
        ok = False
    return {
        "available": ok,
        "runtime": "llm" if ok else "unavailable",
    }


@app.post("/api/prompt/rewrite")
async def prompt_rewrite(body: PromptRewriteBody):
    """Rewrite a Sahne prompt without queueing (LLM instruction polish)."""
    raw = (body.prompt or "").strip()
    if not raw:
        raise HTTPException(400, "prompt yok")
    if not body.prompt_rewriter_enabled:
        return {"prompt": raw, "rewritten": False}
    if not await llm.healthy():
        raise HTTPException(503, "Yönetmen LLM hazır değil — Ayarlar’dan model/key aç")
    out = await _rewrite_scene_text(
        raw, enabled=True, context=body.context or "", require=True
    )
    return {"prompt": out, "rewritten": out.strip() != raw}


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
        f"Each shot is one {clip}s H3 clip. First shot mode t2v, later shots continue "
        f"ONLY when the same cinema character name carries over; cutaway / new cast → t2v. "
        f"When a character appears, write their cinema card name verbatim.\n"
        "Shot text must mention character and location names exactly as in characters[]. "
        "20–40 shots max. No markdown."
    ) + _prompt_optimize_instruction(body.prompt_rewriter_enabled)
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


class CinemaGenerateShotsBody(BaseModel):
    model: Optional[str] = None
    duration: Optional[int] = None
    shot_count: Optional[int] = None
    logline: Optional[str] = None
    prompt_rewriter_enabled: bool = False


class CinemaDirectorBody(BaseModel):
    """Studio-native director: FAZ A outline → FAZ B per-shot SCENE → cinema.shots."""
    model: Optional[str] = None
    duration: Optional[int] = None
    shot_count: Optional[int] = None
    total_seconds: Optional[int] = None
    logline: Optional[str] = None
    prompt_rewriter_enabled: bool = False
    stream: bool = True


def _brief_from_cinema_board(
    lib: dict,
    *,
    clip: int,
    shot_count: int,
    total_seconds: Optional[int] = None,
    logline: str = "",
) -> dict:
    """Map cinema cards → FilmBrief seed for two-phase director."""
    chars = []
    for c in lib.get("characters") or []:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        desc = str(c.get("notes") or c.get("description") or c.get("card") or "").strip()
        chars.append({"name": name, "description": desc or "consistent look and wardrobe"})
    locs = []
    for loc in lib.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        name = str(loc.get("name") or "").strip()
        if not name:
            continue
        desc = str(loc.get("notes") or loc.get("description") or "").strip()
        locs.append({"name": name, "description": desc or "consistent set lighting"})
    setup = lib.get("setup") if isinstance(lib.get("setup"), dict) else {}
    purpose = str(setup.get("purpose") or lib.get("purpose") or "short_film").strip()
    if purpose in ("auto", ""):
        purpose = "short_film"
    style = str(setup.get("style") or lib.get("visualStyle") or "realistic").strip()
    if style in ("auto", ""):
        style = "realistic"
    silent = bool(
        (lib.get("audio") or {}).get("mode") == "silent"
        or purpose in ("music_video", "music-video")
    )
    ll = (
        logline
        or str(lib.get("logline") or "").strip()
        or str(lib.get("title") or "").strip()
        or "Cinema studio film from locked cast and locations."
    )
    need = max(1, int(shot_count))
    total = int(total_seconds) if total_seconds else need * clip
    brief = {
        "purpose": purpose,
        "visualStyle": style,
        "clipDurationSec": clip,
        "aspect": "16:9",
        "logline": ll,
        "totalDurationSec": total,
        "expectedShotCount": need,
        "characters": chars,
        "locations": locs,
        "shots": [],
        "shotOutline": [],
        "silentAudio": silent,
    }
    role = str(lib.get("role_script") or lib.get("script") or "").strip()
    if role and len(role) > 40:
        brief["roleHint"] = role[:6000]
    return validate_brief(brief)


async def _cinema_director_run(body: CinemaDirectorBody, on_status=None) -> dict:
    """Run FAZ A + FAZ B against cinema board; write full SCENE shots into cinema.json."""
    lib = cinema.load()
    chars = [
        c
        for c in (lib.get("characters") or [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    ]
    locs = [
        c
        for c in (lib.get("locations") or [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    ]
    role = str(lib.get("role_script") or "").strip()
    if not chars and not locs and len(role) < 40:
        raise HTTPException(
            400,
            "Önce karakter/mekan kartı ekle veya rol metni yapıştır",
        )
    if not await llm.healthy():
        raise HTTPException(503, "Yönetmen LLM hazır değil — sağ üst Ayarlar’dan key ekle")
    model = await llm.resolve_model(body.model or _director_model)
    clip = int(body.duration or lib.get("duration") or 5)
    if clip not in ALLOWED_DURATIONS:
        clip = 5
    n = int(body.shot_count or 0)
    if n < 1:
        if body.total_seconds:
            n = expected_shot_count(int(body.total_seconds), clip)
        else:
            n = max(4, min(24, 6 + len(chars) * 2))
    n = max(1, min(40, n))

    def _status(text: str) -> None:
        if on_status:
            try:
                on_status({"type": "status", "text": text})
            except Exception:
                pass
        _emit_director_status(text)

    _status(f"Stüdyo yönetmeni — {n} shot iskeleti hazırlanıyor…")
    brief = _brief_from_cinema_board(
        lib,
        clip=clip,
        shot_count=n,
        total_seconds=body.total_seconds,
        logline=str(body.logline or "").strip(),
    )
    # If no cast yet but role text exists, seed characters via outline LLM
    if not brief.get("characters") and role:
        brief["logline"] = brief.get("logline") or role[:240]

    # Temporarily bind progress sink for FAZ B status lines
    token = None
    if on_status:
        token = _director_progress.set(on_status)
    try:
        brief = await _expand_brief_shots(brief, model)
    finally:
        if token is not None:
            _director_progress.reset(token)

    if not brief.get("shots"):
        raise HTTPException(502, "Yönetmen shot üretemedi")

    thin = int(brief.get("thinShotCount") or 0)
    shots = brief.get("shots") or []
    thin_real = sum(
        1
        for i, s in enumerate(shots)
        if isinstance(s, dict)
        and not score_h3_prompt(
            s.get("h3Prompt") or "",
            index=i,
            silent=bool(brief.get("silentAudio")),
            shot=s,
        )["ok"]
    )
    if thin_real > max(1, len(shots) // 3):
        raise HTTPException(
            502,
            f"Yönetmen kalite kapısı: {thin_real}/{len(shots)} shot şablon/zayıf kaldı. "
            "LLM’i güçlendirip tekrar dene (Ayarlar → model) — ince filler üretime alınmaz.",
        )

    out = cinema.ingest_from_director_brief(brief, role_script=role)
    if brief.get("shotOutline"):
        data = cinema.load()
        data["shotOutline"] = brief["shotOutline"]
        out = cinema.save(data)
    slog.info(
        "cinema director",
        shots=len(out.get("shots") or []),
        outline=len(brief.get("shotOutline") or []),
        chars=len(out.get("characters") or []),
    )
    return {
        "ok": True,
        "cinema": out,
        "brief": brief,
        "shot_count": len(out.get("shots") or []),
        "outline": brief.get("shotOutline") or [],
    }


@app.post("/api/cinema/director")
async def cinema_director(body: CinemaDirectorBody):
    """One-click studio director: outline → per-shot SCENE → fill cinema shot list."""
    if body.stream:
        q: asyncio.Queue = asyncio.Queue()

        def on_progress(ev: dict[str, Any]) -> None:
            try:
                q.put_nowait(ev if isinstance(ev, dict) else {"type": "status", "text": str(ev)})
            except Exception:
                pass

        async def produce() -> None:
            try:
                result = await _cinema_director_run(body, on_status=on_progress)
                await q.put({"type": "result", "data": result})
            except HTTPException as e:
                await q.put(
                    {"type": "error", "detail": e.detail, "status": e.status_code}
                )
            except Exception as e:
                await q.put({"type": "error", "detail": str(e)})
            finally:
                await q.put(None)

        async def event_gen():
            task = asyncio.create_task(produce())
            yield (
                "data: "
                + json.dumps(
                    {"type": "status", "text": "Stüdyo yönetmeni başlıyor…"},
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
    return await _cinema_director_run(body)


@app.post("/api/cinema/generate-shots")
async def cinema_generate_shots(body: CinemaGenerateShotsBody):
    """LLM writes shot list from existing cinema cast/locations only (studio production)."""
    lib = cinema.load()
    chars = [c for c in (lib.get("characters") or []) if isinstance(c, dict) and str(c.get("name") or "").strip()]
    locs = [c for c in (lib.get("locations") or []) if isinstance(c, dict) and str(c.get("name") or "").strip()]
    if not chars and not locs:
        raise HTTPException(400, "Önce karakter veya mekan kartı ekle")
    if not await llm.healthy():
        raise HTTPException(503, "Yönetmen LLM hazır değil — sağ üst Ayarlar’dan key ekle")
    model = await llm.resolve_model(body.model or _director_model)
    clip = int(body.duration or lib.get("duration") or 5)
    if clip not in (4, 5, 6, 8, 10, 15):
        clip = 5
    n = int(body.shot_count or 0)
    if n < 1:
        n = max(4, min(24, 6 + len(chars) * 2))
    n = max(2, min(40, n))
    removed: set[str] = set()
    for sess in (_sessions or {}).values():
        removed |= _session_removed_names(sess)
    board = format_cinema_board(lib, full=True)
    sys_msg = (
        "You are MiniMax H3 Cinema Studio shot writer. "
        "Read the studio board and write ONLY a shot list. Reply with JSON only:\n"
        '{"shots":[{"text":"cinematic SCENE paragraph","sectionId":"scene-1","mode":"t2v"|"continue"}]}\n'
        f"Each shot is one {clip}s clip. Group uninterrupted beats with one sectionId: the first is t2v and later shots are continue. "
        f"A new location, time, or action starts a new sectionId with t2v; the same character alone never makes it continue. "
        f"Use cinema character names exactly as on the board.\n"
        f"Write exactly {n} shots. "
        "Use character and location names EXACTLY as on the board. "
        "Do not invent new characters or locations. Do not modify cast cards. No markdown."
    ) + _prompt_optimize_instruction(body.prompt_rewriter_enabled)
    if removed:
        sys_msg += (
            "\nDo not use these removed names: " + ", ".join(sorted(removed)) + "."
        )
    user_bits = [board or "(empty board)"]
    title = str(lib.get("title") or "").strip()
    logline = str(body.logline or "").strip()
    if title:
        user_bits.insert(0, f"Film title: {title}")
    if logline:
        user_bits.insert(0, f"Logline / brief: {logline}")
    role = str(lib.get("role_script") or lib.get("script") or "").strip()
    if role and len(role) > 40:
        user_bits.append("Optional role text (tone only; cast board wins):\n" + role[:8000])
    try:
        reply = await llm.chat(
            model,
            [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": "\n\n".join(user_bits)},
            ],
            temperature=0.45,
            format_json=True,
            num_predict=8192,
        )
    except Exception as e:
        raise HTTPException(502, f"Yönetmen LLM hata ({llm.provider()}): {e}") from e
    parsed = extract_json_object(reply) or {}
    raw_shots = parsed.get("shots") if isinstance(parsed, dict) else None
    if not isinstance(raw_shots, list) or not raw_shots:
        raise HTTPException(502, "LLM shot listesi döndürmedi")
    new_shots: list[dict[str, Any]] = []
    for i, item in enumerate(raw_shots[:n]):
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("h3Prompt") or item.get("prompt") or "").strip()
            mode = str(item.get("mode") or "t2v").lower()
        else:
            text = str(item or "").strip()
            mode = "t2v"
        if not text:
            continue
        if mode not in ("continue", "devam", "i2v", "last_frame"):
            mode = "t2v"
        else:
            mode = "continue"
        if not new_shots:
            mode = "t2v"
        section_id = str(item.get("sectionId") or item.get("section_id") or "").strip() if isinstance(item, dict) else ""
        new_shots.append({"id": str(uuid.uuid4())[:8], "text": text, "mode": mode, "section_id": section_id})
    if not new_shots:
        raise HTTPException(502, "Geçerli shot yok")
    # Normalize the model output into explicit section chains. A new section never
    # inherits the prior section's last frame, even if the same cast is present.
    previous_section = ""
    section_number = 0
    for i, shot in enumerate(new_shots):
        requested = str(shot.get("mode") or "").strip().lower() == "continue"
        section_id = str(shot.get("section_id") or "").strip()
        if not section_id:
            if i and requested and previous_section:
                section_id = previous_section
            else:
                section_number += 1
                section_id = f"scene-{section_number}"
        same_section = bool(i and section_id == previous_section)
        shot["section_id"] = section_id
        shot["mode"] = "continue" if same_section and requested else "t2v"
        previous_section = section_id
    lib["shots"] = new_shots
    lib["script"] = "\n\n---\n\n".join(s["text"] for s in new_shots)
    lib["duration"] = clip
    cinema.save(lib)
    slog.info("cinema generate-shots", shots=len(new_shots), chars=len(chars), locs=len(locs))
    return {"ok": True, "cinema": lib, "shot_count": len(new_shots)}


@app.post("/api/cinema/character")
async def cinema_add_character(body: dict[str, Any]):
    return cinema.upsert_asset("character", body or {})


@app.patch("/api/cinema/character/{asset_id}")
async def cinema_patch_character(asset_id: str, body: dict[str, Any]):
    updated = cinema.update_asset("character", asset_id, body or {})
    if not updated:
        raise HTTPException(404, "karakter yok")
    return updated


@app.delete("/api/cinema/character/{asset_id}")
async def cinema_del_character(asset_id: str):
    data = cinema.load()
    found = next((x for x in (data.get("characters") or []) if str(x.get("id") or "") == str(asset_id)), None)
    name = str((found or {}).get("name") or "").strip()
    if not cinema.delete_asset("character", asset_id):
        raise HTTPException(404, "karakter yok")
    _remember_removed_asset("character", name, asset_id)
    return {"ok": True, "id": asset_id}


@app.post("/api/cinema/location")
async def cinema_add_location(body: dict[str, Any]):
    return cinema.upsert_asset("location", body or {})


@app.patch("/api/cinema/location/{asset_id}")
async def cinema_patch_location(asset_id: str, body: dict[str, Any]):
    updated = cinema.update_asset("location", asset_id, body or {})
    if not updated:
        raise HTTPException(404, "mekan yok")
    return updated


@app.delete("/api/cinema/location/{asset_id}")
async def cinema_del_location(asset_id: str):
    data = cinema.load()
    found = next((x for x in (data.get("locations") or []) if str(x.get("id") or "") == str(asset_id)), None)
    name = str((found or {}).get("name") or "").strip()
    if not cinema.delete_asset("location", asset_id):
        raise HTTPException(404, "mekan yok")
    _remember_removed_asset("location", name, asset_id)
    return {"ok": True, "id": asset_id}


class CinemaMuxBody(BaseModel):
    batch_id: Optional[str] = None
    score_id: Optional[str] = None
    score_volume: Optional[float] = None
    job_ids: Optional[list[str]] = None


class ClipsConcatBody(BaseModel):
    job_ids: list[str] = Field(..., min_length=2)
    batch_id: Optional[str] = None
    title: Optional[str] = None

    @field_validator("job_ids", mode="before")
    @classmethod
    def _coerce_job_ids(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []


def _job_record(job_id: str) -> Optional[dict]:
    jid = (job_id or "").strip()
    if not jid:
        return None
    for j in _jobs:
        if str(j.get("id") or "") == jid:
            return j
    for g in _gallery:
        if str(g.get("id") or "") == jid:
            return g
    return None


async def _paths_for_job_ids(job_ids: list[str]) -> list[Path]:
    ids = [str(x).strip() for x in (job_ids or []) if str(x).strip()]
    if len(ids) < 2:
        raise HTTPException(400, "en az 2 klip seç")
    paths: list[Path] = []
    for jid in ids:
        rec = _job_record(jid)
        if not rec:
            raise HTTPException(404, f"klip bulunamadı: {jid[:8]}")
        st = str(rec.get("status") or "done").lower()
        if st in ("queued", "running"):
            raise HTTPException(400, f"klip hâlâ üretiliyor: {jid[:8]}")
        if st in ("error", "cancelled"):
            raise HTTPException(400, f"klip başarısız: {jid[:8]}")
        try:
            paths.append(await _ensure_job_video(rec))
        except Exception:
            gal = GALLERY / f"{jid}.mp4"
            if not gal.exists():
                raise HTTPException(400, f"klip videosu yok: {jid[:8]}")
            paths.append(gal)
    return paths


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
    """H3MultishotSampler jobs: packs of 8 shots (e.g. 8×5s = 40s). Extra shots = next take."""
    if not detect_multishot_pack(COMFY_ROOT):
        raise HTTPException(
            400,
            "H3 Multishot paketi yok — Pinokio: Download Models → H3 Multishot, sonra Stop → Start",
        )
    if not parsed:
        raise HTTPException(400, "Senaryo / shot yok")
    pack = max(1, int(MULTISHOT_MAX_SHOTS))
    chunks = cinema.group_seamless_takes(parsed, prompts, pack=pack)
    take_total = len(chunks)
    w, h = resolve_size(body.aspect, body.quality)
    steps = body.steps if body.steps and body.steps > 0 else 20
    sampler = body.sampler or "res_multistep"
    scheduler = body.scheduler or "simple"
    jobs: list[dict] = []
    base_seed = body.seed if body.seed >= 0 else int(time.time() * 1000) % (2**53)
    shot_offset = 0
    for take_i, (chunk_parsed, chunk_prompts) in enumerate(chunks, start=1):
        texts: list[str] = []
        bound_hits: list[dict] = []
        for text in chunk_prompts:
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
        take_steps, take_sampler, take_scheduler = _with_lora_preset(
            lora_src, steps, sampler, scheduler, graph="fl2va"
        )
        lora_bits = _lora_fields(lora_src)
        trig_spec = find_spec(
            lora_id=lora_bits.get("lora_id") or "",
            file=lora_bits.get("lora_name") or "",
        )
        texts = [apply_trigger(t, trig_spec) for t in texts]
        script = "\n---\n".join(texts)
        seed = (base_seed + take_i - 1) if body.seed >= 0 else (base_seed + take_i - 1) % (2**53)
        take_title = str((chunk_parsed[0] or {}).get("take_title") or "").strip()
        if take_total == 1:
            label = f"sırada · kesintisiz · {take_title}" if take_title else "sırada · kesintisiz zincir"
        else:
            core = f"{take_title} · " if take_title else ""
            label = f"sırada · {core}take {take_i}/{take_total}"
        job = {
            "id": str(uuid.uuid4()),
            "status": "queued",
            "prompt": script,
            "script": script,
            "duration": body.duration,
            "aspect": body.aspect,
            "quality": normalize_quality(body.quality),
            "width": w,
            "height": h,
            "seed": seed,
            "steps": take_steps,
            "sampler": take_sampler,
            "scheduler": take_scheduler,
            "progress_label": label,
            "continue_from": None,
            "first_frame_name": None,
            "ref_images": [],
            "progress": 0,
            "error": None,
            "output": None,
            "created_at": time.time(),
            "mode": "multishot",
            "batch_index": take_i,
            "batch_total": take_total,
            "shot_count": len(chunk_parsed),
            "silent_audio": silent,
            "purpose": purpose,
            "sage_attention": _sage_mode(body),
            "cinema_batch": cinema_batch,
            "batch_id": cinema_batch,
            "lane": "director",
            "post_pass": _normalize_post_pass(getattr(body, "post_pass", None)),
            "voice_refs": _voice_refs_from_hits(merged_hits.get("hits") or []),
            "chain_normalize": True,
            "shot_id": (chunk_parsed[0] or {}).get("id") if chunk_parsed else None,
            "shot_index": shot_offset + 1,
            "take_title": take_title,
            **_lora_fields(lora_src),
        }
        if audio.get("score_id"):
            job["score_id"] = audio.get("score_id")
        jobs.append(job)
        shot_offset += len(chunk_parsed)
    async with _lock:
        _jobs.extend(jobs)
        _save_jobs()
    slog.info(
        "cinema seamless queued",
        shots=len(parsed),
        takes=take_total,
        pack=pack,
        batch=cinema_batch,
        size=f"{w}x{h}",
        duration=body.duration,
    )
    return {"jobs": jobs, "count": len(jobs), "takes": take_total}


def _brief_shot_modes(shots: list[dict]) -> list[str]:
    modes: list[str] = []
    for i, s in enumerate(shots or []):
        if not isinstance(s, dict):
            modes.append("t2v")
            continue
        link = str(s.get("linkToPrev") or "").strip().lower()
        if not link:
            link = "standalone"
        modes.append("continue" if link == "continue" else "t2v")
    return modes


def _brief_to_cinema_shots(shots: list[dict]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, s in enumerate(shots or []):
        if not isinstance(s, dict):
            continue
        if s.get("enabled") is False:
            continue
        text = str(
            s.get("h3Prompt") or s.get("text") or s.get("prompt") or s.get("action") or ""
        ).strip()
        if not text:
            continue
        link = str(s.get("linkToPrev") or "").strip().lower()
        if not link:
            link = "standalone"
        mode = "continue" if link == "continue" else "t2v"
        row: dict[str, Any] = {"text": text, "mode": mode}
        if s.get("sectionId"):
            row["section_id"] = s.get("sectionId")
        if s.get("id"):
            row["id"] = s.get("id")
        out.append(row)
    return out



@app.post("/api/cinema/creature")
async def cinema_add_creature(body: dict[str, Any]):
    return cinema.upsert_asset("creature", body or {})


@app.patch("/api/cinema/creature/{asset_id}")
async def cinema_patch_creature(asset_id: str, body: dict[str, Any]):
    updated = cinema.update_asset("creature", asset_id, body or {})
    if not updated:
        raise HTTPException(404, "yaratık yok")
    return updated


@app.delete("/api/cinema/creature/{asset_id}")
async def cinema_del_creature(asset_id: str):
    data = cinema.load()
    found = next((x for x in (data.get("creatures") or []) if str(x.get("id") or "") == str(asset_id)), None)
    name = str((found or {}).get("name") or "").strip()
    if not cinema.delete_asset("creature", asset_id):
        raise HTTPException(404, "yaratık yok")
    _remember_removed_asset("creature", name, asset_id)
    return {"ok": True, "id": asset_id}


@app.get("/api/cinema/library")
async def cinema_library_get(kind: Optional[str] = None):
    """Global character/location/creature library (persists across films)."""
    k = (kind or "").strip().lower()
    if k in ("character", "location", "creature"):
        return {"ok": True, **cinema.list_library(k)}
    return {"ok": True, **cinema.list_library()}


class CinemaLibrarySaveBody(BaseModel):
    kind: str = "character"
    asset_id: str = Field(..., min_length=1)


class CinemaLibraryPullBody(BaseModel):
    kind: str = "character"
    library_id: str = Field(..., min_length=1)


@app.post("/api/cinema/library/save")
async def cinema_library_save(body: CinemaLibrarySaveBody):
    kind, _ = cinema.asset_kind_key(body.kind)
    try:
        saved = cinema.save_film_asset_to_library(kind, body.asset_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "asset": saved, "kind": kind, "library": cinema.list_library(kind)}


@app.post("/api/cinema/library/pull")
async def cinema_library_pull(body: CinemaLibraryPullBody):
    kind, _ = cinema.asset_kind_key(body.kind)
    try:
        asset = cinema.pull_library_to_film(kind, body.library_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "asset": asset, "kind": kind, "cinema": cinema.load()}


@app.delete("/api/cinema/library/{kind}/{asset_id}")
async def cinema_library_delete(kind: str, asset_id: str):
    k, _ = cinema.asset_kind_key(kind)
    if not cinema.delete_library_asset(k, asset_id):
        raise HTTPException(404, "kütüphanede yok")
    return {"ok": True, "id": asset_id, "kind": k}



class CinemaSheetBody(BaseModel):
    kind: str = "character"  # character | location
    name: str = Field(..., min_length=1)
    notes: str = ""
    asset_id: Optional[str] = None
    duration: int = 5
    quality: str = "736"
    steps: int = 18
    aspect: str = "16:9"
    style: Optional[str] = None
    seed: int = -1
    # Optional Comfy upload name(s) from /api/refs/upload
    ref_image: Optional[str] = None
    ref_images: Optional[list[str]] = None

    @field_validator("ref_images", mode="before")
    @classmethod
    def _sheet_refs(cls, v: Any) -> Optional[list[str]]:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return [v] if v.strip() else None
        if isinstance(v, list):
            out = [str(x).strip() for x in v if str(x).strip()]
            return out[:3] or None
        return None


async def _maybe_attach_sheet_still(job: dict) -> None:
    """After a sheet generate job finishes, keep only the last-frame still; discard video."""
    aid = str(job.get("sheet_asset_id") or "").strip()
    if not aid:
        return
    kind = "location" if str(job.get("sheet_kind") or "") == "location" else (
        "creature" if str(job.get("sheet_kind") or "") == "creature" else "character"
    )
    try:
        if not job.get("last_frame_path"):
            await _prepare_last_frame(job, upload=True)
    except Exception as e:
        slog.warn_job(job, "sheet last frame prep", err=e)
        return
    src = Path(job.get("last_frame_path") or "")
    if not src.is_file():
        slog.warn_job(job, "sheet still missing frame file")
        return
    lib = cinema.load()
    _, key = cinema.asset_kind_key(kind)
    found = next((x for x in lib.get(key) or [] if str(x.get("id")) == aid), None)
    if not found:
        slog.warn_job(job, "sheet asset missing", asset=aid[:8])
        return
    images = list(found.get("images") or [])
    if len(images) >= cinema.MAX_ASSET_IMAGES:
        slog.warn_job(job, "sheet asset image cap")
        return
    rid = str(uuid.uuid4())[:12]
    dest = REFS / f"h3_sheet_{rid}.png"
    REFS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    panel_paths = [dest]
    if kind in ("character", "creature"):
        try:
            panel_paths = cinema.split_tripanel_still(dest, REFS, f"h3_sheet_{rid}")
        except Exception as e:
            slog.warn_job(job, "sheet still split", err=e)
            panel_paths = [dest]
    uploaded: list[dict] = []
    for part in panel_paths:
        try:
            comfy_name = await comfy.upload_image(part, part.name)
        except Exception as e:
            slog.warn_job(job, "sheet still comfy upload", err=e)
            return
        uploaded.append({"file": comfy_name, "url": f"/api/refs/{comfy_name}"})
    if not uploaded:
        return
    auto_only = (not images) or all(
        str((im.get("file") if isinstance(im, dict) else im) or "").startswith("h3_sheet_")
        for im in images
    )
    images = uploaded if auto_only else (uploaded + images)
    found["images"] = images[: cinema.MAX_ASSET_IMAGES]
    cinema.upsert_asset(kind, found)
    # Persist into global library so film switches / empty saves don't lose the sheet
    try:
        lib_saved = cinema.save_film_asset_to_library(kind, aid)
        job["library_id"] = lib_saved.get("id")
        job["library_saved"] = True
    except Exception as e:
        slog.warn_job(job, "sheet library save", err=e)
    job["sheet_still_url"] = uploaded[0]["url"]
    job["sheet_still_urls"] = [row["url"] for row in uploaded]
    job["sheet_attached"] = True
    # Ephemeral sheet: drop the video — only the still matters for refs
    if job.get("sheet_ephemeral") is not False:
        for key_path in ("local_path",):
            p = Path(job.get(key_path) or "")
            if p.is_file():
                try:
                    p.unlink()
                except OSError as e:
                    slog.warn_job(job, "sheet video unlink", err=e)
        clip_fallback = CLIPS / f"{job.get('id')}.mp4"
        if clip_fallback.is_file():
            try:
                clip_fallback.unlink()
            except OSError:
                pass
        gal = GALLERY / f"{job.get('id')}.mp4"
        if gal.is_file():
            try:
                gal.unlink()
            except OSError:
                pass
        # Drop gallery entry if archived earlier
        global _gallery
        jid = str(job.get("id") or "")
        if jid:
            _gallery[:] = [g for g in _gallery if str(g.get("id")) != jid]
            try:
                _save_gallery()
            except Exception:
                pass
        job["output"] = None
        job["local_path"] = None
        job["download_name"] = None
        job["discarded_video"] = True
        job["progress_label"] = "still hazır · video silindi"
    _save_jobs()
    slog.info_job(job, "sheet still attached", kind=kind, asset=aid[:8])


@app.post("/api/cinema/generate-sheet")
async def cinema_generate_sheet(body: CinemaSheetBody):
    """Queue a silent H3 clip that renders a 3-panel character/location reference sheet."""
    if not await comfy.healthy():
        raise HTTPException(503, "ComfyUI kapalı")
    try:
        return await _queue_cinema_sheet_job(
            kind=body.kind or "character",
            name=body.name,
            notes=body.notes or "",
            asset_id=body.asset_id,
            duration=body.duration,
            quality=body.quality,
            steps=body.steps,
            aspect=body.aspect or "16:9",
            style=body.style,
            seed=body.seed if body.seed is not None else -1,
            ref_image=body.ref_image,
            ref_images=body.ref_images,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)[:300]) from e


async def _queue_cinema_sheet_job(
    *,
    kind: str,
    name: str,
    notes: str = "",
    asset_id: Optional[str] = None,
    duration: int = 5,
    quality: str = "736",
    steps: int = 18,
    aspect: str = "16:9",
    style: Optional[str] = None,
    seed: int = -1,
    ref_image: Optional[str] = None,
    ref_images: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Shared sheet queue used by Generate visual + JSON import."""
    kind_raw = str(kind or "character").lower()
    kind, _ = cinema.asset_kind_key(kind_raw)
    name = (name or "").strip()
    if not name:
        raise ValueError("ad gerekli")
    notes = (notes or "").strip()
    style_key = normalize_style(style) if style else "realistic"
    if not style:
        lib0 = cinema.load()
        setup = lib0.get("setup") if isinstance(lib0.get("setup"), dict) else {}
        style_key = normalize_style(setup.get("style") or "realistic")
    style_line = style_craft_line(style_key)
    refs: list[str] = []
    if ref_images:
        refs.extend(str(x) for x in ref_images if str(x).strip())
    one = (ref_image or "").strip()
    if one and one not in refs:
        refs.insert(0, one)
    refs = refs[:3]
    has_ref = bool(refs)
    if kind == "location":
        prompt = cinema.build_location_sheet_prompt(
            name, notes, style_line=style_line, has_place_ref=has_ref
        )
    else:
        prompt = cinema.build_character_sheet_prompt(
            name,
            notes,
            style_line=style_line,
            has_face_ref=has_ref,
            force_creature=(kind == "creature"),
        )
    asset_payload: dict[str, Any] = {
        "name": name,
        "notes": notes,
    }
    if asset_id:
        asset_payload["id"] = asset_id
    if has_ref:
        asset_payload["source_ref"] = refs[0]
    asset = cinema.upsert_asset(kind, asset_payload)
    quality_n = normalize_quality(quality or "736")
    steps_n = steps if steps and steps > 0 else 18
    dur = int(duration) if duration and int(duration) > 0 else 5
    dur = max(4, min(dur, 10))
    gen_kwargs: dict[str, Any] = {
        "prompt": prompt,
        "duration": dur,
        "aspect": aspect or "16:9",
        "quality": quality_n,
        "seed": seed if seed is not None else -1,
        "steps": steps_n,
        "silent_audio": True,
        "purpose": "short_film",
        "lane": "director",
        "prompt_rewriter_enabled": False,
        "sheet_job": True,
    }
    still = still_catalog_spec()
    if still and spec_ready(still):
        gen_kwargs["lora_id"] = still.get("id") or ""
        gen_kwargs["lora_name"] = still.get("file") or ""
        gen_kwargs["lora_strength"] = still.get("strength") or 1.0
    if has_ref:
        if kind == "character":
            gen_kwargs["mode"] = "face"
            gen_kwargs["ref_images"] = refs
            gen_kwargs["ref_image_size"] = "max"
        else:
            gen_kwargs["mode"] = "ref"
            gen_kwargs["ref_images"] = refs
            gen_kwargs["ref_image_size"] = "match"
        gen_kwargs["skip_cinema_assets"] = True
    else:
        gen_kwargs["skip_cinema_assets"] = True
    job = await generate(GenerateBody(**gen_kwargs))
    jid = str(job.get("id") or "")
    for j in _jobs:
        if str(j.get("id")) == jid:
            j["sheet_asset_id"] = asset.get("id")
            j["sheet_kind"] = kind
            j["sheet_name"] = name
            j["sheet_ephemeral"] = True
            j["sheet_has_ref"] = has_ref
            j["frame_length"] = duration_to_length(dur)
            j["duration"] = dur
            j["lane"] = "director"
            ref_bit = (
                " +yüz" if has_ref and kind == "character" else (" +mekân" if has_ref else "")
            )
            j["progress_label"] = f"sheet{ref_bit} · {quality_n}p/{steps_n} → still"
            job = j
            break
    _save_jobs()
    return {
        "job": job,
        "asset": asset,
        "prompt": prompt,
        "kind": kind,
        "ref_images": refs,
    }


def _asset_needs_sheet(asset: Any, *, force: bool = False) -> bool:
    if not isinstance(asset, dict):
        return False
    if not str(asset.get("name") or "").strip():
        return False
    if force:
        return True
    images = asset.get("images")
    if isinstance(images, list) and any(
        isinstance(x, dict) and str(x.get("file") or x.get("url") or "").strip() for x in images
    ):
        return False
    if str(asset.get("image") or "").strip():
        return False
    return True


async def _queue_sheets_for_cinema(
    cine: dict[str, Any],
    *,
    kinds: Optional[list[str]] = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Queue Görsel oluştur (sheet) for cast cards that still lack stills."""
    if not await comfy.healthy():
        return []
    want = {cinema.asset_kind_key(k)[0] for k in (kinds or ["character", "location", "creature"])}
    queued: list[dict[str, Any]] = []
    setup = cine.get("setup") if isinstance(cine.get("setup"), dict) else {}
    style = setup.get("style") if setup.get("style") not in (None, "", "auto") else None
    quality = str(cine.get("quality") or "736")
    try:
        steps = int(cine.get("steps") or 18)
    except (TypeError, ValueError):
        steps = 18
    try:
        duration = int(cine.get("duration") or 5)
    except (TypeError, ValueError):
        duration = 5
    for kind, key in (
        ("character", "characters"),
        ("creature", "creatures"),
        ("location", "locations"),
    ):
        if kind not in want:
            continue
        for asset in cine.get(key) or []:
            if kind == "character" and not force:
                continue
            if not _asset_needs_sheet(asset, force=force and kind == "character"):
                continue
            aid = str(asset.get("id") or "")
            if aid and any(
                str(j.get("sheet_asset_id") or "") == aid
                and str(j.get("status") or "") in ("queued", "running")
                for j in _jobs
            ):
                continue
            try:
                result = await _queue_cinema_sheet_job(
                    kind=kind,
                    name=str(asset.get("name") or ""),
                    notes=str(asset.get("notes") or ""),
                    asset_id=str(asset.get("id") or "") or None,
                    duration=duration,
                    quality=quality,
                    steps=steps,
                    style=style,
                )
                queued.append(
                    {
                        "kind": kind,
                        "name": result.get("asset", {}).get("name") or asset.get("name"),
                        "asset_id": (result.get("asset") or {}).get("id"),
                        "job_id": (result.get("job") or {}).get("id"),
                    }
                )
            except Exception as e:
                slog.warn("import sheet queue failed", kind=kind, name=asset.get("name"), err=e)
    return queued


async def _maybe_continue_pending_produce() -> None:
    """After character/creature/location sheets finish, queue the waiting scene clips."""
    lib = cinema.load()
    pend = lib.get("pending_produce")
    if not isinstance(pend, dict):
        return
    ids = [str(x) for x in (pend.get("sheet_job_ids") or []) if x]
    if not ids:
        lib["pending_produce"] = None
        cinema.save(lib)
        return
    jobs = [j for j in _jobs if str(j.get("id") or "") in set(ids)]
    if any(str(j.get("status") or "") in ("queued", "running") for j in jobs):
        return
    payload = pend.get("payload") if isinstance(pend.get("payload"), dict) else {}
    lib["pending_produce"] = None
    cinema.save(lib)
    if not payload:
        return
    payload["prepare_sheets"] = False
    try:
        queued = await cinema_produce(CinemaProduceBody(**payload))
        slog.info(
            "cinema pending produce scenes",
            count=queued.get("count") if isinstance(queued, dict) else None,
            batch=queued.get("cinema_batch") if isinstance(queued, dict) else None,
        )
    except Exception as e:
        slog.warn("cinema pending produce failed", err=e)


@app.post("/api/cinema/produce")
async def cinema_produce(body: CinemaProduceBody):
    """Queue cinema shots; each shot is New Video (t2v) or Continue (last-frame)."""
    if body.prepare_sheets and not body.seamless:
        lib0 = cinema.load()
        already = lib0.get("pending_produce")
        if isinstance(already, dict) and already.get("sheet_job_ids"):
            return {
                "ok": True,
                "phase": "sheets",
                "pending_scenes": True,
                "count": 0,
                "sheets_queued": [],
                "message": "Görseller zaten kuyrukta — bitince sahneler başlar",
            }
        if body.setup:
            lib0["setup"] = cinema._clean_setup(body.setup)
        if body.audio is not None:
            lib0["audio"] = cinema._clean_audio(body.audio)
        lib0["duration"] = body.duration
        lib0["quality"] = normalize_quality(body.quality)
        lib0["steps"] = body.steps if body.steps and body.steps > 0 else 20
        cinema.save(lib0)
        sheets = await _queue_sheets_for_cinema(
            cinema.load(), force=bool(body.force_sheets)
        )
        if sheets:
            lib0 = cinema.load()
            payload = body.model_dump()
            payload["prepare_sheets"] = False
            lib0["pending_produce"] = {
                "sheet_job_ids": [s.get("job_id") for s in sheets if s.get("job_id")],
                "payload": payload,
                "created_at": time.time(),
            }
            cinema.save(lib0)
            return {
                "ok": True,
                "phase": "sheets",
                "pending_scenes": True,
                "count": 0,
                "sheets_queued": sheets,
            }
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
    lib["quality"] = normalize_quality(body.quality)
    lib["steps"] = body.steps if body.steps and body.steps > 0 else 20
    look = cinema.setup_preamble(lib.get("setup") or {})
    purpose = (body.purpose or "").strip()
    setup_purpose = str((lib.get("setup") or {}).get("purpose") or "").strip()
    if setup_purpose and setup_purpose not in ("auto", ""):
        purpose = setup_purpose
    lora_bits = _lora_fields(body)
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
    # Cutaway / no cast overlap with previous shot → t2v (avoid wrong last-frame drift)
    parsed = cinema.apply_reentry_modes(parsed, lib)
    lib["shots"] = parsed
    cinema.save(lib)
    prompts = [cinema.apply_look(s["text"], head) for s in parsed]
    modes = [s["mode"] for s in parsed]
    # Face-lock refs: only character portraits named in the shots.
    # Location plates must not kill Multishot — they are not face lock.
    cast_refs: list[str] = []
    for p in prompts:
        for f in cinema.bound_character_portraits(p, lib):
            if f not in cast_refs:
                cast_refs.append(f)
    cast_refs = cast_refs[:9]
    still_lock = bool(cast_refs)
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
        chain_modes = modes
        if body.seamless:
            chain_modes = ["t2v"] + ["continue"] * max(0, len(prompts) - 1)
        bb = BatchBody(
            prompts=prompts,
            modes=chain_modes,
            duration=body.duration,
            aspect=body.aspect,
            quality=body.quality,
            steps=body.steps if body.steps and body.steps > 0 else 20,
            sampler=body.sampler,
            scheduler=body.scheduler,
            link_continue=bool(body.link_continue or body.seamless),
            append_to_chain=bool(body.append_to_chain),
            seed=body.seed,
            silent_audio=silent,
            purpose=purpose or "short_film",
            face_lock=True,
            ref_images=cast_refs or None,
            ref_role="face" if cast_refs else None,
            ref_image_size="max" if cast_refs else None,
            lora_id=body.lora_id,
            lora_name=body.lora_name,
            lora_strength=body.lora_strength,
            sage_attention=_sage_mode(body),
            post_pass=body.post_pass,
            cinema_batch=cinema_batch,
            score_id=audio.get("score_id") or None,
            lane="director",
        )
        queued = await batch(bb)
    for i, job in enumerate(queued.get("jobs") or []):
        if (job.get("mode") or "").lower() == "multishot":
            continue
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
    queued["takes"] = int(queued.get("takes") or (len(queued.get("jobs") or []) if want_seamless else 0) or 0)
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


class CinemaProduceFilmBody(BaseModel):
    total_sec: int = 60
    clip_sec: int = 10
    segment_size: int = 6
    segment_index: Optional[int] = None
    advance: bool = False
    reset_plan: bool = True
    auto_concat: bool = True
    shots: Optional[list[Any]] = None
    setup: Optional[dict[str, Any]] = None
    aspect: str = "16:9"
    quality: str = "736"
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
    seamless: bool = False
    brief: Optional[dict[str, Any]] = None
    post_pass: Optional[str] = None

    @field_validator("seed", "steps", mode="before")
    @classmethod
    def _coerce_int_steps(cls, v):
        if v is None or v == "" or (isinstance(v, float) and v != v):
            return -1
        try:
            return int(v)
        except Exception:
            return -1


def _film_plan_segment_jobs(plan: dict, seg_idx: int) -> list[dict]:
    batches = plan.get("segment_batches") or []
    if seg_idx < 0 or seg_idx >= len(batches):
        return []
    bid = str(batches[seg_idx] or "").strip()
    if not bid:
        return []
    out: list[dict] = []
    for j in _jobs:
        if str(j.get("cinema_batch") or "") == bid:
            out.append(j)
    out.sort(key=lambda x: int(x.get("batch_index") or x.get("shot_index") or 0))
    return out


def _segment_jobs_complete(jobs: list[dict]) -> bool:
    if not jobs:
        return False
    return all(str(j.get("status") or "").lower() == "done" for j in jobs)


def _film_plan_status(lib: dict) -> dict[str, Any]:
    plan = lib.get("film_plan")
    if not isinstance(plan, dict) or not plan.get("segments"):
        return {"ok": True, "plan": None}
    plan = cinema._clean_film_plan(plan)
    seg_count = int(plan.get("segment_count") or 0)
    cur = int(plan.get("current_segment") or 0)
    segment_complete = False
    all_complete = True
    segment_jobs: list[dict] = []
    if seg_count > 0 and cur < seg_count:
        segment_jobs = _film_plan_segment_jobs(plan, cur)
        if segment_jobs:
            segment_complete = _segment_jobs_complete(segment_jobs)
        else:
            segment_complete = False
            all_complete = False
    for i in range(seg_count):
        jobs = _film_plan_segment_jobs(plan, i)
        if not jobs or not _segment_jobs_complete(jobs):
            all_complete = False
            break
    return {
        "ok": True,
        "plan": plan,
        "segment_complete": segment_complete,
        "all_complete": all_complete and seg_count > 0,
        "segment_jobs": len(segment_jobs),
        "missing_stills": cinema.characters_missing_stills(lib),
    }


@app.get("/api/cinema/film-plan")
async def cinema_film_plan_get():
    lib = cinema.load()
    return _film_plan_status(lib)


@app.post("/api/cinema/produce-film")
async def cinema_produce_film(body: CinemaProduceFilmBody):
    """Segmented film production: queue one segment at a time with face lock + chain."""
    lib = cinema.load()
    if body.brief:
        cinema.ingest_from_director_brief(body.brief)
        lib = cinema.load()
    clip = int(body.clip_sec or lib.get("duration") or 5)
    if clip not in ALLOWED_DURATIONS:
        clip = 5
    seg_size = max(1, min(8, int(body.segment_size or 6)))
    total = max(clip, int(body.total_sec or 60))
    shots_raw = body.shots if body.shots else lib.get("shots") or []
    shots_clean = _brief_to_cinema_shots(
        [s if isinstance(s, dict) else {"text": str(s)} for s in shots_raw]
    )
    if not shots_clean:
        shots_clean = _brief_to_cinema_shots(
            [dict(s) for s in cinema.normalize_produce_shots(None, lib.get("script") or "")]
        )
    if not shots_clean:
        raise HTTPException(400, "Shot yok — önce senaryo / yönetmen planı ekle")
    plan = lib.get("film_plan")
    if body.advance:
        if not isinstance(plan, dict) or not plan.get("segments"):
            raise HTTPException(400, "Film planı yok — önce Film modu ile başlat")
        plan = cinema._clean_film_plan(plan)
    elif body.reset_plan or not isinstance(plan, dict) or not plan.get("segments"):
        plan = cinema.build_film_plan(
            shots_clean,
            total_sec=total,
            clip_sec=clip,
            segment_size=seg_size,
            auto_concat=bool(body.auto_concat),
        )
    else:
        plan = cinema._clean_film_plan(plan)
    seg_count = int(plan.get("segment_count") or 0)
    if seg_count < 1:
        raise HTTPException(400, "Segment yok")
    seg_idx = (
        int(body.segment_index)
        if body.segment_index is not None
        else int(plan.get("current_segment") or 0)
    )
    if body.advance:
        cur = int(plan.get("current_segment") or 0)
        jobs = _film_plan_segment_jobs(plan, cur)
        if jobs and not _segment_jobs_complete(jobs):
            raise HTTPException(400, "Mevcut segment henüz bitmedi")
        if cur < seg_count - 1:
            seg_idx = cur + 1
        else:
            seg_idx = cur
    seg_idx = max(0, min(seg_idx, seg_count - 1))
    segment = list((plan.get("segments") or [])[seg_idx])
    if not segment:
        raise HTTPException(400, f"Segment {seg_idx + 1} boş")
    append_chain = seg_idx > 0
    if append_chain and segment and str(segment[0].get("mode") or "") == "continue":
        first = dict(segment[0])
        txt = str(first.get("text") or "")
        if not txt.lower().startswith("continue directly"):
            first["text"] = "Continue directly from the previous shot.\n\n" + txt
        segment = [first, *segment[1:]]
    cp = CinemaProduceBody(
        shots=segment,
        setup=body.setup or lib.get("setup"),
        audio=lib.get("audio"),
        duration=clip,
        aspect=body.aspect,
        quality=normalize_quality(body.quality),
        steps=body.steps if body.steps > 0 else int(lib.get("steps") or 20),
        seed=body.seed,
        silent_audio=body.silent_audio,
        purpose=body.purpose,
        sampler=body.sampler,
        scheduler=body.scheduler,
        lora_id=body.lora_id,
        lora_name=body.lora_name,
        lora_strength=body.lora_strength,
        sage_attention=_sage_mode(body),
        link_continue=bool(body.link_continue),
        append_to_chain=append_chain,
        seamless=bool(body.seamless) and seg_count == 1 and len(segment) <= MULTISHOT_MAX_SHOTS,
        post_pass=body.post_pass,
    )
    queued = await cinema_produce(cp)
    batch_id = str(queued.get("cinema_batch") or "")
    job_ids = [str(j.get("id")) for j in (queued.get("jobs") or []) if j.get("id")]
    batches = list(plan.get("segment_batches") or [])
    seg_jobs = list(plan.get("segment_job_ids") or [])
    while len(batches) <= seg_idx:
        batches.append("")
    while len(seg_jobs) <= seg_idx:
        seg_jobs.append([])
    batches[seg_idx] = batch_id
    seg_jobs[seg_idx] = job_ids
    plan["segment_batches"] = batches
    plan["segment_job_ids"] = seg_jobs
    plan["current_segment"] = seg_idx
    plan["clip_sec"] = clip
    plan["total_sec"] = total
    plan["segment_size"] = seg_size
    plan["status"] = "producing"
    lib["film_plan"] = plan
    lib["duration"] = clip
    lib["shots"] = shots_clean
    cinema.save(lib)
    missing = cinema.characters_missing_stills(lib)
    st = _film_plan_status(cinema.load())
    return {
        **queued,
        "film_plan": plan,
        "segment_index": seg_idx,
        "segment_count": seg_count,
        "missing_stills": missing,
        "film_status": st,
    }


@app.post("/api/cinema/film-plan/concat")
async def cinema_film_plan_concat():
    """Join all segment clips in order (film plan job ids)."""
    lib = cinema.load()
    plan = lib.get("film_plan")
    if not isinstance(plan, dict):
        raise HTTPException(400, "Film planı yok")
    plan = cinema._clean_film_plan(plan)
    ids: list[str] = []
    for row in plan.get("segment_job_ids") or []:
        if isinstance(row, list):
            ids.extend([str(x) for x in row if str(x).strip()])
    if len(ids) < 2:
        raise HTTPException(400, "Birleştirmek için en az 2 klip gerekli")
    batch_id = str(uuid.uuid4())[:8]
    result = await clips_concat(ClipsConcatBody(job_ids=ids, batch_id=batch_id))
    plan["concat_done"] = True
    plan["final_batch_id"] = batch_id
    plan["status"] = "concat"
    lib["film_plan"] = plan
    audio = cinema._clean_audio(lib.get("audio"))
    audio["last_batch"] = batch_id
    lib["audio"] = audio
    cinema.save(lib)
    return {**result, "film_plan": plan}


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
    if body.job_ids and len(body.job_ids) >= 2:
        return await clips_concat(
            ClipsConcatBody(
                job_ids=body.job_ids,
                batch_id=body.batch_id,
            )
        )
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


@app.post("/api/clips/concat")
async def clips_concat(body: ClipsConcatBody):
    """Join user-selected finished clips (keeps each clip's audio)."""
    ids = [str(x).strip() for x in (body.job_ids or []) if str(x).strip()]
    if len(ids) < 2:
        raise HTTPException(400, "en az 2 klip seç")
    paths = await _paths_for_job_ids(ids)
    batch_id = (body.batch_id or "").strip()
    if not batch_id:
        for jid in ids:
            rec = _job_record(jid) or {}
            bid = str(rec.get("cinema_batch") or "").strip()
            if bid:
                batch_id = bid
                break
    if not batch_id:
        batch_id = str(uuid.uuid4())[:8]
    CINEMA_FINALS.mkdir(parents=True, exist_ok=True)
    out = CINEMA_FINALS / f"{batch_id}_final.mp4"
    try:
        concat_keep_audio(video_paths=paths, out_path=out)
    except Exception as e:
        raise HTTPException(500, str(e)[-400:])
    lib = cinema.load()
    audio = cinema._clean_audio(lib.get("audio"))
    audio["last_batch"] = batch_id
    if body.title:
        audio["last_merge_title"] = body.title.strip()
    lib["audio"] = audio
    cinema.save(lib)
    slog.info("clips concat ok", batch=batch_id, clips=len(paths), ids=len(ids))
    return {
        "ok": True,
        "batch_id": batch_id,
        "clips": len(paths),
        "job_ids": ids,
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


@app.get("/api/cinema/export-json")
async def cinema_export_json():
    return cinema.export_project_json()


@app.get("/api/cinema/json-template")
async def cinema_json_template(kind: str = ""):
    """Blank cinema template. kind=seamless → Kesintisiz (max 8); else 12×5s Film."""
    return cinema.project_json_template(kind or "")


class CinemaImportJsonBody(BaseModel):
    payload: Optional[Any] = None
    text: Optional[str] = None
    mode: str = "replace"
    save_to_library: bool = False
    new_film: bool = True
    generate_sheets: bool = False
    keep_stills: bool = True
    redo_characters: bool = False


@app.post("/api/cinema/import-json")
async def cinema_import_json(body: CinemaImportJsonBody):
    raw: Any = body.payload
    if raw is None and body.text:
        try:
            raw = json.loads(body.text)
        except Exception as e:
            raise HTTPException(400, f"JSON parse hata: {e}") from e
    if raw is None:
        raise HTTPException(400, "payload veya text gerekli")
    try:
        out = cinema.import_project_json(
            raw,
            mode=body.mode or "replace",
            save_to_library=bool(body.save_to_library),
            new_film=bool(body.new_film),
            keep_stills=bool(body.keep_stills),
            redo_characters=bool(body.redo_characters),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)[:400]) from e
    except Exception as e:
        raise HTTPException(400, str(e)[:400]) from e
    sheets: list[dict[str, Any]] = []
    if body.generate_sheets:
        try:
            sheets = await _queue_sheets_for_cinema(out.get("cinema") or {})
        except Exception as e:
            slog.warn("cinema import-json sheets", err=e)
        # Reload cinema after sheet upserts
        out["cinema"] = cinema.load()
        out["counts"] = {
            "characters": len(out["cinema"].get("characters") or []),
            "locations": len(out["cinema"].get("locations") or []),
            "creatures": len(out["cinema"].get("creatures") or []),
            "sections": len(out["cinema"].get("shots") or []),
        }
    out["sheets_queued"] = sheets
    slog.info(
        "cinema import-json",
        mode=out.get("mode"),
        counts=out.get("counts"),
        sheets=len(sheets),
    )
    return out


@app.post("/api/cinema/import")
async def cinema_import(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "boş dosya")
    name = (file.filename or "").lower()
    # JSON package (.json) — text cast + sections
    if name.endswith(".json") or (raw[:1] in (b"{", b"[") and b"PK" != raw[:2]):
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except Exception as e:
            raise HTTPException(400, f"JSON okunamadı: {e}") from e
        try:
            out = cinema.import_project_json(payload, mode="replace", new_film=True)
        except Exception as e:
            raise HTTPException(400, str(e)[:300]) from e
        out["cinema"] = cinema.load()
        out["sheets_queued"] = []
        return out
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
        raise HTTPException(400, "quality must be 352, 480, 608, 736, 768, or 1088 (aliases: 720, 1080)")
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
            "quality": normalize_quality(body.quality),
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
            "h3_models": h3_models.resolve("fl2va"),
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


# ─── Director LLM (Ollama / LM Studio / llama.cpp / cloud) ───────


class LlmSettingsBody(BaseModel):
    provider: Optional[str] = None
    ollama_base_url: Optional[str] = None
    lmstudio_base_url: Optional[str] = None
    llamacpp_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    nvidia_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    grok_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None
    ollama_model: Optional[str] = None
    lmstudio_model: Optional[str] = None
    llamacpp_model: Optional[str] = None
    openai_model: Optional[str] = None
    nvidia_model: Optional[str] = None
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


@app.get("/api/llm/models")
async def llm_models_list(provider: Optional[str] = None, base_url: Optional[str] = None):
    """Models for the given provider. Does not change the saved active provider."""
    data = await llm.list_models_for(provider, base_url=base_url)
    return data


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
    return {
        "ok": True,
        "loras": public_list(),
        "download": dict(_lora_dl_status),
    }


class H3ModelsBody(BaseModel):
    unet: Optional[str] = None
    unet_ref2va: Optional[str] = None
    clip: Optional[str] = None
    vae: Optional[str] = None
    audio_vae: Optional[str] = None
    reset: bool = False


@app.get("/api/h3-models")
async def h3_models_get():
    cat = h3_models.list_catalog()
    return {
        "ok": True,
        "selected": h3_models.load(),
        "defaults": cat["defaults"],
        "options": cat["options"],
        "folders": cat["folders"],
        "resolved": {
            "fl2va": h3_models.resolve("fl2va"),
            "ref2va": h3_models.resolve("ref2va"),
        },
    }


@app.post("/api/h3-models")
async def h3_models_set(body: H3ModelsBody):
    if body.reset:
        selected = h3_models.reset()
    else:
        selected = h3_models.save(body.model_dump(exclude={"reset"}))
    return {
        "ok": True,
        "selected": selected,
        "resolved": {
            "fl2va": h3_models.resolve("fl2va"),
            "ref2va": h3_models.resolve("ref2va"),
        },
    }


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
        "default_model_ok": bool(probe.get("default_model_ok", online)),
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
        "removed_characters": [],
        "removed_locations": [],
        "cinema_studio": False,
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
            brief["shots"] = force_continue_chain(cleaned, brief)
            brief["expectedShotCount"] = len(brief["shots"])
            if not brief.get("clipDurationSec"):
                brief["clipDurationSec"] = clip
            if not brief.get("totalDurationSec"):
                brief["totalDurationSec"] = clip * len(brief["shots"])
    sess["brief"] = brief
    sess["ready"] = bool(brief.get("shots"))
    cinema_out = None
    missing_stills: list[str] = []
    if body.apply_cinema and (brief.get("shots") or []):
        cinema_out = cinema.ingest_from_director_brief(brief)
        missing_stills = cinema.characters_missing_stills(cinema_out)
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
        "missing_stills": missing_stills,
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
            "nvidia": "NVIDIA chat reddedildi — build.nvidia.com’da yeni nvapi-… key oluştur; model (ör. minimaxai/minimax-m3) için erişim açık olmalı.",
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
        if isinstance(sess.get("brief"), dict):
            sess["brief"] = merge_session_directives(sess["brief"], sess)

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
            mid = "Senaryo kilitlendi — outline + SCENE’ler shot shot yazılıyor…"
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
                sess["brief"] = _scrub_brief_removed(brief, sess)
                sess["ready"] = True
                sess["messages"].append({"role": "assistant", "content": reply})
                _sessions[sid] = sess
                _save_sessions()
                return {
                    "session_id": sid,
                    "reply": reply,
                    "ready": True,
                    "brief": sess["brief"],
                    "shot_count": n,
                    "model": model,
                    "messages": sess["messages"],
                    "cinema": None,
                }

    # Ask model; empty answers are retried inside llm.chat, then local fallback
    sys = system_prompt()
    sys = (sys or "") + ui_lang_addendum(ui_lang)
    sys = (sys or "") + _prompt_optimize_instruction(body.prompt_rewriter_enabled)
    if plan_mode:
        sys = (sys or "") + "\n\n" + PLAN_MODE_ADDENDUM
        if ui_lang == "en":
            sys += "\nPlan-mode `reply` must be English (not Turkish)."
    if sess.get("cinema_studio"):
        sys = (sys or "") + "\n\n" + CINEMA_STUDIO_ADDENDUM
        cine_board = format_cinema_board(cinema.load(), full=plan_mode)
        if cine_board:
            sys = (sys or "") + "\n\n---\n" + cine_board
    board = format_brief_board(sess.get("brief"), full=plan_mode)
    # Outside cinema studio: never inject cinema.json (prevents deleted-card resurrection).
    # Inside cinema studio: board injected above.
    removed = _session_removed_names(sess)
    if removed:
        sys = (sys or "") + (
            "\n\nREMOVED CHARACTERS/LOCATIONS (do not reintroduce or name these): "
            + ", ".join(sorted(removed))
            + "."
        )
    if board:
        sys = (sys or "") + "\n\n---\n" + board
    history = [{"role": "system", "content": sys}] + sess["messages"][-24:]
    content = ""
    progress = _director_progress.get()
    try:
        content = await llm.chat(
            model,
            history,
            temperature=0.7,
            think=True,
            retries=2,
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
            or brief_cand.get("shotOutline")
            or parsed.get("ready") is True
            or str(parsed.get("phase") or "").lower() == "outline"
        ):
            should_finalize = True
        elif parsed.get("ready") is True:
            should_finalize = True
        elif str(parsed.get("phase") or "").lower() == "outline":
            should_finalize = True
    if not should_finalize and content and (
        (
            re.search(r'"shots"\s*:\s*\[', content)
            and re.search(r'"expectedShotCount"\s*:\s*\d+', content)
        )
        or re.search(r'"shotOutline"\s*:\s*\[', content)
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
        sess["brief"] = merge_session_directives(sess["brief"], sess)
        sess["brief"] = _scrub_brief_removed(apply_shot_patches(sess["brief"], parsed), sess)
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
                "İskelet alındı — önce shot başlıkları, sonra her SCENE tek tek yazılıyor…"
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
            sess["brief"] = _scrub_brief_removed(brief, sess)
            sess["ready"] = True
            if brief.get("purpose") == "music_video":
                sess["purpose"] = "music_video"
                sess["silent_audio"] = True
        elif parsed and parsed.get("reply"):
            reply = str(parsed["reply"])

    sess["messages"].append({"role": "assistant", "content": reply})
    sess["last_raw"] = content
    if isinstance(sess.get("brief"), dict):
        sess["brief"] = _scrub_brief_removed(sess["brief"], sess)
    _sessions[sid] = sess
    _save_sessions()
    out_brief = brief or sess.get("brief")
    if isinstance(out_brief, dict):
        out_brief = _scrub_brief_removed(out_brief, sess)
    out_shots = (out_brief or {}).get("shots") or []
    # Keep ready sticky after a finished brief so UI can show shot panel + Üretime al
    # while the user keeps chatting / revising.
    out_ready = bool(ready or (sess.get("ready") and out_shots))
    cinema_out = None
    # Do NOT auto-ingest director brief into cinema.json on every chat reply —
    # that resurrected deleted character cards via name-merge.
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
        # Still empty — derive N from duration/clip; never hardcode a magic shot count
        if not brief.get("expectedShotCount"):
            clip = int(brief.get("clipDurationSec") or 5)
            if clip not in ALLOWED_DURATIONS:
                clip = 5
            total = int(brief.get("totalDurationSec") or 0)
            if total <= 0:
                raise HTTPException(
                    400,
                    "Shot sayısı / süre yok — yönetmene toplam sn veya ‘N shot’ söyleyip tekrar dene",
                )
            brief["clipDurationSec"] = clip
            brief["totalDurationSec"] = total
            brief["expectedShotCount"] = expected_shot_count(total, clip)
        if body.expand:
            brief = await _expand_brief_shots(brief, model)
        else:
            brief = ensure_shot_count_sync(brief)
    if not brief.get("shots"):
        raise HTTPException(
            400,
            "Shot listesi boş — Ollama shot üretemedi. Yönetmene yaz: "
            "toplam süre + klip sn ile ready brief (ör. 30sn / 5sn → 6 shot).",
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


@app.post("/api/director/rewrite-shots")
async def director_rewrite_shots(body: DirectorRewriteShotsBody):
    """Rewrite each brief h3Prompt with LLM prompt optimize."""
    sess = _sessions.get(body.session_id)
    if not sess or not sess.get("brief"):
        raise HTTPException(400, "Brief yok — önce yönetmenle konuşmayı bitir")
    brief = _scrub_brief_removed(validate_brief(sess["brief"]), sess) or sess["brief"]
    shots = list(brief.get("shots") or [])
    if not shots:
        raise HTTPException(400, "Shot listesi boş")
    changed = 0
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        if shot.get("rewritten_at") and not body.force:
            continue
        raw = str(shot.get("h3Prompt") or shot.get("text") or "").strip()
        if len(raw) < 20:
            continue
        out = await _rewrite_scene_text(
            raw,
            enabled=True,
            context=f"director shot {i + 1}/{len(shots)}",
        )
        cleaned = (out or "").strip()
        if cleaned and cleaned != raw:
            shot["h3Prompt"] = cleaned
            shot["rewritten_at"] = time.time()
            changed += 1
        elif cleaned:
            shot["rewritten_at"] = time.time()
    brief["shots"] = shots
    sess["brief"] = _scrub_brief_removed(brief, sess) or brief
    _save_sessions()
    return {
        "ok": True,
        "brief": sess["brief"],
        "rewritten": changed,
        "shot_count": len(shots),
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
    brief = _scrub_brief_removed(brief, sess) or brief
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

    # Do NOT auto-rewrite every shot here — that blocks Üretime al for minutes
    # (one LLM call per shot). Use Plan → "Rewriter ile düzenle" explicitly.

    prompts = [s["h3Prompt"] for s in shots if isinstance(s, dict) and s.get("h3Prompt")]

    dur = int(brief.get("clipDurationSec") or shots[0].get("durationSec") or 5)
    if dur not in ALLOWED_DURATIONS:
        dur = 5
    aspect = (body.aspect or "").strip() or brief.get("aspect") or "16:9"
    quality = normalize_quality(body.quality or "736")
    silent = bool(brief.get("silentAudio")) or bool(sess.get("music_id"))
    steps = int(body.steps) if body.steps and int(body.steps) > 0 else 20
    sampler = (body.sampler or "res_multistep").strip() or "res_multistep"
    scheduler = (body.scheduler or "simple").strip() or "simple"
    steps, sampler, scheduler = _with_lora_preset(body, steps, sampler, scheduler)
    lora_bits = _lora_fields(body)

    applied = {
        "prompt": prompts[0] if prompts else "",
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

    # Normal Yönetmen (ana Sahne) → scene lane; Sinema stüdyosu → director lane
    commit_lane = "director" if sess.get("cinema_studio") else "scene"
    applied["lane"] = commit_lane

    queued = None
    missing_stills: list[str] = []
    if body.queue:
        if sess.get("cinema_studio"):
            cinema.ingest_from_director_brief(brief)
            lib = cinema.load()
            missing_stills = cinema.characters_missing_stills(lib)
            cp = CinemaProduceBody(
                shots=_brief_to_cinema_shots(shots),
                setup=lib.get("setup"),
                audio=lib.get("audio"),
                duration=dur,
                aspect=aspect,
                quality=quality,
                steps=steps,
                seed=-1,
                silent_audio=silent,
                purpose=brief.get("purpose"),
                sampler=sampler,
                scheduler=scheduler,
                lora_id=lora_bits.get("lora_id") or None,
                lora_name=lora_bits.get("lora_name") or None,
                lora_strength=lora_bits.get("lora_strength"),
                sage_attention=_sage_mode(body),
                link_continue=bool(link),
                seamless=False,
                post_pass=_normalize_post_pass(body.post_pass),
            )
            queued = await cinema_produce(cp)
        else:
            bb = BatchBody(
                prompts=prompts,
                modes=_brief_shot_modes(shots),
                duration=applied["duration"],
                aspect=aspect,
                quality=quality,
                steps=steps,
                sampler=sampler,
                scheduler=scheduler,
                link_continue=bool(link),
                append_to_chain=bool(link),
                face_lock=True,
                music_id=music_id,
                silent_audio=silent,
                purpose=brief.get("purpose"),
                lora_id=lora_bits.get("lora_id") or None,
                lora_name=lora_bits.get("lora_name") or None,
                lora_strength=lora_bits.get("lora_strength"),
                sage_attention=_sage_mode(body),
                lane=commit_lane,
                post_pass=_normalize_post_pass(body.post_pass),
            )
            queued = await batch(bb)

    return {
        "applied": applied,
        "brief": brief,
        "queued": queued,
        "missing_stills": missing_stills,
        "cinema_studio": bool(sess.get("cinema_studio")),
    }


# ─── Music (additive: upload → analyze → mux; does not alter generate core) ─


class MusicAnalyzeBody(BaseModel):
    music_id: str
    session_id: Optional[str] = None
    lyrics: Optional[str] = None
    lyric_timeline: Optional[list[dict[str, Any]]] = None
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
            "lyricTimeline": meta.get("lyricTimeline") or [],
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


@app.delete("/api/music/{music_id}")
async def music_delete(music_id: str):
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", music_id):
        raise HTTPException(400, "geçersiz şarkı kimliği")
    MUSIC.mkdir(parents=True, exist_ok=True)
    meta_path = MUSIC / f"{music_id}.json"
    if not meta_path.exists():
        raise HTTPException(404, "şarkı yok")
    removed = False
    paths = set(MUSIC.glob(f"{music_id}.*"))
    paths.add(MUSIC / f"{music_id}_final.mp4")
    for path in paths:
        if path.is_file():
            removed = _unlink_retry(path) or removed
    if not removed:
        raise HTTPException(404, "şarkı dosyası yok")
    slog.info("music deleted", id=music_id)
    return {"ok": True, "id": music_id}


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
    lyric_timeline: list[dict[str, Any]] = []
    for row in (body.lyric_timeline or [])[:120]:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()[:800]
        if not text:
            continue
        try:
            start = max(0.0, float(row.get("start") or 0))
            end = max(start, float(row.get("end") or start))
        except (TypeError, ValueError):
            continue
        lyric_timeline.append(
            {"start": round(start, 2), "end": round(end, 2), "text": text}
        )
    update_meta(
        MUSIC,
        body.music_id,
        lyrics=lyrics,
        concept=concept,
        lyricTimeline=lyric_timeline,
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
        lyric_timeline=lyric_timeline,
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
        # Repair queued Cinema jobs created by older builds too.  They may have
        # stored a location plate in `ref_images` as if it were a face reference.
        # For a continuation, rebuild that list from named character cards only;
        # the parent clip's final frame remains the actual continuation canvas.
        if job.get("cinema_batch") and mode == "face_continue":
            face_refs = cinema.bound_character_portraits(
                str(job.get("prompt") or ""), cinema.load()
            )
            if face_refs:
                job["ref_images"] = face_refs
                job["ref_role"] = "face"
            else:
                mode = "continue"
                job["mode"] = "continue"
                job["ref_images"] = []
                job["ref_role"] = None
        last_frame = job.get("last_frame_name")
        ref_videos = [str(x) for x in (job.get("ref_videos") or []) if x]
        lora_name, lora_strength = _lora_for_graph(job)
        models = job.get("h3_models") or h3_models.resolve(h3_models.graph_for_mode(mode))
        prompt_text = str(job.get("prompt") or "").strip()
        if job.get("continue_from") and first and "CONTINUATION LOCK" not in prompt_text:
            # The input frame is the physical continuation, but this explicit
            # instruction prevents a detailed new scene prompt from making H3
            # treat it as a fresh establishing shot.
            prompt_text = (
                "CONTINUATION LOCK: Begin on the exact final frame of the previous clip. "
                "Preserve its composition, camera position, character placement, lighting, "
                "and ongoing action at the first moment. Continue forward naturally from that "
                "instant; do not restart the scene, return to a reference still, or introduce "
                "a new establishing shot.\n\n"
                + prompt_text
            )
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
                models=models,
                filename_prefix=f"video/H3_Studio/{job['id'][:8]}",
                silent_audio=silent,
                lora_name=lora_name,
                lora_strength=lora_strength,
                sage_attention=_sage_mode(job),
                post_pass=_normalize_post_pass(job.get("post_pass")),
                chain_normalize=bool(job.get("chain_normalize", True)),
                voice_names=[str(x) for x in (job.get("voice_refs") or []) if x][:3],
            )
        elif mode in ("ref", "face", "v2v"):
            refs = [str(x) for x in (job.get("ref_images") or []) if x]
            if not refs and not ref_videos:
                raise RuntimeError("Referans görsel/video eksik")
            size_mode = job.get("ref_image_size") or ("max" if mode == "face" else "match")
            prompt = build_ref2va_prompt(
                text=prompt_text,
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
                models=models,
                filename_prefix=f"video/H3_Studio/{job['id'][:8]}",
                silent_audio=silent,
                include_video_audio=bool(job.get("include_video_audio", True)),
                lora_name=lora_name,
                lora_strength=lora_strength,
                sage_attention=_sage_mode(job),
                post_pass=_normalize_post_pass(job.get("post_pass")),
            )
        elif mode == "audio_continue":
            if not first or not job.get("continue_from"):
                raise RuntimeError("Sesli devam için önceki klibin son karesi yok")
            parent = _clip_record(job.get("continue_from"))
            if not parent:
                raise RuntimeError("Sesli devam kaynağı bulunamadı")
            source_video = await _ensure_job_video(parent)
            tail_path = REF_AUDIOS / f"h3_studio_{parent['id']}_tail.wav"
            extract_audio_tail(source_video, tail_path, seconds=5.0)
            audio_name = await comfy.upload_audio(tail_path, tail_path.name)
            text = (
                "<Picture 1> is the exact last frame of the previous clip: continue its "
                "composition, action, character, and camera naturally. <Audio 1> is the "
                "final audio from that clip: continue its ambience, music rhythm, and speaker "
                "character naturally, without replaying it verbatim.\n\n"
                + prompt_text
            )
            prompt = build_ref2va_prompt(
                text=text,
                ref_image_names=[first],
                ref_audio_names=[audio_name],
                width=w,
                height=h,
                length=length,
                seed=int(job["seed"]),
                steps=int(job["steps"]),
                sampler=job.get("sampler") or "res_multistep",
                scheduler=job.get("scheduler") or "simple",
                ref_image_size="match",
                models=models,
                filename_prefix=f"video/H3_Studio/{job['id'][:8]}",
                silent_audio=silent,
                lora_name=lora_name,
                lora_strength=lora_strength,
                sage_attention=_sage_mode(job),
                post_pass=_normalize_post_pass(job.get("post_pass")),
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
                prompt_text,
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
                models=models,
                filename_prefix=f"video/H3_Studio/{job['id'][:8]}",
                silent_audio=silent,
                lora_name=lora_name,
                lora_strength=lora_strength,
                sage_attention=_sage_mode(job),
                post_pass=_normalize_post_pass(job.get("post_pass")),
            )
            job["mode"] = "face_continue"
            job["ref_role"] = "face"
        else:
            prompt = build_t2v_prompt(
                text=prompt_text,
                width=w,
                height=h,
                length=length,
                seed=int(job["seed"]),
                steps=int(job["steps"]),
                sampler=job.get("sampler") or "res_multistep",
                scheduler=job.get("scheduler") or "simple",
                first_frame_name=first,
                last_frame_name=last_frame,
                models=models,
                filename_prefix=f"video/H3_Studio/{job['id'][:8]}",
                silent_audio=silent,
                lora_name=lora_name,
                lora_strength=lora_strength,
                sage_attention=_sage_mode(job),
                post_pass=_normalize_post_pass(job.get("post_pass")),
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
        # There is deliberately no wall-clock failure here. Full HD work may
        # wait in ComfyUI for an arbitrary time; only a real Comfy execution
        # error or a confirmed queue disappearance may mark this job failed.
        # The per-job Stop control remains the escape hatch for a true hang.
        tick = 0
        while True:
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
                    # Completion was reported but the SaveVideo node has not
                    # produced its file yet. Keep the last real sampler %;
                    # never manufacture a near-complete progress value.
                    job["progress_label"] = "çıktı hazırlanıyor"
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
                job["download_name"] = video_download_name(job, item_id=job["id"])
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
                try:
                    if job.get("sheet_asset_id"):
                        await _maybe_attach_sheet_still(job)
                except Exception as e:
                    slog.warn_job(job, "sheet still attach failed", err=e)
                await _notify_job(job, "done")
                try:
                    await _maybe_auto_mux_cinema(job)
                except Exception as e:
                    slog.warn("cinema auto mux skip", err=e)
                return

            # Not in history yet — soft progress by elapsed time
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
                # The sampler event is the only source of a real percentage.
                # When WS is quiet, preserve its last value and only update
                # descriptive text / elapsed time.
                if not ws_fresh:
                    step = job.get("comfy_step")
                    step_max = job.get("comfy_step_max")
                    if step is not None and step_max:
                        job["progress_label"] = (
                            f"örnekleme {int(step)}/{int(step_max)} · {clock}"
                        )
                    else:
                        job["progress_label"] = f"Comfy örnekliyor · {clock}"
                    _save_jobs_throttled(2.0)
            elif in_pending:
                absent_ticks = 0
                if not ws_fresh:
                    job["progress"] = 8
                    job["progress_label"] = f"Comfy kuyruğunda · {clock}"
                    job["progress_source"] = "queue"
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
                    job["progress"] = 12
                    job["progress_label"] = f"Comfy’nin işi alması bekleniyor · {clock}"
                    job["progress_source"] = "queue"
                    _save_jobs_throttled(2.0)
            await asyncio.sleep(1)
            tick += 1
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
        try:
            st = str(job.get("status") or "")
            if st in ("done", "error", "cancelled"):
                await _maybe_continue_pending_produce()
        except Exception as e:
            slog.warn("pending produce continue", err=e)


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
