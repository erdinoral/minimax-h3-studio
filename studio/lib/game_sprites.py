"""Game sprites from H3 clips: local colour-key masking, shared scaling and sheet export.

Everything runs on the CPU with numpy, Pillow and scipy.ndimage from the shared env.
The source clip is never modified; every processing run writes a fresh folder.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from PIL import Image

try:
    from scipy import ndimage
except ImportError:  # pragma: no cover - scipy ships with the ComfyUI env
    ndimage = None


FORMAT = "h3-studio-sprite-sheet"
FORMAT_VERSION = 1
CELLS = (32, 64, 128)
DEFAULT_CELL = 64
PALETTES = (0, 8, 16, 32, 64)
DETAILS = {"fine": 0.2, "balanced": 0.35, "clean": 0.5}
BACKDROPS = ("green", "blue")
MAX_FRAMES = 32
SHEET_COLUMNS = 8

# loop: plays back to frame 0; pivot "locked" pins the feet and torso column per frame,
# "free" keeps the clip's own motion (a jump keeps its height).
ANIMATIONS: dict[str, dict] = {
    "idle": {"loop": True, "pivot": "locked", "frames": 6, "fps": 8, "duration": 4,
             "action": "stands in place in a relaxed idle stance, breathing gently with a subtle rhythmic body bob, feet planted"},
    "walk": {"loop": True, "pivot": "locked", "frames": 8, "fps": 10, "duration": 4,
             "action": "walks in place on the spot with a steady repeating walk cycle, like on a treadmill; the body stays at the same position in the frame and never travels"},
    "run": {"loop": True, "pivot": "locked", "frames": 8, "fps": 12, "duration": 4,
            "action": "runs in place on the spot with a steady repeating run cycle, like on a treadmill; the body stays at the same position in the frame and never travels"},
    "jump": {"loop": False, "pivot": "free", "frames": 10, "fps": 12, "duration": 3,
             "action": "crouches, jumps straight up in place, rises, then lands back on the same spot and settles into a standing pose; exactly one jump"},
    "attack": {"loop": False, "pivot": "free", "frames": 8, "fps": 12, "duration": 3,
               "action": "performs one quick attack with its weapon or fists, a single strike toward the right, then returns to its ready stance without stepping away"},
    "hurt": {"loop": False, "pivot": "free", "frames": 5, "fps": 10, "duration": 3,
             "action": "gets hit, flinches backward once, then recovers to its stance on the same spot"},
    "death": {"loop": False, "pivot": "free", "frames": 8, "fps": 10, "duration": 4,
              "action": "is defeated, collapses to the ground on the same spot and lies still, the whole body staying inside the frame"},
    "crouch": {"loop": True, "pivot": "locked", "frames": 4, "fps": 6, "duration": 4,
               "action": "holds a low crouched pose in place with slight breathing"},
    "cast": {"loop": False, "pivot": "free", "frames": 8, "fps": 10, "duration": 3,
             "action": "casts a spell with one expressive hand gesture toward the right, then returns to its stance on the same spot"},
    "victory": {"loop": False, "pivot": "free", "frames": 8, "fps": 10, "duration": 4,
                "action": "celebrates a victory in place with one cheerful pose, then holds it"},
}


class SpriteError(ValueError):
    """A request or clip that cannot produce a usable sprite. ``code`` maps to UI text."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def presets() -> dict:
    return {
        "animations": [{"id": key, **{k: v for k, v in spec.items() if k != "action"}}
                       for key, spec in ANIMATIONS.items()],
        "cells": list(CELLS),
        "default_cell": DEFAULT_CELL,
        "palettes": list(PALETTES),
        "details": list(DETAILS),
        "backdrops": list(BACKDROPS),
        "max_frames": MAX_FRAMES,
    }


def build_prompt(animation: str, description: str = "") -> str:
    """H3 prompt for one animation. The backdrop line is added by the shared generate path."""
    spec = ANIMATIONS.get(animation)
    if not spec:
        raise SpriteError("game.badAnimation", animation)
    who = re.sub(r"\s+", " ", str(description or "")).strip()[:400]
    subject = f"the character ({who})" if who else "the character"
    cycle = ("The motion is one continuous repeating cycle that starts and ends in the same pose, with no pause."
             if spec["loop"] else
             "The action happens once from start to finish, then the character holds still.")
    return (
        f"<Picture 1> is the character reference. Side view of exactly one character: {subject} from "
        f"<Picture 1>, seen in full profile facing right, {spec['action']}. {cycle} "
        "The whole body, including feet, hands and any held object, stays fully inside the frame at all "
        "times with clear empty space on every side; the character fills about half of the frame height. "
        "Locked-off static camera at body height: no camera movement, no pan, no tracking, no zoom, no cuts, "
        "no motion blur. Flat even lighting with no cast shadow on the floor, no floor line, no props, "
        "no other characters, no text. Keep the character's identity, face, hairstyle, outfit, colors, "
        "proportions and any held objects exactly as in <Picture 1>. Clean, readable motion for a 2D game sprite."
    )


@dataclass
class SpriteSettings:
    cell: int = DEFAULT_CELL
    frames: int = 8
    fps: float = 10.0
    palette: int = 0
    tolerance: float = 30.0
    hole_tolerance: float = 18.0
    edge_clean: int = 1
    detail: str = "balanced"
    despill: bool = True
    loop_start: Optional[float] = None
    loop_end: Optional[float] = None

    def as_dict(self) -> dict:
        return asdict(self)


