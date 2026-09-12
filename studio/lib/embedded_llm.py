"""Embedded GGUF director LLM — no Ollama / no cloud API.

Three hardware tiers aimed at ~2B / ~5B / ~9B (max ~9B class):
  light — Qwen3 1.7B Q4 (~1.1 GB) · ≈2B · CPU / 4 GB VRAM
  mid   — Qwen3 4B   Q4 (~2.5 GB) · ≈5B · 6–8 GB VRAM
  high  — Qwen3 8B   Q4 (~5.0 GB) · ≈9B · 8 GB+ VRAM

Downloads GGUF into studio/data/llm/ on first use; unload before Comfy/H3.
"""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any, Optional

STUDIO_ROOT = Path(__file__).resolve().parent.parent
LLM_DIR = STUDIO_ROOT / "data" / "llm"

# Instruct-capable Qwen3 GGUFs — Q4_K_M sweet spot. No true public 2B/5B/9B;
# 1.7≈2, 4≈5, 8≈9. (Compressed 14B multi-file skipped — download/load pain.)
EMBEDDED_CATALOG: dict[str, dict[str, Any]] = {
    "qwen3-1.7b-q4_k_m": {
        "repo": "unsloth/Qwen3-1.7B-GGUF",
        "file": "Qwen3-1.7B-Q4_K_M.gguf",
        "label": "Hafif · Qwen3 1.7B Q4 (≈2B, ~1.1 GB)",
        "tier": "light",
        "params_b": 1.7,
        "approx_gb": 1.1,
        "chat_format": "chatml",
        "no_think": True,
    },
    "qwen3-4b-q4_k_m": {
        "repo": "Qwen/Qwen3-4B-GGUF",
        "file": "Qwen3-4B-Q4_K_M.gguf",
        "label": "Orta · Qwen3 4B Q4 (≈5B, ~2.5 GB)",
        "tier": "mid",
        "params_b": 4.0,
        "approx_gb": 2.5,
        "chat_format": "chatml",
        "no_think": True,
    },
    "qwen3-8b-q4_k_m": {
        "repo": "Qwen/Qwen3-8B-GGUF",
        "file": "Qwen3-8B-Q4_K_M.gguf",
        "label": "Güçlü · Qwen3 8B Q4 (≈9B, ~5 GB)",
        "tier": "high",
        "params_b": 8.0,
        "approx_gb": 5.0,
        "chat_format": "chatml",
        "no_think": True,
    },
    # Uncensored +18 director — only when Studio +18 mode is on
    "dolphin3-llama3.1-8b-q4_k_m": {
        "repo": "bartowski/Dolphin3.0-Llama3.1-8B-GGUF",
        "file": "Dolphin3.0-Llama3.1-8B-Q4_K_M.gguf",
        "label": "+18 Sansürsüz · Dolphin 8B Q4 (~5 GB)",
        "tier": "adult",
        "params_b": 8.0,
        "approx_gb": 5.0,
        "chat_format": "chatml",
        "no_think": False,
        "uncensored": True,
        "adult": True,
    },
}

