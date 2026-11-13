"""Settings downloads: one sequential, resumable queue for base packs, optional engines and catalog LoRAs."""
from __future__ import annotations
import asyncio
import re
import shutil
from pathlib import Path
import httpx
from . import h3_models, loras, lora_access, optional_models

GB = 1000 ** 3


def _hf(repo, path):
    return f"https://huggingface.co/{repo}/resolve/main/{path}?download=true"


H3 = "Comfy-Org/MiniMax-H3"
H3_IMAGE = "Comfy-Org/MiniMax-H3-Image"

PACKS = [
    {"id": "shared", "group": "base", "bytes": int(21.5 * GB),
     "label": ("Ortak metin kodlayıcı + VAE'ler", "Shared text encoder + VAEs"),
     "note": ("Tüm video ve görsel modları için gerekli.", "Required by every video and image mode."),
     "files": [("text_encoders", "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", _hf(H3, "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors")),
               ("vae", "minimax_h3_video_vae_fp16.safetensors", _hf(H3, "vae/minimax_h3_video_vae_fp16.safetensors")),
               ("vae", "minimax_h3_audio_vae_fp32.safetensors", _hf(H3, "vae/minimax_h3_audio_vae_fp32.safetensors"))]},
    {"id": "fl2va", "group": "base", "bytes": int(21.0 * GB),
     "label": ("FL2VA · metin / ilk-son kare", "FL2VA · text / first-last frame"),
     "note": ("T2V, I2V ve devam klipleri.", "T2V, I2V and continuation clips."),
     "files": [("diffusion_models", "minimax_h3_fl2va_pruned_int8_convrot.safetensors", _hf(H3, "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors"))]},
    {"id": "ref2va", "group": "base", "bytes": int(21.0 * GB),
     "label": ("Ref2VA · referanslı video", "Ref2VA · reference video"),
     "note": ("Karakter / referans görselli video.", "Character and reference-image video."),
     "files": [("diffusion_models", "minimax_h3_ref2va_pruned_int8_convrot.safetensors", _hf(H3, "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors"))]},
    {"id": "h3-image", "group": "base", "bytes": int(22.2 * GB),
     "label": ("H3-Image · fotoğraf", "H3-Image · stills"),
     "note": ("Görsel üretimi ve karakter sayfaları.", "Image generation and character sheets."),
     "files": [("diffusion_models", "minimax_h3_image_pruned_int8_convrot.safetensors", _hf(H3_IMAGE, "diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors")),
               ("vae", "minimax_h3_image_vae_fp16.safetensors", _hf(H3_IMAGE, "vae/minimax_h3_image_vae_fp16.safetensors"))]},
    {"id": "encoder-int8", "group": "optional", "bytes": int(27.1 * GB),
     "label": ("INT8 metin kodlayıcı", "INT8 text encoder"),
     "note": ("NVFP4 desteklemeyen GPU'lar için alternatif.", "Alternative for GPUs without NVFP4 support."),
     "files": [("text_encoders", "qwen3vl_32b_minimax_h3_int8_convrot.safetensors", _hf(H3, "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors"))]},
]

_SIZE = re.compile(r"([\d.]+)\s*(GiB|GB|MiB|MB|KiB|KB)", re.I)
_UNITS = {"gib": 1024 ** 3, "gb": GB, "mib": 1024 ** 2, "mb": 1000 ** 2, "kib": 1024, "kb": 1000}

_queue: list[str] = []
_errors: dict[str, str] = {}
_current: dict = {"id": None, "done": 0, "phase": ""}
_runner = None
_cancel = False


class Cancelled(Exception):
    pass


def _hint_bytes(text):
    match = _SIZE.search(text or "")
    return int(float(match.group(1)) * _UNITS[match.group(2).lower()]) if match else 0


def _root():
    return h3_models.MODELS_ROOT


