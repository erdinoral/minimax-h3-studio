"""Explicit shot references and portable film outlines. No runtime data is changed here."""
from __future__ import annotations
import copy
import hashlib
import json
import re
import uuid

KINDS = ("characters", "creatures", "locations")


def clean_shot(raw):
    out = {k: str(raw.get(k) or "") for k in ("chapter", "scene", "selected_job", "approved_signature", "first_frame_name")}
    out["review"] = raw.get("review") if raw.get("review") in ("draft", "producing", "review", "approved") else "draft"
    if "bindings" in raw:
        out["bindings"] = [copy.deepcopy(b) for b in raw.get("bindings", []) if isinstance(b, dict)]
    return out


def signature(shot):
    data = {k: shot.get(k) for k in ("text", "mode", "bindings", "chapter", "scene", "first_frame_name")}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def resolve(shot, lib, exists):
    """Resolve ONLY explicit selections; snapshots keep historical refs stable."""
    assets = {str(a.get("id")): {**a, "kind": k[:-1]} for k in KINDS for a in lib.get(k, [])}
    refs, rows, hits, errors = [], [], [], []
    identities = set()
    owners = {}
    for binding in shot.get("bindings", []):
        aid = str(binding.get("asset_id") or "")
        asset = assets.get(aid)
        if not asset:
            errors.append("Seçili varlık artık projede yok: " + aid)
            continue
        snap = binding.get("snapshot")
        frozen = isinstance(snap, dict) and snap.get("id") == aid
        asset = copy.deepcopy(snap if frozen else asset)
        identity = str(asset.get("identity_id") or aid)
        if identity in identities:
            errors.append("Aynı kimliğin iki görünümü seçili: " + asset.get("name", aid))
        identities.add(identity)
        images = asset.get("images") or ([{"file": asset["image"]}] if asset.get("image") else [])
        files = binding.get("files")
        if files is not None:
            images = [im for im in images if im.get("file") in files]
        if not images:
            errors.append(asset.get("name", aid) + ": referans görseli seçilmeli")
        parent = asset.get("identity_reference") or assets.get(identity)
        if identity != aid:
            portrait = (parent or {}).get("images") or []
            if not portrait:
                errors.append(asset.get("name", aid) + ": ana kimliğin yüz referansı eksik")
            else:
                images = [{**portrait[0], "reference_role": "face only; identity reference sheet — not the filmed frame; ignore clothing; never show collage panels"},
                          *[{**im, "reference_role": "wardrobe and body appearance only; appearance reference — not the filmed frame; use the separate identity face; never paste sheet layout"} for im in images]]
        hits.append(asset)
        for im in images:
            file = str(im.get("file") or "")
            if not exists(file):
                errors.append(asset.get("name", aid) + ": görsel bulunamadı — " + file)
            if file in owners and owners[file] != aid:
                errors.append("Aynı görsel farklı varlıklara atanmış: " + file)
            owners[file] = aid
            if file and file not in refs:
                refs.append(file)
                rows.append({**im, "asset": asset})
    if len(refs) > 9:
        errors.append("Bu çekimde en fazla 9 referans kullanılabilir; seçimi azaltın.")
    first = str(shot.get("first_frame_name") or "")
    if first and not exists(first):
        errors.append("Onaylı başlangıç karesi bulunamadı; yeniden yükleyin.")
    if first and len(refs) > 8:
        errors.append("Başlangıç karesiyle birlikte en fazla 8 varlık referansı kullanılabilir.")
    return {"ref_images": refs, "rows": rows, "hits": hits, "errors": errors,
            "first_frame_name": first,
            **{"has_" + k[:-1]: any(a.get("kind") == k[:-1] for a in hits) for k in KINDS}}


