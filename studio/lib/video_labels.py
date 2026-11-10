"""Burn readable on-screen labels into a finished clip.

Video models garble text, so explainer labels are drawn afterwards: each label is
a transparent PNG (box, optional pointer line and dot) overlaid with FFmpeg for
its time range. Positions are fractions of the frame so they survive any size.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

MAX_LABELS = 12
MAX_CHARS = 60


def _bin(name: str) -> str:
    exe = shutil.which(name)
    if not exe:
        raise RuntimeError(f"{name} is not installed")
    return exe


def _num(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def clean_labels(raw: Any, duration: float | None = None) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    out = []
    for row in rows[:MAX_LABELS]:
        if not isinstance(row, dict):
            continue
        text = " ".join(str(row.get("text") or "").split())[:MAX_CHARS]
        if not text:
            continue
        start = max(0.0, _num(row.get("start"), 0.0))
        end = _num(row.get("end"), start + 3.0)
        if duration:
            start = min(start, max(0.0, duration - 0.1))
            end = min(end, duration)
        if end <= start:
            continue
        out.append({
            "text": text,
            "start": round(start, 2),
            "end": round(end, 2),
            "x": min(1.0, max(0.0, _num(row.get("x"), 0.5))),
            "y": min(1.0, max(0.0, _num(row.get("y"), 0.12))),
            "pointer": bool(row.get("pointer")),
        })
    if not out:
        raise ValueError("add at least one label with text")
    return out


def _font(size: int) -> ImageFont.ImageFont:
    candidates = []
    try:
        import matplotlib

        candidates.append(Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans-Bold.ttf")
    except Exception:
        pass
    candidates += [Path(p) for p in (
        "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    )]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


def layout(label: dict[str, Any], width: int, height: int, box_w: int, box_h: int) -> tuple[int, int]:
    """Top-left corner of the label box; the browser preview uses the same rule."""
    px, py = label["x"] * width, label["y"] * height
    margin = round(height * 0.03)
    if label["pointer"]:
        gap = round(min(width, height) * 0.08)
        left = px + gap if label["x"] < 0.5 else px - gap - box_w
        top = py + gap * 0.5 if label["y"] < 0.5 else py - gap * 0.5 - box_h
    else:
        left, top = px - box_w / 2, py - box_h / 2
    left = min(max(margin, left), width - margin - box_w)
    top = min(max(margin, top), height - margin - box_h)
    return round(left), round(top)


def render_label(label: dict[str, Any], width: int, height: int) -> Image.Image:
    size = max(14, min(72, round(height * 0.042)))
    font = _font(size)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = draw.textbbox((0, 0), label["text"], font=font)
    pad_x, pad_y = round(size * 0.6), round(size * 0.38)
    box_w = min(width - 2, x1 - x0 + 2 * pad_x)
    box_h = y1 - y0 + 2 * pad_y
    left, top = layout(label, width, height, box_w, box_h)
    if label["pointer"]:
        px, py = round(label["x"] * width), round(label["y"] * height)
        anchor_x = left if px < left else left + box_w if px > left + box_w else px
        anchor_y = top if py < top else top + box_h if py > top + box_h else py
        line = max(2, round(size * 0.09))
        draw.line([(px, py), (anchor_x, anchor_y)], fill=(0, 0, 0, 150), width=line + 2)
        draw.line([(px, py), (anchor_x, anchor_y)], fill=(255, 255, 255, 235), width=line)
        dot = max(4, round(size * 0.22))
        draw.ellipse([px - dot, py - dot, px + dot, py + dot], fill=(255, 255, 255, 245), outline=(0, 0, 0, 170), width=2)
    draw.rounded_rectangle([left, top, left + box_w, top + box_h], radius=round(size * 0.35),
                           fill=(12, 14, 18, 190), outline=(255, 255, 255, 70), width=1)
    draw.text((left + pad_x - x0, top + pad_y - y0), label["text"], font=font, fill=(255, 255, 255, 255))
    return canvas


def probe(src: Path) -> dict[str, Any]:
    result = subprocess.run(
        [_bin("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(src)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "could not read the video").strip()[-400:])
    data = json.loads(result.stdout or "{}")
    stream = (data.get("streams") or [{}])[0]
    return {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "duration": _num((data.get("format") or {}).get("duration"), 0.0),
    }


def burn(src: Path, out: Path, labels: list[dict[str, Any]]) -> dict[str, Any]:
    info = probe(src)
    width, height = info["width"], info["height"]
    if not width or not height:
        raise RuntimeError("could not read the video size")
    labels = clean_labels(labels, info["duration"] or None)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out.with_name(out.stem + ".part.mp4")
    with tempfile.TemporaryDirectory(prefix="h3_labels_") as tmp:
        inputs, chain, last = ["-i", str(src)], [], "0:v"
        for index, label in enumerate(labels, 1):
            png = Path(tmp) / f"label_{index}.png"
            render_label(label, width, height).save(png)
            inputs += ["-i", str(png)]
            tag = f"v{index}"
            chain.append(f"[{last}][{index}:v]overlay=0:0:enable='between(t,{label['start']},{label['end']})'[{tag}]")
            last = tag
        cmd = [_bin("ffmpeg"), "-y", "-v", "error", *inputs, "-filter_complex", ";".join(chain),
               "-map", f"[{last}]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
               "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(tmp_out)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            tmp_out.unlink(missing_ok=True)
            raise RuntimeError((result.stderr or "ffmpeg failed").strip()[-400:])
    tmp_out.replace(out)
    return {"labels": labels, **info}
