(() => {
  const $ = (id) => document.getElementById(`music-video-${id}`);
  const form = $("form");
  if (!form) return;

  let chunkDuration = 5;
  let duration = 5;
  let productionMode = "normal";
  let stageView = "workspace";
  let timelineView = "song";
  let promptLayout = "single";
  let rewriting = false;
  let preset = "medium";
  let aspect = "16:9";
  let style = "realistic";
  let stemJob = null;
  let stemTimer;
  let stemBusy = false;
  let stemTracks = [];
  const selectedStems = new Set();
  const stemPlayers = new Map();
  let lyrics = [];
  let lyricKey = "";
  let lyricsBusy = false;
  let lyricsJob = null;
  let lyricsTimer;
  let restoringWorkspace = true;
  let projectSaveBusy = false;
  let projectId = "";
  let workspaceVersion = 0;
  let draftTimer;
  let saveChain = Promise.resolve();
  const projectFileCache = new WeakMap();
  const sections = $("sections");
  const presetOptions = [...$("presets").querySelectorAll("[data-preset]")];
  const audioLimit = 40 * 1024 * 1024;
  const source = $("source");
  const video = $("result");
  const original = $("original");
  const useOriginal = $("use-original");
  const canvas = $("waveform");
  const wave = canvas.parentElement;

  function setTimelineView(view) {
    timelineView = view;
    for (const name of ["song", "queue"]) {
      const active = view === name;
      $(name + "-tab").classList.toggle("on", active);
      $(name + "-tab").setAttribute("aria-selected", String(active));
      $(name + "-tab").tabIndex = active ? 0 : -1;
    }
    $("song-panel").hidden = view !== "song";
    $("queue").hidden = view !== "queue";
    if (view === "song") requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
  }
  for (const name of ["song", "queue"]) {
    $(name + "-tab").addEventListener("click", () => { setTimelineView(name); scheduleWorkspaceSave(); });
    $(name + "-tab").addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? "song" : event.key === "End" ? "queue" : timelineView === "song" ? "queue" : "song";
      setTimelineView(next); $(next + "-tab").focus(); scheduleWorkspaceSave();
    });
  }

  const labels = {
    tr: {
      title: "Müzik Klibi", song: "Şarkı seç", start: "Başlangıç (sn)",
      development: "Geliştirme aşamasında",
      timeline: "Şarkı zaman çizelgesi", none: "Seçilmedi", noPreview: "Henüz önizleme yok",
      loadingWave: "Ses dalgası hazırlanıyor…", badWave: "Ses dalgası okunamadı.",
      listen: "5 saniyeyi dinle", character: "Karakter görseli", direction: "Sahne tarifi",
      directionHint: "Karanlık sahnede yakın plan, mor ışıklar", quality: "Kalite",
      medium: "Orta · 736p", high: "Kaliteli · 1088p", generate: "Performans klibi üret",
      preview: "Performans Önizlemesi", original: "Orijinal şarkıyla dinle",
      empty: "Şarkıyı ve karakter görselini seçerek başla.",
      tooShort: "Şarkı en az 5 saniye olmalı.", tooLarge: "Şarkı en fazla 40 MB olabilir.",
      badAudio: "Bu ses dosyası tarayıcıda açılamadı.", uploading: "Referanslar hazırlanıyor…",
      queued: "Üretim sırada…", rendering: "Performans üretiliyor", done: "Klip hazır. Orijinal şarkıyla senkronu kontrol et.",
      cancelled: "Üretim iptal edildi.", failed: "Üretim tamamlanamadı.",
    },
    en: {
      title: "Music Video", song: "Choose song", start: "Start (s)",
      development: "In development",
      timeline: "Song timeline", none: "No file selected", noPreview: "No preview yet",
      loadingWave: "Reading waveform…", badWave: "Could not read the waveform.",
      listen: "Play 5-second selection", character: "Character image", direction: "Scene direction",
      directionHint: "Close-up on a dark stage with violet lights", quality: "Quality",
      medium: "Medium · 736p", high: "Quality · 1088p", generate: "Generate performance",
      preview: "Performance preview", original: "Play with original song",
      empty: "Choose a song and a character image to get started.",
      tooShort: "The song must be at least 5 seconds long.", tooLarge: "The song must be 40 MB or smaller.",
      badAudio: "This audio file could not be opened in the browser.", uploading: "Preparing references…",
      queued: "Waiting in the queue…", rendering: "Generating performance", done: "Clip ready. Check the sync with the original song.",
      cancelled: "Generation cancelled.", failed: "Generation did not complete.",
    },
  };
  Object.assign(labels.tr, {
    newRecord: "Yeni kayıt", saveProject: "Çalışmayı kaydet", projectName: "Çalışma adı",
    projectSaving: "Çalışma kaydediliyor…", projectSaved: "Çalışma kaydedildi.", projectAutosaved: "Son durum otomatik kaydedildi.", projectLoading: "Çalışma yükleniyor…",
    songTab: "Şarkı", productionQueue: "Üretim kuyruğu", queueEmpty: "Henüz müzik klibi üretimi yok.",
    queueWaiting: "Bekliyor", queueRunning: "Üretiliyor", queueDone: "Tamamlandı", queueError: "Hata", queueCancelled: "İptal edildi", queueOpen: "Sonucu aç", queueClip: "Performans klibi",
    extractLyrics: "Otomatik çıkar", lyricsStarting: "Söz çıkarma başlatılıyor…",
    lyricsModel: "Yerel Whisper modeli hazırlanıyor. İlk kullanımda indirilir…",
    lyricsTranscribing: "Sözler çıkarılıyor", lyricsDone: "Zamanlı sözler eklendi. Düzenle ile kontrol edebilirsin.",
    lyricsNone: "Anlaşılabilir söz bulunamadı. Mevcut sözler korundu.",
    remainingAudio: "İmleçten sonra klip için yeterli ses kalmadı. Daha erken bir konuma geç.",
    experimental: "Deneysel", singlePrompt: "Tek prompt", perSection: "Bölüm bölüm", sectionCount: "Bölüm sayısı",
    continuitySettings: "Tutarlılık ayarları", sharedContext: "Ortak karakter ve ortam", transitionContext: "Geçiş bağlamı",
    balancedContext: "Dengeli · 22 kare", strongContext: "Güçlü · 39 kare (deneysel)", extendable: "Sonradan uzatılabilir kaydet",
    extendableHint: "Açıkken bu iş Spectrum olmadan üretilir. Kapalıyken mevcut Spectrum ayarı kullanılır.",
    generate: "Üret", rewriting: "Prompt düzenleniyor…", rewritten: "Prompt düzenlendi.", needPrompt: "Önce bir prompt yaz.",
    directionHint: "Sahneyi, kamerayı ve performansı anlat… (Ctrl+Enter = sıraya ekle)",
    workspace: "Çalışma alanı", result: "Sonuç", workspaceEmpty: "Karakter görselini seçerek başla.", resultEmpty: "Henüz üretilmiş klip yok.", resultBusy: "Klip üretiliyor. Hazır olduğunda burada görünecek.",
    preset: "Kalite ön ayarı", draft: "Taslak", medium: "Orta", high: "Kaliteli",
    style: "Görsel tarz", duration: "Bölüm süresi", seconds: "saniye", aspect: "Görüntü oranı",
    advanced: "Üretim ayarları", quality: "Çözünürlük", steps: "Adım", normal: "Normal",
    addSection: "+ Devam bölümü", removeSection: "Sil", section: "Bölüm",
    lyrics: "Şarkı sözleri", editLyrics: "Düzenle", saveLyrics: "Sözleri göster",
    importLyrics: "LRC / TXT aç", stampLyric: "Dinlenen anı ekle",
    lyricsHint: "Zamanlı sözlere tıklayarak o ana geç. Satır başına [00:12.50] ekleyebilir veya Dinlenen anı ekle düğmesini kullanabilirsin.",
    lyricsEmpty: "Şarkı sözlerini ekle veya bir LRC dosyası aç.",
    separate: "Stemleri ayır", stemHint: "Model ilk kullanımda indirilir · en fazla 10 dk",
    stemDevice: "İşlemci", stemQuality: "Ayrıştırma kalitesi", stemFast: "Hızlı", stemHigh: "Kaliteli",
    stemChannels: "Kanallar", stemFour: "4 kanal", stemSix: "6 kanal", guitar: "Gitar", piano: "Piyano",
    stemSixFastInfo: "HTDemucs 6s · tek geçiş", stemSixHighInfo: "HTDemucs 6s · iki geçiş · daha fazla örtüşme",
    stemSixHint: "Piyano ayrıştırması deneysel, diğer enstrümanlardan sızıntı olabilir.",
    stemFastInfo: "HDemucs MUSDB · tek geçiş", stemHighInfo: "HDemucs MUSDB+ · iki geçiş · daha fazla örtüşme",
    separating: "Stemler ayrıştırılıyor", loading_model: "Yerel model hazırlanıyor / ilk kullanımda indiriliyor…",
    starting: "Stem işlemi başlatılıyor…", stemDone: "Ayrı ses kanalları hazır.",
    mix: "Şarkı", vocals: "Vokal", drums: "Davul", bass: "Bas", other: "Diğer",
    normalHint: "Klip, oynatma imlecinden başlayan sesi performans referansı olarak kullanır.",
    continuumHint: "Bölümler tek bir Continuum videosu oluşturur. Şarkı önizlemede eşlenir. Bu modda şarkıya bağlı dudak senkronu desteklenmiyor.",
    tooShort: "Şarkı klip süresinden kısa.",
    listenSelection: "Seçimi dinle", modeDirection: "Sahne ve kamera tarifi",
  });
  Object.assign(labels.en, {
    newRecord: "New save", saveProject: "Save workspace", projectName: "Project name",
    projectSaving: "Saving workspace…", projectSaved: "Workspace saved.", projectAutosaved: "Latest state saved automatically.", projectLoading: "Loading workspace…",
    songTab: "Song", productionQueue: "Production queue", queueEmpty: "No music video jobs yet.",
    queueWaiting: "Queued", queueRunning: "Generating", queueDone: "Completed", queueError: "Error", queueCancelled: "Cancelled", queueOpen: "Open result", queueClip: "Performance clip",
    extractLyrics: "Extract lyrics", lyricsStarting: "Starting lyrics extraction…",
    lyricsModel: "Loading local Whisper model. It downloads on first use…",
    lyricsTranscribing: "Extracting lyrics", lyricsDone: "Timed lyrics added. Use Edit to review them.",
    lyricsNone: "No recognizable lyrics found. Existing lyrics were kept.",
    remainingAudio: "There is not enough audio after the playhead for this clip. Seek to an earlier position.",
    experimental: "Experimental", singlePrompt: "Single prompt", perSection: "Per section", sectionCount: "Sections",
    continuitySettings: "Continuity settings", sharedContext: "Shared characters and setting", transitionContext: "Transition context",
    balancedContext: "Balanced · 22 frames", strongContext: "Strong · 39 frames (experimental)", extendable: "Save so it can be extended later",
    extendableHint: "When on, this run skips Spectrum. When off, your existing Spectrum setting is used.",
    generate: "Generate", rewriting: "Rewriting prompt…", rewritten: "Prompt rewritten.", needPrompt: "Write a prompt first.",
    directionHint: "Describe the scene, camera and performance… (Ctrl+Enter = queue)",
    workspace: "Workspace", result: "Result", workspaceEmpty: "Choose a character image to get started.", resultEmpty: "No generated clip yet.", resultBusy: "Your clip is being generated. It will appear here when ready.",
    preset: "Quality preset", draft: "Draft", medium: "Medium", high: "Quality",
    style: "Visual style", duration: "Section duration", seconds: "seconds", aspect: "Aspect ratio",
    advanced: "Generation settings", quality: "Resolution", steps: "Steps", normal: "Normal",
    addSection: "+ Continuation section", removeSection: "Remove", section: "Section",
    lyrics: "Lyrics", editLyrics: "Edit", saveLyrics: "Show lyrics", importLyrics: "Open LRC / TXT",
    stampLyric: "Insert playback time",
    lyricsHint: "Click timed lyrics to seek. Add [00:12.50] at the start of a line, or insert the current playback time.",
    lyricsEmpty: "Add lyrics or open an LRC file.",
    separate: "Separate stems", stemHint: "Model downloads on first use · up to 10 min",
    stemDevice: "Processor", stemQuality: "Separation quality", stemFast: "Fast", stemHigh: "Quality",
    stemChannels: "Channels", stemFour: "4 channels", stemSix: "6 channels", guitar: "Guitar", piano: "Piano",
    stemSixFastInfo: "HTDemucs 6s · one pass", stemSixHighInfo: "HTDemucs 6s · two passes · more overlap",
    stemSixHint: "Piano separation is experimental and may include other instruments.",
    stemFastInfo: "HDemucs MUSDB · one pass", stemHighInfo: "HDemucs MUSDB+ · two passes · more overlap",
    separating: "Separating stems", loading_model: "Loading local model / downloading on first use…",
    starting: "Starting stem separation…", stemDone: "Separated audio tracks are ready.",
    mix: "Song", vocals: "Vocals", drums: "Drums", bass: "Bass", other: "Other",
    normalHint: "The clip uses the audio starting at the playhead as its performance reference.",
    continuumHint: "Sections produce one Continuum video. Preview plays the matching song excerpt. Song-driven lip sync is unavailable in this mode.",
    tooShort: "The song is shorter than the clip duration.",
    listenSelection: "Play selection", modeDirection: "Scene and camera direction",
  });
  const strings = () => labels[document.documentElement.lang] || labels.en;
  let status = "empty";
  let statusDetail = "";
  let busy = false;
  let sourceUrl;
  let characterUrl;
  let lastJob;
  let resultJob;
  let musicJobs = [];
  let musicJobRecords = {};
  try { musicJobRecords = JSON.parse(localStorage.getItem("h3.musicVideoJobs") || "{}"); } catch {}
  if (!musicJobRecords || typeof musicJobRecords !== "object" || Array.isArray(musicJobRecords)) musicJobRecords = {};
  let pollTimer;

  let peaks;
  let waveStatus = "";
  let decoding;

  function showWaveStatus(key) {
    waveStatus = key;
    $("wave-status").textContent = strings()[key] || "";
  }

  function drawTrack(canvas, peaks) {
    const { width, height } = canvas.getBoundingClientRect();
    if (!width || !height) return;
    const ratio = window.devicePixelRatio || 1;
    const pixelWidth = Math.round(width * ratio);
    const pixelHeight = Math.round(height * ratio);
    if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
    if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const theme = getComputedStyle(wave);
    const accent = theme.getPropertyValue("--accent-amber").trim() || "#f5a45f";
    const total = source.duration;
    ctx.fillStyle = theme.getPropertyValue("--border");
    ctx.fillRect(0, height / 2, width, 1);
    if (peaks) {
      for (let x = 0; x < width; x += 2) {
        const first = Math.floor(x / width * peaks.length);
        const last = Math.min(peaks.length, Math.ceil((x + 2) / width * peaks.length));
        let peak = 0;
        for (let i = first; i < last; i++) peak = Math.max(peak, peaks[i]);
        const amplitude = Math.max(0.5, peak * (height / 2 - 6));
        ctx.fillStyle = accent;
        ctx.fillRect(x, height / 2 - amplitude, 1.25, amplitude * 2);
      }
    }
    if (hasAudio()) {
      const position = source.currentTime / total * width;
      ctx.fillStyle = theme.getPropertyValue("--text");
      ctx.fillRect(Math.min(width - 1, position), 0, 1, height);
    }
  }

  function drawWave() {
    drawTrack(canvas, peaks);
    for (const track of stemTracks) {
      const target = $("stems").querySelector('[data-stem-canvas="' + track.name + '"]');
      if (target) drawTrack(target, track.peaks);
    }
  }

  async function readWave(file, url) {
    let context;
    showWaveStatus("loadingWave");
    try {
      context = new OfflineAudioContext(1, 1, 8000);
      const audio = await context.decodeAudioData(await file.arrayBuffer());
      if (sourceUrl !== url) return;
      const count = Math.min(2400, audio.length);
      const bins = new Float32Array(count);
      for (let ch = 0; ch < audio.numberOfChannels; ch++) {
        const samples = audio.getChannelData(ch);
        for (let bin = 0; bin < count; bin++) {
          const first = Math.floor(bin * samples.length / count);
          const end = Math.floor((bin + 1) * samples.length / count);
          let peak = bins[bin];
          for (let i = first; i < end; i++) peak = Math.max(peak, Math.abs(samples[i]));
          bins[bin] = peak;
        }
      }
      const max = Math.max(...bins);
      peaks = max > 0 ? bins.map((peak) => peak / max) : bins;
      showWaveStatus("");
      drawWave();
    } catch {
      if (sourceUrl === url) showWaveStatus("badWave");
    } finally {
      if (sourceUrl === url) {
        decoding = undefined;
        updateForm();
      }
    }
  }

  function showStatus(key, detail = "") {
    status = key;
    statusDetail = detail;
    $("status").textContent = [strings()[key], detail].filter(Boolean).join(" ");
  }

  function translate() {
    const copy = strings();
    document.getElementById("ws-music").textContent = copy.title;
    form.closest("main").querySelectorAll("[data-music-text]").forEach((node) => {
      node.textContent = copy[node.dataset.musicText];
    });
    $("direction").placeholder = copy.directionHint;
    $("project-name").placeholder = copy.projectName;
    $("song-name").textContent = $("song").files[0]?.name || copy.none;
    $("character-name").textContent = $("character").files[0]?.name || copy.none;
    showWaveStatus(waveStatus);
    showStatus(status, statusDetail);
    updateControls();
    renderLyrics();
    renderStems();
    refreshStage();
    renderMusicQueue();
  }

  function timestamp(seconds) {
    return `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(2).padStart(5, "0")}`;
  }

  function hasAudio() {
    return Number.isFinite(source.duration) && source.duration > 0;
  }

  function updateForm() {
    duration = chunkDuration * sectionCount();
    const locked = busy || rewriting || restoringWorkspace || projectSaveBusy;
    const ready = hasAudio();
    $("clock").textContent = timestamp(source.currentTime || 0) + " / " + timestamp(ready ? source.duration : 0);
    wave.setAttribute("aria-valuemax", String(ready ? source.duration : 0));
    wave.setAttribute("aria-valuenow", String(source.currentTime || 0));
    wave.setAttribute("aria-disabled", String(!ready || locked));
    const audioReady = Number.isFinite(source.duration) && source.duration > 0 && Boolean(sourceUrl);
    $("play").disabled = locked || !audioReady || !source.paused;
    $("stop").disabled = !audioReady || source.paused;
    $("restart").disabled = locked || !audioReady;
    $("generate").disabled = locked || !ready || source.currentTime + duration > source.duration + .001 || !$("character").files.length;
    $("song").disabled = locked || Boolean(decoding);
    for (const id of ["character", "direction"]) $(id).disabled = locked;
    for (const node of form.querySelectorAll("#music-video-presets button, #music-video-styles button, #music-video-aspects button, #music-video-continuum, #music-video-layout button, #music-video-count, #music-video-context, #music-video-continuity, #music-video-extendable, #music-video-rewrite, #music-video-sections textarea, #music-video-sections button, #music-video-add-section, #music-video-duration, #music-video-quality, #music-video-steps, #music-video-seed")) node.disabled = locked;
    $("separate").disabled = stemBusy || !sourceUrl || busy;
    $("stem-channels").disabled = $("stem-device").disabled = $("stem-preset").disabled = stemBusy;
    $("lyrics-extract").disabled = lyricsBusy || restoringWorkspace || !sourceUrl;
    for (const id of ["lyrics-input", "lyrics-file", "lyrics-edit", "stamp-lyric"]) $(id).disabled = lyricsBusy || restoringWorkspace || projectSaveBusy;
    $("project-save").disabled = restoringWorkspace || projectSaveBusy;
    $("project-select").disabled = restoringWorkspace || projectSaveBusy;
    $("project-name").disabled = restoringWorkspace || projectSaveBusy;
    updateControls();
    drawWave();
  }

  function refreshStage() {
    const preview = $("character-preview");
    const showResult = stageView === "result" && Boolean(video.getAttribute("src"));
    video.hidden = !showResult;
    preview.hidden = stageView !== "workspace" || !characterUrl;
    $("original-toggle").hidden = !showResult || !original.getAttribute("src");
    $("stage-empty").textContent = stageView === "workspace" ? strings().workspaceEmpty
      : busy ? strings().resultBusy : strings().resultEmpty;
    $("stage-empty").hidden = showResult || !preview.hidden;
    $("view").dataset.view = stageView;
    $("view").setAttribute("aria-label", strings().preview);
    for (const tab of $("view").querySelectorAll("[data-music-view]")) {
      const selected = tab.dataset.musicView === stageView;
      tab.classList.toggle("on", selected);
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    }
    $("stage").classList.toggle("has-video", !preview.hidden || !video.hidden);
  }

  function selectStage(view) {
    video.pause();
    original.pause();
    if (view === "result") source.pause();
    stageView = view;
    refreshStage();
  }
  const stageTabs = [...$("view").querySelectorAll("[data-music-view]")];
  for (const tab of stageTabs) {
    tab.addEventListener("click", () => selectStage(tab.dataset.musicView));
    tab.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const target = event.key === "Home" ? stageTabs[0] : event.key === "End" ? stageTabs[1]
        : stageTabs[1 - stageTabs.indexOf(tab)];
      selectStage(target.dataset.musicView);
      target.focus();
    });
  }

  function pausePreview() {
    source.pause();
    for (const player of stemPlayers.values()) player.pause();
    video.pause();
    original.pause();
  }

  $("song").addEventListener("change", () => {
    pausePreview();
    clearTimeout(stemTimer);
    stemJob = null;
    stemTracks = [];
    selectedStems.clear();
    syncStemPlayers();
    stemBusy = false;
    clearTimeout(lyricsTimer);
    lyricsJob = null;
    lyricsBusy = false;
    $("lyrics-status").textContent = "";
    $("stem-status").textContent = "";
    renderStems();
    if (sourceUrl) URL.revokeObjectURL(sourceUrl);
    sourceUrl = undefined;
    peaks = undefined;
    showWaveStatus("");
    source.removeAttribute("src");
    source.load();
    const file = $("song").files[0];
    lyricKey = file ? "h3.musicLyrics." + [file.name, file.size, file.lastModified].join(".") : "";
    try { $("lyrics-input").value = lyricKey ? localStorage.getItem(lyricKey) || "" : ""; } catch {}
    parseLyrics();

    if (file?.size > audioLimit) {
      $("song").value = "";
      showStatus("tooLarge");
    } else if (file) {
      sourceUrl = URL.createObjectURL(file);
      source.src = sourceUrl;
      showStatus("empty");
      decoding = readWave(file, sourceUrl);
    }
    $("song-name").textContent = $("song").files[0]?.name || strings().none;
    updateForm();
  });
  source.addEventListener("loadedmetadata", () => {
    if (source.duration < duration) showStatus("tooShort");
    updateForm();
  });
  source.addEventListener("error", () => {
    if (sourceUrl) showStatus("badAudio");
    updateForm();
  });
  $("character").addEventListener("change", () => {
    if (characterUrl) URL.revokeObjectURL(characterUrl);
    const file = $("character").files[0];
    characterUrl = file ? URL.createObjectURL(file) : undefined;
    const preview = $("character-preview");
    if (characterUrl) preview.src = characterUrl;
    else preview.removeAttribute("src");
    $("character-name").textContent = file?.name || strings().none;
    refreshStage();
    updateForm();
  });
  let pointer;
  function selectWavePoint(event) {
    const rect = wave.getBoundingClientRect();
    const seconds = (event.clientX - rect.left) / rect.width * source.duration;
    source.currentTime = Math.max(0, Math.min(source.duration, seconds));
    updateForm();
  }
  wave.addEventListener("pointerdown", (event) => {
    if (busy || rewriting || !hasAudio() || event.button !== 0) return;
    source.pause();
    wave.focus({ preventScroll: true });
    pointer = event.pointerId;
    wave.setPointerCapture(pointer);
    selectWavePoint(event);
  });
  wave.addEventListener("pointermove", (event) => {
    if (pointer === event.pointerId && !busy && !rewriting) selectWavePoint(event);
  });
  wave.addEventListener("lostpointercapture", () => { pointer = undefined; });
  wave.addEventListener("keydown", event => {
    if (!hasAudio() || busy || rewriting || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const target = event.key === "Home" ? 0 : event.key === "End" ? source.duration
      : source.currentTime + (event.key === "ArrowRight" ? 5 : -5);
    source.currentTime = Math.max(0, Math.min(source.duration, target));
    updateForm();
  });
  async function playSong(restart = false) {
    if (!sourceUrl || !Number.isFinite(source.duration)) return;
    video.pause();
    original.pause();
    if (restart || source.ended) source.currentTime = 0;
    try {
      await source.play();
    } catch {
      showStatus("badAudio");
    }
    updateForm();
  }
  $("play").addEventListener("click", () => void playSong());
  $("stop").addEventListener("click", () => source.pause());
  $("restart").addEventListener("click", () => void playSong(true));
  source.addEventListener("timeupdate", () => {
    updateForm();
    highlightLyrics(source.currentTime);
  });
  for (const event of ["pause", "ended"]) source.addEventListener(event, updateForm);
  source.addEventListener("play", () => { video.pause(); updateForm(); });

  function syncOriginal(force = false) {
    video.muted = useOriginal.checked;
    if (!useOriginal.checked || video.paused || video.seeking || !original.src) {
      original.pause();
      return;
    }
    const audioTime = video.currentTime + ((resultJob || lastJob)?.audioOffset || 0);
    if (force || Math.abs(original.currentTime - audioTime) > 0.15) {
      original.currentTime = audioTime;
    }
    original.playbackRate = video.playbackRate;
    original.volume = video.volume;
    if (original.paused && !original.ended) {
      original.play().catch(() => {
        useOriginal.checked = false;
        video.muted = false;
      });
    }
  }
  video.addEventListener("play", () => { source.pause(); syncOriginal(true); });
  for (const event of ["playing", "seeked", "ratechange"]) {
    video.addEventListener(event, () => syncOriginal(true));
  }
  video.addEventListener("timeupdate", () => {
    syncOriginal();
    highlightLyrics(((resultJob || lastJob)?.offset || 0) + video.currentTime);
  });
  video.addEventListener("volumechange", () => {
    original.volume = video.volume;
    if (video.muted !== useOriginal.checked) useOriginal.checked = video.muted;
    syncOriginal();
  });
  for (const event of ["waiting", "pause", "seeking", "ended"]) {
    video.addEventListener(event, () => original.pause());
  }
  useOriginal.addEventListener("change", () => syncOriginal(true));

  async function request(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : response.statusText;
      const error = new Error(detail || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function upload(url, file, fields = {}) {
    const body = new FormData();
    body.append("file", file);
    for (const [name, value] of Object.entries(fields)) body.append(name, String(value));
    return request(url, { method: "POST", body });
  }

  function finish(key, detail) {
    busy = false;
    showStatus(key, detail);
    refreshStage();
    updateForm();
  }

  async function watch(job, failures = 0) {
    try {
      const result = await request(`/api/jobs/${encodeURIComponent(job.id)}`);
      updateMusicQueueJob(result);
      if (result.status === "done" && result.output?.url) {
        resultJob = { ...job, output_url: result.output.url };
        video.src = result.output.url;
        original.src = job.audio;
        useOriginal.checked = true;
        video.muted = true;
        stageView = "result";
        refreshStage();
        finish("done");
        scheduleWorkspaceSave();
        return;
      }
      if (["error", "cancelled", "done"].includes(result.status)) {
        finish(result.status === "cancelled" ? "cancelled" : "failed", result.error);
        return;
      }
      if (result.status === "running") showStatus("rendering", `· ${result.progress || 0}%`);
      else showStatus("queued");
      pollTimer = setTimeout(() => watch(job), 2500);
    } catch (error) {
      if (error.status === 404) { finish("failed", error.message); return; }
      showStatus("failed", error.message);
      pollTimer = setTimeout(() => watch(job, failures + 1), Math.min(30000, 2500 * (failures + 1)));
    }
  }

  async function generatePerformance(event) {
    event?.preventDefault();
    if (busy || rewriting || !hasAudio() || !form.reportValidity()) return;
    const song = $("song").files[0];
    const character = $("character").files[0];
    if (!song || !character) return;
    const offset = source.currentTime || 0;
    if (!Number.isFinite(offset) || offset < 0 || offset + duration > source.duration + 0.001) {
      showStatus("remainingAudio");
      window.h3Toast?.(strings().remainingAudio);
      return false;
    }
    const direction = $("direction").value.trim();
    pausePreview();
    stageView = "workspace";
    refreshStage();
    busy = true;
    updateForm();
    showStatus("uploading");
    try {
      const lora = preset === "high" ? { lora_name: "", lora_strengths: {} } : await window.H3MusicProduction.speedLora();
      const audio = await upload("/api/refs/upload-audio", song,
        productionMode === "normal" ? { start: offset, end: offset + duration } : {});
      const image = await upload("/api/refs/upload", character);
      const styleHint = window.H3MusicProduction.styleHint(style);
      const prompt = [
        "<Picture 1> is the performer and defines their identity, hair and clothing.",
        productionMode === "normal" ? "<Audio 1> is the exact song excerpt the performer is singing." : "Visual music video sequence. No speech, text or subtitles.",
        productionMode === "normal" ? "One continuous shot. Match the mouth movements to the sung syllables and pauses in <Audio 1> from the first frame." : "Keep the same performer, costume, scene geography and lighting through the sequence.",
        "Preserve the performer's identity. No spoken dialogue, subtitles or cuts.",
        styleHint,
        direction ? `Scene direction: ${direction}` : "A cinematic live performance on a dark stage with soft colored light.",
      ].join(" ");
      const musicMetadata = {
        song_name: song.name, start_sec: offset, duration_sec: duration,
        audio_file: audio.filename, audio_offset: productionMode === "continuum" ? offset : 0,
      };
      const job = await request("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: "ref", ref_images: [image.name],
          ...(productionMode === "normal"
            ? { scene_audio_file: audio.filename, scene_audio_mode: "reference" }
            : { continuation_method: "continuum", continuum_chunks: sectionCount(),
                continuum_segment_prompts: promptLayout === "single" ? Array(sectionCount()).fill(prompt)
                  : [prompt, ...[...sections.querySelectorAll("textarea")].map(node =>
                    "<Picture 1> defines the same performer, face and clothing. " + styleHint + ". " + node.value.trim())],
                continuum_context: $("context").value.trim() || "One continuous music video performance. Preserve face, clothing, light and screen direction.",
                continuum_continuity: $("continuity").value, continuum_extendable: $("extendable").checked }),
          prompt, duration: chunkDuration, quality: $("quality").value, aspect,
          steps: Number($("steps").value), seed: Number($("seed").value),
          sampler: "res_multistep", scheduler: "simple", ...lora,
          silent_audio: productionMode === "continuum", asset_auto_match: false, prompt_rewriter_enabled: false, lane: "scene",
          music_video: musicMetadata,
        }),
      });
      lastJob = { id: job.id, audio: audio.url, offset, audioOffset: productionMode === "continuum" ? offset : 0 };
      musicJobRecords[job.id] = { ...lastJob, song_name: song.name, duration_sec: duration };
      try { localStorage.setItem("h3.musicVideoJobs", JSON.stringify(musicJobRecords)); } catch {}
      updateMusicQueueJob({ ...job, music_video: musicMetadata });
      try { sessionStorage.setItem("h3.musicVideoJob", JSON.stringify(lastJob)); } catch {}
      scheduleWorkspaceSave();
      await watch(lastJob);
      return true;
    } catch (error) {
      finish("failed", error.message);
      return false;
    }
  }
  form.addEventListener("submit", generatePerformance);

  window.H3MusicProduction.directorContext = () => ({
    workspace: "music", visual_style: style, clip_duration: chunkDuration,
    quality: $("quality").value, aspect, prompt_mode: productionMode,
    section_count: sectionCount(), song: $("song").files[0]?.name || "",
    performer_selected: Boolean($("character").files.length), start: source.currentTime || 0,
    end: (source.currentTime || 0) + duration, current_prompt: $("direction").value,
    section_prompts: [...sections.querySelectorAll("textarea")].map(area => area.value),
  });
  window.H3MusicProduction.setDirectorSettings = (settings) => {
    if (settings.style) {
      style = settings.style;
      markChoice($("styles"), "[data-style]", style, "style");
    }
    if (settings.duration) {
      $("duration").value = settings.duration;
      $("duration").dispatchEvent(new Event("change"));
    }
    updateForm();
    scheduleWorkspaceSave();
  };
  window.H3MusicProduction.applyDirector = async (prompts, { queue = false } = {}) => {
    if (busy || rewriting) throw Error(document.documentElement.lang === "tr" ? "Müzik klibi işlemi devam ediyor." : "A music video operation is already running.");
    if (!prompts.length || prompts.length > 16) throw Error("Continuum: 1–16");
    $("direction").value = prompts[0];
    if (prompts.length > 1) {
      productionMode = "continuum";
      promptLayout = "sections";
      $("continuum").checked = true;
      sections.replaceChildren();
      for (const prompt of prompts.slice(1)) {
        addSection();
        sections.lastElementChild.querySelector("textarea").value = prompt;
      }
    } else {
      productionMode = "normal";
      $("continuum").checked = false;
    }
    updateForm();
    scheduleWorkspaceSave();
    if (!queue) return true;
    if (!hasAudio() || !$("song").files.length || !$("character").files.length) {
      showStatus("empty");
      window.h3Toast?.(strings().empty);
      return false;
    }
    return Boolean(await generatePerformance());
  };

  async function projectAsset(file) {
    if (!file) return null;
    if (!projectFileCache.has(file)) {
      const pending = upload("/api/music-workspace/project-files", file).then(asset => ({
        ...asset, last_modified: file.lastModified,
      })).catch(error => { projectFileCache.delete(file); throw error; });
      projectFileCache.set(file, pending);
    }
    return projectFileCache.get(file);
  }

  async function captureWorkspace() {
    const [song, character] = await Promise.all([
      projectAsset($("song").files[0]), projectAsset($("character").files[0]),
    ]);
    return {
      version: 1, project_id: projectId, project_name: $("project-name").value,
      song, character, position: source.currentTime || 0,
      settings: { preset, aspect, style, chunk_duration: chunkDuration, production_mode: productionMode,
        prompt_layout: promptLayout, quality: $("quality").value, steps: $("steps").value, seed: $("seed").value,
        count: $("count").value, continuity: $("continuity").value, context: $("context").value,
        extendable: $("extendable").checked, stem_device: $("stem-device").value,
        stem_preset: $("stem-preset").value, stem_channels: $("stem-channels").value },
      direction: $("direction").value,
      sections: [...sections.querySelectorAll("textarea")].map(area => area.value),
      lyrics: $("lyrics-input").value, editing_lyrics: !$("lyrics-input").hidden,
      stem_job: stemJob, selected_stems: [...selectedStems], lyrics_job: lyricsBusy ? lyricsJob : null,
      timeline_view: timelineView, stage_view: stageView, last_job: lastJob, result: resultJob, use_original: useOriginal.checked,
      result_position: video.currentTime || 0, job_records: musicJobRecords,
    };
  }

  function persistWorkspace(id, state, name) {
    return request(`/api/music-workspace/projects/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, state }),
    });
  }

  async function saveWorkspaceDraft(version) {
    if (restoringWorkspace || version !== workspaceVersion) return;
    try {
      const state = await captureWorkspace();
      if (restoringWorkspace || version !== workspaceVersion) return;
      await persistWorkspace("draft", state, state.project_name || state.song?.filename || "Music video");
      if (version === workspaceVersion) $("project-status").textContent = strings().projectAutosaved;
    } catch (error) {
      $("project-status").textContent = error.message;
    }
  }

  function scheduleWorkspaceSave() {
    if (restoringWorkspace || projectSaveBusy) return;
    const version = ++workspaceVersion;
    clearTimeout(draftTimer);
    draftTimer = setTimeout(() => {
      saveChain = saveChain.catch(() => {}).then(() => saveWorkspaceDraft(version));
    }, 600);
  }

  async function loadProjectList() {
    const data = await request("/api/music-workspace/projects");
    const select = $("project-select");
    select.replaceChildren();
    const empty = new Option(strings().newRecord, "");
    select.append(empty);
    for (const item of data.projects) select.append(new Option(item.name, item.id));
    select.value = projectId;
  }

  async function restoreProjectAsset(asset, input) {
    if (!asset) { input.value = ""; return; }
    const response = await fetch(`/api/music-workspace/project-files/${encodeURIComponent(asset.file_id)}`);
    if (!response.ok) throw Error("Project file is missing: " + asset.filename);
    const file = new File([await response.blob()], asset.filename, {
      type: asset.type, lastModified: asset.last_modified || 0,
    });
    projectFileCache.set(file, Promise.resolve(asset));
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
  }

  async function restoreWorkspace(record) {
    const state = record.state;
    if (!state || state.version !== 1) throw Error("Unsupported music project version");
    restoringWorkspace = true;
    ++workspaceVersion;
    clearTimeout(draftTimer);
    clearTimeout(pollTimer);
    pausePreview();
    updateForm();
    try {
      const settings = state.settings || {};
      preset = ["draft", "medium", "high"].includes(settings.preset) ? settings.preset : "medium";
      aspect = settings.aspect || "16:9";
      style = settings.style || "realistic";
      chunkDuration = Number(settings.chunk_duration) || 5;
      productionMode = settings.production_mode === "continuum" ? "continuum" : "normal";
      promptLayout = settings.prompt_layout === "sections" ? "sections" : "single";
      for (const [id, value] of Object.entries({ duration: chunkDuration, quality: settings.quality || "736",
        steps: settings.steps || "8", seed: settings.seed ?? "-1", count: settings.count || "2",
        continuity: settings.continuity || "balanced", context: settings.context || "",
        "stem-device": settings.stem_device || "cpu", "stem-preset": settings.stem_preset || "fast",
        "stem-channels": settings.stem_channels || "4" })) $(id).value = value;
      $("continuum").checked = productionMode === "continuum";
      $("extendable").checked = settings.extendable !== false;
      $("direction").value = state.direction || "";
      sections.replaceChildren();
      for (const prompt of (state.sections || []).slice(0, 15)) {
        addSection();
        sections.lastElementChild.querySelector("textarea").value = prompt;
      }
      markChoice($("styles"), "[data-style]", style, "style");
      markChoice($("aspects"), "[data-aspect]", aspect, "aspect");
      await Promise.all([restoreProjectAsset(state.song, $("song")), restoreProjectAsset(state.character, $("character"))]);
      if (state.song) {
        await new Promise(resolve => {
          const finish = () => {
            clearTimeout(timer);
            source.removeEventListener("loadedmetadata", finish);
            source.removeEventListener("error", finish);
            resolve();
          };
          const timer = setTimeout(finish, 20000);
          source.addEventListener("loadedmetadata", finish);
          source.addEventListener("error", finish);
          $("song").dispatchEvent(new Event("change", { bubbles: true }));
        });
      } else $("song").dispatchEvent(new Event("change", { bubbles: true }));
      $("character").dispatchEvent(new Event("change", { bubbles: true }));
      if (hasAudio()) source.currentTime = Math.min(source.duration, Math.max(0, Number(state.position) || 0));
      $("lyrics-input").value = state.lyrics || "";
      saveLyrics();
      $("lyrics-input").hidden = $("stamp-lyric").hidden = !state.editing_lyrics;
      $("lyrics").hidden = Boolean(state.editing_lyrics);
      musicJobRecords = { ...musicJobRecords, ...(state.job_records || {}) };
      lastJob = state.last_job || null;
      resultJob = state.result || null;
      setTimelineView(state.timeline_view === "queue" ? "queue" : "song");
      stageView = state.stage_view === "result" ? "result" : "workspace";
      video.removeAttribute("src");
      original.removeAttribute("src");
      if (resultJob?.output_url) {
        video.src = resultJob.output_url;
        if (resultJob.audio) original.src = resultJob.audio;
        useOriginal.checked = Boolean(resultJob.audio) && state.use_original !== false;
        video.muted = useOriginal.checked;
        video.addEventListener("loadedmetadata", () => { video.currentTime = Math.min(video.duration || 0, state.result_position || 0); }, { once: true });
      }
      stemJob = state.stem_job || null;
      if (stemJob) {
        for (const name of state.selected_stems || []) selectedStems.add(name);
        stemBusy = true;
        await watchStems(stemJob);
      }
      if (state.lyrics_job) {
        lyricsJob = state.lyrics_job;
        lyricsBusy = true;
        await watchLyrics(lyricsJob, lyricKey);
      }
      projectId = record.id === "draft" ? state.project_id || "" : record.id;
      $("project-select").value = projectId;
      $("project-name").value = record.id === "draft" ? state.project_name || "" : record.name;
      refreshStage();
      renderMusicQueue();
    } finally {
      restoringWorkspace = false;
      busy = false;
      updateForm();
    }
    if (lastJob?.id && lastJob.audio) {
      try {
        const job = await request(`/api/jobs/${encodeURIComponent(lastJob.id)}`);
        updateMusicQueueJob(job);
        if (["queued", "running"].includes(job.status)) {
          busy = true;
          updateForm();
          void watch(lastJob);
        }
      } catch (error) { showStatus("failed", error.message); }
    }
  }

  async function initializeMusicWorkspace() {
    $("project-status").textContent = strings().projectLoading;
    try {
      await loadProjectList();
      let draft;
      try { draft = await request("/api/music-workspace/projects/draft"); }
      catch (error) { if (error.status !== 404) throw error; }
      if (draft) await restoreWorkspace(draft);
      else {
        try { lastJob = JSON.parse(sessionStorage.getItem("h3.musicVideoJob") || "null"); } catch {}
        if (lastJob?.id && lastJob.audio) { busy = true; void watch(lastJob); }
      }
      $("project-status").textContent = draft ? strings().projectAutosaved : "";
    } catch (error) { $("project-status").textContent = error.message; }
    finally { restoringWorkspace = false; updateForm(); }
  }

  form.addEventListener("input", scheduleWorkspaceSave);
  form.addEventListener("change", scheduleWorkspaceSave);
  form.addEventListener("click", event => {
    if (event.target.closest("button") && !event.target.closest("#music-video-project-save")) scheduleWorkspaceSave();
  });
  source.addEventListener("pause", scheduleWorkspaceSave);
  source.addEventListener("seeked", scheduleWorkspaceSave);
  video.addEventListener("pause", scheduleWorkspaceSave);
  video.addEventListener("seeked", scheduleWorkspaceSave);
  $("project-select").addEventListener("change", async () => {
    const id = $("project-select").value;
    if (!id) { projectId = ""; scheduleWorkspaceSave(); return; }
    restoringWorkspace = true;
    ++workspaceVersion;
    clearTimeout(draftTimer);
    updateForm();
    $("project-status").textContent = strings().projectLoading;
    try {
      await saveChain;
      await restoreWorkspace(await request(`/api/music-workspace/projects/${id}`));
      $("project-status").textContent = strings().projectSaved;
      scheduleWorkspaceSave();
    } catch (error) { $("project-status").textContent = error.message; }
    finally { restoringWorkspace = false; updateForm(); }
  });
  $("project-save").addEventListener("click", async () => {
    if (restoringWorkspace || projectSaveBusy) return;
    projectSaveBusy = true;
    clearTimeout(draftTimer);
    ++workspaceVersion;
    pausePreview();
    updateForm();
    $("project-status").textContent = strings().projectSaving;
    try {
      await saveChain;
      const state = await captureWorkspace();
      const id = projectId || crypto.randomUUID().replaceAll("-", "").slice(0, 12);
      const name = $("project-name").value.trim() || state.song?.filename || "Music video";
      state.project_id = id;
      state.project_name = name;
      await persistWorkspace(id, state, name);
      await persistWorkspace("draft", state, name);
      projectId = id;
      $("project-name").value = name;
      await loadProjectList();
      $("project-status").textContent = strings().projectSaved;
    } catch (error) { $("project-status").textContent = error.message; }
    finally { projectSaveBusy = false; updateForm(); }
  });

  function isMusicJob(job) {
    return Boolean(job.music_video || musicJobRecords[job.id] || lastJob?.id === job.id ||
      String(job.prompt || "").includes("is the performer and defines their identity, hair and clothing."));
  }

  function updateMusicQueueJob(job) {
    if (!job?.id || !isMusicJob(job)) return;
    const index = musicJobs.findIndex(item => item.id === job.id);
    if (index < 0) musicJobs.push(job);
    else musicJobs[index] = { ...musicJobs[index], ...job };
    renderMusicQueue();
  }

  function openMusicQueueResult(job) {
    if (!job.output?.url) return;
    pausePreview();
    const metadata = job.music_video;
    const saved = musicJobRecords[job.id] || (lastJob?.id === job.id ? lastJob : {});
    const audio = metadata?.audio_file ? `/api/ref-audio/${encodeURIComponent(metadata.audio_file)}`
      : saved.audio || (job.scene_audio_file ? `/api/ref-audio/${encodeURIComponent(job.scene_audio_file)}` : "");
    resultJob = { id: job.id, audio, output_url: job.output.url, offset: metadata?.start_sec ?? saved.offset ?? 0,
      audioOffset: metadata?.audio_offset ?? saved.audioOffset ?? 0 };
    video.src = job.output.url;
    if (audio) original.src = audio;
    else { original.removeAttribute("src"); original.load(); }
    useOriginal.checked = Boolean(audio);
    video.muted = Boolean(audio);
    stageView = "result";
    refreshStage();
    scheduleWorkspaceSave();
  }

  function renderMusicQueue() {
    const holder = $("queue-list");
    if (!holder) return;
    const copy = strings();
    const queued = musicJobs.filter(job => job.status === "queued").length;
    const running = musicJobs.filter(job => job.status === "running").length;
    $("queue-count").textContent = [running ? `${running} ${copy.queueRunning.toLowerCase()}` : "",
      queued ? `${queued} ${copy.queueWaiting.toLowerCase()}` : ""].filter(Boolean).join(" · ") || String(musicJobs.length);
    holder.replaceChildren();
    if (!musicJobs.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = copy.queueEmpty;
      holder.append(empty);
      return;
    }
    const order = { running: 0, queued: 1 };
    const sorted = [...musicJobs].sort((a, b) => {
      const difference = (order[a.status] ?? 2) - (order[b.status] ?? 2);
      if (difference) return difference;
      return a.status === "queued" ? (a.created_at || 0) - (b.created_at || 0)
        : (b.created_at || 0) - (a.created_at || 0);
    });
    for (const job of sorted) {
      const metadata = job.music_video || {};
      const saved = musicJobRecords[job.id] || {};
      const row = document.createElement("article");
      row.className = "music-video-queue-item";
      row.dataset.status = job.status;
      row.dataset.jobId = job.id;
      row.setAttribute("role", "listitem");
      const title = document.createElement("strong");
      title.textContent = metadata.song_name || saved.song_name || copy.queueClip;
      const status = document.createElement("span");
      status.className = "music-video-queue-status";
      status.textContent = ({ queued: copy.queueWaiting, running: copy.queueRunning, done: copy.queueDone,
        error: copy.queueError, cancelled: copy.queueCancelled })[job.status] || job.status;
      const detail = document.createElement("small");
      const offset = metadata.start_sec ?? saved.offset;
      const seconds = metadata.duration_sec || saved.duration_sec || job.planned_duration ||
        (job.continuum_prompts?.length || 1) * (job.duration || 5);
      detail.textContent = [offset != null ? timestamp(offset) : "", `${seconds} s`,
        job.mode === "continuum" ? "Continuum" : copy.normal, job.quality ? job.quality + "p" : ""].filter(Boolean).join(" · ");
      row.append(title, status, detail);
      if (["queued", "running"].includes(job.status)) {
        const progress = document.createElement("progress");
        progress.max = 100;
        progress.value = Math.min(100, Math.max(0, Number(job.progress) || 0));
        progress.setAttribute("aria-label", status.textContent);
        row.append(progress);
      }
      if (job.error) {
        const error = document.createElement("p");
        error.className = "music-video-queue-error";
        error.textContent = String(job.error).slice(0, 220);
        error.title = job.error;
        row.append(error);
      }
      if (job.status === "done" && job.output?.url) {
        const open = document.createElement("button");
        open.type = "button";
        open.className = "btn-secondary";
        open.textContent = copy.queueOpen;
        open.addEventListener("click", () => openMusicQueueResult(job));
        row.append(open);
      }
      holder.append(row);
    }
  }
  document.addEventListener("h3-jobs", event => {
    musicJobs = (event.detail.jobs || []).filter(isMusicJob);
    renderMusicQueue();
  });

  function markChoice(container, selector, value, key) {
    for (const button of container.querySelectorAll(selector)) {
      const on = button.dataset[key] === value;
      button.classList.toggle("on", on);
      button.setAttribute("aria-pressed", String(on));
    }
  }

  function updateControls() {
    const copy = strings();
    const sixChannels = $("stem-channels").value === "6";
    const highQuality = $("stem-preset").value === "quality";
    const profile = sixChannels ? (highQuality ? copy.stemSixHighInfo : copy.stemSixFastInfo)
      : (highQuality ? copy.stemHighInfo : copy.stemFastInfo);
    $("stem-profile").textContent = profile + (sixChannels ? " · " + copy.stemSixHint : "");
    const tr = document.documentElement.lang === "tr";
    const transport = tr ? { play: "Oynat", stop: "Durdur", restart: "En baştan başlat" }
      : { play: "Play", stop: "Stop", restart: "Restart from beginning" };
    for (const [id, label] of Object.entries(transport)) {
      $(id).title = label;
      $(id).setAttribute("aria-label", label);
    }
    $("play").parentElement.setAttribute("aria-label", tr ? "Şarkı oynatıcısı" : "Song player");
    $("mode-hint").textContent = hasAudio() && source.currentTime + duration > source.duration + .001
      ? copy.remainingAudio : productionMode === "normal" ? copy.normalHint : copy.continuumHint;
    $("preset-summary").textContent = `${$("quality").value}p · ${$("steps").value} ${copy.steps.toLowerCase()}${preset !== "high" ? " · Hybrid r48 LoRA" : ""}`;
    const perSection = productionMode === "continuum" && promptLayout === "sections";
    $("continuum-settings").hidden = productionMode !== "continuum";
    $("continuum-state").textContent = productionMode === "continuum" ? "ON" : "OFF";
    $("count-label").hidden = promptLayout !== "single";
    $("first-section").hidden = !perSection;
    $("first-section").textContent = copy.section + " 1";
    $("add-section").hidden = sections.hidden = !perSection;
    $("count").required = productionMode === "continuum" && promptLayout === "single";
    for (const area of sections.querySelectorAll("textarea")) area.required = perSection;
    $("total").textContent = sectionCount() + " × " + chunkDuration + " " + copy.seconds + " = " + duration + " " + copy.seconds;
    markChoice($("layout"), "[data-layout]", promptLayout, "layout");
    $("rewrite").hidden = perSection;
    $("add-section").disabled = busy || rewriting || restoringWorkspace || projectSaveBusy || sections.children.length >= 15;
    for (const node of sections.querySelectorAll("label span")) {
      node.textContent = `${copy.section} ${Number(node.dataset.section) + 2}`;
    }
    markChoice($("presets"), "[data-preset]", preset, "preset");

    $("lyrics-edit").textContent = $("lyrics-input").hidden ? copy.editLyrics : copy.saveLyrics;
    document.dispatchEvent(new Event("h3-music-settings"));
  }

  // Use the main workspace's style choices and its actual prompt descriptions.
  for (const original of document.querySelectorAll("#scene-style-chips [data-style]")) {
    const button = original.cloneNode(true);
    button.removeAttribute("data-group");
    button.addEventListener("click", () => {
      style = button.dataset.style;
      markChoice($("styles"), "[data-style]", style, "style");
    });
    $("styles").append(button);
  }
  markChoice($("styles"), "[data-style]", style, "style");
  for (const button of presetOptions) button.addEventListener("click", () => {
    preset = button.dataset.preset;
    $("quality").value = ({ draft: "480", medium: "736", high: "1088" })[preset];
    $("steps").value = preset === "high" ? "18" : "8";
    updateForm();
  });
  for (const button of $("aspects").querySelectorAll("[data-aspect]")) {
    button.addEventListener("click", () => {
      aspect = button.dataset.aspect;
      markChoice($("aspects"), "[data-aspect]", aspect, "aspect");
    });
  }
  for (const id of ["quality", "steps"]) $(id).addEventListener("input", updateForm);
  $("duration").addEventListener("change", () => {
    pausePreview();
    chunkDuration = Number($("duration").value);
    updateForm();
  });
  function addSection() {
    if (sections.children.length >= 15) return;
    const row = document.createElement("div");
    row.className = "continuum-segment";
    const label = document.createElement("label");
    const title = document.createElement("span");
    const input = document.createElement("textarea");
    input.rows = 3;
    input.maxLength = 8000;
    input.required = true;
    input.placeholder = strings().modeDirection;
    label.append(title, input);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn-ghost";
    remove.textContent = strings().removeSection;
    remove.addEventListener("click", () => {
      row.remove();
      renumberSections();
      updateForm();
    });
    row.append(label, remove);
    sections.append(row);
    renumberSections();
    updateForm();
  }
  function renumberSections() {
    sections.querySelectorAll("label span").forEach((title, index) => { title.dataset.section = index; });
  }
  $("add-section").addEventListener("click", addSection);
  function sectionCount() {
    if (productionMode !== "continuum") return 1;
    return promptLayout === "sections" ? 1 + sections.querySelectorAll("textarea").length
      : Math.max(1, Math.min(16, Number($("count").value) || 1));
  }
  $("continuum").addEventListener("change", () => {
    pausePreview();
    productionMode = $("continuum").checked ? "continuum" : "normal";
    updateForm();
  });
  $("count").addEventListener("input", updateForm);
  $("count").addEventListener("change", () => {
    $("count").value = sectionCount();
    updateForm();
  });
  for (const button of $("layout").querySelectorAll("[data-layout]")) {
    button.addEventListener("click", () => {
      pausePreview();
      promptLayout = button.dataset.layout;
      if (promptLayout === "sections" && !sections.children.length) addSection();
      updateForm();
    });
  }
  $("rewrite").addEventListener("click", async () => {
    const input = $("direction");
    if (!input.value.trim()) { showStatus("needPrompt"); return; }
    const before = input.value;
    rewriting = true;
    updateForm();
    showStatus("rewriting");
    try {
      const result = await request("/api/prompt/rewrite", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: before, prompt_rewriter_enabled: true,
          context: "Music video. Preserve the selected performer, scene actions and camera direction. No additional spoken dialogue. " +
            window.H3MusicProduction.styleHint(style),
        }),
      });
      if (result.prompt) input.value = result.prompt;
      showStatus("rewritten");
    } catch (error) {
      showStatus("failed", error.message);
    } finally {
      rewriting = false;
      updateForm();
    }
  });
  $("direction").addEventListener("keydown", event => {
    if (event.ctrlKey && event.key === "Enter") {
      event.preventDefault();
      if (!$("generate").disabled) form.requestSubmit($("generate"));
    }
  });

  function parseLyrics() {
    lyrics = [];
    for (const line of $("lyrics-input").value.split(/\r?\n/)) {
      const matches = [...line.matchAll(/\[(\d+):([0-5]?\d(?:\.\d+)?)\]/g)];
      const text = line.replace(/\[[^\]]*\]/g, "").trim();
      if (!text) continue;
      if (!matches.length) lyrics.push({ text, time: null });
      for (const match of matches) lyrics.push({ text, time: Number(match[1]) * 60 + Number(match[2]) });
    }
    if (lyrics.every(line => line.time !== null)) lyrics.sort((a, b) => a.time - b.time);
    renderLyrics();
  }
  function renderLyrics() {
    const list = $("lyrics");
    list.replaceChildren();
    if (!lyrics.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = strings().lyricsEmpty;
      list.append(empty);
    }
    lyrics.forEach((lyric, index) => {
      const row = document.createElement(lyric.time === null ? "p" : "button");
      row.className = "music-video-lyric";
      row.dataset.lyric = index;
      if (lyric.time !== null) {
        row.type = "button";
        const time = document.createElement("span");
        time.textContent = timestamp(lyric.time);
        row.append(time);
        row.addEventListener("click", () => {
          if (!sourceUrl || busy || !hasAudio()) return;
          pausePreview();
          source.currentTime = Math.min(source.duration, lyric.time);
          updateForm();
          highlightLyrics(lyric.time);
        });
      }
      row.append(document.createTextNode(lyric.text));
      list.append(row);
    });
    highlightLyrics(source.currentTime || 0);
  }
  function highlightLyrics(time) {
    let active = -1;
    lyrics.forEach((line, index) => {
      if (line.time !== null && line.time <= time && (active < 0 || line.time >= lyrics[active].time)) active = index;
    });
    for (const row of $("lyrics").children) {
      const selected = Number(row.dataset.lyric) === active;
      row.classList.toggle("on", selected);
      if (selected) row.setAttribute("aria-current", "true");
      else row.removeAttribute("aria-current");
    }
  }
  function saveLyrics() {
    try { if (lyricKey) localStorage.setItem(lyricKey, $("lyrics-input").value); } catch {}
    parseLyrics();
    scheduleWorkspaceSave();
  }
  $("lyrics-input").addEventListener("input", saveLyrics);
  $("lyrics-edit").addEventListener("click", () => {
    const editing = $("lyrics-input").hidden;
    $("lyrics-input").hidden = $("stamp-lyric").hidden = !editing;
    $("lyrics").hidden = editing;
    updateControls();
  });
  $("stamp-lyric").addEventListener("click", () => {
    const input = $("lyrics-input");
    const position = input.selectionStart;
    const lineStart = input.value.lastIndexOf("\n", Math.max(0, position - 1)) + 1;
    const now = !video.paused ? ((resultJob || lastJob)?.offset || 0) + video.currentTime : source.currentTime;
    input.setRangeText(`[${timestamp(now)}] `, lineStart, lineStart, "end");
    saveLyrics();
    input.focus();
  });
  $("lyrics-file").addEventListener("change", async () => {
    const file = $("lyrics-file").files[0];
    if (!file) return;
    if (file.size > 1024 * 1024) { showStatus("failed", "LRC / TXT: max 1 MB"); return; }
    $("lyrics-input").value = await file.text();
    saveLyrics();
  });

  async function watchLyrics(id, songKey) {
    try {
      const job = await request(`/api/music-workspace/lyrics/${id}`);
      if (lyricsJob !== id || lyricKey !== songKey) return;
      if (job.status === "error") throw Error(job.error);
      if (job.status === "done") {
        lyricsBusy = false;
        if (job.lrc?.trim()) {
          $("lyrics-input").value = job.lrc;
          saveLyrics();
          $("lyrics-input").hidden = $("stamp-lyric").hidden = true;
          $("lyrics").hidden = false;
          $("lyrics-status").textContent = strings().lyricsDone;
        } else {
          $("lyrics-status").textContent = strings().lyricsNone;
        }
        updateForm();
        return;
      }
      $("lyrics-status").textContent = job.phase === "transcribing"
        ? `${strings().lyricsTranscribing} · ${job.progress || 0}%`
        : job.phase === "loading_model" ? strings().lyricsModel : strings().lyricsStarting;
      lyricsTimer = setTimeout(() => watchLyrics(id, songKey), 2000);
    } catch (error) {
      if (lyricsJob !== id || lyricKey !== songKey) return;
      lyricsBusy = false;
      $("lyrics-status").textContent = error.message;
      updateForm();
    }
  }
  $("lyrics-extract").addEventListener("click", async () => {
    const file = $("song").files[0];
    if (!file || lyricsBusy) return;
    const songKey = lyricKey;
    lyricsBusy = true;
    updateForm();
    $("lyrics-status").textContent = strings().lyricsStarting;
    try {
      const job = await upload("/api/music-workspace/lyrics", file, { stem_job: stemJob || "" });
      if (lyricKey !== songKey) return;
      lyricsJob = job.id;
      scheduleWorkspaceSave();
      await watchLyrics(job.id, songKey);
    } catch (error) {
      if (lyricKey !== songKey) return;
      lyricsBusy = false;
      $("lyrics-status").textContent = error.message;
      updateForm();
    }
  });

  function syncStemPlayback(force = false) {
    for (const [name, player] of stemPlayers) {
      if (player.readyState) {
        const target = Math.min(source.currentTime || 0, player.duration || 0);
        if (Math.abs(player.currentTime - target) > (force ? .01 : .1)) player.currentTime = target;
      }
      player.playbackRate = source.playbackRate;
      player.volume = source.volume;
      if (source.paused || source.ended || source.seeking) {
        player.pause();
      } else if (player.readyState && player.paused && !player.ended) {
        player.play().then(() => {
          if (stemPlayers.get(name) !== player || source.paused) player.pause();
        }).catch(error => {
          if (error.name === "AbortError" || stemPlayers.get(name) !== player) return;
          source.pause();
          showStatus("badAudio");
        });
      }
    }
  }

  function syncStemPlayers() {
    const tracks = new Map(stemTracks.map(track => [track.name, track]));
    for (const name of selectedStems) if (!tracks.has(name)) selectedStems.delete(name);
    for (const [name, player] of stemPlayers) {
      if (!selectedStems.has(name) || player.dataset.trackUrl !== tracks.get(name)?.url) {
        player.pause();
        player.removeAttribute("src");
        player.load();
        player.remove();
        stemPlayers.delete(name);
      }
    }
    for (const name of selectedStems) {
      if (stemPlayers.has(name)) continue;
      const track = tracks.get(name);
      const player = new Audio(track.url);
      player.preload = "auto";
      player.hidden = true;
      player.dataset.musicStem = name;
      player.dataset.trackUrl = track.url;
      player.addEventListener("loadedmetadata", () => syncStemPlayback(true));
      player.addEventListener("canplay", () => syncStemPlayback(true));
      player.addEventListener("error", () => {
        if (stemPlayers.get(name) !== player) return;
        source.pause();
        selectedStems.delete(name);
        syncStemPlayers();
        renderStems();
        showStatus("badAudio");
      });
      source.after(player);
      stemPlayers.set(name, player);
    }
    source.muted = selectedStems.size > 0;
    syncStemPlayback(true);
  }

  function selectStem(name) {
    if (restoringWorkspace) return;
    if (!name) selectedStems.clear();
    else if (selectedStems.has(name)) selectedStems.delete(name);
    else selectedStems.add(name);
    syncStemPlayers();
    renderStems();
  }
  for (const event of ["play", "playing", "pause", "ended", "seeking", "seeked", "ratechange", "volumechange"]) {
    source.addEventListener(event, () => syncStemPlayback(event === "seeked"));
  }
  source.addEventListener("timeupdate", () => syncStemPlayback());

  function renderStems() {
    const holder = $("stems");
    holder.replaceChildren();
    if (!stemTracks.length) return;
    const mix = document.createElement("button");
    mix.type = "button";
    mix.className = "chip" + (!selectedStems.size ? " on" : "");
    mix.textContent = strings().mix;
    mix.setAttribute("aria-pressed", String(!selectedStems.size));
    mix.addEventListener("click", () => selectStem(""));
    holder.append(mix);
    for (const name of ["vocals", "drums", "bass", "guitar", "piano", "other"]) {
      const track = stemTracks.find(item => item.name === name);
      if (!track) continue;
      const row = document.createElement("div");
      row.className = "music-video-stem";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chip" + (selectedStems.has(name) ? " on" : "");
      button.textContent = strings()[name];
      button.setAttribute("aria-pressed", String(selectedStems.has(name)));
      button.addEventListener("click", () => selectStem(name));
      const wave = document.createElement("canvas");
      wave.dataset.stemCanvas = name;
      wave.setAttribute("aria-label", strings()[name]);
      wave.addEventListener("pointerdown", event => {
        if (busy || !hasAudio() || event.button !== 0) return;
        const bounds = wave.getBoundingClientRect();
        source.currentTime = Math.min(source.duration, Math.max(0, (event.clientX - bounds.left) / bounds.width * source.duration));
        updateForm();
      });
      const download = document.createElement("a");
      download.href = track.url;
      download.download = `${name}.wav`;
      download.textContent = "WAV ↓";
      row.append(button, wave, download);
      holder.append(row);
    }
    drawWave();
  }
  async function watchStems(id) {
    try {
      const job = await request(`/api/music-workspace/stems/${id}`);
      if (stemJob !== id) return;
      if (job.status === "error") throw Error(job.error);
      if (job.status === "done") {
        stemBusy = false;
        stemTracks = job.tracks;
        syncStemPlayers();
        renderStems();
        $("stem-status").textContent = strings().stemDone + " " + stemRunInfo(job);
        updateForm();
        scheduleWorkspaceSave();
        return;
      }
      const progress = job.phase === "separating"
        ? `${strings().separating} · ${job.progress}%` : strings()[job.phase] || strings().starting;
      $("stem-status").textContent = progress + " " + stemRunInfo(job);
      stemTimer = setTimeout(() => watchStems(id), 2000);
    } catch (error) {
      if (stemJob !== id) return;
      stemBusy = false;
      $("stem-status").textContent = error.message;
      updateForm();
    }
  }
  function stemRunInfo(job) {
    const device = job.device === "cuda" ? "GPU" : job.device === "cpu" ? "CPU" : "";
    const channels = job.channels === 6 ? strings().stemSix : strings().stemFour;
    return [device, channels, job.model, job.preset === "quality" ? strings().stemHigh : job.preset === "fast" ? strings().stemFast : ""].filter(Boolean).join(" · ");
  }
  $("stem-preset").addEventListener("change", updateControls);
  $("stem-channels").addEventListener("change", updateControls);
  $("separate").addEventListener("click", async () => {
    const file = $("song").files[0];
    if (!file || stemBusy) return;
    stemBusy = true;
    updateForm();
    $("stem-status").textContent = strings().starting;
    const songUrl = sourceUrl;
    try {
      const result = await upload("/api/music-workspace/stems", file, {
        device: $("stem-device").value, preset: $("stem-preset").value, channels: $("stem-channels").value,
      });
      if (songUrl !== sourceUrl) return;
      stemJob = result.id;
      scheduleWorkspaceSave();
      await watchStems(result.id);
    } catch (error) {
      stemBusy = false;
      $("stem-status").textContent = error.message;
      updateForm();
    }
  });

  document.addEventListener("h3-workspace", (event) => {
    if (event.detail.workspace !== "music") pausePreview();
  });
  new MutationObserver(translate).observe(document.documentElement, { attributeFilter: ["lang"] });
  new MutationObserver(drawWave).observe(document.documentElement, { attributeFilter: ["data-theme"] });
  new ResizeObserver(drawWave).observe(wave);
  window.addEventListener("pagehide", () => {
    clearTimeout(pollTimer);
    clearTimeout(stemTimer);
    clearTimeout(lyricsTimer);
    pausePreview();
  });
  translate();
  updateForm();
  void initializeMusicWorkspace();
})();
