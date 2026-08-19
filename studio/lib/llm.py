"""Multi-provider LLM client for H3 Director.

Providers: ollama | openai | gemini | grok | claude
API keys live in studio/data/llm_settings.json (gitignored).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import httpx

from lib.ollama import OllamaClient, OLLAMA_URL

PROVIDERS = ("ollama", "openai", "gemini", "grok", "claude")

# Prefer current AI Studio models — gemini-2.5-* is closed to many new keys (404).
GEMINI_MODELS = (
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
)
GEMINI_MODEL_ALIASES = {
    "gemini-2.5-flash": "gemini-3.6-flash",
    "gemini-2.5-flash-lite": "gemini-3.1-flash-lite",
    "gemini-2.0-flash": "gemini-3.6-flash",
    "gemini-2.0-flash-lite": "gemini-3.1-flash-lite",
    "gemini-1.5-flash": "gemini-3.6-flash",
    "gemini-1.5-pro": "gemini-3.5-flash",
}
GROK_MODELS = (
    "grok-3-mini",
    "grok-3",
    "grok-2-latest",
)
OPENAI_MODELS = (
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1-mini",
    "gpt-4.1",
    "o4-mini",
)
CLAUDE_MODELS = (
    "claude-sonnet-4-20250514",
    "claude-3-5-haiku-latest",
    "claude-3-5-sonnet-latest",
    "claude-opus-4-20250514",
)

KEY_FIELDS = (
    "openai_api_key",
    "gemini_api_key",
    "grok_api_key",
    "claude_api_key",
)

DEFAULT_SETTINGS: dict[str, Any] = {
    "provider": "ollama",
    "ollama_base_url": "",
    "openai_api_key": "",
    "gemini_api_key": "",
    "grok_api_key": "",
    "claude_api_key": "",
    "ollama_model": "",
    "openai_model": OPENAI_MODELS[0],
    "gemini_model": GEMINI_MODELS[0],
    "grok_model": GROK_MODELS[0],
    "claude_model": CLAUDE_MODELS[0],
}


def _mask(key: str) -> str:
    k = (key or "").strip()
    if not k:
        return ""
    if len(k) <= 8:
        return "••••"
    return f"{k[:4]}…{k[-4:]}"


def _normalize_gemini_model(model: Optional[str]) -> str:
    name = (model or "").strip().replace("models/", "")
    if not name:
        return GEMINI_MODELS[0]
    return GEMINI_MODEL_ALIASES.get(name, name)


class LlmRouter:
    def __init__(self, settings_path: Path, ollama: Optional[OllamaClient] = None):
        self.settings_path = settings_path
        self.ollama = ollama or OllamaClient(OLLAMA_URL)
        self._settings = self.load()

    def load(self) -> dict[str, Any]:
        cfg = dict(DEFAULT_SETTINGS)
        env_map = {
            "openai_api_key": ("OPENAI_API_KEY",),
            "gemini_api_key": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
            "grok_api_key": ("XAI_API_KEY", "GROK_API_KEY"),
            "claude_api_key": ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY"),
        }
        for field, envs in env_map.items():
            for e in envs:
                val = os.environ.get(e)
                if val:
                    cfg[field] = val
                    break
        migrated = False
        try:
            if self.settings_path.exists():
                raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    cfg.update({k: raw[k] for k in DEFAULT_SETTINGS if k in raw})
        except Exception:
            pass
        old_g = (cfg.get("gemini_model") or "").strip()
        new_g = _normalize_gemini_model(old_g)
        if new_g != old_g:
            cfg["gemini_model"] = new_g
            migrated = True
        self._settings = cfg
        self._sync_ollama_url(cfg)
        if migrated:
            try:
                self.settings_path.parent.mkdir(parents=True, exist_ok=True)
                self.settings_path.write_text(
                    json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception:
                pass
        return cfg

    def _sync_ollama_url(self, cfg: dict[str, Any]) -> None:
        base = (cfg.get("ollama_base_url") or "").strip().rstrip("/")
        if base:
            self.ollama.base_url = base
        else:
            self.ollama.base_url = OLLAMA_URL

    def save(self, patch: dict[str, Any]) -> dict[str, Any]:
        cfg = self.load()
        for k, v in patch.items():
            if k not in DEFAULT_SETTINGS:
                continue
            if k in KEY_FIELDS and (
                v is None or str(v).strip() in ("", "••••", "keep", "__keep__")
            ):
                continue
            cfg[k] = v if not isinstance(v, str) else v.strip()
        provider = (cfg.get("provider") or "ollama").lower()
        if provider not in PROVIDERS:
            provider = "ollama"
        cfg["provider"] = provider
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._settings = cfg
        self._sync_ollama_url(cfg)
        return cfg

    @property
    def settings(self) -> dict[str, Any]:
        return self._settings

    def public_settings(self) -> dict[str, Any]:
        cfg = self.load()
        return {
            "provider": cfg.get("provider") or "ollama",
            "providers": list(PROVIDERS),
            "ollama_base_url": cfg.get("ollama_base_url") or "",
            "ollama_model": cfg.get("ollama_model") or "",
            "openai_model": cfg.get("openai_model") or OPENAI_MODELS[0],
            "gemini_model": _normalize_gemini_model(cfg.get("gemini_model")),
            "grok_model": cfg.get("grok_model") or GROK_MODELS[0],
            "claude_model": cfg.get("claude_model") or CLAUDE_MODELS[0],
            "openai_api_key_set": bool((cfg.get("openai_api_key") or "").strip()),
            "gemini_api_key_set": bool((cfg.get("gemini_api_key") or "").strip()),
            "grok_api_key_set": bool((cfg.get("grok_api_key") or "").strip()),
            "claude_api_key_set": bool((cfg.get("claude_api_key") or "").strip()),
            "openai_api_key_masked": _mask(cfg.get("openai_api_key") or ""),
            "gemini_api_key_masked": _mask(cfg.get("gemini_api_key") or ""),
            "grok_api_key_masked": _mask(cfg.get("grok_api_key") or ""),
            "claude_api_key_masked": _mask(cfg.get("claude_api_key") or ""),
            "openai_models": list(OPENAI_MODELS),
            "gemini_models": list(GEMINI_MODELS),
            "grok_models": list(GROK_MODELS),
            "claude_models": list(CLAUDE_MODELS),
        }

    def provider(self) -> str:
        return (self.load().get("provider") or "ollama").lower()

    async def healthy(self) -> bool:
        p = await self.probe()
        return bool(p.get("online"))

    async def probe(self) -> dict[str, Any]:
        cfg = self.load()
        provider = (cfg.get("provider") or "ollama").lower()
        if provider == "openai":
            return await self._probe_openai(cfg)
        if provider == "gemini":
            return await self._probe_gemini(cfg)
        if provider == "grok":
            return await self._probe_grok(cfg)
        if provider == "claude":
            return await self._probe_claude(cfg)
        return await self._probe_ollama(cfg)

    async def _probe_ollama(self, cfg: dict[str, Any]) -> dict[str, Any]:
        probe = await self.ollama.probe()
        models = list(probe.get("models") or [])
        default = self.ollama.pick_default_model(models) or cfg.get("ollama_model")
        return {
            "online": bool(probe.get("online")),
            "provider": "ollama",
            "models": models,
            "detail": probe.get("detail") or ("ok" if probe.get("online") else "offline"),
            "default_model": default,
            "ollama_url": self.ollama.base_url,
        }

    async def _probe_openai(self, cfg: dict[str, Any]) -> dict[str, Any]:
        key = (cfg.get("openai_api_key") or "").strip()
        default = cfg.get("openai_model") or OPENAI_MODELS[0]
        if not key:
            return {
                "online": False,
                "provider": "openai",
                "models": list(OPENAI_MODELS),
                "detail": "api_key_missing",
                "default_model": default,
            }
        try:
            models = await self._openai_list_models(key)
            if not models:
                models = list(OPENAI_MODELS)
            if default not in models:
                default = models[0]
            return {
                "online": True,
                "provider": "openai",
                "models": models,
                "detail": "ok",
                "default_model": default,
            }
        except Exception as e:
            return {
                "online": False,
                "provider": "openai",
                "models": list(OPENAI_MODELS),
                "detail": str(e)[:160],
                "default_model": default,
            }

    async def _probe_gemini(self, cfg: dict[str, Any]) -> dict[str, Any]:
        key = (cfg.get("gemini_api_key") or "").strip()
        default = _normalize_gemini_model(cfg.get("gemini_model"))
        if not key:
            return {
                "online": False,
                "provider": "gemini",
                "models": list(GEMINI_MODELS),
                "detail": "api_key_missing",
                "default_model": default,
            }
        try:
            models = await self._gemini_list_models(key)
            if not models:
                models = list(GEMINI_MODELS)
            if default not in models:
                default = models[0]
            return {
                "online": True,
                "provider": "gemini",
                "models": models,
                "detail": "ok",
                "default_model": default,
            }
        except Exception as e:
            return {
                "online": False,
                "provider": "gemini",
                "models": list(GEMINI_MODELS),
                "detail": str(e)[:160],
                "default_model": default,
            }

    async def _probe_grok(self, cfg: dict[str, Any]) -> dict[str, Any]:
        key = (cfg.get("grok_api_key") or "").strip()
        default = cfg.get("grok_model") or GROK_MODELS[0]
        if not key:
            return {
                "online": False,
                "provider": "grok",
                "models": list(GROK_MODELS),
                "detail": "api_key_missing",
                "default_model": default,
            }
        try:
            models = await self._grok_list_models(key)
            if not models:
                models = list(GROK_MODELS)
            if default not in models:
                default = models[0]
            return {
                "online": True,
                "provider": "grok",
                "models": models,
                "detail": "ok",
                "default_model": default,
            }
        except Exception as e:
            return {
                "online": False,
                "provider": "grok",
                "models": list(GROK_MODELS),
                "detail": str(e)[:160],
                "default_model": default,
            }

    async def _probe_claude(self, cfg: dict[str, Any]) -> dict[str, Any]:
        key = (cfg.get("claude_api_key") or "").strip()
        default = cfg.get("claude_model") or CLAUDE_MODELS[0]
        if not key:
            return {
                "online": False,
                "provider": "claude",
                "models": list(CLAUDE_MODELS),
                "detail": "api_key_missing",
                "default_model": default,
            }
        # Anthropic has no cheap list-models for free keys — treat key presence + ping as online
        try:
            await self._claude_ping(key)
            return {
                "online": True,
                "provider": "claude",
                "models": list(CLAUDE_MODELS),
                "detail": "ok",
                "default_model": default,
            }
        except Exception as e:
            # Still offer models; key may work for chat even if ping fails
            err = str(e)[:160]
            online = "authentication" not in err.lower() and "invalid" not in err.lower()
            # If we got 401, offline offline; for 404 on models endpoint, still online
            if "401" in err or "403" in err or "api_key" in err.lower():
                online = False
            else:
                online = True
            return {
                "online": online,
                "provider": "claude",
                "models": list(CLAUDE_MODELS),
                "detail": "ok" if online else err,
                "default_model": default,
            }

    async def resolve_model(self, preferred: Optional[str] = None) -> str:
        cfg = self.load()
        provider = self.provider()
        if preferred and preferred.strip():
            return preferred.strip()
        if provider == "openai":
            return (cfg.get("openai_model") or OPENAI_MODELS[0]).strip()
        if provider == "gemini":
            return _normalize_gemini_model(cfg.get("gemini_model"))
        if provider == "grok":
            return (cfg.get("grok_model") or GROK_MODELS[0]).strip()
        if provider == "claude":
            return (cfg.get("claude_model") or CLAUDE_MODELS[0]).strip()
        if cfg.get("ollama_model"):
            return str(cfg["ollama_model"]).strip()
        names = await self.ollama.list_models()
        picked = self.ollama.pick_default_model(names)
        if not picked:
            raise RuntimeError("Ollama'da model yok")
        return picked

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        format_json: bool = False,
        keep_alive: str | int = "5m",
        think: bool = False,
        retries: int = 3,
        num_predict: int = 4096,
        on_progress=None,
    ) -> str:
        provider = self.provider()
        if on_progress:
            try:
                on_progress({"type": "status", "text": f"{provider} yanıt hazırlıyor…"})
            except Exception:
                pass
        if provider == "openai":
            return await self._openai_chat(
                model, messages, temperature=temperature, format_json=format_json,
                num_predict=num_predict, retries=retries,
            )
        if provider == "gemini":
            return await self._gemini_chat(
                model, messages, temperature=temperature, format_json=format_json,
                num_predict=num_predict, retries=retries, on_progress=on_progress,
            )
        if provider == "grok":
            return await self._grok_chat(
                model, messages, temperature=temperature, format_json=format_json,
                num_predict=num_predict, retries=retries,
            )
        if provider == "claude":
            return await self._claude_chat(
                model, messages, temperature=temperature, format_json=format_json,
                num_predict=num_predict, retries=retries,
            )
        return await self.ollama.chat(
            model, messages, temperature=temperature, format_json=format_json,
            keep_alive=keep_alive, think=think, retries=retries, num_predict=num_predict,
        )

    async def unload_for_production(self) -> list[str]:
        if self.provider() != "ollama":
            return []
        return await self.ollama.unload_all()

    # ── OpenAI ─────────────────────────────────────────────────────

    async def _openai_list_models(self, key: str) -> list[str]:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
            if r.status_code >= 400:
                raise RuntimeError(self._http_err(r))
            data = r.json()
        out = []
        for m in data.get("data") or []:
            mid = m.get("id") or ""
            if mid.startswith(("gpt-", "o1", "o3", "o4")):
                out.append(mid)
        prefer = [n for n in OPENAI_MODELS if n in out]
        rest = sorted(n for n in out if n not in prefer)
        return prefer + rest or list(OPENAI_MODELS)

    async def _openai_chat(
        self, model, messages, *, temperature, format_json, num_predict, retries
    ) -> str:
        cfg = self.load()
        key = (cfg.get("openai_api_key") or "").strip()
        if not key:
            raise RuntimeError("OpenAI API key yok — Ayarlar’dan ekle")
        return await self._openai_compat_chat(
            base_url="https://api.openai.com/v1",
            key=key,
            model=model or cfg.get("openai_model") or OPENAI_MODELS[0],
            messages=messages,
            temperature=temperature,
            format_json=format_json,
            num_predict=num_predict,
            retries=retries,
            label="OpenAI",
        )

    async def _openai_compat_chat(
        self,
        *,
        base_url: str,
        key: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        format_json: bool,
        num_predict: int,
        retries: int,
        label: str,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": m.get("role") or "user", "content": m.get("content") or ""}
                for m in messages
                if m.get("content")
            ],
            "temperature": temperature,
            "max_tokens": max(512, min(int(num_predict), 8192)),
            "stream": False,
        }
        if format_json:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            **(extra_headers or {}),
        }
        last_err: Exception | None = None
        for attempt in range(max(1, retries)):
            try:
                async with httpx.AsyncClient(timeout=180.0) as c:
                    r = await c.post(
                        f"{base_url.rstrip('/')}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    if r.status_code >= 400:
                        raise RuntimeError(self._http_err(r))
                    data = r.json()
                choices = data.get("choices") or []
                if choices:
                    msg = choices[0].get("message") or {}
                    text = (msg.get("content") or "").strip()
                    if text:
                        return text
                last_err = RuntimeError(f"{label} boş yanıt")
            except Exception as e:
                last_err = e
            payload["temperature"] = max(0.2, temperature - 0.15 * (attempt + 1))
        raise RuntimeError(f"{label} chat başarısız: {last_err}")

    # ── Gemini ─────────────────────────────────────────────────────

    async def _gemini_list_models(self, key: str) -> list[str]:
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(url, params={"key": key})
            if r.status_code >= 400:
                raise RuntimeError(self._http_err(r))
            data = r.json()
        out: list[str] = []
        for m in data.get("models") or []:
            name = (m.get("name") or "").replace("models/", "")
            methods = m.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            low = name.lower()
            if "embed" in low or "image" in low or "tts" in low:
                continue
            if "gemini" in low:
                out.append(name)
        prefer = [n for n in GEMINI_MODELS if n in out]
        rest = [n for n in out if n not in prefer]
        return prefer + rest

    async def _gemini_chat(
        self,
        model,
        messages,
        *,
        temperature,
        format_json,
        num_predict,
        retries,
        on_progress=None,
    ) -> str:
        cfg = self.load()
        key = (cfg.get("gemini_api_key") or "").strip()
        if not key:
            raise RuntimeError("Gemini API key yok — Ayarlar’dan ekle")
        model = _normalize_gemini_model(model or cfg.get("gemini_model"))
        system_bits = [
            m["content"]
            for m in messages
            if m.get("role") == "system" and m.get("content")
        ]
        contents: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role") or "user"
            text = (m.get("content") or "").strip()
            if not text or role == "system":
                continue
            grole = "model" if role == "assistant" else "user"
            if contents and contents[-1]["role"] == grole:
                contents[-1]["parts"][0]["text"] += "\n\n" + text
            else:
                contents.append({"role": grole, "parts": [{"text": text}]})
        if not contents:
            contents = [{"role": "user", "parts": [{"text": "Merhaba"}]}]
        if contents[0]["role"] != "user":
            contents.insert(0, {"role": "user", "parts": [{"text": "(devam)"}]})

        gen_cfg: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max(512, min(int(num_predict), 8192)),
            # Show thought summaries while waiting (Gemini 2.5+ / 3.x)
            "thinkingConfig": {"includeThoughts": True},
        }
        if format_json:
            gen_cfg["responseMimeType"] = "application/json"

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": gen_cfg,
        }
        if system_bits:
            payload["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_bits)}]
            }

        # Try preferred model, then newer defaults if Google returns "no longer available"
        candidates: list[str] = []
        for m in (model, *GEMINI_MODELS):
            m = _normalize_gemini_model(m)
            if m and m not in candidates:
                candidates.append(m)

        def _prog(ev: dict[str, Any]) -> None:
            if not on_progress:
                return
            try:
                on_progress(ev)
            except Exception:
                pass

        last_err: Exception | None = None
        for cand in candidates:
            for attempt in range(max(1, retries)):
                try:
                    _prog({"type": "status", "text": f"Gemini · {cand} düşünüyor…"})
                    text = await self._gemini_stream_once(
                        key, cand, payload, on_progress=on_progress
                    )
                    if text:
                        if cand != model:
                            try:
                                self.save({"gemini_model": cand})
                            except Exception:
                                pass
                        return text
                    last_err = RuntimeError("Gemini boş yanıt")
                except Exception as e:
                    last_err = e
                    msg = str(e).lower()
                    if "no longer available" in msg or "http 404" in msg:
                        break
                    # Some models reject thinkingConfig — retry without it once
                    if "thinking" in msg and "thinkingConfig" in payload.get(
                        "generationConfig", {}
                    ):
                        payload["generationConfig"].pop("thinkingConfig", None)
                        continue
                    payload["generationConfig"]["temperature"] = max(
                        0.2, temperature - 0.15 * (attempt + 1)
                    )
        raise RuntimeError(f"Gemini chat başarısız: {last_err}")

    async def _gemini_stream_once(
        self, key: str, model: str, payload: dict[str, Any], *, on_progress=None
    ) -> str:
        """streamGenerateContent — emit thought deltas via on_progress, return answer text."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:streamGenerateContent"
        )
        answer_parts: list[str] = []
        thought_buf = ""
        async with httpx.AsyncClient(timeout=180.0) as c:
            async with c.stream(
                "POST",
                url,
                params={"key": key, "alt": "sse"},
                json=payload,
            ) as r:
                if r.status_code >= 400:
                    body = (await r.aread()).decode("utf-8", errors="replace")
                    raise RuntimeError(self._http_err_raw(r.status_code, body))
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                    elif line.startswith("{"):
                        raw = line.strip()
                    else:
                        continue
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    if data.get("error"):
                        raise RuntimeError(
                            data["error"].get("message")
                            or json.dumps(data["error"])[:200]
                        )
                    thought, answer = self._gemini_chunk_parts(data)
                    if thought:
                        thought_buf += thought
                        if on_progress:
                            try:
                                on_progress(
                                    {
                                        "type": "thinking",
                                        "text": thought,
                                        "full": thought_buf[-1200:],
                                    }
                                )
                            except Exception:
                                pass
                    if answer:
                        answer_parts.append(answer)
                        if on_progress:
                            try:
                                on_progress({"type": "answer", "text": answer})
                            except Exception:
                                pass
        text = "".join(answer_parts).strip()
        if text:
            return text
        # No answer parts — let caller retry / fallback (don't leak raw thoughts as reply)
        return ""

    @staticmethod
    def _http_err_raw(status: int, body: str) -> str:
        try:
            data = json.loads(body)
            msg = (data.get("error") or {}).get("message") or body
        except Exception:
            msg = body
        return f"http {status}: {str(msg)[:400]}"

    @staticmethod
    def _gemini_chunk_parts(data: dict[str, Any]) -> tuple[str, str]:
        thought = ""
        answer = ""
        for cand in data.get("candidates") or []:
            parts = ((cand.get("content") or {}).get("parts")) or []
            for p in parts:
                t = (p.get("text") or "").strip()
                if not t:
                    continue
                if p.get("thought"):
                    thought += t
                else:
                    answer += t
        return thought, answer

    @staticmethod
    def _gemini_extract_text(data: dict[str, Any]) -> str:
        cands = data.get("candidates") or []
        if not cands:
            pf = data.get("promptFeedback") or {}
            br = pf.get("blockReason") or data.get("error", {}).get("message")
            if br:
                raise RuntimeError(f"Gemini engelledi: {br}")
            return ""
        parts = ((cands[0].get("content") or {}).get("parts")) or []
        # Prefer non-thought parts (final answer); fall back to any text
        chunks = [p.get("text") for p in parts if p.get("text") and not p.get("thought")]
        if not chunks:
            chunks = [p.get("text") for p in parts if p.get("text")]
        return "\n".join(chunks).strip()

    # ── Grok ───────────────────────────────────────────────────────

    async def _grok_list_models(self, key: str) -> list[str]:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(
                "https://api.x.ai/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
            if r.status_code >= 400:
                raise RuntimeError(self._http_err(r))
            data = r.json()
        out = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        prefer = [n for n in GROK_MODELS if n in out]
        rest = [n for n in out if n not in prefer]
        return prefer + rest or list(GROK_MODELS)

    async def _grok_chat(
        self, model, messages, *, temperature, format_json, num_predict, retries
    ) -> str:
        cfg = self.load()
        key = (cfg.get("grok_api_key") or "").strip()
        if not key:
            raise RuntimeError("Grok (xAI) API key yok — Ayarlar’dan ekle")
        return await self._openai_compat_chat(
            base_url="https://api.x.ai/v1",
            key=key,
            model=model or cfg.get("grok_model") or GROK_MODELS[0],
            messages=messages,
            temperature=temperature,
            format_json=format_json,
            num_predict=num_predict,
            retries=retries,
            label="Grok",
        )

    # ── Claude (Anthropic) ─────────────────────────────────────────

    async def _claude_ping(self, key: str) -> None:
        """Tiny messages call to validate key (1 token)."""
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CLAUDE_MODELS[1],
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
            if r.status_code in (401, 403):
                raise RuntimeError(self._http_err(r))
            # 400/429 still means key is recognized
            if r.status_code >= 500:
                raise RuntimeError(self._http_err(r))

    async def _claude_chat(
        self, model, messages, *, temperature, format_json, num_predict, retries
    ) -> str:
        cfg = self.load()
        key = (cfg.get("claude_api_key") or "").strip()
        if not key:
            raise RuntimeError("Claude API key yok — Ayarlar’dan ekle")
        model = model or cfg.get("claude_model") or CLAUDE_MODELS[0]
        system = "\n\n".join(
            m["content"]
            for m in messages
            if m.get("role") == "system" and m.get("content")
        )
        contents = []
        for m in messages:
            role = m.get("role") or "user"
            text = (m.get("content") or "").strip()
            if not text or role == "system":
                continue
            crole = "assistant" if role == "assistant" else "user"
            if format_json and crole == "user" and m is messages[-1]:
                text += "\n\nRespond with valid JSON only."
            if contents and contents[-1]["role"] == crole:
                contents[-1]["content"] += "\n\n" + text
            else:
                contents.append({"role": crole, "content": text})
        if not contents:
            contents = [{"role": "user", "content": "Merhaba"}]
        if contents[0]["role"] != "user":
            contents.insert(0, {"role": "user", "content": "(devam)"})

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max(512, min(int(num_predict), 8192)),
            "temperature": temperature,
            "messages": contents,
        }
        if system:
            payload["system"] = system

        last_err: Exception | None = None
        for attempt in range(max(1, retries)):
            try:
                async with httpx.AsyncClient(timeout=180.0) as c:
                    r = await c.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json=payload,
                    )
                    if r.status_code >= 400:
                        raise RuntimeError(self._http_err(r))
                    data = r.json()
                parts = data.get("content") or []
                text = "".join(
                    p.get("text", "") for p in parts if p.get("type") == "text"
                ).strip()
                if text:
                    return text
                last_err = RuntimeError("Claude boş yanıt")
            except Exception as e:
                last_err = e
            payload["temperature"] = max(0.2, temperature - 0.15 * (attempt + 1))
        raise RuntimeError(f"Claude chat başarısız: {last_err}")

    @staticmethod
    def _http_err(r: httpx.Response) -> str:
        try:
            data = r.json()
            err = data.get("error")
            if isinstance(err, dict):
                return f"http {r.status_code}: {err.get('message') or err}"[:400]
            if isinstance(err, str):
                return f"http {r.status_code}: {err}"[:400]
            return f"http {r.status_code}: {str(data)[:300]}"
        except Exception:
            return f"http {r.status_code}: {(r.text or '')[:300]}"
