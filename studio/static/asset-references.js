/* Scene and Director share the server's ordered reference preview. */
(() => {
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tr = () => window.h3Lang?.() !== 'en';
  const word = (a,b) => tr() ? a : b;
  window.assetReferenceLabel = im => {
    const angle = /_(front|rear|right|left)\.png$/i.exec(im.file || '');
    const labels = tr() ? {front:'Ön',rear:'Arka',right:'Sağ yan',left:'Sol yan'} :
      {front:'Front',rear:'Rear',right:'Right side',left:'Left side'};
    return (im.name || im.file) + (angle ? ' · ' + labels[angle[1].toLowerCase()] : '');
  };
  window.previewAssetReferences = async payload => {
    const response = await fetch('/api/asset-references/preview', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : word('Referans seçimi geçersiz','Invalid references'));
    const dialog = document.createElement('dialog'); dialog.className = 'media-trim-dialog';
    dialog.innerHTML = `<h3>${word('Üretime gönderilecek referanslar','References sent to generation')}</h3>
      ${data.first_frame_reserved ? `<p>&lt;Picture 1&gt; · ${word('Başlangıç / önceki son kare','Opening / previous final frame')}</p>` : ''}
      ${data.references.map(r=>`<figure><img style="max-width:140px;max-height:100px" src="/api/refs/${encodeURIComponent(r.file)}" alt="${esc(r.asset)}"><figcaption>&lt;Picture ${r.picture}&gt; · ${esc(r.asset)} · ${esc(r.kind)}<br>${esc(r.file)}</figcaption></figure>`).join('')}
      ${!data.references.length ? `<p>${word('Asset referansı yok','No asset references')}</p>` : ''}
      <details><summary>Prompt</summary><pre style="white-space:pre-wrap">${esc(data.prompt)}</pre></details>
      <button class="btn-secondary">${word('Kapat','Close')}</button>`;
    dialog.querySelector('button').onclick = () => dialog.close();
    dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);dialog.showModal();
    return data;
  };
  window.createSceneAssetReferences = api => {
    const host = document.getElementById('scene-asset-references');
    let film = null, selected = new Map(), explicit = true;
    const assets = () => ['characters','creatures','vehicles','locations'].flatMap(key => film?.[key] || []);
    const payload = () => ({asset_film_id:film?.film_id,
      asset_auto_match:!explicit,
      asset_bindings:explicit ? [...selected].map(([asset_id,files])=>({asset_id,files:[...files]})) : null});
    function remember() {
      try { localStorage.setItem('h3-scene-assets', JSON.stringify(payload())); } catch {}
    }
    function render() {
      if (!host) return;
      host.innerHTML = `<details><summary>${word('Asset referansları','Asset references')}</summary>
      <p>${esc(film?.title || '')} · ${word('Sahne bağımsızdır. Assetleri seç veya isim eşleştirmeyi aç.','Scene is independent. Select assets or enable name matching.')}</p>
      <div class="row-btns"><button class="btn-secondary" data-action="refresh">${word('Yenile','Refresh')}</button><button class="btn-secondary" data-action="auto">${word('İsimlerden otomatik','Automatic by name')}</button><button class="btn-secondary" data-action="none">${word('Asset kullanma','No assets')}</button><button class="btn-secondary" data-action="preview">${word('Gönderilecekleri göster','Preview references')}</button></div>
      ${assets().map(a=>`<div class="film-asset"><strong>${esc(a.name)}</strong><div class="film-ref-images">${(a.images||[]).map(im=>`<label><img src="${esc(im.url||'/api/refs/'+encodeURIComponent(im.file))}" alt="${esc(window.assetReferenceLabel(im))}"><input type="checkbox" data-owner="${esc(a.id)}" data-file="${esc(im.file)}" ${selected.get(a.id)?.has(im.file)?'checked':''}>${esc(window.assetReferenceLabel(im))}</label>`).join('') || `<small>${word('Görsel eksik; Director kartından yükle veya üret.','Missing image; upload or generate it in the Director card.')}</small>`}</div></div>`).join('')}
      <p>${explicit ? word('Yalnızca seçili görseller gönderilecek.','Only selected images will be sent.') : word('Asset isimleri otomatik eşleştirilecek.','Asset names will be matched automatically.')}</p></details>`;
    }
    async function refresh() {
      const response = await fetch('/api/cinema'); if (!response.ok) throw Error('Asset catalog unavailable');
      const current = await response.json();
      if (film && film.film_id !== current.film_id) {selected.clear();explicit=true;}
      film = current;render();
      if (!selected.size) {
        try {
          const saved = JSON.parse(localStorage.getItem('h3-scene-assets') || 'null');
          if (saved?.asset_film_id === film.film_id && Array.isArray(saved.asset_bindings)) {
            selected = new Map(saved.asset_bindings.filter(b => typeof b.asset_id === 'string' && Array.isArray(b.files))
              .map(b => [b.asset_id, new Set(b.files.filter(f=>typeof f==='string'))]));
            explicit=true;render();
          }
        } catch {}
      }
    }
    host?.addEventListener('change', e => {
      const {owner,file} = e.target.dataset; if (!owner || !file) return;
      explicit=true;const files=selected.get(owner)||new Set();
      e.target.checked ? files.add(file) : files.delete(file);
      files.size ? selected.set(owner,files) : selected.delete(owner);
      remember();
    });
    host?.addEventListener('click', async e => {
      const action=e.target.dataset.action;if(!action)return;
      try {
        if(action==='refresh')await refresh();
        if(action==='auto'||action==='none'){selected.clear();explicit=action==='none';remember();render();}
        if(action==='preview')await window.previewAssetReferences({...api.context(),...payload()});
      }catch(error){api.toast(error.message);}
    });
    refresh().catch(error=>api.toast(error.message));
    document.addEventListener('h3-lang', render);
    return {payload, refresh, render};
  };
})();
