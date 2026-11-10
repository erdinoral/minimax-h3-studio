"""MiniMax-H3-Image still workflow; same builders and node ids as qwen_still so the server can swap them."""
from __future__ import annotations

import math
from pathlib import Path

from lib.qwen_still import closest_aspect, reference_view_plan

UNET = "minimax_h3_image_pruned_int8_convrot.safetensors"
VAE = "minimax_h3_image_vae_fp16.safetensors"
# The video text encoder; either published build conditions H3-Image.
TEXT_ENCODERS = ("qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                 "qwen3vl_32b_minimax_h3_int8_convrot.safetensors")
MODELS = {"diffusion_models": UNET, "text_encoders": TEXT_ENCODERS[0], "vae": VAE}
# One model draws and edits; there is no separate edit checkpoint.
EDIT_MODEL = UNET
LABEL = "H3-Image"
# The release is distilled: 6 steps at cfg 1, so negative prompts have no effect.
STEPS = 6
CANVAS_MULTIPLE = 32
# The model is tuned for about 2048x2048 of area and degrades at low resolution.
TARGET_AREA = 2048 * 2048
SIZES = {"16:9": (2560, 1440), "9:16": (1440, 2560), "1:1": (2048, 2048),
         "4:3": (2304, 1728), "3:4": (1728, 2304)}


def text_encoder(comfy_root: Path) -> str:
    folder = comfy_root / "models" / "text_encoders"
    return next((name for name in TEXT_ENCODERS if (folder / name).is_file()), TEXT_ENCODERS[0])


def missing_models(comfy_root: Path, *, edit=False, available_models=()) -> list[str]:
    models = comfy_root / "models"
    missing = [f"{folder}/{name}" for folder, name in (("diffusion_models", UNET), ("vae", VAE))
               if not (models / folder / name).is_file()
               and not (folder == "diffusion_models" and name in available_models)]
    if not any((models / "text_encoders" / name).is_file() for name in TEXT_ENCODERS):
        missing.append("text_encoders/" + TEXT_ENCODERS[0])
    return missing


def canvas(width: int, height: int) -> tuple[int, int]:
    """Scale a requested size to the model's working area, keeping its aspect."""
    scale = math.sqrt(TARGET_AREA / max(1, width * height))
    snap = lambda v: max(CANVAS_MULTIPLE, int(round(v * scale / CANVAS_MULTIPLE)) * CANVAS_MULTIPLE)
    return snap(width), snap(height)


def _conditioning(prompt: str, width: int, height: int, images: list[str] = ()) -> dict:
    inputs = {"clip": ["20", 0], "vae": ["21", 0], "prompt": prompt, "width": width, "height": height}
    inputs.update({f"images.image_{i}": [node, 0] for i, node in enumerate(images, start=1)})
    return {"class_type": "MiniMaxH3ImageConditioning", "inputs": inputs}


def build_graph(*, prompt: str, negative: str = "", aspect: str, steps: int = STEPS, seed: int,
                source_image: str = "", prefix: str = "H3_Studio_H3Image", clip_name: str = TEXT_ENCODERS[0]) -> dict:
    width, height = SIZES.get(closest_aspect(aspect), SIZES["16:9"])
    graph = {
        "10": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "20": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip_name, "type": "minimax", "device": "default"}},
        "21": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "30": _conditioning(prompt, width, height),
        "31": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["30", 0]}},
        "50": {"class_type": "KSampler", "inputs": {"model": ["10", 0], "positive": ["30", 0], "negative": ["31", 0],
                 "latent_image": ["30", 1], "seed": seed, "steps": STEPS, "cfg": 1.0,
                 "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "60": {"class_type": "VAEDecode", "inputs": {"samples": ["50", 0], "vae": ["21", 0]}},
        "70": {"class_type": "SaveImage", "inputs": {"images": ["60", 0], "filename_prefix": prefix}},
    }
    if source_image:
        graph["25"] = {"class_type": "LoadImage", "inputs": {"image": source_image}}
        graph["26"] = {"class_type": "ImageScale", "inputs": {"image": ["25", 0], "upscale_method": "lanczos",
                                                        "width": width, "height": height, "crop": "center"}}
        graph["40"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["26", 0], "vae": ["21", 0]}}
        graph["50"]["inputs"].update({"latent_image": ["40", 0], "denoise": 0.55})
    return graph