def settings_for(animation: str, raw: Optional[dict] = None) -> SpriteSettings:
    """Validated settings; animation presets fill frames/fps the request leaves out."""
    spec = ANIMATIONS.get(animation)
    if not spec:
        raise SpriteError("game.badAnimation", animation)
    raw = dict(raw or {})

    def num(key, default, lo, hi, cast=float):
        value = raw.get(key, default)
        try:
            value = cast(value)
        except (TypeError, ValueError):
            raise SpriteError("game.badSettings", key)
        if not math.isfinite(float(value)) or value < lo or value > hi:
            raise SpriteError("game.badSettings", key)
        return value

    cell = num("cell", DEFAULT_CELL, 1, 4096, int)
    if cell not in CELLS:
        raise SpriteError("game.badSettings", "cell")
    palette = num("palette", 0, 0, 256, int)
    if palette not in PALETTES:
        raise SpriteError("game.badSettings", "palette")
    detail = str(raw.get("detail") or "balanced")
    if detail not in DETAILS:
        raise SpriteError("game.badSettings", "detail")
    start = raw.get("loop_start")
    end = raw.get("loop_end")
    start = None if start in (None, "") else num("loop_start", 0, 0, 120)
    end = None if end in (None, "") else num("loop_end", 0, 0, 120)
    if start is not None and end is not None and end <= start:
        raise SpriteError("game.badSettings", "loop_end")
    return SpriteSettings(
        cell=cell,
        frames=num("frames", spec["frames"], 2, MAX_FRAMES, int),
        fps=round(num("fps", spec["fps"], 1, 60), 3),
        palette=palette,
        tolerance=num("tolerance", 30, 1, 100),
        hole_tolerance=num("hole_tolerance", 18, 0, 100),
        edge_clean=num("edge_clean", 1, 0, 3, int),
        detail=detail,
        despill=bool(raw.get("despill", True)),
        loop_start=start,
        loop_end=end,
    )


# Backdrop suggestion.
def _hsv(rgb: np.ndarray) -> np.ndarray:
    return np.asarray(Image.fromarray(rgb, "RGB").convert("HSV"), dtype=np.int16)


def suggest_backdrop(rgb: np.ndarray) -> dict:
    """Pick the key colour the character uses least. The reference's own flat background is ignored."""
    rgb = np.ascontiguousarray(rgb[..., :3], dtype=np.uint8)
    h, w = rgb.shape[:2]
    scale = max(1, int(max(h, w) / 256))
    small = rgb[::scale, ::scale]
    ring = np.concatenate([small[0], small[-1], small[:, 0], small[:, -1]]).astype(np.int16)
    border = np.median(ring, axis=0)
    spread = float(np.mean(np.abs(ring - border)))
    subject = np.ones(small.shape[:2], bool)
    if spread < 24:
        subject = np.abs(small.astype(np.int16) - border).sum(axis=2) > 60
    if subject.sum() < 16:
        subject = np.ones(small.shape[:2], bool)
    hsv = _hsv(small)[subject]
    hue, sat, val = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    vivid = (sat > 70) & (val > 50)
    total = max(1, len(hsv))
    # PIL hue is 0..255: green about 60-165 degrees, blue about 185-265 degrees.
    scores = {
        "green": round(float(np.sum(vivid & (hue >= 42) & (hue <= 117))) / total, 4),
        "blue": round(float(np.sum(vivid & (hue >= 131) & (hue <= 188))) / total, 4),
    }
    suggested = min(BACKDROPS, key=lambda c: (scores[c], BACKDROPS.index(c)))
    return {"suggested": suggested, "scores": scores, "conflict": scores[suggested] > 0.08}


# Colour key.
_YCC = np.array([[0.299, 0.587, 0.114],
                 [-0.168736, -0.331264, 0.5],
                 [0.5, -0.418688, -0.081312]], dtype=np.float32)
_LUMA_WEIGHT = 0.35
_TOLERANCE_SCALE = 1.2


def _threshold(tolerance: float) -> float:
    return float(tolerance) * _TOLERANCE_SCALE


def key_distance(rgb: np.ndarray, key: Iterable[float]) -> np.ndarray:
    """Chroma-weighted distance to the key; brightness counts less so shaded screen still keys."""
    diff = rgb[..., :3].astype(np.float32) - np.asarray(list(key), dtype=np.float32)
    ycc = diff @ _YCC.T
    ycc[..., 0] *= _LUMA_WEIGHT
    return np.sqrt(np.sum(ycc * ycc, axis=-1))


def _keyish(rgb: np.ndarray, backdrop: str) -> np.ndarray:
    r, g, b = (rgb[..., i].astype(np.int16) for i in range(3))
    if backdrop == "blue":
        return (b > r + 25) & (b > g + 10)
    return (g > r + 25) & (g > b + 25)


def _ring(shape: tuple[int, int]) -> np.ndarray:
    h, w = shape
    width = max(2, int(round(0.02 * min(h, w))))
    ring = np.zeros((h, w), bool)
    ring[:width] = ring[-width:] = True
    ring[:, :width] = ring[:, -width:] = True
    return ring


