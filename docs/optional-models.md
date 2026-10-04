# İsteğe bağlı H3 ana modeller

Ayarlar > Video motoru ve İsteğe bağlı ana modeller.

Singularity Pruned INT8 deneysel bir ana modeldir; karakter LoRA'sı değildir.
İndirme boyutu 20.967.647.456 bayt (yaklaşık 21 GB). Varsayılan kurulum bunu indirmez.
İndir düğmesi yalnız dosyayı kurar; mevcut model seçimini değiştirmez.
İndirme sonrası SHA256 doğrulanır. Eksik .part dosyası model seçimine sunulmaz.
Bağlantı kesilirse indirme aynı kısmi dosyadan devam edebilir.
Aynı Civitai/Hugging Face sürümü farklı bilinen dosya adıyla zaten yüklüyse tekrar indirilmez.

Yüklendikten sonra üstteki H3 Singularity düğmesi FL2VA ve REF2VA seçimlerini birlikte kaydeder.
Varsayılana dön düğmesi mevcut Studio modellerine döndürür, indirilen dosyayı silmez.

Kaynak: https://civitai.com/models/2917208/minimax-h3singularity
Üretici: https://huggingface.co/WarmBloodAban/Minimax-h3_Singularity
SHA256: 412a7b126595a958964193f3b42513d7cf2df4196ef04223a0f05e3622949cce

Yerel karşılaştırma: singularity-comparison.json. İlk test 480p / 10 step kısa karşılaştırmadır; tam kaliteye dair genelleme yapılmamalı.

## Motor seçimi
Ayarların üstündeki MiniMax H3 / H3 Singularity seçicisi hem FL2VA hem REF2VA ana modelini değiştirir. Yeni Sahne ve Direktör işleri bu seçimi kaydeder; mevcut kuyruk işleri kendi model seçimlerini korur. CLIP ve VAE seçimleri korunur. Yüklü Singularity yeniden indirilmez. Gelişmiş bölümde farklı ana modeller seçilirse motor Özel modeller olarak görünür.
