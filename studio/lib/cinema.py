"""Cinema studio library: named character/location refs bound from prompt text."""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

STUDIO_ROOT = Path(__file__).resolve().parent.parent
CINEMA_FILE = STUDIO_ROOT / "data" / "cinema.json"
FILMS_DIR = STUDIO_ROOT / "data" / "films"
REFS_DIR = STUDIO_ROOT / "data" / "refs"
MUSIC_DIR = STUDIO_ROOT / "data" / "music"

SETUP_HINTS: dict[str, dict[str, str]] = {
    "look": {
        "feature": "cinematic feature-film look, composed wide and medium shots, motivated camera moves, theatrical blocking",
        "handheld": "intimate handheld documentary energy, micro-shake, follow-focus, lived-in framing",
        "documentary": "observational documentary cinematography, natural light bias, unobtrusive camera",
        "commercial": "high-end commercial cinematography, glossy product-grade lighting, precise art direction",
        "music_video": "music-video cinematic, rhythmic cutting energy, stylized lighting, bold graphic frames",
        "anamorphic": "anamorphic feature look, oval bokeh, horizontal flares, widescreen compression",
        "found_footage": "found-footage / camcorder aesthetic, raw diegetic camera, imperfect exposure",
        "noir": "classic noir cinematic, high-contrast shadows, wet streets, moral twilight",
        "golden": "golden-hour romantic cinematic, long warm rims, honeyed atmosphere",
        "retro_80s": "1980s cinematic, neon practicals, analog video-era energy, synth-night streets",
    },
    "camera": {
        "35mm": "shot on 35mm spherical cinema lenses, natural falloff, classic motion-picture texture",
        "anamorphic2x": "shot on 2x anamorphic cinema lenses, widescreen squeeze, oval highlights",
        "16mm": "shot on 16mm, grain, slightly softer contrast, documentary texture",
        "imax65": "large-format 65mm / IMAX scale, ultra-resolved landscapes, majestic framing",
        "steadicam": "smooth Steadicam / gimbal move, floating follow through space",
        "handheld": "handheld camera, operator breathing, reactive reframing",
        "drone": "aerial drone cinematography, sweeping establishing moves",
        "iphone": "shot on iPhone cinematic mode, contemporary phone-camera look",
        "gopro": "action-cam wide FOV, helmet/body-mounted energy",
        "crane": "crane / jib cinematic move, rising or descending reveal",
    },
    "palette": {
        "teal_orange": "teal-and-orange cinematic grade, complementary skin warmth against cool shadows",
        "noir": "high-contrast noir grade, crushed blacks, silver highlights",
        "warm": "warm amber grade, golden midtones, cozy tungsten bias",
        "cold": "cold steel-blue grade, desaturated shadows, winter air",
        "neon": "neon night palette, magenta/cyan practicals, wet-street reflections",
        "pastel": "soft pastel grade, lifted blacks, gentle contrast",
        "bleach": "bleach-bypass look, retained silver, harsh contrast, muted color",
        "golden_hour": "golden-hour color, long warm highlights, honeyed rims",
        "kodak": "Kodak motion-picture color, rich reds, creamy skin, filmic density",
        "rec709": "clean Rec.709 broadcast grade, neutral contrast, accurate color",
    },
    "lighting": {
        "natural": "natural available light, motivated windows and sky, no studio fill",
        "studio": "controlled studio lighting, soft key, shaped rim, clean negative fill",
        "neon": "neon and practical signage as key light, colored spill on faces",
        "candle": "candlelight / firelight, warm flicker, deep falloff",
        "overcast": "soft overcast daylight, low-contrast wrap, muted speculars",
        "hard_sun": "hard sunlight, sharp shadows, high-contrast noon look",
        "moonlight": "moonlight night exterior, cool key, deep underexposure",
        "volumetric": "volumetric god-rays / haze, visible beams through atmosphere",
        "practical": "practical-lit interior, lamps and screens as motivated sources",
    },
    "era": {
        "1920s": "1920s period production design, costumes and architecture of the era",
        "1950s": "1950s period look, mid-century wardrobe, cars, interiors",
        "1970s": "1970s period look, earth tones, analog texture, era-correct wardrobe",
        "1980s": "1980s period look, neon practicals, era wardrobe and set dressing",
        "1990s": "1990s period look, early-digital mixed with analog, era fashion",
        "2000s": "early-2000s period look, millennial fashion and interiors",
        "present": "present-day contemporary world, current fashion and technology",
        "near_future": "near-future world, plausible tech and architecture, not space opera",
        "medieval": "medieval period, pre-industrial materials, torch and daylight",
        "ancient": "ancient-world period production design, stone, bronze, linen",
    },
    "style": {
        "realistic": "photorealistic live-action cinematography, natural skin texture, realistic reflections, film grain",
        "anime": "high-end Japanese 2D anime cinematic, cel shading, sakuga motion, detailed painted backgrounds — not live-action",
        "disney": "Disney/Pixar-quality 3D character animation, appealing proportions, stylized (not photoreal) faces, studio lighting",
        "game": "AAA video-game cinematic (Unreal Engine 5), ray-traced lighting, game-character look",
        "cgi_3d": "premium 3D CGI animation, physically based rendering, cinematic studio lighting — not live-action",
        "comic": "stylized comic-book cinematic, inked linework, graphic color blocking",
        "illustration": "illustrated storybook cinematic, painterly 2D, storybook lighting",
        "oil_paint": "oil-painting cinematic, visible brushwork, classical canvas texture",
        "clay": "claymation / stop-motion look, tactile miniature sets",
        "found_footage": "found-footage live-action, diegetic camera, raw documentary capture",
    },
    "purpose": {
        "short_film": "narrative short-film pacing and blocking",
        "music_video": "music-video performance energy, rhythmic visual beats, lip-sync-ready framing",
        "ad": "advertising-spot pacing, product-clear hero shots",
        "trailer": "trailer pacing, hook shots, escalating energy",
        "social": "social-clip pacing, punchy short-form framing",
        "documentary": "documentary observational pacing",
        "intro": "title-sequence / intro pacing",
        "outro": "end-credits / outro pacing",
    },
}

