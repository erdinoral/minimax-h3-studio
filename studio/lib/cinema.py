"""Cinema studio library: named character/location refs bound from prompt text."""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Optional

STUDIO_ROOT = Path(__file__).resolve().parent.parent
CINEMA_FILE = STUDIO_ROOT / "data" / "cinema.json"

SETUP_HINTS: dict[str, dict[str, str]] = {
    "look": {
        "feature": "cinematic feature-film look, composed wide and medium shots, motivated camera moves, theatrical blocking",
        "handheld": "intimate handheld documentary energy, micro-shake, follow-focus, lived-in framing",
        "documentary": "observational documentary cinematography, natural light bias, unobtrusive camera",
        "commercial": "high-end commercial cinematography, glossy product-grade lighting, precise art direction",
        "music_video": "music-video cinematic, rhythmic cutting energy, stylized lighting, bold graphic frames",
        "anamorphic": "anamorphic feature look, oval bokeh, horizontal flares, widescreen compression",
        "found_footage": "found-footage / camcorder aesthetic, raw diegetic camera, imperfect exposure",
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

_EMPTY: dict[str, Any] = {
    "title": "",
    "script": "",
    "shots": [],
    "setup": dict(_DEFAULT_SETUP),
    "audio": dict(_DEFAULT_AUDIO),
    "duration": 5,
    "quality": "720",
    "steps": 20,
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
    return {
        "mode": mode,
        "score_id": str(src.get("score_id") or "").strip(),
        "score_name": str(src.get("score_name") or "").strip(),
        "voice_lang": str(src.get("voice_lang") or "Turkish").strip() or "Turkish",
        "last_batch": str(src.get("last_batch") or "").strip(),
    }


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
    text = str(item.get("text") or item.get("prompt") or "").strip()
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
    cleaned: list[dict[str, Any]] = []
    if isinstance(raw, list) and raw:
        for i, item in enumerate(raw):
            shot = _clean_shot(item, i)
            cleaned.append(shot)
        if any(s.get("text") for s in cleaned):
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
    data.setdefault("title", "")
    data.setdefault("script", "")
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
    out = {
        "title": str(data.get("title") or ""),
        "script": script,
        "shots": shots,
        "setup": _clean_setup(data.get("setup")),
        "audio": _clean_audio(data.get("audio")),
        "duration": duration,
        "quality": str(data.get("quality") or "720"),
        "steps": steps,
        "characters": [_clean_asset(x, "character") for x in (data.get("characters") or [])],
        "locations": [_clean_asset(x, "location") for x in (data.get("locations") or [])],
        "updated_at": _now(),
    }
    CINEMA_FILE.parent.mkdir(parents=True, exist_ok=True)
    CINEMA_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _clean_asset(item: Any, kind: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    name = str(item.get("name") or "").strip()
    trigger = str(item.get("trigger") or "").strip()
    image = str(item.get("image") or "").strip()
    notes = str(item.get("notes") or item.get("description") or "").strip()
    aid = str(item.get("id") or "").strip() or str(uuid.uuid4())
    out: dict[str, Any] = {
        "id": aid,
        "kind": kind,
        "name": name,
        "trigger": trigger,
        "image": image,
        "url": str(item.get("url") or (f"/api/refs/{image}" if image else "")),
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
    return _hit_token(text, asset.get("trigger") or "") or _hit_token(text, asset.get("name") or "")


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


def annotate_prompt(text: str, hits: list[dict[str, Any]]) -> str:
    prompt = (text or "").strip()
    if not hits:
        return prompt
    lines = []
    pic_i = 0
    for h in hits:
        label = h.get("name") or h.get("trigger") or "ref"
        notes = (h.get("notes") or "").strip()
        voice = (h.get("voice") or "").strip()
        note_bit = f" Description: {notes}." if notes else ""
        voice_bit = ""
        if h.get("kind") == "character" and voice:
            voice_bit = (
                f" SPEAKER LOCK: {label} always speaks with this identical voice — {voice}. "
                f"Same timbre, accent, age and pitch every time {label} talks."
            )
        if h.get("image"):
            pic_i += 1
            role = (
                "character identity / wardrobe lock"
                if h.get("kind") == "character"
                else "location / set lock"
            )
            lines.append(
                f"<Picture {pic_i}> is the {role} for {label}.{note_bit}{voice_bit} "
                f"Keep this look consistent whenever {label} appears."
            )
        elif voice_bit or notes:
            lines.append(
                f"{label}:{note_bit}{voice_bit} Same person every shot; do not recast."
            )
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
    for h in hits:
        img = (h.get("image") or "").strip()
        if img and img not in refs:
            refs.append(img)
    refs = refs[:9]
    chosen_lora = (lora_id or "").strip()
    chosen_strength = None
    if not chosen_lora:
        for h in hits:
            if h.get("kind") == "character" and h.get("lora_id"):
                chosen_lora = str(h["lora_id"])
                chosen_strength = h.get("lora_strength")
                break
    return {
        "prompt": annotate_prompt(text, hits) if hits else (text or "").strip(),
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
    for key in ("look", "camera", "palette", "lighting", "era", "style"):
        val = setup.get(key) or "auto"
        if val in ("", "auto"):
            continue
        hint = (SETUP_HINTS.get(key) or {}).get(val) or ""
        if hint:
            parts.append(hint)
    return " ".join(parts).strip()


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
