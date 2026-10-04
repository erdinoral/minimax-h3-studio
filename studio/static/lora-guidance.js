window.createLoraGuidanceEditor = function (catalog, toast) {
  const t=k=>window.t(`loraGuide.${k}`);
  function translate(){document.querySelectorAll('[data-lora-guide]').forEach(b=>b.textContent=t('title'));}
  translate();document.addEventListener('h3-lang',translate);
  document.addEventListener('click',async e=>{
    const button=e.target.closest('[data-lora-guide]');if(!button)return;
    const ids=[...(document.getElementById(button.dataset.loraGuide)?.selectedOptions||[])].map(o=>o.value);
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
        const triggers=document.createElement('input');triggers.value=data.triggers||'';triggers.maxLength=500;triggerLabel.append(triggers);
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
