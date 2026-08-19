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

# Short film / ad / trailer / social: dialogue + diegetic SFX only (one H3 audio track).
NO_BGM_AUDIO_LOCK = (
    "AUDIO POLICY — NO MUSIC / NO SCORE: no background music, no BGM, no soundtrack, "
    "no non-diegetic underscore, no phonk/techno/orchestral bed, no singing. "
    "Allowed audio only: (1) spoken dialogue in <d>[Lang]…</d> tags with lipsync, "
    "(2) diegetic environmental and action SFX — footsteps, wind, rain, vehicles, "
    "weapons, swords, gunfire, impacts, debris, explosions, cloth, breath, room tone. "
    "Keep the mix dry and diegetic; do not invent a song."
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
    purpose = (brief.get("purpose") or "").lower().strip()
    return bool(brief.get("silentAudio")) or purpose in (
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
    """Silent music-video locks, or dialogue+SFX-only (no BGM) for other purposes."""
    silent = _is_silent_brief(brief)
    p = (prompt or "").strip()
    if silent:
        low = p.lower()
        if "silent visual only" in low or "no generated music" in low:
            return p
        return (p + "\n\n" + SILENT_MUSIC_VIDEO_LOCK).strip()
    p = upgrade_inline_dialogue_tags(p)
    low = p.lower()
    if "audio policy — no music" in low or "no background music, no bgm" in low:
        return p
    return (p + "\n\n" + NO_BGM_AUDIO_LOCK).strip()


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
    "dialogue": ["<d>[Turkish] …</d>"],
    "h3Prompt": "FULL SCENE body for that shot only"
  }
}
```

Birden fazla shot: `"patches": [{ "shot": 2, ... }, { "shot": 5, ... }]`.
`shot` 1-indexed. h3Prompt kalitesi GOLD STANDARD (continue lock shot 2+).
Türkçe `reply` ile ne değiştiğini söyle. Üretime alma, kuyruk yok.
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
    if not isinstance(shots, list) or not shots:
        return ""
    clip = brief.get("clipDurationSec") or ""
    total = brief.get("totalDurationSec") or ""
    need = brief.get("expectedShotCount") or len(shots)
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
        f"clipDurationSec={clip} totalDurationSec={total} shots={len(shots)}/{need}",
    ]
    if char_bits:
        lines.append("characters: " + " | ".join(char_bits[:8]))
    for i, shot in enumerate(shots):
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
            f"character {c.get('name') or '?'}: {_clip_text(c.get('description'), 220)}"
            + (f" voice={_clip_text(c.get('voice'), 80)}" if c.get("voice") else "")
        )
    for loc in locs:
        if not isinstance(loc, dict):
            continue
        lines.append(
            f"location {loc.get('name') or '?'}: {_clip_text(loc.get('description'), 220)}"
        )
    for i, shot in enumerate(shots):
        if isinstance(shot, dict):
            mode = shot.get("mode") or "t2v"
            text = shot.get("text") or shot.get("prompt") or ""
        else:
            mode = "t2v"
            text = str(shot)
        lines.append(f"\n## Studio shot {i + 1} · {mode}\n{_clip_text(text, cap)}")
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
        lambda m: f'"dialogue": ["<d>[Turkish] {m.group(1)}</d>"]',
        t,
    )
    # bare Lang dialogue typos
    t = re.sub(
        r'"dialogue"\s*:\s*"([^"]*)"',
        lambda m: f'"dialogue": ["<d>[Turkish] {m.group(1)}</d>"]',
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
        need = 12 if total and total >= 60 else None
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
    out = {
        "purpose": purpose,
        "visualStyle": style if style in VISUAL_STYLES else "realistic",
        "clipDurationSec": clip,
        "aspect": brief.get("aspect") or brief.get("aspectRatio") or "16:9",
        "logline": logline,
        "totalDurationSec": int(total or (need or 1) * clip),
        "expectedShotCount": int(need or max(1, len(shots))),
        "characters": chars,
        "shots": shots,
        "silentAudio": purpose == "music_video",
        "shotsIncomplete": True,
    }
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

    # Explicit shot count: "12 shot", "12×5", "12 x 5" — not "16:9" or JSON keys.
    m = re.search(
        r"(?<![A-Za-z_])(\d{1,3})\s*(?:[×x]\s*(?:4|5|6|8|10|15)\s*)?(?:shot|sahne|klip)\b",
        raw,
        re.I,
    )
    if m:
        n = int(m.group(1))
        if 1 <= n <= 120:
            return n * clip, n

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
            f"{name} is {desc}. Keep identical face, age, hair, eyes and wardrobe."
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
    t0 = index * dur
    t1 = t0 + dur
    cameras = (
        "low angle slow push-in, 35mm, shallow depth of field",
        "tight medium close-up with subtle lateral drift, 50mm",
        "slow circular orbit at medium distance, 35mm",
        "low tracking shot parallel to the subject, 35mm",
        "pull-back reveal from medium to wide, 35mm",
    )
    camera = cameras[index % len(cameras)]
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
        link = "standalone"
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
        shots = force_continue_chain(shots[:need])
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
        char_paras.append(f"{name}: {desc}. Keep identical face, age, hair and wardrobe.")
        same_lock_bits.append(f"same {name}")
    style = normalize_style(brief.get("visualStyle"))
    style_txt = style_craft_line(style)
    camera = (shot.get("camera") or "eye-level medium shot, subtle push-in, 35mm").strip()
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
    link = (shot.get("linkToPrev") or ("standalone" if index == 0 else "continue")).strip()
    base = (shot.get("h3Prompt") or "").strip()

    silent = _is_silent_brief(brief)

    # Model already wrote SCENE-density screenplay — keep (ensure continue opener + <d> tags)
    if len(base) >= 1100:
        out = base
        if link == "continue" and not base.lower().startswith("continue directly"):
            out = "Continue directly from the previous shot.\n\n" + base
        out = ensure_dialogue_in_h3_prompt(out, dlg, silent=silent)
        return apply_audio_policy(out, brief)

    same_lock = (
        ", ".join(same_lock_bits) + ", identical clothing and appearance"
        if same_lock_bits
        else "same characters, identical clothing and appearance"
    )
    char_block = "\n\n".join(char_paras) if char_paras else "Keep cast continuity across the continue chain."
    beats = action or base or "characters hold tension; micro-expressions progress the emotional beat"
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
                    "Clear spoken dialogue audio, mouth moves in sync. "
                    f"{NO_BGM_AUDIO_LOCK}"
                    if dlg
                    else f"One continuous shot, no cuts. No dialogue. {NO_BGM_AUDIO_LOCK}"
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
                    "Clear spoken dialogue audio, mouth moves in sync. "
                    f"{NO_BGM_AUDIO_LOCK}"
                    if dlg
                    else f"One continuous shot, no cuts. No dialogue. {NO_BGM_AUDIO_LOCK}"
                )
            ),
        ]
    body = "\n\n".join(p for p in paras if p)
    body = ensure_dialogue_in_h3_prompt(body, dlg, silent=silent)
    return apply_audio_policy(body, brief)


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
    link = s.get("linkToPrev") or ("standalone" if i == 0 else "continue")
    if link not in ("standalone", "continue", "ref"):
        link = "continue" if i else "standalone"
    shot = {
        "durationSec": sd,
        "camera": s.get("camera") or "",
        "action": action,
        "dialogue": dlg,
        "soundscape": s.get("soundscape") or "",
        "music": s.get("music") or "",
        "h3Prompt": prompt or action,
        "linkToPrev": link,
    }
    if brief is not None:
        shot["h3Prompt"] = build_rich_h3_prompt(
            shot=shot, index=i, total=total_shots or (i + 1), brief=brief
        )
    return shot


def force_continue_chain(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, s in enumerate(shots):
        ss = dict(s)
        ss["linkToPrev"] = "standalone" if i == 0 else "continue"
        out.append(ss)
    return out


def validate_brief(brief: dict[str, Any]) -> dict[str, Any]:
    dur = int(brief.get("clipDurationSec") or 5)
    if dur not in CLIP_DURATIONS:
        dur = 5
    brief["clipDurationSec"] = dur
    brief["aspect"] = brief.get("aspect") or "16:9"

    total = brief.get("totalDurationSec")
    if total is not None:
        parsed = parse_duration_to_seconds(total)
        if parsed:
            brief["totalDurationSec"] = parsed
            total = parsed
    need = None
    if isinstance(total, int) and total > 0:
        computed = expected_shot_count(total, dur)
        need = computed
        brief["expectedShotCount"] = need

    raw_shots = brief.get("shots") or []
    cleaned = []
    n_hint = need or len(raw_shots) or 1
    for i, s in enumerate(raw_shots):
        c = _clean_shot(s, i, dur, brief=brief, total_shots=n_hint)
        if c:
            cleaned.append(c)

    # Respect optional "force_continue" flag on the brief (default True)
    if brief.get("force_continue", True):
        cleaned = force_continue_chain(cleaned)
    if need and len(cleaned) > need:
        cleaned = cleaned[:need]

    # Re-enrich with final count
    final = []
    for i, s in enumerate(cleaned):
        s2 = dict(s)
        s2["h3Prompt"] = build_rich_h3_prompt(
            shot=s2, index=i, total=len(cleaned), brief=brief
        )
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
            "Dialogue tags stay `<d>[English]…</d>` or `<d>[Turkish]…</d>` matching the spoken line, "
            "not the UI language.\n"
        )
    return (
        "\n\n## ARAYÜZ DİLİ\n"
        "Kullanıcıya **Türkçe** konuş (`reply` ve sohbet). JSON anahtarları İngilizce.\n"
        "Her `h3Prompt` / SCENE gövdesi her zaman İngilizce — UI TR olsa bile.\n"
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
            "I write each shot as a **cinematic SCENE screenplay**, not a short keyword prompt "
            "(character card, micro-action, camera, atmosphere).\n"
            "**music video** = silent picture + song mux at the end.\n"
            "Type: short film / ad / trailer / social / documentary / intro / outro.\n"
            "Look: realistic, anime, disney, game, 3D CGI, comic, illustration, oil paint, clay, found footage.\n"
            "Give duration + story + character/location; then **Queue for production**.\n"
            "The **Plan** tab lets you read and edit every shot.\n\n"
            "What are we making? Look and total duration in seconds?"
        )
    return (
        "Merhaba — ben **H3 Yönetmen**. Chip’ten proje seç.\n\n"
        "Her shot’u kısa prompt değil, **sinematik SCENE senaryosu** yazarım "
        "(karakter kartı, mikro eylem, kamera, atmosfer — Arrival/Shadow kalitesi).\n"
        "**müzik klibi** = sessiz görüntü + finalde şarkı mux.\n"
        "Tür: kısa film / reklam / trailer / sosyal / belgesel / intro / outro.\n"
        "Tarz: gerçekçi, anime, disney, oyun, 3D CGI, çizgi roman, illüstrasyon, yağlı boya, kil, found footage.\n"
        "Süre + hikâye + karakter/lokasyon ver; bitince **Üretime al**.\n"
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


def expand_shots_user_prompt(brief: dict[str, Any], start: int, end: int, need: int) -> str:
    chars = brief.get("characters") or []
    prev = brief.get("shots") or []
    prev_tail = prev[-2:] if prev else []
    return (
        f"Create shots {start}-{end} of {need} for this music video / film. "
        f"Each shot {brief.get('clipDurationSec', 5)} seconds. Continue chain.\n"
        f"{H3_PROMPT_GUIDE}\n"
        f"purpose={brief.get('purpose')} style={brief.get('visualStyle')} "
        f"aspect={brief.get('aspect')} logline={brief.get('logline')}\n"
        f"characters={json.dumps(chars, ensure_ascii=False)}\n"
        f"previous_shots_tail={json.dumps(prev_tail, ensure_ascii=False)}\n"
        "Return ONLY valid JSON: {\"shots\":[...]} with exactly "
        f"{end - start + 1} shots. Each shot needs camera, action, dialogue[], "
        "soundscape, music, and a FULL cinematic SCENE screenplay as h3Prompt "
        "(≥1100 chars, multi-paragraph beat-by-beat — NOT keyword prompts). "
        "Write like director shot notes: character cards, micro-actions, camera moves, "
        "atmosphere, technical close, 'One continuous shot, no cuts'. "
        "Each h3Prompt must be ≥1100 chars with 8+ short paragraphs — never keyword soup. "
        "Continue shots MUST start with 'Continue directly from the previous shot.' "
        "Keep character age/wardrobe identical. No vague one-liners."
    )
