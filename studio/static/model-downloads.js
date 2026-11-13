(() => {
  const host=document.getElementById('model-downloads');
  if (!host) return;
  let state=null; let timer=0; let installedIds=null;
  const en=()=>window.h3Lang?.() !== 'tr';
  const t=(tr,eng)=>en()?eng:tr;
  const size=bytes=>!bytes ? '' : bytes>=1000**3 ? (bytes/1000**3).toFixed(1)+' GB' : (bytes/1000**2).toFixed(1)+' MB';
  const messages={
    'storage.busy':['Üretim veya indirme sürüyor; bitince tekrar dene.','Generation or downloading is active; try again when it finishes.'],
    'storage.queueUnknown':['Üretim kuyruğu kontrol edilemedi; silme yapılmadı.','Cannot check the generation queue; nothing was deleted.'],
    'storage.protected':['Sıradaki veya çalışan bir iş bu modeli kullanıyor.','A queued or running job uses this model.'],
    'storage.notFound':['Model zaten silinmiş.','Model has already been removed.'],
    'storage.fileBusy':['Dosya kullanımda (ComfyUI yüklemiş olabilir); daha sonra tekrar dene.','File is in use (ComfyUI may have it loaded); try again later.']
  };
  const groups=[['base','Temel modeller','Base models'],['optional','İsteğe bağlı','Optional'],['lora','LoRA’lar','LoRAs']];
  const el=(tag,props={},...children)=>{const node=Object.assign(document.createElement(tag),props);node.append(...children);return node;};

  async function post(url,body){
    const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
    const data=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(messages[data.detail?.code]?.[en()?1:0] || String(data.detail?.code || data.detail || r.status));
    return data;
  }
  async function run(action){
    try{await action();}catch(error){window.alert(error.message);}
    await load();
  }
  function status(item){
    if(item.active)return item.phase==='verifying'?t('Doğrulanıyor…','Verifying…'):t(`İniyor · %${item.progress}`,`Downloading · ${item.progress}%`);
    if(item.queued)return t('Sırada','Queued');
    if(item.installed)return t('Kurulu','Installed');
    if(item.error)return t('Hata: ','Error: ')+item.error;
    if(item.needs_key)return t('Civitai anahtarı gerekli','Civitai key required');
    return t('Kurulu değil','Not installed');
  }
  function row(item){
    const label=el('div',{style:'flex:1;min-width:0;overflow-wrap:anywhere'},
      el('strong',{textContent:en()?item.label_en:item.label_tr}),
      el('div',{className:'muted',style:'font-size:12px',textContent:[size(item.bytes),en()?item.note_en:item.note_tr,status(item)].filter(Boolean).join(' · ')}));
    if(item.error && !item.installed && !item.active)label.lastChild.style.color='var(--danger, #e66)';
    const button=el('button',{type:'button'});
    if(item.installed){
      button.className='btn-ghost';button.textContent=t('Sil','Delete');button.disabled=state.busy;
      button.onclick=()=>{
        const name=en()?item.label_en:item.label_tr;
        if(!window.confirm(t(`${name} (${size(item.bytes)}) diskten silinsin mi? Gerekirse buradan yeniden kurabilirsin.`,`Delete ${name} (${size(item.bytes)}) from disk? You can reinstall it here later.`)))return;
        button.disabled=true;run(()=>post('/api/models/downloads/delete',{id:item.id}));
      };
    } else {
      button.className='btn-secondary';button.textContent=item.active||item.queued?'…':t('Kur','Install');
      button.disabled=item.active||item.queued;
      button.onclick=()=>{button.disabled=true;run(()=>post('/api/models/downloads/install',{ids:[item.id]}));};
    }
    return el('div',{className:'model-download-row',style:'display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border, #555)'},label,button);
  }
  function render(){
    if(!state)return;
    const expanded=new Set([...host.querySelectorAll('details[open][data-group]')].map(node=>node.dataset.group));
    const first=!host.querySelector('details[data-group]');
    host.replaceChildren();
    host.append(el('h3',{className:'llm-settings-title',textContent:t('Modeller ve indirmeler','Models & downloads')}));
    host.append(el('p',{className:'muted mode-hint',textContent:t(
      'Modelleri buradan kur veya sil. İndirmeler sırayla yapılır, yarıda kalırsa kaldığı yerden devam eder.',
      'Install or delete models here. Downloads run one at a time and resume if interrupted.')}));
    const actions=el('div',{style:'display:flex;gap:8px;flex-wrap:wrap;align-items:center'});
    const all=el('button',{type:'button',className:'btn-secondary',disabled:state.busy||!state.missing,
      textContent:state.missing?t(`Hepsini kur (${state.missing} · ~${size(state.missing_bytes)})`,`Install all (${state.missing} · ~${size(state.missing_bytes)})`):t('Hepsi kurulu','All installed')});
    all.onclick=()=>{
      const msg=t(`${state.missing} öğe (~${size(state.missing_bytes)}) indirilecek. Boş alan: ${size(state.free_bytes)}. Devam edilsin mi?`,
        `${state.missing} items (~${size(state.missing_bytes)}) will be downloaded. Free space: ${size(state.free_bytes)}. Continue?`);
      if(window.confirm(msg)){all.disabled=true;run(()=>post('/api/models/downloads/install',{all:true}));}
    };
    actions.append(all);
    if(state.busy){
      const stop=el('button',{type:'button',className:'btn-ghost',textContent:t('Durdur','Stop')});
      stop.onclick=()=>{stop.disabled=true;run(()=>post('/api/models/downloads/cancel'));};
      actions.append(stop);
    }
    actions.append(el('span',{className:'muted',style:'font-size:12px',textContent:t('Boş alan: ','Free space: ')+size(state.free_bytes)}));
    host.append(actions);
    const list=el('div',{style:'margin-top:10px'});
    groups.forEach(([id,tr,eng])=>{
      const items=state.items.filter(item=>item.group===id);
      if(!items.length)return;
      const ready=items.filter(item=>item.installed).length;
      const group=el('details',{className:'lora-category',open:first?id==='base':expanded.has(id)},
        el('summary',{textContent:`${en()?eng:tr} · ${ready}/${items.length}`}),
        el('div',{className:'lora-category-items'},...items.map(row)));
      group.dataset.group=id;
      list.append(group);
    });
    host.append(list);
  }
  async function load(){
    clearTimeout(timer);
    try{
      const r=await fetch('/api/models/downloads',{cache:'no-store'});if(!r.ok)throw Error(String(r.status));
      state=await r.json();
      const ids=state.items.filter(item=>item.installed).map(item=>item.id).sort().join('|');
      if(installedIds!==null && ids!==installedIds)window.dispatchEvent(new Event('h3-model-files-changed'));
      installedIds=ids;
      render();
      if(state.busy)timer=setTimeout(load,2000);
    }catch(error){host.textContent=t('Model listesi okunamadı: ','Model list unavailable: ')+error.message;}
  }
  new MutationObserver(()=>render()).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
  window.addEventListener('h3-model-files-changed',()=>{if(!state?.busy)load();});
  load();
})();
