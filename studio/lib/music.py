"""Song upload, duration probe, and final mux helpers for H3 Studio."""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Optional


ALLOWED_EXT = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"}


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg bulunamadı (Pinokio PATH / conda)")
    return exe


def _ffprobe() -> str:
    exe = shutil.which("ffprobe")
    if not exe:
        raise RuntimeError("ffprobe bulunamadı (Pinokio PATH / conda)")
    return exe


def probe_duration_sec(path: Path) -> float:
    cmd = [
        _ffprobe(),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe hata: {(r.stderr or '')[-400:]}")
    try:
        return max(0.1, float((r.stdout or "").strip()))
    except ValueError as e:
        raise RuntimeError(f"süre okunamadı: {r.stdout!r}") from e


def suggested_sections(duration_sec: float, clip_sec: int = 5) -> list[dict[str, Any]]:
    """Coarse song sections for director timing (not DSP beat-tracking)."""
    d = float(duration_sec)
    if d <= 0:
        return []
    # Typical pop/phonk-ish layout scaled to length
    raw = [
        ("intro", 0.0, min(15.0, d * 0.12)),
        ("verse", min(15.0, d * 0.12), min(d * 0.45, d * 0.12 + 40)),
        ("chorus", min(d * 0.45, d * 0.12 + 40), min(d * 0.70, d * 0.45 + 35)),
        ("bridge", min(d * 0.70, d * 0.45 + 35), min(d * 0.85, d)),
        ("outro", min(d * 0.85, d), d),
    ]
    out: list[dict[str, Any]] = []
    for name, a, b in raw:
        a = max(0.0, min(a, d))
        b = max(a, min(b, d))
        if b - a < 0.5:
            continue
        shots = max(1, math.ceil((b - a) / clip_sec))
        out.append(
            {
                "name": name,
                "startSec": round(a, 2),
                "endSec": round(b, 2),
                "approxShots": shots,
            }
        )
    return out


def _section_at(sections: list[dict[str, Any]], t_mid: float) -> str:
    for s in sections:
        if float(s.get("startSec") or 0) <= t_mid < float(s.get("endSec") or 0) + 0.001:
            return str(s.get("name") or "verse")
    return sections[-1].get("name") if sections else "verse"


def _mean_volume_db(path: Path, start: float, length: float) -> Optional[float]:
    cmd = [
        _ffmpeg(),
        "-hide_banner",
        "-nostats",
        "-ss",
        f"{max(0.0, start):.2f}",
        "-t",
        f"{max(0.2, length):.2f}",
        "-i",
        str(path),
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", r.stderr or "", re.I)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def probe_energy_timeline(
    path: Path,
    *,
    duration_sec: float,
    clip_sec: int = 5,
) -> list[dict[str, Any]]:
    """Loudness per clip window (ffmpeg volumedetect). Not beat-tracking."""
    clip = int(clip_sec) if int(clip_sec or 0) in (4, 5, 6, 8, 10, 15) else 5
    dur = max(0.1, float(duration_sec))
    n = max(1, math.ceil(dur / clip))
    window = clip
    if n > 36:
        window = max(clip, int(math.ceil(dur / 36)))
        n = max(1, math.ceil(dur / window))
    sections = suggested_sections(dur, clip)
    levels: list[Optional[float]] = []
    for i in range(n):
        a = i * window
        length = min(window, max(0.2, dur - a))
        levels.append(_mean_volume_db(path, a, length))
    valid = [x for x in levels if x is not None]
    if not valid:
        return []
    ranked = sorted(valid)
    lo_cut = ranked[max(0, int(len(ranked) * 0.35))]
    hi_cut = ranked[min(len(ranked) - 1, int(len(ranked) * 0.72))]
    out: list[dict[str, Any]] = []
    for i, db in enumerate(levels):
        a = round(i * window, 2)
        b = round(min(dur, (i + 1) * window), 2)
        if db is None:
            energy = "mid"
        elif db <= lo_cut:
            energy = "low"
        elif db >= hi_cut:
            energy = "high"
        else:
            energy = "mid"
        mid = (a + b) / 2.0
        out.append(
            {
                "index": i + 1,
                "startSec": a,
                "endSec": b,
                "meanDb": round(db, 1) if db is not None else None,
                "energy": energy,
                "section": _section_at(sections, mid),
            }
        )
    return out


def stamp_shots_with_timeline(brief: dict[str, Any], timeline: list[dict[str, Any]]) -> dict[str, Any]:
    shots = brief.get("shots") if isinstance(brief.get("shots"), list) else []
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict) or i >= len(timeline):
            continue
        t = timeline[i]
        shot["startSec"] = t.get("startSec")
        shot["endSec"] = t.get("endSec")
        shot["energy"] = t.get("energy")
        shot["section"] = t.get("section")
        act = (shot.get("action") or "").strip()
        tag = f"{t.get('section')} · {t.get('energy')} energy"
        if tag.lower() not in act.lower():
            shot["action"] = f"{tag}; {act}" if act else tag
    brief["shots"] = shots
    brief["force_continue"] = True
    brief["silentAudio"] = True
    return brief


