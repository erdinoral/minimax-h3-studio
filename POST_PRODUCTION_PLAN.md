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


## Güncel açık işler — 2026-10-15

Bu bölüm mevcut uygulama için geçerli plandır. Ağustos listesindeki UI shell maddesi tarihsel bir hedeftir; güncel arayüz geliştirmeleri sonrası yeniden değerlendirilmeden aktif işe çevrilmeyecek. Eski LoRA araştırma listesi yeni indirme veya geliştirme emri değildir; kullanıcının yeni LoRA istememe tercihi geçerlidir.

### Öncelikli: Continuum üretimini kurtarma
- [ ] Her iş için tamamlanan bölüm sayısını ve güvenilir kayıt durumunu göster.
- [ ] Hata, uygulama kapanması veya bilgisayarın yeniden açılması sonrası son doğrulanmış bölümden devam et.
- [ ] Model, referans, seed, sampler ve kaynak kayıt uyumunu doğrula; önceki bölümleri sessizce yeniden üretme.
- [ ] Eksik/bozuk/uyumsuz kayıtları açıkça belirt. Standart MP4 veya eski Spectrum’lu Continuum kaydını kurtarılabilir native kayıt gibi sunma.

### Sonraki: Seçilen bölümden itibaren yeniden üretim
- [ ] Kullanıcı yeniden üretimin başlayacağı bölümü seçebilsin.
- [ ] Önceki bölümler aynen korunsun; seçilen bölüm ve sonrası yeniden üretilsin.
- [ ] Yeni sonuç ayrı galeri kaydı olsun; önceki video korunmaya devam etsin.
- [ ] Yeni dalın kaynak revision bilgisini sakla; başka bir dalın kaydını yanlışlıkla kullanma.

### Açık kalite ve doğrulama işleri
- [ ] Devam tutarlılığı: karakter/yüz, kadraj, ışık ve hareket kaymasını azaltacak yöntemleri karşılaştırmalı test et. Mevcut iyileştirmeler kusursuz tutarlılık sağlamıyor.
- [ ] Max Identity ile Match Output farkını aynı kaynak ve ayarlarla karşılaştır; maksimum ayarın bellek/süre/kalite etkisi henüz ölçülmedi.
- [ ] Uzun Continuum dizileri ve ses/müzik geçişleri için gerçek testler yap. Şu ana kadarki kısa görsel kontroller ses doğrulaması değildir.
- [ ] Spectrum’un Singularity ve Hybrid’de gerçek hız/kalite karşılaştırmasını yap. Graph bağlantı testleri geçti; motor başına GPU hız kazancı doğrulanmadı.
- [ ] Continuum + Spectrum kayıt uyumluluğu: yeni çalışmalarda Spectrum kullanılabilir, fakat Spectrum varken native kayıt depolaması kapalıdır. Eski Spectrum’lu kayıttan devam güvenilir runtime imzası doğrulanmadan açılmayacak.

### Kullanıcı isteğiyle sonraya bırakılanlar
- [ ] API/LLM gerektirmeyen üretim öncesi referans etiketi ve teknik devam kontrolü.
- [ ] Süreye uygun prompt/konuşma uyarısı ve isteğe bağlı anlamsal devam kontrolü.

Bu liste uygulama planıdır; bu turda üretim kuyruğu veya yeni model indirmesi başlatılmadı.
