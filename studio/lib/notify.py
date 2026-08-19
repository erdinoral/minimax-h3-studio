"""Phone / Telegram notifications for H3 Studio production events.

Primary: Telegram bot (same setup as AkiFactory data/telegram.json).
Optional: ntfy.sh topic push.
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any, Optional

import httpx

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "provider": "telegram",  # telegram | ntfy
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "telegram_bot_username": "",
    "ntfy_server": "https://ntfy.sh",
    "ntfy_topic": "",
    "on_batch_done": True,
    "on_each_clip": False,
    "on_error": True,
    "akifactory_path": "",  # optional override to telegram.json
}

# Common AkiFactory locations on this machine
_AKIFACTORY_TELEGRAM_CANDIDATES = (
    Path(r"C:\Users\ERDIN\Desktop\AkiFactory\data\telegram.json"),
    Path.home() / "Desktop" / "AkiFactory" / "data" / "telegram.json",
    Path.home() / "OneDrive" / "Desktop" / "AkiFactory" / "data" / "telegram.json",
)


def default_topic() -> str:
    return "h3-" + secrets.token_urlsafe(8).lower().replace("_", "").replace("-", "")[:14]


def _mask_token(token: str) -> str:
    t = (token or "").strip()
    if not t:
        return ""
    if len(t) <= 12:
        return "••••"
    return f"{t[:6]}…{t[-4:]}"


class NotifyService:
    def __init__(self, path: Path):
        self.path = path
        self._cfg = self.load()

    def load(self) -> dict[str, Any]:
        cfg = dict(DEFAULTS)
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for k in DEFAULTS:
                        if k in raw:
                            cfg[k] = raw[k]
        except Exception:
            pass
        # First run: pull AkiFactory telegram.json if we have no token yet
        if not (cfg.get("telegram_bot_token") or "").strip():
            imported = self._read_akifactory_telegram(cfg.get("akifactory_path") or "")
            if imported:
                cfg["telegram_bot_token"] = imported.get("bot_token") or ""
                cfg["telegram_chat_id"] = str(imported.get("chat_id") or "")
                cfg["telegram_bot_username"] = imported.get("bot_username") or ""
                cfg["provider"] = "telegram"
                if imported.get("enabled") is not None:
                    cfg["enabled"] = bool(imported.get("enabled"))
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self.path.write_text(
                        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                except Exception:
                    pass
        if not (cfg.get("ntfy_topic") or "").strip():
            cfg["ntfy_topic"] = default_topic()
        self._cfg = cfg
        return cfg

    def _read_akifactory_telegram(self, override: str = "") -> Optional[dict[str, Any]]:
        paths: list[Path] = []
        if override:
            p = Path(override)
            paths.append(p if p.name.endswith(".json") else p / "data" / "telegram.json")
        env = (os.environ.get("AKIFACTORY_TELEGRAM_JSON") or "").strip()
        if env:
            paths.append(Path(env))
        paths.extend(_AKIFACTORY_TELEGRAM_CANDIDATES)
        for p in paths:
            try:
                if not p.is_file():
                    continue
                raw = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and (raw.get("bot_token") or "").strip():
                    return raw
            except Exception:
                continue
        return None

    def import_akifactory(self, path: str = "") -> dict[str, Any]:
        imported = self._read_akifactory_telegram(path)
        if not imported:
            raise FileNotFoundError(
                "AkiFactory telegram.json bulunamadı — yolu kontrol et"
            )
        return self.save(
            {
                "enabled": True,
                "provider": "telegram",
                "telegram_bot_token": (imported.get("bot_token") or "").strip(),
                "telegram_chat_id": str(imported.get("chat_id") or "").strip(),
                "telegram_bot_username": (imported.get("bot_username") or "").strip(),
                "akifactory_path": path or str(
                    next(
                        (
                            c
                            for c in _AKIFACTORY_TELEGRAM_CANDIDATES
                            if c.is_file()
                        ),
                        "",
                    )
                ),
            }
        )

    def save(self, patch: dict[str, Any]) -> dict[str, Any]:
        cfg = self.load()
        for k, v in patch.items():
            if k not in DEFAULTS:
                continue
            if k in ("enabled", "on_batch_done", "on_each_clip", "on_error"):
                cfg[k] = bool(v)
            elif k == "telegram_bot_token":
                # keep existing if UI sent blank / mask
                s = ("" if v is None else str(v)).strip()
                if s and s not in ("••••", "__keep__", "keep"):
                    cfg[k] = s
            elif isinstance(v, str):
                cfg[k] = v.strip()
            else:
                cfg[k] = v
        if not (cfg.get("ntfy_topic") or "").strip():
            cfg["ntfy_topic"] = default_topic()
        server = (cfg.get("ntfy_server") or "https://ntfy.sh").rstrip("/")
        if not server.startswith("http"):
            server = "https://" + server
        cfg["ntfy_server"] = server
        prov = (cfg.get("provider") or "telegram").lower()
        if prov not in ("telegram", "ntfy"):
            prov = "telegram"
        cfg["provider"] = prov
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._cfg = cfg
        return cfg

    def public(self) -> dict[str, Any]:
        cfg = self.load()
        token = (cfg.get("telegram_bot_token") or "").strip()
        chat = str(cfg.get("telegram_chat_id") or "").strip()
        topic = (cfg.get("ntfy_topic") or "").strip()
        server = (cfg.get("ntfy_server") or "https://ntfy.sh").rstrip("/")
        bot_user = (cfg.get("telegram_bot_username") or "").strip().lstrip("@")
        return {
            "enabled": bool(cfg.get("enabled")),
            "provider": cfg.get("provider") or "telegram",
            "telegram_configured": bool(token and chat),
            "telegram_bot_token_set": bool(token),
            "telegram_bot_token_masked": _mask_token(token),
            "telegram_chat_id": chat,
            "telegram_bot_username": bot_user,
            "telegram_bot_link": f"https://t.me/{bot_user}" if bot_user else "",
            "ntfy_server": server,
            "ntfy_topic": topic,
            "subscribe_url": f"{server}/{topic}" if topic else "",
            "on_batch_done": bool(cfg.get("on_batch_done", True)),
            "on_each_clip": bool(cfg.get("on_each_clip")),
            "on_error": bool(cfg.get("on_error", True)),
            "akifactory_path": cfg.get("akifactory_path") or "",
            "hint": (
                "AkiFactory Telegram botu ile üretim bitince mesaj gelir. "
                "İstersen Ayarlar’dan AkiFactory’den aktar."
            ),
        }

    async def send(
        self,
        title: str,
        message: str,
        *,
        priority: int = 3,
        tags: Optional[str] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        cfg = self.load()
        if not force and not cfg.get("enabled"):
            return {"ok": False, "detail": "disabled"}
        prov = (cfg.get("provider") or "telegram").lower()
        if prov == "telegram":
            return await self._send_telegram(title, message, force=force)
        return await self._send_ntfy(title, message, priority=priority, tags=tags, force=force)

    async def _send_telegram(
        self, title: str, message: str, *, force: bool = False
    ) -> dict[str, Any]:
        cfg = self.load()
        if not force and not cfg.get("enabled"):
            return {"ok": False, "detail": "disabled"}
        token = (cfg.get("telegram_bot_token") or "").strip()
        chat_id = str(cfg.get("telegram_chat_id") or "").strip()
        if not token:
            return {"ok": False, "detail": "telegram_bot_token yok"}
        if not chat_id:
            return {"ok": False, "detail": "telegram_chat_id yok — bota /start yaz"}
        text = f"{(title or 'H3 Studio').strip()}\n\n{(message or '').strip()}".strip()[:3900]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "disable_web_page_preview": True,
                    },
                )
            data = r.json() if r.content else {}
            if r.status_code >= 400 or not data.get("ok"):
                desc = (data.get("description") if isinstance(data, dict) else None) or r.text
                return {"ok": False, "detail": str(desc)[:200]}
            return {"ok": True, "detail": "telegram_sent"}
        except Exception as e:
            return {"ok": False, "detail": str(e)[:200]}

    async def _send_ntfy(
        self,
        title: str,
        message: str,
        *,
        priority: int = 3,
        tags: Optional[str] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        cfg = self.load()
        if not force and not cfg.get("enabled"):
            return {"ok": False, "detail": "disabled"}
        topic = (cfg.get("ntfy_topic") or "").strip()
        if not topic:
            return {"ok": False, "detail": "topic_missing"}
        server = (cfg.get("ntfy_server") or "https://ntfy.sh").rstrip("/")
        url = f"{server}/{topic}"
        headers = {
            "Title": (title or "H3 Studio")[:120],
            "Priority": str(max(1, min(5, int(priority)))),
        }
        if tags:
            headers["Tags"] = tags
        try:
            async with httpx.AsyncClient(timeout=12.0) as c:
                r = await c.post(url, content=(message or "").encode("utf-8"), headers=headers)
            if r.status_code >= 400:
                return {"ok": False, "detail": f"http {r.status_code}: {r.text[:160]}"}
            return {"ok": True, "detail": "ntfy_sent"}
        except Exception as e:
            return {"ok": False, "detail": str(e)[:200]}

    async def notify_job_event(
        self, job: dict[str, Any], event: str, *, jobs: Optional[list] = None
    ) -> None:
        """event: done | error — respects settings; batch-complete preferred."""
        cfg = self.load()
        if not cfg.get("enabled"):
            return
        status = (event or "").lower()
        bi = int(job.get("batch_index") or 0)
        bt = int(job.get("batch_total") or 0)
        dur = job.get("duration")
        res = ""
        if job.get("width") and job.get("height"):
            res = f"{job['width']}×{job['height']}"

        if status == "error":
            if not cfg.get("on_error"):
                return
            err = str(job.get("error") or "bilinmeyen hata")[:180]
            title = "H3 · üretim hatası"
            if bi and bt:
                title = f"H3 · hata {bi}/{bt}"
            await self.send(title, err, priority=4, tags="warning,video_camera")
            return

        if status != "done":
            return

        batch_complete = False
        if bi > 0 and bt > 0 and jobs is not None:
            same = [
                j
                for j in jobs
                if int(j.get("batch_total") or 0) == bt
                and int(j.get("batch_index") or 0) > 0
            ]
            if same:
                done_n = sum(1 for j in same if j.get("status") == "done")
                active = sum(
                    1 for j in same if j.get("status") in ("queued", "running")
                )
                batch_complete = done_n >= bt or (done_n > 0 and active == 0 and bi >= bt)

        prod_idle = False
        if jobs is not None:
            prod_idle = not any(
                j.get("status") in ("queued", "running") for j in jobs
            )

        if batch_complete and cfg.get("on_batch_done"):
            await self.send(
                f"H3 · seri bitti ({bt} shot)",
                f"Tüm klipler hazır"
                + (f" · {res}" if res else "")
                + (f" · {dur}sn/klip" if dur else ""),
                priority=4,
                tags="white_check_mark,movie_camera",
            )
            return

        if prod_idle and cfg.get("on_batch_done") and not (bi and bt and bi < bt):
            await self.send(
                "H3 · üretim bitti",
                f"Kuyruk boş"
                + (f" · son klip {res}" if res else "")
                + (f" · {dur}sn" if dur else ""),
                priority=4,
                tags="white_check_mark,movie_camera",
            )
            return

        if cfg.get("on_each_clip"):
            title = "H3 · klip hazır"
            if bi and bt:
                title = f"H3 · klip {bi}/{bt} hazır"
            await self.send(
                title,
                (f"{res} · {dur}sn" if res or dur else "Video kaydedildi"),
                priority=3,
                tags="movie_camera",
            )
