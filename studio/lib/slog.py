"""H3 Studio diagnostics logger — file + console, easy to tail when queue breaks."""
from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

_LOG_DIR: Optional[Path] = None
_READY = False
_logger = logging.getLogger("h3.studio")


def setup(log_dir: Path, *, level: int = logging.INFO) -> Path:
    """Idempotent setup. Returns log directory."""
    global _LOG_DIR, _READY
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    _LOG_DIR = log_dir

    if _READY:
        return log_dir

    _logger.setLevel(level)
    _logger.handlers.clear()
    _logger.propagate = False

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-5s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    main = RotatingFileHandler(
        log_dir / "studio.log",
        maxBytes=2_000_000,
        backupCount=8,
        encoding="utf-8",
    )
    main.setFormatter(fmt)
    main.setLevel(level)

    # Always-overwrite "latest" convenience pointer (same stream as studio.log tail)
    latest = logging.FileHandler(log_dir / "latest.log", mode="a", encoding="utf-8")
    latest.setFormatter(fmt)
    latest.setLevel(level)

    err = RotatingFileHandler(
        log_dir / "errors.log",
        maxBytes=1_000_000,
        backupCount=4,
        encoding="utf-8",
    )
    err.setFormatter(fmt)
    err.setLevel(logging.WARNING)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(level)

    _logger.addHandler(main)
    _logger.addHandler(latest)
    _logger.addHandler(err)
    _logger.addHandler(console)
    _READY = True
    _logger.info("log sistemi hazır → %s", log_dir)
    return log_dir


def log_dir() -> Optional[Path]:
    return _LOG_DIR


def _fmt(msg: str, **ctx: Any) -> str:
    if not ctx:
        return msg
    bits = []
    for k, v in ctx.items():
        if v is None:
            continue
        s = str(v)
        if len(s) > 160:
            s = s[:157] + "…"
        bits.append(f"{k}={s}")
    return f"{msg} | {' '.join(bits)}" if bits else msg


def info(msg: str, **ctx: Any) -> None:
    _logger.info(_fmt(msg, **ctx))


def warn(msg: str, **ctx: Any) -> None:
    _logger.warning(_fmt(msg, **ctx))


def error(msg: str, **ctx: Any) -> None:
    _logger.error(_fmt(msg, **ctx))


def exception(msg: str, exc: BaseException | None = None, **ctx: Any) -> None:
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _logger.error("%s\n%s", _fmt(msg, **ctx), tb.rstrip())
    else:
        _logger.exception(_fmt(msg, **ctx))


def job_line(job: dict, msg: str, **ctx: Any) -> str:
    ctx = {
        "job": str(job.get("id") or "")[:8],
        "batch": (
            f"{job.get('batch_index')}/{job.get('batch_total')}"
            if job.get("batch_index")
            else None
        ),
        "mode": job.get("mode"),
        "status": job.get("status"),
        **ctx,
    }
    return _fmt(msg, **ctx)


def info_job(job: dict, msg: str, **ctx: Any) -> None:
    _logger.info(job_line(job, msg, **ctx))


def warn_job(job: dict, msg: str, **ctx: Any) -> None:
    _logger.warning(job_line(job, msg, **ctx))


def error_job(job: dict, msg: str, **ctx: Any) -> None:
    _logger.error(job_line(job, msg, **ctx))


def tail(path: Path, lines: int = 200) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"(okunamadı: {e})"
    parts = text.splitlines()
    if lines > 0:
        parts = parts[-lines:]
    return "\n".join(parts)
