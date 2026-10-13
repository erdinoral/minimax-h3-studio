(() => {
  const $ = id => document.getElementById(id);
  let caps = {}, clip = null, method = 'standard', chunks = 1, layout = 'single', segments = [''], directorBackend='multishot';
  const text = (tr, en) => window.h3Lang?.() === 'en' ? en : tr;
  window.getVideoWorkflowPayload = () => ({continuation_method:method,
    continuum_chunks:layout==='segments'?segments.length:chunks,
    ...(method==='continuum' && layout==='segments'?{continuum_segment_prompts:segments.map(p=>p.trim())}:{}), prepare_refine:false});
  window.getContinuumMainPrompt = () => method==='continuum' && layout==='segments' ? segments[0]?.trim() : null;
  window.getDirectorContinuumBackend = () => directorBackend;
  function updateTotal() {
    const target=$('continuum-total');if(!target)return;
    const selected=document.querySelector('#dur-chips .chip.on');
    let seconds=Number(selected?.dataset.dur)||5;
    const continuing=document.querySelector('#panel-mode-continue')?.classList.contains('hidden')===false;
    const count=layout==='segments'?segments.length:chunks;
    target.textContent=`${count} ${text('bölüm','sections')} × ${seconds} ${text('sn','s')} = ${count*seconds} ${text('sn','s')}${continuing?text(' yeni içerik; önceki diziye eklenir.',' of new content; appended to the previous sequence.'):''}`;
  }
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
    host.innerHTML = `<div class="continuum-heading"><strong>Continuum <small>${text('Deneysel','Experimental')}</small></strong>
      <label class="continuum-toggle"><input id="h3-continuum-toggle" type="checkbox" ${method==='continuum'?'checked':''} ${caps.continuum_ready?'':'disabled'}><span>${method==='continuum'?'ON':'OFF'}</span></label></div>
      <div ${method==='continuum'?'':'hidden'}>
        <div class="continuum-layout"><button type="button" data-layout="single" class="chip ${layout==='single'?'on':''}">${text('Tek prompt','Single prompt')}</button><button type="button" data-layout="segments" class="chip ${layout==='segments'?'on':''}">${text('Bölüm bölüm','Per section')}</button></div>
        ${layout==='single'?`<label>${text('Bölüm sayısı','Sections')} <input id="h3-continuum-chunks" type="number" min="1" max="16" value="${chunks}"></label>`:`<div id="continuum-segments"></div><button type="button" id="continuum-add" class="btn-secondary" ${segments.length>=16?'disabled':''}>+ ${text('Bölüm ekle','Add section')}</button>`}
        <p id="continuum-total" class="muted"></p>
      </div>
      `;
    $('h3-continuum-toggle').onchange=e=>{method=e.target.checked?'continuum':'standard';render();};
    host.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>{layout=b.dataset.layout;render();});
    const count=$('h3-continuum-chunks');
    if(count)count.onchange=e=>{chunks=Math.max(1,Math.min(16,Number(e.target.value)||1));e.target.value=chunks;updateTotal();};
    const cards=$('continuum-segments');
    if(cards)segments.forEach((prompt,i)=>{
      const card=document.createElement('div');card.className='continuum-segment';
      const title=document.createElement('label');title.textContent=`${text('Bölüm','Section')} ${i+1}`;
      const area=document.createElement('textarea');area.value=prompt;area.rows=3;area.placeholder=text('Bu bölümde ne olacak?','What happens in this section?');area.setAttribute('aria-label',title.textContent);area.oninput=e=>{segments[i]=e.target.value;};
      const remove=document.createElement('button');remove.type='button';remove.className='btn-secondary';remove.textContent=text('Kaldır','Remove');remove.disabled=segments.length===1;remove.onclick=()=>{segments.splice(i,1);render();};
      card.append(title,area,remove);cards.append(card);
    });
    if($('continuum-add'))$('continuum-add').onclick=()=>{if(segments.length<16){segments.push('');render();}};
    updateTotal();
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
  document.addEventListener('click',()=>requestAnimationFrame(updateTotal));
  document.addEventListener('h3-lang',render);
  render();fetch('/api/video-workflows').then(r=>r.ok?r.json():{}).then(data=>{caps=data;render();}).catch(()=>{});
})();
