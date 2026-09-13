"""Known H3 LoRAs + Comfy models/loras path helpers."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

# studio/ → launcher root → app/models/loras (Pinokio drive link)
STUDIO_ROOT = Path(__file__).resolve().parent.parent
LORAS_DIR = STUDIO_ROOT.parent / "app" / "models" / "loras"

CATALOG: list[dict[str, Any]] = [
    {
        "id": "",
        "label": "Yok (varsayılan)",
        "file": "",
        "steps": 20,
        "sampler": "res_multistep",
        "scheduler": "simple",
        "strength": 1.0,
        "graphs": ["fl2va", "ref2va"],
        "hint": "20 step · res_multistep",
        "url": "",
        "preset": True,
    },
    {
        "id": "lightx2v-turbo",
        "label": "LightX2V Turbo (4 step)",
        "file": "minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors",
        "steps": 4,
        "sampler": "er_sde",
        "scheduler": "simple",
        "strength": 0.75,
        "graphs": ["fl2va"],
        "hint": "Yeni video / first-last · 4 step · strength 0.75 · Ref/V2V’de kullanılmaz",
        "size_hint": "~1.8 GB",
        "url": (
            "https://huggingface.co/Kijai/MiniMax-H3_comfy/resolve/main/"
            "loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors"
            "?download=true"
        ),
        "preset": True,
    },
    {
        "id": "erosmax-4step",
        "label": "ErosMax Turbo (4 step)",
        "file": "minimax_h3_fl2v_turbo_4step_v1.0_768p_10ErosMax_beta1_pruned_compat_v001_T8.safetensors",
        "steps": 4,
        "sampler": "er_sde",
        "scheduler": "simple",
        "strength": 0.8,
        "graphs": ["fl2va"],
        "hint": "4 step turbo · FL2VA · Ref/yüz/V2V’de kullanılmaz",
        "size_hint": "~1.8 GB",
        "adult": True,
        "url": (
            "https://huggingface.co/t8star/"
            "minimax_h3_turbo_4step_10ErosMax_test4_pruned_curveproj1025_T8/resolve/main/"
            "minimax_h3_fl2v_turbo_4step_v1.0_768p_10ErosMax_beta1_pruned_compat_v001_T8.safetensors"
            "?download=true"
        ),
        "preset": True,
    },
    {
        "id": "turbo-6step",
        "label": "H3 Turbo 6-step EMA",
        "file": "minimax_h3_turbo_6step_ema_fl2va_pruned.safetensors",
        "steps": 6,
        "sampler": "er_sde",
        "scheduler": "simple",
        "strength": 0.8,
        "graphs": ["fl2va"],
        "hint": "6 step turbo · FL2VA · Ref/yüz/V2V’de kullanılmaz",
        "size_hint": "~0.8 GB",
        "url": (
            "https://huggingface.co/SanDiegoDude/H3-Turbo-6-Step-LoRA-Comfy/resolve/main/"
            "minimax_h3_turbo_6step_ema_fl2va_pruned.safetensors?download=true"
        ),
        "preset": True,
    },
    {
        "id": "turbo-v4",
        "label": "H3 Turbo v4 EMA",
        "file": "minimax_h3_turbo_v4_step600_ema.safetensors",
        "steps": None,
        "sampler": None,
        "scheduler": None,
        "strength": 0.8,
        "graphs": ["fl2va"],
        "hint": "Turbo · step600 eğitim adımı (4 step değil) · FL2VA · step sen ayarla",
        "size_hint": "~0.7 GB",
        "url": (
            "https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora/resolve/main/"
            "minimax_h3_turbo_v4_step600_ema.safetensors?download=true"
        ),
        "preset": False,
    },
    {
        "id": "h3-realism-people",
        "label": "H3 Realism People",
        "file": "h3-realism-people-t2v-i2v-r2v.safetensors",
        "steps": None,
        "sampler": None,
        "scheduler": None,
        "strength": 0.8,
        "graphs": ["fl2va", "ref2va"],
        "hint": "Gerçekçi insan · T2V / I2V / Ref · step/sampler aynı kalır",
        "size_hint": "~125 MB",
        "url": (
            "https://huggingface.co/fal/MiniMax-H3-Realism-People-LoRA/resolve/main/"
            "h3-realism-people-t2v-i2v-r2v.safetensors?download=true"
        ),
        "preset": False,
    },
    {
        "id": "pinkfluffybunny",
        "label": "PinkFluffyBunny (karakter)",
        "file": "PinkFluffyBunny-pruned-fl2va-v1-rank128.safetensors",
        "aliases": ["PinkFluffyBunny-pruned-v1-rank128.safetensors"],
        "steps": None,
        "sampler": None,
        "scheduler": None,
        "strength": 0.75,
        "graphs": ["fl2va", "ref2va"],
        "hint": "Karakter LoRA · Yeni video + Ref/yüz · step aynı",
        "size_hint": "~2.3 GB",
        "url": (
            "https://huggingface.co/SexGod1979/PinkFluffyBunny-MiniMax-H3/resolve/main/"
            "PinkFluffyBunny-pruned-fl2va-v1-rank128.safetensors?download=true"
        ),
        "preset": False,
    },
    {
        "id": "cinematic-look",
        "label": "Cinematic Look (DY)",
        "file": "minimax_h3_cinematic_look_v01.safetensors",
        "aliases": [
            "Minimax H3真实电影质感V0.1（解决张量报错）.safetensors",
        ],
        "steps": None,
        "sampler": None,
        "scheduler": None,
        "strength": 0.7,
        "graphs": ["fl2va", "ref2va"],
        "hint": "Film dokusu · trigger DY · strength 0.7 (harekette 0.5)",
        "size_hint": "~148 MB",
        "trigger": "DY",
        "url": (
            "https://huggingface.co/Alex995647/loras-minimax-h3/resolve/main/"
            "minimax-h3-cinematic-look-no-tensor-errors/"
            "Minimax%20H3%E7%9C%9F%E5%AE%9E%E7%94%B5%E5%BD%B1%E8%B4%A8%E6%84%9F"
            "V0.1%EF%BC%88%E8%A7%A3%E5%86%B3%E5%BC%A0%E9%87%8F%E6%8A%A5%E9%94%99"
            "%EF%BC%89.safetensors?download=true"
        ),
        "preset": False,
    },
    {
        "id": "better-motion",
        "label": "Better Motion",
        "file": "mvmt_h3_lora_v1_500.safetensors",
        "steps": None,
        "sampler": None,
        "scheduler": None,
        "strength": 0.6,
        "graphs": ["fl2va", "ref2va"],
        "hint": "Hareket kalitesi · strength 0.4–0.8",
        "size_hint": "~296 MB",
        "url": (
            "https://huggingface.co/Alex995647/loras-minimax-h3/resolve/main/"
            "better-motion-ltx-minimax-h3/mvmt_h3_lora_v1_500.safetensors?download=true"
        ),
        "preset": False,
    },
    {
        "id": "spatial-physics",
        "label": "Spatial & Physics",
        "file": "wushu_spatial_physics_clean_3000_pruned.safetensors",
        "steps": None,
        "sampler": None,
        "scheduler": None,
        "strength": 0.85,
        "graphs": ["fl2va", "ref2va"],
        "hint": "Çarpışma / yerçekimi / cisim · strength 0.8–1.0 · turbo ile üst üste",
        "size_hint": "~148 MB",
        "url": (
            "https://huggingface.co/Jojocodex/minimax-h3-spatial-physics-lora/resolve/main/"
            "wushu_spatial_physics_clean_3000_pruned.safetensors?download=true"
        ),
        "preset": False,
    },
    {
        "id": "ref2v-turbo-8step",
        "label": "Ref2V Turbo (8 step)",
        "file": "minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_resized_avg_rank_64_bf16.safetensors",
        "steps": 8,
        "sampler": "er_sde",
        "scheduler": "simple",
        "strength": 0.8,
        "graphs": ["ref2va"],
        "hint": "Ref/yüz 8 step turbo · T2V’de kullanılmaz · er_sde",
        "size_hint": "~933 MB",
        "url": (
            "https://huggingface.co/Alex995647/loras-minimax-h3/resolve/main/"
            "ref2v-turbo-8-step-v1-0-768p-rank-64/"
            "minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_resized_avg_rank_64_bf16"
            ".safetensors?download=true"
        ),
        "preset": True,
    },
    {
        "id": "photoreal-still",
        "label": "Photoreal still (ph0t0r34l)",
        "file": "h3_photoreal_ph0t0r34l_1024-step00003780.safetensors",
        "steps": None,
        "sampler": None,
        "scheduler": None,
        "strength": 1.0,
        "graphs": ["still"],
        "hint": "Karakter/mekan stilli · video kuyruğuna uygulanmaz · trigger ph0t0r34l",
        "size_hint": "~148 MB",
        "trigger": "ph0t0r34l",
        "url": (
            "https://huggingface.co/Alex995647/loras-minimax-h3/resolve/main/"
            "minimax-h3-photorealistic-image-generator-lora-workflow/"
            "h3_photoreal_ph0t0r34l_1024-step00003780.safetensors?download=true"
        ),
        "preset": False,
    },
]

# Shared Comfy loras/ often has SDXL/Pony/Wan/Flux files. H3 cannot use them.
# ClipProj is a text-encoder MLP, not a video LoRA — LoraLoader would break.
_SKIP_LORA = re.compile(
    r"(sdxl|sd[_\- ]?xl|pony|flux|wan[\-_]?2|stable[\-_]?diffusion|clipproj|clip[_-]?proj)",
    re.I,
)


def is_h3_lora_name(filename: str) -> bool:
    name = Path(filename or "").name
    if not name or name.endswith(".part"):
        return False
    return _SKIP_LORA.search(name) is None


def disk_spec(filename: str, bytes_n: int = 0) -> dict[str, Any]:
    name = Path(filename).name
    low = name.lower()
    steps = None
    sampler = None
    scheduler = None
    preset = False
    graphs = ["fl2va", "ref2va"]
    hint = "Klasörden eklendi · step/sampler aynı kalır · sadece MiniMax H3 LoRA"
    if re.search(r"4[\-_]?step", low):
        steps, sampler, scheduler, preset = 4, "er_sde", "simple", True
        graphs = ["fl2va"]
        hint = "4 step turbo · FL2VA · Ref/yüz/V2V’de kullanılmaz"
    elif re.search(r"6[\-_]?step", low):
        steps, sampler, scheduler, preset = 6, "er_sde", "simple", True
        graphs = ["fl2va"]
        hint = "6 step turbo · FL2VA · Ref/yüz/V2V’de kullanılmaz"
    elif "fl2v" in low or "fl2va" in low:
        graphs = ["fl2va"]
        hint = "FL2VA LoRA · Yeni video / first-last"
    return {
        "id": f"file:{name}",
        "label": Path(name).stem,
        "file": name,
        "steps": steps,
        "sampler": sampler,
        "scheduler": scheduler,
        "strength": 0.8,
        "graphs": graphs,
        "hint": hint,
        "url": "",
        "preset": preset,
        "ready": True,
        "bytes": bytes_n,
        "downloadable": False,
        "size_hint": "",
    }


def candidates(spec: dict[str, Any]) -> list[str]:
    names: list[str] = []
    fname = Path(spec.get("file") or "").name
    if fname:
        names.append(fname)
    for alias in spec.get("aliases") or []:
        a = Path(alias or "").name
        if a and a not in names:
            names.append(a)
    return names


def file_ready(filename: str) -> bool:
    name = Path(filename or "").name
    if not name:
        return True
    path = LORAS_DIR / name
    return path.is_file() and path.stat().st_size > 1024 * 1024


def spec_ready(spec: dict[str, Any]) -> bool:
    names = candidates(spec)
    if not names:
        return True
    return any(file_ready(n) for n in names)


def resolved_file(spec: dict[str, Any]) -> str:
    for name in candidates(spec):
        if file_ready(name):
            return name
    return Path(spec.get("file") or "").name


def _copy_spec(spec: dict[str, Any]) -> dict[str, Any]:
    item = dict(spec)
    item["aliases"] = list(spec.get("aliases") or [])
    item["file"] = resolved_file(spec) or spec.get("file") or ""
    return item


def is_still_lora(spec: Optional[dict[str, Any]]) -> bool:
    graphs = (spec or {}).get("graphs") or []
    return "still" in graphs


def still_catalog_spec() -> Optional[dict[str, Any]]:
    for spec in CATALOG:
        if is_still_lora(spec):
            return _copy_spec(spec)
    return None


def apply_trigger(text: str, spec: Optional[dict[str, Any]] = None) -> str:
    """Prepend a LoRA trigger word when the prompt does not already include it."""
    trig = str((spec or {}).get("trigger") or "").strip()
    body = text or ""
    if not trig:
        return body
    if trig.lower() in body.lower():
        return body
    return f"{trig}, {body}".strip()


def is_adult_lora(*, lora_id: str = "", file: str = "", spec: Optional[dict[str, Any]] = None) -> bool:
    row = spec if spec is not None else find_spec(lora_id=lora_id, file=file)
    if not row:
        return False
    if row.get("adult"):
        return True
    label = f"{row.get('id') or ''} {row.get('file') or ''} {row.get('label') or ''}".lower()
    return "erosmax" in label


def find_spec(lora_id: str = "", file: str = "") -> Optional[dict[str, Any]]:
    lid = (lora_id or "").strip()
    fname = Path(file or "").name
    if lid.startswith("file:"):
        fname = lid[5:].strip() or fname
    for spec in CATALOG:
        if lid and spec["id"] == lid:
            return _copy_spec(spec)
        if fname and fname in candidates(spec):
            return _copy_spec(spec)
    if fname:
        path = LORAS_DIR / fname
        if path.is_file():
            return disk_spec(fname, path.stat().st_size)
    return None


def public_list() -> list[dict[str, Any]]:
    known_files: set[str] = set()
    for spec in CATALOG:
        known_files.update(candidates(spec))
    out = []
    for spec in CATALOG:
        item = {k: spec[k] for k in spec if k not in ("url", "aliases")}
        item["adult"] = bool(spec.get("adult")) or is_adult_lora(spec=spec)
        item["ready"] = spec_ready(spec)
        item["downloadable"] = bool(spec.get("url"))
        item["size_hint"] = spec.get("size_hint") or ""
        item["bytes"] = 0
        on_disk = resolved_file(spec) if spec.get("file") else ""
        if on_disk:
            item["file"] = on_disk
            p = LORAS_DIR / on_disk
            if p.is_file():
                item["bytes"] = p.stat().st_size
        # Local-only entries (no download URL) stay hidden until the file exists.
        if spec.get("file") and not item["ready"] and not spec.get("url"):
            continue
        out.append(item)
    if LORAS_DIR.is_dir():
        for p in sorted(LORAS_DIR.glob("*.safetensors")):
            if p.name in known_files or p.name.endswith(".part"):
                continue
            if not is_h3_lora_name(p.name):
                continue
            if p.stat().st_size < 1024 * 1024:
                continue
            out.append(disk_spec(p.name, p.stat().st_size))
    return out


def dest_for(spec: dict[str, Any]) -> Path:
    LORAS_DIR.mkdir(parents=True, exist_ok=True)
    lid = spec.get("id") or ""
    for row in CATALOG:
        if lid and row.get("id") == lid and row.get("file"):
            return LORAS_DIR / row["file"]
    return LORAS_DIR / Path(spec.get("file") or "lora.safetensors").name


def filename_from_url(url: str, fallback: str = "") -> str:
    """Last path segment if it is a .safetensors file (Hugging Face resolve URLs work)."""
    raw = (url or "").strip()
    name = Path(unquote(urlparse(raw).path)).name
    if name.lower().endswith(".safetensors") and is_h3_lora_name(name):
        return name
    fb = Path(fallback or "").name
    if fb.lower().endswith(".safetensors") and is_h3_lora_name(fb):
        return fb
    return ""