LOCAL_TIERS: dict[str, dict[str, Any]] = {
    "light": {
        "id": "light",
        "label": "Hafif ≈2B",
        "hint": "Qwen3 1.7B · CPU / düşük VRAM (≈4 GB)",
        "embedded": "qwen3-1.7b-q4_k_m",
        "min_chars": 600,
        "n_ctx": 4096,
        "num_predict": 2048,
        "ollama_prefer": (
            "qwen3:1.7b",
            "qwen2.5:1.5b",
            "qwen3:4b",
            "qwen2.5:3b",
            "llama3.2:3b",
            "phi3:mini",
        ),
        "max_params_b": 2.5,
        "target_params_b": 1.7,
    },
    "mid": {
        "id": "mid",
        "label": "Orta ≈5B",
        "hint": "Qwen3 4B · orta kart (≈6–8 GB VRAM)",
        "embedded": "qwen3-4b-q4_k_m",
        "min_chars": 750,
        "n_ctx": 6144,
        "num_predict": 3072,
        "ollama_prefer": (
            "qwen3:4b",
            "qwen3:4b-instruct",
            "qwen2.5:7b",
            "qwen3:8b",
            "qwen2.5:3b",
        ),
        "max_params_b": 5.5,
        "target_params_b": 4.0,
    },
    "high": {
        "id": "high",
        "label": "Güçlü ≈9B",
        "hint": "Qwen3 8B · daha iyi kalite (≈8 GB+ VRAM) — 9B üstü yok",
        "embedded": "qwen3-8b-q4_k_m",
        "min_chars": 900,
        "n_ctx": 8192,
        "num_predict": 4096,
        "ollama_prefer": (
            "qwen3:8b",
            "qwen2.5:7b",
            "qwen3:9b",
            "qwen2.5:9b",
            "llama3.1:8b",
        ),
        "max_params_b": 9.0,
        "target_params_b": 8.0,
    },
    "adult": {
        "id": "adult",
        "label": "+18 Sansürsüz",
        "hint": "Dolphin 8B · açık yetişkin yazım (Ayarlar’da +18 gerekir, ≈8 GB+)",
        "embedded": "dolphin3-llama3.1-8b-q4_k_m",
        "min_chars": 900,
        "n_ctx": 8192,
        "num_predict": 4096,
        "ollama_prefer": (
            "dolphin3:8b",
            "dolphin-llama3:8b",
            "dolphin-llama3.1:8b",
            "dolphin3.0-llama3.1:8b",
            "nous-hermes2:10.7b",
        ),
        "max_params_b": 11.0,
        "target_params_b": 8.0,
        "adult": True,
        "uncensored": True,
    },
}

DEFAULT_LOCAL_TIER = "mid"
DEFAULT_EMBEDDED_MODEL = LOCAL_TIERS[DEFAULT_LOCAL_TIER]["embedded"]


def normalize_local_tier(tier: Optional[str]) -> str:
    t = (tier or DEFAULT_LOCAL_TIER).strip().lower()
    if t in ("light", "hafif", "low", "1.5b", "1.7b", "2b", "small"):
        return "light"
    if t in (
        "adult",
        "uncensored",
        "nsfw",
        "+18",
        "18",
        "eros",
        "dolphin",
        "sansursuz",
        "sansürsüz",
    ):
        return "adult"
    if t in ("high", "guclu", "güçlü", "strong", "7b", "8b", "9b", "max"):
        return "high"
    if t in ("mid", "orta", "medium", "3b", "4b", "5b", "default"):
        return "mid"
    return DEFAULT_LOCAL_TIER if t not in LOCAL_TIERS else t


def is_adult_tier(tier: Optional[str] = None) -> bool:
    return normalize_local_tier(tier) == "adult"


def tier_for_embedded_model(model_id: str) -> str:
    meta = EMBEDDED_CATALOG.get(model_id) or {}
    t = str(meta.get("tier") or "")
    return t if t in LOCAL_TIERS else DEFAULT_LOCAL_TIER


def embedded_id_for_tier(tier: str) -> str:
    t = normalize_local_tier(tier)
    return str(LOCAL_TIERS[t]["embedded"])


def min_chars_for_tier(tier: Optional[str]) -> int:
    t = normalize_local_tier(tier)
    return int(LOCAL_TIERS[t].get("min_chars") or 750)


def num_predict_for_tier(tier: Optional[str]) -> int:
    t = normalize_local_tier(tier)
    return int(LOCAL_TIERS[t].get("num_predict") or 3072)


def local_director_addendum(tier: Optional[str] = None) -> str:
    """Compact rules so small local models still produce usable director JSON / SCENE."""
    t = normalize_local_tier(tier)
    mc = min_chars_for_tier(t)
    common = (
        f"\n\n## LOCAL LLM · DIRECTOR ({t.upper()} · ≈2B/5B/9B class)\n"
        "Be concise but complete.\n"
        "- Reply with ONE JSON object when the brief is ready (ready:true).\n"
        "- No markdown fences unless wrapping that JSON.\n"
        f"- Each h3Prompt SCENE body ≥{mc} English characters; include camera, subject, action, light.\n"
        "- music_video + silentAudio=true: NO dialogue, NO singing, NO SFX, NO score — silent visual only.\n"
        "- Keep 1–2 characters with FIXED wardrobe; location stays consistent across shots.\n"
        "- Shot 1 standalone; shot 2+ start with Continue directly from the previous shot.\n"
    )
    if t == "light":
        return common + (
            "- Prefer outline first: shotOutline[] with title/beat/camera, then fill shots[] "
            "(expand step can write full SCENE).\n"
            "- Shorter logline/reply OK. Prioritize valid JSON structure over prose.\n"
            "- You are the DIRECTOR, not the analyst — never write 'as the analyst'.\n"
        )
    if t == "high":
        return common + (
            "- Aim for richer lighting, camera verbs, and beat-synced action per energy window.\n"
            "- Still stay under verbose chat — JSON brief is the product.\n"
        )
    if t == "adult":
        return common + (
            "- Adult/uncensored: write explicit SCENE body when purpose=adult — "
            "do not refuse or euphemize away requested acts/nudity.\n"
            "- Still keep JSON valid; never invent underage characters.\n"
        )
    return common + (
        "- If context is long, prioritize shotOutline + characters + first shots; expand fills the rest.\n"
    )


