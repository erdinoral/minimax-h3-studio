"""Extract last/first frame from a video via ffmpeg."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg bulunamadı (Pinokio PATH / conda)")
    return exe


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _ok_image(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 32


def _probe_duration(ffmpeg: str, video_path: Path) -> float:
    r = _run([ffmpeg, "-hide_banner", "-i", str(video_path)])
    blob = (r.stderr or "") + (r.stdout or "")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", blob)
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def extract_last_frame(video_path: Path, out_path: Path) -> Path:
    """Grab the last video frame. Avoids full reverse (OOM on long clips)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg()
    last_err = ""
    attempts: list[list[str]] = [
        [
            ffmpeg, "-hide_banner", "-y",
            "-sseof", "-0.15",
            "-i", str(video_path),
            "-an", "-frames:v", "1", "-q:v", "2",
            str(out_path),
        ],
        [
            ffmpeg, "-hide_banner", "-y",
            "-sseof", "-1",
            "-i", str(video_path),
            "-an", "-update", "1", "-q:v", "2",
            str(out_path),
        ],
    ]
    dur = _probe_duration(ffmpeg, video_path)
    if dur > 0.05:
        attempts.append(
            [
                ffmpeg, "-hide_banner", "-y",
                "-ss", f"{max(0.0, dur - 0.08):.3f}",
                "-i", str(video_path),
                "-an", "-frames:v", "1", "-q:v", "2",
                str(out_path),
            ]
        )
    for cmd in attempts:
        try:
            if out_path.exists():
                out_path.unlink()
        except OSError:
            pass
        r = _run(cmd)
        if r.returncode == 0 and _ok_image(out_path):
            return out_path
        last_err = ((r.stderr or r.stdout or "")[-500:]).strip()
    # Last resort: decode the clip and keep the last written frame (4–15s H3 clips).
    try:
        if out_path.exists():
            out_path.unlink()
    except OSError:
        pass
    r = _run(
        [
            ffmpeg, "-hide_banner", "-y",
            "-i", str(video_path),
            "-an", "-vsync", "0", "-q:v", "2", "-update", "1",
            str(out_path),
        ]
    )
    if r.returncode == 0 and _ok_image(out_path):
        return out_path
    last_err = ((r.stderr or r.stdout or last_err)[-500:]).strip()
    raise RuntimeError(f"son kare alınamadı: {last_err or 'ffmpeg çıktı vermedi'}")


def resize_image(src: Path, out_path: Path, width: int, height: int) -> Path:
    """Force exact WxH (H3 first_frame latent pack requires matching size)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = int(width), int(height)
    if w < 16 or h < 16:
        raise RuntimeError(f"geçersiz boyut {w}x{h}")
    cmd = [
        _ffmpeg(),
        "-y",
        "-i",
        str(src),
        "-vf",
        f"scale={w}:{h}:flags=lanczos,setsar=1",
        "-frames:v",
        "1",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"kare ölçeklenemedi ({w}x{h}): {(r.stderr or '')[-400:]}")
    return out_path


def duration_to_length(seconds: int) -> int:
    """H3 17k+5 grid @ 24fps (Comfy Math Expression in stock workflow)."""
    a = max(5, int(round(seconds * 24)))
    return a + (5 - (a % 17)) % 17


def strip_audio(video_path: Path) -> Path:
    """Remove audio track in-place (music-video preview / pre-mux)."""
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(str(video_path))
    tmp = video_path.with_suffix(".silent.tmp.mp4")
    cmd = [
        _ffmpeg(),
        "-y",
        "-i",
        str(video_path),
        "-an",
        "-c:v",
        "copy",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists():
        # re-encode fallback
        cmd = [
            _ffmpeg(),
            "-y",
            "-i",
            str(video_path),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(tmp),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not tmp.exists():
            raise RuntimeError(f"ses silinemedi: {(r.stderr or '')[-400:]}")
    tmp.replace(video_path)
    return video_path
