(() => {
  const $ = id => document.getElementById(id);
  let caps = {}, clip = null, method = 'standard', chunks = 1, layout = 'single', segments = [''], context = '', continuity = 'balanced';
  let sourceId = null, sourceMeta = null;
  try { localStorage.removeItem('h3.prepareRefine'); } catch {}
  const text = (tr, en) => window.h3Lang?.() === 'en' ? en : tr;
  window.getVideoWorkflowPayload = () => ({continuation_method:method,
    continuum_context:context, continuum_continuity:continuity, continuum_chunks:layout==='segments'?segments.length:chunks,
    ...(method==='continuum' && layout==='segments'?{continuum_segment_prompts:segments.map(p=>p.trim())}:{}), prepare_refine:false});
  window.getContinuumMainPrompt = () => method==='continuum' && layout==='segments' ? segments[0]?.trim() : null;
  window.getDirectorContinuumBackend = () => "continuum";
  window.isDirectorContinuumReady = () => caps.continuum_ready === true;
  window.canSetContinueReferences = () => !(method==='continuum' && sourceMeta?.continuum_run);
  function updateTotal() {
    if($('continue-reference-inputs')) $('continue-reference-inputs').hidden=!window.canSetContinueReferences();
    const target=$('continuum-total');if(!target)return;
    const selected=document.querySelector('#dur-chips .chip.on');
    let seconds=Number(selected?.dataset.dur)||5;
    const continuing=document.querySelector('#panel-mode-continue')?.classList.contains('hidden')===false;
    if(continuing && sourceMeta?.continuum_chunk_seconds)seconds=sourceMeta.continuum_chunk_seconds;
    for(const id of ['continuum-context','continuum-continuity']){
      const control=$(id);if(control)control.disabled=continuing && !!sourceMeta?.continuum_run;
    }
    if(continuing && sourceMeta?.continuum_run){
      context=sourceMeta.continuum_context || ''; continuity=sourceMeta.continuum_continuity || 'balanced';
      if($('continuum-context'))$('continuum-context').value=context;
      if($('continuum-continuity'))$('continuum-continuity').value=continuity;
    }
    const count=layout==='segments'?segments.length:chunks;
    if(continuing && sourceMeta?.continuum_prompts){
      const old=sourceMeta.continuum_prompts.length*seconds;
      target.textContent=`${old} ${text('sn mevcut','s existing')} + ${count*seconds} ${text('sn yeni','s new')} = ${old+count*seconds} ${text('sn toplam','s total')}`;
      return;
    }
    target.textContent=`${count} ${text('bölüm','sections')} × ${seconds} ${text('sn','s')} = ${count*seconds} ${text('sn','s')}${continuing?text(' yeni içerik; önceki diziye eklenir.',' of new content; appended to the previous sequence.'):''}`;
  }
  function render() {
    const legacyAudio=$('continue-audio-continuity')?.closest('label');
    if(legacyAudio)legacyAudio.hidden=method==='continuum';
    const host = $('video-workflow-controls');
    if (!host) return;
    const sectionMode = method==='continuum' && layout==='segments';
    if ($('prompt')) $('prompt').hidden=sectionMode;
    if ($('btn-prompt-rewrite')) $('btn-prompt-rewrite').hidden=sectionMode;
    host.closest('.zone-prompt')?.classList.toggle('has-continuum-sections',sectionMode);
    host.innerHTML = `<div class="continuum-heading"><strong>Continuum <small>${text('Deneysel','Experimental')}</small></strong>
      <label class="continuum-toggle"><input id="h3-continuum-toggle" type="checkbox" ${method==='continuum'?'checked':''} ${caps.continuum_ready?'':'disabled'}><span>${method==='continuum'?'ON':'OFF'}</span></label></div>
      <div ${method==='continuum'?'':'hidden'}>
        <div class="continuum-layout"><button type="button" data-layout="single" class="chip ${layout==='single'?'on':''}">${text('Tek prompt','Single prompt')}</button><button type="button" data-layout="segments" class="chip ${layout==='segments'?'on':''}">${text('Bölüm bölüm','Per section')}</button></div>
        ${layout==='single'?`<label>${text('Bölüm sayısı','Sections')} <input id="h3-continuum-chunks" type="number" min="1" max="16" value="${chunks}"></label>`:`<div id="continuum-segments"></div><button type="button" id="continuum-add" class="btn-secondary" ${segments.length>=16?'disabled':''}>+ ${text('Bölüm ekle','Add section')}</button>`}
        <details class="continuum-advanced"><summary>${text('Tutarlılık ayarları','Continuity settings')}</summary>
          <label>${text('Ortak karakter ve ortam','Shared characters and setting')}<textarea id="continuum-context" rows="3"></textarea></label>
          <label>${text('Geçiş bağlamı','Transition context')}<select id="continuum-continuity"><option value="balanced">${text('Dengeli · 22 kare','Balanced · 22 frames')}</option><option value="strong">${text('Güçlü · 39 kare (deneysel)','Strong · 39 frames (experimental)')}</option></select></label>
        </details>
        <p id="continuum-total" class="muted"></p>
      </div>
      `;
    $('h3-continuum-toggle').onchange=e=>{method=e.target.checked?'continuum':'standard';render();};
    host.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>{
      if(b.dataset.layout==='segments' && layout==='single' && segments.length===1 && !segments[0].trim()) segments[0]=$('prompt')?.value || '';
      layout=b.dataset.layout;render();
    });
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
    $('continuum-context').value=context;
    $('continuum-context').oninput=e=>{context=e.target.value;};
    $('continuum-continuity').value=continuity;
    $('continuum-continuity').onchange=e=>{continuity=e.target.value;};
    updateTotal();
    const button = $('btn-h3-refine');
    if (button) {
      button.innerHTML = `H3 Refine <small>${text('Deneysel','Experimental')}</small>`;
      button.disabled = !clip || !caps.video_refine_ready || Math.min(clip.width,clip.height)>=1088;
      button.title = !clip ? text('Önce bir video aç','Open a video first') : !caps.video_refine_ready ? text('Video kalite artırma araçları yüklü değil','Video enhancement tools are unavailable') : Math.min(clip.width,clip.height)>=1088 ? text('Video zaten en yüksek Refine çözünürlüğünde','This video is already at the maximum Refine resolution') : text('Mevcut videoyu AI ile büyüt; ön kayıt gerekmez','Enhance the existing video with AI; no recording required');
      button.onclick = openRefine;
    }
  }
  function openRefine() {
    if (!clip) return;
    const id = clip.id, options = [352,480,608,736,768,1088].filter(q=>q>Math.min(clip.width,clip.height));
    const modal=document.createElement('dialog');modal.className='h3-refine-dialog';
    modal.innerHTML=`<form method="dialog"><h3>H3 Refine · ${text('Kalite artır','Enhance video')}</h3><p>${text('Mevcut MP4 işlenir; önceden kayıt hazırlamak gerekmez. Kaynak korunur, sonuç ayrı video olarak galeriye kaydedilir.','Processes the existing MP4; no prior recording required. The source is preserved and the result becomes a separate Gallery video.')}</p>
    <label>${text('Hedef çözünürlük','Target resolution')} <select>${options.map(q=>{const scale=q/Math.min(clip.width,clip.height), snap=v=>Math.max(32,Math.floor(v/32+0.5)*32);return `<option value="${q}">${q}p · ${snap(clip.width*scale)}×${snap(clip.height*scale)}</option>`;}).join('')}</select></label>
    <p class="muted">${text('H3 için öğrenilmiş 3D latent büyütme kullanılır; yeni sahne üretilmez. Ses ve kare hızı kaynaktan alınır. Sonuç kaynak kalitesine bağlıdır.','Uses H3-trained 3D latent upscaling without generating a new scene. Audio and frame rate come from the source. Results depend on source quality.')}</p>
    <p role="status"></p><div class="row-btns"><button type="button" class="cta">${text('Sıraya ekle','Add to queue')}</button><button class="btn-secondary">${text('Vazgeç','Cancel')}</button></div></form>`;
    document.body.appendChild(modal);modal.onclose=()=>modal.remove();modal.showModal();
    modal.querySelector('button[type=button]').onclick=async event=>{
      event.target.disabled=true;
      try {
        const response=await fetch(`/api/clips/${encodeURIComponent(id)}/refine`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({quality:modal.querySelector('select').value,method:'video'})});
        const data=await response.json();if(!response.ok)throw Error(data.detail || 'Refine failed');
        modal.querySelector('[role=status]').textContent=text('Kuyruğa eklendi; sonuç galeride görünecek.','Queued; the result will appear in Gallery.');
      }catch(error){modal.querySelector('[role=status]').textContent=error.message;event.target.disabled=false;}
    };
  }
  document.addEventListener('h3-player-clip',e=>{clip=e.detail;render();});
  document.addEventListener('change',e=>{if(e.target.id==='cinema-seamless-toggle')render();});
  async function syncSource() {
    const id=$('continue-source')?.value || null;
    if(id===sourceId)return;
    sourceId=id;sourceMeta=null;updateTotal();
    if(!id)return;
    try { const response=await fetch(`/api/jobs/${encodeURIComponent(id)}`);const data=response.ok?await response.json():null;
      if(sourceId===id){sourceMeta=data;updateTotal();}
    } catch {}
  }
  document.addEventListener('change',e=>{if(e.target.id==='continue-source')syncSource();});
  document.addEventListener('click',()=>requestAnimationFrame(()=>{syncSource();updateTotal();}));
  document.addEventListener('h3-lang',render);
  render();fetch('/api/video-workflows').then(r=>r.ok?r.json():{}).then(data=>{caps=data;render();document.dispatchEvent(new Event("h3-video-workflows"));}).catch(()=>{});
})();
