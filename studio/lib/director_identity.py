"""Resolve Director visual cast before composing or queuing film prompts."""
import copy
import re
from . import backdrop, cinema


def shot_backdrop(shot):
    return backdrop.normalize((shot.get("structured") or {}).get("backdrop"))


def prepare_shot(shot, lib):
    out = _prepare_cast(shot, lib)
    if shot_backdrop(shot):
        # A keyed shot has no set: location plates would paint one back in.
        locations = {a.get("id") for a in lib.get("locations", [])}
        bindings = out.get("bindings")
        if bindings is None:
            bindings = [{"asset_id":a["id"]} for a in cinema.match_prompt(str(shot.get("text") or ""), lib)]
        out["bindings"] = [b for b in bindings if b.get("asset_id") not in locations]
    return out


def _prepare_cast(shot, lib):
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
            raise ValueError("Scene character not found on the cards: " + name.strip())
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
    text = str(shot.get("text") or "")
    hits = cinema.match_prompt(text, lib)
    selected = {b.get("asset_id") for b in shot.get("bindings") or []}
    actors = [a for a in lib.get("characters", []) if a.get("id") in selected]
    if shot.get("bindings") is None:
        actors = [a for a in hits if a.get("kind") == "character"]
    fields = shot.get("structured") or {}
    speaker = str(fields.get("speaker") or "").strip().casefold()
    speaking_actors = [actor for actor in actors if actor["name"].casefold() == speaker] if speaker else actors
    scoped = {**lib, "characters": speaking_actors}
    tagged_dialogue = bool(re.search(r"<d>\s*\S.*?</d>", text, flags=re.I | re.S))
    authored = bool(fields.get("action") or "dialogue" in fields)
    dialogue_rule = ""
    if not silent and tagged_dialogue:
        dialogue_rule = (
            "DIALOGUE FOR THIS SECTION ONLY: Speak the exact words inside this section's dialogue tags, "
            "once, by the specified speaker. Everyone else stays silent. "
            "No ad-libs, filler words, narration, background voices, or lines carried over from another section."
        )
    elif not silent and authored:
        dialogue_rule = (
            "NO DIALOGUE IN THIS SECTION. Nobody speaks or mouths words. "
            "No whispers, narration, intelligible background voices, or repeated lines from other sections. "
            "Use only non-vocal ambience and Foley appropriate to the scene."
        )
    head = "\n\n".join(part for part in (
        cinema.setup_preamble(lib.get("setup") or {}),
        dialogue_rule,
        "" if silent or (authored and not tagged_dialogue) else cinema.film_audio_preamble(cinema._clean_audio(lib.get("audio"))),
        "" if silent or (authored and not tagged_dialogue) else cinema.cast_voice_bible(scoped),
        ("VISUAL CAST LOCK: " + ", ".join(a["name"] for a in actors)
         + ". Keep each actor's identity separate. Do not transfer facial features, hair, costume or voice between actors."
         if actors else ""),
    ) if part)
    return cinema.apply_look(backdrop.apply(text, shot_backdrop(shot)),head)


def manifest(plan):
    return [{"asset_id":a.get("id"),"name":a.get("name"),"voice":a.get("voice") or "",
             "reference_files":[r["file"] for r in plan.get("rows",[]) if (r.get("asset") or {}).get("id")==a.get("id")]}
            for a in plan.get("hits",[]) if isinstance(a,dict) and a.get("kind")=="character"]
