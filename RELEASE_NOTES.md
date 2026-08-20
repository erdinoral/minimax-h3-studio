# H3 Studio — Güncelleme Notları

**Sürüm:** 2026-08-20 (Studio patch 2)  
**Repo:** https://github.com/erdinoral/minimax-h3-studio  
**Pinokio:** `minimax-h3-studio` → **Update** → **Stop** → **Start** (tarayıcıda **Ctrl+F5**)

---

## Özet

Yönetmen LLM (Gemini / NVIDIA), Plan modu, Sinema stüdyosu, arayüz (TR/EN), dosya seçici ve üretim kuyruğu için toplu düzeltme ve iyileştirme paketi.

---

## 1. Yönetmen LLM — Gemini, NVIDIA, Kaydet / Uygula

### Gemini
- `/api/director/chat` artık `ui_lang` ve `plan_mode` alanlarını kabul ediyor — **“istek başarısız”** / sunucu hatası düzeltildi.
- Kaydettiğin model (ör. `gemini-3.6-flash`) listede ve durum çubuğunda korunur.
- **Ayarlar** → sağlayıcı **Gemini** → key (`AIza…`) → model → **API ayarlarını kaydet** → Yönetmen panelinde **Yönetmeni uygula**.

### NVIDIA NIM
- `nvapi-…` anahtarları ayrı **NVIDIA NIM** sağlayıcısı ile gider (OpenAI alanından otomatik taşıma devam ediyor).
- Durum sorgusu: varsayılan model kapalıysa hafif bir yedek model denenir; tüm NVIDIA “kapalı” yanlış pozitifi azaltıldı.
- **429 rate limit** için net uyarı (ör. `minimaxai/minimax-m3` kotası dolunca `meta/llama-3.1-8b-instruct` dene).

### Kaydet / Yönetmeni uygula
- Butonlar artık “Kaydediliyor…” / “Uygulanıyor…” durumunda takılı kalmıyor.
- Kaydetmeden önce kaydedilmemiş key uyarısı; üretim panelinde sağlayıcı seçimi Ayarlar ile senkron.

> Video üretimi (Comfy / H3) bu LLM ayarlarından **etkilenmez** — sadece Yönetmen sohbeti, Plan ve senaryo ingest.

---

## 2. Plan modu

- Shot başına **tek prompt alanı**; gereksiz alt alanlar kaldırıldı.
- Her shot’ta çalışan **Sil** butonu.
- Plan → Kaydet / Stüdyoya aktar / Üretime al akışı aynı.

---

## 3. Sinema stüdyosu

- **Karakter ekle+** / **Mekan ekle+** sonrası kartların görünmemesi düzeltildi.
- Silme / ekleme sonrası kartlar zorla yeniden çiziliyor; ilgili bölüm açılıp yeni karta kaydırılıyor.
- Kuyruk / müzik / kaydet toast’ları dile göre güncelleniyor.

---

## 4. Arayüz — TR / EN

- **Varsayılan dil: EN** (yeni kullanıcılar).
- Son seçim `localStorage` ile hatırlanır (TR seçtiysen bir sonraki açılışta TR).
- Sinema stüdyosu ipuçları (ör. *Add characters / locations → name them in shots → queue*) ve eksik çeviriler tamamlandı.
- Sahne paneli: Üretim türü / Görsel tarz chip’leri yönetmen modalı açıkken de tıklanabilir.

---

## 5. Dosya seçici (Görsel seç)

- Görseli × ile kaldırınca dosya adı (**yamal.png** vb.) artık **Seçilmedi** / **Not selected** olarak sıfırlanır.
- İlk/son kare, referans, yüz ve V2V listelerinde aynı mantık.

---

## 6. Launcher / backend

- `start.js`: Comfy kapanışı için `--timeout-graceful-shutdown 8`.
- Studio: kapanışta tek örnek kilidi ve Comfy bellek boşaltma iyileştirmeleri.

---

## Güncelleme sonrası

1. Pinokio → **Update** (veya repo’yu çek).
2. **Stop** → **Start**.
3. Studio’da **Ctrl+F5** (önbellek: `cinema54`).
4. LLM: Ayarlar → sağlayıcı + key + model → **Kaydet** → Yönetmen → **Yönetmeni uygula**.

---

## Pinokio post özeti (kopyala-yapıştır)

**TR:** H3 Studio güncellendi — Gemini/NVIDIA yönetmen düzeltmeleri, Plan shot silme, sinema kartları, EN varsayılan + TR hatırlama, görsel seçici temizleme, sahne chip’leri. Update → Stop → Start → Ctrl+F5.

**EN:** H3 Studio update — Director LLM (Gemini/NVIDIA), Plan delete, cinema cards fix, default EN + remembered locale, file-picker label reset, scene chips under modal. Update → Stop → Start → hard refresh.

---

## Teknik (geliştiriciler)

| Alan | Dosyalar |
|------|----------|
| LLM | `studio/lib/llm.py`, `studio/server.py` |
| Director / cinema API | `studio/server.py`, `studio/lib/cinema.py` |
| UI | `studio/static/app.js`, `app.css`, `i18n.js`, `index.html` |
| Launcher | `start.js` |

---

## English (short)

- **Gemini director** chat fixed (`ui_lang`, `plan_mode`); save/apply buttons no longer stuck.
- **NVIDIA NIM** status probe improved; 429 hints for rate-limited models.
- **Plan mode:** one prompt field per shot + working **Delete**.
- **Cinema studio:** character/location cards render after add/remove; i18n toasts.
- **i18n:** default **EN**, last choice remembered; cinema hints translated.
- **File picker:** removing a thumb clears the filename label.
- **Scene chips** clickable while director modal is open.
- **Launcher:** graceful Comfy shutdown timeout.

After update: **Stop → Start**, **Ctrl+F5**, re-save LLM in Settings.
