"""Known H3 LoRAs + Comfy models/loras path helpers."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

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
        "url": "",
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
        "url": "",
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
        "url": "",
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
        "url": "",
        "preset": False,
    },
    {
        "id": "pinkfluffybunny",
        "label": "PinkFluffyBunny (karakter)",
        "file": "PinkFluffyBunny-pruned-v1-rank128.safetensors",
        "steps": None,
        "sampler": None,
        "scheduler": None,
        "strength": 0.75,
        "graphs": ["fl2va", "ref2va"],
        "hint": "Karakter LoRA · Yeni video + Ref/yüz · step aynı",
        "url": "",
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
    }


def find_spec(lora_id: str = "", file: str = "") -> Optional[dict[str, Any]]:
    lid = (lora_id or "").strip()
    fname = Path(file or "").name
    if lid.startswith("file:"):
        fname = lid[5:].strip() or fname
    for spec in CATALOG:
        if lid and spec["id"] == lid:
            return spec
        if fname and spec["file"] == fname:
            return spec
    if fname:
        path = LORAS_DIR / fname
        if path.is_file():
            return disk_spec(fname, path.stat().st_size)
    return None


def file_ready(filename: str) -> bool:
    name = Path(filename or "").name
    if not name:
        return True
    path = LORAS_DIR / name
    return path.is_file() and path.stat().st_size > 1024 * 1024


def public_list() -> list[dict[str, Any]]:
    known_files = {spec["file"] for spec in CATALOG if spec.get("file")}
    out = []
    for spec in CATALOG:
        item = {k: spec[k] for k in spec if k != "url"}
        item["ready"] = file_ready(spec["file"]) if spec["file"] else True
        item["bytes"] = 0
        if spec["file"]:
            p = LORAS_DIR / spec["file"]
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
    return LORAS_DIR / spec["file"]
