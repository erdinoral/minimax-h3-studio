(() => {
  const $ = (id) => document.getElementById(`music-video-${id}`);
  const form = $("form");
  if (!form) return;

  const duration = 5;
  const audioLimit = 40 * 1024 * 1024;
  const source = $("source");
  const start = $("start");
  const range = $("range");
  const video = $("result");
  const original = $("original");
  const useOriginal = $("use-original");
  const canvas = $("waveform");
  const wave = canvas.parentElement;
  const qualityOptions = [...$("quality-options").querySelectorAll("[data-quality]")];
  const labels = {
    tr: {
      title: "Müzik Klibi", song: "Şarkı seç", start: "Başlangıç (sn)",
      development: "Geliştirme aşamasında",
      timeline: "Şarkı zaman çizelgesi", none: "Seçilmedi", noPreview: "Henüz önizleme yok",
      loadingWave: "Ses dalgası hazırlanıyor…", badWave: "Ses dalgası okunamadı. Başlangıç saniyesini elle seçebilirsin.",
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
      loadingWave: "Reading waveform…", badWave: "Could not read the waveform. You can still enter a start time.",
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
  const strings = () => labels[document.documentElement.lang] || labels.en;
  let status = "empty";
  let statusDetail = "";
  let busy = false;
  let sourceUrl;
  let characterUrl;
  let auditionEnd = null;
  let lastJob;
  let pollTimer;
  let quality = "736";
  let peaks;
  let waveStatus = "";
  let decoding;

  function showWaveStatus(key) {
    waveStatus = key;
    $("wave-status").textContent = strings()[key] || "";
  }

  function drawWave() {
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
    const offset = Number(range.value);
    const selected = hasRange();
    const from = selected ? width * offset / total : 0;
    const to = selected ? width * (offset + duration) / total : 0;
    if (selected) {
      ctx.globalAlpha = 0.18;
      ctx.fillStyle = accent;
      ctx.fillRect(from, 0, to - from, height);
      ctx.globalAlpha = 1;
    }
    ctx.fillStyle = theme.getPropertyValue("--border");
    ctx.fillRect(0, height / 2, width, 1);
    if (peaks) {
      for (let x = 0; x < width; x += 2) {
        const first = Math.floor(x / width * peaks.length);
        const last = Math.min(peaks.length, Math.ceil((x + 2) / width * peaks.length));
        let peak = 0;
        for (let i = first; i < last; i++) peak = Math.max(peak, peaks[i]);
        const amplitude = Math.max(0.5, peak * (height / 2 - 6));
        ctx.fillStyle = x >= from && x <= to ? accent : theme.getPropertyValue("--muted");
        ctx.fillRect(x, height / 2 - amplitude, 1.25, amplitude * 2);
      }
    }
    if (selected) {
      ctx.fillStyle = accent;
      ctx.fillRect(Math.min(width - 1, from), 0, 1, height);
      ctx.fillRect(Math.min(width - 1, to), 0, 1, height);
      const position = source.currentTime / total * width;
      ctx.fillStyle = theme.getPropertyValue("--text");
      ctx.fillRect(Math.min(width - 1, position), 0, 1, height);
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
    $("song-name").textContent = $("song").files[0]?.name || copy.none;
    $("character-name").textContent = $("character").files[0]?.name || copy.none;
    showWaveStatus(waveStatus);
    showStatus(status, statusDetail);
  }

  function timestamp(seconds) {
    return `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(2).padStart(5, "0")}`;
  }

  function hasRange() {
    return Number.isFinite(source.duration) && source.duration >= duration;
  }

  function updateForm() {
    const ready = hasRange();
    const end = ready ? Math.max(0, Math.floor((source.duration - duration) * 100) / 100) : 0;
    const offset = Math.min(end, Math.max(0, Number(start.value) || 0));
    start.max = range.max = String(end);
    range.value = String(offset);
    $("selection").textContent = `${timestamp(offset)} – ${timestamp(offset + duration)}`;
    start.disabled = range.disabled = $("listen").disabled = busy || !ready;
    $("listen").textContent = auditionEnd === null ? strings().listen : (document.documentElement.lang === "tr" ? "Durdur" : "Stop");
    $("generate").disabled = busy || !ready || !start.validity.valid || !$("character").files.length;
    $("song").disabled = busy || Boolean(decoding);
    for (const id of ["character", "direction"]) $(id).disabled = busy;
    for (const button of qualityOptions) button.disabled = busy;
    drawWave();
  }

  function refreshStage() {
    const preview = $("character-preview");
    preview.hidden = !characterUrl || !video.hidden;
    $("stage").classList.toggle("has-video", !preview.hidden || !video.hidden);
  }

  function pausePreview() {
    source.pause();
    video.pause();
    original.pause();
  }

  $("song").addEventListener("change", () => {
    pausePreview();
    auditionEnd = null;
    if (sourceUrl) URL.revokeObjectURL(sourceUrl);
    sourceUrl = undefined;
    peaks = undefined;
    showWaveStatus("");
    source.removeAttribute("src");
    source.load();
    start.value = "0";
    const file = $("song").files[0];
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
    if (!hasRange()) showStatus("tooShort");
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
  start.addEventListener("input", updateForm);
  range.addEventListener("input", () => { start.value = range.value; updateForm(); });
  let pointer;
  function selectWavePoint(event) {
    const rect = wave.getBoundingClientRect();
    const seconds = (event.clientX - rect.left) / rect.width * source.duration;
    start.value = Math.max(0, Math.min(Number(range.max), seconds)).toFixed(2);
    updateForm();
  }
  wave.addEventListener("pointerdown", (event) => {
    if (range.disabled || event.button !== 0) return;
    source.pause();
    range.focus({ preventScroll: true });
    pointer = event.pointerId;
    wave.setPointerCapture(pointer);
    selectWavePoint(event);
  });
  wave.addEventListener("pointermove", (event) => {
    if (pointer === event.pointerId && !range.disabled) selectWavePoint(event);
  });
  wave.addEventListener("lostpointercapture", () => { pointer = undefined; });
  for (const button of qualityOptions) button.addEventListener("click", () => {
    quality = button.dataset.quality;
    for (const option of qualityOptions) {
      const selected = option === button;
      option.classList.toggle("on", selected);
      option.setAttribute("aria-pressed", String(selected));
    }
  });
  $("listen").addEventListener("click", () => {
    if (!hasRange() || !start.reportValidity()) return;
    if (!source.paused) { source.pause(); return; }
    video.pause();
    source.currentTime = Number(start.value);
    auditionEnd = source.currentTime + duration;
    source.play().catch(() => {
      auditionEnd = null;
      updateForm();
      showStatus("badAudio");
    });
    updateForm();
  });
  source.addEventListener("timeupdate", () => {
    if (auditionEnd !== null && source.currentTime >= auditionEnd) {
      source.pause();
    }
    drawWave();
  });
  source.addEventListener("pause", () => { auditionEnd = null; updateForm(); });
  source.addEventListener("play", () => video.pause());

  function syncOriginal(force = false) {
    video.muted = useOriginal.checked;
    if (!useOriginal.checked || video.paused || video.seeking || !original.src) {
      original.pause();
      return;
    }
    if (force || Math.abs(original.currentTime - video.currentTime) > 0.15) {
      original.currentTime = video.currentTime;
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
  video.addEventListener("timeupdate", () => syncOriginal());
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
      throw new Error(detail || `HTTP ${response.status}`);
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
    updateForm();
  }

  async function watch(job, failures = 0) {
    try {
      const result = await request(`/api/jobs/${encodeURIComponent(job.id)}`);
      if (result.status === "done" && result.output?.url) {
        video.src = result.output.url;
        original.src = job.audio;
        useOriginal.checked = true;
        video.muted = true;
        video.hidden = $("original-toggle").hidden = false;
        refreshStage();
        finish("done");
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
      showStatus("failed", error.message);
      pollTimer = setTimeout(() => watch(job, failures + 1), Math.min(30000, 2500 * (failures + 1)));
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !hasRange() || !form.reportValidity()) return;
    const song = $("song").files[0];
    const character = $("character").files[0];
    if (!song || !character) return;
    const offset = Number(start.value);
    if (!Number.isFinite(offset) || offset < 0 || offset + duration > source.duration + 0.001) return;
    const direction = $("direction").value.trim();
    pausePreview();
    video.hidden = $("original-toggle").hidden = true;
    refreshStage();
    busy = true;
    updateForm();
    showStatus("uploading");
    try {
      const audio = await upload("/api/refs/upload-audio", song, { start: offset, end: offset + duration });
      const image = await upload("/api/refs/upload", character);
      const prompt = [
        "<Picture 1> is the performer and defines their identity, hair and clothing.",
        "<Audio 1> is the exact song excerpt the performer is singing.",
        "One continuous close or medium shot. Match the mouth movements to the sung syllables and pauses in <Audio 1> from the first frame.",
        "Preserve the performer's identity. No spoken dialogue, subtitles or cuts.",
        direction ? `Scene direction: ${direction}` : "A cinematic live performance on a dark stage with soft colored light.",
      ].join(" ");
      const job = await request("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: "ref", ref_images: [image.name], scene_audio_file: audio.filename, scene_audio_mode: "reference",
          prompt, duration, quality, aspect: "16:9", steps: 18, lora_name: "", lora_strengths: {},
          silent_audio: false, asset_auto_match: false, prompt_rewriter_enabled: false, lane: "scene",
        }),
      });
      lastJob = { id: job.id, audio: audio.url };
      try { sessionStorage.setItem("h3.musicVideoJob", JSON.stringify(lastJob)); } catch {}
      await watch(lastJob);
    } catch (error) {
      finish("failed", error.message);
    }
  });

  document.addEventListener("h3-workspace", (event) => {
    if (event.detail.workspace !== "music") pausePreview();
  });
  new MutationObserver(translate).observe(document.documentElement, { attributeFilter: ["lang"] });
  new MutationObserver(drawWave).observe(document.documentElement, { attributeFilter: ["data-theme"] });
  new ResizeObserver(drawWave).observe(wave);
  window.addEventListener("pagehide", () => clearTimeout(pollTimer));
  translate();
  try { lastJob = JSON.parse(sessionStorage.getItem("h3.musicVideoJob") || "null"); } catch {}
  if (lastJob?.id && lastJob.audio) {
    busy = true;
    showStatus("queued");
    void watch(lastJob);
  }
  updateForm();
})();