_DEFAULT_SETUP: dict[str, str] = {
    "look": "auto",
    "camera": "auto",
    "palette": "auto",
    "lighting": "auto",
    "era": "auto",
    "purpose": "auto",
    "style": "auto",
}

_DEFAULT_AUDIO: dict[str, str] = {
    "mode": "film",
    "score_id": "",
    "score_name": "",
    "voice_lang": "Turkish",
    "last_batch": "",
}

MAX_ASSET_IMAGES = 5

_EMPTY: dict[str, Any] = {
    "film_id": "",
    "title": "",
    "script": "",
    "role_script": "",
    "shots": [],
    "setup": dict(_DEFAULT_SETUP),
    "audio": dict(_DEFAULT_AUDIO),
    "duration": 5,
    "quality": "720",
    "steps": 20,
    "seed": -1,
    "seed_lock": False,
    "characters": [],
    "locations": [],
    "updated_at": 0,
}


def _now() -> float:
    return time.time()


def _clean_audio(raw: Any) -> dict[str, str]:
    src = raw if isinstance(raw, dict) else {}
    mode = str(src.get("mode") or "film").strip().lower() or "film"
    if mode not in ("film", "silent"):
        mode = "film"
    out = {
        "mode": mode,
        "score_id": str(src.get("score_id") or "").strip(),
        "score_name": str(src.get("score_name") or "").strip(),
        "voice_lang": str(src.get("voice_lang") or "Turkish").strip() or "Turkish",
        "last_batch": str(src.get("last_batch") or "").strip(),
    }
    muxed = str(src.get("auto_muxed") or "").strip()
    if muxed:
        out["auto_muxed"] = muxed
    return out


def _clean_setup(raw: Any) -> dict[str, str]:
    src = raw if isinstance(raw, dict) else {}
    out = dict(_DEFAULT_SETUP)
    for key in _DEFAULT_SETUP:
        val = str(src.get(key) or "auto").strip().lower() or "auto"
        out[key] = val
    return out


def _clean_shot(item: Any, index: int = 0) -> dict[str, Any]:
    if isinstance(item, str):
        item = {"text": item}
    if not isinstance(item, dict):
        item = {}
    text = str(item.get("text") or item.get("prompt") or item.get("h3Prompt") or "").strip()
    mode = str(item.get("mode") or "").strip().lower()
    if mode in ("continue", "devam", "i2v", "last_frame"):
        mode = "continue"
    else:
        mode = "t2v"
    sid = str(item.get("id") or "").strip() or str(uuid.uuid4())
    return {"id": sid, "text": text, "mode": mode, "index": index}


