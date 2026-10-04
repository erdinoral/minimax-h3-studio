# AI Yönetmen

Direktör içindeki AI Yönetmen düğmesi hikâye ve hedef süre ister. Klip süresi mevcut film ayarından alınır; hedef süre klip sayısına yukarı yuvarlanır (en fazla 40 sahne).

Ayarlar içindeki aktif LLM sağlayıcısı ve model kullanılır. Yönetmen mevcut karakter, mekân, yaratık ve araç kartlarını bağlam olarak görür; görsel alanları İngilizce, diyalogları hikâyenin konuşma dilinde hazırlar. Ana model, kalite, adım ve LoRA seçimleri film ayarlarında kalır.

POST /api/cinema/ai-plan geçerli h3-cinema/v1 paketi döndürür. Sahne sayısı, aksiyon/kamera, açılış/son kadraj, kart adları ve devam bağlantıları kontrol edilir; eksik yanıt bir kez yeniden istenir. Bu endpoint filme yazmaz.

Arayüz sonucu mevcut POST /api/cinema/import-json üzerinden ayrı bölüme ekler. Yeni kartlar eklenir; mevcut kartların LoRA, ses, görsel ve notları korunur. expected_film_id kontrolü başka filme aktarımı engeller. Görsel/video üretimi başlatılmaz; kullanıcı sahneleri kontrol edip Üret ile başlatır.

JSON içe/dışa aktarma seçenekleri kullanılmaya devam eder. Senaryo üretimi başarısızsa hikâye kutusu korunur ve hiçbir eksik paket filme aktarılmaz.

Doğrulama: canlı Gemini denemesi 2 ayrıntılı sahne (t2v + continue) üretti; gerçek paket geçici film deposuna aktarıldı ve sahne editörü alanları kontrol edildi. Kullanıcının açık filmi değiştirilmedi. Gemini akışındaki boşluk kaybı da düzeltildi: parça sınırlarında karakter/mekân adları birleşmez.