def local_music_analyst_addendum(tier: Optional[str] = None) -> str:
    """Rules for song-analysis turns — Analyst identity, not Director chat."""
    t = normalize_local_tier(tier)
    mc = min_chars_for_tier(t)
    common = (
        f"\n\n## LOCAL LLM · MUSIC ANALYST ({t.upper()} · ≈2B/5B/9B class)\n"
        "- Read energy windows + lyrics; plan shotOutline aligned to the song timeline.\n"
        "- Output ONE JSON FilmBrief (ready:true). User-facing `reply` as Analyst.\n"
        f"- Prefer solid shotOutline + characters[]; fill shots[] with SCENE ≥{mc} chars when possible.\n"
        "- silentAudio music_video: silent visual only — no lip-sync, no invented score/SFX.\n"
        "- Continuity: one wardrobe, one primary location; shot 2+ continue.\n"
        "- You are the ANALYST, not the director — never write 'as the director'; "
        "say you completed the song analysis.\n"
    )
    if t == "light":
        return common + (
            "- Context is tight: characters + full shotOutline first; partial shots OK "
            "(Director expand will write missing SCENE bodies).\n"
            "- JSON validity > long prose.\n"
        )
    if t == "high":
        return common + (
            "- Match energy=high windows with bigger camera/light moves; energy=low with intimate micro-action.\n"
            "- Still keep reply short; the brief is the deliverable.\n"
        )
    return common + (
        "- If the song is long, outline every window; write as many full shots as context allows.\n"
    )


def public_tiers() -> list[dict[str, Any]]:
    out = []
    for tid in ("light", "mid", "high", "adult"):
        meta = LOCAL_TIERS[tid]
        emb = meta["embedded"]
        cat = EMBEDDED_CATALOG.get(emb) or {}
        out.append(
            {
                "id": tid,
                "label": meta["label"],
                "hint": meta["hint"],
                "embedded_model": emb,
                "ollama_model": str((meta.get("ollama_prefer") or ("",))[0] or ""),
                "approx_gb": cat.get("approx_gb"),
                "params_b": cat.get("params_b"),
                "min_chars": meta.get("min_chars"),
                "adult": bool(meta.get("adult") or cat.get("adult")),
                "uncensored": bool(meta.get("uncensored") or cat.get("uncensored")),
            }
        )
    return out


def _vram_gb() -> float:
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return float(props.total_memory) / (1024**3)
    except Exception:
        pass
    return 0.0


