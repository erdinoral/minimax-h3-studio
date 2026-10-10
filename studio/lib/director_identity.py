"""Resolve Director visual cast before composing or queuing film prompts."""
import copy
import re
from . import cinema


def prepare_shot(shot, lib):
    out = copy.deepcopy(shot)
    text = str(shot.get("text") or "")
    cast = str((shot.get("structured") or {}).get("character") or "").strip()
    if not cast:
        match = re.search(r"\bMain characters?\s*:\s*(.*?)(?=\s+Opening composition\s*:|\n|$)", text, re.I)
        cast = match.group(1).strip() if match else ""
    if not cast:
        return out
    assets = [a for group in ("characters", "creatures", "vehicles") for a in lib.get(group, [])]
    by_name = {str(a.get("name") or "").strip().casefold():a for a in assets}
    actors = []
    for name in cast.split(","):
        if not name.strip():
            continue
        actor = by_name.get(name.strip().casefold())
        if not actor:
            raise ValueError("Sahne karakteri kartlarda bulunamadı: " + name.strip())
        if actor["id"] not in {a["id"] for a in actors}:
            actors.append(actor)
    ids = {a["id"] for a in actors}
    character_ids = {a["id"] for a in lib.get("characters", [])}
    bindings = [b for b in out.get("bindings") or []
                if b.get("asset_id") not in character_ids or b.get("asset_id") in ids]
    selected = {b.get("asset_id") for b in bindings}
    bindings.extend({"asset_id":a["id"]} for a in actors if a["id"] not in selected)
    # Previously automatic location/prop references remain automatic when the
    # shot had no explicit selection; character selection is now deterministic.
    if shot.get("bindings") is None:
        selected = {b.get("asset_id") for b in bindings}
        bindings.extend({"asset_id":a["id"]} for a in cinema.match_prompt(text,lib)
                        if a.get("kind") != "character" and a["id"] not in selected)
    out["bindings"] = bindings
    return out


def prompt_for_shot(shot, lib, silent=False):
    hits = cinema.match_prompt(str(shot.get("text") or ""), lib)
    selected = {b.get("asset_id") for b in shot.get("bindings") or []}
    actors = [a for a in lib.get("characters", []) if a.get("id") in selected]
    if shot.get("bindings") is None:
        actors = [a for a in hits if a.get("kind") == "character"]
    scoped = {**lib,"characters":actors}
    head = "\n\n".join(part for part in (
        cinema.setup_preamble(lib.get("setup") or {}),
        "" if silent else cinema.film_audio_preamble(cinema._clean_audio(lib.get("audio"))),
        "" if silent else cinema.cast_voice_bible(scoped),
        ("VISUAL CAST LOCK: " + ", ".join(a["name"] for a in actors)
         + ". Keep each actor's identity separate. Do not transfer facial features, hair, costume or voice between actors."
         if actors else ""),
    ) if part)
    return cinema.apply_look(str(shot.get("text") or ""),head)


def manifest(plan):
    return [{"asset_id":a.get("id"),"name":a.get("name"),"voice":a.get("voice") or "",
             "use_lora":cinema.uses_lora(a),"lora_id":a.get("lora_id") if cinema.uses_lora(a) else "",
             "lora_strength":a.get("lora_strength") if cinema.uses_lora(a) else None,
             "reference_files":[r["file"] for r in plan.get("rows",[]) if (r.get("asset") or {}).get("id")==a.get("id")]}
            for a in plan.get("hits",[]) if isinstance(a,dict) and a.get("kind")=="character"]
