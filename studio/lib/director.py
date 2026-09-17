"""Director interview → FilmBrief helper."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Optional

PROMPTS = Path(__file__).resolve().parent.parent / "prompts" / "director_system.md"
H3_SKILL_DIR = Path(__file__).resolve().parent.parent / "prompts" / "h3_skill"
CLIP_DURATIONS = (4, 5, 6, 8, 10, 15)

# MiniMax H3 looks the model can actually hold — craft line goes into SCENE close.
VISUAL_STYLES: dict[str, str] = {
    "realistic": (
        "photorealistic live-action cinematography, natural skin texture, "
        "realistic reflections, film grain"
    ),
    "anime": (
        "high-end Japanese 2D anime cinematic, cel shading, sakuga motion, "
        "detailed painted backgrounds — not live-action"
    ),
    "disney": (
        "Disney/Pixar-quality 3D character animation, appealing proportions, "
        "subsurface scattering, stylized (not photoreal) faces, studio lighting"
    ),
    "game": (
        "AAA video-game cinematic (Unreal Engine 5), ray-traced lighting, "
        "game-character look, cinematic in-engine camera"
    ),
    "cgi_3d": (
        "premium 3D CGI animation, physically based rendering, "
        "cinematic studio lighting — not live-action"
    ),
    "comic": (
        "stylized comic-book cinematic, inked linework, graphic color blocking, "
        "halftone accents"
    ),
    "illustration": (
        "illustrated storybook cinematic, painterly 2D, storybook lighting"
    ),
    "oil_paint": (
        "oil-painting animated cinematic, visible brushstrokes, classical palette"
    ),
    "clay": (
        "claymation / stop-motion look, tactile clay surfaces, miniature set lighting"
    ),
    "found_footage": (
        "handheld found-footage documentary camera, natural light, raw texture"
    ),
}

ALLOWED_PURPOSES = (
    "short_film",
    "music_video",
    "ad",
    "trailer",
    "social",
    "documentary",
    "intro",
    "outro",
)

_STYLE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("found_footage", ("found footage", "found_footage", "el kamera", "belgesel kamera")),
    ("clay", ("claymation", "kil animasyon", "stop-motion", "stop motion", "clay")),
    ("oil_paint", ("oil paint", "oil-paint", "yağlı boya", "oil_paint")),
    ("illustration", ("illustration", "illüstrasyon", "storybook", "illustration")),
    ("comic", ("comic", "çizgi roman", "graphic novel")),
    ("disney", ("disney", "pixar", "dreamworks")),
    ("cgi_3d", ("cgi_3d", "3d cgi", "cgi ", "3d animasyon")),
    ("game", ("unreal", "video game", "oyun tarz", "oyun sinematik", "game cinematic", "aaa game")),
    ("anime", ("anime", "ghibli", "sakuga")),
    ("realistic", ("photoreal", "gerçekçi", "live-action", "realistic")),
)


def normalize_style(value: Any = None, raw: str = "") -> str:
    v = str(value or "").lower().strip()
    if v in VISUAL_STYLES:
        return v
    if v in ("oyun", "pixar", "3d"):
        return {"oyun": "game", "pixar": "disney", "3d": "cgi_3d"}[v]
    blob = f"{v} {raw or ''}".lower()
    for key, needles in _STYLE_ALIASES:
        if any(n in blob for n in needles):
            return key
    return "realistic"


def style_craft_line(style: Any) -> str:
    key = normalize_style(style)
    return VISUAL_STYLES.get(key, VISUAL_STYLES["realistic"])


def normalize_purpose(value: Any = None, raw: str = "") -> str:
    v = str(value or "").lower().strip().replace("-", "_")
    if v in ALLOWED_PURPOSES:
        return v
    blob = f"{v} {raw or ''}".lower()
    pairs = (
        ("music_video", ("müzik klibi", "music_video")),
        ("documentary", ("belgesel",)),
        ("intro", ("açılış",)),
        ("outro", ("kapanış", "jenerik")),
        ("trailer", ("fragman",)),
        ("ad", ("reklam",)),
        ("social", ("sosyal", "reels")),
        ("short_film", ("kısa film", "short_film")),
    )
    for key, needles in pairs:
        if any(n in blob for n in needles):
            return key
    return "short_film"

H3_PROMPT_GUIDE = (
    "Each h3Prompt is a CINEMATIC SCENE SCREENPLAY in English (NOT keyword prompts). "
    "Multi-paragraph ≥1100 chars: world open (location/light/props); full character cards "
    "(age, face, hair, eyes, build, exact wardrobe — identical across shots); "
    "beat-by-beat micro-actions (notice, look, smile, step — never vague); "
    "camera height/lens/move/focus; atmosphere line; technical close "
    "MUST MATCH visualStyle (photoreal / anime / Disney-Pixar 3D / game cinematic / "
    "CGI / comic / illustration / oil paint / claymation / found-footage — never "
    "write photoreal skin if the style is Disney/anime/game); end with "
    "'One continuous shot, no cuts'. "
    "Continue shots MUST start with 'Continue directly from the previous shot.' "
    "then Same X, same Y, identical clothing locks. "
    "SPOKEN DIALOGUE (non-music-video): ALWAYS wrap lines as "
    "<d>[English] Exact words.</d> or <d>[Turkish] …</d> — never bare quotes "
    "and never bare [English] without <d>…</d>. Mouth moves in sync; audible speech. "
    "NON-MUSIC-VIDEO AUDIO: diegetic SFX + dialogue ONLY — NO BGM/score/underscore. "
    "Music video / silentAudio: no dialogue tags, silent visual only. "
    "Write like a director's shot notes (Arrival/Shadow/No Substitute quality), "
    "never like 'cinematic shot of X, dark mood, 35mm'."
)

SILENT_MUSIC_VIDEO_LOCK = (
    "SILENT VISUAL ONLY for music video: no spoken dialogue, no singing lipsync, "
    "no generated music, no sound effects, no diegetic audio description. "
    "Picture-only cinematic performance; final song will be muxed later. "
    "One continuous shot, no cuts, no dialogue, silent."
)

# Formerly appended a long "AUDIO POLICY" block to every prompt. Models ignored it
# (and often treated the SFX list as content to invent). Do not reinject it.
_AUDIO_POLICY_BLOCK = re.compile(
    r"(?:\n\s*)*AUDIO POLICY\s*[—\-].*?(?=\n\n|\Z)",
    re.I | re.S,
)

_DIALOGUE_LANGS = (
    "English|Turkish|Japanese|Korean|Chinese|Spanish|French|German|"
    "Italian|Portuguese|Russian|Arabic|Hindi"
)
_BARE_LANG_LINE = re.compile(
    rf"\[({_DIALOGUE_LANGS})\]\s*([^\n<]+)",
    re.I,
)


def _is_silent_brief(brief: dict[str, Any]) -> bool:
    if "silentAudio" in (brief or {}):
        return bool(brief.get("silentAudio"))
    purpose = (brief.get("purpose") or "").lower().strip()
    return purpose in (
        "music_video",
        "music-video",
        "muzik_klibi",
    )


def normalize_dialogue_tag(text: str, default_lang: str = "English") -> str:
    """Force MiniMax H3 spoken-dialogue form: <d>[Lang] line</d>."""
    t = (text or "").strip()
    if not t:
        return ""
    m = re.search(r"<d>\s*(.*?)\s*</d>", t, re.I | re.S)
    if m:
        inner = m.group(1).strip()
        lang_m = re.match(r"\[([^\]]+)\]\s*(.*)", inner, re.S)
        if lang_m:
            lang = lang_m.group(1).strip()
            line = lang_m.group(2).strip().strip("\"'")
            return f"<d>[{lang}] {line}</d>"
        line = inner.strip().strip("\"'")
        lang = "Turkish" if re.search(r"[ğüşıöçĞÜŞİÖÇ]", line) else default_lang
        return f"<d>[{lang}] {line}</d>"
    lang_m = re.match(rf"\[({_DIALOGUE_LANGS})\]\s*(.*)", t, re.I | re.S)
    if lang_m:
        lang = lang_m.group(1).strip()
        line = lang_m.group(2).strip().strip("\"'")
        return f"<d>[{lang}] {line}</d>"
    line = t.strip().strip("\"'")
    if re.search(r"[ğüşıöçĞÜŞİÖÇ]", line):
        lang = "Turkish"
    elif re.search(r"[A-Za-z]{3,}", line):
        lang = "English"
    else:
        lang = default_lang
    return f"<d>[{lang}] {line}</d>"


def upgrade_inline_dialogue_tags(prompt: str) -> str:
    """Upgrade bare [English] lines inside a SCENE prompt to <d>…</d>."""
    p = prompt or ""
    if not p.strip():
        return p
    protected: list[str] = []

    def _protect(m: re.Match[str]) -> str:
        protected.append(m.group(0))
        return f"\x00D{len(protected) - 1}\x00"

    p2 = re.sub(r"<d>.*?</d>", _protect, p, flags=re.I | re.S)
    p2 = _BARE_LANG_LINE.sub(
        lambda m: f"<d>[{m.group(1)}] {m.group(2).strip().rstrip()}</d>",
        p2,
    )
    for i, orig in enumerate(protected):
        p2 = p2.replace(f"\x00D{i}\x00", orig)
    return p2


def ensure_dialogue_in_h3_prompt(
    prompt: str,
    dialogues: list[str],
    *,
    silent: bool,
) -> str:
    """Ensure spoken lines use <d> tags and appear in the SCENE body (non-silent)."""
    p = upgrade_inline_dialogue_tags((prompt or "").strip())
    if silent:
        return p
    tags = [normalize_dialogue_tag(d) for d in (dialogues or []) if str(d).strip()]
    tags = [t for t in tags if t]
    if not tags:
        return p
    missing: list[str] = []
    plow = p.lower()
    for tag in tags:
        inner = re.sub(r"</?d>", "", tag, flags=re.I)
        spoken = re.sub(r"^\[[^\]]+\]\s*", "", inner).strip()
        if tag.lower() in plow:
            continue
        if spoken and spoken.lower() in plow:
            # spoken text present but not tagged — already upgraded by upgrade_inline
            continue
        missing.append(tag)
    if missing:
        p = (
            p
            + "\n\nSpoken dialogue (must be audible, lipsync): "
            + " ".join(missing)
            + "\nClear spoken dialogue audio, mouth moves in sync with the words."
        ).strip()
    elif "<d>" in p.lower() and "mouth moves" not in plow and "lipsync" not in plow:
        p = (p + "\nClear spoken dialogue audio, mouth moves in sync with the words.").strip()
    return p


def apply_audio_policy(prompt: str, brief: dict[str, Any]) -> str:
    """Music-video silent lock only. Strip legacy AUDIO POLICY blobs; do not re-append them."""
    silent = _is_silent_brief(brief)
    p = _AUDIO_POLICY_BLOCK.sub("", (prompt or "").strip()).strip()
    if silent:
        low = p.lower()
        if "silent visual only" in low or "no generated music" in low:
            return p
        return (p + "\n\n" + SILENT_MUSIC_VIDEO_LOCK).strip()
    return upgrade_inline_dialogue_tags(p)


def system_prompt() -> str:
    base = PROMPTS.read_text(encoding="utf-8") if PROMPTS.exists() else ""
    skill_bits: list[str] = []
    skill_md = H3_SKILL_DIR / "SKILL.md"
    base_en = H3_SKILL_DIR / "base-en.txt"
    if skill_md.exists():
        skill_bits.append(skill_md.read_text(encoding="utf-8")[:4000])
    if base_en.exists():
        # Keep the structure rules; trim long case dump for context size
        txt = base_en.read_text(encoding="utf-8")
        skill_bits.append(txt[:9000])
    if skill_bits:
        base = (
            (base or "")
            + "\n\n---\n# Official MiniMax H3 prompt skill (follow structure)\n\n"
            + "\n\n".join(skill_bits)
            + "\n\nFor Studio briefs: keep cinematic SCENE quality; "
            "prefer `non_diegetic_music: N/A` unless the user wants score. "
            "Dialogue stays in `<d>[Lang]…</d>`.\n"
        )
    if base:
        return base
    return "You are the H3 Studio director. Speak the Studio UI language. Return JSON when the brief is ready."


PLAN_MODE_ADDENDUM = """
## PLAN MODU (şu an açık)
Üretim yok. Shot tahtası kaynak gerçekliktir — sohbet özetine güvenme.

