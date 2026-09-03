"""H3 base model pickers (UNET / CLIP / VAE) — Advanced Settings only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from lib.comfy import DEFAULT_MODELS, REF2VA_MODELS

STUDIO_ROOT = Path(__file__).resolve().parent.parent
MODELS_ROOT = STUDIO_ROOT.parent / "app" / "models"
SETTINGS_PATH = STUDIO_ROOT / "data" / "h3_models.json"

# Empty string = use Studio default for that slot
SLOT_KEYS = ("unet", "unet_ref2va", "clip", "vae", "audio_vae")

FOLDER_MAP: dict[str, tuple[str, ...]] = {
    "unet": ("diffusion_models", "unet"),
    "unet_ref2va": ("diffusion_models", "unet"),
    "clip": ("text_encoders", "clip"),
    "vae": ("vae",),
    "audio_vae": ("vae",),
}

HINT_RE: dict[str, tuple[str, ...]] = {
    "unet": ("fl2va", "h3", "minimax"),
    "unet_ref2va": ("ref2va", "h3", "minimax"),
    "clip": ("qwen", "minimax", "h3"),
    "vae": ("video", "h3", "minimax"),
    "audio_vae": ("audio", "h3", "minimax"),
}


def defaults() -> dict[str, str]:
    return {
        "unet": DEFAULT_MODELS["unet"],
        "unet_ref2va": REF2VA_MODELS["unet"],
        "clip": DEFAULT_MODELS["clip"],
        "vae": DEFAULT_MODELS["vae"],
        "audio_vae": DEFAULT_MODELS["audio_vae"],
    }


def _list_dir(*rel: str) -> list[str]:
    names: set[str] = set()
    for r in rel:
        folder = MODELS_ROOT / r
        if not folder.is_dir():
            continue
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() in (".safetensors", ".sft", ".ckpt", ".pt", ".pth", ".gguf"):
                names.add(p.name)
    return sorted(names, key=str.lower)


def _rank(name: str, hints: tuple[str, ...]) -> tuple[int, str]:
    low = name.lower()
    for i, h in enumerate(hints):
        if h in low:
            return (i, low)
    return (len(hints) + 1, low)


def list_catalog() -> dict[str, Any]:
    out: dict[str, Any] = {"defaults": defaults(), "options": {}, "folders": {}}
    for key in SLOT_KEYS:
        folders = FOLDER_MAP[key]
        files = _list_dir(*folders)
        hints = HINT_RE.get(key, ())
        files = sorted(files, key=lambda n: _rank(n, hints))
        out["options"][key] = files
        out["folders"][key] = list(folders)
    return out


def load() -> dict[str, str]:
    raw: dict[str, Any] = {}
    if SETTINGS_PATH.is_file():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                raw = data
        except Exception:
            raw = {}
    cleaned: dict[str, str] = {}
    for k in SLOT_KEYS:
        v = str(raw.get(k) or "").strip()
        cleaned[k] = v
    return cleaned


def save(patch: dict[str, Any]) -> dict[str, str]:
    cur = load()
    for k in SLOT_KEYS:
        if k not in patch:
            continue
        v = patch.get(k)
        if v is None:
            cur[k] = ""
            continue
        s = str(v).strip()
        # Only keep filenames that exist (or empty = default)
        if not s:
            cur[k] = ""
            continue
        opts = set(_list_dir(*FOLDER_MAP[k]))
        cur[k] = s if s in opts else ""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(cur, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return cur


def reset() -> dict[str, str]:
    empty = {k: "" for k in SLOT_KEYS}
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(empty, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return empty


def resolve(graph: str = "fl2va", overrides: Optional[dict[str, Any]] = None) -> dict[str, str]:
    """Return Comfy loader names for this graph (unet/clip/vae/audio_vae)."""
    g = (graph or "fl2va").strip().lower()
    base = dict(REF2VA_MODELS if g in ("ref2va", "ref", "face", "v2v", "face_continue") else DEFAULT_MODELS)
    saved = load()
    if overrides:
        for k, v in overrides.items():
            if k in SLOT_KEYS and v:
                saved[k] = str(v).strip()

    if saved.get("clip"):
        base["clip"] = saved["clip"]
    if saved.get("vae"):
        base["vae"] = saved["vae"]
    if saved.get("audio_vae"):
        base["audio_vae"] = saved["audio_vae"]

    if g in ("ref2va", "ref", "face", "v2v", "face_continue"):
        if saved.get("unet_ref2va"):
            base["unet"] = saved["unet_ref2va"]
    else:
        if saved.get("unet"):
            base["unet"] = saved["unet"]
    return base


def graph_for_mode(mode: Optional[str]) -> str:
    m = (mode or "t2v").strip().lower()
    if m in ("ref", "face", "v2v", "face_continue"):
        return "ref2va"
    if m == "multishot":
        return "fl2va"
    return "fl2va"