def split_shots(script: str) -> list[str]:
    raw = (script or "").replace("\r\n", "\n").strip()
    if not raw:
        return []
    if re.search(r"\n\s*---\s*\n", raw):
        parts = re.split(r"\n\s*---\s*\n", raw)
    elif re.search(r"(?im)^\s*(shot|sahne|clip)\s*\d+\s*[:.\-]", raw):
        parts = re.split(r"(?im)(?=^\s*(?:shot|sahne|clip)\s*\d+\s*[:.\-])", raw)
    else:
        parts = re.split(r"\n\s*\n+", raw)
    out = []
    for p in parts:
        t = (p or "").strip()
        if t:
            out.append(t)
    return out


def _migrate_shots(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("shots")
    if isinstance(raw, list):
        cleaned = [_clean_shot(item, i) for i, item in enumerate(raw)]
        # Keep explicit shot rows (even empty drafts). Only fall back to script when
        # the shots key is missing — legacy saves stored script only.
        if cleaned or "shots" in data:
            return cleaned
    texts = split_shots(str(data.get("script") or ""))
    return [
        _clean_shot({"text": t, "mode": "t2v" if i == 0 else "continue"}, i)
        for i, t in enumerate(texts)
    ]


def load() -> dict[str, Any]:
    if not CINEMA_FILE.is_file():
        return json.loads(json.dumps(_EMPTY))
    try:
        data = json.loads(CINEMA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(_EMPTY))
    if not isinstance(data, dict):
        return json.loads(json.dumps(_EMPTY))
    data.setdefault("film_id", "")
    data.setdefault("title", "")
    data.setdefault("script", "")
    data.setdefault("role_script", "")
    data.setdefault("characters", [])
    data.setdefault("locations", [])
    if not isinstance(data["characters"], list):
        data["characters"] = []
    if not isinstance(data["locations"], list):
        data["locations"] = []
    data["setup"] = _clean_setup(data.get("setup"))
    data["audio"] = _clean_audio(data.get("audio"))
    data["shots"] = _migrate_shots(data)
    try:
        data["duration"] = int(data.get("duration") or 5)
    except (TypeError, ValueError):
        data["duration"] = 5
    data["quality"] = str(data.get("quality") or "720")
    try:
        data["steps"] = int(data.get("steps") or 20)
    except (TypeError, ValueError):
        data["steps"] = 20
    try:
        data["seed"] = int(data.get("seed") if data.get("seed") is not None else -1)
    except (TypeError, ValueError):
        data["seed"] = -1
    data["seed_lock"] = bool(data.get("seed_lock"))
    if not data.get("script"):
        data["script"] = "\n\n---\n\n".join(s["text"] for s in data["shots"] if s.get("text"))
    return data


def save(data: dict[str, Any]) -> dict[str, Any]:
    prev: dict[str, Any] = {}
    if CINEMA_FILE.is_file():
        try:
            raw_prev = json.loads(CINEMA_FILE.read_text(encoding="utf-8"))
            if isinstance(raw_prev, dict):
                prev = raw_prev
        except Exception:
            prev = {}
    if "shots" not in data:
        data = {**data, "shots": prev.get("shots") or []}
    if "setup" not in data:
        data = {**data, "setup": prev.get("setup")}
    if "audio" not in data:
        data = {**data, "audio": prev.get("audio")}
    for key in ("duration", "quality", "steps"):
        if key not in data and prev.get(key) is not None:
            data = {**data, key: prev.get(key)}
    shots = [_clean_shot(x, i) for i, x in enumerate(data.get("shots") or [])]
    script = str(data.get("script") or "").strip()
    if shots:
        script = "\n\n---\n\n".join(s["text"] for s in shots if s.get("text"))
    try:
        duration = int(data.get("duration") or 5)
    except (TypeError, ValueError):
        duration = 5
    try:
        steps = int(data.get("steps") or 20)
    except (TypeError, ValueError):
        steps = 20
    try:
        seed = int(
            data["seed"] if "seed" in data and data.get("seed") is not None else prev.get("seed", -1)
        )
    except (TypeError, ValueError):
        seed = -1
    seed_lock = bool(
        data["seed_lock"] if "seed_lock" in data else prev.get("seed_lock")
    )
    fid = str(data.get("film_id") or prev.get("film_id") or "").strip() or uuid.uuid4().hex[:10]
    out = {
        "film_id": fid,
        "title": str(data.get("title") or ""),
        "script": script,
        "role_script": str(
            data["role_script"] if "role_script" in data else (prev.get("role_script") or "")
        ),
        "shots": shots,
        "setup": _clean_setup(data.get("setup")),
        "audio": _clean_audio(data.get("audio")),
        "duration": duration,
        "quality": str(data.get("quality") or "720"),
        "steps": steps,
        "seed": seed,
        "seed_lock": seed_lock,
        "characters": [_clean_asset(x, "character") for x in (data.get("characters") or [])],
        "locations": [_clean_asset(x, "location") for x in (data.get("locations") or [])],
        "updated_at": _now(),
    }
    CINEMA_FILE.parent.mkdir(parents=True, exist_ok=True)
    CINEMA_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    _archive_film(out)
    return out


def _slug(name: str) -> str:
    s = (name or "").strip().lower()
    s = s.translate(
        str.maketrans(
            {
                "ç": "c",
                "ğ": "g",
                "ı": "i",
                "ö": "o",
                "ş": "s",
                "ü": "u",
                "â": "a",
                "î": "i",
                "û": "u",
            }
        )
    )
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s or "asset"


def _clean_images(item: dict[str, Any], name: str) -> list[dict[str, str]]:
    slug = _slug(name)
    raw = item.get("images")
    rows: list[dict[str, str]] = []
    if isinstance(raw, list) and raw:
        for x in raw:
            if isinstance(x, str) and x.strip():
                file = x.strip()
                rows.append({"file": file, "url": f"/api/refs/{file}"})
            elif isinstance(x, dict):
                file = str(x.get("file") or x.get("image") or "").strip()
                if not file:
                    continue
                url = str(x.get("url") or f"/api/refs/{file}").strip()
                rows.append({"file": file, "url": url})
    else:
        image = str(item.get("image") or "").strip()
        if image:
            rows.append(
                {
                    "file": image,
                    "url": str(item.get("url") or f"/api/refs/{image}"),
                }
            )
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, row in enumerate(rows[:MAX_ASSET_IMAGES]):
        file = row["file"]
        if file in seen:
            continue
        seen.add(file)
        out.append(
            {
                "name": f"{slug}{len(out) + 1}",
                "file": file,
                "url": row.get("url") or f"/api/refs/{file}",
            }
        )
        if len(out) >= MAX_ASSET_IMAGES:
            break
    return out


def _clean_asset(item: Any, kind: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    name = str(item.get("name") or "").strip()
    trigger = str(item.get("trigger") or "").strip()
    notes = str(item.get("notes") or item.get("description") or "").strip()
    aid = str(item.get("id") or "").strip() or str(uuid.uuid4())
    images = _clean_images(item, name)
    first = images[0] if images else {}
    out: dict[str, Any] = {
        "id": aid,
        "kind": kind,
        "name": name,
        "trigger": trigger or name,
        "images": images,
        "image": first.get("file") or "",
        "url": first.get("url") or "",
        "notes": notes,
        "voice": str(item.get("voice") or "").strip(),
    }
    if kind == "character":
        out["lora_id"] = str(item.get("lora_id") or "").strip()
        try:
            out["lora_strength"] = float(item.get("lora_strength") or 0.8)
        except (TypeError, ValueError):
            out["lora_strength"] = 0.8
    return out


def new_asset(kind: str, **fields: Any) -> dict[str, Any]:
    fields = dict(fields)
    fields["id"] = str(uuid.uuid4())
    return _clean_asset(fields, kind)


def upsert_asset(kind: str, asset: dict[str, Any]) -> dict[str, Any]:
    data = load()
    key = "characters" if kind == "character" else "locations"
    cleaned = _clean_asset(asset, kind)
    items = data[key]
    idx = next((i for i, x in enumerate(items) if x.get("id") == cleaned["id"]), -1)
    if idx >= 0:
        items[idx] = cleaned
    else:
        items.append(cleaned)
    data[key] = items
    save(data)
    return cleaned


def delete_asset(kind: str, asset_id: str) -> bool:
    data = load()
    key = "characters" if kind == "character" else "locations"
    before = len(data[key])
    data[key] = [x for x in data[key] if x.get("id") != asset_id]
    if len(data[key]) == before:
        return False
    save(data)
    return True


def _hit_token(text: str, value: str) -> bool:
    token = (value or "").strip()
    if not token or len(token) < 2:
        return False
    escaped = re.escape(token)
    pat = rf"(?i)(?:@{escaped}|(?<!\w){escaped}(?!\w))"
    return re.search(pat, text or "") is not None


def asset_mentioned(text: str, asset: dict[str, Any]) -> bool:
    if _hit_token(text, asset.get("trigger") or "") or _hit_token(text, asset.get("name") or ""):
        return True
    for im in asset.get("images") or []:
        if isinstance(im, dict) and _hit_token(text, im.get("name") or ""):
            return True
    return False


def mentioned_images(text: str, asset: dict[str, Any]) -> list[dict[str, str]]:
    imgs = [x for x in (asset.get("images") or []) if isinstance(x, dict) and x.get("file")]
    if not imgs:
        return []
    specific = [im for im in imgs if _hit_token(text, im.get("name") or "")]
    if specific:
        return specific
    if _hit_token(text, asset.get("trigger") or "") or _hit_token(text, asset.get("name") or ""):
        return imgs
    return []


def match_prompt(text: str, lib: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    lib = lib or load()
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for kind, key in (("character", "characters"), ("location", "locations")):
        for raw in lib.get(key) or []:
            item = _clean_asset(raw, kind)
            if not asset_mentioned(text, item):
                continue
            uid = item.get("id") or item.get("image") or item.get("name")
            if uid in seen:
                continue
            seen.add(uid)
            hits.append(item)
    return hits[:9]


def annotate_prompt(text: str, hits: list[dict[str, Any]], bound_images: Optional[list[dict[str, Any]]] = None) -> str:
    prompt = (text or "").strip()
    if not hits and not bound_images:
        return prompt
    lines = []
    pic_i = 0
    used_files: set[str] = set()
    image_rows = list(bound_images or [])
    if not image_rows:
        for h in hits:
            for im in h.get("images") or []:
                if isinstance(im, dict) and im.get("file"):
                    image_rows.append({**im, "asset": h})
    for row in image_rows:
        file = str(row.get("file") or "").strip()
        if not file or file in used_files:
            continue
        used_files.add(file)
        pic_i += 1
        h = row.get("asset") or {}
        label = h.get("name") or row.get("name") or "ref"
        call = row.get("name") or label
        notes = (h.get("notes") or "").strip()
        voice = (h.get("voice") or "").strip()
        note_bit = f" Description: {notes}." if notes else ""
        voice_bit = ""
        if h.get("kind") == "character" and voice:
            voice_bit = (
                f" SPEAKER LOCK: {label} always speaks with this identical voice — {voice}."
            )
        role = (
            "character identity / wardrobe lock"
            if h.get("kind") == "character"
            else "location / set lock"
        )
        lines.append(
            f"<Picture {pic_i}> is {call} — {role} for {label}.{note_bit}{voice_bit} "
            f"Call this still as {call}. Keep this look consistent whenever {label} appears."
        )
    for h in hits:
        label = h.get("name") or h.get("trigger") or "ref"
        notes = (h.get("notes") or "").strip()
        voice = (h.get("voice") or "").strip()
        has_img = any(
            (row.get("asset") or {}).get("id") == h.get("id")
            or (not row.get("asset") and row.get("file") in {im.get("file") for im in (h.get("images") or []) if isinstance(im, dict)})
            for row in image_rows
        )
        if has_img:
            continue
        note_bit = f" Description: {notes}." if notes else ""
        voice_bit = ""
        if h.get("kind") == "character" and voice:
            voice_bit = (
                f" SPEAKER LOCK: {label} always speaks with this identical voice — {voice}."
            )
        if voice_bit or notes:
            lines.append(f"{label}:{note_bit}{voice_bit} Same person every shot; do not recast.")
    preamble = "\n".join(lines)
    if preamble and preamble[:40] in prompt:
        return prompt
    return f"{preamble}\n\n{prompt}".strip()


def cast_voice_bible(lib: Optional[dict[str, Any]] = None) -> str:
    lib = lib or load()
    lines: list[str] = []
    for raw in lib.get("characters") or []:
        item = _clean_asset(raw, "character")
        name = (item.get("name") or "").strip()
        voice = (item.get("voice") or "").strip()
        if name and voice:
            lines.append(
                f"- {name}: identical speaking voice in every shot — {voice}. Never recast."
            )
    if not lines:
        return ""
    return (
        "CAST VOICE BIBLE — named speakers keep the same voice across the whole film; "
        "do not invent a new timbre between clips:\n" + "\n".join(lines)
    )


def film_audio_preamble(audio: Optional[dict[str, Any]] = None) -> str:
    audio = _clean_audio(audio or {})
    if audio.get("mode") == "silent":
        return ""
    lang = audio.get("voice_lang") or "Turkish"
    return (
        f"Spoken dialogue uses <d>[{lang}] line</d> tags with lipsync. "
        "The same named person must sound identical in every shot. "
        "No background music and no original score — underscore is mixed later."
    )


def bind_prompt(
    text: str,
    *,
    existing_refs: Optional[list[str]] = None,
    lora_id: str = "",
    lib: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    hits = match_prompt(text, lib)
    refs = [str(x) for x in (existing_refs or []) if x]
    bound_rows: list[dict[str, Any]] = []
    for h in hits:
        for im in mentioned_images(text, h):
            file = str(im.get("file") or "").strip()
            if not file:
                continue
            bound_rows.append({**im, "asset": h})
            if file not in refs:
                refs.append(file)
    refs = refs[:9]
    bound_rows = bound_rows[:9]
    chosen_lora = (lora_id or "").strip()
    chosen_strength = None
    if not chosen_lora:
        for h in hits:
            if h.get("kind") == "character" and h.get("lora_id"):
                chosen_lora = str(h["lora_id"])
                chosen_strength = h.get("lora_strength")
                break
    return {
        "prompt": annotate_prompt(text, hits, bound_rows) if hits else (text or "").strip(),
        "ref_images": refs,
        "hits": hits,
        "lora_id": chosen_lora,
        "lora_strength": chosen_strength,
        "has_character": any(h.get("kind") == "character" for h in hits),
        "has_location": any(h.get("kind") == "location" for h in hits),
    }


def setup_preamble(setup: Optional[dict[str, Any]] = None) -> str:
    setup = _clean_setup(setup or {})
    parts: list[str] = []
    for key in ("look", "camera", "palette", "lighting", "era", "style", "purpose"):
        val = setup.get(key) or "auto"
        if val in ("", "auto"):
            continue
        hint = (SETUP_HINTS.get(key) or {}).get(val) or ""
        if hint:
            parts.append(hint)
    blob = " ".join(parts).strip()
    if not blob:
        return ""
    return "Visual production lock: " + blob


def apply_look(text: str, look: str) -> str:
    look = (look or "").strip()
    text = (text or "").strip()
    if not look:
        return text
    if look[:48] in text:
        return text
    return f"{look}\n\n{text}".strip()


def normalize_produce_shots(
    raw_shots: Any = None,
    script: str = "",
    modes: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Return [{text, mode}] ready to queue. Empty texts are dropped."""
    items: list[Any] = list(raw_shots) if isinstance(raw_shots, list) else []
    parsed: list[dict[str, Any]] = []
    mode_list = [str(m or "").strip().lower() for m in (modes or [])]
    if items:
        all_strings = all(isinstance(x, str) for x in items)
        for i, item in enumerate(items):
            if isinstance(item, dict):
                shot = _clean_shot(item, i)
            else:
                fallback = "t2v" if i == 0 else "continue"
                if i < len(mode_list):
                    fallback = mode_list[i]
                elif not all_strings:
                    fallback = "t2v"
                shot = _clean_shot({"text": str(item or ""), "mode": fallback}, i)
            if shot.get("text"):
                parsed.append(shot)
        return parsed
    texts = split_shots(script or "")
    return [
        _clean_shot({"text": t, "mode": "t2v" if i == 0 else "continue"}, i)
        for i, t in enumerate(texts)
    ]


def _merge_named_assets(kind: str, existing: list[dict[str, Any]], incoming: list[Any]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in existing:
        item = _clean_asset(raw, kind)
        key = (item.get("name") or item.get("id") or "").strip().lower()
        if not key:
            key = item["id"]
        by_key[key] = item
        order.append(key)
    for raw in incoming or []:
        if isinstance(raw, str):
            raw = {"name": raw}
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        prev = by_key.get(key) or {}
        merged = {
            **prev,
            "name": name,
            "notes": str(raw.get("notes") or raw.get("description") or raw.get("card") or prev.get("notes") or ""),
            "voice": str(raw.get("voice") or prev.get("voice") or ""),
            "images": prev.get("images") or [],
            "image": prev.get("image") or "",
            "id": prev.get("id") or str(uuid.uuid4()),
        }
        if kind == "character":
            merged["lora_id"] = prev.get("lora_id") or ""
            merged["lora_strength"] = prev.get("lora_strength") or 0.8
        by_key[key] = _clean_asset(merged, kind)
        if key not in order:
            order.append(key)
    return [by_key[k] for k in order if k in by_key]


def ingest_from_director_brief(brief: dict[str, Any], role_script: str = "") -> dict[str, Any]:
    """Director FilmBrief → cinema characters / locations / shots (keep stills)."""
    chars: list[dict[str, Any]] = []
    for c in brief.get("characters") or []:
        if isinstance(c, dict):
            chars.append(
                {
                    "name": c.get("name") or c.get("role") or "",
                    "notes": c.get("notes") or c.get("card") or c.get("description") or "",
                    "voice": c.get("voice") or "",
                }
            )
        elif str(c).strip():
            chars.append({"name": str(c).strip(), "notes": "", "voice": ""})
    locs: list[dict[str, Any]] = []
    for loc in brief.get("locations") or []:
        if isinstance(loc, dict):
            locs.append(
                {
                    "name": loc.get("name") or "",
                    "notes": loc.get("notes") or loc.get("card") or loc.get("description") or "",
                }
            )
        elif str(loc).strip():
            locs.append({"name": str(loc).strip(), "notes": ""})
    shots: list[dict[str, Any]] = []
    for i, s in enumerate(brief.get("shots") or []):
        if isinstance(s, dict):
            text = str(
                s.get("h3Prompt") or s.get("text") or s.get("prompt") or s.get("action") or ""
            ).strip()
            link = str(s.get("linkToPrev") or "")
            mode = "t2v" if i == 0 or link == "standalone" else "continue"
        else:
            text = str(s).strip()
            mode = "t2v" if i == 0 else "continue"
        if text:
            shots.append({"text": text, "mode": mode})
    parsed = {
        "title": str(brief.get("title") or brief.get("logline") or "").strip(),
        "characters": chars,
        "locations": locs,
        "shots": shots,
    }
    return apply_ingest(parsed, role_script or str(brief.get("logline") or ""))


def apply_ingest(parsed: dict[str, Any], role_script: str) -> dict[str, Any]:
    """Merge LLM-parsed role text into the cinema library (keep existing stills)."""
    data = load()
    title = str(parsed.get("title") or parsed.get("logline") or data.get("title") or "").strip()
    chars = parsed.get("characters") or []
    locs = parsed.get("locations") or []
    shots_raw = parsed.get("shots") or []
    shots = normalize_produce_shots(shots_raw, "")
    if not shots:
        shots = normalize_produce_shots(None, role_script)
    data["title"] = title or data.get("title") or ""
    data["role_script"] = role_script
    data["characters"] = _merge_named_assets("character", data.get("characters") or [], chars)
    data["locations"] = _merge_named_assets("location", data.get("locations") or [], locs)
    data["shots"] = shots
    return save(data)


def _archive_film(out: dict[str, Any]) -> None:
    fid = str(out.get("film_id") or "").strip()
    if not fid:
        return
    FILMS_DIR.mkdir(parents=True, exist_ok=True)
    (FILMS_DIR / f"{fid}.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def list_films() -> list[dict[str, Any]]:
    active = load()
    aid = str(active.get("film_id") or "")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    FILMS_DIR.mkdir(parents=True, exist_ok=True)
    files = list(FILMS_DIR.glob("*.json"))
    if aid and not (FILMS_DIR / f"{aid}.json").is_file():
        _archive_film(active)
        files = list(FILMS_DIR.glob("*.json"))
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        fid = str(data.get("film_id") or p.stem)
        if fid in seen:
            continue
        seen.add(fid)
        rows.append(
            {
                "id": fid,
                "title": str(data.get("title") or "") or fid,
                "updated_at": data.get("updated_at") or 0,
                "active": fid == aid,
                "shots": len(data.get("shots") or []),
                "characters": len(data.get("characters") or []),
            }
        )
    if aid and aid not in seen:
        rows.append(
            {
                "id": aid,
                "title": str(active.get("title") or "") or aid,
                "updated_at": active.get("updated_at") or 0,
                "active": True,
                "shots": len(active.get("shots") or []),
                "characters": len(active.get("characters") or []),
            }
        )
    rows.sort(key=lambda x: float(x.get("updated_at") or 0), reverse=True)
    return rows


def new_film() -> dict[str, Any]:
    save(load())
    blank = json.loads(json.dumps(_EMPTY))
    blank["film_id"] = uuid.uuid4().hex[:10]
    return save(blank)


def switch_film(film_id: str) -> dict[str, Any]:
    fid = (film_id or "").strip()
    if not fid:
        raise ValueError("film yok")
    save(load())
    path = FILMS_DIR / f"{fid}.json"
    if not path.is_file():
        raise FileNotFoundError("film bulunamadı")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("film bozuk")
    data["film_id"] = fid
    CINEMA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return load()


def delete_film(film_id: str) -> dict[str, Any]:
    fid = (film_id or "").strip()
    active = load()
    path = FILMS_DIR / f"{fid}.json"
    if path.is_file():
        path.unlink()
    if str(active.get("film_id") or "") == fid:
        return new_film()
    return active


def shot_calls(text: str, lib: Optional[dict[str, Any]] = None) -> list[str]:
    bound = bind_prompt(text or "", lib=lib)
    names: list[str] = []
    seen: set[str] = set()
    for h in bound.get("hits") or []:
        for im in mentioned_images(text or "", h):
            n = str(im.get("name") or "").strip()
            if n and n not in seen:
                seen.add(n)
                names.append(n)
        label = str(h.get("name") or "").strip()
        if label and label not in seen:
            seen.add(label)
            names.append(label)
    return names


def produce_preview(lib: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    lib = lib or load()
    audio = _clean_audio(lib.get("audio"))
    silent = audio.get("mode") == "silent"
    look = setup_preamble(lib.get("setup") or {})
    head = "\n\n".join(
        x
        for x in (
            look,
            "" if silent else film_audio_preamble(audio),
            "" if silent else cast_voice_bible(lib),
        )
        if x
    )
    shots = []
    has_stills = False
    for s in lib.get("shots") or []:
        if not isinstance(s, dict) or not (s.get("text") or "").strip():
            continue
        text = apply_look(s["text"], head)
        bound = bind_prompt(text, lib=lib)
        refs = bound.get("ref_images") or []
        if refs:
            has_stills = True
        shots.append(
            {
                "id": s.get("id"),
                "mode": s.get("mode") or "t2v",
                "calls": shot_calls(s.get("text") or "", lib),
                "refs": len(refs),
                "prompt": bound.get("prompt") or text,
            }
        )
    return {
        "look": look,
        "head": head,
        "silent": silent,
        "has_stills": has_stills,
        "shots": shots,
    }


def _ref_files_in(lib: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("characters", "locations"):
        for raw in lib.get(key) or []:
            item = raw if isinstance(raw, dict) else {}
            for im in item.get("images") or []:
                if isinstance(im, dict) and im.get("file"):
                    names.append(str(im["file"]))
                elif isinstance(im, str) and im.strip():
                    names.append(im.strip())
            if item.get("image"):
                names.append(str(item["image"]))
    out: list[str] = []
    seen: set[str] = set()
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def export_zip() -> bytes:
    lib = load()
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("cinema.json", json.dumps(lib, indent=2, ensure_ascii=False))
        for name in _ref_files_in(lib):
            src = REFS_DIR / Path(name).name
            if src.is_file():
                zf.write(src, f"refs/{src.name}")
        score = str((_clean_audio(lib.get("audio"))).get("score_id") or "").strip()
        if score:
            for p in MUSIC_DIR.glob(f"{score}*"):
                if p.is_file() and p.suffix.lower() != ".json":
                    zf.write(p, f"music/{p.name}")
                    break
    return buf.getvalue()


def import_zip(raw: bytes) -> dict[str, Any]:
    save(load())
    buf = BytesIO(raw)
    with zipfile.ZipFile(buf, "r") as zf:
        names = zf.namelist()
        cine_name = next((n for n in names if n.endswith("cinema.json")), None)
        if not cine_name:
            raise ValueError("zip içinde cinema.json yok")
        data = json.loads(zf.read(cine_name).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("cinema.json bozuk")
        REFS_DIR.mkdir(parents=True, exist_ok=True)
        for n in names:
            if not n.startswith("refs/") or n.endswith("/"):
                continue
            dest = REFS_DIR / Path(n).name
            with zf.open(n) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
        MUSIC_DIR.mkdir(parents=True, exist_ok=True)
        for n in names:
            if not n.startswith("music/") or n.endswith("/"):
                continue
            dest = MUSIC_DIR / Path(n).name
            with zf.open(n) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
    data["film_id"] = uuid.uuid4().hex[:10]
    return save(data)
