# Studio skill set (portable)

Kaynak: MiniMax Design **Skill Connector** (`~/.hub-global/skills`) + Design `agent-profiles`.

## Ne işe yarar?

| Katman | Rol |
|--------|-----|
| `vendor/` | Orijinal Hub skill metinleri (referans; Midjourney/canvas çalıştırılmaz) |
| `packs/genre_craft.json` | Bizim değerler: setup bundle + craft + avoid + ses |
| `catalog.json` | look id ↔ pack eşlemesi |
| `lib/skills.py` | Compose / `setup_preamble` için craft enjekte eder |

## Üretim kalitesi

Evet — **prompt’a yazılan craft satırları** H3 çıktısını etkiler (ışık, malzeme, kaçınılacak klişeler).  
Hayır — Hub’ın STEP 2–3 Midjourney / four-view / canvas pipeline’ı burada otomatik koşmaz; kalite artışı **prompt disiplini + look preset** üzerinden gelir.

## Yeni genre eklemek

1. `packs/genre_craft.json` içine look id + setup/craft/avoid ekle  
2. `catalog.json` packs listesine yaz  
3. UI `CINEMA_LOOK_PRESETS` + i18n `cinema.look.<id>`  
4. `cinema.py` `SETUP_HINTS["look"]` satırını güncelle (veya skills craft’ına bırak)