def freeze(shot, lib):
    assets = {str(a.get("id")): {**a, "kind": k[:-1]} for k in KINDS for a in lib.get(k, [])}
    for b in shot.get("bindings", []):
        a = assets.get(str(b.get("asset_id")))
        if a and a.get("images") and not b.get("snapshot"):
            b["snapshot"] = copy.deepcopy(a)
            parent = assets.get(str(a.get("identity_id")))
            if parent and parent.get("id") != a.get("id"):
                b["snapshot"]["identity_reference"] = copy.deepcopy(parent)
    return shot


def continuity(shots):
    out = copy.deepcopy(shots)
    prev = None
    for s in out:
        if "bindings" in s:
            key = lambda x: sorted((str(b.get("asset_id")), tuple(b.get("files") or [])) for b in x.get("bindings", []))
            changed = prev is None or "bindings" not in prev or key(s) != key(prev) or s.get("chapter") != prev.get("chapter") or s.get("scene") != prev.get("scene")
            if changed and s.get("mode") == "continue":
                s["mode"] = "t2v"
                s["continuity_note"] = "Referans, görünüm veya sahne değişti; yeni çekim kullanılacak."
        prev = s
    return out


def parse_markdown(text):
    """Parse an outline as data, never execute document instructions."""
    assets = {k: [] for k in KINDS}
    section, chapter, current = "", "Bölüm 1", None
    shots = []
    title = "İçe aktarılan film"
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        if re.match(r"###\s+(Characters|Karakterler)", line, re.I): section = "characters"
        elif re.match(r"###\s+(Places|Locations|Mekanlar|Mekânlar)", line, re.I): section = "locations"
        elif re.match(r"###\s+(Creatures|Yaratıklar)", line, re.I): section = "creatures"
        elif re.match(r"###\s+(PART|BÖLÜM)\s+\d+", line, re.I):
            chapter, section = line.lstrip("# ").strip(), ""
        m = re.match(r"\s*[*-]\s+\*\*(.+?)\*\*\s*[—–-]\s*(.+)", line)
        if section and m:
            name, notes = m.groups()
            kind = "creatures" if section == "characters" and re.search(r"\bdragon\b", notes, re.I) else section
            assets[kind].append({"id": uuid.uuid4().hex, "name": name, "notes": notes, "kind": kind[:-1], "images": []})
        m = re.match(r"\s*[*-]\s+\*\*(?:Shot|Çekim)\s+(\d+)\*\*", line, re.I)
        if m:
            current = {"id": uuid.uuid4().hex, "chapter": chapter, "scene": "", "text": "", "mode": "t2v", "bindings": [], "review": "draft", "_names": []}
            shots.append(current)
        m = re.match(r"\s*[*-]\s+(mode|cast|place|action):\s*(.*)", line, re.I)
        if current is not None and m:
            key, value = m.groups()
            if key.lower() == "mode": current["mode"] = "continue" if value == "continue" else "t2v"
            elif key.lower() == "action": current["text"] = value
            else:
                current["_names"].extend(n.strip() for n in value.split(",") if n.strip() not in ("—", "-"))
                if key.lower() == "place": current["scene"] = value
    by_name = {a["name"].casefold(): a for k in KINDS for a in assets[k]}
    warnings = []
    for a in assets["characters"]:
        # Link an explicitly stated shared identity; do not merge unrelated names.
        m = re.search(r"Same face/identity as (.+?)\.", a["notes"], re.I)
        parent = by_name.get(m.group(1).casefold()) if m else None
        a["identity_id"] = parent["id"] if parent else a["id"]
        a["appearance"] = a["name"] if parent else "Ana görünüm"
    for s in shots:
        for name in s.pop("_names"):
            a = by_name.get(name.casefold())
            if a: s["bindings"].append({"asset_id": a["id"]})
            else: warnings.append("Kart bulunamadı: " + name)
    if not shots: raise ValueError("Çekim bulunamadı. **Shot 1** ve mode/cast/place/action alanları bekleniyor.")
    return {"title": title, **assets, "shots": shots, "warnings": list(dict.fromkeys(warnings))}