def _parse_params_b(name: str) -> Optional[float]:
    import re

    low = (name or "").lower()
    m = re.search(r"(?:[:\-_/]|^)(\d+(?:\.\d+)?)\s*b\b", low)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def pick_ollama_for_tier(names: list[str], tier: str) -> Optional[str]:
    """Pick an installed Ollama model for tier; never above ~9B."""
    if not names:
        return None
    t = normalize_local_tier(tier)
    meta = LOCAL_TIERS[t]
    max_b = float(meta.get("max_params_b") or 9.0)
    prefer = tuple(meta.get("ollama_prefer") or ())

    def allowed(n: str) -> bool:
        pb = _parse_params_b(n)
        if pb is not None and pb > max_b + 0.05:
            return False
        low = n.lower()
        # Hard ban heavy models regardless of tier
        if any(x in low for x in ("14b", "32b", "70b", "72b", "405b")):
            return False
        return True

    pool = [n for n in names if allowed(n)]
    if not pool:
        pool = list(names)

    for p in prefer:
        if p in pool:
            return p
    # Fuzzy: prefer contains prefer-token
    for p in prefer:
        token = p.split(":")[0]
        for n in pool:
            if token in n.lower() and allowed(n):
                return n
    # Size-ordered fallback within cap
    scored: list[tuple[float, str]] = []
    for n in pool:
        pb = _parse_params_b(n)
        if pb is None:
            scored.append((3.0, n))
        elif pb <= max_b:
            scored.append((pb, n))
    if not scored:
        return pool[0]
    # Prefer largest under cap for high/adult, mid-sized for mid, smallest for light
    scored.sort(key=lambda x: x[0])
    if t == "light":
        return scored[0][1]
    if t in ("high", "adult"):
        return scored[-1][1]
    # mid: closest to tier target (~4–5B)
    target = float(meta.get("target_params_b") or 4.0)
    return min(scored, key=lambda x: abs(x[0] - target))[1]


