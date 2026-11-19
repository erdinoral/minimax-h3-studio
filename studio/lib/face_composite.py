"""Place aligned generated faces on source frames, preserving source scenery.

Ambiguous detections and large pose mismatches leave the source frame intact.
This deliberately handles one visible person. Multi-person identity selection
requires an identity tracker rather than choosing the largest face every frame.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .face_crop import _model
from .frames import _ffmpeg, _run


def _video_info(path):
    probe = str(Path(_ffmpeg()).with_name('ffprobe' + Path(_ffmpeg()).suffix))
    result = _run([probe, '-v', 'error', '-select_streams', 'v:0',
                   '-show_entries', 'stream=width,height,avg_frame_rate',
                   '-of', 'json', str(path)])
    if result.returncode:
        raise RuntimeError(result.stderr[-400:])
    stream = json.loads(result.stdout)['streams'][0]
    num, den = map(int, stream['avg_frame_rate'].split('/'))
    if num <= 0 or den <= 0:
        raise ValueError('Source video has no usable frame rate')
    return stream, num / den


def blend_face(source, generated, source_face, generated_face):
    """Five-landmark alignment with a feathered inner-face mask."""
    import cv2
    import numpy as np

    src_points = source_face[4:14].reshape(5, 2).astype(np.float32)
    gen_points = generated_face[4:14].reshape(5, 2).astype(np.float32)
    matrix, _ = cv2.estimateAffinePartial2D(gen_points, src_points, method=cv2.LMEDS)
    if matrix is None:
        return source, False
    aligned_points = cv2.transform(gen_points[None], matrix)[0]
    face_width = float(source_face[2])
    if np.linalg.norm(aligned_points - src_points, axis=1).max() > face_width * .12:
        return source, False
    h, w = source.shape[:2]
    aligned = cv2.warpAffine(generated, matrix, (w, h))
    x, y, fw, fh = map(float, source_face[:4])
    mask = np.zeros((h, w), np.float32)
    # Keep hair, hats, ears, neck and everything outside the inner face original.
    cv2.ellipse(mask, (round(x + fw / 2), round(y + fh * .56)),
                (max(1, round(fw * .40)), max(1, round(fh * .43))),
                0, 0, 360, 1, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), max(1., fw * .035))
    # Match local lighting, including the changing illumination of an explosion.
    valid = mask > .6
    if not valid.any():
        return source, False
    delta = source[valid].mean(axis=0) - aligned[valid].mean(axis=0)
    corrected = np.clip(aligned.astype(np.float32) + delta, 0, 255)
    result = source.astype(np.float32) * (1 - mask[..., None]) + corrected * mask[..., None]
    return np.clip(result, 0, 255).astype(np.uint8), True


def composite(source: Path, generated: Path, output: Path, models: Path,
              keep_audio: bool = True) -> dict:
    """Stream frames at source dimensions/rate, atomically publish a final MP4.

    Source and generated inputs must cover the same timeline. Original frames
    are used where detection/alignment fails. No unbounded frame cache is kept.
    """
    import cv2
    import numpy as np

    source, generated, output = map(Path, (source, generated, output))
    if source.resolve() == output.resolve():
        raise ValueError('Output must not overwrite the source video')
    info, fps = _video_info(source)
    w, h = int(info['width']), int(info['height'])
    source_cap, gen_cap = cv2.VideoCapture(str(source)), cv2.VideoCapture(str(generated))
    encoder = None
    stats = dict(frames=0, blended=0, preserved=0, width=w, height=h, fps=fps)
    try:
        if not source_cap.isOpened() or not gen_cap.isOpened():
            raise RuntimeError('Cannot open FaceSwap source or generated video')
        gen_fps = gen_cap.get(cv2.CAP_PROP_FPS)
        if gen_fps <= 0:
            raise RuntimeError('Generated video has no usable frame rate')
        detector = cv2.FaceDetectorYN.create(str(_model(models)), '', (w, h), .85)
        gen_detector = cv2.FaceDetectorYN.create(str(_model(models)), '', (w, h), .85)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='face-composite-', dir=output.parent) as temp:
            temp = Path(temp)
            silent = temp / 'silent.mp4'
            # File-backed stderr avoids a blocked encoder pipe on verbose failures.
            with (temp / 'encoder.log').open('w+b') as log:
                encoder = subprocess.Popen([
                    _ffmpeg(), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                    '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}',
                    '-r', info['avg_frame_rate'], '-i', 'pipe:0', '-an',
                    '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:v', 'libx264',
                    '-crf', '16', '-preset', 'fast', '-pix_fmt', 'yuv420p', str(silent)],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
                gen_index, gen_frame = -1, None
                previous = None
                while True:
                    ok, frame = source_cap.read()
                    if not ok:
                        break
                    wanted = round(stats['frames'] * gen_fps / fps)
                    while gen_index < wanted:
                        ok, candidate = gen_cap.read()
                        gen_index += 1
                        gen_frame = cv2.resize(candidate, (w, h)) if ok else None
                    _, faces = detector.detect(frame)
                    selected = faces[0] if faces is not None and len(faces) == 1 else None
                    blended = False
                    if selected is not None and gen_frame is not None:
                        # Avoid jumping to a new person on a cut or ambiguous frame.
                        stable = previous is not None and np.linalg.norm(
                            selected[:2] - previous[:2]) < max(selected[2], previous[2]) * .5
                        _, generated_faces = gen_detector.detect(gen_frame)
                        if stable and generated_faces is not None and len(generated_faces) == 1:
                            frame, blended = blend_face(frame, gen_frame, selected, generated_faces[0])
                    previous = selected.copy() if selected is not None else None
                    encoder.stdin.write(frame.tobytes())
                    stats['frames'] += 1
                    stats['blended' if blended else 'preserved'] += 1
                encoder.stdin.close()
                if encoder.wait(timeout=120):
                    log.seek(0)
                    raise RuntimeError('Face compositor encode failed: ' + log.read().decode(errors='replace')[-400:])
            if not stats['blended']:
                raise RuntimeError('FaceSwap could not align a face; no swapped output was published')
            muxed = temp / 'final.mp4'
            cmd = [_ffmpeg(), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                   '-i', str(silent)]
            if keep_audio:
                cmd += ['-i', str(source), '-map', '0:v:0', '-map', '1:a:0?', '-c:a', 'aac']
            else:
                cmd += ['-map', '0:v:0', '-an']
            cmd += ['-c:v', 'copy', '-t', f"{stats['frames'] / fps:.9f}",
                    '-movflags', '+faststart', str(muxed)]
            result = _run(cmd)
            if result.returncode:
                raise RuntimeError('Face compositor audio mux failed: ' + result.stderr[-400:])
            # Windows will refuse replacement while VideoCapture holds the input
            # open when generated and output are the same path.
            gen_cap.release()
            muxed.replace(output)
        return stats
    finally:
        source_cap.release()
        gen_cap.release()
        if encoder is not None and encoder.poll() is None:
            encoder.kill()
            encoder.wait()
