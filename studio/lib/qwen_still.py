"""Native Qwen-Image still workflow for H3 Studio's own ComfyUI."""
from __future__ import annotations

from pathlib import Path

MODELS = {
    "diffusion_models": "qwen_image_2512_fp8_e4m3fn.safetensors",
    "text_encoders": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
    "vae": "qwen_image_vae.safetensors",
}
EDIT_MODEL = "qwen_image_edit_2511_fp8mixed.safetensors"
LABEL = "Qwen"
SIZES = {"16:9": (1664, 928), "9:16": (928, 1664), "1:1": (1328, 1328),
         "4:3": (1472, 1104), "3:4": (1104, 1472)}


def closest_aspect(aspect: str) -> str:
    if aspect in SIZES:
        return aspect
    try:
        a, b = (float(x) for x in str(aspect).split(":", 1))
        ratio = a / b
    except (ValueError, ZeroDivisionError):
        return "16:9"
    return min(SIZES, key=lambda k: abs(SIZES[k][0] / SIZES[k][1] - ratio))


def missing_models(comfy_root: Path, *, edit=False, available_models=()) -> list[str]:
    models = {**MODELS, **({"diffusion_models": EDIT_MODEL} if edit else {})}
    return [f"{folder}/{name}" for folder, name in models.items()
            if not (comfy_root / "models" / folder / name).is_file()
            and not (folder == "diffusion_models" and name in available_models)]


def reference_view_plan(kind):
    """The views of a reference sheet and what each must preserve from the source image."""
    views = (["front full-body view", "left profile full-body view", "right profile full-body view", "rear full-body view", "front face portrait"]
             if kind in ("character", "creature") else
             ["front view", "rear view", "right side view", "left side view"] if kind == "vehicle" else
             ["wide establishing view", "left viewpoint", "right viewpoint", "reverse viewpoint"])
    identity = {"character": "identity, face, hair, body proportions, clothing and accessories",
                "creature": "anatomy, markings, colors and proportions",
                "vehicle": "geometry, paint, wheels, proportions and mechanical details",
                "location": "architecture, materials, objects and spatial layout"}[kind]
    return views, identity


def build_reference_views(*, kind, notes, style_line, source_image, steps, seed, width, height):
    """Generate independent images conditioned on the original, never crop panels."""
    views, identity = reference_view_plan(kind)
    graph = build_graph(prompt="", negative="", aspect="16:9", steps=steps, seed=seed)
    graph["10"]["inputs"]["unet_name"] = EDIT_MODEL
    for key in ("30", "31", "40", "50", "60", "70"):
        graph.pop(key)
    graph["25"] = {"class_type": "LoadImage", "inputs": {"image": source_image}}
    graph["31"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {
        "clip": ["20", 0], "prompt": "", "vae": ["21", 0], "image1": ["25", 0]}}
    for index, view in enumerate(views):
        prefix = f"view_{index}"
        text = (f"Generate one new image showing the subject in the input image: {view}. "
                f"Preserve the exact {identity} from the input image. "
                "Change the camera viewpoint and framing as requested. Keep the entire subject visible in full-body views. "
                "A single coherent image, no collage, no panels, no text. " + style_line + " Details: " + notes)
        graph[prefix + "_text"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {
            "clip": ["20", 0], "prompt": text, "vae": ["21", 0], "image1": ["25", 0]}}
        graph[prefix + "_latent"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        graph[prefix + "_sample"] = {"class_type": "KSampler", "inputs": {
            "model": ["12", 0], "positive": [prefix + "_text", 0], "negative": ["31", 0],
            "latent_image": [prefix + "_latent", 0], "seed": (seed + index) % (2**32), "steps": steps,
            "cfg": 4.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}}
        graph[prefix + "_decode"] = {"class_type": "VAEDecode", "inputs": {"samples": [prefix + "_sample", 0], "vae": ["21", 0]}}
        graph[f"70_{index}"] = {"class_type": "SaveImage", "inputs": {
            "images": [prefix + "_decode", 0], "filename_prefix": f"H3_Studio_Qwen_Edit/{view.replace(' ', '_')}"}}
    return graph


def build_storyboard_frame(*, prompt: str, negative: str, ref_images: list[str], aspect: str,
                           steps: int, seed: int) -> dict:
    """One film frame. With refs, Qwen Edit sees them as Picture 1..3; without, plain text-to-image."""
    refs = [r for r in ref_images if r][:3]
    aspect = closest_aspect(aspect)
    graph = build_graph(prompt=prompt, negative=negative, aspect=aspect, steps=steps, seed=seed,
                        prefix="H3_Studio_Frame")
    if not refs:
        return graph
    graph["10"]["inputs"]["unet_name"] = EDIT_MODEL
    images = {}
    for index, name in enumerate(refs, start=1):
        graph[f"25_{index}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
        images[f"image{index}"] = [f"25_{index}", 0]
    graph["30"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {
        "clip": ["20", 0], "prompt": prompt, "vae": ["21", 0], **images}}
    graph["31"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {
        "clip": ["20", 0], "prompt": negative, "vae": ["21", 0]}}
    return graph


def build_sketch_edit(*, prompt: str, negative: str, reference: str, aspect: str, steps: int, seed: int,
                      prefix: str = "H3_Studio_Sketch") -> dict:
    """Drawing as Picture 1 of Qwen-Image-Edit; a fresh latent, so the strokes never show through."""
    aspect = closest_aspect(aspect)
    graph = build_graph(prompt=prompt, negative=negative, aspect=aspect, steps=steps, seed=seed, prefix=prefix)
    graph["10"]["inputs"]["unet_name"] = EDIT_MODEL
    graph["25"] = {"class_type": "LoadImage", "inputs": {"image": reference}}
    graph["30"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {
        "clip": ["20", 0], "prompt": prompt, "vae": ["21", 0], "image1": ["25", 0]}}
    graph["31"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {
        "clip": ["20", 0], "prompt": negative, "vae": ["21", 0]}}
    return graph


def build_graph(*, prompt: str, negative: str, aspect: str, steps: int, seed: int,
                source_image: str = "", prefix: str = "H3_Studio_Qwen") -> dict:
    width, height = SIZES.get(aspect, SIZES["16:9"])
    graph = {
        "10": {"class_type": "UNETLoader", "inputs": {"unet_name": MODELS["diffusion_models"], "weight_dtype": "default"}},
        "12": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["10", 0], "shift": 3.1}},
        "20": {"class_type": "CLIPLoader", "inputs": {"clip_name": MODELS["text_encoders"], "type": "qwen_image", "device": "default"}},
        "21": {"class_type": "VAELoader", "inputs": {"vae_name": MODELS["vae"]}},
        "30": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["20", 0], "text": prompt}},
        "31": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["20", 0], "text": negative}} if negative else
              {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["30", 0]}},
        "40": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "50": {"class_type": "KSampler", "inputs": {"model": ["12", 0], "positive": ["30", 0], "negative": ["31", 0],
                 "latent_image": ["40", 0], "seed": seed, "steps": steps, "cfg": 4.0,
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
