"""Local, durable music stem jobs, isolated from the video render process."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import wave
import time
import uuid
from pathlib import Path
from typing import Literal

import psutil
from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[1]
STEMS = ("vocals", "drums", "bass", "guitar", "piano", "other")
PROFILES = {
    "fast": {"bundle": "HDEMUCS_HIGH_MUSDB", "model": "HDemucs MUSDB", "overlap": 1, "shifts": 1},
    "quality": {"bundle": "HDEMUCS_HIGH_MUSDB_PLUS", "model": "HDemucs MUSDB+", "overlap": 2.5, "shifts": 2},
}


def separation_settings(device, preset, channels):
    settings = {"requested_device": device, "preset": preset, "channels": channels, **PROFILES[preset]}
    if channels == 6:
        settings.update(bundle="htdemucs_6s", model="HTDemucs 6s")
    return settings


def write_status(folder, **state):
    target = folder / "status.json"
    temp = folder / f"status-{os.getpid()}.tmp"
    temp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(temp, target)


def read_status(folder):
    try:
        state = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "error", "error": "Stem job record is unavailable"}
    if state.get("status") in ("running", "queued") and state.get("pid"):
        try:
            process = psutil.Process(state["pid"])
            alive = str(folder) in process.cmdline()
        except (psutil.Error, OSError):
            alive = False
        if not alive:
            state.update(status="error", error="Stem worker stopped. You can retry separation.")
    return state


def launch_worker(folder, suffix, ffmpeg, *options):
    python = ROOT.parent / "app" / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        python = Path(sys.executable)
    with (folder / "worker.log").open("ab") as log:
        subprocess.Popen(
            [str(python), "-m", "lib.music_workspace", str(folder), suffix, ffmpeg, *map(str, options)],
            cwd=ROOT, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )


def create_router(data_dir):
    router = APIRouter(prefix="/api/music-workspace")
    root = Path(data_dir) / "music_stems"
    lyrics_root = Path(data_dir) / "music_lyrics"
    projects_root = Path(data_dir) / "music_projects"
    project_files = projects_root / "files"
    lock = threading.Lock()

    def folder_for(key, storage=root):
        if not re.fullmatch(r"[0-9a-f]{24}", key):
            raise HTTPException(400, "Invalid stem job")
        folder = storage / key
        if not folder.is_dir():
            raise HTTPException(404, "Stem job not found")
        return folder

    def project_path(key):
        if key != "draft" and not re.fullmatch(r"[0-9a-f]{12}", key):
            raise HTTPException(400, "Invalid music project")
        return projects_root / f"{key}.json"

    @router.post("/project-files")
    async def upload_project_file(file: UploadFile = File(...)):
        name = Path(file.filename or "file").name
        suffix = Path(name).suffix.lower()
        if suffix not in {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(400, "Unsupported music project file")
        raw = await file.read(40 * 1024 * 1024 + 1)
        if not raw or len(raw) > 40 * 1024 * 1024:
            raise HTTPException(413, "Project file must be between 1 byte and 40 MB")
        key = hashlib.sha256(raw).hexdigest() + suffix
        project_files.mkdir(parents=True, exist_ok=True)
        target = project_files / key
        if not target.is_file():
            temp = project_files / (uuid.uuid4().hex + ".tmp")
            temp.write_bytes(raw)
            os.replace(temp, target)
        return {"file_id": key, "filename": name, "type": file.content_type or "application/octet-stream"}

    @router.get("/project-files/{key}")
    async def project_file(key: str):
        if not re.fullmatch(r"[0-9a-f]{64}\.(mp3|wav|flac|ogg|m4a|aac|png|jpg|jpeg|webp)", key):
            raise HTTPException(400, "Invalid project file")
        path = project_files / key
        if not path.is_file():
            raise HTTPException(404, "Project file is missing")
        return FileResponse(path)

    @router.get("/projects")
    async def list_projects():
        projects = []
        for path in projects_root.glob("*.json"):
            if path.stem == "draft":
                continue
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                projects.append({"id": item["id"], "name": item["name"], "updated_at": item["updated_at"]})
            except (OSError, ValueError, KeyError):
                continue
        return {"projects": sorted(projects, key=lambda row: row["updated_at"], reverse=True)}

    @router.get("/projects/{key}")
    async def load_project(key: str):
        path = project_path(key)
        if not path.is_file():
            raise HTTPException(404, "Music project not found")
        return json.loads(path.read_text(encoding="utf-8"))

    @router.put("/projects/{key}")
    async def save_project(key: str, body: dict = Body(...)):
        path = project_path(key)
        state = body.get("state")
        if not isinstance(state, dict) or len(json.dumps(state)) > 1024 * 1024:
            raise HTTPException(400, "Invalid music project state")
        for field in ("song", "character"):
            asset = state.get(field)
            if asset:
                if not isinstance(asset, dict):
                    raise HTTPException(400, "Invalid music project file")
                file_id = str(asset.get("file_id") or "")
                if not re.fullmatch(r"[0-9a-f]{64}\.[a-z0-9]+", file_id) or not (project_files / file_id).is_file():
                    raise HTTPException(400, "A music project file is missing")
        record = {"id": key, "name": str(body.get("name") or "Music video")[:160],
                  "updated_at": time.time(), "state": state}
        projects_root.mkdir(parents=True, exist_ok=True)
        with lock:
            temp = projects_root / (uuid.uuid4().hex + ".tmp")
            temp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, path)
        return record

    @router.post("/stems")
    async def separate(file: UploadFile = File(...), device: Literal["cpu", "gpu"] = Form("cpu"),
                       preset: Literal["fast", "quality"] = Form("fast"), channels: int = Form(4)):
        if channels not in (4, 6):
            raise HTTPException(400, "Stem channel count must be 4 or 6")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}:
            raise HTTPException(400, "Unsupported audio format")
        raw = await file.read(40 * 1024 * 1024 + 1)
        if not raw or len(raw) > 40 * 1024 * 1024:
            raise HTTPException(413, "Song must be between 1 byte and 40 MB")
        cache_version = f"htdemucs-6s-v1:{device}:{preset}:" if channels == 6 else f"hdemucs-v2:{device}:{preset}:"
        key = hashlib.sha256(cache_version.encode() + raw).hexdigest()[:24]
        root.mkdir(parents=True, exist_ok=True)
        with lock:
            folder = root / key
            if (folder / "status.json").exists():
                state = read_status(folder)
                if state["status"] in ("done", "queued", "running"):
                    return {"id": key, **state}
            for record in root.glob("*/status.json"):
                if read_status(record.parent).get("status") in ("queued", "running"):
                    raise HTTPException(409, "Another song is being separated. Wait for it to finish.")
            folder.mkdir(exist_ok=True)
            (folder / ("source" + suffix)).write_bytes(raw)
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise HTTPException(503, "ffmpeg is unavailable in the Studio environment")
            settings = separation_settings(device, preset, channels)
            write_status(folder, status="queued", progress=0, phase="starting", **settings)
            try:
                launch_worker(folder, suffix, ffmpeg, device, preset, channels)
            except OSError as exc:
                write_status(folder, status="error", error=str(exc))
                raise HTTPException(503, "Could not start local stem worker") from exc
        return {"id": key, "status": "queued", "progress": 0}

    @router.post("/lyrics")
    async def extract_lyrics(file: UploadFile = File(...), stem_job: str = Form("")):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}:
            raise HTTPException(400, "Unsupported audio format")
        raw = await file.read(40 * 1024 * 1024 + 1)
        if not raw or len(raw) > 40 * 1024 * 1024:
            raise HTTPException(413, "Song must be between 1 byte and 40 MB")
        vocals = None
        if re.fullmatch(r"[0-9a-f]{24}", stem_job):
            stem_folder = root / stem_job
            original = next(stem_folder.glob("source.*"), None)
            candidate = stem_folder / "vocals.wav"
            if (original and candidate.is_file() and read_status(stem_folder).get("status") == "done"
                    and hashlib.sha256(original.read_bytes()).digest() == hashlib.sha256(raw).digest()):
                vocals = candidate
        key = hashlib.sha256(b"whisper-small-int8-v1:" + (stem_job if vocals else "original").encode() + raw).hexdigest()[:24]
        lyrics_root.mkdir(parents=True, exist_ok=True)
        with lock:
            folder = lyrics_root / key
            if (folder / "status.json").is_file():
                state = read_status(folder)
                if state["status"] in ("queued", "running", "done"):
                    return {"id": key, **state}
            for record in lyrics_root.glob("*/status.json"):
                if read_status(record.parent).get("status") in ("queued", "running"):
                    raise HTTPException(409, "Another lyrics extraction is running. Wait for it to finish.")
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise HTTPException(503, "ffmpeg is unavailable")
            folder.mkdir(exist_ok=True)
            if vocals:
                suffix = ".wav"
                shutil.copyfile(vocals, folder / "source.wav")
            else:
                (folder / ("source" + suffix)).write_bytes(raw)
            write_status(folder, status="queued", phase="starting", progress=0)
            try:
                launch_worker(folder, suffix, ffmpeg, "lyrics", "vocals" if vocals else "song")
            except OSError as exc:
                write_status(folder, status="error", error=str(exc))
                raise HTTPException(503, "Could not start lyrics extraction") from exc
        return {"id": key, "status": "queued", "progress": 0}

    @router.get("/lyrics/{key}")
    async def lyrics_status(key: str):
        return {"id": key, **read_status(folder_for(key, lyrics_root))}

    @router.get("/stems/{key}")
    async def status(key: str):
        return {"id": key, **read_status(folder_for(key))}

    @router.get("/stems/{key}/{name}")
    async def audio(key: str, name: str):
        if name not in STEMS:
            raise HTTPException(404, "Unknown stem")
        folder = folder_for(key)
        if read_status(folder).get("status") != "done":
            raise HTTPException(409, "Stems are not ready")
        if not (folder / f"{name}.wav").is_file():
            raise HTTPException(404, "This stem is not part of the result")
        return FileResponse(folder / f"{name}.wav", media_type="audio/wav")

    return router


def run_worker(folder, suffix, ffmpeg, device="cpu", preset="fast", channels=4):
    """HDemucs with bounded device windows and a shared gain across all stems."""
    settings = separation_settings(device, preset, channels)

    def report(**state):
        write_status(folder, pid=os.getpid(), **settings, **state)

    try:
        report(status="running", progress=0, phase="loading_model")
        import numpy as np
        import soundfile as sf
        import torch
        from torchaudio import pipelines

        if device not in ("cpu", "gpu"):
            raise ValueError("Unknown stem device")
        if device == "gpu" and not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU is unavailable. Select CPU for stem separation.")
        target = torch.device("cuda" if device == "gpu" else "cpu")
        settings["device"] = str(target)
        settings["device_name"] = torch.cuda.get_device_name(target) if device == "gpu" else "CPU"
        report(status="running", progress=0, phase="loading_model")

        torch.set_num_threads(max(1, min(4, (os.cpu_count() or 4) // 2)))
        decoded = folder / "decoded.wav"
        result = subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", str(folder / ("source" + suffix)),
             "-t", "601", "-ar", "44100", "-ac", "2", str(decoded)], capture_output=True,
        )
        if result.returncode:
            raise ValueError("Could not decode song: " + result.stderr.decode(errors="replace")[-300:])
        waveform, sr = sf.read(decoded, dtype="float32", always_2d=True)
        if not len(waveform) or len(waveform) > sr * 600:
            raise ValueError("Stem separation supports songs up to 10 minutes")
        if channels == 6:
            from demucs.pretrained import get_model
            ensemble = get_model("htdemucs_6s")
            if len(ensemble.models) != 1:
                raise ValueError("Expected a single six-channel model")
            model = ensemble.models[0]
        else:
            bundle = getattr(pipelines, settings["bundle"])
            model = bundle.get_model()
        model = model.eval().to(target)
        source_count = len(model.sources)
        if source_count != channels:
            raise ValueError("The loaded model does not match the requested channel count")
        sample = torch.from_numpy(waveform.T.copy())
        mono = sample.mean(0)
        mean, std = mono.mean(), mono.std().clamp_min(1e-8)
        sample = (sample - mean) / std
        length = sample.shape[-1]
        window = sr * (6 if device == "gpu" else 10)
        if channels == 6:
            window = min(window, int(model.segment * sr) - int(sr * .25 * (settings["shifts"] - 1)))
        overlap = int(sr * settings["overlap"])
        stride = window - overlap
        output = torch.zeros(source_count, 2, length)
        weights = torch.zeros(length)
        with torch.inference_mode():
            for offset in range(0, length, stride):
                end = min(length, offset + window)
                chunk = sample[:, offset:end]
                estimate = torch.zeros(source_count, 2, end - offset)
                for index in range(settings["shifts"]):
                    shift = int(sr * .25 * index)
                    shifted = torch.nn.functional.pad(chunk, (shift, 0)).unsqueeze(0).to(target)
                    prediction = model(shifted)[0][..., shift:shift + end - offset]
                    estimate += prediction.cpu() / settings["shifts"]
                    del shifted, prediction
                fade = torch.ones(end - offset)
                if offset:
                    n = min(overlap, len(fade))
                    fade[:n] = torch.linspace(1 / n, 1, n)
                if end < length:
                    n = min(overlap, len(fade))
                    fade[-n:] = torch.linspace(1, 1 / n, n)
                output[..., offset:end] += estimate * fade
                weights[offset:end] += fade
                report(status="running", phase="separating", progress=round(end / length * 95))
                if end == length:
                    break
        output = output / weights.clamp_min(1e-8) * std + mean / source_count
        gain = max(1.0, float(output.abs().max()) / .99)
        tracks = []
        for index, name in enumerate(model.sources):
            values = (output[index] / gain).T.numpy()
            sf.write(folder / f"{name}.wav", values, sr, subtype="PCM_24")
            bins = np.array_split(np.abs(values).max(axis=1), min(2400, len(values)))
            tracks.append({"name": name, "peaks": [round(float(x.max()), 5) for x in bins],
                           "url": f"/api/music-workspace/stems/{folder.name}/{name}"})
        report(status="done", progress=100, duration=length / sr, tracks=tracks)
        decoded.unlink(missing_ok=True)
    except Exception as exc:
        error = str(exc)[-600:]
        if device == "gpu" and "out of memory" in str(exc).lower():
            error = "GPU memory is insufficient. Finish the current video render or select CPU for stems."
        report(status="error", error=error)
        raise


def run_lyrics_worker(folder, suffix, ffmpeg, input_kind="song"):
    def report(**state):
        write_status(folder, pid=os.getpid(), model="Whisper small", device="cpu", input_kind=input_kind, **state)

    try:
        report(status="running", phase="decoding", progress=0)
        decoded = folder / "decoded.wav"
        result = subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", str(folder / ("source" + suffix)),
             "-t", "601", "-ar", "16000", "-ac", "1", str(decoded)], capture_output=True,
        )
        if result.returncode:
            raise ValueError("Could not decode the song")
        with wave.open(str(decoded), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
        if not 0 < duration <= 600:
            raise ValueError("Automatic lyrics supports songs up to 10 minutes")
        report(status="running", phase="loading_model", progress=0)
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
        report(status="running", phase="transcribing", progress=0)
        segments, info = model.transcribe(str(decoded), beam_size=5, vad_filter=True,
                                          condition_on_previous_text=False)
        lines = []
        timed = []
        for segment in segments:
            text = " ".join(segment.text.split())
            if text and segment.no_speech_prob < .8:
                start = max(0, min(duration, segment.start))
                end = max(start, min(duration, segment.end))
                ticks = round(start * 100)
                lines.append(f"[{ticks // 6000:02d}:{ticks // 100 % 60:02d}.{ticks % 100:02d}] {text}")
                timed.append({"start": start, "end": end, "text": text})
            report(status="running", phase="transcribing", progress=min(99, round(segment.end / duration * 100)))
        report(status="done", progress=100, language=info.language, duration=duration,
               lrc="\n".join(lines), segments=timed)
        decoded.unlink(missing_ok=True)
    except Exception as exc:
        report(status="error", error=str(exc)[-600:])
        raise


if __name__ == "__main__":
    if len(sys.argv) > 4 and sys.argv[4] == "lyrics":
        run_lyrics_worker(Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[5])
    else:
        run_worker(Path(sys.argv[1]), sys.argv[2], sys.argv[3],
                   sys.argv[4] if len(sys.argv) > 4 else "cpu", sys.argv[5] if len(sys.argv) > 5 else "fast",
                   int(sys.argv[6]) if len(sys.argv) > 6 else 4)
