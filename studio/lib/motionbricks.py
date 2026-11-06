"""Local mirror of the MotionBricks Playground runtime and robot take encoding.

The playground (Apache-2.0 runtime, BSD-3 robot meshes) is fetched on first use from a pinned
Hugging Face Space revision into Studio's data folder, so the Motion tab can drive it from the
same origin. The NVIDIA model and sample clips are never mirrored: the page streams them from
their own hosts under their own licenses.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import httpx

SPACE = "townbox/motionbricks-playground"
REVISION = "6407b61e635163a97b9f2934579ac8e22695d43e"
FILES = frozenset({
    "index.html", "style.css", "css/style.css",
    "js/assets.js", "js/capture.js", "js/character.js", "js/icons.js", "js/inference.js", "js/main.js",
    "js/mathx.js", "js/motion.js", "js/primitives.js", "js/promo.js", "js/robot.js", "js/worker.js",
    "assets/g1.glb", "assets/g1_lite.glb", "assets/g1_kinematics.json",
    "licenses/motionbricks-Apache-2.0.txt", "licenses/unitree-BSD-3-Clause.txt", "models/LICENSE.md",
})
MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".json": "application/json",
    ".glb": "model/gltf-binary", ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8",
}
FPS = 24
MIN_SECONDS, MAX_SECONDS = 4.0, 30.0

_locks: dict[str, asyncio.Lock] = {}


def media_type(path: str) -> str:
    return MEDIA_TYPES.get(Path(path).suffix.lower(), "application/octet-stream")


async def ensure_file(path: str, cache_root: Path) -> Path:
    """Return the cached copy of an allowed playground file, downloading it once."""
    if path not in FILES:
        raise FileNotFoundError(path)
    dest = Path(cache_root) / REVISION / path
    if dest.is_file():
        return dest
    lock = _locks.setdefault(path, asyncio.Lock())
    async with lock:
        if dest.is_file():
            return dest
        url = f"https://huggingface.co/spaces/{SPACE}/resolve/{REVISION}/{path}"
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            response = await client.get(url)
        response.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(response.content)
        tmp.replace(dest)
    return dest


def encode_take(frames: Path, dest: Path, fps: int = FPS) -> float:
    """Encode a concatenated JPEG stream (one frame per JPEG) into an H.264 MP4; return seconds."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg bulunamadı (Pinokio PATH / conda)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([
        ffmpeg, "-hide_banner", "-v", "error", "-y", "-f", "mjpeg", "-framerate", str(fps), "-i", str(frames),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", "-c:v", "libx264", "-preset", "fast",
        "-crf", "18", "-r", str(fps), "-movflags", "+faststart", str(dest),
    ], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode or not dest.is_file() or not dest.stat().st_size:
        raise RuntimeError(f"Robot kaydı videoya çevrilemedi: {(result.stderr or '')[-400:]}")
    return frame_count(dest) / fps


def frame_count(video: Path) -> int:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe bulunamadı (Pinokio PATH / conda)")
    result = subprocess.run([
        ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets",
        "-show_entries", "stream=nb_read_packets", "-of", "default=nokey=1:noprint_wrappers=1", str(video),
    ], capture_output=True, text=True)
    try:
        return int(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("Robot kaydının kare sayısı okunamadı") from exc
