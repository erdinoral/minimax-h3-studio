(() => {
  let configured=false;
  const render=()=>{const el=document.getElementById('lora-access-status');if(el)el.textContent=window.t(configured?'lora.keySaved':'lora.keyNeeded');};
  document.addEventListener('h3-lang',render);
  document.addEventListener('DOMContentLoaded',async()=>{
    try {const response=await fetch('/api/loras/access');if(response.ok)configured=!!(await response.json()).configured;}catch{}
    render();
    try {
      const response=await fetch('/api/film-tools');
      if(response.ok){const data=await response.json(), link=document.getElementById('film-tools-link');if(link&&(data.look_sheets||data.native_av)){link.href=data.comfy_url;link.hidden=false;}}
    }catch{}
    document.getElementById('btn-lora-civitai-key')?.addEventListener('click',async()=>{
      const input=document.getElementById('lora-civitai-key'),button=document.getElementById('btn-lora-civitai-key');
      if(!input.value.trim())return;
      button.disabled=true;
      try {
        const response=await fetch('/api/loras/access',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({civitai_api_key:input.value.trim()})});
        if(!response.ok)throw Error(window.t('err.requestFailed'));
        configured=!!(await response.json()).configured;input.value='';render();
      }catch(e){document.getElementById('lora-access-status').textContent=e.message;}finally{button.disabled=false;}
    });
  });
})();
