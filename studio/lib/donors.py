"""Public donor roll: Open Collective + GitHub Sponsors + optional local names."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

STUDIO_ROOT = Path(__file__).resolve().parent.parent
DONORS_FILE = STUDIO_ROOT / "data" / "donors.json"
DEFAULT_SLUG = "minimax-h3-studio"
DEFAULT_GH_LOGIN = "erdinoral"
CACHE_SEC = 900
SKIP = {"guest", "anonymous", "incognito", "deleted", "incognito user"}
_OC_CACHE: dict[str, Any] = {"at": 0.0, "key": "", "names": []}
_GH_CACHE: dict[str, Any] = {"at": 0.0, "key": "", "names": []}

GH_SPONSORS_QUERY = """
query($login: String!) {
  user(login: $login) {
    sponsorshipsAsMaintainer(first: 100, includePrivate: false) {
      nodes {
        sponsorEntity {
          ... on User { login name }
          ... on Organization { login name }
        }
      }
    }
  }
}
"""


def _local_cfg() -> dict[str, Any]:
    cfg = {
        "opencollective_slug": DEFAULT_SLUG,
        "github_login": DEFAULT_GH_LOGIN,
        "names": [],
    }
    if not DONORS_FILE.is_file():
        return cfg
    try:
        raw = json.loads(DONORS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return cfg
    if not isinstance(raw, dict):
        return cfg
    names = [str(x).strip() for x in (raw.get("names") or []) if str(x).strip()]
    slug = str(raw.get("opencollective_slug") or DEFAULT_SLUG).strip() or DEFAULT_SLUG
    login = str(raw.get("github_login") or DEFAULT_GH_LOGIN).strip() or DEFAULT_GH_LOGIN
    return {"opencollective_slug": slug, "github_login": login, "names": names}


def _clean_name(name: str) -> str:
    n = (name or "").strip()
    if not n or n.lower() in SKIP:
        return ""
    return n


def _unique(names: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = _clean_name(raw)
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _github_token() -> str:
    for key in ("GITHUB_TOKEN", "GH_TOKEN", "GH_PAT"):
        tok = str(os.environ.get(key) or "").strip()
        if tok:
            return tok
    gh = shutil.which("gh")
    if not gh:
        return ""
    try:
        proc = subprocess.run(
            [gh, "auth", "token"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except Exception:
        return ""
    return (proc.stdout or "").strip()


async def _fetch_opencollective(slug: str) -> list[str]:
    url = f"https://opencollective.com/{slug}/members.json"
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            res = await client.get(url)
            res.raise_for_status()
            rows = res.json()
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    names: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("role") or "").upper() != "BACKER":
            continue
        try:
            amount = float(row.get("totalAmountDonated") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            continue
        names.append(str(row.get("name") or ""))
    return _unique(names)


def _sponsor_display(entity: dict[str, Any]) -> str:
    return _clean_name(str(entity.get("name") or entity.get("login") or ""))


async def _fetch_github_sponsors(login: str) -> list[str]:
    token = _github_token()
    if not token:
        return []
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.post(
                "https://api.github.com/graphql",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "minimax-h3-studio",
                },
                json={"query": GH_SPONSORS_QUERY, "variables": {"login": login}},
            )
            res.raise_for_status()
            payload = res.json()
    except Exception:
        return []
    user = ((payload or {}).get("data") or {}).get("user") or {}
    nodes = ((user.get("sponsorshipsAsMaintainer") or {}).get("nodes") or [])
    names: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        entity = node.get("sponsorEntity") or {}
        if isinstance(entity, dict):
            names.append(_sponsor_display(entity))
    return _unique(names)


async def _cached_names(cache: dict[str, Any], key: str, fetcher) -> list[str]:
    now = time.time()
    if cache["key"] == key and cache["at"] and now - float(cache["at"]) < CACHE_SEC:
        return list(cache["names"])
    names = await fetcher()
    cache["at"] = now
    cache["key"] = key
    cache["names"] = names
    return names


async def list_donors() -> dict[str, Any]:
    cfg = _local_cfg()
    slug = cfg["opencollective_slug"]
    login = cfg["github_login"]
    oc_names = await _cached_names(_OC_CACHE, slug, lambda: _fetch_opencollective(slug))
    gh_names = await _cached_names(_GH_CACHE, login, lambda: _fetch_github_sponsors(login))
    names = _unique([*cfg["names"], *gh_names, *oc_names])
    return {
        "names": names,
        "opencollective_slug": slug,
        "github_login": login,
        "donate_url": f"https://opencollective.com/{slug}",
        "github_sponsors": f"https://github.com/sponsors/{login}",
    }
