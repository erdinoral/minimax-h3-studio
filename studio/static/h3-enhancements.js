(() => {
  let busy = false;
  let loaded = false;
  let config = {refmod_enabled: false, refmod_ready: false};
  const en = () => window.h3Lang?.() === 'en';
  const text = (a,b) => en() ? a : b;
  const anchors = ['studio-theme-settings', 'scene-asset-references', 'btn-cinema-library-toggle'];
  function render() {
    for (const [index, anchorId] of anchors.entries()) {
      const anchor = document.getElementById(anchorId);
      if (!anchor) continue;
      let card = document.getElementById('h3-refmod-' + index);
      if (!card) {
        card = document.createElement('div'); card.id = 'h3-refmod-' + index;
        card.className = 'h3-refmod-control'; anchor.insertAdjacentElement('afterend', card);
      }
      card.innerHTML = `<label class="h3-refmod-label"><span><strong>RefMod</strong><span class="muted">${text('Cached asset references', 'Önbellekli asset referansları')}</span></span><input type="checkbox" role="switch" aria-label="RefMod" ${config.refmod_enabled?'checked':''} ${config.refmod_ready && !busy?'':'disabled'}></label>${index===0 ? `<p class="muted">${!loaded ? text('Checking reference tools…', 'Referans araçları kontrol ediliyor…') : config.refmod_ready ? text('Uses full reference retention and reuses encoded references. Applies to Scene and Director reference videos; does not train a LoRA or guarantee identity. Speed LoRAs load their compatible step and sampler presets automatically.', 'Tam referans gücüyle kodlanmış referansları yeniden kullanır. Sahne ve Direktör referans videolarına uygulanır; LoRA eğitmez ve kimliği garanti etmez. Hız LoRA’larının uyumlu adım ve sampler ayarları otomatik uygulanır.') : text('Reference tools are not loaded. Install Film tools, then restart Studio.', 'Referans araçları yüklenmemiş. Film araçlarını yükleyip Studio’yu yeniden başlat.')}</p>` : ''}`;
      card.querySelector('input').onchange = async event => {
        const enabled = event.target.checked; busy = true; render();
        try {
          const response = await fetch('/api/h3-enhancements', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({refmod_enabled:enabled})});
          const data = await response.json();
          if (!response.ok) throw Error(data.detail || 'RefMod settings failed');
          config = data;
        } catch(error) { window.alert(error.message); }
        busy = false; render();
      };
    }
  }
  document.addEventListener('h3-lang', render);
  fetch('/api/h3-enhancements').then(r => r.ok ? r.json() : Promise.reject()).then(data => {config=data;loaded=true;render();}).catch(() => {});
})();
