"""Full-length Motion Transfer: render a long reference video in short GPU-safe parts.

Each part follows its own slice of the reference video. Parts after the first
start one frame early and are anchored on the previous part's boundary frame,
so dropping that duplicated first frame keeps the joined timeline exact.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .frames import _ffmpeg, _probe_duration, _run, duration_to_length

FPS = 24
SEGMENT_SECONDS = 5.0
# 2/3 s renders are trimmed after generation, which would remove the frames a part needs.
RENDER_DURATIONS = (4, 5, 6, 8, 10)
MIN_SECONDS = 4.0
MAX_SECONDS = 30.0


def probe_seconds(path: Path) -> float:
    return _probe_duration(_ffmpeg(), Path(path))


def plan_windows(total_seconds: float, segment_seconds: float = SEGMENT_SECONDS) -> list[dict]:
    total = int(round(float(total_seconds) * FPS))
    step = int(round(float(segment_seconds) * FPS))
    if total < FPS or step < FPS:
        raise ValueError("Reference video is too short")
    spans: list[list[int]] = []
    start = 0
    while start < total:
        frames = min(step, total - start)
        spans.append([start, frames])
        start += frames
    # A sub-second tail gives H3 too little motion to follow; fold it into the previous part.
    if len(spans) > 1 and spans[-1][1] < FPS:
        spans[-2][1] += spans.pop()[1]
    windows = []
    for index, (start, frames) in enumerate(spans):
        skip = 0 if index == 0 else 1
        need = frames + skip
        duration = next((d for d in RENDER_DURATIONS if duration_to_length(d) >= need), None)
        if duration is None:
            raise ValueError("Motion Transfer part is longer than a supported render")
        windows.append({
            "start_frame": start,
            "frames": frames,
            "skip": skip,
            "duration": duration,
            "ref_start": (start - skip) / FPS,
            "ref_seconds": need / FPS,
        })
    return windows


def part_prompts(base: str, beats: list[dict], windows: list[dict]) -> list[str]:
    """Give each part only the actions timed inside it.

    A beat is {"start": s, "end": s | None, "text": str}; an open end lasts until
    the next beat starts. Sending every action to every part makes H3 rush the
    whole story into the first part.
    """
    timed = sorted(
        ({"start": float(b.get("start") or 0.0), "end": b.get("end"), "text": str(b.get("text") or "").strip()}
         for b in beats or []),
        key=lambda b: b["start"],
    )
    timed = [b for b in timed if b["text"]]
    for i, beat in enumerate(timed):
        if beat["end"] is None:
            beat["end"] = timed[i + 1]["start"] if i + 1 < len(timed) else float("inf")
        beat["end"] = max(float(beat["end"]), beat["start"])
    prompts = []
    for window in windows:
        lo = window["start_frame"] / FPS
        hi = (window["start_frame"] + window["frames"]) / FPS
        texts = [b["text"].rstrip(".") for b in timed if b["start"] < hi and b["end"] > lo]
        if texts:
            prompts.append(f"{base.strip()} In this shot: {'. Then '.join(texts)}.")
        else:
            prompts.append(base)
    return prompts


def has_audio(path: Path) -> bool:
    result = _run([_ffmpeg(), "-hide_banner", "-i", str(path)])
    return "Audio:" in ((result.stderr or "") + (result.stdout or ""))


def slice_reference(source: Path, output: Path, start: float, seconds: float) -> Path:
    """Exact 24 fps excerpt; H3 reads reference frames as 24 fps."""
    output.parent.mkdir(parents=True, exist_ok=True)
    result = _run([
        _ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-ss", f"{max(0.0, start):.6f}", "-i", str(source), "-t", f"{seconds:.6f}",
        "-map", "0:v:0", "-map", "0:a:0?", "-r", str(FPS),
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-preset", "fast",
        "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart",
        str(output),
    ])
    if result.returncode or not output.is_file() or output.stat().st_size < 64:
        raise RuntimeError(f"Reference slice failed: {(result.stderr or '')[-400:]}")
    return output


def extract_frame(video: Path, index: int, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = _run([
        _ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(video),
        "-vf", f"select=eq(n\\,{int(index)})", "-vsync", "0", "-frames:v", "1", str(output),
    ])
    if result.returncode or not output.is_file() or output.stat().st_size < 100:
        raise RuntimeError(f"Boundary frame {index} could not be extracted: {(result.stderr or '')[-300:]}")
    return output


def assemble(parts: list[tuple[Path, int, int]], output: Path, audio_source: Optional[Path] = None) -> Path:
    """Join (video, skip, frames) parts; prefer the reference video's own soundtrack."""
    if not parts:
        raise ValueError("No parts to join")
    output.parent.mkdir(parents=True, exist_ok=True)
    total = sum(frames for _, _, frames in parts) / FPS
    use_source = bool(audio_source and Path(audio_source).is_file() and has_audio(audio_source))
    use_generated = not use_source and all(has_audio(path) for path, _, _ in parts)
    cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    for path, _, _ in parts:
        cmd += ["-i", str(path)]
    filters, labels = [], []
    for i, (_, skip, frames) in enumerate(parts):
        filters.append(f"[{i}:v]trim=start_frame={skip}:end_frame={skip + frames},setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
        if use_generated:
            filters.append(f"[{i}:a]atrim=start={skip / FPS:.6f}:end={(skip + frames) / FPS:.6f},asetpts=PTS-STARTPTS[a{i}]")
            labels.append(f"[a{i}]")
    n = len(parts)
    filters.append("".join(labels) + f"concat=n={n}:v=1:a={1 if use_generated else 0}" + ("[v][a]" if use_generated else "[v]"))
    maps = ["-map", "[v]"]
    if use_generated:
        maps += ["-map", "[a]"]
    elif use_source:
        cmd += ["-i", str(audio_source)]
        maps += ["-map", f"{n}:a:0"]
    cmd += ["-filter_complex", ";".join(filters), *maps,
            "-r", str(FPS), "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-t", f"{total:.6f}", "-movflags", "+faststart", str(output)]
    result = _run(cmd)
    if result.returncode or not output.is_file() or output.stat().st_size < 64:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"Motion Transfer join failed: {(result.stderr or '')[-600:]}")
    return output
