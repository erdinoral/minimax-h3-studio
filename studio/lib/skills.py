"""Portable skill packs derived from MiniMax Design Hub skills.

Hub pipelines (Midjourney, canvas, image_N) are not executed. Packs only supply
cinema setup bundles and H3 craft / avoid lines that affect prompt quality.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"
CATALOG_PATH = SKILLS_ROOT / "catalog.json"
GENRE_CRAFT_PATH = SKILLS_ROOT / "packs" / "genre_craft.json"


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    if not CATALOG_PATH.is_file():
        return {"packs": []}
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"packs": []}
    return data if isinstance(data, dict) else {"packs": []}


@lru_cache(maxsize=1)
def load_genre_craft() -> dict[str, dict[str, Any]]:
    if not GENRE_CRAFT_PATH.is_file():
        return {}
    try:
        data = json.loads(GENRE_CRAFT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def genre_pack(look_id: str) -> dict[str, Any]:
    look = (look_id or "").strip()
    craft = load_genre_craft()
    pack = craft.get(look)
    return pack if isinstance(pack, dict) else {}


def look_setup_bundle(look_id: str) -> dict[str, str]:
    pack = genre_pack(look_id)
    setup = pack.get("setup") if isinstance(pack.get("setup"), dict) else {}
    out = {k: str(v).strip() for k, v in setup.items() if str(v).strip()}
    return out


def look_craft_line(look_id: str) -> str:
    pack = genre_pack(look_id)
    craft = str(pack.get("craft") or "").strip()
    avoid = str(pack.get("avoid") or "").strip()
    bits = []
    if craft:
        bits.append(craft)
    if avoid:
        bits.append("Avoid: " + avoid)
    return " ".join(bits).strip()


def look_visual_style_default(look_id: str) -> str:
    pack = genre_pack(look_id)
    return str(pack.get("visual_style") or "").strip()


def look_soundscape_default(look_id: str) -> str:
    pack = genre_pack(look_id)
    return str(pack.get("soundscape") or "").strip()


def look_music_default(look_id: str) -> str:
    pack = genre_pack(look_id)
    raw = str(pack.get("music") or "").strip()
    return raw or "N/A"


def enrich_structured_from_look(
    structured: Optional[dict[str, Any]],
    look_id: str,
) -> dict[str, str]:
    """Fill empty author fields from genre pack defaults (never overwrite user text)."""
    src = structured if isinstance(structured, dict) else {}
    keys = (
        "title",
        "location",
        "character",
        "action",
        "dialogue",
        "dialogue_lang",
        "camera",
        "visual_style",
        "audio",
        "music",
        "important",
    )
    s = {k: str(src.get(k) or "").strip() for k in keys}
    pack = genre_pack(look_id)
    if not pack:
        return s
    if not s.get("visual_style"):
        vs = look_visual_style_default(look_id)
        if vs:
            s["visual_style"] = vs
    if not s.get("important"):
        avoid = str(pack.get("avoid") or "").strip()
        bias = str(pack.get("camera_bias") or "").strip()
        bits = [b for b in (bias, ("Avoid: " + avoid) if avoid else "") if b]
        if bits:
            s["important"] = " ".join(bits)
    if not s.get("audio"):
        audio = look_soundscape_default(look_id)
        if audio:
            s["audio"] = audio
    if not s.get("music"):
        s["music"] = look_music_default(look_id)
    if not s.get("camera"):
        bias = str(pack.get("camera_bias") or "").strip()
        if bias:
            s["camera"] = bias
    return s


def catalog_public() -> dict[str, Any]:
    cat = load_catalog()
    packs = []
    for p in cat.get("packs") or []:
        if not isinstance(p, dict):
            continue
        look = str(p.get("look") or "").strip()
        craft = genre_pack(look) if look else {}
        packs.append(
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "look": look or None,
                "role": p.get("role"),
                "vendor": p.get("vendor") or [],
                "has_craft": bool(craft),
            }
        )
    return {"version": cat.get("version", 1), "packs": packs}