def estimate_key(frames: list[np.ndarray], backdrop: str) -> tuple[np.ndarray, float]:
    """Median screen colour from the frame borders and the share of border that looks like screen."""
    if backdrop not in BACKDROPS:
        raise SpriteError("game.badBackdrop", str(backdrop))
    if not frames:
        raise SpriteError("game.noFrames")
    step = max(1, len(frames) // 12)
    ring = _ring(frames[0].shape[:2])
    pixels = np.concatenate([f[ring] for f in frames[::step]])
    keyish = _keyish(pixels, backdrop)
    match = float(keyish.mean()) if len(pixels) else 0.0
    if keyish.any():
        key = np.median(pixels[keyish].astype(np.float32), axis=0)
    else:
        key = np.array([0, 255, 0] if backdrop == "green" else [0, 0, 255], np.float32)
    return key, match


def _need_scipy():
    if ndimage is None:
        raise SpriteError("game.noScipy", "scipy is required for sprite masking")


_FOUR = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)
_EIGHT = np.ones((3, 3), bool)


def _edge_background(candidate: np.ndarray) -> np.ndarray:
    labels, count = ndimage.label(candidate, structure=_FOUR)
    if not count:
        return np.zeros_like(candidate)
    edge = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    edge = edge[edge > 0]
    return np.isin(labels, edge)


def mask_frame(dist: np.ndarray, s: SpriteSettings) -> np.ndarray:
    """Foreground mask from a key-distance map. True = character."""
    _need_scipy()
    thr = _threshold(s.tolerance)
    candidate = dist < thr
    bg = _edge_background(candidate)
    if s.hole_tolerance > 0:
        # Screen seen between arms, legs or a held object is not edge-connected. Such a
        # pocket is removed only when most of it matches the screen closely, so character
        # parts that merely resemble the key colour stay.
        pockets, count = ndimage.label(candidate & ~bg, structure=_FOUR)
        if count:
            index = np.arange(1, count + 1)
            sizes = ndimage.sum(np.ones_like(dist), pockets, index)
            strict = ndimage.mean(dist < _threshold(s.hole_tolerance), pockets, index)
            min_area = max(6.0, 0.00015 * dist.size)
            keep = np.concatenate([[False], (sizes >= min_area) & (strict >= 0.6)])
            bg |= keep[pockets]
    fg = ~bg
    if s.edge_clean:
        fringe_thr = thr * 1.3
        for _ in range(int(s.edge_clean)):
            edge = fg & ~ndimage.binary_erosion(fg, structure=_EIGHT, border_value=0)
            fringe = edge & (dist < fringe_thr)
            if not fringe.any():
                break
            fg &= ~fringe
    labels, count = ndimage.label(fg, structure=_EIGHT)
    if count > 1:
        sizes = ndimage.sum(np.ones_like(dist), labels, np.arange(1, count + 1))
        keep = np.concatenate([[False], sizes >= max(16.0, 0.01 * float(sizes.max()))])
        fg = keep[labels]
    return fg


def stabilize(masks: list[np.ndarray], dists: list[np.ndarray], center: int, tolerance: float) -> np.ndarray:
    """Majority vote with the neighbouring source frames, only where the key distance is borderline."""
    current = masks[center]
    if len(masks) < 3:
        return current
    thr = _threshold(tolerance)
    unsure = np.abs(dists[center] - thr) < 0.3 * thr
    votes = sum(m.astype(np.uint8) for m in masks)
    return np.where(unsure, votes >= 2, current)


def clean_colors(rgb: np.ndarray, fg: np.ndarray, key: np.ndarray, dist: np.ndarray, s: SpriteSettings) -> np.ndarray:
    """Despill the edge band, then pull every background pixel to its nearest character colour
    so nearest-neighbour sampling never picks screen colour."""
    out = rgb[..., :3].copy()
    if s.despill and fg.any():
        band = fg & ndimage.binary_dilation(~fg, structure=_EIGHT, iterations=2)
        band &= dist < _threshold(s.tolerance) * 1.6
        dom = int(np.argmax(key))
        others = [i for i in range(3) if i != dom]
        limit = np.maximum(out[..., others[0]], out[..., others[1]])
        spill = band & (out[..., dom] > limit)
        out[..., dom] = np.where(spill, limit, out[..., dom])
    if fg.any() and not fg.all():
        idx = ndimage.distance_transform_edt(~fg, return_distances=False, return_indices=True)
        out = out[idx[0], idx[1]]
    return out


# Frame sources.
class ArrayFrames:
    """In-memory frames (tests and previews)."""

    def __init__(self, frames: list[np.ndarray], fps: float = 24.0):
        self.frames = [np.ascontiguousarray(f[..., :3], dtype=np.uint8) for f in frames]
        self.fps = float(fps)
        self.count = len(self.frames)
        self.size = self.frames[0].shape[1::-1] if self.frames else (0, 0)

    def analysis(self, step: int) -> list[np.ndarray]:
        return [f[::step, ::step] for f in self.frames]

    def read(self, indices: Iterable[int]) -> dict[int, np.ndarray]:
        return {i: self.frames[i] for i in sorted(set(indices)) if 0 <= i < self.count}


def _ffmpeg() -> str:
    from lib.frames import _ffmpeg as find
    return find()


def probe_video(path: Path) -> tuple[int, int, float]:
    r = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    blob = (r.stderr or "") + (r.stdout or "")
    line = next((ln for ln in blob.splitlines() if "Video:" in ln), "")
    size = re.search(r"\b(\d{2,5})x(\d{2,5})\b", line)
    fps = re.search(r"(\d+(?:\.\d+)?) fps", line)
    if not size:
        raise SpriteError("game.badVideo", "no video stream")
    return int(size.group(1)), int(size.group(2)), float(fps.group(1)) if fps else 24.0


