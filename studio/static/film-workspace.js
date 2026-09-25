/* Film workspace: selections are explicit; imported Markdown is data only. */
window.createFilmWorkspace = function (api) {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let sceneFilter = '';
  let chapter = '', filmId = '', active = '', importData = null;
  const history = [];
  let host;
  const groups = [['characters', 'characters'], ['creatures', 'creatures'], ['vehicles', 'vehicles'], ['locations', 'locations']];
  const w = key => window.t(`film.ws.${key}`);
  const wn = (key, n) => w(key).replace('{n}', String(n));
  const chapterDisplay = name => {
    const match = /^Bölüm (\d+)$/.exec(name) || /^Sahne (\d+)$/.exec(name);
    return match && window.h3Lang?.() === 'en' ? wn('chapterDefault', match[1]) : name;
  };
  const clone = x => JSON.parse(JSON.stringify(x));
  const assets = () => groups.flatMap(([key]) => (api.get()[key] || []).map(a => ({...a, kind:key.slice(0,-1)})));
  const snapshot = a => { const snap=clone(a); const parent=assets().find(x=>x.id===a.identity_id && x.id!==a.id); if(parent)snap.identity_reference=clone(parent); return snap; };
  const shot = () => api.get().shots.find(s => s.id === active);
  const chapterOf = s => s.chapter || 'Bölüm 1';
  const busy = s => (api.jobs() || []).some(j => j.shot_id === s.id && (!j.film_id || j.film_id === api.get().film_id) && ['queued','running','processing','uploading'].includes(j.status));
  const reviewLabel = s => s.review === 'approved' ? w('approved') : busy(s) ? w('producing') : s.review === 'review' || s.review === 'producing' ? w('review') : w('draft');
  function checkpoint() { history.push(clone(api.get().shots)); if (history.length > 30) history.shift(); }
  async function save() { await api.save(); render(); }
  /** Native window.prompt mangles Turkish on some Windows/WebView builds — use UTF-8 HTML dialog. */
  function askText(title, value) {
    return new Promise(resolve => {
      const dialog = document.createElement('dialog');
      dialog.className = 'film-import-dialog';
      dialog.innerHTML = `<h2>${esc(title)}</h2><label>${esc(title)}<input id="film-ask-text" value="${esc(value || '')}"></label><button data-ask="cancel" type="button">${esc(window.t('cinema.sceneCancel'))}</button><button data-ask="ok" type="button">${esc(w('ok'))}</button>`;
      let done = false;
      const finish = (result) => {
        if (done) return;
        done = true;
        dialog.close();
        dialog.remove();
        resolve(result);
      };
      dialog.addEventListener('cancel', ev => { ev.preventDefault(); finish(null); });
      dialog.addEventListener('click', ev => {
        const act = ev.target.dataset?.ask;
        if (act === 'cancel') finish(null);
        if (act === 'ok') finish(dialog.querySelector('#film-ask-text')?.value || '');
      });
      dialog.addEventListener('keydown', ev => {
        if (ev.key === 'Enter') { ev.preventDefault(); finish(dialog.querySelector('#film-ask-text')?.value || ''); }
      });
      document.body.append(dialog);
      dialog.showModal();
      const input = dialog.querySelector('#film-ask-text');
      input?.focus();
      input?.select();
    });
  }
  function invalidate(s) {
    s.review = 'draft'; s.approved_signature = '';
    const list = api.get().shots, i = list.indexOf(s);
    for (let n=i+1;n<list.length && list[n].mode==='continue';n++) { list[n].review='review'; }
  }
  function render() {
    host = document.getElementById('film-workspace');
    if (!host) return;
    const film = api.get();
    if (filmId !== film.film_id) { filmId=film.film_id; chapter=''; sceneFilter=''; active=''; history.length=0; }
    const films = typeof api.films === 'function' ? (api.films() || []) : [];
    const chapters = [...new Set((film.shots || []).map(chapterOf))];
    if (!chapters.includes(chapter)) chapter=chapters[0] || 'Bölüm 1';
    const inChapter=(film.shots || []).filter(s => chapterOf(s)===chapter);
    const scenes=[...new Set(inChapter.map(s=>s.scene).filter(Boolean))];
    if(sceneFilter && !scenes.includes(sceneFilter))sceneFilter='';
    const visible=inChapter.filter(s=>!sceneFilter||s.scene===sceneFilter);
    if (!visible.some(s=>s.id===active)) active=visible[0]?.id || '';
    const s=shot();
    const jobs=api.jobs().filter(j=>j.shot_id===active && (!j.film_id || j.film_id===film.film_id));
    const selected=jobs.find(j=>j.id===s?.selected_job) || (s?.selected_job?{id:s.selected_job,status:'done'}:null) || [...jobs].reverse().find(j=>j.status==='done');
    const url=selected?.status==='done' ? `/api/gallery/${encodeURIComponent(selected.id)}/video` : '';
    // Preserve the playing video and focused edits during background refreshes.
    if (host.contains(document.activeElement) && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
    const video=host.querySelector('video'); const time=video?.currentTime||0, playing=video && !video.paused;
    host.innerHTML = `<div class="film-toolbar">
      <strong>${esc(w('title'))}</strong><span id="film-save-state" role="status">${esc(api.saveStatus())}</span>
      <button data-film="undo" ${history.length?'':'disabled'}>${esc(w('undo'))}</button>
      <label class="film-import">${esc(w('import'))}<input type="file" accept=".md,.txt" data-film="import" hidden></label>
      <button data-film="library">${esc(w('library'))}</button><button data-film="save-lib">${esc(w('saveLibrary'))}</button>
      <button data-film="queue">${esc(w('queue'))}</button></div>
      <div class="film-layout"><nav aria-label="${esc(w('chapters'))}">
      ${films.length ? `<h3>${esc(w('films'))}</h3>${films.map(f=>`<button data-film-id="${esc(f.id)}" class="${f.id===film.film_id?'selected':''}">${esc(f.title||f.id)}<small>${esc(f.meta||'')}</small></button>`).join('')}` : ''}
      <h3>${esc(w('chapters'))}</h3>${chapters.map(c=>`<button data-chapter="${esc(c)}" class="${c===chapter?'selected':''}">${esc(chapterDisplay(c))}<small>${esc(wn('shotCount', film.shots.filter(x=>chapterOf(x)===c).length))}</small></button>`).join('')}
      <button data-film="chapter">${esc(w('addChapter'))}</button>
      ${scenes.length ? `<h3>${esc(w('scenes'))}</h3><button data-scene="">${esc(w('allScenes'))}</button>${scenes.map(name=>`<button data-scene="${esc(name)}" class="${sceneFilter===name?'selected':''}">${esc(name)}</button>`).join('')}` : ''}
      <p>${esc(wn('totalShots', film.shots.length))}</p></nav>
      <section class="film-stage"><div class="film-stage-head"><h3>${esc(chapterDisplay(chapter))}</h3><button data-film="produce-chapter">${esc(w('produceChapter'))}</button></div>
      ${!url && s?.first_frame_name ? `<img class="film-start-frame" src="/api/refs/${encodeURIComponent(s.first_frame_name)}" alt="${esc(w('startFrameAlt'))}">` : url ? `<video controls preload="metadata" src="${esc(url)}"></video>` : `<div class="film-preview-placeholder">${esc(w(s ? 'previewHint' : 'addHint'))}</div>`}
      <div class="film-shot-strip">${visible.map((x,i)=>`<button data-shot="${esc(x.id)}" class="${x.id===active?'selected':''}"><b>${esc(wn('shot', i+1))}</b><span>${esc(x.text?.slice(0,58)||w('newShot'))}</span><small>${esc(reviewLabel(x))}</small></button>`).join('')}</div>
      <button data-film="add">${esc(w('addShot'))}</button>${s ? `<button data-film="up">${esc(w('moveLeft'))}</button><button data-film="down">${esc(w('moveRight'))}</button><button data-film="duplicate">${esc(w('duplicate'))}</button><button data-film="delete">${esc(w('removeShot'))}</button>` : ''}
      ${s ? `<div class="film-takes"><label>${esc(w('alternateTake'))} <select data-film="take"><option value="">${esc(w('latestFinished'))}</option>${jobs.filter(j=>j.status==='done').map((j,i)=>`<option value="${esc(j.id)}" ${s.selected_job===j.id?'selected':''}>${esc(wn('shot', i+1))} · ${esc(j.id.slice(0,8))}</option>`).join('')}</select></label><button data-film="approve" ${selected?'':'disabled'}>${esc(w('approve'))}</button><button data-film="produce-shot">${esc(w('produceAlternate'))}</button></div>` : ''}</section>
      <aside class="film-inspector">${s ? `<h3>${esc(w('references'))}</h3><label class="film-import">${esc(w('uploadFrame'))}<input type="file" accept="image/png,image/jpeg,image/webp" data-film="frame" hidden></label>${s.first_frame_name ? `<small>${esc(s.first_frame_name)}</small><button data-film="clear-frame">${esc(w('removeFrame'))}</button>` : ''}<label>${esc(w('sceneName'))}<input data-film="scene" value="${esc(s.scene)}" placeholder="${esc(w('scenePlaceholder'))}"></label><label>${esc(w('action'))}<textarea data-film="text" rows="4">${esc(s.text)}</textarea></label><label>${esc(w('link'))}<select data-film="mode"><option value="t2v" ${s.mode!=='continue'?'selected':''}>${esc(w('newTake'))}</option><option value="continue" ${s.mode==='continue'?'selected':''}>${esc(w('continueTake'))}</option></select></label>
      ${!Array.isArray(s.bindings) ? `<p class="film-warning">${esc(w('legacyBindings'))}</p><button data-film="explicit">${esc(w('pickReferences'))}</button>` : ''}
      ${groups.map(([key,label])=>`<fieldset><legend>${esc(w(label))}</legend>${(film[key]||[]).map(a=>{
        const b=s.bindings?.find(b=>b.asset_id===a.id), snap=b?.snapshot||a, ims=snap.images||[];
        return `<div class="film-asset"><label><input type="checkbox" data-asset="${esc(a.id)}" ${b?'checked':''} ${!Array.isArray(s.bindings)?'disabled':''}>${esc(a.name)}${a.appearance&&a.appearance!=='Ana görünüm'?` · ${esc(a.appearance)}`:''}</label>${b?`<div class="film-ref-images">${snap.identity_reference?.images?.[0]?`<label><img src="${esc(snap.identity_reference.images[0].url||'/api/refs/'+encodeURIComponent(snap.identity_reference.images[0].file))}" alt="${esc(w('mainFace'))}"><small>${esc(w('mainFace'))}</small></label>`:''}${ims.map(im=>`<label><img src="${esc(im.url||'/api/refs/'+encodeURIComponent(im.file))}" alt="${esc(im.name||a.name)}"><input type="checkbox" data-ref="${esc(im.file)}" data-owner="${esc(a.id)}" ${!b.files||b.files.includes(im.file)?'checked':''}></label>`).join('')}</div>${!ims.length?`<p class="film-warning">${esc(w('missingReference'))}</p>`:''}<small>${esc(w(b.snapshot?'referenceLocked':'referencePending'))}</small><button data-refresh="${esc(a.id)}">${esc(w('refreshReferences'))}</button>`:''}</div>`;
      }).join('') || `<p>${esc(w('noCards'))} <button type="button" data-film="library">${esc(w('library'))}</button> ${esc(w('addToFilm'))}</p>`}</fieldset>`).join('')}
      <p class="film-warning">${esc(w('cardsHint'))}</p>` : `<p>${esc(w('pickShot'))}</p>`}</aside></div>`;
    const next=host.querySelector('video'); if(next && video?.getAttribute('src')===next.getAttribute('src')) {next.addEventListener('loadedmetadata',()=>{next.currentTime=time;if(playing) void next.play().catch(()=>{});},{once:true});}
    api.filter(chapter,active);
  }
  async function change(e) {
    const el=e.target, action=el.dataset.film, s=shot();
    if(action==='import') {
      const file=el.files?.[0]; if(!file)return;
      try {
        if(file.size>1000000)throw Error(w('fileTooLarge'));
        const r=await fetch('/api/cinema/outline-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:await file.text()})});
        const data=await r.json();if(!r.ok)throw Error(data.detail||w('fileReadError'));importData=data;
        const dialog=document.createElement('dialog');dialog.className='film-import-dialog';
        dialog.innerHTML=`<h2>${esc(w('previewImport'))}</h2><p>${esc(data.title)}</p><p>${esc(wn('shotCount',data.shots.length))} · ${esc(wn('chapterCount',new Set(data.shots.map(chapterOf)).size))} · ${groups.map(([k,l])=>`${data[k].length} ${esc(w(l).toLowerCase())}`).join(' · ')}</p><p>${esc(w('importHint'))}</p><label>${esc(w('filmName'))}<input id="film-import-title" value="${esc(data.title)}"></label><label>${esc(w('shotPreview'))}<textarea readonly rows="9">${esc(data.shots.map((s,i)=>`${i+1}. ${chapterDisplay(s.chapter)}\n${s.text}`).join('\n\n'))}</textarea></label>${data.warnings.map(w=>`<p>${esc(w)}</p>`).join('')}<button data-import="cancel">${esc(window.t('cinema.sceneCancel'))}</button><button data-import="apply">${esc(w('openAsNew'))}</button>`;
        document.body.append(dialog);dialog.showModal();dialog.addEventListener('close',()=>dialog.remove());
        dialog.addEventListener('click',async ev=>{if(ev.target.dataset.import==='cancel')dialog.close();if(ev.target.dataset.import==='apply'){ev.target.disabled=true;try{importData.title=dialog.querySelector('input').value;await api.importFilm(importData);dialog.close();render();}catch(err){api.toast(err.message);ev.target.disabled=false;}}});
      }catch(err){api.toast(err.message);}return;
    }
    if(!s)return;
    checkpoint();
    if(action==='frame'){
      const file=el.files?.[0];if(!file)return;
      const data=new FormData();data.append('file',file);
      const r=await fetch('/api/refs/upload',{method:'POST',body:data}),body=await r.json();
      if(!r.ok)throw Error(body.detail||w('uploadError'));
      s.first_frame_name=body.name;invalidate(s);await save();return;
    }
    if(['scene','text','mode'].includes(action)){s[action]=el.value;invalidate(s);}
    if(action==='take'){s.selected_job=el.value;s.review='review';}
    if(el.dataset.asset){
      const a=assets().find(a=>a.id===el.dataset.asset);
      s.bindings=s.bindings||[];
      if(el.checked){s.bindings=s.bindings.filter(b=>{const other=assets().find(x=>x.id===b.asset_id);return (other?.identity_id||other?.id)!==(a.identity_id||a.id);});s.bindings.push({asset_id:a.id,...(a.images?.length?{snapshot:snapshot(a),files:a.images.map(im=>im.file)}:{})});}
      else s.bindings=s.bindings.filter(b=>b.asset_id!==a.id);
      invalidate(s);
    }
    if(el.dataset.ref){const b=s.bindings.find(b=>b.asset_id===el.dataset.owner);b.files=b.files||b.snapshot.images.map(im=>im.file);b.files=el.checked?[...new Set([...b.files,el.dataset.ref])]:b.files.filter(f=>f!==el.dataset.ref);invalidate(s);}
    await save();
  }
  async function click(e){
    const el=e.target.closest('button');if(!el)return;
    if(el.dataset.filmId){
      if(el.dataset.filmId===api.get().film_id)return;
      if(typeof api.switchFilm==='function') await api.switchFilm(el.dataset.filmId);
      render();
      return;
    }
    if(el.dataset.chapter){chapter=el.dataset.chapter;sceneFilter='';active='';render();return;}
    if(el.hasAttribute('data-scene')){sceneFilter=el.dataset.scene;active='';render();return;}
    if(el.dataset.shot){active=el.dataset.shot;api.select(active);render();return;}
    const action=el.dataset.film,s=shot();
    if(action==='queue'){document.body.classList.toggle('film-queue-open');return;}
    if(action==='library'){
      if(typeof api.openLibrary==='function') api.openLibrary();
      return;
    }
    if(action==='save-lib'){
      if(typeof api.saveAllToLibrary==='function') await api.saveAllToLibrary();
      return;
    }
    if(action==='produce-chapter'||action==='produce-shot'){
      const selected=api.get().shots.filter(x=>action==='produce-shot'?x.id===active:chapterOf(x)===chapter);
      selected.forEach(x=>{ if(x.review!=='approved') x.review='producing'; });
      await api.produce(selected);render();return;
    }
    if(action==='chapter'){
      const name=await askText(w('chapterName'), wn('chapterDefault',new Set(api.get().shots.map(chapterOf)).size+1));
      if(!name?.trim())return;
      chapter=name.trim();
    }
    if(action==='add'||action==='chapter'){checkpoint();const x={id:crypto.randomUUID?.() || Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join(''),text:'',mode:'t2v',chapter,scene:sceneFilter,bindings:[],review:'draft'};api.get().shots.push(x);active=x.id;await save();return;}
    if(action==='undo'){if(history.length){api.get().shots=history.pop();await save();}return;}
    if(!s)return;
    if(['up','down','delete','duplicate'].includes(action)){
      checkpoint();const list=api.get().shots,i=list.indexOf(s);
      if(action==='delete'){list.splice(i,1);active='';}
      if(action==='duplicate'){const dupe=clone(s);dupe.id=String(Date.now())+'-'+Math.random().toString(36).slice(2);dupe.selected_job='';dupe.review='draft';dupe.approved_signature='';list.splice(i+1,0,dupe);active=dupe.id;}
      if(action==='up'||action==='down'){const n=i+(action==='up'?-1:1);if(list[n]&&chapterOf(list[n])===chapter){[list[i],list[n]]=[list[n],list[i]];invalidate(s);invalidate(list[i]);}}
      await save();return;
    }
    if(action==='clear-frame'){checkpoint();s.first_frame_name='';invalidate(s);await save();}
    if(action==='explicit'){checkpoint();s.bindings=[];invalidate(s);await save();}
    if(el.dataset.refresh){checkpoint();const b=s.bindings.find(b=>b.asset_id===el.dataset.refresh),a=assets().find(a=>a.id===el.dataset.refresh);if(a){b.snapshot=snapshot(a);b.files=(a.images||[]).map(im=>im.file);invalidate(s);await save();}}
    if(action==='approve'){const jobs=api.jobs().filter(j=>j.shot_id===s.id&&j.status==='done');const j=jobs.find(j=>j.id===s.selected_job)||jobs.at(-1);if(j){checkpoint();if(api.approve){const approved=await api.approve(s,j);Object.assign(shot(),approved);render();}else{s.selected_job=j.id;s.approved_signature=j.shot_signature||'';s.review='approved';await save();}}}
  }
  document.addEventListener('change',e=>{if(e.target.closest('#film-workspace'))void change(e).catch(err=>api.toast(err.message));});
  document.addEventListener('click',e=>{if(e.target.closest('#film-workspace'))void click(e).catch(err=>api.toast(err.message));});
  document.addEventListener('h3-lang', () => render());
  return {render, currentChapter:()=>chapter, active:()=>active};
};