def _lora_folder(spec):
    return loras.LORAS_DIR.parent / spec["storage_folder"] if spec.get("storage_folder") else loras.LORAS_DIR


def _items():
    items = {}
    for pack in PACKS:
        items[pack["id"]] = {**pack, "kind": "pack"}
    single = optional_models.SINGULARITY
    items[single["id"]] = {"id": single["id"], "group": "optional", "kind": "singularity", "bytes": single["bytes"],
        "label": ("Singularity · Pruned INT8 (deneysel)", single["label"]),
        "note": ("Alternatif FL2VA/Ref2VA motoru.", "Alternative FL2VA/Ref2VA engine.")}
    for spec in loras.CATALOG:
        if not spec.get("url"):
            continue
        items["lora:" + spec["id"]] = {"id": "lora:" + spec["id"], "group": "lora", "kind": "lora", "spec": spec,
            "bytes": spec.get("expected_bytes") or _hint_bytes(spec.get("size_hint")),
            "label": (spec["label"], spec["label"]), "note": ("", ""),
            "needs_key": "civitai.com" in spec["url"]}
    return items


def _installed(item):
    if item["kind"] == "pack":
        return all((_root() / folder / name).is_file() for folder, name, _ in item["files"])
    if item["kind"] == "singularity":
        return bool(optional_models.installed())
    return loras.spec_ready(item["spec"])


def _files_on_disk(item):
    if item["kind"] == "pack":
        paths = [_root() / folder / name for folder, name, _ in item["files"]]
    elif item["kind"] == "singularity":
        paths = [optional_models.installed()] if optional_models.installed() else []
    else:
        folder = _lora_folder(item["spec"])
        paths = [folder / name for name in loras.candidates(item["spec"])]
    return [path for path in paths if path and path.is_file()]


def busy():
    return bool(_runner and not _runner.done())


def catalog():
    has_key = bool(lora_access.key())
    rows = []
    for item in _items().values():
        installed = _installed(item)
        active = _current["id"] == item["id"]
        on_disk = sum(path.stat().st_size for path in _files_on_disk(item)) if installed else 0
        rows.append({"id": item["id"], "group": item["group"],
            "label_tr": item["label"][0], "label_en": item["label"][1],
            "note_tr": item["note"][0], "note_en": item["note"][1],
            "bytes": on_disk or item["bytes"], "installed": installed,
            "queued": item["id"] in _queue and not active, "active": active,
            "phase": _current["phase"] if active else "",
            "progress": round(min(99.0, 100 * _current["done"] / item["bytes"]), 1) if active and item["bytes"] else 0,
            "error": _errors.get(item["id"]),
            "needs_key": bool(item.get("needs_key")) and not has_key})
    root = _root()
    while not root.exists() and root.parent != root:
        root = root.parent
    missing = [row for row in rows if not row["installed"] and not row["needs_key"]]
    return {"items": rows, "busy": busy(), "current": _current["id"], "queue": list(_queue),
        "missing": len(missing), "missing_bytes": sum(row["bytes"] for row in missing),
        "free_bytes": shutil.disk_usage(root).free}


def enqueue(ids):
    global _runner
    items = _items()
    unknown = [item_id for item_id in ids if item_id not in items]
    if unknown:
        raise KeyError(unknown[0])
    for item_id in ids:
        if item_id not in _queue and not _installed(items[item_id]):
            _errors.pop(item_id, None)
            _queue.append(item_id)
    if _queue and not busy():
        _runner = asyncio.create_task(_run())
    return catalog()


def enqueue_all():
    has_key = bool(lora_access.key())
    return enqueue([item_id for item_id, item in _items().items()
        if not _installed(item) and (has_key or not item.get("needs_key"))])


def cancel():
    global _cancel
    if busy():
        _cancel = True
        _queue[1:] = []
        if _current["id"] == optional_models.SINGULARITY["id"]:
            optional_models.cancel()
    return catalog()


