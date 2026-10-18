"""Persisted Spectrum video blend; independent of solver step scheduling."""
import json
import math
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "data" / "h3_acceleration.json"
PRESETS = {"light": 0.25, "balanced": 0.5, "strong": 0.75}


def graph_settings(graph):
    """Recorded graph truth, independent of settings changed after submission."""
    inputs = next((node.get('inputs', {}) for node in graph.values()
                   if node.get('class_type') == 'SpectrumApplyMiniMaxH3'), None)
    if inputs is None:
        return {'enabled': False}
    return {'enabled': inputs.get('enabled') is True,
            'video_blend_weight': inputs.get('blend_weight'),
            'audio_blend_weight': inputs.get('audio_blend_weight'),
            'offline_smoothing_replay': inputs.get('offline_smoothing_replay')}


def clean_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    preset = raw.get("spectrum_preset", "balanced")
    preset = preset if preset in (*PRESETS, "custom") else "balanced"
    weight = raw.get("spectrum_blend_weight", PRESETS.get(preset, 0.5))
    try:
        if isinstance(weight, bool):
            raise ValueError
        weight = float(weight)
        if not math.isfinite(weight) or not 0 <= weight <= 1:
            raise ValueError
    except (TypeError, ValueError):
        weight = PRESETS.get(preset, 0.5)
    if preset in PRESETS and weight != PRESETS[preset]:
        preset = "custom"
    return {"spectrum_enabled": raw.get("spectrum_enabled") is True,
            "spectrum_preset": preset, "spectrum_blend_weight": weight}


def load_settings(path=None):
    try:
        return clean_settings(json.loads((path or SETTINGS_PATH).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return clean_settings({})


def update_settings(current, changes):
    merged = {**clean_settings(current), **changes}
    preset = changes.get("spectrum_preset")
    if "spectrum_blend_weight" in changes:
        merged["spectrum_preset"] = "custom"
    elif preset in PRESETS:
        merged["spectrum_blend_weight"] = PRESETS[preset]
    return clean_settings(merged)


def save_settings(settings, path=None):
    path = path or SETTINGS_PATH
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(clean_settings(settings), indent=2), encoding="utf-8")
    temporary.replace(path)
