/* Select an excerpt before upload; FFmpeg performs the actual trim on the server. */
window.selectReferenceRange = function (file, kind) {
  return new Promise(resolve => {
    const t = k => window.t(`trim.${k}`);
    const dialog = document.createElement('dialog');
    dialog.className = 'media-trim-dialog';
    const title = document.createElement('h3'); title.textContent = t('title');
    const name = document.createElement('p'); name.textContent = file.name;
    const media = document.createElement(kind === 'video' ? 'video' : 'audio');
    media.controls = true; media.preload = 'metadata';
    const url = URL.createObjectURL(file); media.src = url;
    const canvas = document.createElement('canvas'); canvas.width=600; canvas.height=90;
    canvas.setAttribute('aria-label',file.name); canvas.hidden=true;
    const status = document.createElement('p'); status.setAttribute('role','status');
    const controls = document.createElement('div');
    const inputs = {};
    for (const key of ['start','end']) {
      const label=document.createElement('label');label.textContent=t(key);
      const number=document.createElement('input');number.type='number';number.step='0.01';number.min='0';number.disabled=true;
      const slider=document.createElement('input');slider.type='range';slider.step='0.01';slider.min='0';slider.disabled=true;
      number.setAttribute('aria-label',t(key));slider.setAttribute('aria-label',t(key));
      label.append(number,slider);controls.append(label);inputs[key]={number,slider};
    }
    const actions=document.createElement('div');actions.className='row-btns';
    const use=document.createElement('button');use.type='button';use.textContent=t('use');use.disabled=true;
    const full=document.createElement('button');full.type='button';full.textContent=t('full');
    const cancel=document.createElement('button');cancel.type='button';cancel.textContent=t('cancel');
    actions.append(use,full,cancel);
    for(const button of [use,full,cancel])button.className='btn-secondary';
    const quick=document.createElement('div');quick.className='row-btns';
    let duration=0, start=0, end=0, done=false;
    function sync() {
      const valid=Number.isFinite(start)&&Number.isFinite(end)&&start>=0&&end<=duration&&end-start>=0.1&&end-start<=15;
      use.disabled=!valid;
      for(const key of ['start','end']) {const value=key==='start'?start:end;inputs[key].number.value=String(Math.round(value*100)/100);inputs[key].slider.value=String(value);}
    }
    for(const seconds of [3,5,10]) {
      const b=document.createElement('button');b.type='button';b.textContent=`${seconds}s`;
      b.className='btn-secondary';
      b.onclick=()=>{if(!duration)return;start=Math.min(start,Math.max(0,duration-seconds));end=Math.min(duration,start+seconds);media.pause();media.currentTime=start;sync();};quick.append(b);
    }
    for(const key of ['start','end']) for(const input of Object.values(inputs[key])) {
      input.addEventListener('input',()=>{const value=Number(input.value);if(key==='start')start=value;else end=value;media.pause();if(Number.isFinite(start)&&start>=0&&start<=duration)media.currentTime=start;sync();});
    }
    function finish(value) {
      if(done)return;done=true;clearTimeout(timer);media.pause();media.removeAttribute('src');media.load();URL.revokeObjectURL(url);dialog.close();dialog.remove();resolve(value);
    }
    const timer=setTimeout(()=>{if(!duration&&!done)status.textContent=t('failed');},10000);
    use.onclick=()=>{if(!use.disabled)finish({start,end});};
    full.onclick=()=>finish({});cancel.onclick=()=>finish(null);
    dialog.addEventListener('cancel',e=>{e.preventDefault();finish(null);});
    media.addEventListener('play',()=>{if(duration && (media.currentTime<start||media.currentTime>=end))media.currentTime=start;});
    media.addEventListener('timeupdate',()=>{if(!media.paused&&media.currentTime>=end)media.pause();});
    media.addEventListener('error',()=>{status.textContent=t('failed');});
    media.addEventListener('loadedmetadata',()=>{
      if(done||!Number.isFinite(media.duration)||media.duration<=0)return;
      clearTimeout(timer);duration=media.duration;end=Math.min(duration,15);status.textContent=`${duration.toFixed(2)}s · ${file.name}`;
      for(const pair of Object.values(inputs))for(const input of Object.values(pair)){input.disabled=false;input.max=String(duration);}
      sync();
    },{once:true});
    dialog.append(title,name,media,canvas,status,controls,quick,actions);document.body.append(dialog);dialog.showModal();cancel.focus();
    // A bounded waveform overview is optional; trimming still works if decoding fails.
    if(kind==='audio' && file.size<=40*1024*1024) void (async()=>{
      let ctx;
      try{
        ctx=new (window.AudioContext||window.webkitAudioContext)();
        const audio=await ctx.decodeAudioData(await file.arrayBuffer());if(done)return;
        const samples=audio.getChannelData(0),draw=canvas.getContext('2d');
        draw.strokeStyle=getComputedStyle(dialog).color;draw.beginPath();
        const step=Math.max(1,Math.floor(samples.length/canvas.width));
        for(let x=0;x<canvas.width;x++){let peak=0;for(let j=x*step;j<Math.min(samples.length,(x+1)*step);j+=Math.max(1,Math.floor(step/100)))peak=Math.max(peak,Math.abs(samples[j]));draw.moveTo(x,45-peak*42);draw.lineTo(x,45+peak*42);}
        draw.stroke();canvas.hidden=false;
      }catch{}finally{if(ctx)void ctx.close().catch(()=>{});}
    })();
    if(kind==='video') void (async()=>{
      const sampler=document.createElement('video');sampler.muted=true;sampler.preload='auto';sampler.src=url;
      function event(name, change) {
        return new Promise((resolve,reject)=>{
          const clean=()=>{clearTimeout(timeout);sampler.removeEventListener(name,ok);sampler.removeEventListener('error',fail);};
          const ok=()=>{clean();resolve();},fail=()=>{clean();reject(Error('Preview unavailable'));};
          const timeout=setTimeout(fail,5000);sampler.addEventListener(name,ok,{once:true});sampler.addEventListener('error',fail,{once:true});if(change)change();
        });
      }
      try{
        await event('loadeddata',()=>sampler.load());
        if(done||!Number.isFinite(sampler.duration)||!sampler.videoWidth)return;
        const draw=canvas.getContext('2d');canvas.height=90;
        for(let i=0;i<6;i++){
          if(done)return;
          await event('seeked',()=>{sampler.currentTime=Math.min(sampler.duration-0.01,Math.max(0.001,sampler.duration*(i+0.5)/6));});
          if(done)return;
          draw.drawImage(sampler,i*100,0,100,90);
        }
        canvas.hidden=false;
      }catch{}finally{sampler.removeAttribute('src');sampler.load();}
    })();
  });
};