Kullanıcı shot düzenletiyorsa TÜM brief'i baştan yazma. Sadece değişen shot'lar:

```json
{
  "ready": true,
  "reply": "Shot 3 kamerayı alçalttım, replik aynı.",
  "patch": {
    "shot": 3,
    "camera": "low tracking 35mm",
    "action": "kısa özet",
    "dialogue": ["<d>[English] …</d>"],
    "h3Prompt": "FULL SCENE body for that shot only"
  }
}
```

Birden fazla shot: `"patches": [{ "shot": 2, ... }, { "shot": 5, ... }]`.
`shot` 1-indexed. h3Prompt kalitesi GOLD STANDARD (continue lock shot 2+).
**Kamera / açı değişince** `camera` alanını güncelle VE `h3Prompt` içindeki `The camera:` paragrafını aynı çerçeveyle yeniden yaz — eski açıyı bırakma.
Kullanıcı global açı istediğinde (`hep low angle`, `her shot farklı açı`) tüm outline / patch'lerde bunu uygula.
Türkçe `reply` ile ne değiştiğini söyle. Üretime alma, kuyruk yok.
"""

DEFAULT_CAMERA = "eye-level medium, subtle push-in, 35mm"

GENERIC_CAMERAS = frozenset(
    {
        DEFAULT_CAMERA.lower(),
        "eye-level medium shot, subtle push-in, 35mm",
    }
)

CAMERA_VARIETY: tuple[str, ...] = (
    "low angle slow push-in, 35mm, shallow depth of field",
    "tight medium close-up with subtle lateral drift, 50mm",
    "high angle wide establishing, 24mm, deep focus",
    "slow circular orbit at medium distance, 35mm",
    "low tracking shot parallel to the subject, 35mm",
    "pull-back reveal from medium to wide, 35mm",
    "over-the-shoulder handheld, 40mm, shallow depth of field",
    "Dutch angle medium shot with slow push, 32mm",
    "bird's-eye top-down descending, wide lens",
    "extreme close-up on eyes or hands, 85mm shallow depth of field",
)

_ORDINAL_SHOT = {
    "birinci": 1,
    "ikinci": 2,
    "üçüncü": 3,
    "ucuncu": 3,
    "dördüncü": 4,
    "dorduncu": 4,
    "beşinci": 5,
    "besinci": 5,
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
}

_CAMERA_TOPIC = re.compile(
    r"(?:"
    r"low\s*angle|high\s*angle|bird['\s-]*s?\s*eye|dutch|close[\s-]*up|extreme\s+close|"
    r"wide\s+shot|medium\s+shot|over[\s-]*the[\s-]*shoulder|tracking|orbit|push[\s-]*in|"
    r"pull[\s-]*back|handheld|pov|üstten|alttan|geniş\s+plan|yakın\s+plan|"
    r"kuşbakışı|kuş\s*bakışı|karşıdan|karşı|önden|yüzüne|yüzüme|"
    r"açı|kamera|framing|lens|35mm|50mm|24mm|85mm|anamorphic"
    r")",
    re.I,
)

_VARY_ANGLES = re.compile(
    r"(?:"
    r"farklı\s+açı|her\s+shot.{0,24}açı|çeşitli\s+kamera|açı\s+değiştir|"
    r"vary.{0,12}(?:angle|camera)|different.{0,20}(?:angle|camera|framing)|"
    r"rotate.{0,12}camera|never\s+same\s+(?:angle|camera)"
    r")",
    re.I,
)


def _is_generic_camera(camera: Any) -> bool:
    c = str(camera or "").strip().lower()
    if not c:
        return True
    if c in GENERIC_CAMERAS:
        return True
    return "eye-level medium" in c and "35mm" in c and "push" in c


def _strip_user_prefix(text: str) -> str:
    t = str(text or "").strip()
    t = re.sub(r"^\[proje:[^\]]+\]\s*", "", t, flags=re.I)
    t = re.sub(r"^\[sinema stüdyosu\]\s*", "", t, flags=re.I)
    return t.strip()


def extract_director_directives(messages: list[Any]) -> dict[str, Any]:
    """Mine user chat for camera / framing directives (global, per-shot, vary)."""
    global_camera = ""
    per_shot: dict[int, str] = {}
    vary_angles = False
    notes: list[str] = []

    for m in messages or []:
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        raw = _strip_user_prefix(str(m.get("content") or ""))
        if not raw or not _CAMERA_TOPIC.search(raw):
            if _VARY_ANGLES.search(raw):
                vary_angles = True
                notes.append(raw[:500])
            continue
        notes.append(raw[:500])
        if _VARY_ANGLES.search(raw):
            vary_angles = True

        for m2 in re.finditer(
            r"(?:shot|plan)\s*#?\s*(\d+)|(\d+)\s*[\.)]\s*(?:shot|plan)",
            raw,
            flags=re.I,
        ):
            idx = int(m2.group(1) or m2.group(2) or 0)
            if idx < 1:
                continue
            tail = raw[m2.end() : m2.end() + 160].strip(" :—-.,;")
            per_shot[idx] = tail or raw[:200]

        for m2 in re.finditer(
            r"\b(birinci|ikinci|üçüncü|ucuncu|dördüncü|dorduncu|beşinci|besinci|"
            r"first|second|third|fourth|fifth)\s+(?:shot|plan)\b",
            raw,
            flags=re.I,
        ):
            idx = _ORDINAL_SHOT.get(m2.group(1).lower(), 0)
            if idx < 1:
                continue
            tail = raw[m2.end() : m2.end() + 160].strip(" :—-.,;")
            per_shot[idx] = tail or raw[:200]

        if re.search(
            r"(?:hep|her\s+zaman|always|tüm\s+shot|all\s+shots|every\s+shot|bütün)",
            raw,
            flags=re.I,
        ):
            global_camera = raw[:240]

    return {
        "globalCamera": global_camera,
        "perShot": per_shot,
        "varyAngles": vary_angles,
        "notes": notes[-8:],
    }


def merge_session_directives(
    brief: dict[str, Any],
    sess: Optional[dict[str, Any]],
) -> dict[str, Any]:
    out = dict(brief or {})
    messages = list((sess or {}).get("messages") or [])
    directives = extract_director_directives(messages)
    if directives.get("notes") or directives.get("globalCamera") or directives.get("perShot"):
        out["directorDirectives"] = directives
    elif out.get("directorDirectives"):
        directives = out["directorDirectives"]
    else:
        out = merge_user_scene_into_brief(out, sess)
        return out
    outline = normalize_shot_outline(out)
    if outline:
        need = int(out.get("expectedShotCount") or len(outline) or 0)
        outline = apply_directives_to_outline(outline, directives, need)
        outline = diversify_outline_cameras(outline, directives)
        out["shotOutline"] = outline
    out = merge_user_scene_into_brief(out, sess)
    return out


def format_directives_block(directives: Optional[dict[str, Any]]) -> str:
    if not isinstance(directives, dict):
        return ""
    parts: list[str] = []
    if directives.get("varyAngles"):
        parts.append(
            "VARY CAMERA: use a different height/lens/movement on EVERY shot — "
            "never repeat the same framing twice in a row."
        )
    if directives.get("globalCamera"):
        parts.append(f"GLOBAL CAMERA LOCK: {directives['globalCamera']}")
    per = directives.get("perShot") or {}
    if isinstance(per, dict) and per:
        lines = [f"  shot {k}: {v}" for k, v in sorted(per.items(), key=lambda x: int(x[0]))]
        parts.append("PER-SHOT CAMERA (exact):\n" + "\n".join(lines))
    notes = directives.get("notes") or []
    if notes:
        parts.append(
            "USER CAMERA / FRAMING NOTES (highest priority — obey exactly):\n"
            + "\n---\n".join(str(n) for n in notes[-4:])
        )
    if not parts:
        return ""
    return "\n## DIRECTOR CAMERA DIRECTIVES (mandatory)\n" + "\n".join(parts) + "\n"


def camera_for_outline_index(
    index: int,
    *,
    directives: Optional[dict[str, Any]] = None,
    row: Optional[dict[str, Any]] = None,
) -> str:
    """Resolve camera string for outline row `index` (0-based)."""
    d = directives or {}
    per = d.get("perShot") if isinstance(d.get("perShot"), dict) else {}
    if per.get(index + 1):
        return str(per[index + 1]).strip()
    row_cam = str((row or {}).get("camera") or "").strip()
    if row_cam and not _is_generic_camera(row_cam):
        return row_cam
    if d.get("globalCamera"):
        return str(d["globalCamera"]).strip()
    if d.get("varyAngles") or not row_cam or _is_generic_camera(row_cam):
        return CAMERA_VARIETY[index % len(CAMERA_VARIETY)]
    return row_cam or DEFAULT_CAMERA


def apply_directives_to_outline(
    outline: list[dict[str, Any]],
    directives: Optional[dict[str, Any]],
    need: int,
) -> list[dict[str, Any]]:
    if not outline:
        return outline
    d = directives or {}
    out: list[dict[str, Any]] = []
    for i, row in enumerate(outline):
        r = dict(row)
        r["camera"] = camera_for_outline_index(i, directives=d, row=r)
        out.append(r)
    return out[:need] if need else out


def diversify_outline_cameras(
    outline: list[dict[str, Any]],
    directives: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """When every row still shares the generic default, assign variety."""
    if not outline:
        return outline
    d = directives or {}
    if d.get("globalCamera") and not d.get("varyAngles"):
        cam = str(d["globalCamera"]).strip()
        return [{**row, "camera": cam} for row in outline]
    cams = [str(r.get("camera") or "").strip() for r in outline]
    if len(outline) > 1 and all(_is_generic_camera(c) for c in cams):
        return [
            {**row, "camera": CAMERA_VARIETY[i % len(CAMERA_VARIETY)]}
            for i, row in enumerate(outline)
        ]
    if d.get("varyAngles") and len(outline) > 1:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for i, row in enumerate(outline):
            r = dict(row)
            cam = camera_for_outline_index(i, directives=d, row=r)
            if cam.lower() in seen:
                cam = CAMERA_VARIETY[i % len(CAMERA_VARIETY)]
            seen.add(cam.lower())
            r["camera"] = cam
            out.append(r)
        return out
    return outline


def ensure_camera_in_h3_prompt(body: str, camera: str, *, force: bool = False) -> str:
    """Inject or replace the camera paragraph so h3Prompt matches shot.camera."""
    cam = str(camera or "").strip()
    text = str(body or "").strip()
    if not text or not cam or _is_generic_camera(cam):
        return text
    core = cam.lower()[:28]
    if not force and core in text.lower():
        return text
    cam_line = f"The camera: {cam}."
    replaced = re.sub(
        r"The camera:\s*[^\n]+",
        cam_line,
        text,
        count=1,
        flags=re.I,
    )
    if replaced != text:
        return replaced
    for marker in (
        "One continuous shot",
        "Photorealistic",
        "Stay locked in this look",
        "Diegetic soundscape",
    ):
        pos = text.find(marker)
        if pos > 40:
            return text[:pos].rstrip() + "\n\n" + cam_line + "\n\n" + text[pos:]
    return text.rstrip() + "\n\n" + cam_line


def sync_shot_outline_from_shots(brief: dict[str, Any]) -> dict[str, Any]:
    """Keep shotOutline.camera aligned when shots are patched in Plan mode."""
    out = dict(brief or {})
    shots = out.get("shots") if isinstance(out.get("shots"), list) else []
    outline = normalize_shot_outline(out)
    if not outline and not shots:
        return out
    need = int(out.get("expectedShotCount") or len(shots) or len(outline) or 0)
    merged: list[dict[str, Any]] = []
    for i in range(max(need, len(outline), len(shots))):
        row = dict(outline[i]) if i < len(outline) else {
            "index": i + 1,
            "title": f"Shot {i + 1}",
            "beat": "",
            "camera": DEFAULT_CAMERA,
        }
        if i < len(shots) and isinstance(shots[i], dict):
            s = shots[i]
            if s.get("camera"):
                row["camera"] = str(s["camera"]).strip()
            if s.get("action"):
                row["beat"] = str(s["action"]).strip()
            body = str(s.get("h3Prompt") or "").strip()
            if body and not row.get("beat"):
                row["beat"] = body[:160]
        row["index"] = i + 1
        merged.append(row)
    if need:
        merged = merged[:need]
    out["shotOutline"] = merged
    return out


def parse_camera_from_text(text: str) -> str:
    """Map TR/EN framing hints to a concrete camera line."""
    t = str(text or "").lower()
    if re.search(
        r"kar[sş]idan|karsidan|karşı\s+karşı|önünden|yüzüme|yüzüne|yuzume|yuzune|"
        r"frontal|facing\s+(?:the\s+)?camera|head[\s-]*on",
        t,
    ):
        return (
            "frontal medium shot, subject facing camera directly, eye-level, "
            "50mm, shallow depth of field — subject looks into lens throughout"
        )
    if re.search(r"kuşbakış|bird['\s-]*s?\s*eye|üstten", t):
        return "high angle bird's-eye descending, wide lens, deep focus"
    if re.search(r"alttan|low\s*angle", t):
        return "low angle slow push-in, 35mm, shallow depth of field"
    if re.search(r"yakın\s+plan|close[\s-]*up|extreme\s+close", t):
        return "tight close-up, 85mm, shallow depth of field, subtle drift"
    if re.search(r"geniş\s+plan|wide\s+shot", t):
        return "wide establishing shot, 24mm, deep focus, slow push-in"
    return ""


def scene_action_english_hint(text: str) -> str:
    """Best-effort English beat from a short TR/EN user scene line."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    if not re.search(r"[ğüşıöçĞÜŞİÖÇ]", raw):
        return raw
    t = raw.lower()
    subject = "The subject"
    if re.search(r"rus\s+(?:k[iı]z|kad[iı]n)|russian\s+(?:girl|woman)", t):
        subject = "A young Russian woman"
    props = ""
    if re.search(r"nargile|hookah|shisha", t):
        props = " beside a lit hookah with a glass base and hose"
    actions: list[str] = []
    if re.search(r"içecek|iccek|icecek|çekecek|cek|inhale|draw", t):
        actions.append(
            "lifts the hose mouthpiece to her lips and draws a smooth, controlled inhale — "
            "cheeks softly hollow, throat calm, eyes steady on camera"
        )
    if re.search(r"salacak|verecek|püskür|pusur|exhale|release", t):
        actions.append(
            "holds the smoke a beat, then exhales toward camera: a thick ribbon of white smoke "
            "blooms forward, curling in the practical light before drifting apart"
        )
    if not actions:
        actions.append("performs the described action clearly in one continuous take")
    env = ""
    if re.search(r"nargile|hookah", t):
        env = (
            "Hookah water bubbles faintly in the base; charcoal glows; "
            "ambient room tone and soft exhale SFX only — no music."
        )
    lead = f"{subject}{props}"
    if len(actions) == 1:
        line = f"{lead} {actions[0]}"
    else:
        line = f"{lead} {actions[0]}. Then she " + ". Then she ".join(actions[1:])
    return (line + (f" {env}" if env else "")).strip()