class VideoFrames:
    """Streams rgb24 frames from ffmpeg; only requested frames are kept in memory."""

    def __init__(self, path: Path):
        self.path = Path(path)
        w, h, self.fps = probe_video(self.path)
        self.size = (w, h)
        self.count = 0

    def _stream(self):
        w, h = self.size
        frame_bytes = w * h * 3
        proc = subprocess.Popen(
            [_ffmpeg(), "-v", "error", "-i", str(self.path), "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            index = 0
            while True:
                buf = proc.stdout.read(frame_bytes)
                if len(buf) < frame_bytes:
                    break
                yield index, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
                index += 1
        finally:
            proc.stdout.close()
            proc.kill()
            proc.wait()

    def analysis(self, step: int) -> list[np.ndarray]:
        out = [frame[::step, ::step].copy() for _, frame in self._stream()]
        self.count = len(out)
        return out

    def read(self, indices: Iterable[int]) -> dict[int, np.ndarray]:
        wanted = set(indices)
        last = max(wanted) if wanted else -1
        out = {}
        for index, frame in self._stream():
            if index in wanted:
                out[index] = frame.copy()
            if index >= last:
                break
        return out


# Frame window.
def _pair_diff(sa, sb, ca, cb) -> float:
    union = sa | sb
    n = int(union.sum())
    if not n:
        return 0.0
    iou = float((sa & sb).sum()) / n
    color = float(np.abs(ca[union].astype(np.int16) - cb[union].astype(np.int16)).mean()) / 255.0
    return 0.6 * (1.0 - iou) + 0.4 * color


def choose_window(sil: list[np.ndarray], low: list[np.ndarray], fps: float, loop: bool,
                  animation: str, s: SpriteSettings) -> dict:
    """Source frame range. Loops search the period with the closest seam; one-shots trim still ends."""
    total = len(sil)
    if total < 2:
        raise SpriteError("game.noFrames")
    if s.loop_start is not None or s.loop_end is not None:
        a = int(round((s.loop_start or 0) * fps))
        b = int(round(s.loop_end * fps)) if s.loop_end is not None else total
        a, b = max(0, min(a, total - 2)), max(0, min(b, total))
        if b - a < 2:
            raise SpriteError("game.badSettings", "loop_end")
        return {"start": a, "end": b, "manual": True, "seam": None}
    if loop:
        lo_s, hi_s = (1.0, 3.0) if animation in ("idle", "crouch") else (0.45, 2.0)
        p_min = max(2, int(round(lo_s * fps)))
        skip = min(int(round(0.25 * fps)), max(0, total - p_min - 2))
        p_max = min(int(round(hi_s * fps)), total - skip - 2)
        # Several consecutive pairs: a single pair matches at the wrong period near pose extremes.
        pairs = 3
        p_max = min(p_max, total - skip - pairs)
        per_period = {}
        for p in range(p_min, p_max + 1):
            for a in range(skip, total - p - pairs + 1):
                score = sum(_pair_diff(sil[a + k], sil[a + p + k], low[a + k], low[a + p + k])
                            for k in range(pairs)) / pairs
                if p not in per_period or score < per_period[p][0]:
                    per_period[p] = (score, a)
        if not per_period:
            return {"start": 0, "end": total, "manual": False, "seam": None}
        # Two cycles match as well as one; take the shortest period that is nearly as good.
        best = min(v[0] for v in per_period.values())
        p = min(q for q, v in per_period.items() if v[0] <= best * 1.08 + 0.003)
        score, a = per_period[p]
        return {"start": a, "end": a + p, "manual": False, "seam": round(score, 4)}
    energy = np.array([_pair_diff(sil[i], sil[i + 1], low[i], low[i + 1]) for i in range(total - 1)])
    if energy.max(initial=0) <= 0:
        return {"start": 0, "end": total, "manual": False, "seam": None}
    active = np.nonzero(energy > 0.2 * energy.max())[0]
    a = max(0, int(active[0]) - 2)
    b = min(total, int(active[-1]) + 3)
    if b - a < 2:
        a, b = 0, total
    return {"start": a, "end": b, "manual": False, "seam": None}


def sample_indices(window: dict, count: int, loop: bool) -> list[int]:
    a, b = window["start"], window["end"]
    span = b - a
    if loop:
        picks = [a + int(math.floor(k * span / count)) for k in range(count)]
    else:
        picks = [int(round(v)) for v in np.linspace(a, b - 1, count)]
    out = []
    for p in picks:
        if not out or p != out[-1]:
            out.append(p)
    return out


# Layout.
def _baseline(fg: np.ndarray) -> int:
    rows = fg.sum(axis=1)
    x = np.nonzero(fg.any(axis=0))[0]
    width = (x[-1] - x[0] + 1) if len(x) else 1
    solid = np.nonzero(rows >= max(2, 0.01 * width))[0]
    if len(solid):
        return int(solid[-1])
    return int(np.nonzero(rows)[0][-1])


def _torso_x(fg: np.ndarray) -> float:
    ys = np.nonzero(fg.any(axis=1))[0]
    top, bottom = int(ys[0]), int(ys[-1])
    upper = fg[top: top + max(1, int(0.6 * (bottom - top + 1)))]
    cols = np.nonzero(upper)[1]
    return float(cols.mean()) if len(cols) else float(np.nonzero(fg)[1].mean())


def _bbox(fg: np.ndarray) -> tuple[int, int, int, int]:
    ys = np.nonzero(fg.any(axis=1))[0]
    xs = np.nonzero(fg.any(axis=0))[0]
    return int(xs[0]), int(ys[0]), int(xs[-1]), int(ys[-1])


def plan_layout(masks: list[np.ndarray], pivot_mode: str, cell: int) -> dict:
    """One transform for the whole animation: shared scale, optional per-frame feet/torso lock."""
    bases = [_baseline(m) for m in masks]
    centers = [_torso_x(m) for m in masks]
    if pivot_mode == "locked":
        ground = int(round(float(np.median(bases))))
        column = float(np.median(centers))
        shifts = [(int(round(column - c)), ground - b) for b, c in zip(bases, centers)]
    else:
        ground, column = bases[0], centers[0]
        shifts = [(0, 0)] * len(masks)
    boxes = [_bbox(m) for m in masks]
    x0 = min(b[0] + dx for b, (dx, _) in zip(boxes, shifts))
    y0 = min(b[1] + dy for b, (_, dy) in zip(boxes, shifts))
    x1 = max(b[2] + dx for b, (dx, _) in zip(boxes, shifts))
    y1 = max(b[3] + dy for b, (_, dy) in zip(boxes, shifts))
    margin = max(1, cell // 32)
    avail = cell - 2 * margin
    uw, uh = x1 - x0 + 1, y1 - y0 + 1
    scale = min(avail / uw, avail / uh)
    off_x = (cell - uw * scale) / 2.0
    off_y = cell - margin - uh * scale
    pivot_x = int(round((column - x0 + 0.5) * scale + off_x - 0.5))
    pivot_y = int(round((ground + 1 - y0) * scale + off_y))
    return {
        "scale": scale, "union": (x0, y0, x1, y1), "offset": (off_x, off_y), "shifts": shifts,
        "pivot": {"x": max(0, min(cell - 1, pivot_x)), "y": max(0, min(cell, pivot_y))},
        "margin": margin,
    }


def render_cell(fg: np.ndarray, colors: np.ndarray, layout: dict, shift: tuple[int, int],
                cell: int, alpha_threshold: float) -> np.ndarray:
    """Nearest-neighbour colour sample per cell pixel; opacity is hard (coverage >= threshold)."""
    h, w = fg.shape
    scale = layout["scale"]
    x0, y0 = layout["union"][:2]
    off_x, off_y = layout["offset"]
    dx, dy = shift
    centers = np.arange(cell) + 0.5
    sx = x0 + (centers - off_x) / scale - dx
    sy = y0 + (centers - off_y) / scale - dy
    xi = np.clip(np.floor(sx).astype(int), 0, w - 1)
    yi = np.clip(np.floor(sy).astype(int), 0, h - 1)
    inside_x = (sx >= 0) & (sx < w)
    inside_y = (sy >= 0) & (sy < h)
    half = 0.5 / scale
    if half >= 0.5:
        integral = np.zeros((h + 1, w + 1), np.int64)
        integral[1:, 1:] = np.cumsum(np.cumsum(fg, axis=0), axis=1)
        xl = np.clip(np.floor(sx - half).astype(int), 0, w)
        xh = np.clip(np.floor(sx + half).astype(int), 0, w)
        yl = np.clip(np.floor(sy - half).astype(int), 0, h)
        yh = np.clip(np.floor(sy + half).astype(int), 0, h)
        xh = np.maximum(xh, np.minimum(xl + 1, w))
        yh = np.maximum(yh, np.minimum(yl + 1, h))
        box = (integral[np.ix_(yh, xh)] - integral[np.ix_(yl, xh)]
               - integral[np.ix_(yh, xl)] + integral[np.ix_(yl, xl)])
        area = np.outer(np.maximum(yh - yl, 1), np.maximum(xh - xl, 1))
        cover = box / area
    else:
        cover = fg[np.ix_(yi, xi)].astype(np.float32)
    opaque = (cover >= alpha_threshold) & np.outer(inside_y, inside_x)
    out = np.zeros((cell, cell, 4), np.uint8)
    out[..., :3] = colors[np.ix_(yi, xi)]
    out[..., 3] = np.where(opaque, 255, 0)
    out[..., :3][~opaque] = 0
    return out


def shared_palette(cells: list[np.ndarray], colors: int) -> tuple[list[np.ndarray], list[str]]:
    """Quantize every frame with one palette built from the opaque pixels of all frames."""
    opaque = np.concatenate([c[..., :3][c[..., 3] > 0] for c in cells])
    if not len(opaque):
        return cells, []
    pal_img = Image.fromarray(opaque.reshape(1, -1, 3), "RGB").quantize(
        colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    out = []
    used: set[tuple[int, int, int]] = set()
    for c in cells:
        rgb = np.asarray(Image.fromarray(np.ascontiguousarray(c[..., :3]), "RGB")
                         .quantize(palette=pal_img, dither=Image.Dither.NONE).convert("RGB"))
        frame = c.copy()
        frame[..., :3] = np.where(c[..., 3:4] > 0, rgb, 0)
        used.update(map(tuple, frame[..., :3][frame[..., 3] > 0].reshape(-1, 3).tolist()))
        out.append(frame)
    return out, sorted("#%02x%02x%02x" % c for c in used)


def _cell_diff(a: np.ndarray, b: np.ndarray) -> float:
    oa, ob = a[..., 3] > 0, b[..., 3] > 0
    union = oa | ob
    if not union.any():
        return 0.0
    both = oa & ob
    shape = float((oa ^ ob).sum()) / float(union.sum())
    color = float(np.abs(a[..., :3][both].astype(np.int16) - b[..., :3][both].astype(np.int16)).mean()) / 255.0 if both.any() else 1.0
    return 0.7 * shape + 0.3 * color


def loop_seam(cells: list[np.ndarray]) -> dict:
    """How much the last-to-first step jumps compared with an ordinary frame step."""
    if len(cells) < 3:
        return {"ratio": None, "grade": "unknown"}
    steps = [_cell_diff(cells[i], cells[i + 1]) for i in range(len(cells) - 1)]
    seam = _cell_diff(cells[-1], cells[0])
    typical = float(np.median(steps)) or 1e-6
    ratio = round(seam / typical, 2) if typical > 1e-6 else (0.0 if seam < 1e-6 else 99.0)
    grade = "good" if ratio <= 1.5 else "fair" if ratio <= 2.5 else "poor"
    return {"ratio": ratio, "grade": grade, "seam": round(seam, 4), "typical": round(typical, 4)}


# Quality.
def check_quality(masks: dict[int, np.ndarray], picks: list[int], key_match: float,
                  layout: Optional[dict], frame_shape: tuple[int, int]) -> list[dict]:
    issues: list[dict] = []
    if key_match < 0.45:
        issues.append({"code": "noBackdrop", "level": "error", "value": round(key_match, 3)})
    ratios = [float(masks[i].mean()) for i in picks]
    if min(ratios) < 0.002:
        issues.append({"code": "emptyMask", "level": "error", "value": round(min(ratios), 4)})
    if max(ratios) > 0.85:
        issues.append({"code": "fullMask", "level": "error", "value": round(max(ratios), 4)})
    ring = _ring(frame_shape)
    touching = sum(1 for i in picks if float(masks[i][ring].mean()) > 0.01)
    if touching:
        issues.append({"code": "edgeTouch", "level": "warn", "value": touching})
    jumps = []
    for i in picks:
        for j in (i - 1, i + 1):
            if j in masks:
                a, b = masks[i], masks[j]
                union = float((a | b).sum())
                if union:
                    jumps.append(1.0 - float((a & b).sum()) / union)
    if jumps and max(jumps) > 0.35:
        issues.append({"code": "flicker", "level": "warn", "value": round(max(jumps), 3)})
    if layout and (layout["union"][3] - layout["union"][1] + 1) < 0.12 * frame_shape[0]:
        issues.append({"code": "tinyCharacter", "level": "warn"})
    return issues


def _status(issues: list[dict]) -> str:
    if any(i["level"] == "error" for i in issues):
        return "failed"
    return "warn" if issues else "ok"


# Export.
def sheet_layout(count: int, cell: int, columns: int = SHEET_COLUMNS) -> dict:
    cols = max(1, min(count, columns))
    rows = int(math.ceil(count / cols))
    rects = [{"x": (i % cols) * cell, "y": (i // cols) * cell, "w": cell, "h": cell} for i in range(count)]
    return {"columns": cols, "rows": rows, "width": cols * cell, "height": rows * cell, "rects": rects}


def _animation_entry(name: str, spec: dict, s: SpriteSettings, rects: list[dict], picks: list[int],
                     pivot: dict, files: list[str]) -> dict:
    duration = round(1000.0 / s.fps, 3)
    return {
        "name": name,
        "loop": bool(spec["loop"]),
        "fps": s.fps,
        "frame_duration_ms": duration,
        "pivot": dict(pivot),
        "pivot_mode": spec["pivot"],
        "facing": "right",
        "frames": [{"index": i, **rects[i], "duration_ms": duration, "file": files[i], "source_frame": int(picks[i])}
                   for i in range(len(rects))],
    }


README_TXT = """H3 Studio sprite export
=======================
<name>_sheet.png   transparent sprite sheet, frames left-to-right, top-to-bottom
frames/*.png       the same frames as separate transparent PNGs
<name>.json        layout and timing (format "h3-studio-sprite-sheet", version 1)

JSON fields
  image, image_size        sheet file and its pixel size
  cell                     size of one frame cell in pixels
  layout                   columns, rows, order ("row-major")
  animations[]             name, loop, fps, frame_duration_ms, pivot, pivot_mode, facing, frames[]
  frames[]                 index, x, y, w, h (pixel rectangle in the sheet), duration_ms, file, source_frame
  pivot                    ground contact point inside a cell, pixels from the cell's top-left corner;
                           y is the row directly under the feet
  pivot_mode               "locked": feet and torso pinned per frame (idle/walk/run);
                           "free": the clip's own motion is kept (a jump keeps its height)
  palette                  shared colour list when a palette limit was used, otherwise null
Frames face right; mirror them in the engine for left-facing movement.
"""


def write_export(out_dir: Path, name: str, cells: list[np.ndarray], entry: dict, layout: dict,
                 extra: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "frames").mkdir(exist_ok=True)
    cell = cells[0].shape[0]
    sheet = np.zeros((layout["height"], layout["width"], 4), np.uint8)
    for frame, rect, meta in zip(cells, layout["rects"], entry["frames"]):
        sheet[rect["y"]: rect["y"] + cell, rect["x"]: rect["x"] + cell] = frame
        Image.fromarray(frame, "RGBA").save(out_dir / meta["file"])
    sheet_name = f"{name}_sheet.png"
    Image.fromarray(sheet, "RGBA").save(out_dir / sheet_name)
    doc = {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "image": sheet_name,
        "image_size": {"w": layout["width"], "h": layout["height"]},
        "cell": {"w": cell, "h": cell},
        "layout": {"columns": layout["columns"], "rows": layout["rows"], "order": "row-major"},
        "animations": [entry],
        **extra,
    }
    json_name = f"{name}.json"
    (out_dir / json_name).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    zip_name = f"{name}_sprites.zip"
    with zipfile.ZipFile(out_dir / zip_name, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(out_dir / sheet_name, sheet_name)
        z.write(out_dir / json_name, json_name)
        for meta in entry["frames"]:
            z.write(out_dir / meta["file"], meta["file"])
        z.writestr("README.txt", README_TXT)
    return {"sheet": sheet_name, "json": json_name, "zip": zip_name,
            "frames": [m["file"] for m in entry["frames"]]}


def _checker(h: int, w: int, size: int = 8) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    on = ((yy // size) + (xx // size)) % 2 == 0
    out = np.empty((h, w, 3), np.uint8)
    out[on] = (205, 205, 205)
    out[~on] = (150, 150, 150)
    return out


def mask_preview(frames: list[np.ndarray], masks: list[np.ndarray], path: Path, height: int = 200) -> None:
    """Rows of source | removed area tinted magenta | cutout on a checkerboard."""
    rows = []
    for rgb, fg in zip(frames, masks):
        h, w = fg.shape
        pw = max(1, int(round(w * height / h)))
        src = np.asarray(Image.fromarray(rgb[..., :3]).resize((pw, height), Image.Resampling.BILINEAR))
        m = np.asarray(Image.fromarray(fg.astype(np.uint8) * 255).resize((pw, height), Image.Resampling.NEAREST)) > 0
        tint = src.copy()
        tint[~m] = (0.35 * src[~m] + 0.65 * np.array([255, 0, 255])).astype(np.uint8)
        cut = _checker(height, pw)
        cut[m] = src[m]
        rows.append(np.concatenate([src, tint, cut], axis=1))
    width = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, width - r.shape[1]), (0, 0))) for r in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.concatenate(rows, axis=0)).save(path)


# Pipeline.
def _analysis_step(size: tuple[int, int]) -> int:
    return max(1, int(round(min(size) / 192)))


def _masks_for(full: dict[int, np.ndarray], key: np.ndarray, s: SpriteSettings):
    dists = {i: key_distance(f, key) for i, f in full.items()}
    masks = {i: mask_frame(d, s) for i, d in dists.items()}
    return dists, masks


def _final_masks(picks, dists, masks, s):
    out = {}
    for i in picks:
        group = [j for j in (i - 1, i, i + 1) if j in masks]
        out[i] = stabilize([masks[j] for j in group], [dists[j] for j in group], group.index(i), s.tolerance)
    return out


def _prepare(source, animation: str, backdrop: str, s: SpriteSettings):
    _need_scipy()
    spec = ANIMATIONS.get(animation)
    if not spec:
        raise SpriteError("game.badAnimation", animation)
    step = _analysis_step(source.size)
    low = source.analysis(step)
    if len(low) < 2:
        raise SpriteError("game.noFrames")
    key, match = estimate_key(low, backdrop)
    thr = _threshold(s.tolerance)
    sil = [~_edge_background(key_distance(f, key) < thr) for f in low]
    window = choose_window(sil, low, source.fps, spec["loop"], animation, s)
    picks = sample_indices(window, s.frames, spec["loop"])
    return spec, key, match, window, picks, len(low)


def preview(source, animation: str, backdrop: str, settings: SpriteSettings, path: Path) -> dict:
    """Mask preview for three frames of the chosen window, without writing an export."""
    spec, key, match, window, picks, total = _prepare(source, animation, backdrop, settings)
    chosen = sorted({picks[0], picks[len(picks) // 2], picks[-1]})
    full = source.read({j for i in chosen for j in (i - 1, i, i + 1) if 0 <= j < total})
    dists, masks = _masks_for(full, key, settings)
    final = _final_masks(chosen, dists, masks, settings)
    mask_preview([full[i] for i in chosen], [final[i] for i in chosen], path)
    issues = check_quality({**masks, **final}, chosen, match, None, next(iter(full.values())).shape[:2])
    return {"status": _status(issues), "issues": issues, "frames": chosen,
            "coverage": [round(float(final[i].mean()), 4) for i in chosen],
            "key_rgb": [int(round(v)) for v in key]}


def process(source, animation: str, backdrop: str, settings: SpriteSettings, out_dir: Path,
            source_meta: Optional[dict] = None) -> dict:
    """Mask, align and export one animation. A failed quality check writes only the mask preview."""
    spec, key, match, window, picks, total = _prepare(source, animation, backdrop, settings)
    full = source.read({j for i in picks for j in (i - 1, i, i + 1) if 0 <= j < total})
    if any(i not in full for i in picks):
        raise SpriteError("game.badVideo", "frames missing")
    dists, masks = _masks_for(full, key, settings)
    final = _final_masks(picks, dists, masks, settings)
    shape = full[picks[0]].shape[:2]
    out_dir.mkdir(parents=True, exist_ok=True)
    preview_picks = sorted({picks[0], picks[len(picks) // 2], picks[-1]})
    mask_preview([full[i] for i in preview_picks], [final[i] for i in preview_picks], out_dir / "mask_preview.png")
    issues = check_quality({**masks, **final}, picks, match, None, shape)
    base = {
        "animation": animation,
        "settings": settings.as_dict(),
        "key_rgb": [int(round(v)) for v in key],
        "backdrop": backdrop,
        "window": {"start": window["start"], "end": window["end"], "manual": window["manual"],
                   "start_s": round(window["start"] / source.fps, 3), "end_s": round(window["end"] / source.fps, 3)},
        "source_frames": picks,
        "source_fps": source.fps,
        "natural_fps": round(len(picks) * source.fps / max(1, window["end"] - window["start"]), 2),
        "loop": bool(spec["loop"]),
        "files": {"mask_preview": "mask_preview.png"},
    }
    if _status(issues) == "failed":
        return {**base, "ok": False, "status": "failed", "issues": issues}
    layout = plan_layout([final[i] for i in picks], spec["pivot"], settings.cell)
    issues = check_quality({**masks, **final}, picks, match, layout, shape)
    threshold = DETAILS[settings.detail]
    cells = []
    for i, shift in zip(picks, layout["shifts"]):
        colors = clean_colors(full[i], final[i], key, dists[i], settings)
        cells.append(render_cell(final[i], colors, layout, shift, settings.cell, threshold))
    if any(not (c[..., 3] > 0).any() for c in cells):
        issues.append({"code": "emptyFrame", "level": "error"})
        return {**base, "ok": False, "status": "failed", "issues": issues}
    palette = []
    if settings.palette:
        cells, palette = shared_palette(cells, settings.palette)
    seam = loop_seam(cells) if spec["loop"] else None
    if seam and seam["grade"] == "poor":
        issues.append({"code": "loopSeam", "level": "warn", "value": seam["ratio"]})
    sheet = sheet_layout(len(cells), settings.cell)
    files = [f"frames/{animation}_{i:03d}.png" for i in range(len(cells))]
    entry = _animation_entry(animation, spec, settings, sheet["rects"], picks, layout["pivot"], files)
    extra = {
        "palette": palette or None,
        "source": {**(source_meta or {}), "source_fps": source.fps,
                   "window_start_s": base["window"]["start_s"], "window_end_s": base["window"]["end_s"]},
        "settings": settings.as_dict(),
    }
    written = write_export(out_dir, animation, cells, entry, sheet, extra)
    return {
        **base, "ok": True, "status": _status(issues), "issues": issues,
        "frames": len(cells), "cell": settings.cell, "fps": settings.fps, "pivot": layout["pivot"],
        "seam": seam, "palette": palette or None,
        "files": {**base["files"], **written},
    }


def build_atlas(items: list[tuple[Path, dict]], out_dir: Path, name: str = "atlas") -> dict:
    """Combine processed animations (same cell size) into one sheet, one row per animation."""
    if not items:
        raise SpriteError("game.atlasEmpty")
    docs = []
    for folder, result in items:
        doc = json.loads((folder / result["files"]["json"]).read_text(encoding="utf-8"))
        docs.append((folder, doc))
    cells = {doc["cell"]["w"] for _, doc in docs}
    if len(cells) != 1:
        raise SpriteError("game.atlasCells")
    cell = cells.pop()
    columns = max(len(doc["animations"][0]["frames"]) for _, doc in docs)
    width, height = columns * cell, len(docs) * cell
    sheet = np.zeros((height, width, 4), np.uint8)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "frames").mkdir(exist_ok=True)
    animations = []
    for row, (folder, doc) in enumerate(docs):
        anim = dict(doc["animations"][0])
        frames = []
        for col, meta in enumerate(anim["frames"]):
            frame = np.asarray(Image.open(folder / meta["file"]).convert("RGBA"))
            x, y = col * cell, row * cell
            sheet[y: y + cell, x: x + cell] = frame
            Image.fromarray(frame, "RGBA").save(out_dir / meta["file"])
            frames.append({**meta, "x": x, "y": y, "w": cell, "h": cell})
        anim["frames"] = frames
        animations.append(anim)
    sheet_name, json_name, zip_name = f"{name}_sheet.png", f"{name}.json", f"{name}_sprites.zip"
    Image.fromarray(sheet, "RGBA").save(out_dir / sheet_name)
    doc = {
        "format": FORMAT, "version": FORMAT_VERSION, "image": sheet_name,
        "image_size": {"w": width, "h": height}, "cell": {"w": cell, "h": cell},
        "layout": {"columns": columns, "rows": len(docs), "order": "row-per-animation"},
        "animations": animations,
        "palette": None,
    }
    (out_dir / json_name).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    with zipfile.ZipFile(out_dir / zip_name, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(out_dir / sheet_name, sheet_name)
        z.write(out_dir / json_name, json_name)
        for anim in animations:
            for meta in anim["frames"]:
                z.write(out_dir / meta["file"], meta["file"])
        z.writestr("README.txt", README_TXT)
    return {"sheet": sheet_name, "json": json_name, "zip": zip_name, "animations": [a["name"] for a in animations]}
