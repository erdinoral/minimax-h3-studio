window.createLoraGuidanceEditor = function (catalog, toast) {
  const t=k=>window.t(`loraGuide.${k}`);
  function translate(){document.querySelectorAll('[data-lora-notes]').forEach(b=>b.textContent=window.h3Lang?.() === 'en' ? 'Usage notes' : 'Kullanım notları');}
  translate();document.addEventListener('h3-lang',translate);
  document.addEventListener('click',async e=>{
    const button=e.target.closest('[data-lora-notes]');if(!button)return;
    const ids=[...(document.getElementById(button.dataset.loraNotes)?.selectedOptions||[])].map(o=>o.value);
    const specs=catalog().filter(s=>ids.includes(s.id)&&s.file);
    if(!specs.length){toast(t('select'));return;}
    button.disabled=true;
    try{
      const dialog=document.createElement('dialog');dialog.className='media-trim-dialog';
      const title=document.createElement('h3');title.textContent=t('title');dialog.append(title);
      const hint=document.createElement('p');hint.textContent=t('hint');dialog.append(hint);
      const editors=[];
      for(const spec of specs){
        const r=await fetch(`/api/loras/guidance?file=${encodeURIComponent(spec.file)}`);if(!r.ok)throw Error(t('failed'));
        const data=await r.json();const h=document.createElement('h4');h.textContent=spec.label||spec.file;
        const triggerLabel=document.createElement('label');triggerLabel.textContent=t('triggers');
        const triggers=document.createElement('input');triggers.value=data.triggers||'';triggers.maxLength=500;triggers.readOnly=true;triggerLabel.hidden=true;triggerLabel.append(triggers);
        const guideLabel=document.createElement('label');guideLabel.textContent=t('guide');
        const guide=document.createElement('textarea');guide.rows=6;guide.value=data.guide||'';guide.maxLength=4000;guideLabel.append(guide);
        dialog.append(h,triggerLabel,guideLabel);editors.push({file:spec.file,triggers,guide});
      }
      const save=document.createElement('button');save.type='button';save.textContent=t('save');
      const cancel=document.createElement('button');cancel.type='button';cancel.textContent=window.t('trim.cancel');
      save.className='btn-secondary';cancel.className='btn-secondary';
      const status=document.createElement('p');status.setAttribute('role','status');dialog.append(save,cancel,status);
      let saving=false;
      cancel.onclick=()=>{if(!saving)dialog.close();};
      dialog.addEventListener('cancel',e=>{if(saving)e.preventDefault();});
      dialog.addEventListener('close',()=>dialog.remove());
      save.onclick=async()=>{
        saving=true;save.disabled=true;cancel.disabled=true;
        try{for(const row of editors){const r=await fetch('/api/loras/guidance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file:row.file,triggers:row.triggers.value,guide:row.guide.value})});if(!r.ok)throw Error(t('failed'));}toast(t('saved'));dialog.close();}
        catch(err){status.textContent=err.message;}
        finally{saving=false;save.disabled=false;cancel.disabled=false;}
      };
      document.body.append(dialog);dialog.showModal();editors[0].guide.focus();
    }catch(err){toast(err.message);}finally{button.disabled=false;}
  });
};

(() => {
  const sections = [
    ['Üretim hızlandırma', 'Generation acceleration', 'Uyumlu iş akışında daha az adımla video üretmeye yardımcı olur. Seçilen LoRA’nın adım ve sampler ön ayarları uygulanır; hız ve kalite dengesi modele göre değişir.', 'Helps compatible workflows generate video in fewer steps. The selected LoRA applies its step and sampler presets; speed and quality depend on the model.'],
    ['Karakter LoRA’ları', 'Character LoRAs', 'Belirli bir karakterin görünümünü üretime taşır. Tetikleyici kelimeler ve uygun ağırlık önemlidir; sahneler arasında aynı görünümü korumaya yardımcı olur.', 'Bring a specific character’s appearance into generation. Trigger words and suitable weights matter; these can help maintain appearance across scenes.'],
    ['Görsel stil ve detay', 'Visual style and detail', 'Videonun estetiğini, dokusunu ve ayrıntılarını yönlendirir. Karakter seçimi veya hızlandırmadan farklı olarak görüntünün tarzını etkiler.', 'Influence aesthetics, textures and detail. These affect visual style rather than selecting a character or accelerating generation.'],
    ['Hareket ve aksiyon', 'Motion and action', 'Belirli hareket ve aksiyonların oluşmasını destekler. İstenen hareketi promptta da tarif etmek gerekir.', 'Support particular movements and actions. Describe the desired action in the prompt as well.'],
    ['Mimik ve konuşma', 'Expression and speech', 'Yüz ifadeleri ve konuşma benzeri hareketleri destekler. Yüklenen sese birebir dudak senkronu sağladığı anlamına gelmez.', 'Support facial expressions and speech-like motion. This does not imply exact lip synchronization to uploaded audio.'],
    ['Kamera hareketleri', 'Camera movement', 'Kamera kaydırma, yaklaşma veya benzeri çekim hareketlerini yönlendirmeye yardımcı olur. Sonuç seçilen LoRA’ya ve prompta bağlıdır.', 'Help guide camera motion such as pans or push-ins. Results depend on the selected LoRA and prompt.'],
    ['Yüz ve karakter değiştirme', 'Face and character replacement', 'Uyumlu iş akışlarında yüz veya karakter görünümünü değiştirmeye yardımcı olur. Gerekli referansları ilgili üretim modunda hazırlamak gerekir.', 'Help change face or character appearance in compatible workflows. Prepare the required references in the relevant generation mode.']
  ];
  const en = () => window.h3Lang?.() === 'en';
  const label = (tr, english) => en() ? english : tr;
  const translate = () => document.querySelectorAll('[data-lora-guide]').forEach(button => {button.textContent = label('LoRA rehberi', 'LoRA guide');});
  document.addEventListener('h3-lang', translate);
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-lora-guide]'); if (!button) return;
    const dialog = document.createElement('dialog'); dialog.className = 'lora-help-modal';
    const header = document.createElement('header');
    const title = document.createElement('h2'); title.textContent = label('LoRA rehberi', 'LoRA guide');
    const close = document.createElement('button'); close.type = 'button'; close.className = 'btn-ghost'; close.textContent = '×'; close.setAttribute('aria-label', label('Kapat', 'Close')); close.onclick = () => dialog.close();
    header.append(title, close); dialog.append(header);
    const content = document.createElement('div'); content.className = 'lora-help-content';
    const workflow = document.createElement('section');
    const workflowTitle = document.createElement('h3'); workflowTitle.textContent = label('Adım adım ilk videon', 'Your first video, step by step'); workflow.append(workflowTitle);
    const steps = [
      ['1. Üretim modunu seç', '1. Choose a production mode', 'Sahne sekmesinde Yeni video ile başla. Sıfırdan üretmek için T2V’yi seç; bir görselden başlamak için I2V’yi seç ve başlangıç görselini yükle. Mevcut klibi uzatmak için Videoyu devam ettir modunu kullan.', 'Start with New video in the Scene tab. Choose T2V to generate from text, or I2V and upload an opening image. Use Continue video to extend an existing clip.'],
      ['2. Görünümü ve video ayarlarını belirle', '2. Set the look and video settings', 'Üretim türü ve Görsel tarz kartlarından istediğin seçimleri yap. İlk denemede kısa bir süre ve düşük çözünürlük kullan; örneğin 5 saniye ve 480p. Oranı kullanımına göre seç: yatay video için 16:9, dikey video için 9:16.', 'Choose Project type and Visual style. For a first test, use a short duration and low resolution, such as 5 seconds at 480p. Choose 16:9 for landscape or 9:16 for portrait video.'],
      ['3. Prompt’u yaz', '3. Write the prompt', 'Prompt / Sahne alanına karakteri, ortamı, yaptığı hareketi ve kamerayı yaz. Tek klipte tek bir ana aksiyonla başla. Örnek: Bir kadın yağmurlu sokakta yürür. Kamera onu yandan takip eder. Islak zeminde neon yansımaları, gerçekçi sinema görünümü.', 'Describe the subject, setting, action and camera in Prompt / Scene. Start with one main action per clip. Example: A woman walks along a rainy street. The camera tracks her from the side. Neon reflections on wet pavement, realistic cinematic look.'],
      ['4. Gerekliyse LoRA seç', '4. Select a LoRA if needed', 'LoRA kullanmadan da video üretebilirsin. İhtiyacına uygun grubu aç: daha hızlı deneme için hızlandırma, belirli görünüm için karakter veya stil, çekim hareketi için kamera. Switch’i aç, ağırlığı kontrol et ve Uygula’ya bas. İlk denemede varsayılan ağırlıkla başla; aynı anda çok sayıda LoRA ekleme.', 'You can generate without a LoRA. Open a relevant category: acceleration for faster tests, character or style for appearance, camera for shot motion. Enable the switch, check the weight and click Apply. Start with the default weight and avoid adding many LoRAs at once.'],
      ['5. Tetikleyiciler otomatik uygulanır', '5. Triggers are applied automatically', 'Katalogda tanımlı tetikleyici kelimeler seçilen LoRA ile otomatik uygulanır. Ayrıca yazman gerekmez. Her LoRA tetikleyici gerektirmez; yalnızca kayıtlı bilgiler kullanılır.', 'Catalog trigger words are applied automatically with the selected LoRA. You do not need to type them. Not every LoRA requires a trigger; only recorded information is used.'],
      ['6. İsteğe bağlı ses ve son geçiş', '6. Optional audio and post-pass', 'Ses kartında kaydını seçip Sesi hazırla’ya basabilirsin. Ses referansı üretilen sesi yönlendirir; Kaydımı videoya ekle kaydı sonuç videoya yerleştirir. Bunlar birebir dudak senkronu sağlamaz. İlk testte Son geçiş’i Kapalı bırak; uygun sonuçta upscale kullanabilirsin.', 'Select a recording under Audio and click Prepare audio. An audio reference guides generated sound; Add my recording to the video places the recording in the result. Neither provides exact lip sync. Keep Post-pass off for the first test; use upscale once you have a suitable result.'],
      ['7. Üret veya sıraya ekle', '7. Generate or add to queue', 'Tek deneme için Üret’e bas. Birden fazla prompt hazırlayacaksan her birini Sıraya ekle ile kuyruğa al. Üretim listesinden durumunu takip et. Hata oluşursa aynı ayarlarla sürekli tekrar etmek yerine hata mesajını incele.', 'Click Generate for a single test. To prepare several prompts, add each to the queue. Follow progress in the Production list. If a job fails, inspect the error instead of repeatedly retrying the same settings.'],
      ['8. Sonucu incele ve geliştir', '8. Review and refine', 'Biten klibi Oynat ile aç. Önce hareketi, karakteri ve kamerayı kontrol et. Değişiklik gerekiyorsa prompt veya tek bir ayarı değiştirip yeniden dene. Daha iyi sonuca ulaştığında çözünürlüğü artır. İndir ile kaydet; devam klibi için Bu videodan devam’ı kullan. Klip birleştirme Galeri’den yapılır.', 'Open a finished clip with Play. Check action, character and camera first. Change the prompt or one setting at a time and retry. Increase resolution after you have a good result. Download to save, use Continue from this video for an extension, and merge clips in Gallery.']
    ];
    for (const [trTitle, enTitle, trBody, enBody] of steps) {
      const heading = document.createElement('h4'); heading.textContent = label(trTitle, enTitle);
      const body = document.createElement('p'); body.textContent = label(trBody, enBody); workflow.append(heading, body);
    }
    content.append(workflow);
    const categoriesTitle = document.createElement('h3'); categoriesTitle.textContent = label('LoRA grupları ne işe yarar?', 'What do the LoRA categories do?'); categoriesTitle.className = 'lora-guide-category-heading'; content.append(categoriesTitle);
    for (const [trTitle, enTitle, trBody, enBody] of sections) {
      const section = document.createElement('section'); const heading = document.createElement('h3'); const body = document.createElement('p');
      heading.textContent = label(trTitle, enTitle); body.textContent = label(trBody, enBody); section.append(heading, body); content.append(section);
    }
    const note = document.createElement('p'); note.className = 'muted'; note.textContent = label('LoRA’yı aç, ağırlığını ayarla ve Uygula’ya bas. Birden fazla hızlandırma LoRA’sını birlikte seçme. Katalogda tanımlı tetikleyiciler otomatik uygulanır.', 'Enable a LoRA, set its weight and click Apply. Do not combine multiple acceleration LoRAs. Catalog trigger words are applied automatically.'); content.append(note); dialog.append(content);
    dialog.setAttribute('aria-label', title.textContent); dialog.addEventListener('close', () => dialog.remove());
    dialog.addEventListener('click', e => {if (e.target === dialog) {const r = dialog.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close();}});
    document.body.append(dialog); dialog.showModal();
  });
})();