def extract_user_scene_intent(messages: list[Any]) -> dict[str, Any]:
    """Last substantive user line → scene beat, camera, single-shot hint."""
    text = ""
    for m in reversed(messages or []):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        cand = _strip_user_prefix(str(m.get("content") or ""))
        if len(cand) >= 12:
            text = cand
            break
    if not text:
        return {}
    camera = parse_camera_from_text(text)
    beat_en = scene_action_english_hint(text)
    simple = not re.search(
        r"\d+\s*(?:shot|sahne|klip)|shot\s*#?\s*\d|dakika|minute\b|\bfilm\b",
        text,
        flags=re.I,
    )
    return {
        "raw": text,
        "beat": beat_en or text,
        "camera": camera,
        "simpleSingleShot": bool(simple),
        "logline": beat_en or text,
    }


def merge_user_scene_into_brief(
    brief: dict[str, Any],
    sess: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Fold the user's literal scene description into brief + outline (not generic arcs)."""
    intent = extract_user_scene_intent((sess or {}).get("messages") or [])
    if not intent.get("raw"):
        return brief
    out = dict(brief or {})
    out["sceneIntent"] = intent
    ll = str(out.get("logline") or "").strip()
    generic = (
        not ll
        or "fixed character music video" in ll.lower()
        or "scene lighting and blocking evolve" in ll.lower()
        or len(ll) < 12
    )
    if generic:
        out["logline"] = str(intent.get("logline") or intent["raw"])[:400]
    clip = int(out.get("clipDurationSec") or 5)
    if clip not in CLIP_DURATIONS:
        clip = 5
    explicit_need = None
    blob = "\n".join(
        _strip_user_prefix(str(m.get("content") or ""))
        for m in (sess or {}).get("messages") or []
        if isinstance(m, dict) and m.get("role") == "user"
    )
    _tot, need_from_user = infer_duration_and_shots(blob, clip_sec=clip)
    try:
        if out.get("expectedShotCount") is not None:
            explicit_need = int(out["expectedShotCount"])
    except (TypeError, ValueError):
        explicit_need = None
    # Single concrete scene → default 1 shot unless user asked for N shots
    if intent.get("simpleSingleShot") and not need_from_user:
        out["expectedShotCount"] = 1
        out["totalDurationSec"] = clip
    elif need_from_user:
        out["expectedShotCount"] = int(need_from_user)
        out["totalDurationSec"] = max(
            int(out.get("totalDurationSec") or 0),
            int(need_from_user) * clip,
        )
    outline = normalize_shot_outline(out)
    if not outline:
        outline = [
            {
                "index": 1,
                "title": "User scene",
                "beat": intent["beat"],
                "camera": intent.get("camera") or DEFAULT_CAMERA,
            }
        ]
    else:
        row = dict(outline[0])
        row["beat"] = intent["beat"]
        row["title"] = row.get("title") or "User scene"
        if intent.get("camera"):
            row["camera"] = intent["camera"]
        outline[0] = row
    need = int(out.get("expectedShotCount") or len(outline) or 1)
    outline = apply_directives_to_outline(outline, out.get("directorDirectives"), need)
    if intent.get("camera"):
        outline[0]["camera"] = intent["camera"]
    out["shotOutline"] = outline[:need]
    chars = list(out.get("characters") or [])
    if not chars and re.search(r"rus\s+(?:k[iı]z|kad[iı]n)", intent["raw"], re.I):
        out["characters"] = [
            {
                "name": "Elena",
                "description": (
                    "mid-20s Russian woman, cool striking features, fair skin, "
                    "loose light blonde hair, emerald-green eyes, simple black turtleneck"
                ),
            }
        ]
    return out


def build_scene_from_intent(
    *,
    shot: dict[str, Any],
    index: int,
    total: int,
    brief: dict[str, Any],
    intent: dict[str, Any],
) -> str:
    """English SCENE fallback that follows the user's described action (not beat arcs)."""
    dur = int(shot.get("durationSec") or brief.get("clipDurationSec") or 5)
    style = style_craft_line(normalize_style(brief.get("visualStyle")))
    camera = str(
        shot.get("camera")
        or intent.get("camera")
        or parse_camera_from_text(intent.get("raw") or "")
        or DEFAULT_CAMERA
    ).strip()
    beat = str(intent.get("beat") or intent.get("raw") or "").strip()
    silent = _is_silent_brief(brief)
    chars = brief.get("characters") or []
    char_block = ""
    if chars and isinstance(chars[0], dict):
        c0 = chars[0]
        name = (c0.get("name") or "She").strip()
        desc = (c0.get("description") or "consistent look").strip()
        char_block = f"{name}: {desc}. Keep identical face, age, hair, eyes and wardrobe."
    hookah_block = ""
    if re.search(r"nargile|hookah|shisha", intent.get("raw") or "", re.I):
        hookah_block = (
            "A hookah/nargile with glass base and metal stem sits in frame; "
            "charcoal glows; water in the base ripples when she draws."
        )
    paras = [
        f"A {style} scene — shot {index + 1} of {total}, one continuous take (~{dur}s).",
        char_block or "Lead subject holds consistent identity throughout.",
        hookah_block,
        f"Action beat (follow exactly, step by step): {beat}",
        (
            "She keeps frontal eye contact with lens if frontal framing was requested. "
            "Hands, mouth, and smoke read clearly — no cutaways, no time jumps."
        ),
        f"The camera: {camera}.",
        (
            "Diegetic sound only: hookah bubble, soft inhale, exhale rush, room tone — "
            "no BGM, no score."
            if not silent
            else "Silent picture — no dialogue, no SFX, no generated music."
        ),
        f"{style}. Cinematic contrast, natural skin texture, realistic smoke volume and light scatter.",
        (
            SILENT_MUSIC_VIDEO_LOCK
            if silent
            else "One continuous shot, no cuts. No dialogue."
        ),
    ]
    body = "\n\n".join(p for p in paras if p)
    body = ensure_camera_in_h3_prompt(body, camera, force=True)
    return apply_audio_policy(body, brief)


CINEMA_STUDIO_ADDENDUM = """
## SİNEMA STÜDYOSU (şu an açık)
Kullanıcı Direktör sinema panelinden geldi. Aşağıdaki DİREKTÖR STÜDYOSU board kaynağıdır.

Kurallar:
- Sadece board’daki karakter ve mekan adlarını kullan; board dışından karakter/mekan uydurma.
- Shot metninde karakter/mekan adlarını birebir yaz (Arthur, Rooftop).
- Mevcut still / görselleri silme; kartları isimle birleştir.
- Brief / shot listesi yazarken characters[], locations[], shots[] (h3Prompt veya text + continue) ver.
- Üretime alma — stüdyo altyapısını ve shot metinlerini kur.
"""


def _clip_text(value: Any, limit: int) -> str:
    t = str(value or "").strip()
    if limit > 0 and len(t) > limit:
        return t[: max(0, limit - 1)] + "…"
    return t


def format_brief_board(brief: Optional[dict[str, Any]], *, full: bool = False) -> str:
    """Serialize current FilmBrief shots so the LLM can see / edit them."""
    if not isinstance(brief, dict):
        return ""
    shots = brief.get("shots") or []
    outline = brief.get("shotOutline") or []
    if (not isinstance(shots, list) or not shots) and (
        not isinstance(outline, list) or not outline
    ):
        return ""
    clip = brief.get("clipDurationSec") or ""
    total = brief.get("totalDurationSec") or ""
    need = brief.get("expectedShotCount") or len(shots) or len(outline)
    logline = _clip_text(brief.get("logline") or brief.get("title") or "", 240)
    chars = brief.get("characters") or []
    char_bits = []
    for c in chars:
        if isinstance(c, dict):
            char_bits.append(
                f"{c.get('name') or '?'}: {_clip_text(c.get('description') or c.get('card') or '', 180)}"
            )
        else:
            char_bits.append(_clip_text(c, 180))
    prompt_cap = 2200 if full else 480
    lines = [
        "# GÜNCEL SHOT TAHTASI (kaynak gerçeklik)",
        f"logline: {logline or '(yok)'}",
        f"purpose={brief.get('purpose') or '-'} visualStyle={brief.get('visualStyle') or '-'}",
        f"clipDurationSec={clip} totalDurationSec={total} shots={len(shots) if isinstance(shots, list) else 0}/{need}",
    ]
    if char_bits:
        lines.append("characters: " + " | ".join(char_bits[:8]))
    if isinstance(outline, list) and outline:
        lines.append("\n## shotOutline (FAZ A)")
        for row in outline[: int(need) if need else len(outline)]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {row.get('index')}: {row.get('title') or '?'} — "
                f"{_clip_text(row.get('beat'), 160)} "
                f"[{_clip_text(row.get('camera'), 80)}]"
            )
    for i, shot in enumerate(shots if isinstance(shots, list) else []):
        if not isinstance(shot, dict):
            lines.append(f"\n## Shot {i + 1}\n{_clip_text(shot, prompt_cap)}")
            continue
        link = shot.get("linkToPrev") or ("standalone" if i == 0 else "continue")
        dlg = shot.get("dialogue") or []
        if isinstance(dlg, str):
            dlg_s = dlg
        elif isinstance(dlg, list):
            dlg_s = " / ".join(str(x) for x in dlg if x)
        else:
            dlg_s = ""
        prompt = (
            shot.get("h3Prompt")
            or shot.get("prompt")
            or shot.get("action")
            or shot.get("text")
            or ""
        )
        lines.append(
            f"\n## Shot {i + 1} · {shot.get('durationSec') or clip}sn · {link}\n"
            f"camera: {_clip_text(shot.get('camera'), 200)}\n"
            f"action: {_clip_text(shot.get('action'), 280)}\n"
            f"dialogue: {_clip_text(dlg_s, 300)}\n"
            f"h3Prompt:\n{_clip_text(prompt, prompt_cap)}"
        )
    return "\n".join(lines).strip()


