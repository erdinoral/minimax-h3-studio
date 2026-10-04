"""Optional base models; never installed or selected by the default launcher."""
from __future__ import annotations
import asyncio
import hashlib
import shutil
from pathlib import Path
import httpx
from .h3_models import MODELS_ROOT
from . import h3_models

SINGULARITY = {
    "id": "singularity-pruned-int8", "label": "Singularity · Pruned INT8 (experimental)",
    "file": "minimaxH3Singularity_prunedInt8.safetensors", "bytes": 20967647456,
    "sha256": "412a7b126595a958964193f3b42513d7cf2df4196ef04223a0f05e3622949cce",
    "url": "https://huggingface.co/WarmBloodAban/Minimax-h3_Singularity/resolve/main/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors",
    "source": "https://civitai.com/models/2917208/minimax-h3singularity",
    "slots": ["unet", "unet_ref2va"],
}
ALIASES = [SINGULARITY["file"], "Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors"]
_status: dict = {}
_task = None

def folder():
    return MODELS_ROOT / "diffusion_models"

def installed():
    return next((MODELS_ROOT/sub/name for sub in ("diffusion_models", "unet") for name in ALIASES
        if (MODELS_ROOT/sub/name).is_file() and (MODELS_ROOT/sub/name).stat().st_size == SINGULARITY["bytes"]), None)

def engine_status():
    selected = h3_models.load()
    resolved = {g: h3_models.resolve(g) for g in ("fl2va", "ref2va")}
    names = [resolved[g]["unet"] for g in resolved]
    active = "singularity" if all(n in ALIASES for n in names) else (
        "minimax" if all(resolved[g]["unet"] == h3_models.defaults()["unet_ref2va" if g == "ref2va" else "unet"] for g in resolved) else "custom")
    return {"active": active, "singularity_ready": bool(installed()), "resolved": resolved}

def select_engine(engine):
    if engine not in ("minimax", "singularity"):
        raise ValueError("Unknown engine")
    path = installed() if engine == "singularity" else None
    if engine == "singularity" and not path:
        raise ValueError("Singularity model is not installed")
    name = path.name if path else ""
    h3_models.save({"unet": name, "unet_ref2va": name})
    state = engine_status()
    if state["active"] != engine:
        raise ValueError("Engine selection could not be applied")
    return state

def catalog():
    path = installed()
    partial = folder()/(SINGULARITY["file"] + ".part")
    downloaded = SINGULARITY["bytes"] if path else partial.stat().st_size if partial.is_file() else 0
    return [{**SINGULARITY, "ready": bool(path), "installed_file": path.name if path else None,
        "downloaded": downloaded, "progress": round(100*downloaded/SINGULARITY["bytes"], 1),
        "busy": bool(_task and not _task.done()), "phase": _status.get("phase", ""), "error": _status.get("error")}]

def verify(path):
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8*1024*1024): digest.update(block)
    if path.stat().st_size != SINGULARITY["bytes"] or digest.hexdigest() != SINGULARITY["sha256"]:
        raise ValueError("Model SHA256 mismatch; partial file was not activated")

async def _download():
    target=folder()/SINGULARITY["file"]
    partial=target.with_name(target.name+".part")
    try:
        folder().mkdir(parents=True,exist_ok=True)
        offset=partial.stat().st_size if partial.is_file() else 0
        if shutil.disk_usage(folder()).free < max(0,SINGULARITY["bytes"]-offset)+1024**3:
            raise ValueError("Insufficient disk space")
        _status.update(phase="downloading",error=None)
        if offset < SINGULARITY["bytes"]:
            headers={"Range": f"bytes={offset}-"} if offset else {}
            async with httpx.AsyncClient(follow_redirects=True,timeout=httpx.Timeout(60,connect=30)) as client:
                async with client.stream("GET",SINGULARITY["url"],headers=headers) as response:
                    response.raise_for_status()
                    if offset and response.status_code == 206 and not response.headers.get("content-range", "").startswith(f"bytes {offset}-"):
                        raise ValueError("Invalid resume range")
                    mode="ab" if offset and response.status_code == 206 else "wb"
                    received=offset if mode == "ab" else 0
                    with partial.open(mode) as stream:
                        async for chunk in response.aiter_bytes(1024*1024):
                            received+=len(chunk)
                            if received>SINGULARITY["bytes"]: raise ValueError("Unexpected model size")
                            stream.write(chunk)
        _status["phase"]="verifying"
        await asyncio.to_thread(verify,partial)
        partial.replace(target)
        _status["phase"]="ready"
    except Exception as exc:
        _status.update(phase="failed",error=str(exc))

async def start(model_id):
    global _task
    if model_id != SINGULARITY["id"]: raise ValueError("Unknown optional model")
    if installed(): return catalog()[0]
    if not _task or _task.done(): _task=asyncio.create_task(_download())
    return catalog()[0]
