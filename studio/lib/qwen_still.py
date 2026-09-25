"""Native Qwen-Image still workflow for H3 Studio's own ComfyUI."""
from __future__ import annotations

from pathlib import Path

MODELS = {
    "diffusion_models": "qwen_image_2512_fp8_e4m3fn.safetensors",
    "text_encoders": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
    "vae": "qwen_image_vae.safetensors",
}
SIZES = {"16:9": (1664, 928), "9:16": (928, 1664), "1:1": (1328, 1328),
         "4:3": (1472, 1104), "3:4": (1104, 1472)}


def missing_models(comfy_root: Path) -> list[str]:
    return [f"{folder}/{name}" for folder, name in MODELS.items()
            if not (comfy_root / "models" / folder / name).is_file()]


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
