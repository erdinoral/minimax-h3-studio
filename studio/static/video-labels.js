(() => {
  const $ = (id) => document.getElementById(id);
  const t = (key) => (typeof window.t === 'function' ? window.t(key) : key);
  const MAX_LABELS = 12;
  let clip = null;

  function syncButton() {
    const button = $('btn-video-labels');
    if (!button) return;
    button.disabled = !clip?.id;
    button.title = clip?.id ? t('labels.hint') : t('labels.needClip');
  }

  // Same placement rule as lib/video_labels.py layout(); sizes are in source pixels.
  function layout(label, W, H, boxW, boxH) {
    const px = label.x * W, py = label.y * H, margin = Math.round(H * 0.03);
    let left, top;
    if (label.pointer) {
      const gap = Math.round(Math.min(W, H) * 0.08);
      left = label.x < 0.5 ? px + gap : px - gap - boxW;
      top = label.y < 0.5 ? py + gap * 0.5 : py - gap * 0.5 - boxH;
    } else {
      left = px - boxW / 2;
      top = py - boxH / 2;
    }
    left = Math.min(Math.max(margin, left), W - margin - boxW);
    top = Math.min(Math.max(margin, top), H - margin - boxH);
    return [Math.round(left), Math.round(top)];
  }

  function drawLabel(ctx, label, W, H) {
    const size = Math.max(14, Math.min(72, Math.round(H * 0.042)));
    ctx.font = `bold ${size}px "DejaVu Sans", Verdana, sans-serif`;
    const padX = Math.round(size * 0.6), padY = Math.round(size * 0.38);
    const boxW = Math.min(W - 2, Math.ceil(ctx.measureText(label.text).width) + 2 * padX);
    const boxH = Math.round(size * 0.95) + 2 * padY;
    const [left, top] = layout(label, W, H, boxW, boxH);
    if (label.pointer) {
      const px = Math.round(label.x * W), py = Math.round(label.y * H);
      const ax = Math.min(Math.max(px, left), left + boxW), ay = Math.min(Math.max(py, top), top + boxH);
      const line = Math.max(2, Math.round(size * 0.09)), dot = Math.max(4, Math.round(size * 0.22));
      ctx.strokeStyle = 'rgba(255,255,255,.92)';
      ctx.lineWidth = line;
      ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(ax, ay); ctx.stroke();
      ctx.fillStyle = '#fff';
      ctx.beginPath(); ctx.arc(px, py, dot, 0, Math.PI * 2); ctx.fill();
    }
    ctx.fillStyle = 'rgba(12,14,18,.75)';
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(left, top, boxW, boxH, Math.round(size * 0.35));
    else ctx.rect(left, top, boxW, boxH);
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.textBaseline = 'middle';
    ctx.fillText(label.text, left + padX, top + boxH / 2);
  }

  function openEditor() {
    if (!clip?.id) return;
    const id = clip.id;
    let labels = [], active = -1, busy = false;
    const modal = document.createElement('dialog');
    modal.className = 'video-labels-dialog';
    modal.innerHTML = `<form method="dialog">
      <h3>${t('labels.title')}</h3>
      <p class="muted">${t('labels.intro')}</p>
      <div class="vl-stage"><video playsinline preload="auto"></video><canvas></canvas></div>
      <div class="vl-transport"><button type="button" class="btn-secondary vl-play">▶</button><input type="range" class="vl-seek" min="0" step="0.05" value="0"><span class="vl-time">0.0 s</span></div>
      <div class="vl-rows"></div>
      <div class="row-btns"><button type="button" class="btn-secondary vl-add">+ ${t('labels.add')}</button></div>
      <p class="muted vl-tip">${t('labels.tip')}</p>
      <p role="status"></p>
      <div class="row-btns"><button type="button" class="cta vl-apply">${t('labels.apply')}</button><button class="btn-secondary">${t('labels.cancel')}</button></div>
    </form>`;
    document.body.appendChild(modal);
    const video = modal.querySelector('video'), canvas = modal.querySelector('canvas');
    const seek = modal.querySelector('.vl-seek'), timeText = modal.querySelector('.vl-time');
    const rows = modal.querySelector('.vl-rows'), status = modal.querySelector('[role=status]');
    const playButton = modal.querySelector('.vl-play'), addButton = modal.querySelector('.vl-add');
    video.src = `/api/clips/${encodeURIComponent(id)}/video`;
    const duration = () => (Number.isFinite(video.duration) ? video.duration : Number(clip.duration) || 0);

    function draw() {
      const W = video.videoWidth || clip.width || 1280, H = video.videoHeight || clip.height || 720;
      if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, W, H);
      const now = video.currentTime || 0;
      labels.forEach((label, index) => {
        if (!label.text.trim()) return;
        if (index !== active && (now < label.start || now > label.end)) return;
        ctx.globalAlpha = now >= label.start && now <= label.end ? 1 : 0.45;
        drawLabel(ctx, { ...label, text: label.text.trim() }, W, H);
      });
      ctx.globalAlpha = 1;
      seek.value = String(now);
      timeText.textContent = `${now.toFixed(1)} / ${duration().toFixed(1)} s`;
    }

    function renderRows() {
      rows.innerHTML = '';
      labels.forEach((label, index) => {
        const row = document.createElement('div');
        row.className = 'vl-row' + (index === active ? ' on' : '');
        row.innerHTML = `<input type="text" class="vl-text" maxlength="60">
          <label>${t('labels.start')} <input type="number" class="vl-start" min="0" step="0.1"></label>
          <label>${t('labels.end')} <input type="number" class="vl-end" min="0" step="0.1"></label>
          <label class="vl-check"><input type="checkbox" class="vl-pointer"> ${t('labels.pointer')}</label>
          <button type="button" class="btn-secondary vl-remove">${t('labels.remove')}</button>`;
        const textInput = row.querySelector('.vl-text');
        textInput.value = label.text;
        textInput.placeholder = t('labels.placeholder');
        row.querySelector('.vl-start').value = label.start;
        row.querySelector('.vl-end').value = label.end;
        row.querySelector('.vl-pointer').checked = label.pointer;
        row.addEventListener('focusin', () => {
          if (active === index) return;
          active = index;
          rows.querySelectorAll('.vl-row').forEach((el, i) => el.classList.toggle('on', i === index));
          draw();
        });
        textInput.oninput = (e) => { label.text = e.target.value; draw(); };
        row.querySelector('.vl-start').onchange = (e) => { label.start = Math.max(0, Number(e.target.value) || 0); draw(); };
        row.querySelector('.vl-end').onchange = (e) => { label.end = Math.max(label.start + 0.1, Number(e.target.value) || 0); e.target.value = label.end; draw(); };
        row.querySelector('.vl-pointer').onchange = (e) => { label.pointer = e.target.checked; draw(); };
        row.querySelector('.vl-remove').onclick = () => {
          labels.splice(index, 1);
          active = Math.min(active, labels.length - 1);
          renderRows(); draw();
        };
        rows.appendChild(row);
      });
      addButton.disabled = labels.length >= MAX_LABELS;
    }

    addButton.onclick = () => {
      const start = Math.round((video.currentTime || 0) * 10) / 10;
      const end = Math.round(Math.min(duration() || start + 3, start + 3) * 10) / 10;
      labels.push({ text: '', start, end: end > start ? end : start + 1, x: 0.5, y: 0.5, pointer: true });
      active = labels.length - 1;
      renderRows(); draw();
      rows.querySelectorAll('.vl-text')[active]?.focus();
    };
    canvas.onclick = (event) => {
      if (active < 0 || !labels[active]) return;
      const rect = canvas.getBoundingClientRect();
      const scale = Math.min(rect.width / canvas.width, rect.height / canvas.height);
      const shownW = canvas.width * scale, shownH = canvas.height * scale;
      const offX = rect.left + (rect.width - shownW) / 2, offY = rect.top + (rect.height - shownH) / 2;
      labels[active].x = Math.min(1, Math.max(0, (event.clientX - offX) / shownW));
      labels[active].y = Math.min(1, Math.max(0, (event.clientY - offY) / shownH));
      draw();
    };
    playButton.onclick = () => { if (video.paused) video.play().catch(() => {}); else video.pause(); };
    video.onplay = () => { playButton.textContent = '❚❚'; };
    video.onpause = () => { playButton.textContent = '▶'; };
    video.onloadedmetadata = () => { seek.max = String(duration()); draw(); };
    video.ontimeupdate = draw;
    video.onseeked = draw;
    seek.oninput = () => { video.currentTime = Number(seek.value) || 0; };

    modal.querySelector('.vl-apply').onclick = async (event) => {
      if (busy) return;
      const payload = labels.filter((label) => label.text.trim()).map((label) => ({ ...label, text: label.text.trim() }));
      if (!payload.length) { status.textContent = t('labels.empty'); return; }
      busy = true;
      event.target.disabled = true;
      status.textContent = t('labels.working');
      try {
        const response = await fetch(`/api/clips/${encodeURIComponent(id)}/labels`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ labels: payload }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw Error(window.h3ErrDetail?.(data) || data.detail || t('labels.failed'));
        status.textContent = t('labels.saved');
        await window.h3RefreshJobs?.();
        window.h3PlayJob?.(data.id);
        modal.close();
      } catch (error) {
        status.textContent = error.message || t('labels.failed');
        event.target.disabled = false;
      } finally {
        busy = false;
      }
    };
    modal.onclose = () => { video.pause(); video.removeAttribute('src'); modal.remove(); };
    renderRows();
    modal.showModal();
    draw();
  }

  document.addEventListener('h3-player-clip', (e) => { clip = e.detail; syncButton(); });
  document.addEventListener('h3-lang', syncButton);
  function bind() {
    const button = $('btn-video-labels');
    if (button) button.onclick = openEditor;
    syncButton();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
  else bind();
})();
