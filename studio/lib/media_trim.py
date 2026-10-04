"""Accurate reference excerpts; the uploaded original is never overwritten."""
from __future__ import annotations

import math
import subprocess
from pathlib import Path
from .frames import _ffmpeg, _probe_duration


def validate_range(start, end, duration: float, maximum: float = 15.0) -> tuple[float, float]:
    if start is None or end is None:
        raise ValueError("Both start and end are required")
    start, end = float(start), float(end)
    if not all(math.isfinite(v) for v in (start, end, duration)) or duration <= 0:
        raise ValueError("Invalid media duration or range")
    if start < 0 or end <= start or end > duration + 0.05:
        raise ValueError("Selection must be inside the source media")
    if end - start < 0.1 or end - start > maximum + 0.001:
        raise ValueError("Reference selection must be between 0.1 and 15 seconds")
    return start, min(end, duration)


def trim_reference(source: Path, output: Path, kind: str, start, end) -> Path:
    if kind not in {"audio", "video"} or source.resolve() == output.resolve():
        raise ValueError("Invalid trim destination")
    ffmpeg = _ffmpeg()
    start, end = validate_range(start, end, _probe_duration(ffmpeg, source))
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-ss", f"{start:.6f}", "-i", str(source), "-t", f"{end-start:.6f}"]
    if kind == "video":
        cmd += ["-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264",
                "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:a", "aac", "-movflags", "+faststart"]
    else:
        cmd += ["-map", "0:a:0", "-vn", "-c:a", "pcm_s16le", "-ar", "32000", "-ac", "2"]
    try:
        result = subprocess.run(cmd + [str(output)], capture_output=True, timeout=120)
        if result.returncode or not output.is_file() or output.stat().st_size < 64:
            raise RuntimeError("Reference trim failed; check media and FFmpeg")
        measured = _probe_duration(ffmpeg, output)
        if measured <= 0 or abs(measured - (end-start)) > 0.2:
            raise RuntimeError("Trimmed reference has an unexpected duration")
        return output
    except Exception:
        output.unlink(missing_ok=True)
        raise
