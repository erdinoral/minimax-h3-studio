"""One ordered reference plan shared by Scene and Director."""
from pathlib import Path
import re
from . import cinema, film_project


def resolve(text, bindings, lib, exists, existing=(), continuation=False):
    if bindings is not None:
        result = film_project.resolve({"bindings": bindings}, lib, exists)
        if result["errors"]:
            raise ValueError("; ".join(result["errors"]))
        hits, rows = result["hits"], result["rows"]
    else:
        hits = cinema.match_prompt(text, lib)
        rows = [{**im, "asset": asset} for asset in hits
                for im in cinema.mentioned_images(text, asset) if not cinema.uses_lora(asset)]
        missing = [a.get("name", "Asset") for a in hits if not cinema.uses_lora(a) and not cinema.mentioned_images(text, a)]
        if missing:
            raise ValueError("Referans görseli eksik: " + ", ".join(missing))
    for actor in hits:
        if not cinema.uses_lora(actor):
            continue
        from .loras import find_spec, spec_ready
        from .lora_guidance import guidance
        spec = find_spec(lora_id=actor.get("lora_id") or "")
        if not spec or not spec_ready(spec):
            raise ValueError("Karakter LoRA dosyası seçilmeli ve hazır olmalı: " + actor.get("name", ""))
        trigger = guidance(spec["file"]).get("triggers") or actor.get("trigger") or ""
        text += "\nCharacter " + actor.get("name", "") + " uses the learned identity: " + trigger + "."
        if actor.get("voice"):
            text += " Voice: " + actor["voice"] + "."
    ordered = []
    by_file = {}
    for row in rows:
        previous = by_file.get(row["file"])
        if previous and (previous.get("asset") or {}).get("id") != (row.get("asset") or {}).get("id"):
            raise ValueError("Aynı görsel farklı assetlere atanmış: " + row["file"])
        by_file[row["file"]] = row
    seen = set()
    for row in [*(by_file.get(f, {"file": f}) for f in existing), *rows]:
        file = str(row.get("file") or "")
        if not file or file in seen:
            continue
        if Path(file).name != file or "/" in file or "\\" in file or not exists(file):
            raise ValueError("Referans görseli bulunamadı: " + file)
        seen.add(file)
        ordered.append(row)
    limit = 8 if continuation else 9
    if len(ordered) > limit:
        raise ValueError(f"Bu çekimde en fazla {limit} referans kullanılabilir; seçimi azaltın.")
    if any(int(n) < 1 or int(n) > len(ordered) for n in re.findall(r"<Picture\s+(\d+)>", text, re.I)):
        raise ValueError("Prompttaki Picture numarası seçili referans listesinde yok")
    lora_owner = next((a for a in hits if a.get("kind") == "character" and cinema.uses_lora(a) and a.get("lora_id")), {})
    return {"prompt": text, "rows": ordered, "ref_images": [r["file"] for r in ordered],
            "hits": hits, "lora_id": lora_owner.get("lora_id", ""), "lora_strength": lora_owner.get("lora_strength"),
            **{"has_" + k[:-1]: any(a.get("kind") == k[:-1] for a in hits) for k in film_project.KINDS}}


def prompt(text, rows, start_index=0):
    if start_index:
        text = re.sub(r"<Picture\s+(\d+)>", lambda m: f"<Picture {int(m[1]) + start_index}>", text, flags=re.I)
    return cinema.annotate_prompt(text, [], rows, start_index=start_index)


async def materialize(rows, refs_dir, input_dir, upload):
    """Restore canonical source files into Comfy before building the graph."""
    result = []
    for row in rows:
        source_name = row.get("source_file") or row["file"]
        if Path(source_name).name != source_name or "/" in source_name or "\\" in source_name:
            raise ValueError("Geçersiz referans dosyası")
        source = Path(refs_dir) / source_name
        if source.is_file():
            uploaded = await upload(source, source_name)
        elif (Path(input_dir) / source_name).is_file():
            uploaded = source_name
        else:
            raise ValueError("Kuyruktaki referans görseli artık bulunamıyor: " + source_name)
        result.append({**row, "source_file": source_name, "file": uploaded})
    return result
