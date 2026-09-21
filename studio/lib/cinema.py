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
COMFY_INPUT_DIR = STUDIO_ROOT.parent / "app" / "input"
MUSIC_DIR = STUDIO_ROOT / "data" / "music"
LIBRARY_FILE = STUDIO_ROOT / "data" / "asset_library.json"


def _unlink_retry(path: Path, attempts: int = 8) -> bool:
    if not path or str(path) in ("", ".", "None"):
        return True
    try:
        if not path.exists() or not path.is_file():
            return True
    except OSError:
        return True
    for attempt in range(attempts):
        try:
            path.unlink()
            return True
        except OSError:
            if attempt + 1 < attempts:
                time.sleep(0.12 * (attempt + 1))
    return False

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
        "sci_fi_hard": "hard-science deep-space cinematic, worn titanium cabins, practical instrument light, cold controlled contrast",
        "sci_fi_opera": "epic space-opera cinematic, monumental architecture, vast negative space, solemn natural light",
        "sci_fi_wasteland": "wasteland relic sci-fi cinematic, eroded tech ruins, harsh daylight, dusty earth tones",
        "sci_fi_alien": "alien organic ecology cinematic, wet biological architecture, localized bioluminescence only",
        "micro_expression": "intimate micro-expression close-up cinematic, performance-first facial detail",
        "product_minimal": "minimalist product-hero cinematic, clean negative space, material-true studio light",
        "title_sequence": "cinematic title-sequence energy, graphic silhouette reveals, editorial pacing",
        "handdrawn_live": "hand-drawn live hybrid, ink and paper texture over staged performance",
        "cgi_short": "premium 3D CGI cinematic short, PBR materials, clear silhouette animation",
        "music_video_cool": "cool music-video cinematic, rhythmic graphic frames, bold lighting accents",
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
    "voice_lang": "English",
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
    "creatures": [],
    "studio_mode": "",
    "film_plan": None,
    "pending_produce": None,
    "updated_at": 0,
}


def _now() -> float:
    return time.time()

def _empty_library() -> dict[str, Any]:
    return {"characters": [], "locations": [], "creatures": [], "updated_at": 0}


# --- restored from stash: asset library + sheet prompts ---

def asset_kind_key(kind: str) -> tuple[str, str]:
    """Normalize kind -> (singular, plural list key)."""
    k = str(kind or "").strip().lower()
    if k in ("location", "locations", "loc", "place"):
        return "location", "locations"
    if k in ("creature", "creatures", "monster", "beast", "canavar", "yaratik", "yaratık"):
        return "creature", "creatures"
    return "character", "characters"


def load_library() -> dict[str, Any]:
    if not LIBRARY_FILE.is_file():
        return _empty_library()
    try:
        raw = json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _empty_library()
    if not isinstance(raw, dict):
        return _empty_library()
    out = _empty_library()
    out["characters"] = [
        _clean_asset(x, "character") for x in (raw.get("characters") or []) if isinstance(x, dict)
    ]
    out["locations"] = [
        _clean_asset(x, "location") for x in (raw.get("locations") or []) if isinstance(x, dict)
    ]
    out["creatures"] = [
        _clean_asset(x, "creature") for x in (raw.get("creatures") or []) if isinstance(x, dict)
    ]
    out["updated_at"] = raw.get("updated_at") or 0
    return out



def save_library(data: dict[str, Any]) -> dict[str, Any]:
    out = {
        "characters": [
            _clean_asset(x, "character") for x in (data.get("characters") or []) if isinstance(x, dict)
        ],
        "locations": [
            _clean_asset(x, "location") for x in (data.get("locations") or []) if isinstance(x, dict)
        ],
        "creatures": [
            _clean_asset(x, "creature") for x in (data.get("creatures") or []) if isinstance(x, dict)
        ],
        "updated_at": _now(),
    }
    LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out



def list_library(kind: Optional[str] = None) -> dict[str, Any]:
    lib = load_library()
    k, _ = asset_kind_key(kind) if kind else ("", "")
    if k == "character":
        return {"characters": lib["characters"], "locations": [], "creatures": []}
    if k == "location":
        return {"characters": [], "locations": lib["locations"], "creatures": []}
    if k == "creature":
        return {"characters": [], "locations": [], "creatures": lib.get("creatures") or []}
    return lib



def delete_library_asset(kind: str, asset_id: str) -> bool:
    k, key = asset_kind_key(kind)
    aid = str(asset_id or "").strip()
    if not aid:
        return False
    lib = load_library()
    before = len(lib.get(key) or [])
    lib[key] = [x for x in (lib.get(key) or []) if str(x.get("id") or "") != aid]
    if len(lib[key]) == before:
        return False
    save_library(lib)
    return True



