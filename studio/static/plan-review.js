/* Review is read-only; repairs are previews until explicitly applied. */
window.createPlanReview = function (api) {
  let report = null, preview = null, busy = false, baseline = '';
  const selected = new Set();
  const host = document.getElementById('cinema-plan-review');
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const t = k => window.t(`review.${k}`);
  const snapshot = () => JSON.stringify({...api.get(), updated_at: undefined});
  const error = data => { const key = String(data.detail || 'review.failed'); return window.t(key) || key; };
  async function post(path, body) {
    const r = await fetch(`/api/cinema/review${path}`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data = await r.json(); if (!r.ok) throw Error(error(data)); return data;
  }
  function render() {
    if (!host) return;
    const summary=host.parentElement?.querySelector('summary');
    if(summary)summary.textContent=t('title');
    if (report && snapshot() !== baseline) { report = null; preview = null; selected.clear(); }
    const rows = report?.issues || [];
    const shots = api.get().shots || [];
    host.innerHTML = `<div class="row-btns"><button type="button" data-review="basic" ${busy?'disabled':''}>${esc(t('check'))}</button><button type="button" data-review="ai" ${busy?'disabled':''}>${esc(t('ai'))}</button>${report?`<button type="button" data-review="draft" ${busy||!selected.size?'disabled':''}>${esc(t('draft'))}</button>`:''}</div><p role="status">${esc(busy?t('working'):report?(rows.length?t('flagged').replace('{n}',String(rows.length)):t(report.semantic?'clear':'basicClear')):t('hint'))}</p>
      ${rows.map(row=>{const s=shots.find(s=>s.id===row.shot_id);const i=shots.indexOf(s)+1;const msg=row.message.startsWith('review.')?window.t(row.message):row.message;return `<div class="plan-review-issue"><label><input type="checkbox" data-review-shot="${esc(row.shot_id)}" ${selected.has(row.shot_id)?'checked':''} ${busy||!row.repairable?'disabled':''}>${esc(t('shot').replace('{n}',String(i)))}: ${esc(msg)}</label>${row.evidence?`<blockquote>${esc(row.evidence)}</blockquote>`:''}</div>`;}).join('')}
      ${preview?`<h4>${esc(t('preview'))}</h4>${Object.entries(preview.patches).map(([id,text])=>`<details><summary>${esc(t('shot').replace('{n}',String(shots.findIndex(s=>s.id===id)+1)))}</summary><div class="plan-review-compare"><div><b>${esc(t('before'))}</b><pre>${esc(shots.find(s=>s.id===id)?.text)}</pre></div><div><b>${esc(t('after'))}</b><pre>${esc(text)}</pre></div></div></details>`).join('')}<div class="row-btns"><button type="button" data-review="apply" ${busy||!selected.size?'disabled':''}>${esc(t('apply'))}</button><button type="button" data-review="discard" ${busy?'disabled':''}>${esc(t('discard'))}</button></div>`:''}`;
    host.querySelectorAll?.('button').forEach(button=>button.classList.add('btn-secondary'));
  }
  host?.addEventListener('change', e => {
    const id = e.target.dataset.reviewShot;
    if (!id || busy) return;
    if (e.target.checked) selected.add(id); else selected.delete(id);
    preview = null; render();
  });
  host?.addEventListener('click', async e => {
    const action = e.target.closest('button')?.dataset.review;
    if (!action || busy) return;
    if (action === 'discard') { preview = null; render(); return; }
    busy = true; render();
    try {
      if (action === 'basic' || action === 'ai') {
        report=null; preview=null; selected.clear();
        await api.save();
        const start = snapshot();
        const result = await post('',{film_id:api.get().film_id,semantic:action==='ai',lang:window.h3Lang?.()||'tr',lora_names:api.get().active_lora_names||[]});
        if (snapshot() !== start) throw Error(t('stale'));
        report=result; baseline=start;
        result.issues.filter(r=>r.repairable).slice(0,20).forEach(r=>selected.add(r.shot_id));
      } else {
        if (!report || snapshot() !== baseline) throw Error(t('stale'));
        const ids = [...selected];
        if (action === 'draft') {
          const result = await post('/draft',{checkpoint:report.checkpoint,shot_ids:ids});
          if (snapshot() !== baseline) throw Error(t('stale'));
          preview=result;
        }
        if (action === 'apply' && preview) {
          api.lock?.(true);
          const result = await post('/apply',{checkpoint:report.checkpoint,shot_ids:ids});
          api.replace(result.cinema); report=null; preview=null; selected.clear();
          api.toast(t('applied'));
        }
      }
    } catch (err) { api.toast(err.message); }
    finally {api.lock?.(false);busy=false;render();}
  });
  document.addEventListener('h3-lang',render);
  render();
  return {render};
};
