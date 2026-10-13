(() => {
  const $ = id => document.getElementById(id);
  let caps = {}, clip = null, method = 'standard', chunks = 1, prepare = false, directorBackend='multishot';
  const text = (tr, en) => window.h3Lang?.() === 'en' ? en : tr;
  window.getVideoWorkflowPayload = () => ({continuation_method:method,
    continuum_chunks:chunks, prepare_refine:prepare && method === 'standard'});
  window.getDirectorContinuumBackend = () => directorBackend;
  function render() {
    const legacyAudio=$('continue-audio-continuity')?.closest('label');
    if(legacyAudio)legacyAudio.hidden=method==='continuum';
    const director=$('director-continuum-control');
    if(director){
      director.hidden = !$('cinema-seamless-toggle')?.checked;
      director.innerHTML=`<label>${text('Kesintisiz motoru','Seamless engine')} <small>${text('Deneysel','Experimental')}</small></label><select><option value="multishot">${text('Mevcut Multishot','Existing Multishot')}</option><option value="continuum" ${caps.continuum_ready?'':'disabled'}>Continuum</option></select><p class="muted">${text('Continuum: take başına en fazla 16 bölüm. Mevcut Multishot seçeneği korunur; kalite testi tamamlanana kadar varsayılan değiştirilmez.','Continuum: up to 16 chunks per take. The default stays unchanged until quality validation is complete.')}</p>`;
      director.querySelector('select').value=directorBackend;
      director.querySelector('select').onchange=e=>{directorBackend=e.target.value;};
    }
    const host = $('video-workflow-controls');
    if (!host) return;
    host.innerHTML = `<label>${text('Üretim yöntemi','Generation method')} <small>${text('Deneysel','Experimental')}</small></label>
      <select id="h3-continuation-method"><option value="standard">${text('Standart H3','Standard H3')}</option>
      <option value="continuum" ${caps.continuum_ready?'':'disabled'}>Continuum</option></select>
      <div id="h3-continuum-options" ${method==='continuum'?'':'hidden'}>
      <label>${text('Yeni bölüm sayısı','New chunks')} <input id="h3-continuum-chunks" type="number" min="1" max="16" value="${chunks}"></label>
      <p class="muted">${text('1–16 bölüm. Devam için Continuum kaydı gerekir. Seed, adım, çözünürlük ve ses devamlılığı kaynak kayıttan alınır. Yeni video tüm diziyi içerir; önceki kayıt korunur.','1–16 chunks. Continuation requires a Continuum record. Seed, steps, resolution and audio continuity come from the source record. The new video contains the complete sequence; the source is preserved.')}</p></div>
      <label class="check"><input id="h3-prepare-refine" type="checkbox" ${prepare && method==='standard'?'checked':''} ${caps.refine_ready && method==='standard'?'':'disabled'}> ${text('H3 Refine için kayıt hazırla','Prepare H3 Refine recording')}</label>
      <p class="muted">${text('Refine kaydı ek RAM ve disk kullanır. Tek klipte önizleme ve son geçiş kapalıyken kullanılabilir.','Refine recording uses additional RAM and disk. Available for single clips with preview and post-pass disabled.')}</p>
      ${caps.continuum_ready && caps.refine_ready?'':`<p class="muted">${text('Araçlar henüz yüklenmemiş. Kuyruk bitince Studio’yu yeniden başlat.','Tools are not loaded yet. Restart Studio after the queue finishes.')}</p>`}`;
    $('h3-continuation-method').value = method;
    $('h3-continuation-method').onchange = e => {method=e.target.value;render();};
    $('h3-continuum-chunks').onchange = e => {chunks=Math.max(1,Math.min(16,Number(e.target.value)||1));e.target.value=chunks;};
    $('h3-prepare-refine').onchange = e => {prepare=e.target.checked;};
    const button = $('btn-h3-refine');
    if (button) {
      button.innerHTML = `H3 Refine <small>${text('Deneysel','Experimental')}</small>`;
      button.disabled = !clip || !clip.prepare_refine || !caps.refine_ready || Math.min(clip.width,clip.height)>=1088;
      button.title = clip?.prepare_refine ? text('Daha yüksek çözünürlükte yeni bir galeri videosu üret','Create a new gallery video at higher resolution') : text('Üretim sırasında Refine kaydı hazırlanmadı','No Refine recording was prepared while rendering');
      button.onclick = openRefine;
    }
  }
  function openRefine() {
    if (!clip) return;
    const id = clip.id, options = [352,480,608,736,768,1088].filter(q=>q>Math.min(clip.width,clip.height));
    const modal=document.createElement('dialog');modal.className='h3-refine-dialog';
    modal.innerHTML=`<form method="dialog"><h3>H3 Refine · ${text('Deneysel','Experimental')}</h3><p>${text('Kaynak korunur. Sonuç ayrı video olarak galeriye kaydedilir. Yeniden örnekleme görünümü değiştirebilir.','The source is preserved. The result is a separate Gallery video. Resampling may change appearance.')}</p>
    <label>${text('Hedef çözünürlük','Target resolution')} <select>${options.map(q=>{const scale=q/Math.min(clip.width,clip.height), snap=v=>Math.max(32,Math.floor(v/32+0.5)*32);return `<option value="${q}">${q}p · ${snap(clip.width*scale)}×${snap(clip.height*scale)}</option>`;}).join('')}</select></label>
    <p class="muted">${text('H3 için öğrenilmiş 3D büyütme + Flow yeniden işleme. Hareket ve detaylar değişebilir.','H3-trained 3D upscaling + Flow resampling. Motion and detail may change.')}</p>
    <p role="status"></p><div class="row-btns"><button type="button" class="cta">${text('Sıraya ekle','Add to queue')}</button><button class="btn-secondary">${text('Vazgeç','Cancel')}</button></div></form>`;
    document.body.appendChild(modal);modal.onclose=()=>modal.remove();modal.showModal();
    modal.querySelector('button[type=button]').onclick=async event=>{
      event.target.disabled=true;
      try {
        const response=await fetch(`/api/clips/${encodeURIComponent(id)}/refine`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({quality:modal.querySelector('select').value})});
        const data=await response.json();if(!response.ok)throw Error(data.detail || 'Refine failed');
        modal.querySelector('[role=status]').textContent=text('Kuyruğa eklendi; sonuç galeride görünecek.','Queued; the result will appear in Gallery.');
      }catch(error){modal.querySelector('[role=status]').textContent=error.message;event.target.disabled=false;}
    };
  }
  document.addEventListener('h3-player-clip',e=>{clip=e.detail;render();});
  document.addEventListener('change',e=>{if(e.target.id==='cinema-seamless-toggle')render();});
  document.addEventListener('h3-lang',render);
  render();fetch('/api/video-workflows').then(r=>r.ok?r.json():{}).then(data=>{caps=data;render();}).catch(()=>{});
})();