async def _run():
    global _cancel
    try:
        while _queue and not _cancel:
            item_id = _queue[0]
            _current.update(id=item_id, done=0, phase="downloading")
            item = _items().get(item_id)
            try:
                if item and not _installed(item):
                    await _install(item)
            except Cancelled:
                pass
            except Exception as exc:
                _errors[item_id] = str(exc)[-300:] or type(exc).__name__
            finally:
                if _queue and _queue[0] == item_id:
                    _queue.pop(0)
    finally:
        _queue.clear()
        _current.update(id=None, done=0, phase="")
        _cancel = False


async def _install(item):
    if item["kind"] == "singularity":
        await optional_models.start(item["id"])
        while True:
            state = optional_models.catalog()[0]
            _current.update(done=state["downloaded"], phase=state["phase"] or "downloading")
            if not state["busy"]:
                break
            if _cancel:
                optional_models.cancel()
                raise Cancelled()
            await asyncio.sleep(1)
        if _cancel:
            raise Cancelled()
        if not optional_models.installed():
            raise ValueError(state.get("error") or "Download failed")
        return
    if item["kind"] == "pack":
        files = [(_root() / folder / name, url, None) for folder, name, url in item["files"]]
    else:
        spec = item["spec"]
        files = [(_lora_folder(spec) / spec["file"], spec["url"], spec)]
    finished = 0
    for target, url, spec in files:
        if target.is_file():
            finished += target.stat().st_size
            continue
        await _fetch(target, url, spec, finished)
        finished += target.stat().st_size


async def _fetch(target: Path, url, spec, finished):
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    expected = (spec or {}).get("expected_bytes") or 0
    offset = partial.stat().st_size if partial.is_file() else 0
    if expected and offset >= expected:
        partial.unlink()
        offset = 0
    headers = lora_access.request_headers(url)
    if offset:
        headers["Range"] = f"bytes={offset}-"
    async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(60, connect=30)) as client:
        async with client.stream("GET", url, headers=headers) as response:
            if response.status_code == 416:
                partial.unlink(missing_ok=True)
                raise ValueError("Resume range rejected; partial file removed, try again")
            if response.status_code in (401, 403):
                raise ValueError("Access denied (Civitai key required)" if "civitai.com" in url else f"HTTP {response.status_code}")
            response.raise_for_status()
            resumed = bool(offset) and response.status_code == 206
            received = offset if resumed else 0
            length = int(response.headers.get("content-length") or 0)
            total = received + length if length else expected
            free = shutil.disk_usage(target.parent).free
            if total and free < total - received + 1024 ** 3:
                raise ValueError(f"Not enough disk space: need {(total - received) / GB:.1f} GB, free {free / GB:.1f} GB")
            with partial.open("ab" if resumed else "wb") as stream:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    if _cancel:
                        raise Cancelled()
                    stream.write(chunk)
                    received += len(chunk)
                    _current["done"] = finished + received
    if total and partial.stat().st_size != total:
        raise ValueError("Download size mismatch")
    _current["phase"] = "verifying"
    if spec:
        await asyncio.to_thread(loras.verify_download, partial, spec)
    partial.replace(target)
    _current["phase"] = "downloading"


def remove(item_id, protected=frozenset()):
    item = _items().get(item_id)
    if not item:
        raise KeyError(item_id)
    if _current["id"] == item_id or item_id in _queue:
        raise ValueError("storage.busy")
    paths = _files_on_disk(item)
    if not paths:
        raise FileNotFoundError(item_id)
    if any(path.name in protected for path in paths):
        raise ValueError("storage.protected")
    engine = optional_models.engine_status()["active"] if item["kind"] == "singularity" else ""
    freed = 0
    for path in paths:
        size = path.stat().st_size
        path.unlink()
        freed += size
    if engine == "singularity":
        optional_models.select_engine("minimax")
    return {"id": item_id, "freed": freed}
