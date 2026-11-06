"""Crop a reference still to the main face so a face swap gets identity, not a scene.

A full-frame still also carries background, wardrobe and props, and H3 Ref2VA
takes those along — the swapped person ends up in the still's scene instead of
the video's.
"""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path
from typing import Optional

YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
# Head plus hairline; wider crops bring the shirt, props and set back in.
HEAD_SCALE = 1.45


def _model(folder: Path) -> Path:
    path = folder / "face_detection_yunet_2023mar.onnx"
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == YUNET_SHA256:
        return path
    folder.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with urllib.request.urlopen(YUNET_URL, timeout=60) as r:
        tmp.write_bytes(r.read())
    if hashlib.sha256(tmp.read_bytes()).hexdigest() != YUNET_SHA256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Face detector download failed verification")
    tmp.replace(path)
    return path


def crop_main_face(source: Path, output: Path, model_folder: Path) -> Optional[Path]:
    """Write a square head crop of the largest face; None when no face is found."""
    import cv2
    import numpy as np

    image = cv2.imdecode(np.fromfile(str(source), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    h, w = image.shape[:2]
    detector = cv2.FaceDetectorYN.create(str(_model(model_folder)), "", (w, h), 0.7)
    _, faces = detector.detect(image)
    if faces is None or not len(faces):
        return None
    x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])[:4]
    side = min(max(fw, fh) * HEAD_SCALE, w, h)
    cx, cy = x + fw / 2, y + fh / 2 - fh * 0.12
    left = int(min(max(cx - side / 2, 0), w - side))
    top = int(min(max(cy - side / 2, 0), h - side))
    crop = image[top:top + int(side), left:left + int(side)]
    output.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", crop)
    if not ok:
        return None
    encoded.tofile(str(output))
    return output