def format_cinema_board(data: Optional[dict[str, Any]], *, full: bool = False) -> str:
    """Direktör stüdyosu (cinema.json) — karakter / mekan / shot metinleri."""
    if not isinstance(data, dict):
        return ""
    shots = data.get("shots") or []
    chars = data.get("characters") or []
    locs = data.get("locations") or []
    if not shots and not chars and not locs:
        return ""
    cap = 1800 if full else 360
    lines = ["# DİREKTÖR STÜDYOSU (cinema.json)"]
    title = _clip_text(data.get("title"), 160)
    if title:
        lines.append(f"title: {title}")
    for c in chars:
        if not isinstance(c, dict):
            continue
        lines.append(
            f"character {c.get('name') or '?'}: stills="
            + ",".join(
                str(im.get("name") or "")
                for im in (c.get("images") or [])
                if isinstance(im, dict) and im.get("name")
            )
            + f" notes={_clip_text(c.get('notes') or c.get('description'), 220)}"
            + (f" voice={_clip_text(c.get('voice'), 80)}" if c.get("voice") else "")
        )
    for loc in locs:
        if not isinstance(loc, dict):
            continue
        lines.append(
            f"location {loc.get('name') or '?'}: stills="
            + ",".join(
                str(im.get("name") or "")
                for im in (loc.get("images") or [])
                if isinstance(im, dict) and im.get("name")
            )
            + f" notes={_clip_text(loc.get('notes') or loc.get('description'), 220)}"
        )
    for i, shot in enumerate(shots):
        if isinstance(shot, dict):
            mode = shot.get("mode") or "t2v"
            text = shot.get("text") or shot.get("prompt") or ""
        else:
            mode = "t2v"
            text = str(shot)
        lines.append(f"\n## Studio shot {i + 1} · {mode}\n{_clip_text(text, cap)}")
    lines.append(
        "When writing shots, name stills by call id (arthur1, arthur2) or the character name "
        "(Arthur binds every still). Do not invent extra characters that are not on this board."
    )
    return "\n".join(lines).strip()


def _patch_shot_index(raw: Any, n: int) -> Optional[int]:
    try:
        idx = int(raw)
    except (TypeError, ValueError):
        return None
    if 1 <= idx <= n:
        return idx - 1
    if 0 <= idx < n:
        return idx
    return None