def save_upload(
    music_dir: Path,
    *,
    filename: str,
    data: bytes,
) -> dict[str, Any]:
    music_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(filename or "track.mp3").suffix.lower() or ".mp3"
    if ext not in ALLOWED_EXT:
        raise ValueError(f"desteklenmeyen format: {ext}")
    mid = str(uuid.uuid4())
    dest = music_dir / f"{mid}{ext}"
    dest.write_bytes(data)
    duration = probe_duration_sec(dest)
    meta = {
        "id": mid,
        "filename": Path(filename).name,
        "path": str(dest),
        "ext": ext,
        "durationSec": round(duration, 3),
        "created_at": time.time(),
        "lyrics": "",
        "concept": "",
    }
    (music_dir / f"{mid}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def load_meta(music_dir: Path, music_id: str) -> dict[str, Any]:
    p = music_dir / f"{music_id}.json"
    if not p.exists():
        raise FileNotFoundError("şarkı kaydı yok")
    meta = json.loads(p.read_text(encoding="utf-8"))
    path = Path(meta.get("path") or "")
    if not path.exists():
        # recover by glob
        hits = list(music_dir.glob(f"{music_id}.*"))
        hits = [h for h in hits if h.suffix.lower() in ALLOWED_EXT]
        if not hits:
            raise FileNotFoundError("şarkı dosyası yok")
        meta["path"] = str(hits[0])
    return meta


def update_meta(music_dir: Path, music_id: str, **fields: Any) -> dict[str, Any]:
    meta = load_meta(music_dir, music_id)
    meta.update({k: v for k, v in fields.items() if v is not None})
    (music_dir / f"{music_id}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def build_song_director_seed(
    *,
    meta: dict[str, Any],
    clip_sec: int,
    lyrics: str = "",
    concept: str = "",
    visual_style: str = "realistic",
    timeline: Optional[list[dict[str, Any]]] = None,
) -> str:
    dur = float(meta.get("durationSec") or 0)
    n = max(1, math.ceil(dur / clip_sec))
    sections = suggested_sections(dur, clip_sec)
    lyr = (lyrics or meta.get("lyrics") or "").strip()
    idea = (concept or meta.get("concept") or "").strip()
    sec_txt = json.dumps(sections, ensure_ascii=False)
    tl = timeline or meta.get("energyTimeline") or []
    if tl:
        rows = []
        for t in tl[:n]:
            db = t.get("meanDb")
            db_s = f"{db}dB" if db is not None else "?"
            rows.append(
                f"#{t.get('index')} {t.get('startSec')}–{t.get('endSec')}s "
                f"{t.get('section')} energy={t.get('energy')} rms={db_s}"
            )
        tl_txt = "\n".join(rows)
    else:
        tl_txt = "(enerji ölçümü yok — bölüm tahminine uy)"
    lyr_block = lyr[:6000] if lyr else "(söz yok — enerji eğrisine göre sahne yaz; uydurma lyric overlay yazma)"
    return (
        f"Müzik klibi üret. Şarkı: {meta.get('filename')} · süre {dur:.1f}sn · "
        f"klip {clip_sec}sn → tam {n} shot, TEK continue zinciri (shot1 standalone, 2+ continue).\n"
        f"purpose=music_video visualStyle={visual_style} aspect=16:9 "
        f"totalDurationSec={int(round(dur))} expectedShotCount={n} clipDurationSec={clip_sec} "
        f"silentAudio=true force_continue=true.\n"
        f"Konsept: {idea or 'cinematic music video; one lead, one wardrobe, one primary location'}\n"
        f"Bölüm tahmini: {sec_txt}\n"
        f"GERÇEK SES EĞRİSİ (her satır = bir shot; enerjiye uy — high=chorus push, low=intro/outro hold):\n"
        f"{tl_txt}\n"
        f"Sözler / lyric ipucu (sadece görüntü hikâyesi; ağız şarkı söylemesin, lip-sync yok):\n{lyr_block}\n\n"
        "TUTARLILIK (zorunlu):\n"
        "- characters[] içinde 1–2 kişi: age, face, hair, eyes, build, EXACT wardrobe. "
        "Her h3Prompt aynı kartı tekrarlar; kıyafet/saç değişmez.\n"
        "- Tek ana mekân (veya tek gece/tek iç mekân). Chorus’ta kamera/ışık büyür, set değişmez.\n"
        "- Shot 2+ h3Prompt 'Continue directly from the previous shot.' + Same [names], identical clothing.\n"
        "- Her shot ≥1100 karakter İngilizce SCENE; energy=high ise daha geniş hareket / ışık; "
        "energy=low ise yakın, yavaş, mikro eylem.\n"
        "- Söz varsa o zaman aralığındaki duyguyu yansıt; ekranda yazı/lyric overlay yok.\n"
        "CRITICAL silentAudio=true: no dialogue, no singing, no SFX, no generated music — "
        "SILENT VISUAL ONLY (song muxed later).\n"
        "Bitince ready:true ile TAM JSON brief ver (purpose=music_video, silentAudio=true, characters[], shots[n])."
    )


def concat_and_mux(
    *,
    video_paths: list[Path],
    audio_path: Path,
    out_path: Path,
) -> Path:
    """Concat clips (video only), then replace audio with the user song."""
    if not video_paths:
        raise ValueError("birleştirilecek video yok")
    for p in video_paths:
        if not p.exists():
            raise FileNotFoundError(f"video yok: {p}")
    if not audio_path.exists():
        raise FileNotFoundError(f"şarkı yok: {audio_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.parent / f"_mux_{out_path.stem}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        list_file = work / "concat.txt"
        lines = []
        for p in video_paths:
            # ffmpeg concat demuxer needs escaped single quotes
            esc = str(p.resolve()).replace("'", r"'\''")
            lines.append(f"file '{esc}'")
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        silent = work / "concat_silent.mp4"
        cmd1 = [
            _ffmpeg(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(silent),
        ]
        r1 = subprocess.run(cmd1, capture_output=True, text=True)
        if r1.returncode != 0 or not silent.exists():
            # re-encode fallback (codec mismatch across clips)
            cmd1b = [
                _ffmpeg(),
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "24",
                str(silent),
            ]
            r1b = subprocess.run(cmd1b, capture_output=True, text=True)
            if r1b.returncode != 0 or not silent.exists():
                raise RuntimeError(
                    f"video birleştirme başarısız: {(r1b.stderr or r1.stderr or '')[-600:]}"
                )

        cmd2 = [
            _ffmpeg(),
            "-y",
            "-i",
            str(silent),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(out_path),
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True)
        if r2.returncode != 0 or not out_path.exists():
            raise RuntimeError(f"şarkı mux başarısız: {(r2.stderr or '')[-600:]}")
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _has_audio_stream(path: Path) -> bool:
    cmd = [
        _ffprobe(),
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return bool((r.stdout or "").strip())


def _normalize_clip_keep_audio(src: Path, dest: Path) -> None:
    """H264 + stereo AAC so concat/amix stay compatible. Silent clips get room tone."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if _has_audio_stream(src):
        cmd = [
            _ffmpeg(),
            "-y",
            "-i",
            str(src),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "24",
            "-c:a",
            "aac",
            "-ar",
            "32000",
            "-ac",
            "2",
            "-b:a",
            "160k",
            str(dest),
        ]
    else:
        cmd = [
            _ffmpeg(),
            "-y",
            "-i",
            str(src),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=32000:cl=stereo",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "24",
            "-c:a",
            "aac",
            "-shortest",
            str(dest),
        ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(f"klip normalize başarısız: {(r.stderr or '')[-600:]}")


def concat_keep_audio(*, video_paths: list[Path], out_path: Path) -> Path:
    """Join clips in order, keep each clip's dialogue/SFX."""
    if not video_paths:
        raise ValueError("birleştirilecek video yok")
    for p in video_paths:
        if not p.exists():
            raise FileNotFoundError(f"video yok: {p}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.parent / f"_cinema_cat_{out_path.stem}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        normalized: list[Path] = []
        for i, p in enumerate(video_paths):
            dest = work / f"clip_{i:03d}.mp4"
            _normalize_clip_keep_audio(p, dest)
            normalized.append(dest)
        list_file = work / "concat.txt"
        lines = []
        for p in normalized:
            esc = str(p.resolve()).replace("'", r"'\''")
            lines.append(f"file '{esc}'")
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        cmd = [
            _ffmpeg(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(out_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not out_path.exists():
            raise RuntimeError(f"video birleştirme başarısız: {(r.stderr or '')[-600:]}")
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)


def concat_keep_audio_mix_score(
    *,
    video_paths: list[Path],
    audio_path: Path,
    out_path: Path,
    score_volume: float = 0.16,
) -> Path:
    """Concat clips keeping dialogue/SFX, then mix one film score underneath."""
    if not video_paths:
        raise ValueError("birleştirilecek video yok")
    for p in video_paths:
        if not p.exists():
            raise FileNotFoundError(f"video yok: {p}")
    if not audio_path.exists():
        raise FileNotFoundError(f"film müziği yok: {audio_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.parent / f"_cinema_mux_{out_path.stem}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        normalized: list[Path] = []
        for i, p in enumerate(video_paths):
            dest = work / f"clip_{i:03d}.mp4"
            _normalize_clip_keep_audio(p, dest)
            normalized.append(dest)

        list_file = work / "concat.txt"
        lines = []
        for p in normalized:
            esc = str(p.resolve()).replace("'", r"'\''")
            lines.append(f"file '{esc}'")
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        concat = work / "concat.mp4"
        cmd1 = [
            _ffmpeg(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(concat),
        ]
        r1 = subprocess.run(cmd1, capture_output=True, text=True)
        if r1.returncode != 0 or not concat.exists():
            raise RuntimeError(f"video birleştirme başarısız: {(r1.stderr or '')[-600:]}")

        vol = max(0.02, min(0.6, float(score_volume)))
        cmd2 = [
            _ffmpeg(),
            "-y",
            "-i",
            str(concat),
            "-stream_loop",
            "-1",
            "-i",
            str(audio_path),
            "-filter_complex",
            (
                f"[1:a]volume={vol},aformat=sample_fmts=fltp:sample_rates=32000:channel_layouts=stereo[sc];"
                "[0:a]aformat=sample_fmts=fltp:sample_rates=32000:channel_layouts=stereo[dx];"
                "[dx][sc]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
            ),
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(out_path),
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True)
        if r2.returncode != 0 or not out_path.exists():
            raise RuntimeError(f"film müziği karışımı başarısız: {(r2.stderr or '')[-600:]}")
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)
