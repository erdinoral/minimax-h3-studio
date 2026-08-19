"""Thin ComfyUI HTTP client."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import httpx

DEFAULT_MODELS = {
    "unet": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "clip": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "vae": "minimax_h3_video_vae_fp16.safetensors",
    "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
}

REF2VA_MODELS = {
    **DEFAULT_MODELS,
    "unet": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
}


def enhance_ref_prompt(
    text: str,
    *,
    n_images: int,
    role: str = "general",
    n_face: int = 0,
) -> str:
    """Ensure <Picture N> tags exist; for face mode add identity-lock preamble."""
    prompt = (text or "").strip()
    if n_images <= 0:
        return prompt
    has_tags = any(f"<Picture {i}>" in prompt for i in range(1, n_images + 1))
    if role == "face_continue":
        # Pictures 1..n_face = identity; last picture = previous last frame
        nf = max(1, min(int(n_face or max(1, n_images - 1)), n_images))
        face_pics = ", ".join(f"<Picture {i}>" for i in range(1, nf + 1))
        frame_pic = f"<Picture {n_images}>" if n_images > nf else None
        lock = (
            f"{face_pics} {'is' if nf == 1 else 'are'} the face / identity reference "
            f"for the main character. Lock this person's face, age, hair, eyes and skin "
            f"exactly — do not change who they are."
        )
        if frame_pic:
            lock += (
                f" {frame_pic} is the last frame of the previous shot: continue the action "
                f"and camera from that exact composition while keeping the face locked to "
                f"{face_pics}."
            )
        if "identity" not in prompt.lower() or frame_pic and frame_pic not in prompt:
            prompt = f"{lock}\n\n{prompt}".strip()
    elif role == "face":
        pics = ", ".join(f"<Picture {i}>" for i in range(1, n_images + 1))
        lock = (
            f"{pics} {'is' if n_images == 1 else 'are'} the face / identity reference "
            f"for the main character. Lock this person's face, age, hair, eyes and skin "
            f"across the whole clip. Preserve identity — do not change who they are."
        )
        if not has_tags or "identity" not in prompt.lower():
            prompt = f"{lock}\n\n{prompt}".strip()
    elif not has_tags:
        tags = " ".join(f"<Picture {i}>" for i in range(1, n_images + 1))
        prompt = (
            f"Use {tags} as visual reference(s) for style / subject / scene as described below.\n\n"
            f"{prompt}"
        ).strip()
    return prompt


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        u = (base_url or "").strip() or "http://127.0.0.1:8188"
        if not u.startswith(("http://", "https://")):
            u = "http://" + u.lstrip("/")
        self.base_url = u.rstrip("/")
        self.client_id = str(uuid.uuid4())

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(f"{self.base_url}/system_stats")
                return r.status_code == 200
        except Exception:
            return False

    async def system_stats(self) -> dict:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{self.base_url}/system_stats")
            r.raise_for_status()
            return r.json()

    async def queue_prompt(self, prompt: dict) -> str:
        payload = {"prompt": prompt, "client_id": self.client_id}
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=60.0) as c:
                    r = await c.post(f"{self.base_url}/prompt", json=payload)
                    if r.status_code >= 400:
                        raise RuntimeError(r.text)
                    data = r.json()
                    if "error" in data:
                        raise RuntimeError(json.dumps(data["error"]))
                    return data["prompt_id"]
            except Exception as e:
                last_err = e
                await asyncio.sleep(1.2 * (attempt + 1))
        raise RuntimeError(f"Comfy queue başarısız: {last_err}")

    async def history(self, prompt_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(f"{self.base_url}/history/{prompt_id}")
            r.raise_for_status()
            return r.json()

    async def queue_status(self) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self.base_url}/queue")
            r.raise_for_status()
            return r.json()

    def ws_url(self) -> str:
        base = self.base_url
        if base.startswith("https://"):
            return "wss://" + base[len("https://") :] + f"/ws?clientId={self.client_id}"
        if base.startswith("http://"):
            return "ws://" + base[len("http://") :] + f"/ws?clientId={self.client_id}"
        return f"ws://{base}/ws?clientId={self.client_id}"

    async def watch_prompt(
        self,
        prompt_id: str,
        on_progress: Callable[[int, str], Awaitable[None] | None],
        *,
        stop_event: asyncio.Event,
    ) -> None:
        """Listen Comfy WS for sampler progress until stop_event is set."""
        try:
            import websockets
        except ImportError:
            return

        async def _emit(pct: int, label: str, meta: Optional[dict] = None):
            try:
                res = on_progress(pct, label, meta)
            except TypeError:
                res = on_progress(pct, label)
            if asyncio.iscoroutine(res):
                await res

        try:
            async with websockets.connect(self.ws_url(), max_size=8 * 1024 * 1024) as ws:
                while not stop_event.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        return
                    if isinstance(raw, bytes):
                        continue
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    mtype = msg.get("type")
                    data = msg.get("data") or {}
                    pid = data.get("prompt_id")
                    if pid and pid != prompt_id:
                        continue
                    if mtype == "progress":
                        value = float(data.get("value") or 0)
                        maxv = float(data.get("max") or 1) or 1.0
                        # True Comfy sampler % (same as ComfyUI progress bar)
                        pct = int(round(100.0 * value / maxv))
                        await _emit(
                            max(0, min(99, pct)),
                            f"örnekleme {int(value)}/{int(maxv)}",
                            meta={
                                "comfy_step": int(value),
                                "comfy_step_max": int(maxv),
                                "source": "ws",
                            },
                        )
                    elif mtype == "executing":
                        node = data.get("node")
                        if node is None and (not pid or pid == prompt_id):
                            await _emit(99, "tamamlanıyor", meta={"source": "ws"})
                        # ignore mid-graph node ticks — they used to look like stalls
                    elif mtype in ("execution_success", "executed"):
                        if not pid or pid == prompt_id:
                            await _emit(99, "çıktı hazırlanıyor", meta={"source": "ws"})
                    elif mtype == "execution_error":
                        await _emit(99, "comfy hata", meta={"source": "ws"})
                        return
        except asyncio.CancelledError:
            return
        except Exception:
            return

    @staticmethod
    def extract_video_meta(outputs: dict) -> Optional[dict]:
        """Find first video-like file in Comfy history outputs."""
        if not outputs:
            return None
        # Prefer explicit video containers
        for node_out in outputs.values():
            if not isinstance(node_out, dict):
                continue
            for key in ("gifs", "videos", "images"):
                for item in node_out.get(key) or []:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("filename") or "")
                    low = name.lower()
                    if key in ("gifs", "videos") or low.endswith(
                        (".mp4", ".webm", ".mkv", ".mov", ".gif", ".webp")
                    ):
                        return item
        # Fallback: any file-like output
        for node_out in outputs.values():
            if not isinstance(node_out, dict):
                continue
            for key in ("gifs", "videos", "images"):
                items = node_out.get(key) or []
                if items and isinstance(items[0], dict) and items[0].get("filename"):
                    return items[0]
        return None

    @staticmethod
    def format_execution_error(messages: Any) -> str:
        """Turn Comfy status.messages into a short human error."""
        text = json.dumps(messages, ensure_ascii=False) if not isinstance(messages, str) else messages
        # Prefer exception_message fields
        try:
            if isinstance(messages, list):
                for m in messages:
                    if isinstance(m, (list, tuple)) and len(m) >= 2 and isinstance(m[1], dict):
                        em = m[1].get("exception_message") or m[1].get("message")
                        et = m[1].get("exception_type") or ""
                        if em:
                            # Drop huge tensor dumps
                            em = str(em)
                            if "tensor(" in em.lower() or len(em) > 280:
                                if "out of memory" in em.lower() or "oom" in em.lower():
                                    return "VRAM yetersiz (CUDA OOM) — kaliteyi düşür veya Comfy'yi boşalt"
                                if "shape" in em.lower():
                                    return f"{et}: tensor/shape uyumsuzluğu (first_frame boyutu?)".strip(": ")
                                return (f"{et}: Comfy node hatası (ayrıntı kısaltıldı)".strip(": ")
                                        or "Comfy node hatası")
                            return f"{et}: {em}".strip(": ")
        except Exception:
            pass
        compact = text.replace("\\n", " ")
        if "out of memory" in compact.lower():
            return "VRAM yetersiz (CUDA OOM)"
        return (compact[-400:] if len(compact) > 400 else compact) or "Comfy execution error"

    async def interrupt(self) -> None:
        async with httpx.AsyncClient(timeout=10.0) as c:
            await c.post(f"{self.base_url}/interrupt")

    async def free_memory(self, *, unload_models: bool = True) -> bool:
        """Unload H3 weights and empty CUDA cache (ComfyUI POST /free)."""
        payload = {"unload_models": unload_models, "free_memory": True}
        try:
            async with httpx.AsyncClient(timeout=60.0) as c:
                r = await c.post(f"{self.base_url}/free", json=payload)
                return r.status_code < 400
        except Exception:
            return False

    async def upload_image(self, path: Path, name: Optional[str] = None) -> str:
        filename = name or path.name
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=120.0) as c:
                    with path.open("rb") as f:
                        r = await c.post(
                            f"{self.base_url}/upload/image",
                            files={"image": (filename, f, "image/png")},
                            data={"overwrite": "true"},
                        )
                    r.raise_for_status()
                    data = r.json()
                    return data.get("name") or filename
            except Exception as e:
                last_err = e
                await asyncio.sleep(1.2 * (attempt + 1))
        raise RuntimeError(f"Comfy upload başarısız: {last_err}")

    async def upload_video(self, path: Path, name: Optional[str] = None) -> str:
        """Upload a video into Comfy input/ (same endpoint as images; LoadVideo reads it)."""
        filename = name or path.name
        mime = "video/mp4"
        low = filename.lower()
        if low.endswith(".webm"):
            mime = "video/webm"
        elif low.endswith(".mov"):
            mime = "video/quicktime"
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=300.0) as c:
                    with path.open("rb") as f:
                        r = await c.post(
                            f"{self.base_url}/upload/image",
                            files={"image": (filename, f, mime)},
                            data={"overwrite": "true"},
                        )
                    r.raise_for_status()
                    data = r.json()
                    return data.get("name") or filename
            except Exception as e:
                last_err = e
                await asyncio.sleep(1.2 * (attempt + 1))
        raise RuntimeError(f"Comfy video upload başarısız: {last_err}")

    async def download_view(
        self, filename: str, subfolder: str = "", type_: str = "output", dest: Path = None
    ) -> Path:
        params = {"filename": filename, "subfolder": subfolder, "type": type_}
        async with httpx.AsyncClient(timeout=300.0) as c:
            r = await c.get(f"{self.base_url}/view", params=params)
            r.raise_for_status()
            dest = dest or Path(filename)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            return dest


def build_t2v_prompt(
    *,
    text: str,
    width: int = 1344,
    height: int = 768,
    length: int = 124,
    seed: int = 0,
    steps: int = 20,
    sampler: str = "res_multistep",
    scheduler: str = "simple",
    first_frame_name: Optional[str] = None,
    last_frame_name: Optional[str] = None,
    models: Optional[dict] = None,
    filename_prefix: str = "video/H3_Studio",
    silent_audio: bool = False,
    lora_name: Optional[str] = None,
    lora_strength: float = 0.75,
) -> dict[str, Any]:
    """Build FL2VA graph. silent_audio skips AudioVAE load + VAEDecodeAudio (faster end)."""
    m = {**DEFAULT_MODELS, **(models or {})}
    g: dict[str, Any] = {
        "6": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": m["unet"], "weight_dtype": "default"},
        },
        "13": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": m["clip"],
                "type": "minimax",
                "device": "default",
            },
        },
        "11": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": m["vae"]},
        },
        "104": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {
                "clip": ["13", 0],
                "vae": ["11", 0],
                "prompt": text,
                "width": width,
                "height": height,
                "length": length,
            },
        },
        "16": {
            "class_type": "BasicGuider",
            "inputs": {"model": ["6", 0], "conditioning": ["104", 0]},
        },
        "17": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": sampler},
        },
        "9": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["6", 0],
                "scheduler": scheduler,
                "steps": steps,
                "denoise": 1.0,
            },
        },
        "15": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed},
        },
        "14": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["15", 0],
                "guider": ["16", 0],
                "sampler": ["17", 0],
                "sigmas": ["9", 0],
                "latent_image": ["104", 1],
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["14", 0], "vae": ["11", 0]},
        },
        "92": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["91", 0],
                "filename_prefix": filename_prefix,
                "format": "auto",
                "codec": "auto",
            },
        },
    }
    if silent_audio:
        # Skip AudioVAE + VAEDecodeAudio — CreateVideo images-only (no SFX track).
        # Sampler still runs joint latent; decode/mux audio cost is what we cut.
        g["91"] = {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["10", 0],
                "fps": 24.0,
            },
        }
    else:
        g["24"] = {
            "class_type": "VAELoader",
            "inputs": {"vae_name": m["audio_vae"]},
        }
        g["23"] = {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": ["14", 0], "vae": ["24", 0]},
        }
        g["91"] = {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["10", 0],
                "audio": ["23", 0],
                "fps": 24.0,
            },
        }
    if first_frame_name:
        g["200"] = {
            "class_type": "LoadImage",
            "inputs": {"image": first_frame_name},
        }
        g["104"]["inputs"]["first_frame"] = ["200", 0]
    if last_frame_name:
        g["201"] = {
            "class_type": "LoadImage",
            "inputs": {"image": last_frame_name},
        }
        g["104"]["inputs"]["last_frame"] = ["201", 0]
    return apply_lora(g, lora_name, lora_strength)


def build_ref2va_prompt(
    *,
    text: str,
    ref_image_names: Optional[list[str]] = None,
    ref_video_names: Optional[list[str]] = None,
    width: int = 1344,
    height: int = 768,
    length: int = 124,
    seed: int = 0,
    steps: int = 20,
    sampler: str = "res_multistep",
    scheduler: str = "simple",
    ref_image_size: str = "match",
    models: Optional[dict] = None,
    filename_prefix: str = "video/H3_Studio_Ref",
    silent_audio: bool = False,
    include_video_audio: bool = True,
    lora_name: Optional[str] = None,
    lora_strength: float = 0.75,
) -> dict[str, Any]:
    """Build Ref2VA graph (MiniMaxH3ReferenceToVideo + Ref2VA UNET).

    Videos: LoadVideo → GetVideoComponents → IMAGE (+ optional AUDIO) into
    ref_videos / ref_video_audios (Comfy object_info: ref_video is IMAGE).
    """
    ref_image_names = list(ref_image_names or [])
    ref_video_names = list(ref_video_names or [])
    if not ref_image_names and not ref_video_names:
        raise ValueError("Ref2VA için en az 1 referans görsel veya video gerekir")
    if len(ref_image_names) > 9:
        raise ValueError("En fazla 9 referans görsel")
    if len(ref_video_names) > 3:
        raise ValueError("En fazla 3 referans video")
    size_mode = "max" if str(ref_image_size).lower() == "max" else "match"
    m = {**REF2VA_MODELS, **(models or {})}
    g: dict[str, Any] = {
        "6": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": m["unet"], "weight_dtype": "default"},
        },
        "13": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": m["clip"],
                "type": "minimax",
                "device": "default",
            },
        },
        "11": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": m["vae"]},
        },
        "24": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": m["audio_vae"]},
        },
        "104": {
            "class_type": "MiniMaxH3ReferenceToVideo",
            "inputs": {
                "clip": ["13", 0],
                "vae": ["11", 0],
                "audio_vae": ["24", 0],
                "prompt": text,
                "width": width,
                "height": height,
                "length": length,
                "ref_image_size": size_mode,
            },
        },
        "16": {
            "class_type": "BasicGuider",
            "inputs": {"model": ["6", 0], "conditioning": ["104", 0]},
        },
        "17": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": sampler},
        },
        "9": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["6", 0],
                "scheduler": scheduler,
                "steps": steps,
                "denoise": 1.0,
            },
        },
        "15": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed},
        },
        "14": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["15", 0],
                "guider": ["16", 0],
                "sampler": ["17", 0],
                "sigmas": ["9", 0],
                "latent_image": ["104", 1],
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["14", 0], "vae": ["11", 0]},
        },
        "92": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["91", 0],
                "filename_prefix": filename_prefix,
                "format": "auto",
                "codec": "auto",
            },
        },
    }
    for i, name in enumerate(ref_image_names):
        nid = str(200 + i)
        g[nid] = {
            "class_type": "LoadImage",
            "inputs": {"image": name},
        }
        g["104"]["inputs"][f"ref_images.ref_image_{i}"] = [nid, 0]

    # Video refs: LoadVideo (file in Comfy input/) → frames + embedded audio
    for i, vname in enumerate(ref_video_names):
        load_id = str(300 + i * 2)
        split_id = str(301 + i * 2)
        g[load_id] = {
            "class_type": "LoadVideo",
            "inputs": {"file": vname},
        }
        g[split_id] = {
            "class_type": "GetVideoComponents",
            "inputs": {"video": [load_id, 0]},
        }
        g["104"]["inputs"][f"ref_videos.ref_video_{i}"] = [split_id, 0]
        if include_video_audio:
            g["104"]["inputs"][f"ref_video_audios.ref_video_audio_{i}"] = [
                split_id,
                1,
            ]

    if silent_audio:
        g["91"] = {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["10", 0],
                "fps": 24.0,
            },
        }
    else:
        g["23"] = {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": ["14", 0], "vae": ["24", 0]},
        }
        g["91"] = {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["10", 0],
                "audio": ["23", 0],
                "fps": 24.0,
            },
        }
    return apply_lora(g, lora_name, lora_strength)


def apply_lora(
    g: dict[str, Any],
    lora_name: Optional[str],
    strength: float = 0.75,
) -> dict[str, Any]:
    """Patch UNET with LoraLoaderModelOnly; rewire guider + scheduler."""
    name = Path(lora_name or "").name.strip()
    if not name:
        return g
    try:
        st = float(strength)
    except (TypeError, ValueError):
        st = 0.75
    g["7"] = {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {
            "model": ["6", 0],
            "lora_name": name,
            "strength_model": st,
        },
    }
    for nid in ("16", "9"):
        node = g.get(nid) or {}
        inputs = node.get("inputs") or {}
        if inputs.get("model") == ["6", 0]:
            inputs["model"] = ["7", 0]
    return g
