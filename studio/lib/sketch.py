"""Hand drawing → finished still for Qwen-Image img2img.

Qwen-Image 2512 cannot read a picture; img2img only starts from it. One pass either keeps
flat shapes (low denoise) or re-composes the scene from the seed (≥0.78: objects move, get
duplicated). So closed shapes are painted with their outline colour, a low-denoise layout
pass renders them where they were drawn, and a refine pass turns that coherent picture into
a finished one. Freeing only the paper (Differential Diffusion) was tried: the model then
invents its own subject in the background.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps
from scipy import ndimage

# Layout-pass denoise, measured with seed-matched runs: 0.65 keeps every object in place,
# 0.70 already starts turning shapes into other things.
FIDELITY = {"faithful": 0.60, "balanced": 0.65, "free": 0.70}
# Refine-pass denoise: removes leftover strokes and flat fills; 0.70 starts redrawing objects.
REFINE = 0.60
NEGATIVE = ("sketch, line drawing, pencil lines, doodle, stick figure, white background, blank background, "
            "picture frame, border, panels, collage, text, logo, brand name, watermark")


def denoise(fidelity: str) -> float:
    return FIDELITY.get(str(fidelity or "").strip().lower(), FIDELITY["balanced"])


def frame_prompt(text: str, style_line: str = "") -> str:
    subject = " ".join(str(text or "").split()).rstrip(" .") or "the scene"
    style = style_line.strip().rstrip(".")
    parts = [f"{style}." if style else "", f"{subject}.",
             "A finished, fully rendered image with a complete, detailed background filling the whole frame."]
    return " ".join(p for p in parts if p)


def _fill_enclosed(out: np.ndarray, pixels: np.ndarray, stroke: np.ndarray) -> None:
    """Paint closed shapes in ``out`` with their outline colour."""
    regions, count = ndimage.label(~stroke)
    if count < 2:
        return
    border = np.unique(np.concatenate([regions[0], regions[-1], regions[:, 0], regions[:, -1]]))
    sizes = ndimage.sum_labels(np.ones_like(regions), regions, index=np.arange(count + 1))
    # A shape covering most of the canvas is a frame or a background, not an object.
    keep = sizes <= stroke.size * 0.35
    keep[border] = False
    keep[0] = False
    # Anti-aliased stroke edges are pale; only solid ink decides a shape's colour.
    solid = (pixels.min(axis=2) < 128) | (np.ptp(pixels, axis=2) > 100)
    boxes = ndimage.find_objects(regions)
    h, w = stroke.shape
    for label in np.flatnonzero(keep):
        rs, cs = boxes[label - 1]
        box = (slice(max(rs.start - 6, 0), min(rs.stop + 6, h)), slice(max(cs.start - 6, 0), min(cs.stop + 6, w)))
        inside = regions[box] == label
        ring = ndimage.binary_dilation(inside, iterations=6) & ~inside & solid[box]
        if not ring.any():
            continue
        colour = np.median(pixels[box][ring], axis=0)
        patch = out[box]
        patch[inside] = colour * 0.75 + patch[inside] * 0.25


def prepare(source: Path, dest: Path, width: int, height: int, seed: int = 0) -> Path:
    """Fit the drawing on a width×height canvas, swap the paper for a soft gradient, fill closed shapes."""
    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            paper = Image.new("RGBA", im.size, "white")
            im = Image.alpha_composite(paper, im)
        im = im.convert("RGB")
        # A thin pad strip (1280×720 board vs 1664×928) comes back as a dark border; crop instead.
        if abs(im.width / im.height - width / height) < 0.04 * width / height:
            im = ImageOps.fit(im, (width, height), Image.LANCZOS)
        else:
            im = ImageOps.pad(im, (width, height), Image.LANCZOS, color="white")
    pixels = np.asarray(im).astype(np.float32)
    darkest = pixels.min(axis=2)
    # Any dark or saturated stroke counts as ink; pale paper does not.
    ink = Image.fromarray((255 - darkest).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))
    ink = np.asarray(ink).astype(np.float32)[..., None] / 255.0
    rng = np.random.default_rng(seed)
    # A quiet gradient, lighter towards the top: any pattern here survives the layout pass
    # (confetti noise became a wall of flowers, soft blobs a leaf wallpaper).
    coarse = rng.normal(0, 1, (height // 48 + 2, width // 48 + 2, 3)) * 10
    noise = Image.fromarray((coarse + 135).clip(0, 255).astype(np.uint8)).resize((width, height), Image.BICUBIC)
    noise = np.asarray(noise).astype(np.float32) + np.linspace(30, -30, height, dtype=np.float32)[:, None, None]
    # The thickened halo around a stroke takes the stroke colour, or near-black for paper pixels.
    ink_rgb = np.where(darkest[..., None] < 200, pixels, 20.0)
    out = noise * (1 - ink) + ink_rgb * ink
    _fill_enclosed(out, pixels, ink[..., 0] > 0.5)
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(dest)
    return dest
