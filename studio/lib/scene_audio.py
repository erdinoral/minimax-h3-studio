"""Explicit audio routing for a single Scene clip."""
from pathlib import Path
import re


def validate_source(name, mode, root):
    if mode not in ("reference", "original"):
        raise ValueError("Choose an audio mode: reference or original")
    if not re.fullmatch(r"h3_voice_[A-Za-z0-9_-]+\.(wav|mp3|flac|ogg|m4a|aac)", name or ""):
        raise ValueError("Invalid uploaded audio file")
    path = Path(root) / name
    if not path.is_file():
        raise ValueError("Uploaded audio is missing; select it again")
    return path


def replace_audio(video, source):
    import subprocess
    from .music import _ffmpeg
    video = Path(video)
    output = video.with_name(video.stem + "_audio.mp4")
    try:
        result = subprocess.run([_ffmpeg(), "-y", "-i", str(video), "-i", str(source),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
            "-af", "apad", "-shortest", str(output)], capture_output=True, text=True)
        if result.returncode or not output.is_file():
            raise RuntimeError("Audio attachment failed: " + result.stderr[-400:])
        output.replace(video)
    finally:
        output.unlink(missing_ok=True)