def build_storyboard_frame(*, prompt: str, negative: str = "", ref_images: list[str], aspect: str,
                           steps: int = STEPS, seed: int, clip_name: str = TEXT_ENCODERS[0]) -> dict:
    """One film frame; refs are Picture 1..3 of the same model."""
    graph = build_graph(prompt=prompt, aspect=aspect, seed=seed, prefix="H3_Studio_Frame", clip_name=clip_name)
    refs = [r for r in ref_images if r][:3]
    for index, name in enumerate(refs, start=1):
        graph[f"25_{index}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
    width, height = graph["30"]["inputs"]["width"], graph["30"]["inputs"]["height"]
    graph["30"] = _conditioning(prompt, width, height, [f"25_{i}" for i in range(1, len(refs) + 1)])
    return graph


def build_sketch_edit(*, prompt: str, negative: str = "", reference: str, aspect: str, steps: int = STEPS,
                      seed: int, prefix: str = "H3_Studio_Sketch", clip_name: str = TEXT_ENCODERS[0]) -> dict:
    """Drawing as Picture 1 on a fresh latent, so the strokes never show through."""
    graph = build_graph(prompt=prompt, aspect=aspect, seed=seed, prefix=prefix, clip_name=clip_name)
    graph["25"] = {"class_type": "LoadImage", "inputs": {"image": reference}}
    width, height = graph["30"]["inputs"]["width"], graph["30"]["inputs"]["height"]
    graph["30"] = _conditioning(prompt, width, height, ["25"])
    return graph


def build_reference_views(*, kind, notes, style_line, source_image, steps=STEPS, seed, width, height,
                          clip_name: str = TEXT_ENCODERS[0]) -> dict:
    """One independent image per view, each conditioned on the original; panels are never cropped."""
    views, identity = reference_view_plan(kind)
    width, height = canvas(width, height)
    graph = build_graph(prompt="", aspect="16:9", seed=seed, clip_name=clip_name)
    for key in ("30", "31", "50", "60", "70"):
        graph.pop(key)
    graph["25"] = {"class_type": "LoadImage", "inputs": {"image": source_image}}
    for index, view in enumerate(views):
        prefix = f"view_{index}"
        text = (f"Generate one new image showing the subject in <Picture 1>: {view}. "
                f"Preserve the exact {identity} from <Picture 1>. "
                "Change the camera viewpoint and framing as requested. Keep the entire subject visible in full-body views. "
                "A single coherent image, no collage, no panels, no text. " + style_line + " Details: " + notes)
        graph[prefix + "_text"] = _conditioning(text, width, height, ["25"])
        graph[prefix + "_zero"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": [prefix + "_text", 0]}}
        graph[prefix + "_sample"] = {"class_type": "KSampler", "inputs": {
            "model": ["10", 0], "positive": [prefix + "_text", 0], "negative": [prefix + "_zero", 0],
            "latent_image": [prefix + "_text", 1], "seed": (seed + index) % (2**32), "steps": STEPS,
            "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}}
        graph[prefix + "_decode"] = {"class_type": "VAEDecode", "inputs": {"samples": [prefix + "_sample", 0], "vae": ["21", 0]}}
        graph[f"70_{index}"] = {"class_type": "SaveImage", "inputs": {
            "images": [prefix + "_decode", 0], "filename_prefix": f"H3_Studio_H3Image_Edit/{view.replace(' ', '_')}"}}
    return graph
