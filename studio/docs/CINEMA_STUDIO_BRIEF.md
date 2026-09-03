# Cinema Stüdyo Brief (Claude / geliştirme)

Bu belge H3 Studio **Direktör · Sinema stüdyosu** için ürün brief’idir: istekler, mevcut sistem, mimari, new vs continue, yol haritası.

## 1. Amacımız

1. Kullanıcı **karakter** tanımlar (ad + görünüm şablonu + referans görsel)
2. İsterse **mekan** tanımlar
3. Sistem shot’ları yazar / kullanıcı düzenler
4. Sistem tutarsızlığı bozmadan videoları üretir
5. Her shot için **New Video (t2v)** mi **Continue (son kare)** mi doğru seçilir

Başarı = karakter/mekân film boyunca tanınır; cutaway sonrası drift yok; kullanıcı 5 dk’da üretir.

## 2. İstediklerimiz

- Kart adı shot’ta geçince otomatik görsel + şablon kilidi
- Sistem `new` / `continue` kararını anlasın ve uygulasın
- Kolay UI: cast → shot → kuyruk
- Mevcut H3 / Comfy / Pinokio motorunu bozmadan üstüne bina
- **Sahne** (tek klip) ile **Direktör** (film) net ayrı workspace

## 3. Olanlar

| Parça | Durum |
|-------|--------|
| Cinema UI, karakter/mekan kartları, shot listesi | Var |
| `bind_prompt` → Picture + ref_images | Var |
| `face_continue` yüz kilidi | Var |
| Yönetmen FAZ A/B | Var |
| Cutaway / cast örtüşmezse hard-cut (`apply_reentry_modes`) | Var |
| Sahne: t2v / continue / ref / face / v2v | Ayrı |

## 4. Çalışma prensibi

```
Kart (ad + notes + image)
  → shot metninde ad
  → bind_prompt
  → t2v | continue | face | ref | face_continue
  → Comfy H3 → galeri
```

Referans görsel ≠ I2V başlangıç. Continue = önceki klipin **son karesi**.

## 5. Motorlar

- UI: `studio/static/`
- API: `studio/server.py`
- Cinema: `studio/lib/cinema.py`
- Director: `studio/lib/director.py`
- LLM: `studio/lib/llm.py`
- Video: ComfyUI + MiniMax H3 (Pinokio)

## 6. New vs Continue

| Durum | Mode |
|-------|------|
| Aynı beat / cast / mekân | Continue |
| Cutaway sonrası karakter dönüşü | **t2v + refs** |
| İlk shot / yeni mekân+karakter | t2v + refs |

**Her klip continue olmamalı** — cutaway’de continue drift üretir.

## 7. Yol haritası

- Faz 1: checklist, tek CTA, produce kapısı, bind badge, isim chip
- Faz 2: guided empty, gelişmiş fold, progress özeti
- Faz 3: cast QA, storyboard, tür presetleri

## 8. Claude’dan istenen

1. New/continue karar ağacı + UX copy  
2. Cinema bilgi mimarisi (Faz 1–2)  
3. `bind_prompt` / reentry’yi bozmadan UX  
4. Dosya bazlı görev listesi  

Kısıt: H3 graph yeniden yazma yok; kart→isim→ref sözleşmesi korunur.