def apply_shot_patches(brief: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    """Merge LLM patch / patches / replacement shots into an existing brief."""
    out = dict(brief or {})
    shots = list(out.get("shots") or [])
    incoming = parsed.get("brief") if isinstance(parsed.get("brief"), dict) else None
    if incoming and isinstance(incoming.get("shots"), list) and incoming["shots"]:
        for key, val in incoming.items():
            if key != "shots":
                out[key] = val
        shots = list(incoming["shots"])
        out["shots"] = shots
        out["expectedShotCount"] = incoming.get("expectedShotCount") or len(shots)
        return out

    patches: list[Any] = []
    if isinstance(parsed.get("patches"), list):
        patches.extend(parsed["patches"])
    if isinstance(parsed.get("patch"), dict):
        patches.append(parsed["patch"])
    if not patches or not shots:
        return out

    for p in patches:
        if not isinstance(p, dict):
            continue
        idx = _patch_shot_index(p.get("shot") if p.get("shot") is not None else p.get("index"), len(shots))
        if idx is None:
            continue
        cur = dict(shots[idx]) if isinstance(shots[idx], dict) else {"h3Prompt": str(shots[idx])}
        for key in ("camera", "action", "soundscape", "music", "h3Prompt", "prompt", "text", "linkToPrev"):
            if p.get(key) not in (None, ""):
                if key in ("prompt", "text") and not p.get("h3Prompt"):
                    cur["h3Prompt"] = str(p[key])
                elif key not in ("prompt", "text"):
                    cur[key] = p[key]
        if "dialogue" in p:
            dlg = p["dialogue"]
            if isinstance(dlg, str):
                cur["dialogue"] = [dlg] if dlg.strip() else []
            elif isinstance(dlg, list):
                cur["dialogue"] = dlg
        shots[idx] = cur
    out["shots"] = shots
    out = sync_shot_outline_from_shots(out)
    for s in out.get("shots") or []:
        if not isinstance(s, dict):
            continue
        cam = str(s.get("camera") or "").strip()
        body = str(s.get("h3Prompt") or "").strip()
        if cam and body:
            s["h3Prompt"] = ensure_camera_in_h3_prompt(body, cam, force=True)
    return out


def _brace_slice(text: str) -> Optional[str]:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def repair_json_text(text: str) -> str:
    t = text.strip()
    # strip markdown fences leftovers
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    # invalid dialogue keys → dialogue array
    t = re.sub(
        r'"<d>[^"]*</d>"\s*:\s*"([^"]*)"',
        lambda m: f'"dialogue": ["{normalize_dialogue_tag(m.group(1))}"]',
        t,
    )
    # bare Lang dialogue typos
    t = re.sub(
        r'"dialogue"\s*:\s*"([^"]*)"',
        lambda m: f'"dialogue": ["{normalize_dialogue_tag(m.group(1))}"]',
        t,
    )
    # trailing commas
    t = re.sub(r",\s*([}\]])", r"\1", t)
    # smart quotes
    t = t.replace("“", '"').replace("”", '"').replace("’", "'")
    return t


def _balance_counts(text: str) -> tuple[int, int, int, int]:
    """Return (open_brace, close_brace, open_bracket, close_bracket) ignoring strings."""
    ob = cb = oq = cq = 0
    in_str = False
    esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            ob += 1
        elif ch == "}":
            cb += 1
        elif ch == "[":
            oq += 1
        elif ch == "]":
            cq += 1
    return ob, cb, oq, cq


def salvage_truncated_json(text: str) -> Optional[str]:
    """Close truncated JSON after last complete object in shots array if possible."""
    t = repair_json_text(text)
    start = t.find("{")
    if start < 0:
        return None
    t = t[start:]
    # Drop dangling incomplete trailing string/object after last complete `}`
    last_obj = t.rfind("}")
    if last_obj > 0:
        # Prefer cutting at last full shot object ending `},` or `}`
        cut = t[: last_obj + 1]
    else:
        cut = t
    # If mid-array, trim to last `},` that looks like end of a shot
    if '"shots"' in cut and cut.rstrip().endswith(","):
        cut = cut.rstrip().rstrip(",")
    ob, cb, oq, cq = _balance_counts(cut)
    # Close open structures
    if oq > cq:
        cut += "]" * (oq - cq)
    if ob > cb:
        cut += "}" * (ob - cb)
    # Remove trailing commas again after close
    cut = re.sub(r",\s*([}\]])", r"\1", cut)
    return cut


def extract_json_object(text: str) -> Optional[dict[str, Any]]:
    if not text or not str(text).strip():
        return None
    raw = str(text).strip()
    candidates: list[str] = []
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if m:
        candidates.append(m.group(1))
    # greedy fenced block (model may nest ``` wrongly)
    m2 = re.search(r"```(?:json)?\s*([\s\S]+)", raw)
    if m2:
        candidates.append(m2.group(1).split("```")[0])
    sliced = _brace_slice(raw)
    if sliced:
        candidates.append(sliced)
    brief_m = re.search(r'"brief"\s*:\s*\{', raw)
    if brief_m:
        idx = raw.rfind("{", 0, brief_m.start())
        outer = _brace_slice(raw[idx:] if idx >= 0 else raw)
        if outer:
            candidates.append(outer)
    # salvage truncated payloads (common when model dumps 20/35 shots then stops)
    salv = salvage_truncated_json(raw)
    if salv:
        candidates.append(salv)
    if m:
        salv2 = salvage_truncated_json(m.group(1))
        if salv2:
            candidates.append(salv2)
    # Empty shots truncation: "... \"shots\": [" → close as empty array
    for src in (raw, m.group(1) if m else ""):
        if not src or '"shots"' not in src:
            continue
        if re.search(r'"shots"\s*:\s*\[\s*$', src.strip()) or re.search(
            r'"shots"\s*:\s*\[\s*$', src, re.M
        ):
            closed = re.sub(r'"shots"\s*:\s*\[\s*$', '"shots": []', src.strip())
            closed = salvage_truncated_json(closed) or closed
            candidates.append(closed)

    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        for variant in (cand, repair_json_text(cand), salvage_truncated_json(cand) or ""):
            if not variant:
                continue
            try:
                data = json.loads(variant)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            if "shots" in data and "brief" not in data:
                return {"ready": True, "reply": "Brief alındı", "brief": data}
            if "brief" in data or data.get("ready") is not None or "shots" in data:
                return data
    return None


def skeleton_brief_from_text(text: str) -> Optional[dict[str, Any]]:
    """Build a queueable brief skeleton when the model cut off before h3Prompts."""
    if not text:
        return None
    raw = str(text)
    parsed = extract_json_object(raw)
    brief: dict[str, Any] = {}
    if parsed:
        if isinstance(parsed.get("brief"), dict):
            brief = dict(parsed["brief"])
        elif isinstance(parsed.get("shots"), list) or parsed.get("expectedShotCount"):
            brief = dict(parsed)

    def _num(key: str, *alts: str) -> Optional[int]:
        if brief.get(key) is not None:
            try:
                return int(brief[key])
            except Exception:
                pass
        for k in (key,) + alts:
            m = re.search(rf'"{k}"\s*:\s*(\d+)', raw)
            if m:
                return int(m.group(1))
        return None

    total = _num("totalDurationSec") or parse_duration_to_seconds(
        brief.get("totalDurationSec")
    )
    clip = _num("clipDurationSec", "clipLengthSec") or 5
    if clip not in CLIP_DURATIONS:
        clip = 5
    need = _num("expectedShotCount")
    # Chat language: "12 shot", "1 dakika", "60 sn"
    tot_inf, need_inf = infer_duration_and_shots(raw, clip_sec=clip, default_total=total)
    if need_inf and (not need or need_inf > need):
        need = need_inf
    if tot_inf and (not total or (need_inf and tot_inf >= int(need_inf) * clip // 2)):
        total = tot_inf
    if not total:
        m = re.search(r"(\d+)\s*(?:sn|saniye|sec)", raw, re.I)
        if m:
            total = int(m.group(1))
        elif re.search(r"1\s*dakika|60\s*sn", raw, re.I):
            total = 60
    if not need and total:
        need = expected_shot_count(int(total), clip)
    if not need:
        m = re.search(r"(\d+)\s*[×x]\s*(?:4|5|6|8|10|15)\b", raw)
        if m:
            need = int(m.group(1))
    if not need:
        need = expected_shot_count(int(total), clip) if total else None
    if not need and not brief.get("characters") and not brief.get("logline"):
        return None

    purpose = normalize_purpose(brief.get("purpose"), raw)
    style = normalize_style(brief.get("visualStyle"), raw)

    chars = brief.get("characters") if isinstance(brief.get("characters"), list) else []
    if not chars:
        cm = re.search(
            r'"characters"\s*:\s*(\[[\s\S]*?\])\s*,\s*"shots"',
            raw,
        )
        if not cm:
            cm = re.search(r'"characters"\s*:\s*(\[[\s\S]*?\])', raw)
        if cm:
            try:
                chars = json.loads(repair_json_text(cm.group(1)))
            except Exception:
                chars = []
    if not chars and re.search(r"Robotic Angel|robotik angel", raw, re.I):
        chars = [
            {
                "name": "Robotic Angel",
                "description": (
                    "Ageless androgynous humanoid, pale synthetic skin, glowing blue circuitry "
                    "on neck/shoulders/chest, luminous cyan-white eyes, smooth crown with antenna, "
                    "minimalist black bodysuit with LED strips, high collar, metallic boots"
                ),
            }
        ]

    logline = brief.get("logline") or ""
    if not logline:
        lm = re.search(r'"logline"\s*:\s*"([^"]+)"', raw)
        if lm:
            logline = lm.group(1)
        else:
            logline = (
                "Fixed character music video; scene lighting and blocking evolve across shots."
            )

    shots = brief.get("shots") if isinstance(brief.get("shots"), list) else []
    outline = brief.get("shotOutline") if isinstance(brief.get("shotOutline"), list) else []
    if not outline:
        om = re.search(r'"shotOutline"\s*:\s*(\[[\s\S]*?\])\s*,\s*"', raw)
        if not om:
            om = re.search(r'"shotOutline"\s*:\s*(\[[\s\S]*?\])', raw)
        if om:
            try:
                outline = json.loads(repair_json_text(om.group(1)))
            except Exception:
                outline = []
    out = {
        "purpose": purpose,
        "visualStyle": style if style in VISUAL_STYLES else "realistic",
        "clipDurationSec": clip,
        "aspect": brief.get("aspect") or brief.get("aspectRatio") or "16:9",
        "logline": logline,
        "totalDurationSec": int(total or (need or 1) * clip),
        "expectedShotCount": int(need or max(1, len(shots) or len(outline) or 1)),
        "characters": chars,
        "shots": shots,
        "silentAudio": purpose == "music_video",
        "shotsIncomplete": True,
    }
    if outline:
        out["shotOutline"] = outline
    return out


# Video aspect ratios — must never be read as clock times (16:9 ≠ 16 min 9 sec).
_ASPECT_PAIRS = {
    (16, 9),
    (9, 16),
    (1, 1),
    (21, 9),
    (4, 3),
    (3, 2),
    (4, 5),
    (5, 4),
    (3, 4),
    (2, 1),
    (1, 2),
    (18, 9),
    (19, 9),
}


def _is_aspect_pair(a: int, b: int) -> bool:
    return (a, b) in _ASPECT_PAIRS


def parse_duration_to_seconds(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        n = int(value)
        return n if n > 0 else None
    s = str(value).strip().lower().replace(",", ".")
    if not s:
        return None
    m = re.match(r"^(\d{1,2})\s*[:：]\s*(\d{1,2})(?:\s*[:：]\s*(\d{1,2}))?$", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if m.group(3) is None and _is_aspect_pair(a, b):
            return None
        if m.group(3) is None:
            return a * 60 + b if b < 60 else None
        c = int(m.group(3))
        return a * 3600 + b * 60 + c if b < 60 and c < 60 else None
    m = re.match(r"^(\d+)\.(\d{1,2})$", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if b < 60 and a < 180:
            return a * 60 + b
    if re.search(r"aspect|oran|\d+\s*p\b", s):
        return None
    m = re.search(r"(\d+)", s)
    if m:
        return int(m.group(1))
    return None


def expected_shot_count(total_sec: int, clip_sec: int) -> int:
    clip = clip_sec if clip_sec in CLIP_DURATIONS else 5
    total = max(1, int(total_sec))
    return max(1, math.ceil(total / clip))


def infer_duration_and_shots(
    text: str,
    *,
    clip_sec: int = 5,
    default_total: Optional[int] = None,
) -> tuple[Optional[int], Optional[int]]:
    """From user/assistant text → (totalDurationSec, expectedShotCount)."""
    if not text:
        return default_total, None
    raw = str(text)
    clip = clip_sec if clip_sec in CLIP_DURATIONS else 5

    # Explicit shot count: "12 shot", "5 shotlık", "12×5" — not "16:9" or JSON keys.
    m = re.search(
        r"(?<![A-Za-z_])(\d{1,3})\s*(?:[×x]\s*(?:4|5|6|8|10|15)\s*)?"
        r"(?:shot(?:lık|luk)?|sahne(?:lik|lık|ler)?|klip(?:lik|lık)?)\b",
        raw,
        re.I,
    )
    if m:
        n = int(m.group(1))
        if 1 <= n <= 120:
            shot_total = n * clip
            # Also read explicit duration ("25 saniyelik") — may differ from n×clip.
            dur_total = None
            dm = re.search(r"(\d+)\s*(?:sn\b|saniye(?:lik)?|sec(?:onds)?\b)", raw, re.I)
            if dm:
                dur_total = int(dm.group(1))
            total_out = max(shot_total, dur_total) if dur_total else shot_total
            return int(total_out), n

    # Prefer "1 dakika" / "10 saniye" over clock times so "16:9" cannot win.
    total = None
    m = re.search(r"(\d+)\s*dakika", raw, re.I)
    if m:
        total = int(m.group(1)) * 60
    if total is None:
        m = re.search(r"(\d+)\s*(?:sn\b|saniye(?:lik)?|sec(?:onds)?\b)", raw, re.I)
        if m:
            total = int(m.group(1))
    if total is None:
        for cm in re.finditer(r"(\d{1,2})\s*[:：]\s*(\d{1,2})\b", raw):
            a, b = int(cm.group(1)), int(cm.group(2))
            if b >= 60 or _is_aspect_pair(a, b):
                continue
            total = a * 60 + b
            break
    if total is None:
        total = default_total
    if total:
        return int(total), expected_shot_count(int(total), clip)
    return None, None


_BEAT_ARCS = (
    "awakening / first awareness; eyes open; first light finds the subject",
    "body systems activate; subtle LED/glow or muscle tension rises",
    "face / expression micro-shift; gaze intensifies",
    "first deliberate motor movement of a hand or arm",
    "weight shifts; stance becomes intentional",
    "environment lighting reacts; color temperature drifts",
    "subject claims space; slow turn or step forward",
    "camera closes in; emotional peak of the beat",
    "hold / resolve; subject settles into a strong final pose for this chapter",
)


def build_scene_placeholder_shot(
    *,
    index: int,
    total: int,
    brief: dict[str, Any],
) -> dict[str, Any]:
    """Full SCENE-length h3Prompt so queue never collapses to 1 shot if LLM stalls."""
    dur = int(brief.get("clipDurationSec") or 5)
    if dur not in CLIP_DURATIONS:
        dur = 5
    chars = brief.get("characters") or []
    char_paras: list[str] = []
    same_bits: list[str] = []
    for c in chars:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "Character").strip()
        desc = (c.get("description") or "consistent look").strip()
        char_paras.append(
            f"{name} is {desc}. Keep identical scale, silhouette, markings and materials "
            "across the continue chain."
            if re.search(
                r"\b(dragon|ejder|wyvern|beast|creature|kaiju|robot|mecha)\b",
                f"{name} {desc}".lower(),
            )
            else f"{name} is {desc}. Keep identical face, age, hair, eyes and wardrobe."
        )
        same_bits.append(f"same {name}")
    char_block = "\n\n".join(char_paras) if char_paras else (
        "Keep the lead subject identical in face, age, hair and wardrobe across the continue chain."
    )
    same_lock = (
        ", ".join(same_bits) + ", identical clothing and appearance"
        if same_bits
        else "same characters, identical clothing and appearance"
    )
    logline = (brief.get("logline") or "cinematic music-video chapter").strip()
    style = normalize_style(brief.get("visualStyle"))
    purpose = (brief.get("purpose") or "").lower()
    silent = bool(brief.get("silentAudio")) or purpose in ("music_video", "music-video")
    beat = _BEAT_ARCS[index % len(_BEAT_ARCS)]
    intent = brief.get("sceneIntent") if isinstance(brief.get("sceneIntent"), dict) else {}
    if intent.get("beat"):
        beat = str(intent["beat"])
    elif intent.get("raw"):
        beat = scene_action_english_hint(str(intent["raw"])) or str(intent["raw"])
    t0 = index * dur
    t1 = t0 + dur
    cameras = CAMERA_VARIETY
    camera = camera_for_outline_index(index, directives=brief.get("directorDirectives"))
    if intent.get("camera") and index == 0:
        camera = str(intent["camera"])
    atmos = (
        "Dark melodic techno-house atmosphere, nocturnal energy, controlled body language."
        if silent or "music" in purpose
        else "Cinematic dramatic atmosphere matching the story beat."
    )
    tech = f"{style_craft_line(style)}. Stay locked in this look."
    lock = (
        "One continuous shot, no cuts, no dialogue, silent visual only, no generated music, no SFX."
        if silent
        else "One continuous shot, no cuts, no dialogue."
    )

    if index == 0:
        body = "\n\n".join(
            [
                (
                    f"A {style_craft_line(style)} scene. Story: {logline}. "
                    f"This is shot 1 of {total}, covering approximately {t0}–{t1}s."
                ),
                char_block,
                (
                    f"Across this {dur}-second continuous take the emotional beat is: {beat}. "
                    "Actions are specific and readable: eyes, breath, micro-expression, then a clear physical beat."
                ),
                f"The camera: {camera}.",
                atmos,
                tech,
                lock,
            ]
        )
        link = "standalone" if index == 0 else "continue"
        action = beat
    else:
        body = "\n\n".join(
            [
                "Continue directly from the previous shot.",
                f"{same_lock.capitalize()}.",
                f"Story context remains: {logline}. Shot {index + 1} of {total} ({t0}–{t1}s).",
                (
                    f"Across this {dur}-second continuous take the new beat is: {beat}. "
                    "Do not reset wardrobe or identity. Progress only this moment with micro-expressions "
                    "and one clear physical action."
                ),
                f"The camera: {camera}.",
                atmos,
                tech,
                lock,
            ]
        )
        link = "continue"
        action = beat

    shot = {
        "durationSec": dur,
        "camera": camera,
        "action": action,
        "dialogue": [],
        "soundscape": "visual only" if silent else "diegetic ambience and action SFX — no music",
        "music": "picture mood only" if silent else "none",
        "h3Prompt": body,
        "linkToPrev": link,
        "_placeholder": True,
    }
    shot["h3Prompt"] = apply_audio_policy(body, brief)
    return shot


def ensure_shot_count_sync(brief: dict[str, Any]) -> dict[str, Any]:
    """Pad/truncate shots to expectedShotCount using SCENE placeholders (no LLM)."""
    brief = validate_brief(brief)
    dur = int(brief.get("clipDurationSec") or 5)
    need = brief.get("expectedShotCount")
    if not need:
        total = brief.get("totalDurationSec")
        if total:
            need = expected_shot_count(int(total), dur)
            brief["expectedShotCount"] = need
    shots = list(brief.get("shots") or [])
    if not need:
        need = max(1, len(shots))
        brief["expectedShotCount"] = need
    # If totalDuration missing, derive from need
    if not brief.get("totalDurationSec"):
        brief["totalDurationSec"] = int(need) * dur
    while len(shots) < need:
        shots.append(
            build_scene_placeholder_shot(index=len(shots), total=need, brief=brief)
        )
    # Respect optional "force_continue" flag on the brief (default True)
    if brief.get("force_continue", True):
        shots = force_continue_chain(shots[:need], brief)
    else:
        shots = shots[:need]
    # Re-apply rich prompt + audio policy
    final = []
    for i, s in enumerate(shots):
        s2 = dict(s)
        s2["h3Prompt"] = build_rich_h3_prompt(
            shot=s2, index=i, total=need, brief=brief
        )
        final.append(s2)
    brief["shots"] = final
    brief["shotsIncomplete"] = False
    brief["expectedShotCount"] = need
    return brief


def _collect_dialogue(s: dict[str, Any]) -> list[str]:
    dlg = s.get("dialogue")
    out: list[str] = []
    if isinstance(dlg, list):
        out.extend([str(x) for x in dlg if str(x).strip()])
    elif isinstance(dlg, str) and dlg.strip():
        out.append(dlg.strip())
    for k, v in list(s.items()):
        if isinstance(k, str) and "<d>" in k and isinstance(v, str) and v.strip():
            out.append(v.strip())
    # Also harvest bare [Lang] lines from h3Prompt / action
    for field in ("h3Prompt", "action"):
        blob = s.get(field)
        if isinstance(blob, str) and blob.strip():
            for m in _BARE_LANG_LINE.finditer(blob):
                out.append(f"[{m.group(1)}] {m.group(2).strip()}")
            for m in re.finditer(r"<d>\s*(.*?)\s*</d>", blob, re.I | re.S):
                out.append(m.group(0))
    # normalize → unique <d>[Lang]…</d>
    seen: set[str] = set()
    norm: list[str] = []
    for d in out:
        tag = normalize_dialogue_tag(d)
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        norm.append(tag)
    return norm


def build_rich_h3_prompt(
    *,
    shot: dict[str, Any],
    index: int,
    total: int,
    brief: dict[str, Any],
) -> str:
    """Compose SCENE-style MiniMax-H3 prompt from shot fields + brief."""
    chars = brief.get("characters") or []
    char_paras: list[str] = []
    same_lock_bits: list[str] = []
    for c in chars:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "Character").strip()
        desc = (c.get("description") or "consistent look, wardrobe continuity").strip()
        blob = f"{name} {desc}".lower()
        if re.search(r"\b(dragon|ejder|wyvern|beast|creature|kaiju|robot|mecha)\b", blob):
            char_paras.append(
                f"{name}: {desc}. Keep identical scale, silhouette, markings and materials."
            )
        else:
            char_paras.append(
                f"{name}: {desc}. Keep identical face, age, hair and wardrobe."
            )
        same_lock_bits.append(f"same {name}")
    style = normalize_style(brief.get("visualStyle"))
    style_txt = style_craft_line(style)
    camera = (shot.get("camera") or DEFAULT_CAMERA).strip()
    action = (shot.get("action") or "").strip()
    sound = (
        shot.get("soundscape")
        or "diegetic ambience only: room tone, wind, footsteps, action impacts — no music"
    ).strip()
    music = (shot.get("music") or "none — no BGM, no score").strip()
    dlg = _collect_dialogue(shot)
    dlg_txt = " ".join(dlg) if dlg else "no dialogue"
    dur = shot.get("durationSec") or brief.get("clipDurationSec") or 5
    logline = (brief.get("logline") or "").strip()
    link = (shot.get("linkToPrev") or "standalone").strip()
    base = (shot.get("h3Prompt") or "").strip()

    silent = _is_silent_brief(brief)

    # Model already wrote SCENE-density screenplay — keep (ensure continue opener + <d> tags)
    # Reject thin templates even if they are long (boilerplate padding).
    if len(base) >= MIN_H3_PROMPT_CHARS and not is_thin_template_prompt(base):
        out = base
        if link == "continue" and not base.lower().startswith("continue directly"):
            out = "Continue directly from the previous shot.\n\n" + base
        out = ensure_dialogue_in_h3_prompt(out, dlg, silent=silent)
        out = ensure_camera_in_h3_prompt(out, camera)
        return apply_audio_policy(out, brief)

    same_lock = (
        ", ".join(same_lock_bits) + ", identical clothing and appearance"
        if same_lock_bits
        else "same characters, identical clothing and appearance"
    )
    char_block = "\n\n".join(char_paras) if char_paras else "Keep cast continuity across the continue chain."
    intent = brief.get("sceneIntent") if isinstance(brief.get("sceneIntent"), dict) else {}
    if intent.get("beat") and (
        not action
        or action in _BEAT_ARCS
        or "awakening / first awareness" in (action or "")
    ):
        beats = str(intent["beat"])
    else:
        beats = action or base or "characters hold tension; micro-expressions progress the emotional beat"
    if intent.get("camera") and _is_generic_camera(camera):
        camera = str(intent["camera"])
    t0, t1 = 0, int(dur)
    atmos = (
        "Visual mood only (silent music video): " + (music or "picture mood only")
        if silent
        else (
            f"Diegetic soundscape (NO MUSIC): {sound}. "
            "No soundtrack, no BGM, no underscore."
        )
    )

    if link == "continue" or index > 0:
        paras = [
            "Continue directly from the previous shot.",
            f"{same_lock.capitalize()}.",
            f"Story context remains: {logline}" if logline else "",
            f"Across {t0}–{t1}s: {beats}.",
            f"The camera: {camera}.",
            atmos,
            f"{style_txt}. Stay locked in this look. Cinematic contrast, "
            "depth of field, 35mm lens language.",
            (
                SILENT_MUSIC_VIDEO_LOCK
                if silent
                else (
                    f"One continuous shot, no cuts. Spoken line: {dlg_txt}. "
                    "Clear spoken dialogue audio, mouth moves in sync."
                    if dlg
                    else "One continuous shot, no cuts. No dialogue."
                )
            ),
        ]
    else:
        paras = [
            (
                f"A {style_txt} scene. {logline}"
                if logline
                else f"A {style_txt} scene with strong atmosphere."
            ),
            char_block,
            "" if silent else f"Diegetic environment sound (NO MUSIC): {sound}.",
            f"Across {t0}–{t1}s: {beats}.",
            f"The camera: {camera}.",
            atmos,
            f"{style_txt}. Stay locked in this look. Cinematic contrast, "
            "depth of field, 35mm lens language.",
            (
                SILENT_MUSIC_VIDEO_LOCK
                if silent
                else (
                    f"One continuous shot, no cuts. Spoken line: {dlg_txt}. "
                    "Clear spoken dialogue audio, mouth moves in sync."
                    if dlg
                    else "One continuous shot, no cuts. No dialogue."
                )
            ),
        ]
    body = "\n\n".join(p for p in paras if p)
    body = ensure_dialogue_in_h3_prompt(body, dlg, silent=silent)
    out = apply_audio_policy(body, brief)
    if intent.get("raw") and is_thin_template_prompt(out):
        out = build_scene_from_intent(
            shot=shot, index=index, total=total, brief=brief, intent=intent
        )
    # Mark so QA never treats this filler as director-level
    shot["_thin_template"] = is_thin_template_prompt(out)
    return out


def _clean_shot(
    s: dict[str, Any],
    i: int,
    dur: int,
    brief: Optional[dict[str, Any]] = None,
    total_shots: int = 0,
) -> Optional[dict[str, Any]]:
    if not isinstance(s, dict):
        return None
    sd = dur
    if sd not in CLIP_DURATIONS:
        sd = 5
    dlg = _collect_dialogue(s)
    action = (s.get("action") or "").strip()
    prompt = (s.get("h3Prompt") or "").strip()
    if not prompt and not action:
        return None
    link = s.get("linkToPrev") or "standalone"
    if link not in ("standalone", "continue", "ref"):
        link = "standalone"
    shot = {
        "durationSec": sd,
        "camera": s.get("camera") or "",
        "action": action,
        "dialogue": dlg,
        "soundscape": s.get("soundscape") or "",
        "music": s.get("music") or "",
        "h3Prompt": prompt or action,
        "linkToPrev": link,
        "sectionId": str(s.get("sectionId") or s.get("section_id") or "").strip(),
    }
    if s.get("_placeholder"):
        shot["_placeholder"] = True
    if s.get("_thin_template"):
        shot["_thin_template"] = True
    if brief is not None:
        silent = _is_silent_brief(brief)
        # Preserve strong LLM SCENE bodies — do not rebuild into filler templates
        if len(prompt) >= MIN_H3_PROMPT_CHARS and not is_thin_template_prompt(prompt):
            body = prompt
            if link == "continue" and not prompt.lower().startswith("continue directly"):
                body = "Continue directly from the previous shot.\n\n" + prompt
            shot["h3Prompt"] = apply_audio_policy(
                ensure_dialogue_in_h3_prompt(body, dlg, silent=silent),
                brief,
            )
            shot["_thin_template"] = False
            shot["_placeholder"] = False
        else:
            shot["h3Prompt"] = build_rich_h3_prompt(
                shot=shot, index=i, total=total_shots or (i + 1), brief=brief
            )
            if is_thin_template_prompt(shot["h3Prompt"]):
                shot["_thin_template"] = True
    return shot


def _character_names_in_text(text: str, characters: list[Any]) -> set[str]:
    """Match brief character names inside a SCENE body (case-insensitive word boundary)."""
    found: set[str] = set()
    blob = text or ""
    for c in characters or []:
        if isinstance(c, dict):
            name = str(c.get("name") or "").strip()
        else:
            name = str(c or "").strip()
        if len(name) < 2:
            continue
        pat = rf"(?i)(?<!\w){re.escape(name)}(?!\w)"
        if re.search(pat, blob):
            found.add(name.lower())
    return found


def force_continue_chain(
    shots: list[dict[str, Any]],
    brief: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Normalize production into section chains.

    The first shot in every ``sectionId`` is a new T2V video. Only a later shot
    that explicitly requests ``linkToPrev: "continue"`` in that same section
    inherits the prior clip's last frame. A location/action change must get a new
    section ID even when the character remains the same.
    """
    out: list[dict[str, Any]] = []
    previous_section = ""
    section_number = 0
    for i, raw in enumerate(shots):
        shot = dict(raw)
        requested = str(shot.get("linkToPrev") or "").strip().lower()
        section = str(shot.get("sectionId") or shot.get("section_id") or "").strip()
        if not section:
            if i and requested == "continue" and previous_section:
                section = previous_section
            else:
                section_number += 1
                section = f"scene-{section_number}"
        is_same_section = bool(i and section == previous_section)
        shot["sectionId"] = section
        shot["linkToPrev"] = "continue" if is_same_section and requested == "continue" else "standalone"
        out.append(shot)
        previous_section = section
    return out


def validate_brief(brief: dict[str, Any]) -> dict[str, Any]:
    dur = int(brief.get("clipDurationSec") or 5)
    if dur not in CLIP_DURATIONS:
        dur = 5
    brief["clipDurationSec"] = dur
    brief["aspect"] = brief.get("aspect") or "16:9"
    brief["visualStyle"] = normalize_style(brief.get("visualStyle"))
    if brief.get("purpose"):
        brief["purpose"] = normalize_purpose(brief.get("purpose"))

    total = brief.get("totalDurationSec")
    if total is not None:
        parsed = parse_duration_to_seconds(total)
        if parsed:
            brief["totalDurationSec"] = parsed
            total = parsed

    explicit_need: Optional[int] = None
    try:
        if brief.get("expectedShotCount") is not None:
            explicit_need = int(brief["expectedShotCount"])
    except (TypeError, ValueError):
        explicit_need = None

    need = None
    if isinstance(total, int) and total > 0:
        computed = expected_shot_count(total, dur)
        if explicit_need and explicit_need > computed:
            need = explicit_need
            brief["expectedShotCount"] = need
            brief["totalDurationSec"] = max(int(total), explicit_need * dur)
        else:
            need = computed
            brief["expectedShotCount"] = need
    elif explicit_need and explicit_need > 0:
        need = explicit_need
        brief["expectedShotCount"] = need
        if not brief.get("totalDurationSec"):
            brief["totalDurationSec"] = need * dur

    # Preserve / normalize FAZ A outline (even when shots empty)
    outline = normalize_shot_outline(brief)
    if outline:
        brief["shotOutline"] = outline
        if not need:
            need = len(outline)
            brief["expectedShotCount"] = need
            if not brief.get("totalDurationSec"):
                brief["totalDurationSec"] = need * dur

    raw_shots = brief.get("shots") or []
    cleaned = []
    n_hint = need or len(raw_shots) or 1
    for i, s in enumerate(raw_shots):
        c = _clean_shot(s, i, dur, brief=brief, total_shots=n_hint)
        if c:
            cleaned.append(c)

    # Respect optional "force_continue" flag on the brief (default True)
    if brief.get("force_continue", True):
        cleaned = force_continue_chain(cleaned, brief)
    if need and len(cleaned) > need:
        cleaned = cleaned[:need]

    # Re-enrich with final count
    final = []
    intent = brief.get("sceneIntent") if isinstance(brief.get("sceneIntent"), dict) else {}
    for i, s in enumerate(cleaned):
        s2 = dict(s)
        built = build_rich_h3_prompt(shot=s2, index=i, total=len(cleaned), brief=brief)
        if is_thin_template_prompt(built) and intent.get("raw"):
            built = build_scene_from_intent(
                shot=s2, index=i, total=len(cleaned), brief=brief, intent=intent
            )
            s2["_thin_template"] = False
        s2["h3Prompt"] = built
        final.append(s2)

    brief["shots"] = final
    if final and not brief.get("totalDurationSec"):
        brief["totalDurationSec"] = sum(x["durationSec"] for x in final)
    brief["shotsIncomplete"] = bool(need and len(final) < need)
    return brief


def normalize_ui_lang(value: Any = None) -> str:
    s = str(value or "tr").lower().strip()
    return "en" if s.startswith("en") else "tr"


def ui_lang_addendum(lang: Any = None) -> str:
    if normalize_ui_lang(lang) == "en":
        return (
            "\n\n## UI LANGUAGE OVERRIDE (highest priority)\n"
            "The Studio UI is English. Speak to the user in **English** in every `reply` and chat turn. "
            "This overrides any instruction to speak Turkish.\n"
            "JSON keys stay English. Every `h3Prompt` / SCENE body MUST stay English.\n"
            "Spoken dialogue defaults to **pure English**: use `<d>[English] …</d>` only. "
            "Do not use Turkish/Japanese/Korean/other language tags unless the user "
            "explicitly requests that language for the spoken line.\n"
            "SFX: only sounds motivated by the SCENE — never invent rain/smoke/explosions.\n"
        )
    return (
        "\n\n## ARAYÜZ DİLİ\n"
        "Kullanıcıya **Türkçe** konuş (`reply` ve sohbet). JSON anahtarları İngilizce.\n"
        "Her `h3Prompt` / SCENE gövdesi her zaman İngilizce — UI TR olsa bile.\n"
        "Diyalog: kullanıcı Türkçe replik istediyse `<d>[Turkish] …</d>`; "
        "İngilizce / dil belirtmediyse `<d>[English] …</d>`.\n"
        "SFX: yalnız sahnede gerekçesi olan sesler — yağmur/duman/patlama uydurma.\n"
    )


def ready_shots_reply(n: int, need: Any = None, lang: Any = None) -> str:
    extra = ""
    if need and need != n:
        extra = (
            f" (target {need})"
            if normalize_ui_lang(lang) == "en"
            else f" (hedef {need})"
        )
    if normalize_ui_lang(lang) == "en":
        noun = "shot" if n == 1 else "shots"
        return (
            f"{n} {noun} ready{extra}.\n\n"
            "**Queue for production** — every scene goes on the queue."
        )
    return (
        f"{n} shot hazır{extra}.\n\n"
        "**Üretime al** — hepsi sahne sahne kuyruğa girer."
    )


def opening_message(lang: Any = None) -> str:
    if normalize_ui_lang(lang) == "en":
        return (
            "Hi — I'm **H3 Director**. Pick a project from the chips.\n\n"
            "Workflow: we lock the idea → I give you an **N-shot outline** (titles + beats) "
            "→ then each shot is written as a full **cinematic SCENE** one by one "
            "(character card, micro-action, camera — not keyword soup).\n"
            "**music video** = silent picture + song mux at the end.\n"
            "Type: short film / ad / trailer / social / documentary / intro / outro.\n"
            "Look: realistic, anime, disney, game, 3D CGI, comic, illustration, oil paint, clay, found footage.\n"
            "Give duration + story + character/location; say when the idea is locked.\n"
            "The **Plan** tab lets you read and edit every shot.\n\n"
            "What are we making? Look and total duration in seconds?"
        )
    return (
        "Merhaba — ben **H3 Yönetmen**. Chip’ten proje seç.\n\n"
        "Akış: fikri kilitle → ben **N shot’lık iskelet** (başlık + beat) çıkarırım "
        "→ sonra her shot’u **tek tek** sinematik SCENE olarak yazarım "
        "(karakter kartı, mikro eylem, kamera — keyword soup yok).\n"
        "**müzik klibi** = sessiz görüntü + finalde şarkı mux.\n"
        "Tür: kısa film / reklam / trailer / sosyal / belgesel / intro / outro.\n"
        "Tarz: gerçekçi, anime, disney, oyun, 3D CGI, çizgi roman, illüstrasyon, yağlı boya, kil, found footage.\n"
        "Süre + hikâye + karakter/lokasyon ver; “tamam / N shot / fikrimiz bu” de.\n"
        "**Plan** sekmesinde tüm shot metinlerini görüp düzenleyebilirsin.\n\n"
        "Şimdi: ne üretiyoruz? Tarz ve toplam süre kaç sn?"
    )


def fallback_director_reply(sess: dict[str, Any], user_msg: str = "", lang: Any = None) -> str:
    """Never leave the UI with an empty assistant turn if the LLM fails."""
    ui = normalize_ui_lang(lang or (sess or {}).get("ui_lang"))
    purpose = (sess.get("purpose") or "").strip()
    style = (sess.get("visual_style") or "").strip()
    silent = bool(sess.get("silent_audio"))
    clip = int(sess.get("clip_duration") or 5)
    bits = []
    if purpose:
        bits.append(f"purpose={purpose}" if ui == "en" else f"proje={purpose}")
    if style:
        bits.append(f"look={style}" if ui == "en" else f"tarz={style}")
    if silent or purpose in ("music_video", "music-video"):
        bits.append(
            "silent picture (song at the end)"
            if ui == "en"
            else "sessiz görüntü (şarkı finalde)"
        )
    bits.append(f"clip={clip}s" if ui == "en" else f"klip={clip}sn")
    ctx = ", ".join(bits)
    low = (user_msg or "").lower()
    if any(k in low for k in ("süre", "sn", "saniye", "dakika", "dk", "sec", "second", "minute")):
        if ui == "en":
            return (
                f"Got the duration ({ctx}). "
                "Now send a short logline + main character(s) + location; "
                f"I'll build the {clip}s SCENE chain."
            )
        return (
            f"Süreyi aldım ({ctx}). "
            "Şimdi kısa logline + ana karakter(ler) + lokasyon yaz; "
            f"ben de {clip}sn’lik SCENE zincirini kurayım."
        )
    if purpose in ("music_video", "music-video") or silent:
        if ui == "en":
            return (
                f"We're in music-video mode ({ctx}). "
                "Send song feel / tempo + story + character + location; "
                "I'll write silent SCENE screenplays."
            )
        return (
            f"Müzik klibi modundayız ({ctx}). "
            "Şarkı hissi / tempo + hikâye + karakter + mekanı yaz; "
            "ben sessiz SCENE senaryolarını çıkarırım."
        )
    if purpose:
        if ui == "en":
            return (
                f"Noted ({ctx}). "
                "Give total duration (sec) + 1–2 sentence story + character/location; "
                "then I'll write the cinematic SCENEs."
            )
        return (
            f"Not aldım ({ctx}). "
            "Toplam süre (sn) + 1–2 cümle hikâye + karakter/mekân ver; "
            "ardından sinematik SCENE’leri yazarım."
        )
    if ui == "en":
        return (
            "The connection dropped, but I'm here. "
            "Pick a project chip or write: film / music video, total duration (sec), "
            "story + character. I'll write the SCENE screenplays."
        )
    return (
        "Bağlantı kısa kesildi ama buradayım. "
        "Chip’ten proje seç veya yaz: film / müzik klibi, toplam süre (sn), "
        "hikâye + karakter. Ben SCENE senaryolarını yazarım."
    )


MIN_H3_PROMPT_CHARS = 1100


def format_project_bible(brief: dict[str, Any]) -> str:
    """Locked cast / locations / style for per-shot writing (deterministic continuity)."""
    brief = brief or {}
    chars = brief.get("characters") or []
    locs = brief.get("locations") or []
    style = normalize_style(brief.get("visualStyle"))
    lines = [
        "PROJECT BIBLE (lock — do not change identity/wardrobe/location across shots):",
        f"purpose={brief.get('purpose') or '-'} visualStyle={style}",
        f"craft={style_craft_line(style)}",
        f"logline={brief.get('logline') or '-'}",
        f"clipDurationSec={brief.get('clipDurationSec') or 5} "
        f"totalDurationSec={brief.get('totalDurationSec') or '-'} "
        f"expectedShotCount={brief.get('expectedShotCount') or '-'}",
        f"silentAudio={_is_silent_brief(brief)}",
        "characters:",
    ]
    if isinstance(chars, list) and chars:
        for c in chars:
            if isinstance(c, dict):
                lines.append(
                    f"- {(c.get('name') or 'Character').strip()}: "
                    f"{(c.get('description') or '').strip()}"
                )
            else:
                lines.append(f"- {c}")
    else:
        lines.append("- (none listed — invent once and keep identical)")
    lines.append("locations:")
    if isinstance(locs, list) and locs:
        for loc in locs:
            if isinstance(loc, dict):
                lines.append(
                    f"- {(loc.get('name') or 'Location').strip()}: "
                    f"{(loc.get('description') or '').strip()}"
                )
            else:
                lines.append(f"- {loc}")
    else:
        lines.append("- (derive from logline; keep identical)")
    return "\n".join(lines)


def normalize_shot_outline(
    brief: dict[str, Any],
    *,
    pad: bool = False,
) -> list[dict[str, Any]]:
    """Return outline rows from shotOutline or thin shots. Optionally pad to N."""
    brief = brief or {}
    need = int(brief.get("expectedShotCount") or 0)
    shots = brief.get("shots") if isinstance(brief.get("shots"), list) else []
    raw = brief.get("shotOutline") if isinstance(brief.get("shotOutline"), list) else []
    out: list[dict[str, Any]] = []
    if raw:
        for i, row in enumerate(raw):
            if not isinstance(row, dict):
                continue
            idx = int(row.get("index") or (i + 1))
            out.append(
                {
                    "index": idx,
                    "title": str(row.get("title") or f"Shot {idx}").strip(),
                    "beat": str(
                        row.get("beat") or row.get("action") or row.get("title") or ""
                    ).strip(),
                    "camera": str(
                        row.get("camera") or DEFAULT_CAMERA
                    ).strip(),
                }
            )
    elif shots:
        for i, s in enumerate(shots):
            if not isinstance(s, dict):
                continue
            action = str(s.get("action") or "").strip()
            prompt = str(s.get("h3Prompt") or "").strip()
            # Skip empty placeholders — they are not a real outline
            if not action and len(prompt) < 80:
                continue
            out.append(
                {
                    "index": i + 1,
                    "title": str(s.get("title") or action or f"Shot {i + 1}")[:80],
                    "beat": action or (prompt[:160] if prompt else ""),
                    "camera": str(s.get("camera") or DEFAULT_CAMERA).strip(),
                }
            )
    if pad and need and len(out) < need:
        while len(out) < need:
            i = len(out) + 1
            out.append(
                {
                    "index": i,
                    "title": f"Beat {i}",
                    "beat": (
                        f"Continue the story beat for shot {i} of {need}; "
                        f"logline: {brief.get('logline') or 'progress the scene'}"
                    ),
                    "camera": CAMERA_VARIETY[(i - 1) % len(CAMERA_VARIETY)],
                }
            )
    if need and len(out) > need:
        out = out[:need]
    for i, row in enumerate(out):
        row["index"] = i + 1
    return out


_TEMPLATE_FINGERPRINTS = (
    "across 0–5s:",
    "across 0-5s:",
    "across 0–",
    "body systems activate",
    "subtle led/glow",
    "led/glow or muscle",
    "first deliberate motor movement of a hand or arm",
    "subject claims space; slow turn",
    "hold / resolve; subject settles into a strong final pose",
    "awakening / first awareness",
    "picture mood only",
    "visual mood only (silent music video): picture mood only",
    "keep identical face, age, hair and wardrobe",
    "keep identical face, age, hair, eyes and wardrobe",
    "story context remains:",
    "emotional beat is:",
)


def is_thin_template_prompt(text: str) -> bool:
    """True when body is the deterministic placeholder / build_rich filler."""
    plow = (text or "").lower()
    if not plow:
        return True
    hits = sum(1 for fp in _TEMPLATE_FINGERPRINTS if fp in plow)
    if hits >= 2:
        return True
    if any(fp in plow for fp in _BEAT_ARCS):
        return True
    # Boilerplate silent lock dominating a short body
    if "silent visual only for music video" in plow and len(plow) < 1600:
        if "across 0" in plow or "story context remains" in plow:
            return True
    return False


def score_h3_prompt(
    text: str,
    *,
    index: int = 0,
    silent: bool = False,
    shot: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Heuristic quality gate for director-level SCENE bodies."""
    p = (text or "").strip()
    reasons: list[str] = []
    n = len(p)
    if shot and (shot.get("_placeholder") or shot.get("_thin_template")):
        reasons.append("placeholder_shot")
    if is_thin_template_prompt(p):
        reasons.append("thin_template")
    if n < MIN_H3_PROMPT_CHARS:
        reasons.append(f"too_short:{n}<{MIN_H3_PROMPT_CHARS}")
    paras = [x for x in re.split(r"\n\s*\n", p) if x.strip()]
    if len(paras) < 6:
        reasons.append(f"few_paragraphs:{len(paras)}")
    plow = p.lower()
    if index > 0 and not plow.startswith("continue directly"):
        reasons.append("missing_continue_opener")
    if "one continuous shot" not in plow:
        reasons.append("missing_continuous_lock")
    if n < 400 and ("," in p) and p.count("\n") < 3:
        reasons.append("keyword_soup")
    vague = ("they interact", "cinematic shot of", "dark mood, 35mm")
    if any(v in plow for v in vague):
        reasons.append("vague_beat")
    if not silent and re.search(r"\b(bgm|soundtrack|underscore|phonk bed)\b", plow):
        if "no bgm" not in plow and "no music" not in plow and "silent" not in plow:
            reasons.append("bgm_bleed")
    # h3Prompt must be English SCENE body (Turkish OK only inside <d> tags)
    stripped = re.sub(r"<d>.*?</d>", "", p, flags=re.I | re.S)
    if re.search(r"[ğüşıöçĞÜŞİÖÇ]", stripped):
        reasons.append("non_english_scene_body")
    # Creature/fantasy with human skin boilerplate = wrong craft
    if re.search(r"\b(dragon|ejder|wyvern|beast|creature|kaiju)\b", plow):
        if "natural skin texture" in plow or "identical face, age, hair" in plow:
            reasons.append("creature_human_boilerplate")
    hard_prefixes = (
        "too_short",
        "missing_continue_opener",
        "keyword_soup",
        "few_paragraphs",
        "thin_template",
        "placeholder_shot",
        "non_english_scene_body",
        "creature_human_boilerplate",
    )
    hard_hit = [r for r in reasons if any(r.startswith(h) for h in hard_prefixes)]
    ok = len(hard_hit) == 0 and n >= MIN_H3_PROMPT_CHARS
    return {"ok": ok, "chars": n, "reasons": reasons, "paragraphs": len(paras)}


def outline_generation_user_prompt(brief: dict[str, Any]) -> str:
    dur = int(brief.get("clipDurationSec") or 5)
    if dur not in CLIP_DURATIONS:
        dur = 5
    need = brief.get("expectedShotCount")
    try:
        need = int(need) if need is not None else 0
    except (TypeError, ValueError):
        need = 0
    if need < 1:
        total = brief.get("totalDurationSec")
        try:
            total_i = int(total) if total is not None else 0
        except (TypeError, ValueError):
            total_i = 0
        need = expected_shot_count(total_i, dur) if total_i > 0 else 1
    role = str(brief.get("roleHint") or brief.get("_roleHint") or "").strip()
    role_bit = f"\nRole / screenplay tone (optional):\n{role[:4000]}\n" if role else ""
    directives = format_directives_block(brief.get("directorDirectives"))
    intent = brief.get("sceneIntent") if isinstance(brief.get("sceneIntent"), dict) else {}
    scene_bit = ""
    if intent.get("raw"):
        scene_bit = (
            f"\nUSER SCENE (shot 1 beat MUST follow this — inhale/exhale steps, frontal if requested):\n"
            f"{intent['raw']}\n"
            f"English: {intent.get('beat') or intent['raw']}\n"
        )
        if intent.get("camera"):
            scene_bit += f"Camera for shot 1: {intent['camera']}\n"
    return (
        f"FAZ A only. Build a shot OUTLINE for exactly {need} shots "
        f"({dur}s each). Do NOT write h3Prompt bodies.\n"
        f"{format_project_bible(brief)}\n"
        f"{directives}"
        f"{scene_bit}"
        f"{role_bit}"
        "Each outline row MUST have a **distinct** `camera` field (height, lens, movement). "
        "Never copy the same camera line for every shot unless the user explicitly locked one angle.\n"
        "If USER CAMERA NOTES exist above, they override everything — bake them into each row's `camera`.\n"
        "Return ONLY JSON:\n"
        "{\n"
        '  "ready": false,\n'
        '  "phase": "outline",\n'
        '  "brief": {\n'
        f'    "expectedShotCount": {need},\n'
        '    "logline": "...",\n'
        '    "characters": [...],\n'
        '    "locations": [...],\n'
        '    "shotOutline": [\n'
        '      {"index": 1, "title": "...", "beat": "...", "camera": "..."},\n'
        f"      ... exactly {need} items\n"
        "    ],\n"
        '    "shots": []\n'
        "  }\n"
        "}\n"
        "Each beat must be a concrete micro-action for that clip only. "
        "Titles unique. No markdown."
    )


def single_shot_user_prompt(
    brief: dict[str, Any],
    *,
    index: int,
    need: int,
    outline_row: dict[str, Any],
    prev_shot: Optional[dict[str, Any]] = None,
) -> str:
    """FAZ B — write exactly one GOLD STANDARD h3Prompt."""
    dur = int(brief.get("clipDurationSec") or 5)
    link = "standalone"
    title = (outline_row or {}).get("title") or f"Shot {index + 1}"
    beat = (outline_row or {}).get("beat") or title
    camera = camera_for_outline_index(index, directives=brief.get("directorDirectives"), row=outline_row)
    directives = format_directives_block(brief.get("directorDirectives"))
    intent = brief.get("sceneIntent") if isinstance(brief.get("sceneIntent"), dict) else {}
    scene_block = ""
    if intent.get("raw"):
        scene_block = (
            "\nUSER SCENE (mandatory — write THIS action in English SCENE; "
            "no generic 'awakening' beats, no unrelated arcs):\n"
            f"Original: {intent['raw']}\n"
            f"English beat: {intent.get('beat') or intent['raw']}\n"
        )
        if intent.get("camera"):
            scene_block += f"Required camera/framing: {intent['camera']}\n"
    cast_names: list[str] = []
    for c in brief.get("characters") or []:
        if isinstance(c, dict) and (c.get("name") or "").strip():
            cast_names.append(str(c["name"]).strip())
        elif isinstance(c, str) and c.strip():
            cast_names.append(c.strip())
    cast_rule = ""
    if cast_names:
        cast_rule = (
            "CAST NAMES (use these exact spellings in the SCENE when the character appears; "
            "never rename/translate): "
            + ", ".join(cast_names)
            + ".\n"
            "Assign sectionId such as scene-1. Keep the same sectionId and use linkToPrev=continue only when this shot starts at the exact final moment of the previous clip. A recurring character in a new location/action starts a new sectionId with linkToPrev=standalone.\n"
        )
    prev_snip = ""
    if prev_shot and isinstance(prev_shot, dict):
        prev_body = (prev_shot.get("h3Prompt") or "")[:900]
        prev_section = str(prev_shot.get("sectionId") or "scene-1")
        prev_snip = f"PREVIOUS SHOT (sectionId={prev_section}):\n{prev_body}\n"
    return (
        f"FAZ B — write ONLY shot {index + 1} of {need} "
        f"({dur} seconds, suggested linkToPrev={link}).\n"
        f"{H3_PROMPT_GUIDE}\n"
        f"{format_project_bible(brief)}\n"
        f"{directives}"
        f"{scene_block}"
        f"{cast_rule}"
        f"OUTLINE for this shot: title={title!r} beat={beat!r} camera={camera!r}\n"
        f"MANDATORY: `camera` field AND a full paragraph starting with 'The camera:' MUST match {camera!r} exactly. "
        "User camera notes override outline defaults.\n"
        f"{prev_snip}"
        "Return ONLY JSON: "
        '{"shot":{'
        f'"durationSec":{dur},"camera":"...","action":"...","dialogue":[],'
        '"soundscape":"...","music":"none","linkToPrev":'
        f'"standalone|continue","sectionId":"scene-1","h3Prompt":"FULL multi-paragraph SCENE ≥{MIN_H3_PROMPT_CHARS} chars"'
        "}}\n"
        "Rules: English SCENE screenplay; use the current sectionId for an uninterrupted sequence. "
        "A new place, time, or action starts a new sectionId and standalone video. Use linkToPrev=continue only within one section, then start with 'Continue directly from the previous shot.' "
        "+ Same X, same Y, identical clothing; micro-actions only; "
        "no keyword soup; no BGM unless silent music-video lock."
    )


def expand_shots_user_prompt(brief: dict[str, Any], start: int, end: int, need: int) -> str:
    """Legacy chunk expand — prefer single_shot_user_prompt / outline flow."""
    chars = brief.get("characters") or []
    prev = brief.get("shots") or []
    prev_tail = prev[-2:] if prev else []
    outline = normalize_shot_outline(brief)
    slice_out = [o for o in outline if start <= int(o.get("index") or 0) <= end]
    return (
        f"Create shots {start}-{end} of {need} for this music video / film. "
        f"Each shot {brief.get('clipDurationSec', 5)} seconds. Continue chain.\n"
        f"{H3_PROMPT_GUIDE}\n"
        f"{format_project_bible(brief)}\n"
        f"shotOutline_slice={json.dumps(slice_out, ensure_ascii=False)}\n"
        f"characters={json.dumps(chars, ensure_ascii=False)}\n"
        f"previous_shots_tail={json.dumps(prev_tail, ensure_ascii=False)}\n"
        "Return ONLY valid JSON: {\"shots\":[...]} with exactly "
        f"{end - start + 1} shots. Each shot needs camera, action, dialogue[], "
        "soundscape, music, and a FULL cinematic SCENE screenplay as h3Prompt "
        f"(≥{MIN_H3_PROMPT_CHARS} chars, multi-paragraph beat-by-beat — NOT keyword prompts). "
        "Continue shots MUST start with 'Continue directly from the previous shot.' "
        "Keep character age/wardrobe identical. No vague one-liners."
    )