def upsert_library_asset(kind: str, asset: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace a card in the global asset library."""
    k, key = asset_kind_key(kind)
    lib = load_library()
    cleaned = _clean_asset(asset if isinstance(asset, dict) else {}, k)
    lid = str(
        (asset or {}).get("library_id") or (asset or {}).get("id") or cleaned.get("id") or ""
    ).strip()
    if lid:
        cleaned["id"] = lid
    items = list(lib.get(key) or [])
    idx = next((i for i, x in enumerate(items) if str(x.get("id") or "") == cleaned["id"]), -1)
    if idx >= 0:
        items[idx] = cleaned
    else:
        items.append(cleaned)
    lib[key] = items
    save_library(lib)
    return cleaned


def save_film_asset_to_library(kind: str, asset_id: str) -> dict[str, Any]:
    k, key = asset_kind_key(kind)
    aid = str(asset_id or "").strip()
    data = load()
    found = next((x for x in (data.get(key) or []) if str(x.get("id") or "") == aid), None)
    if not found:
        raise ValueError("asset yok")
    payload = dict(found)
    payload["library_id"] = str(found.get("library_id") or found.get("id") or "")
    saved = upsert_library_asset(k, payload)
    # Mark film card as linked
    found["library_id"] = saved["id"]
    update_asset(k, aid, {"library_id": saved["id"]})
    return saved



def pull_library_to_film(kind: str, library_id: str) -> dict[str, Any]:
    """Copy a library asset into the active film (new film-local id)."""
    k, key = asset_kind_key(kind)
    lid = str(library_id or "").strip()
    lib = load_library()
    found = next((x for x in (lib.get(key) or []) if str(x.get("id") or "") == lid), None)
    if not found:
        raise ValueError("kütüphanede yok")
    data = load()
    # If already in film (same library_id or same name+images), return existing
    for x in data.get(key) or []:
        if str(x.get("library_id") or "") == lid:
            return _clean_asset(x, k)
        if (
            str(x.get("name") or "").strip().lower() == str(found.get("name") or "").strip().lower()
            and str(x.get("image") or "") == str(found.get("image") or "")
        ):
            return _clean_asset(x, k)
    payload = dict(found)
    payload.pop("id", None)
    payload["library_id"] = lid
    payload["id"] = str(uuid.uuid4())
    return upsert_asset(k, payload)


_CREATURE_HINT = re.compile(
    r"\b(dragon|wyvern|drake|beast|creature|kaiju|monster|griffin|phoenix|"
    r"serpent|ashwing|ejder|yaratik|yaratık|canavar)\b",
    re.I,
)


def _sheet_is_creature(name: str, notes: str = "") -> bool:
    """True when name/notes clearly describe a non-human creature (not a person)."""
    return bool(_CREATURE_HINT.search(f"{name or ''} {notes or ''}"))


SHEET_PANEL_LABELS = ("portrait", "front", "back")


def is_tripanel_still(path: Path) -> bool:
    """True when the still is a wide 3-panel sheet, not a single portrait/place."""
    try:
        from PIL import Image
    except ImportError:
        return False
    src = Path(path)
    if not src.is_file():
        return False
    try:
        with Image.open(src) as im:
            w, h = im.size
    except Exception:
        return False
    return bool(w and h and w >= int(h * 1.55))


def split_tripanel_still(src: Path, dest_dir: Path, stem: str) -> list[Path]:
    """Crop a 3-panel sheet into portrait / front / back PNGs. Location stills stay 1 frame."""
    from PIL import Image

    src = Path(src)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size
        if w < int(h * 1.55):
            dest = dest_dir / f"{stem}_portrait.png"
            rgb.save(dest, "PNG")
            return [dest]
        third = max(1, w // 3)
        out: list[Path] = []
        for i, label in enumerate(SHEET_PANEL_LABELS):
            left = i * third
            right = w if i == 2 else (i + 1) * third
            dest = dest_dir / f"{stem}_{label}.png"
            rgb.crop((left, 0, right, h)).save(dest, "PNG")
            out.append(dest)
        return out


def build_character_sheet_prompt(
    name: str,
    notes: str = "",
    *,
    style_line: str = "",
    has_face_ref: bool = False,
    force_creature: bool = False,
) -> str:
    """H3 SCENE prompt for a 3-panel character turnaround still (portrait|front|back)."""
    who = (name or "character").strip() or "character"
    look = (notes or "").strip()
    creature = bool(force_creature) or _sheet_is_creature(who, look)
    if not look:
        look = (
            "legendary dragon: massive scaled body, four legs, membranous wings, long tail, "
            "horned reptilian head, no human anatomy"
            if creature
            else "distinctive face, clear age, hair, wardrobe, and proportions"
        )
    style = (style_line or "").strip() or (
        "cinematic fantasy creature photography, detailed scales and anatomy"
        if creature
        else "photorealistic live-action cinematography, natural skin texture"
    )
    identity = ""
    if has_face_ref:
        if creature:
            identity = (
                "IDENTITY LOCK: <Picture 1> is the creature / species reference. "
                "All three panels must show the same non-human creature as Picture 1 — "
                "identical head shape, scales/fur, colors, and proportions. "
                "Do not turn it into a human wearing a costume or mask. "
            )
        else:
            identity = (
                "IDENTITY LOCK: <Picture 1> is the face / identity reference for this character. "
                "All three panels must show the same person as Picture 1 — identical face shape, "
                "eyes, nose, mouth, age, skin tone, and hair. Do not invent a different face. "
            )
    if creature:
        return (
            f"Locked static CREATURE reference sheet for {who}. "
            f"{identity}"
            "CRITICAL: the subject is a full non-human creature (animal / mythical beast), "
            "NOT a human, NOT a person in a dragon mask, NOT cosplay, NOT a bipedal humanoid "
            "wearing a costume. Show the real creature body. "
            "One continuous shot, no cuts, camera completely locked, no pan, no zoom, no dialogue, silent. "
            "A single wide photographic frame divided into three equal vertical panels side by side "
            "on a seamless medium-grey studio backdrop with soft even studio lighting, no text, no logos, no watermark. "
            "Left panel: close-up of the creature HEAD only (snout/jaws/eyes/horns), facing camera, sharp scale detail. "
            "Center panel: full-body FRONT or three-quarter standing pose of the entire creature, "
            "head-to-tail / wings visible, four legs or true creature anatomy, grounded on studio floor. "
            "Right panel: full-body REAR or opposite three-quarter of the same creature, identical species and markings. "
            "All three panels show the exact same creature with consistent anatomy, color, and scale pattern. "
            f"Creature appearance: {look}. "
            f"Visual craft: {style}. "
            "Clean production reference plate, not a story scene, empty grey studio, no human figures."
        )
    return (
        f"Locked static character reference sheet for {who}. "
        f"{identity}"
        "One continuous shot, no cuts, camera completely locked, no pan, no zoom, no dialogue, silent. "
        "A single wide photographic frame divided into three equal vertical panels side by side "
        "on a seamless medium-grey studio backdrop with soft even studio lighting, no text, no logos, no watermark. "
        "Left panel: close-up head-and-shoulders portrait facing camera, neutral expression, sharp facial detail. "
        "Center panel: full-body front standing pose, arms relaxed at sides, head-to-toe visible, same identity and wardrobe. "
        "Right panel: full-body back view, identical stance and clothing, same hair and proportions. "
        "All three panels show the exact same person with consistent face, body, and outfit. "
        f"Subject appearance: {look}. "
        f"Visual craft: {style}. "
        "Clean production reference plate, not a story scene, no props clutter, bare studio floor."
    )



def build_location_sheet_prompt(
    name: str,
    notes: str = "",
    *,
    style_line: str = "",
    has_place_ref: bool = False,
) -> str:
    """H3 SCENE prompt for a single location reference still (one frame, no triptych)."""
    place = (name or "location").strip() or "location"
    look = (notes or "").strip() or (
        "clear architecture, lighting, materials, and spatial depth"
    )
    style = (style_line or "").strip() or (
        "photorealistic live-action cinematography, natural materials"
    )
    place_lock = ""
    if has_place_ref:
        place_lock = (
            "PLACE LOCK: <Picture 1> is the visual reference for this location. "
            "Match architecture, materials, lighting, and spatial layout of Picture 1 — "
            "same place, not a different set. "
        )
    return (
        f"Locked static location reference still for {place}. "
        f"{place_lock}"
        "One continuous shot, no cuts, camera completely locked, no dialogue, silent. "
        "ONE single wide cinematic photograph of the whole place — one cohesive frame only. "
        "Do NOT split into panels, triptych, grid, collage strips, or side-by-side views. "
        "No black bars, no panel dividers, no multi-angle montage. "
        "Show the full space in one establishing hero angle: architecture, depth, light, "
        "materials, and atmosphere readable at a glance. "
        f"Place description: {look}. "
        f"Visual craft: {style}. "
        "Clean production reference plate, empty of named characters unless required by the description."
    )


def _clean_audio(raw: Any) -> dict[str, str]:
    src = raw if isinstance(raw, dict) else {}
    mode = str(src.get("mode") or "film").strip().lower() or "film"
    if mode not in ("film", "silent"):
        mode = "film"
    out = {
        "mode": mode,
        "score_id": str(src.get("score_id") or "").strip(),
        "score_name": str(src.get("score_name") or "").strip(),
        "voice_lang": str(src.get("voice_lang") or "English").strip() or "English",
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


_STRUCTURED_KEYS = (
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


def _clean_structured(raw: Any) -> dict[str, str]:
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, str] = {}
    for key in _STRUCTURED_KEYS:
        out[key] = str(src.get(key) or "").strip()
    return out


def _dialogue_lang_label(structured: dict[str, str]) -> str:
    """H3 <d>[Language] tag — never invent Arabic; preserve user choice / light auto."""
    explicit = (structured.get("dialogue_lang") or "").strip()
    if explicit and explicit.lower() not in ("auto", ""):
        return explicit
    dialogue = structured.get("dialogue") or ""
    if re.search(r"[\u0600-\u06FF]", dialogue):
        return "Arabic"
    if re.search(r"[\u0400-\u04FF]", dialogue):
        return "Russian"
    if re.search(r"[\u3040-\u30FF\u4E00-\u9FFF]", dialogue):
        return "Japanese" if re.search(r"[\u3040-\u30FF]", dialogue) else "Chinese"
    if re.search(r"[\uAC00-\uD7AF]", dialogue):
        return "Korean"
    if re.search(r"[ğüşıöçĞÜŞİÖÇ]", dialogue):
        return "Turkish"
    return "English"


def _wrap_dialogue_block(dialogue: str, lang: str) -> str:
    text = (dialogue or "").strip()
    if not text:
        return ""
    # Already H3-tagged — leave as-is
    if "<d>" in text.lower():
        return text
    label = (lang or "English").strip() or "English"
    # Multi-line dialogue: keep as one <d> block
    return f"says: <d>[{label}] {text}</d>"


def compose_h3_prompt(structured: Any, look_id: str = "") -> str:
    """Author fields → official H3 three-field prompt (base-en.txt)."""
    try:
        from . import skills as skill_lib

        s = skill_lib.enrich_structured_from_look(structured, look_id)
    except Exception:
        s = _clean_structured(structured)
    if not any(s.get(k) for k in _STRUCTURED_KEYS if k != "dialogue_lang"):
        return ""

    style = s.get("visual_style") or "Live-action, cinematic"
    parts: list[str] = [f"[Shot 1] {style}"]
    if s.get("location"):
        parts.append(f"Location: {s['location']}")
    if s.get("character"):
        parts.append(f"Main character: {s['character']}")
    if s.get("action"):
        parts.append(f"Action: {s['action']}")
    if s.get("camera"):
        parts.append(f"Camera: {s['camera']}")
    if s.get("dialogue"):
        lang = _dialogue_lang_label(s)
        who = s.get("character") or "The speaker (S1)"
        # Prefer identity + dialogue in multimodal body
        if "(S1)" in who or "(S2)" in who:
            parts.append(f"{who} {_wrap_dialogue_block(s['dialogue'], lang)}")
        else:
            parts.append(f"{who} (S1) {_wrap_dialogue_block(s['dialogue'], lang)}")
    if s.get("important"):
        parts.append(f"Constraints: {s['important']}")

    multimodal = " ".join(p.strip() for p in parts if p.strip())
    if s.get("title"):
        multimodal = f"SCENE – {s['title']}. {multimodal}"

    soundscape = s.get("audio") or (
        "Natural ambient sound matching the scene, with clear dialogue when present."
    )
    music_raw = (s.get("music") or "").strip()
    if not music_raw or music_raw.lower() in ("n/a", "na", "none", "no", "yok", "off"):
        music = "N/A"
    else:
        music = music_raw

    return (
        f"integrated_multimodal_description: {multimodal}\n\n"
        f"overall_soundscape: {soundscape}\n\n"
        f"non_diegetic_music: {music}"
    )


_H3_MARKERS = (
    ("location", re.compile(r"\bLocation:\s*", re.I)),
    ("character", re.compile(r"\bMain character:\s*", re.I)),
    ("action", re.compile(r"\bAction:\s*", re.I)),
    ("camera", re.compile(r"\bCamera:\s*", re.I)),
    ("important", re.compile(r"\bConstraints:\s*", re.I)),
)
_H3_HEAD = re.compile(
    r"(?is)^\s*(?:SCENE\s*[–—-]\s*(?P<title>.+?)\.\s+)?\[Shot\s*\d+\]\s*(?P<style>.*?)\s*$"
)
_H3_SAYS = re.compile(
    r"(?is)\s+\(S\d+\)\s+says:\s*(?:<d>\[(?P<lang>[^\]]+)\]\s*)?(?P<line>.*?)</d>\s*$"
)
_H3_WHO = re.compile(r"^(?P<camera>.+)\s+(?P<who>[A-Z][^()]+)$")
_H3_BLOCKS = re.compile(
    r"(?is)integrated[_\s]+multimodal[_\s]+description\s*[?:]\s*(?P<body>.*?)"
    r"(?:\s+overall_soundscape\s*[?:]\s*(?P<audio>.*?))?"
    r"(?:\s+non_diegetic_music\s*[?:]\s*(?P<music>.*?))?\s*$"
)


def _has_author_fields(structured: dict[str, str]) -> bool:
    return any(structured.get(k) for k in _STRUCTURED_KEYS if k != "dialogue_lang")


def _looks_like_h3_prompt(text: Any) -> bool:
    return bool(re.search(r"(?i)integrated[_\s]+multimodal[_\s]+description", str(text or "")))


def parse_h3_prompt(text: Any) -> dict[str, str]:
    """Reverse compose_h3_prompt so Director fields refill from a compiled clip."""
    raw = str(text or "").strip()
    out = _clean_structured({})
    if not raw:
        return out
    packed = re.sub(r"\s+", " ", raw).strip()
    blocks = _H3_BLOCKS.search(packed)
    body = packed
    if blocks:
        body = (blocks.group("body") or "").strip()
        out["audio"] = (blocks.group("audio") or "").strip()
        out["music"] = (blocks.group("music") or "").strip()
    hits: list[tuple[int, int, str]] = []
    for key, rx in _H3_MARKERS:
        m = rx.search(body)
        if m:
            hits.append((m.start(), m.end(), key))
    if not hits and not blocks:
        return _clean_structured({})
    hits.sort()
    head = body[: hits[0][0]].strip() if hits else body
    hm = _H3_HEAD.match(head)
    if hm:
        out["title"] = (hm.group("title") or "").strip()
        out["visual_style"] = (hm.group("style") or "").strip()
    elif head.lower().startswith("scene"):
        out["title"] = re.sub(r"(?i)^SCENE\s*[–—-]\s*", "", head).strip(" .")
    for i, (_start, end, key) in enumerate(hits):
        stop = hits[i + 1][0] if i + 1 < len(hits) else len(body)
        out[key] = body[end:stop].strip()
    cam = out.get("camera") or ""
    dm = _H3_SAYS.search(cam)
    if dm:
        before = cam[: dm.start()].strip()
        who = (out.get("character") or "").strip()
        if who and before.endswith(who):
            out["camera"] = before[: -len(who)].strip()
        else:
            wm = _H3_WHO.match(before)
            if wm:
                out["camera"] = (wm.group("camera") or "").strip()
                if not who:
                    out["character"] = (wm.group("who") or "").strip()
            else:
                out["camera"] = before
        line = (dm.group("line") or "").strip()
        if line:
            out["dialogue"] = line
            lang = (dm.group("lang") or "").strip()
            if lang:
                out["dialogue_lang"] = lang
    if out.get("music") and out["music"].lower() in ("n/a", "na", "none", "no", "yok", "off"):
        out["music"] = "N/A"
    return out


def _clean_shot(item: Any, index: int = 0, look_id: str = "") -> dict[str, Any]:
    if isinstance(item, str):
        item = {"text": item}
    if not isinstance(item, dict):
        item = {}
    structured = _clean_structured(item.get("structured"))
    text = str(item.get("text") or item.get("prompt") or item.get("h3Prompt") or "").strip()
    blob = text or structured.get("action") or ""
    only_blob = _looks_like_h3_prompt(blob) and not any(
        structured.get(k) for k in ("title", "location", "character", "camera")
    )
    if (not _has_author_fields(structured) or only_blob) and blob:
        parsed = parse_h3_prompt(blob)
        if _has_author_fields(parsed):
            structured = parsed
    composed = compose_h3_prompt(structured, look_id=look_id)
    if composed:
        text = composed
    mode = str(item.get("mode") or "").strip().lower()
    if mode in ("continue", "devam", "i2v", "last_frame"):
        mode = "continue"
    else:
        mode = "t2v"
    sid = str(item.get("id") or "").strip() or str(uuid.uuid4())
    out = {
        "id": sid,
        "text": text,
        "mode": mode,
        "enabled": item.get("enabled") is not False,
        "index": index,
    }
    # A section imported from JSON (or explicitly set in the editor) has an
    # intentional new/continue choice.  Do not later replace it with the
    # heuristic cutaway mode just because character names differ in the text.
    if item.get("mode_locked") is True:
        out["mode_locked"] = True
    section_id = str(item.get("sectionId") or item.get("section_id") or "").strip()
    if section_id:
        out["section_id"] = section_id
    if item.get("durationSec") not in (None, ""):
        try:
            out["durationSec"] = max(1, min(15, int(item.get("durationSec") or 5)))
        except Exception:
            pass
    if _has_author_fields(structured):
        out["structured"] = structured
    if item.get("take_id"):
        out["take_id"] = str(item.get("take_id") or "").strip()
    if item.get("take_title"):
        out["take_title"] = str(item.get("take_title") or "").strip()
    if item.get("take_index") not in (None, ""):
        try:
            out["take_index"] = max(1, int(item.get("take_index") or 1))
        except Exception:
            out["take_index"] = 1
    return out


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
    look_id = ""
    setup = data.get("setup") if isinstance(data.get("setup"), dict) else {}
    look_id = str(setup.get("look") or "").strip()
    raw = data.get("shots")
    if isinstance(raw, list):
        cleaned = [_clean_shot(item, i, look_id=look_id) for i, item in enumerate(raw)]
        # Keep explicit shot rows (even empty drafts). Only fall back to script when
        # the shots key is missing — legacy saves stored script only.
        if cleaned or "shots" in data:
            return cleaned
    texts = split_shots(str(data.get("script") or ""))
    return [
        _clean_shot({"text": t, "mode": "t2v" if i == 0 else "continue"}, i, look_id=look_id)
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
    data.setdefault("creatures", [])
    if not isinstance(data["characters"], list):
        data["characters"] = []
    if not isinstance(data["locations"], list):
        data["locations"] = []
    if not isinstance(data["creatures"], list):
        data["creatures"] = []
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
    data["studio_mode"] = _clean_studio_mode(data.get("studio_mode"))
    if not data.get("script"):
        data["script"] = "\n\n---\n\n".join(s["text"] for s in data["shots"] if s.get("text"))
    fp = data.get("film_plan")
    data["film_plan"] = _clean_film_plan(fp) if isinstance(fp, dict) else None
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
    look_id = str((_clean_setup(data.get("setup")).get("look") or "")).strip()
    prev_by_id = {
        str(s.get("id") or ""): s
        for s in (prev.get("shots") or [])
        if isinstance(s, dict) and s.get("id")
    }
    merged_shots: list[Any] = []
    for i, x in enumerate(data.get("shots") or []):
        row = dict(x) if isinstance(x, dict) else {"text": x}
        incoming = _clean_structured(row.get("structured"))
        if not _has_author_fields(incoming):
            older = prev_by_id.get(str(row.get("id") or ""))
            if isinstance(older, dict):
                prev_s = _clean_structured(older.get("structured"))
                if _has_author_fields(prev_s):
                    row["structured"] = prev_s
        merged_shots.append(_clean_shot(row, i, look_id=look_id))
    shots = merged_shots
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
        "characters": [
            _clean_asset(x, "character")
            for x in _keep_asset_stills(data.get("characters") or [], prev.get("characters") or [])
        ],
        "locations": [
            _clean_asset(x, "location")
            for x in _keep_asset_stills(data.get("locations") or [], prev.get("locations") or [])
        ],
        "creatures": [
            _clean_asset(x, "creature")
            for x in _keep_asset_stills(
                data["creatures"] if "creatures" in data else (prev.get("creatures") or []),
                prev.get("creatures") or [],
            )
        ],
        "studio_mode": _clean_studio_mode(
            data["studio_mode"] if "studio_mode" in data else prev.get("studio_mode")
        ),
        "updated_at": _now(),
    }
    outline = data.get("shotOutline")
    if outline is None:
        outline = prev.get("shotOutline")
    if isinstance(outline, list) and outline:
        out["shotOutline"] = outline
    # Scene produce waits on this; a whitelist save used to drop it so
    # sheets finished and the 24 clips never queued.
    if "pending_produce" in data:
        pend = data.get("pending_produce")
        out["pending_produce"] = pend if isinstance(pend, dict) else None
    else:
        prev_pend = prev.get("pending_produce")
        if isinstance(prev_pend, dict):
            out["pending_produce"] = prev_pend
    CINEMA_FILE.parent.mkdir(parents=True, exist_ok=True)
    CINEMA_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    _archive_film(out)
    return out


def _asset_has_still(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if str(item.get("image") or "").strip() or str(item.get("url") or "").strip():
        return True
    imgs = item.get("images")
    if not isinstance(imgs, list):
        return False
    return any(
        (isinstance(x, str) and x.strip())
        or (isinstance(x, dict) and (x.get("file") or x.get("url") or x.get("image")))
        for x in imgs
    )


def _asset_image_files(item: Any) -> list[str]:
    if not isinstance(item, dict):
        return []
    files: list[str] = []
    seen: set[str] = set()
    for x in item.get("images") or []:
        file = ""
        if isinstance(x, str):
            file = x.strip()
        elif isinstance(x, dict):
            file = str(x.get("file") or x.get("image") or "").strip()
        if file and file not in seen:
            seen.add(file)
            files.append(file)
    single = str(item.get("image") or "").strip()
    if single and single not in seen:
        files.append(single)
    return files


def _asset_name_key(item: Any) -> str:
    if isinstance(item, str):
        return item.strip().lower()
    if isinstance(item, dict):
        return str(item.get("name") or "").strip().lower()
    return ""


def _stills_donor_index(donors: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for src in donors or []:
        if not isinstance(src, dict) or not _asset_has_still(src):
            continue
        key = _asset_name_key(src)
        if key and key not in out:
            out[key] = src
    return out


def _copy_asset_stills(dest: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    row = dict(dest)
    row["images"] = list(src.get("images") or [])
    row["image"] = src.get("image") or ""
    row["url"] = src.get("url") or ""
    if src.get("id") and not _asset_has_still(dest):
        row["id"] = src.get("id") or row.get("id")
    if src.get("library_id"):
        row["library_id"] = src.get("library_id")
    if src.get("lora_id"):
        row["lora_id"] = src.get("lora_id")
        row["lora_strength"] = src.get("lora_strength") or row.get("lora_strength") or 0.8
    if src.get("voice_audio"):
        row["voice_audio"] = src.get("voice_audio")
    return row


def _adopt_stills_by_name(incoming: list[Any], *donor_lists: list[Any]) -> tuple[list[dict[str, Any]], int]:
    """Reuse stills from current film / library when the imported name already exists."""
    donors: list[Any] = []
    for block in donor_lists:
        donors.extend(block or [])
    by_name = _stills_donor_index(donors)
    out: list[dict[str, Any]] = []
    kept = 0
    for raw in incoming or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        prev = by_name.get(_asset_name_key(item))
        if prev and not _asset_has_still(item):
            item = _copy_asset_stills(item, prev)
            kept += 1
        out.append(item)
    return out, kept


def _keep_asset_stills(incoming: list[Any], previous: list[Any]) -> list[Any]:
    """Keep sheet stills if a stale UI PUT sends empty or older 1-frame collages."""
    prev_by_id = {
        str(x.get("id") or ""): x
        for x in (previous or [])
        if isinstance(x, dict) and x.get("id")
    }
    prev_by_name = _stills_donor_index(previous or [])
    out: list[Any] = []
    for row in incoming or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        prev = prev_by_id.get(str(item.get("id") or "")) or prev_by_name.get(
            _asset_name_key(item)
        )
        if prev and _asset_has_still(prev):
            prev_files = _asset_image_files(prev)
            inc_files = _asset_image_files(item)
            stale_collage = (
                not inc_files
                or (len(prev_files) > len(inc_files) and len(prev_files) >= 3)
            )
            if stale_collage:
                item["images"] = list(prev.get("images") or [])
                item["image"] = prev.get("image") or ""
                item["url"] = prev.get("url") or ""
        out.append(item)
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
    voice_audio = str(item.get("voice_audio") or "").strip()
    if voice_audio:
        out["voice_audio"] = Path(voice_audio).name
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
    kind, key = asset_kind_key(kind)
    cleaned = _clean_asset(asset, kind)
    items = data[key]
    idx = next((i for i, x in enumerate(items) if str(x.get("id") or "") == cleaned["id"]), -1)
    if idx >= 0:
        items[idx] = cleaned
    else:
        items.append(cleaned)
    data[key] = items
    save(data)
    return cleaned


def update_asset(kind: str, asset_id: str, fields: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Patch an existing card in one load/save. Never re-creates a deleted id."""
    aid = str(asset_id or "").strip()
    if not aid:
        return None
    data = load()
    kind, key = asset_kind_key(kind)
    items = data.setdefault(key, [])
    idx = next((i for i, x in enumerate(items) if str(x.get("id") or "") == aid), -1)
    if idx < 0:
        return None
    merged = {**(items[idx] if isinstance(items[idx], dict) else {}), **(fields or {})}
    merged["id"] = aid
    cleaned = _clean_asset(merged, kind)
    items[idx] = cleaned
    data[key] = items
    save(data)
    return cleaned


def delete_asset(kind: str, asset_id: str) -> bool:
    data = load()
    kind, key = asset_kind_key(kind)
    aid = str(asset_id or "").strip()
    removed = [x for x in data[key] if str(x.get("id") or "") == aid]
    before = len(data[key])
    data[key] = [x for x in data[key] if str(x.get("id") or "") != aid]
    if len(data[key]) == before:
        return False
    save(data)
    keep_files = {
        Path(str(image.get("file"))).name
        for item in data[key]
        for image in item.get("images") or []
        if isinstance(image, dict) and image.get("file")
    }
    for item in data[key]:
        if item.get("image"):
            keep_files.add(Path(str(item["image"])).name)
    for item in removed:
        images = list(item.get("images") or [])
        if item.get("image"):
            images.append({"file": item["image"]})
        for image in images:
            if not isinstance(image, dict):
                continue
            filename = image.get("file") or image.get("name")
            if not filename:
                continue
            name = Path(str(filename)).name
            if name in keep_files:
                continue
            for path in (REFS_DIR / name, COMFY_INPUT_DIR / name):
                if path.exists():
                    _unlink_retry(path)
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
    for kind, key in (
        ("character", "characters"),
        ("creature", "creatures"),
        ("location", "locations"),
    ):
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
        kind = str(h.get("kind") or "")
        if kind == "character":
            role = "character identity / wardrobe lock"
        elif kind == "creature":
            role = "creature / species lock"
        else:
            role = "location / set lock"
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
    lang = audio.get("voice_lang") or "English"
    # Never put a sample <d>…</d> here — H3 speaks tag contents, so a
    # placeholder word like "line" becomes the first audible word in the clip.
    return (
        f"Only tagged spoken words are audible. Language for those tags is {lang}. "
        "Do not speak instructions, tag names, language names, or placeholders. "
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
    primary: list[dict[str, Any]] = []
    extra: list[dict[str, Any]] = []
    for h in hits:
        imgs = mentioned_images(text, h)
        if not imgs:
            continue
        primary.append({**imgs[0], "asset": h})
        extra.extend({**im, "asset": h} for im in imgs[1:])
    for row in primary + extra:
        file = str(row.get("file") or "").strip()
        if not file:
            continue
        bound_rows.append(row)
        if file not in refs:
            refs.append(file)
        if len(refs) >= 9:
            break
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
    look = setup.get("look") or ""
    if look and look != "auto":
        try:
            from . import skills as skill_lib

            craft = skill_lib.look_craft_line(look)
            if craft and craft not in " ".join(parts):
                parts.append(craft)
        except Exception:
            pass
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


def character_ids_in_text(text: str, lib: Optional[dict[str, Any]] = None) -> set[str]:
    """Cinema character asset ids mentioned in shot text (name / trigger / still name)."""
    out: set[str] = set()
    for h in match_prompt(text or "", lib):
        if h.get("kind") != "character":
            continue
        uid = str(h.get("id") or h.get("name") or "").strip()
        if uid:
            out.add(uid)
    return out


def apply_reentry_modes(
    shots: list[dict[str, Any]],
    lib: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Hard-cut (t2v) when a shot has no character continuity with the previous shot.

    Same beat / same cast overlap → keep continue. Cutaway or different cast with
    no overlap → t2v so last-frame drift does not steal character identity.
    """
    lib = lib or load()
    out: list[dict[str, Any]] = []
    prev: set[str] = set()
    for i, raw in enumerate(shots or []):
        if not isinstance(raw, dict):
            continue
        shot = dict(raw)
        text = str(shot.get("text") or shot.get("h3Prompt") or "")
        curr = character_ids_in_text(text, lib)
        mode = str(shot.get("mode") or "t2v").lower()
        if mode in ("devam", "i2v", "last_frame"):
            mode = "continue"
        if i == 0:
            mode = "t2v"
        elif not shot.get("mode_locked") and curr and not (curr & prev):
            mode = "t2v"
        shot["mode"] = mode
        out.append(shot)
        prev = curr
    return out


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
                fallback = "t2v"
                if i < len(mode_list):
                    fallback = mode_list[i]
                elif not all_strings:
                    fallback = "t2v"
                shot = _clean_shot({"text": str(item or ""), "mode": fallback}, i)
            if shot.get("text") and shot.get("enabled", True):
                parsed.append(shot)
        return parsed
    texts = split_shots(script or "")
    return [_clean_shot({"text": t, "mode": "t2v"}, i) for i, t in enumerate(texts)]


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


def _portrait_file(value: Any) -> str:
    file = str(value or "").strip()
    if not file or file.startswith("preview:"):
        return ""
    return file


def character_portrait_files(asset: Any) -> list[str]:
    """Uploaded character still filenames (not location plates, not blob previews)."""
    if not isinstance(asset, dict):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for im in asset.get("images") or []:
        file = ""
        if isinstance(im, dict):
            file = _portrait_file(im.get("file") or im.get("image"))
        elif isinstance(im, str):
            file = _portrait_file(im)
        if file and file not in seen:
            seen.add(file)
            out.append(file)
    leftover = _portrait_file(asset.get("image"))
    if leftover and leftover not in seen:
        out.append(leftover)
    return out


def bound_character_portraits(text: str, lib: Optional[dict[str, Any]] = None) -> list[str]:
    """Portrait files for character cards actually named in this prompt."""
    files: list[str] = []
    seen: set[str] = set()
    for hit in match_prompt(text, lib):
        if hit.get("kind") != "character":
            continue
        for file in character_portrait_files(hit):
            if file not in seen:
                seen.add(file)
                files.append(file)
    return files


def characters_missing_stills(lib: Optional[dict[str, Any]] = None) -> list[str]:
    """Character names with no uploaded stills (face lock weaker without them)."""
    lib = lib or load()
    missing: list[str] = []
    for ch in lib.get("characters") or []:
        if not isinstance(ch, dict):
            continue
        name = str(ch.get("name") or "").strip()
        if not name:
            continue
        if not character_portrait_files(ch):
            missing.append(name)
    return missing


def _clean_film_plan(raw: Any) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    try:
        total_sec = max(1, int(src.get("total_sec") or 60))
    except (TypeError, ValueError):
        total_sec = 60
    try:
        clip_sec = int(src.get("clip_sec") or 5)
    except (TypeError, ValueError):
        clip_sec = 5
    if clip_sec not in (4, 5, 6, 8, 10, 15):
        clip_sec = 5
    try:
        segment_size = max(1, min(8, int(src.get("segment_size") or 6)))
    except (TypeError, ValueError):
        segment_size = 6
    segments = src.get("segments") if isinstance(src.get("segments"), list) else []
    clean_segments: list[list[dict[str, Any]]] = []
    for seg in segments:
        if not isinstance(seg, list):
            continue
        row = [_clean_shot(s, i) for i, s in enumerate(seg) if isinstance(s, dict)]
        row = [s for s in row if s.get("text")]
        if row:
            clean_segments.append(row)
    try:
        current = max(0, int(src.get("current_segment") or 0))
    except (TypeError, ValueError):
        current = 0
    status = str(src.get("status") or "idle").strip().lower() or "idle"
    if status not in ("idle", "producing", "done", "concat"):
        status = "idle"
    return {
        "total_sec": total_sec,
        "clip_sec": clip_sec,
        "segment_size": segment_size,
        "shot_count": int(src.get("shot_count") or sum(len(s) for s in clean_segments)),
        "segment_count": len(clean_segments),
        "segments": clean_segments,
        "current_segment": current,
        "segment_batches": [str(x) for x in (src.get("segment_batches") or []) if str(x).strip()],
        "segment_job_ids": [
            [str(j) for j in row if str(j).strip()]
            for row in (src.get("segment_job_ids") or [])
            if isinstance(row, list)
        ],
        "auto_concat": bool(src.get("auto_concat", True)),
        "concat_done": bool(src.get("concat_done")),
        "final_batch_id": str(src.get("final_batch_id") or "").strip(),
        "status": status,
    }


def split_film_segments(
    shots: list[dict[str, Any]], segment_size: int = 6
) -> list[list[dict[str, Any]]]:
    size = max(1, min(8, int(segment_size or 6)))
    rows = [_clean_shot(s, i) for i, s in enumerate(shots or []) if isinstance(s, dict)]
    rows = [s for s in rows if s.get("text")]
    if not rows:
        return []
    out: list[list[dict[str, Any]]] = []
    for i in range(0, len(rows), size):
        out.append(rows[i : i + size])
    return out


def build_film_plan(
    shots: list[dict[str, Any]],
    *,
    total_sec: int = 60,
    clip_sec: int = 10,
    segment_size: int = 6,
    auto_concat: bool = True,
) -> dict[str, Any]:
    segments = split_film_segments(shots, segment_size)
    return _clean_film_plan(
        {
            "total_sec": total_sec,
            "clip_sec": clip_sec,
            "segment_size": segment_size,
            "shot_count": sum(len(s) for s in segments),
            "segment_count": len(segments),
            "segments": segments,
            "current_segment": 0,
            "segment_batches": [],
            "segment_job_ids": [],
            "auto_concat": auto_concat,
            "concat_done": False,
            "final_batch_id": "",
            "status": "idle",
        }
    )


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
        others = sorted(FILMS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if others:
            data = json.loads(others[0].read_text(encoding="utf-8"))
            data["film_id"] = others[0].stem
            CINEMA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return load()
        # Do not create a new UUID when the last film is deleted.
        blank = json.loads(json.dumps(_EMPTY))
        blank["film_id"] = fid
        save(blank)
        return load()
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


CINEMA_JSON_SCHEMA = "h3-cinema/v1"
CINEMA_SEAMLESS_SCHEMA = "h3-cinema-seamless/v1"
CINEMA_JSON_TEMPLATE_FILE = STUDIO_ROOT / "schemas" / "h3-cinema-v1.example.json"
CINEMA_SEAMLESS_TEMPLATE_FILE = STUDIO_ROOT / "schemas" / "h3-cinema-seamless-v1.example.json"
SEAMLESS_MAX_SHOTS = 8
SEAMLESS_DEFAULT_DURATION = 5


def _clean_studio_mode(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("seamless", "kesintisiz", "multishot"):
        return "seamless"
    if raw in ("assets", "asset", "karakter", "face", "film"):
        return "assets"
    return ""


def _looks_like_take_block(item: Any) -> bool:
    if isinstance(item, list):
        return True
    if not isinstance(item, dict):
        return False
    return any(isinstance(item.get(k), list) for k in ("sections", "shots", "beats"))


def extract_take_blocks(payload: Any) -> list[dict[str, Any]] | None:
    """JSON takes[] / scenes[] → [{title, sections}]. Flat shot lists return None."""
    if not isinstance(payload, dict):
        return None
    for key in ("takes", "scenes"):
        raw = payload.get(key)
        if not isinstance(raw, list) or not raw:
            continue
        if key == "scenes" and not all(_looks_like_take_block(x) for x in raw):
            continue
        if key == "takes" and not any(_looks_like_take_block(x) for x in raw):
            continue
        blocks: list[dict[str, Any]] = []
        for i, block in enumerate(raw, start=1):
            if isinstance(block, list):
                block = {"title": f"Sahne {i}", "sections": block}
            if not isinstance(block, dict):
                continue
            secs = (
                block.get("sections")
                if isinstance(block.get("sections"), list)
                else block.get("shots")
                if isinstance(block.get("shots"), list)
                else block.get("beats")
                if isinstance(block.get("beats"), list)
                else []
            )
            title = str(
                block.get("title") or block.get("name") or block.get("scene") or f"Sahne {i}"
            ).strip() or f"Sahne {i}"
            blocks.append({"title": title, "sections": secs})
        if blocks:
            return blocks
    return None


def is_seamless_package(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    schema = str(payload.get("schema") or "").strip().lower()
    if schema in (CINEMA_SEAMLESS_SCHEMA, "h3-cinema-seamless", "h3-cinema-seamless/v1"):
        return True
    if _clean_studio_mode(payload.get("studio_mode") or payload.get("produce")) == "seamless":
        return True
    if payload.get("seamless") is True:
        return True
    return bool(extract_take_blocks(payload))


def group_seamless_takes(
    parsed: list[dict[str, Any]],
    prompts: Optional[list[str]] = None,
    *,
    pack: int = SEAMLESS_MAX_SHOTS,
) -> list[tuple[list[dict[str, Any]], list[str]]]:
    """One Multishot job per take. Prefer shot.take_index; else packs of 8."""
    pack = max(1, int(pack or SEAMLESS_MAX_SHOTS))
    items = [s for s in (parsed or []) if isinstance(s, dict)]
    n = len(items)
    texts = list(prompts or [])
    while len(texts) < n:
        texts.append(str(items[len(texts)].get("text") or ""))
    texts = texts[:n]
    if not n:
        return []

    def _parts(idxs: list[int]) -> list[tuple[list[dict[str, Any]], list[str]]]:
        out: list[tuple[list[dict[str, Any]], list[str]]] = []
        for j in range(0, len(idxs), pack):
            part = idxs[j : j + pack]
            out.append(([items[k] for k in part], [texts[k] for k in part]))
        return out

    if any(s.get("take_index") not in (None, "", 0) for s in items):
        groups: dict[int, list[int]] = {}
        order: list[int] = []
        for i, s in enumerate(items):
            try:
                tid = int(s.get("take_index") or 0)
            except Exception:
                tid = 0
            if tid < 1:
                tid = order[-1] if order else 1
            if tid not in groups:
                groups[tid] = []
                order.append(tid)
            groups[tid].append(i)
        chunks: list[tuple[list[dict[str, Any]], list[str]]] = []
        for tid in order:
            chunks.extend(_parts(groups[tid]))
        return chunks
    return [
        (items[i : i + pack], texts[i : i + pack])
        for i in range(0, n, pack)
    ]


def _stamp_take(shot: dict[str, Any], *, take_index: int, take_title: str, take_id: str) -> dict[str, Any]:
    shot["take_index"] = take_index
    shot["take_title"] = take_title
    shot["take_id"] = take_id
    return shot


def _shots_from_take_blocks(
    blocks: list[dict[str, Any]],
    *,
    look_id: str = "",
    warnings: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    idx = 0
    take_n = 0
    split_n = 0
    notes = warnings if isinstance(warnings, list) else []
    for block in blocks or []:
        secs = [x for x in (block.get("sections") or []) if isinstance(x, (dict, str))]
        if not secs:
            continue
        parts = [
            secs[j : j + SEAMLESS_MAX_SHOTS]
            for j in range(0, len(secs), SEAMLESS_MAX_SHOTS)
        ]
        if len(parts) > 1:
            split_n += 1
        base_title = str(block.get("title") or "").strip() or f"Sahne {take_n + 1}"
        for pi, part in enumerate(parts):
            take_n += 1
            take_id = uuid.uuid4().hex[:8]
            title = base_title if len(parts) == 1 else f"{base_title} ({pi + 1})"
            for item in part:
                shot = _shot_from_section(item, idx, look_id=look_id)
                _stamp_take(shot, take_index=take_n, take_title=title, take_id=take_id)
                if shot.get("text") or shot.get("structured"):
                    shots.append(shot)
                    idx += 1
    if split_n:
        notes.append(
            f"{split_n} take {SEAMLESS_MAX_SHOTS} shot sınırını aştı — fazla beat sonraki take oldu"
        )
    if take_n:
        notes.append(
            f"Kesintisiz {len(shots)} shot → {take_n} take "
            f"({SEAMLESS_MAX_SHOTS} shot/take, örn. 8×5sn = 40sn)"
        )
    return shots


def _stamp_flat_takes(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    take_ids: dict[int, str] = {}
    for i, shot in enumerate(shots):
        ti = i // SEAMLESS_MAX_SHOTS + 1
        if ti not in take_ids:
            take_ids[ti] = uuid.uuid4().hex[:8]
        _stamp_take(
            shot,
            take_index=ti,
            take_title=str(shot.get("take_title") or f"Sahne {ti}").strip() or f"Sahne {ti}",
            take_id=take_ids[ti],
        )
    return shots


def _takes_from_shots(shots: list[Any]) -> list[dict[str, Any]]:
    rows = [s for s in (shots or []) if isinstance(s, dict)]
    if not rows:
        return []
    stamped = [s for s in rows if s.get("take_index") not in (None, "", 0)]
    if len(stamped) == len(rows):
        by: dict[int, dict[str, Any]] = {}
        order: list[int] = []
        for s in rows:
            try:
                ti = int(s.get("take_index") or 1)
            except Exception:
                ti = 1
            if ti not in by:
                title = str(s.get("take_title") or f"Sahne {ti}").strip() or f"Sahne {ti}"
                by[ti] = {"title": title, "sections": []}
                order.append(ti)
            by[ti]["sections"].append(_section_from_shot(s))
        return [by[i] for i in order]
    out: list[dict[str, Any]] = []
    for i in range(0, len(rows), SEAMLESS_MAX_SHOTS):
        part = rows[i : i + SEAMLESS_MAX_SHOTS]
        ti = len(out) + 1
        title = str((part[0] or {}).get("take_title") or "").strip() or f"Sahne {ti}"
        out.append({"title": title, "sections": [_section_from_shot(s) for s in part]})
    return out


def _blank_seamless_template() -> dict[str, Any]:
    section = {
        "title": "",
        "location": "",
        "character": "",
        "action": "",
        "dialogue": "",
        "dialogue_lang": "auto",
        "camera": "",
        "visual_style": "",
        "audio": "",
        "music": "N/A",
        "important": "",
    }
    return {
        "schema": CINEMA_SEAMLESS_SCHEMA,
        "studio_mode": "seamless",
        "seamless": True,
        "title": "",
        "logline": "",
        "look": "auto",
        "setup": {
            "look": "auto",
            "camera": "auto",
            "palette": "auto",
            "lighting": "auto",
            "era": "auto",
            "purpose": "short_film",
            "style": "realistic",
        },
        "duration": SEAMLESS_DEFAULT_DURATION,
        "quality": "736",
        "steps": 18,
        "characters": [
            {
                "name": "",
                "notes": "",
                "voice": "",
                "trigger": "",
                "lora_id": "",
                "lora_strength": 0.8,
            }
        ],
        "locations": [{"name": "", "notes": "", "trigger": ""}],
        "creatures": [],
        "_user": {"scenes": 5, "about": ""},
        "takes": [
            {
                "title": f"Sahne {ti}",
                "sections": [dict(section) for _ in range(SEAMLESS_MAX_SHOTS)],
            }
            for ti in range(1, 4)
        ],
    }


def project_json_template(kind: str = "") -> dict[str, Any]:
    """Blank cinema package. kind=seamless → Kesintisiz (8-shot takes); else 12×5s Film."""
    want_seamless = str(kind or "").strip().lower() in (
        "seamless",
        "kesintisiz",
        "multishot",
        CINEMA_SEAMLESS_SCHEMA,
    )
    if want_seamless:
        if CINEMA_SEAMLESS_TEMPLATE_FILE.is_file():
            try:
                raw = json.loads(CINEMA_SEAMLESS_TEMPLATE_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    raw["schema"] = CINEMA_SEAMLESS_SCHEMA
                    raw["studio_mode"] = "seamless"
                    raw["seamless"] = True
                    return raw
            except Exception:
                pass
        return _blank_seamless_template()
    if CINEMA_JSON_TEMPLATE_FILE.is_file():
        try:
            raw = json.loads(CINEMA_JSON_TEMPLATE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw["schema"] = CINEMA_JSON_SCHEMA
                return raw
        except Exception:
            pass
    return {
        "schema": CINEMA_JSON_SCHEMA,
        "title": "",
        "logline": "",
        "look": "auto",
        "setup": {
            "look": "auto",
            "camera": "auto",
            "palette": "auto",
            "lighting": "auto",
            "era": "auto",
            "purpose": "short_film",
            "style": "realistic",
        },
        "duration": 5,
        "quality": "736",
        "steps": 18,
        "characters": [
            {
                "name": "",
                "notes": "",
                "voice": "",
                "trigger": "",
                "lora_id": "",
                "lora_strength": 0.8,
            }
        ],
        "locations": [{"name": "", "notes": "", "trigger": ""}],
        "creatures": [{"name": "", "notes": "", "trigger": ""}],
        # Fallback: 12×5s = 60s (full template lives in schemas/h3-cinema-v1.example.json)
        "sections": [
            {
                "mode": "t2v" if i == 0 else "continue",
                "title": "",
                "location": "",
                "character": "",
                "action": "",
                "dialogue": "",
                "dialogue_lang": "auto",
                "camera": "",
                "visual_style": "",
                "audio": "",
                "music": "N/A",
                "important": "",
            }
            for i in range(12)
        ],
    }


def _asset_public(asset: Any, kind: str) -> dict[str, Any]:
    """Text-only asset card for portable JSON (no binary refs required)."""
    item = _clean_asset(asset if isinstance(asset, dict) else {}, kind)
    out: dict[str, Any] = {
        "name": item.get("name") or "",
        "notes": item.get("notes") or "",
    }
    if kind == "character":
        out["voice"] = item.get("voice") or ""
        if item.get("lora_id"):
            out["lora_id"] = item.get("lora_id") or ""
            out["lora_strength"] = item.get("lora_strength") or 0.8
    if item.get("trigger") and item.get("trigger") != item.get("name"):
        out["trigger"] = item.get("trigger") or ""
    return out


def _section_from_shot(shot: Any) -> dict[str, Any]:
    if not isinstance(shot, dict):
        return {"text": str(shot or "").strip(), "mode": "t2v"}
    structured = _clean_structured(shot.get("structured"))
    has_struct = _has_author_fields(structured)
    mode = str(shot.get("mode") or "t2v").strip().lower()
    if mode not in ("continue", "devam", "i2v", "last_frame"):
        mode = "t2v"
    else:
        mode = "continue"
    row: dict[str, Any] = {"type": "continue" if mode == "continue" else "new"}
    section_id = str(shot.get("section_id") or shot.get("sectionId") or "").strip()
    if section_id:
        row["id"] = section_id
    duration = shot.get("durationSec") or shot.get("duration")
    if duration not in (None, ""):
        try:
            row["duration"] = max(1, int(duration))
        except Exception:
            pass
    if has_struct:
        if structured.get("title"):
            row["title"] = structured["title"]
        if structured.get("location"):
            row["scene"] = structured["location"]
        if structured.get("character"):
            row["characters"] = structured["character"]
        if structured.get("action"):
            row["prompt"] = structured["action"]
        # Preserve optional advanced values when an older project has them.
        for key in ("dialogue", "dialogue_lang", "camera", "visual_style", "audio", "music", "important"):
            val = structured.get(key) or ""
            if val and not (key == "dialogue_lang" and val.lower() == "auto"):
                row[key] = val
    else:
        text = str(shot.get("text") or shot.get("h3Prompt") or shot.get("prompt") or "").strip()
        if text:
            row["text"] = text
    return row


def _shot_from_section(item: Any, index: int, look_id: str = "") -> dict[str, Any]:
    if isinstance(item, str):
        return _clean_shot(
            {"text": item, "mode": "t2v" if index == 0 else "continue"},
            index,
            look_id=look_id,
        )
    if not isinstance(item, dict):
        return _clean_shot({"text": "", "mode": "t2v"}, index, look_id=look_id)
    structured_raw = item.get("structured")
    if not isinstance(structured_raw, dict):
        structured_raw = {k: item.get(k) for k in _STRUCTURED_KEYS if item.get(k) not in (None, "")}
    structured = _clean_structured(structured_raw)
    # Portable section JSON uses simple, readable keys. Map them to the
    # internal fields without compiling away the supplied prompt or scene.
    if not structured.get("location") and item.get("scene") not in (None, ""):
        structured["location"] = str(item.get("scene") or "").strip()
    characters = item.get("characters") or item.get("character")
    if not structured.get("character") and characters not in (None, ""):
        if isinstance(characters, (list, tuple)):
            characters = ", ".join(str(x).strip() for x in characters if str(x).strip())
        structured["character"] = str(characters or "").strip()
    if not structured.get("action") and item.get("prompt") not in (None, ""):
        structured["action"] = str(item.get("prompt") or "").strip()
    section_type = str(item.get("type") or "").strip().lower()
    mode = str(
        item.get("mode")
        or ("continue" if section_type in ("continue", "devam") else "t2v" if section_type in ("new", "t2v") else ("t2v" if index == 0 else "continue"))
    ).strip().lower()
    text = str(
        item.get("text") or item.get("h3Prompt") or item.get("prompt") or item.get("action") or ""
    ).strip()
    if not _has_author_fields(structured) and text:
        parsed = parse_h3_prompt(text)
        if _has_author_fields(parsed):
            structured = parsed
    payload: dict[str, Any] = {
        "mode": mode,
        "text": text,
        "section_id": item.get("id") or item.get("section_id") or "",
        "mode_locked": bool(item.get("type") or item.get("mode")),
    }
    if item.get("duration") not in (None, ""):
        payload["durationSec"] = item.get("duration")
    if _has_author_fields(structured):
        payload["structured"] = structured
    for key in ("take_index", "take_title", "take_id"):
        if item.get(key) not in (None, ""):
            payload[key] = item.get(key)
    return _clean_shot(payload, index, look_id=look_id)


def export_project_json() -> dict[str, Any]:
    """Portable film package: cast + structured sections (LLM-friendly)."""
    data = load()
    look_id = str((_clean_setup(data.get("setup")).get("look") or "")).strip()
    studio_mode = _clean_studio_mode(data.get("studio_mode"))
    seamless = studio_mode == "seamless"
    shots = [s for s in (data.get("shots") or []) if isinstance(s, dict)]
    payload: dict[str, Any] = {
        "schema": CINEMA_SEAMLESS_SCHEMA if seamless else CINEMA_JSON_SCHEMA,
        "studio_mode": studio_mode or "assets",
        "seamless": seamless,
        "title": str(data.get("title") or "").strip(),
        "logline": str(data.get("role_script") or "").strip()[:4000],
        "setup": _clean_setup(data.get("setup")),
        "duration": int(data.get("duration") or 5),
        "quality": str(data.get("quality") or "720"),
        "steps": int(data.get("steps") or 20),
        "characters": [_asset_public(x, "character") for x in (data.get("characters") or [])],
        "locations": [_asset_public(x, "location") for x in (data.get("locations") or [])],
        "creatures": [_asset_public(x, "creature") for x in (data.get("creatures") or [])],
        "sections": [_section_from_shot(s) for s in shots],
        "look": look_id,
    }
    if seamless:
        payload["takes"] = _takes_from_shots(shots)
    return payload


def _coerce_project_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raise ValueError("JSON nesne olmalı")
    # Allow wrappers from external tools
    for key in ("film", "cinema", "project", "data"):
        nested = raw.get(key)
        if isinstance(nested, dict) and (
            nested.get("sections")
            or nested.get("shots")
            or nested.get("scenes")
            or nested.get("takes")
            or nested.get("characters")
        ):
            raw = nested
            break
    return raw


def import_project_json(
    raw: Any,
    *,
    mode: str = "replace",
    save_to_library: bool = False,
    new_film: bool = True,
    keep_stills: bool = True,
    redo_characters: bool = False,
) -> dict[str, Any]:
    """
    Build cinema cast + sections from portable JSON.

    mode:
      - replace: overwrite characters/locations/creatures/shots from JSON
      - merge: merge assets by name; replace shots when sections present
    """
    payload = _coerce_project_payload(raw)
    user_meta = payload.get("_user") if isinstance(payload.get("_user"), dict) else {}
    # Drop AI briefing / meta keys (e.g. _instructions) if the filler forgot to delete them
    payload = {
        k: v
        for k, v in payload.items()
        if not (isinstance(k, str) and k.startswith("_"))
    }
    seamless_pkg = is_seamless_package(payload)
    warnings: list[str] = []
    mode_l = (mode or "replace").strip().lower()
    if mode_l not in ("replace", "merge"):
        mode_l = "replace"

    setup_raw = payload.get("setup") if isinstance(payload.get("setup"), dict) else {}
    look_hint = str(payload.get("look") or setup_raw.get("look") or "").strip()

    take_blocks = extract_take_blocks(payload)
    sections = (
        []
        if take_blocks
        else payload.get("sections")
        if isinstance(payload.get("sections"), list)
        else payload.get("shots")
        if isinstance(payload.get("shots"), list)
        else payload.get("scenes")
        if isinstance(payload.get("scenes"), list)
        else []
    )
    if take_blocks:
        shots = _shots_from_take_blocks(take_blocks, look_id=look_hint, warnings=warnings)
    else:
        shots = [
            _shot_from_section(item, i, look_id=look_hint)
            for i, item in enumerate(sections)
            if isinstance(item, (dict, str))
        ]
        shots = [s for s in shots if s.get("text") or s.get("structured")]
        if seamless_pkg and shots:
            _stamp_flat_takes(shots)
            takes = (len(shots) + SEAMLESS_MAX_SHOTS - 1) // SEAMLESS_MAX_SHOTS
            warnings.append(
                f"Kesintisiz {len(shots)} shot → {takes} take "
                f"({SEAMLESS_MAX_SHOTS} shot/take, örn. 8×5sn = 40sn)"
            )

    chars_in = payload.get("characters") or payload.get("cast") or []
    locs_in = payload.get("locations") or payload.get("places") or []
    creatures_in = payload.get("creatures") or payload.get("monsters") or []

    # Archive current before replace-into-new-film
    cur = load()
    if new_film and mode_l == "replace":
        try:
            save(cur)
        except Exception:
            pass
        data = json.loads(json.dumps(_EMPTY))
        data["film_id"] = uuid.uuid4().hex[:10]
    else:
        data = cur

    title = str(payload.get("title") or payload.get("name") or data.get("title") or "").strip()
    about = str(payload.get("about") or user_meta.get("about") or "").strip()
    logline = str(
        payload.get("logline") or payload.get("role_script") or about or ""
    ).strip()
    if title:
        data["title"] = title
    if logline:
        data["role_script"] = logline

    if isinstance(payload.get("setup"), dict):
        data["setup"] = _clean_setup({**_clean_setup(data.get("setup")), **payload["setup"]})
    elif look_hint:
        setup = _clean_setup(data.get("setup"))
        setup["look"] = look_hint
        data["setup"] = setup

    for key in ("duration", "quality", "steps"):
        if payload.get(key) is not None:
            data[key] = payload.get(key)
    if seamless_pkg:
        data["studio_mode"] = "seamless"
        if payload.get("duration") is None:
            data["duration"] = SEAMLESS_DEFAULT_DURATION
    elif _clean_studio_mode(payload.get("studio_mode")):
        data["studio_mode"] = _clean_studio_mode(payload.get("studio_mode"))

    if mode_l == "replace":
        data["characters"] = _merge_named_assets("character", [], chars_in)
        data["locations"] = _merge_named_assets("location", [], locs_in)
        data["creatures"] = _merge_named_assets("creature", [], creatures_in)
        if shots:
            data["shots"] = shots
        elif sections == [] and (chars_in or locs_in or creatures_in):
            # Cast-only package — keep existing shots unless empty film
            data.setdefault("shots", data.get("shots") or [])
        else:
            data["shots"] = shots
    else:
        data["characters"] = _merge_named_assets(
            "character", data.get("characters") or [], chars_in
        )
        data["locations"] = _merge_named_assets(
            "location", data.get("locations") or [], locs_in
        )
        data["creatures"] = _merge_named_assets(
            "creature", data.get("creatures") or [], creatures_in
        )
        if shots:
            data["shots"] = shots

    stills_kept = {"characters": 0, "locations": 0, "creatures": 0}
    if keep_stills:
        lib_assets = load_library()
        data["locations"], stills_kept["locations"] = _adopt_stills_by_name(
            data.get("locations") or [],
            cur.get("locations") or [],
            lib_assets.get("locations") or [],
        )
        data["creatures"], stills_kept["creatures"] = _adopt_stills_by_name(
            data.get("creatures") or [],
            cur.get("creatures") or [],
            lib_assets.get("creatures") or [],
        )
        if not redo_characters and not seamless_pkg:
            data["characters"], stills_kept["characters"] = _adopt_stills_by_name(
                data.get("characters") or [],
                cur.get("characters") or [],
                lib_assets.get("characters") or [],
            )

    out = save(data)

    if save_to_library:
        for kind, key in (
            ("character", "characters"),
            ("location", "locations"),
            ("creature", "creatures"),
        ):
            for asset in out.get(key) or []:
                if not str(asset.get("name") or "").strip():
                    continue
                try:
                    save_film_asset_to_library(kind, str(asset.get("id") or ""))
                except Exception:
                    pass

    if seamless_pkg:
        for ch in out.get("characters") or []:
            if character_portrait_files(ch):
                warnings.append(
                    "Kartta portre var — Üret Kesintisiz yerine yüz kilitli Continue’a düşer"
                )
                break

    return {
        "ok": True,
        "schema": CINEMA_SEAMLESS_SCHEMA if seamless_pkg else CINEMA_JSON_SCHEMA,
        "studio_mode": "seamless" if seamless_pkg else (_clean_studio_mode(out.get("studio_mode")) or "assets"),
        "seamless": bool(seamless_pkg),
        "mode": mode_l,
        "title": out.get("title") or "",
        "film_id": out.get("film_id") or "",
        "counts": {
            "characters": len(out.get("characters") or []),
            "locations": len(out.get("locations") or []),
            "creatures": len(out.get("creatures") or []),
            "sections": len(out.get("shots") or []),
            "takes": len(
                {
                    int(s.get("take_index") or 0)
                    for s in (out.get("shots") or [])
                    if isinstance(s, dict) and s.get("take_index") not in (None, "", 0)
                }
            ),
        },
        "stills_kept": stills_kept,
        "warnings": warnings,
        "cinema": out,
    }


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