class EmbeddedLlm:
    def __init__(self, models_dir: Optional[Path] = None):
        self.models_dir = Path(models_dir or LLM_DIR)
        self._llm = None
        self._loaded_id: str = ""
        self._lock = threading.Lock()

    def model_ids(self) -> list[str]:
        return list(EMBEDDED_CATALOG.keys())

    def model_labels(self) -> dict[str, str]:
        return {k: v.get("label") or k for k, v in EMBEDDED_CATALOG.items()}

    def path_for(self, model_id: str) -> Path:
        meta = EMBEDDED_CATALOG.get(model_id) or EMBEDDED_CATALOG[DEFAULT_EMBEDDED_MODEL]
        return self.models_dir / meta["file"]

    def is_ready(self, model_id: Optional[str] = None) -> bool:
        mid = (model_id or DEFAULT_EMBEDDED_MODEL).strip() or DEFAULT_EMBEDDED_MODEL
        if mid not in EMBEDDED_CATALOG:
            mid = DEFAULT_EMBEDDED_MODEL
        return self.path_for(mid).is_file()

    def ensure_llama_cpp(self) -> None:
        try:
            import llama_cpp  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "llama-cpp-python yok — Pinokio: Update / Install "
                "(studio/requirements.txt → llama-cpp-python)."
            ) from e

    def ensure_model(self, model_id: str) -> Path:
        mid = (model_id or DEFAULT_EMBEDDED_MODEL).strip() or DEFAULT_EMBEDDED_MODEL
        if mid not in EMBEDDED_CATALOG:
            mid = DEFAULT_EMBEDDED_MODEL
        meta = EMBEDDED_CATALOG[mid]
        dest = self.path_for(mid)
        if dest.is_file() and dest.stat().st_size > 1_000_000:
            return dest
        self.models_dir.mkdir(parents=True, exist_ok=True)
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as e:
            raise RuntimeError(
                "huggingface_hub yok — Pinokio Update / Install ile studio deps kur."
            ) from e
        path = hf_hub_download(
            repo_id=meta["repo"],
            filename=meta["file"],
            local_dir=str(self.models_dir),
        )
        return Path(path)

    def _n_gpu_layers(self, model_id: str) -> int:
        """Scale offload by free-ish VRAM and model size — avoid OOM on 4–6 GB cards."""
        try:
            import torch

            if not torch.cuda.is_available():
                return 0
        except Exception:
            return 0
        vram = _vram_gb()
        meta = EMBEDDED_CATALOG.get(model_id) or {}
        need = float(meta.get("approx_gb") or 2.0)
        # Leave headroom for Comfy later; unload still clears before produce
        if vram < 3.5:
            return 0
        if vram < need + 1.5:
            return 8
        if vram < need + 3.0:
            return 20
        if vram < 10:
            return 28
        return 33

    def _n_ctx(self, model_id: str) -> int:
        tier = tier_for_embedded_model(model_id)
        return int(LOCAL_TIERS.get(tier, {}).get("n_ctx") or 6144)

    def _load_locked(self, model_id: str):
        self.ensure_llama_cpp()
        from llama_cpp import Llama

        mid = (model_id or DEFAULT_EMBEDDED_MODEL).strip() or DEFAULT_EMBEDDED_MODEL
        if mid not in EMBEDDED_CATALOG:
            mid = DEFAULT_EMBEDDED_MODEL
        path = self.ensure_model(mid)
        if self._llm is not None and self._loaded_id == mid:
            return self._llm
        self._unload_locked()
        meta = EMBEDDED_CATALOG.get(mid) or {}
        chat_fmt = str(meta.get("chat_format") or "chatml")
        self._llm = Llama(
            model_path=str(path),
            n_ctx=self._n_ctx(mid),
            n_gpu_layers=self._n_gpu_layers(mid),
            verbose=False,
            chat_format=chat_fmt,
        )
        self._loaded_id = mid
        return self._llm

    def _unload_locked(self) -> list[str]:
        freed: list[str] = []
        if self._llm is not None:
            freed.append(self._loaded_id or "embedded")
            try:
                del self._llm
            except Exception:
                pass
            self._llm = None
            self._loaded_id = ""
            try:
                import gc

                gc.collect()
            except Exception:
                pass
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
        return freed

    def unload(self) -> list[str]:
        with self._lock:
            return self._unload_locked()

    def chat_sync(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        format_json: bool = False,
        num_predict: int = 4096,
    ) -> str:
        cleaned: list[dict[str, str]] = []
        for m in messages or []:
            role = str(m.get("role") or "user").strip().lower()
            if role not in ("system", "user", "assistant"):
                role = "user"
            content = str(m.get("content") or "").strip()
            if not content:
                continue
            cleaned.append({"role": role, "content": content})
        if not cleaned:
            raise RuntimeError("Boş mesaj")
        mid = (model_id or DEFAULT_EMBEDDED_MODEL).strip()
        meta = EMBEDDED_CATALOG.get(mid) or EMBEDDED_CATALOG[DEFAULT_EMBEDDED_MODEL]
        # Qwen3 hybrid models: force non-thinking for structured director JSON
        if meta.get("no_think"):
            cleaned = list(cleaned)
            if cleaned and cleaned[0]["role"] == "system":
                cleaned[0] = {
                    "role": "system",
                    "content": cleaned[0]["content"] + "\n/no_think",
                }
            else:
                cleaned.insert(
                    0,
                    {
                        "role": "system",
                        "content": "You are a concise director assistant. /no_think",
                    },
                )
        if format_json:
            cleaned = list(cleaned)
            cleaned.append(
                {
                    "role": "user",
                    "content": "Respond with valid JSON only. No markdown fences. /no_think",
                }
            )
        with self._lock:
            llm = self._load_locked(model_id)
            tier = tier_for_embedded_model(mid)
            cap = 2048 if tier == "light" else 3072 if tier == "mid" else 4096
            out = llm.create_chat_completion(
                messages=cleaned,
                temperature=float(temperature),
                max_tokens=max(256, min(int(num_predict or 1024), cap)),
            )
        try:
            return (out["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            raise RuntimeError(f"gömülü LLM boş yanıt: {e}") from e

    async def chat(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        format_json: bool = False,
        num_predict: int = 4096,
    ) -> str:
        return await asyncio.to_thread(
            self.chat_sync,
            model_id,
            messages,
            temperature=temperature,
            format_json=format_json,
            num_predict=num_predict,
        )

    async def probe(self, model_id: Optional[str] = None) -> dict[str, Any]:
        mid = (model_id or DEFAULT_EMBEDDED_MODEL).strip() or DEFAULT_EMBEDDED_MODEL
        if mid not in EMBEDDED_CATALOG:
            mid = DEFAULT_EMBEDDED_MODEL
        try:
            self.ensure_llama_cpp()
        except Exception as e:
            return {
                "online": False,
                "provider": "embedded",
                "models": self.model_ids(),
                "detail": str(e)[:160],
                "default_model": mid,
            }
        ready = self.is_ready(mid)
        return {
            "online": True,
            "provider": "embedded",
            "models": self.model_ids(),
            "detail": "ok" if ready else "will_download_on_first_chat",
            "default_model": mid,
            "model_ready": ready,
            "local_tier": tier_for_embedded_model(mid),
            "vram_gb": round(_vram_gb(), 1),
        }


embedded_llm = EmbeddedLlm()
