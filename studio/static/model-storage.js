(() => {
  const host=document.getElementById('model-storage');
  if (!host) return;
  let files=[];
  const en=()=>window.h3Lang?.()==='en';
  const size=bytes=>bytes>=1024**3 ? (bytes/1024**3).toFixed(1)+' GB' : (bytes/1024**2).toFixed(1)+' MB';
  const messages={
    'storage.busy':['Üretim veya indirme sürüyor; bitince tekrar dene.','Generation or downloading is active; try again when it finishes.'],
    'storage.queueUnknown':['Üretim kuyruğu kontrol edilemedi; silme yapılmadı.','Cannot check the generation queue; nothing was deleted.'],
    'storage.protected':['Aktif veya temel kurulum dosyası silinemez.','Active or required base files cannot be deleted.'],
    'storage.notFound':['Dosya zaten silinmiş.','File has already been removed.'],
    'storage.fileBusy':['Dosya kullanımda; daha sonra tekrar dene.','File is in use; try again later.'],
    'storage.invalidFile':['Geçersiz model dosyası.','Invalid model file.']
  };
  function render() {
    host.replaceChildren();
    const title=document.createElement('h3');title.textContent=en()?'Model storage':'Model depolama';host.append(title);
    const hint=document.createElement('p');hint.className='muted';hint.textContent=en()?'Delete downloaded weights to free disk space. Active and required base files are protected.':'Diskte yer açmak için indirilen ağırlıkları sil. Aktif motor ve temel kurulum dosyaları korunur.';host.append(hint);
    const refresh=document.createElement('button');refresh.type='button';refresh.className='btn-secondary';refresh.textContent=en()?'Refresh':'Yenile';refresh.onclick=load;host.append(refresh);
    const list=document.createElement('div');list.style.cssText='max-height:340px;overflow:auto;margin-top:12px';host.append(list);
    let folder='';
    files.forEach(file=>{
      if(folder!==file.folder){folder=file.folder;const heading=document.createElement('h4');heading.textContent=folder==='loras'?'LoRA':folder;list.append(heading);}
      const row=document.createElement('div');row.style.cssText='display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border, #555)';
      const label=document.createElement('span');label.style.cssText='flex:1;min-width:0;overflow-wrap:anywhere';label.textContent=file.file+' · '+size(file.bytes);row.append(label);
      const del=document.createElement('button');del.type='button';del.className='btn-ghost';del.disabled=file.protected;del.textContent=file.protected?(en()?'Protected':'Korumalı'):(en()?'Delete':'Sil');
      del.onclick=async()=>{
        if(!window.confirm(en()?`Delete ${file.file} (${size(file.bytes)}) from disk?`:`${file.file} (${size(file.bytes)}) diskten silinsin mi?`))return;
        del.disabled=true;
        try {
          const r=await fetch('/api/models/storage/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:file.folder,file:file.file})});
          const data=await r.json();if(!r.ok)throw Error(messages[data.detail?.code]?.[en()?1:0] || String(data.detail || 'Error'));
          window.dispatchEvent(new Event('h3-model-files-changed'));await load();
        } catch(error){window.alert(error.message);del.disabled=false;}
      };
      row.append(del);list.append(row);
    });
  }
  async function load(){
    try{const r=await fetch('/api/models/storage',{cache:'no-store'});if(!r.ok)throw Error(String(r.status));files=(await r.json()).files || [];render();}
    catch(error){host.textContent=(en()?'Storage unavailable: ':'Depolama okunamadı: ')+error.message;}
  }
  new MutationObserver(()=>render()).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
  window.addEventListener('h3-model-files-changed',load);
  load();
})();
