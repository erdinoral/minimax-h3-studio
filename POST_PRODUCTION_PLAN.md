---
name: Post-production H3 features
status: in_progress — started 2026-08-13
overview: Üretim bitince restart; galeri üretim süresi; prompt skill; V2V; Direktör; FL2VA+storyboard; süre; UI son. Müzik ayırma yok (H3 tek track).
todos:
  - id: restart-verify
    content: Üretim idle doğrula + smoke (VRAM/Telegram/progress)
    status: completed
  - id: gallery-render-time
    content: Galeri kart meta — video kaç dk/sn’de üretildi (started_at→done_at)
    status: completed
  - id: prompt-skill
    content: MiniMax h3-prompt-writing → director_system
    status: completed
  - id: v2v-ref2va
    content: Video-to-Video — Ref2VA video refs ≤3
    status: completed
  - id: director-mode
    content: Direktör modu ProjectBible
    status: completed
  - id: fl2va-last
    content: build_t2v_prompt last_frame + API/UI first+last
    status: completed
  - id: storyboard-chain
    content: Storyboard zinciri N görsel
    status: completed
  - id: flex-duration
    content: Esnek süre 4/6/8 + Fast preset
    status: completed
  - id: ui-higgsfield
    content: SON İŞ — Seedance/Higgsfield shell (stage, ref slots, generation bar)
    status: pending
  - id: bgm-bleed-fix
    content: Müzik ayırma — vazgeçildi
    status: cancelled
---

# Üretim bitince: H3 Studio planı

## Durum (2026-08-13)

Fonksiyonel maddeler uygulandı. **Studio’yu bir kez restart et** ki `server.py` / `comfy.py` / `director.py` yüklensin (statik UI soft-refresh olabilir).

Kalan: **UI shell (Higgsfield)** — en son iş.

### Yapılanlar
- Galeri `render_sec` + `started_at` (disk backfill 33 klip)
- H3 prompt skill dosyaları `studio/prompts/h3_skill/`
- V2V: `upload-video`, Ref2VA video graph, UI mod
- FL2VA last_frame + first/last UI
- Storyboard `/api/storyboard`
- Süre 4/5/6/8/10/15 + Fast preset
- Direktör sekmesi + `/api/director/bible/generate`
