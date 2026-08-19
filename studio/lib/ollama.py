"""Ollama HTTP client for H3 Studio Director."""
from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Optional

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_URL):
        self.base_url = base_url

    async def healthy(self) -> bool:
        """True if Ollama HTTP API answers.

        Cold start / first /api/tags can take several seconds on Windows —
        keep timeout generous so a slow but running serve is not marked offline.
        """
        try:
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def probe(self) -> dict[str, Any]:
        """Health + short diagnostic for UI (online / refused / timeout / error)."""
        try:
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(f"{self.base_url}/api/tags")
                if r.status_code == 200:
                    models = r.json().get("models") or []
                    names = [m.get("name") for m in models if m.get("name")]
                    return {
                        "online": True,
                        "models": names,
                        "detail": "ok",
                    }
                return {
                    "online": False,
                    "models": [],
                    "detail": f"http {r.status_code}",
                }
        except httpx.ConnectError:
            return {
                "online": False,
                "models": [],
                "detail": "connect_refused",
            }
        except httpx.TimeoutException:
            return {
                "online": False,
                "models": [],
                "detail": "timeout",
            }
        except Exception as e:
            return {
                "online": False,
                "models": [],
                "detail": str(e)[:120],
            }

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=12.0) as c:
            r = await c.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
            models = r.json().get("models") or []
            return [m.get("name") for m in models if m.get("name")]

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
    ) -> str:
        """Chat completion with empty-reply retries.

        Qwen3 / Qwen3.5 thinking models often return content="" and dump the
        whole answer into message.thinking unless think=false is set top-level
        (not inside options). Director needs the visible reply, so default off.
        """
        # Thinking models: always force think off for Director UX
        force_no_think = think is False or self._is_thinking_model(model)
        last_err: Exception | None = None
        content = ""

        for attempt in range(max(1, retries)):
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": False,
                "keep_alive": keep_alive,
                "think": False if force_no_think else think,
                "options": {
                    "temperature": temperature if attempt == 0 else max(0.2, temperature - 0.15 * attempt),
                    "num_predict": num_predict,
                },
            }
            if format_json:
                payload["format"] = "json"
            # On retry 2+, nudge without polluting caller session
            if attempt > 0:
                payload["messages"] = list(messages) + [
                    {
                        "role": "user",
                        "content": (
                            "[sistem] Önceki çıktın boş veya görünmezdi. "
                            "Şimdi Türkçe, kullanıcıya görünen somut bir yönetmen cevabı yaz. "
                            "Asıl cevap content'te olsun; düşünceyi gizleme bahanesi yok. "
                            "En az 2 cümle."
                        ),
                    }
                ]
            try:
                async with httpx.AsyncClient(timeout=180.0) as c:
                    r = await c.post(f"{self.base_url}/api/chat", json=payload)
                    if r.status_code >= 400:
                        raise RuntimeError(r.text[:500])
                    data = r.json()
                    msg = data.get("message") or {}
                    content = (msg.get("content") or "").strip()
                    if not content:
                        thinking = (
                            msg.get("thinking") or msg.get("reasoning") or ""
                        ).strip()
                        if thinking:
                            content = self._extract_answer_from_thinking(thinking)
                    content = self._strip_think_tags(content).strip()
                    if content:
                        return content
            except Exception as e:
                last_err = e
            if attempt + 1 < retries:
                await asyncio.sleep(0.35 * (attempt + 1))

        if last_err and not content:
            raise RuntimeError(f"Ollama chat başarısız: {last_err}")
        return content

    _THINKING_MODELS = {
        "qwen3.5",
        "qwen3:",
        "deepseek-r1",
    }

    @staticmethod
    def _is_thinking_model(model: str) -> bool:
        low = (model or "").lower()
        return any(tm in low for tm in OllamaClient._THINKING_MODELS)

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        if not text:
            return ""
        cleaned = re.sub(
            r"<think>[\s\S]*?</think>",
            "",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"<thinking>[\s\S]*?</thinking>",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        return cleaned.strip()

    @staticmethod
    def _extract_answer_from_thinking(thinking: str) -> str:
        """Best-effort: if content was empty, pull a final answer from thinking."""
        if not thinking:
            return ""
        for pat in (
            r"(?i)final\s+(?:answer|selection|choice|response|reply)\s*[:：]\s*(.+)$",
            r"(?i)(?:yanıt|cevap)\s*[:：]\s*(.+)$",
            r"(?i)decision\s*[:：]\s*(.+)$",
            r"[\"“]([^\"”]{12,})[\"”]\s*$",
        ):
            m = re.search(pat, thinking, flags=re.MULTILINE)
            if m:
                got = m.group(1).strip().strip("*").strip()
                if len(got) >= 8:
                    return got
        # Prefer last markdown / Turkish paragraph that looks like dialogue
        paras = [p.strip() for p in re.split(r"\n\s*\n", thinking) if p.strip()]
        for p in reversed(paras):
            if len(p) < 20:
                continue
            if re.match(
                r"(?i)^(thinking|analyze|determine|draft|option|step|process|wait)",
                p,
            ):
                continue
            if p.startswith(("#", "-", "*", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.")):
                continue
            # Skip pure English meta outlines
            if p.count(" ") < 3 and len(p) < 40:
                continue
            return p[:1200]
        # Last resort: trim the end of the thinking blob
        tail = thinking.strip()[-900:].strip()
        return tail if len(tail) >= 40 else ""

    async def loaded_models(self) -> list[str]:
        """Models currently resident in memory (VRAM/RAM)."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(f"{self.base_url}/api/ps")
                if r.status_code >= 400:
                    return []
                models = r.json().get("models") or []
                names = []
                for m in models:
                    n = m.get("name") or m.get("model")
                    if n:
                        names.append(n)
                return names
        except Exception:
            return []

    async def unload(self, model: str) -> None:
        """Force model out of memory (keep_alive=0)."""
        payload = {"model": model, "prompt": "", "keep_alive": 0, "think": False}
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.post(f"{self.base_url}/api/generate", json=payload)
            if r.status_code >= 400:
                await c.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": model,
                        "messages": [],
                        "keep_alive": 0,
                        "think": False,
                    },
                )

    async def unload_all(self) -> list[str]:
        """Unload every resident model. Returns names that were targeted."""
        names = await self.loaded_models()
        freed: list[str] = []
        for name in names:
            try:
                await self.unload(name)
                freed.append(name)
            except Exception:
                pass
        return freed

    def pick_default_model(self, names: list[str]) -> Optional[str]:
        # Prefer non-thinking / instruct-friendly chat models for Director.
        # qwen3.5 thinking builds can return empty content unless think=false;
        # qwen3:8b is stabler for interview + JSON brief turns.
        prefer = (
            "qwen3:8b",
            "qwen3:4b-instruct",
            "qwen2.5:9b",
            "qwen2.5vl:7b",
            "qwen3:9b",
            "qwen3.5:9b",
            "qwen3.5:latest",
            "qwen2.5:14b",
        )
        for p in prefer:
            if p in names:
                return p
        lower = {n: n.lower() for n in names}
        for n, low in lower.items():
            if "14b" in low:
                continue
            if ":9b" in low or "9b" in low.split(":")[-1] or low.endswith("9b"):
                return n
        for n, low in lower.items():
            if "8b" in low or "7b" in low:
                return n
        return names[0] if names else None
