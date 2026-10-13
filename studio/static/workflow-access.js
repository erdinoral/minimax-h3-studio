/* Single-clip audio, persistent themes and a bilingual workflow guide. */
(() => {
  const $ = id => document.getElementById(id);
  const tr = () => window.h3Lang?.() !== 'en';
  const label = (en, turkish) => tr() ? turkish : en;
  let audio = null, busy = false, revision = 0;
  const status = message => { $('scene-audio-status').textContent = message; };
  const clear = () => {
    revision++; audio = null;
    const player = $('scene-audio-preview'); player.pause(); player.removeAttribute('src'); player.load(); player.hidden = true;
    status('');
  };
  function render() {
    $('btn-workflow-guide').textContent = label('Guide', 'Rehber');
    const names = {
      'scene-reference-title': ['Visual references', 'Görsel referanslar'],
      'scene-audio-title': ['Audio', 'Ses'],
      'scene-audio-purpose': ['Upload a recording to guide generated sound or add it to the finished video.', 'Ses dosyası yükle: üretilen sese referans ver veya kaydını bitmiş videoya ekle.'],
      'scene-audio-mode-label': ['Use audio as', 'Ses kullanım amacı'],
      'scene-audio-pick': ['Select audio', 'Ses seç'],
      'scene-audio-remove': ['Remove', 'Kaldır'],
      'scene-audio-upload': ['Prepare audio', 'Sesi hazırla'],
      'scene-audio-start-label': ['Start (seconds)', 'Başlangıç (saniye)'],
      'scene-audio-end-label': ['End (seconds; optional)', 'Bitiş (saniye; isteğe bağlı)'],
    };
    for (const [id, words] of Object.entries(names)) { const element = $(id); if (element) element.textContent = label(...words); }
    $('scene-audio-mode').options[0].textContent = label('Guide generated audio', 'Üretilen sese referans ver');
    $('scene-audio-mode').options[1].textContent = label('Add my recording to the video', 'Kaydımı videoya ekle');
    $('scene-audio-hint').textContent = $('scene-audio-mode').value === 'reference'
      ? label('Guides generated voice and sound. Does not guarantee exact words, timing or lip sync. Describe the speech in your prompt. Audio references use the Ref2VA model.', 'Üretilen sesi yönlendirir. Kelimeleri, zamanlamayı veya dudak senkronunu garanti etmez. Konuşmayı promptta yaz. Ses referansı Ref2VA modelini kullanır.')
      : label('Adds your recording to the result from its beginning and replaces generated audio. Longer audio is cut to video length; shorter audio ends in silence. Does not create lip sync. For song-wide lyric planning, use Director.', 'Kaydını başından itibaren sonuç videoya ekler ve üretilen sesi değiştirir. Uzun ses video süresinde kesilir; kısa sesin sonrası sessizdir. Dudak senkronu oluşturmaz. Şarkının tümüne söz/sahne planı için Direktör kullan.');
    const theme = document.documentElement.dataset.theme || 'orange';
    const style = document.documentElement.dataset.uiStyle || 'modern';
    $('studio-theme-settings').innerHTML = `<h3>${label('Appearance', 'Görünüm')}</h3>
      <div class="appearance-columns">
        <div class="appearance-group"><h4>${label('Colors', 'Renkler')}</h4><div class="ios-segment theme-choices" role="group" aria-label="${label('Colors', 'Renkler')}">${[['orange','Orange'],['blue','Blue'],['graphite','Graphite']].map(([id,name]) => `<button type="button" data-theme-choice="${id}" aria-pressed="${theme===id}" class="${theme===id?'on':''}"><span class="appearance-swatch swatch-${id}" aria-hidden="true"></span><span>${name}</span></button>`).join('')}</div></div>
        <div class="appearance-group"><h4>${label('Style', 'Stil')}</h4><div class="ios-segment style-choices" role="group" aria-label="${label('Style', 'Stil')}">${[['modern','Modern'],['old-school','Old School'],['studio','Studio']].map(([id,name]) => `<button type="button" data-style-choice="${id}" aria-pressed="${style===id}" class="${style===id?'on':''}"><span class="style-sample sample-${id}" aria-hidden="true">Aa</span><span>${name}</span></button>`).join('')}</div></div>
      </div><p class="muted appearance-hint">${label('Choose colors and style independently. Style changes fonts, corners and controls.', 'Renk ve stili ayrı seç. Stil; yazı tipini, köşeleri ve kontrolleri değiştirir.')}</p>`;
  }
  $('scene-audio-file').addEventListener('change', clear);
  for (const id of ['scene-audio-start', 'scene-audio-end']) $(id).addEventListener('input', clear);
  $('scene-audio-mode').addEventListener('change', render);
  $('scene-audio-remove').onclick = () => { clear(); $('scene-audio-file').value = ''; };
  $('scene-audio-upload').onclick = async () => {
    if (busy) return;
    const file = $('scene-audio-file').files[0];
    if (!file) return status(label('Select an audio file first.', 'Önce ses dosyası seç.'));
    if (file.size > 40 * 1024 * 1024) return status(label('Maximum file size: 40 MB.', 'En fazla 40 MB.'));
    const start = Number($('scene-audio-start').value || 0), end = $('scene-audio-end').value;
    if (!Number.isFinite(start) || start < 0 || (end && (!Number.isFinite(Number(end)) || Number(end) <= start)))
      return status(label('End must be later than start.', 'Bitiş başlangıçtan sonra olmalı.'));
    const token = ++revision;
    busy = true; $('scene-audio-upload').disabled = true;
    status(label('Preparing audio…', 'Ses hazırlanıyor…'));
    try {
      const form = new FormData(); form.append('file', file); form.append('start', String(start));
      if (end) form.append('end', end);
      const response = await fetch('/api/refs/upload-audio', {method:'POST', body:form});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Audio upload failed');
      if (token !== revision) return;
      audio = data; $('scene-audio-preview').src = data.url; $('scene-audio-preview').hidden = false;
      status(label('Ready: ', 'Hazır: ') + file.name);
    } catch (error) { if (token === revision) status(error.message); }
    finally { busy = false; $('scene-audio-upload').disabled = false; }
  };
  window.getSceneAudioPayload = () => {
    if (busy || ($('scene-audio-file').files.length && !audio))
      throw new Error(label('Prepare or remove the selected audio before generating.', 'Üretmeden önce seçili sesi hazırla veya kaldır.'));
    return audio ? {scene_audio_file:audio.filename, scene_audio_mode:$('scene-audio-mode').value} : {};
  };
  window.hasPreparedSceneAudioReference = () => !!audio && $('scene-audio-mode').value === 'reference';
  $('studio-theme-settings').addEventListener('click', event => {
    const button = event.target.closest('[data-theme-choice], [data-style-choice]'); if (!button) return;
    if (button.dataset.themeChoice) {
      document.documentElement.dataset.theme = button.dataset.themeChoice;
      try { localStorage.setItem('h3-theme', button.dataset.themeChoice); } catch {}
    } else {
      document.documentElement.dataset.uiStyle = button.dataset.styleChoice;
      try { localStorage.setItem('h3-ui-style', button.dataset.styleChoice); } catch {}
    }
    render();
  });
  $('btn-workflow-guide').onclick = () => {
    const old = $('workflow-guide'); if (old) old.remove();
    const dialog = document.createElement('dialog'); dialog.id = 'workflow-guide';
    dialog.setAttribute('aria-label', label('Scene and Director guide', 'Sahne ve Direktör rehberi'));
    dialog.innerHTML = window.h3StudioGuideHTML(tr());
    dialog.querySelector('button').onclick = () => dialog.close();
    dialog.addEventListener('close', () => dialog.remove()); document.body.append(dialog); dialog.showModal();
  };
  document.addEventListener('h3-lang', render);
  render();
})();
