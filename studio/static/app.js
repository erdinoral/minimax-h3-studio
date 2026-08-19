(() => {
  const ASPECT_BASE = {
    "16:9": [1920, 1080],
    "9:16": [1080, 1920],
    "1:1": [1080, 1080],
    "21:9": [2560, 1080],
    "4:3": [1440, 1080],
  };

  const state = {
    duration: 5,
    quality: "720",
    aspect: "16:9",
    produceMode: "t2v", // t2v | continue | ref | face | v2v | cinema
    selectedJobId: null,
    clipPrompt: "",
    continueFrom: null,
    pendingContinueChild: null,
    playerCleared: true,
    jobs: [],
    queueItems: [],
    refImages: [], // { name, url }
    faceImages: [],
    v2vVideos: [], // { name, url }
    v2vImages: [],
    storyboardImages: [],
    cinema: { title: "", script: "", characters: [], locations: [] },
    galleryItems: [],
    firstFrameName: null,
    lastFrameName: null,
    refImageSize: "match",
    directorSessionId: null,
    directorReady: false,
    directorBrief: null,
    directorBusy: false,
    directorOnline: false,
    musicId: null,
    musicMeta: null,
    projectPurpose: null, // short_film | music_video | ad | trailer | social | documentary | intro | outro
    projectStyle: null, // realistic | anime | disney | game | cgi_3d | comic | illustration | oil_paint | clay | found_footage
    projectSilent: false,
    progressHideTimer: null,
    lastRunningId: null,
    loraId: "",
    loraStrength: 0.75,
    loraApplied: false,
    loraCatalog: [],
    // Director tabs: per-session chat state
    directorSessions: [], // { id, title, messages: [ {role, content} ] }
    directorSessionCounter: 0,
    directorTab: "chat",
  };

  function purposeLabel(k) {
    return (typeof window.t === "function" ? window.t("purpose." + k) : k) || k;
  }
  function styleLabel(k) {
    return (typeof window.t === "function" ? window.t("style." + k) : k) || k;
  }
  const PURPOSE_KEYS = [
    "short_film",
    "music_video",
    "ad",
    "trailer",
    "social",
    "documentary",
    "intro",
    "outro",
  ];
  const STYLE_KEYS = [
    "realistic",
    "anime",
    "disney",
    "game",
    "cgi_3d",
    "comic",
    "illustration",
    "oil_paint",
    "clay",
    "found_footage",
  ];
  const STYLE_HINT = {
    realistic:
      "photorealistic live-action cinematography, natural skin texture, realistic reflections, film grain",
    anime:
      "high-end Japanese 2D anime cinematic, cel shading, sakuga motion, detailed painted backgrounds — not live-action",
    disney:
      "Disney/Pixar-quality 3D character animation, appealing proportions, subsurface scattering, stylized (not photoreal) faces, studio lighting",
    game:
      "AAA video-game cinematic (Unreal Engine 5), ray-traced lighting, game-character look, cinematic in-engine camera",
    cgi_3d:
      "premium 3D CGI animation, physically based rendering, cinematic studio lighting — not live-action",
    comic:
      "stylized comic-book cinematic, inked linework, graphic color blocking, halftone accents",
    illustration: "illustrated storybook cinematic, painterly 2D, storybook lighting",
    oil_paint: "oil-painting animated cinematic, visible brushstrokes, classical palette",
    clay: "claymation / stop-motion look, tactile clay surfaces, miniature set lighting",
    found_footage: "handheld found-footage documentary camera, natural light, raw texture",
  };

  function tt(key) {
    return typeof t === "function" ? t(key) : key;
  }
  function tf(key, map) {
    let s = tt(key);
    if (map) {
      Object.keys(map).forEach((k) => {
        s = s.split("{" + k + "}").join(String(map[k]));
      });
    }
    return s;
  }
  function uiLang() {
    return typeof h3Lang === "function" ? h3Lang() : "tr";
  }

  const CINEMA_SETUP_OPTIONS = {
    look: [
      ["auto", "Auto"],
      ["feature", "Sinematik"],
      ["handheld", "El kamerası"],
      ["documentary", "Belgesel"],
      ["commercial", "Reklam"],
      ["music_video", "Klip"],
      ["anamorphic", "Anamorphic"],
      ["found_footage", "Found footage"],
    ],
    camera: [
      ["auto", "Auto"],
      ["35mm", "35mm"],
      ["anamorphic2x", "Anamorphic 2x"],
      ["16mm", "16mm"],
      ["imax65", "IMAX 65mm"],
      ["steadicam", "Steadicam"],
      ["handheld", "Handheld"],
      ["drone", "Drone"],
      ["iphone", "iPhone"],
      ["gopro", "GoPro"],
      ["crane", "Crane"],
    ],
    palette: [
      ["auto", "Auto"],
      ["teal_orange", "Teal & orange"],
      ["noir", "Noir"],
      ["warm", "Warm"],
      ["cold", "Cold"],
      ["neon", "Neon"],
      ["pastel", "Pastel"],
      ["bleach", "Bleach bypass"],
      ["golden_hour", "Golden hour"],
      ["kodak", "Kodak"],
      ["rec709", "Rec.709"],
    ],
    lighting: [
      ["auto", "Auto"],
      ["natural", "Natural"],
      ["studio", "Studio"],
      ["neon", "Neon"],
      ["candle", "Candle"],
      ["overcast", "Overcast"],
      ["hard_sun", "Hard sun"],
      ["moonlight", "Moonlight"],
      ["volumetric", "Volumetric"],
      ["practical", "Practical"],
    ],
    era: [
      ["auto", "Auto"],
      ["1920s", "1920s"],
      ["1950s", "1950s"],
      ["1970s", "1970s"],
      ["1980s", "1980s"],
      ["1990s", "1990s"],
      ["2000s", "2000s"],
      ["present", "Günümüz"],
      ["near_future", "Yakın gelecek"],
      ["medieval", "Ortaçağ"],
      ["ancient", "Antik"],
    ],
  };
  const CINEMA_SETUP_META = {
    look: { label: "Film setup", icon: "🎞" },
    camera: { label: "Camera", icon: "📷" },
    palette: { label: "Color palette", icon: "🎨" },
    lighting: { label: "Lighting", icon: "💡" },
    era: { label: "Era", icon: "📅" },
    purpose: { label: "Purpose", icon: "🎬" },
    style: { label: "Style", icon: "✦" },
  };

  function cinemaId() {
    return (
      (crypto.randomUUID && crypto.randomUUID()) ||
      "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
    );
  }

  function emptyCinema() {
    return {
      title: "",
      script: "",
      shots: [],
      setup: {
        look: "auto",
        camera: "auto",
        palette: "auto",
        lighting: "auto",
        era: "auto",
        purpose: "auto",
        style: "auto",
      },
      duration: 5,
      quality: "720",
      steps: 20,
      audio: {
        mode: "film",
        score_id: "",
        score_name: "",
        voice_lang: "Turkish",
        last_batch: "",
      },
      characters: [],
      locations: [],
    };
  }

  function ensureCinema() {
    const base = emptyCinema();
    state.cinema = { ...base, ...(state.cinema || {}) };
    state.cinema.setup = { ...base.setup, ...(state.cinema.setup || {}) };
    state.cinema.audio = { ...base.audio, ...(state.cinema.audio || {}) };
    if (!Array.isArray(state.cinema.shots)) state.cinema.shots = [];
    if (!Array.isArray(state.cinema.characters)) state.cinema.characters = [];
    if (!Array.isArray(state.cinema.locations)) state.cinema.locations = [];
    return state.cinema;
  }

  function cinemaSetupOptions(key) {
    if (key === "purpose") {
      return [["auto", "Auto"]].concat(PURPOSE_KEYS.map((id) => [id, purposeLabel(id)]));
    }
    if (key === "style") {
      return [["auto", "Auto"]].concat(STYLE_KEYS.map((id) => [id, styleLabel(id)]));
    }
    return CINEMA_SETUP_OPTIONS[key] || [["auto", "Auto"]];
  }

  function cinemaSetupValueLabel(key, id) {
    const found = cinemaSetupOptions(key).find((row) => row[0] === id);
    return (found && found[1]) || "Auto";
  }

  function withStyleLock(prompt) {
    const s = state.projectStyle;
    const hint = s && STYLE_HINT[s];
    if (!hint) return prompt;
    const needle = hint.slice(0, 28).toLowerCase();
    if ((prompt || "").toLowerCase().includes(needle)) return prompt;
    return `${(prompt || "").trim()}\n\nVisual style lock: ${hint}. Stay in this look for the whole shot.`;
  }

  const $ = (id) => document.getElementById(id);

  function toast(msg) {
    $("prod-text").textContent = msg;
  }

  async function copyText(text, okMsg) {
    const t = (text == null ? "" : String(text)).trim();
    if (!t) {
      toast("Prompt yok");
      return false;
    }
    try {
      await navigator.clipboard.writeText(t);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = t;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
      } finally {
        ta.remove();
      }
    }
    toast(okMsg || "Prompt kopyalandı");
    return true;
  }

  function setClipPrompt(text, meta) {
    state.clipPrompt = text == null ? "" : String(text);
    const has = !!state.clipPrompt.trim();
    const pre = $("clip-prompt-text");
    if (pre) pre.textContent = has ? state.clipPrompt : "(prompt yok)";
    const metaEl = $("clip-prompt-meta");
    if (metaEl) metaEl.textContent = meta || "";
    $("btn-open-prompt")?.classList.toggle("hidden", !has);
  }

  function openPromptView(text, meta) {
    if (text !== undefined) setClipPrompt(text, meta);
    const t = (state.clipPrompt || "").trim();
    if (!t) {
      toast("Bu videonun prompt’u yok");
      return;
    }
    const pre = $("clip-prompt-text");
    if (pre) pre.textContent = t;
    $("view-clip-prompt")?.classList.remove("hidden");
  }

  function closePromptView() {
    $("view-clip-prompt")?.classList.add("hidden");
  }

  function syncFilePickName(input) {
    const wrap = input?.closest?.(".file-pick");
    const nameEl = wrap?.querySelector(".file-pick-name");
    if (!nameEl) return;
    const files = input.files;
    if (!files || !files.length) return;
    nameEl.textContent = files.length === 1 ? files[0].name : `${files.length} dosya`;
    nameEl.classList.add("has-file");
    nameEl.title = Array.from(files).map((f) => f.name).join(", ");
  }

  function setProgress(pct, label, show) {
    const wrap = $("progress-wrap");
    const fill = $("progress-fill");
    const pctEl = $("progress-pct");
    const lab = $("progress-label");
    if (!wrap || !fill || !pctEl || !lab) return;
    const n = Math.max(0, Math.min(100, Number(pct) || 0));
    if (show === false) {
      wrap.classList.add("hidden");
      lab.textContent = "";
      fill.style.width = "0%";
      pctEl.textContent = "0%";
      return;
    }
    wrap.classList.remove("hidden");
    fill.style.width = `${n}%`;
    pctEl.textContent = `${Math.round(n)}%`;
    lab.textContent = label || "";
  }

  function hideProgressNow() {
    if (state.progressHideTimer) {
      clearTimeout(state.progressHideTimer);
      state.progressHideTimer = null;
    }
    state.lastRunningId = null;
    setProgress(0, "", false);
  }

  function scheduleHideProgress(ms = 1800) {
    if (state.progressHideTimer) {
      clearTimeout(state.progressHideTimer);
      state.progressHideTimer = null;
    }
    state.progressHideTimer = setTimeout(() => {
      state.progressHideTimer = null;
      setProgress(0, "", false);
    }, ms);
  }

  function syncDirectorDockHeight() {
    const dock = document.getElementById("director-dock");
    if (!dock) return;
    const root = document.documentElement;
    // Height comes from .director.size-* / .collapsed — clear stale root overrides
    root.style.removeProperty("--director-h");
    if (dock.classList.contains("modal-open")) {
      // Modal floats — keep a thin strip so workspace isn't shoved
      root.style.setProperty("--director-pad", "56px");
      return;
    }
    // Pad = real dock height so Prompt Üret / gen-hint sit above the dock (not under it)
    const apply = () => {
      const h = Math.ceil(dock.getBoundingClientRect().height) || 56;
      root.style.setProperty("--director-pad", `${Math.max(56, h)}px`);
    };
    apply();
    requestAnimationFrame(apply);
  }

  function setDirectorOpen(open) {
    const dock = $("director-dock");
    if (!dock) return;
    if (!open) {
      setDirectorModal(false);
      dock.classList.add("collapsed");
    } else {
      dock.classList.remove("collapsed");
      // Clear any leftover modal inline geometry
      dock.style.removeProperty("left");
      dock.style.removeProperty("right");
      dock.style.removeProperty("top");
      dock.style.removeProperty("bottom");
      dock.style.removeProperty("height");
      dock.style.removeProperty("width");
    }
    syncDirectorDockHeight();
  }

  const DIR_SIZES = ["size-sm", "size-md", "size-lg"];
  function directorSizeIndex() {
    const dock = $("director-dock");
    return Math.max(0, DIR_SIZES.findIndex((c) => dock.classList.contains(c)));
  }
  function setDirectorSize(idx) {
    const dock = $("director-dock");
    const i = Math.max(0, Math.min(DIR_SIZES.length - 1, idx));
    DIR_SIZES.forEach((c) => dock.classList.remove(c));
    dock.classList.add(DIR_SIZES[i]);
    dock.style.height = "";
    dock.style.removeProperty("--director-h");
    try {
      localStorage.setItem("h3_director_size", DIR_SIZES[i]);
    } catch {
      /* ignore */
    }
    syncDirectorDockHeight();
  }
  function setDirectorModal(open) {
    const dock = $("director-dock");
    const backdrop = $("director-backdrop");
    if (!dock) return;
    if (open) {
      dock.classList.remove("collapsed");
    } else {
      // Restore bottom-dock geometry after modal
      dock.style.removeProperty("left");
      dock.style.removeProperty("right");
      dock.style.removeProperty("top");
      dock.style.removeProperty("bottom");
      dock.style.removeProperty("height");
      dock.style.removeProperty("width");
    }
    dock.classList.toggle("modal-open", !!open);
    backdrop?.classList.toggle("hidden", !open);
    $("btn-dir-modal")?.classList.toggle("on", !!open);
    if ($("btn-dir-modal")) {
      $("btn-dir-modal").textContent = open ? "✕" : "⛶";
      $("btn-dir-modal").title = open ? "Küçük panele dön" : "Sohbeti büyüt — chat burada";
    }
    try {
      localStorage.setItem("h3_director_modal", open ? "1" : "0");
    } catch {
      /* ignore */
    }
    syncDirectorDockHeight();
    const log = $("director-log");
    if (log) log.scrollTop = log.scrollHeight;
    if (open) $("director-msg")?.focus();
  }

  $("btn-dir-smaller").onclick = () => {
    if ($("director-dock").classList.contains("modal-open")) setDirectorModal(false);
    setDirectorOpen(true);
    setDirectorSize(directorSizeIndex() - 1);
  };
  $("btn-dir-bigger").onclick = () => {
    setDirectorOpen(true);
    if ($("director-dock").classList.contains("modal-open")) return;
    const idx = directorSizeIndex();
    if (idx >= DIR_SIZES.length - 1) {
      setDirectorModal(true);
      return;
    }
    setDirectorSize(idx + 1);
  };
  $("btn-dir-modal").onclick = () => {
    setDirectorOpen(true);
    setDirectorModal(!$("director-dock").classList.contains("modal-open"));
  };
  $("btn-dir-collapse").onclick = () => setDirectorOpen(false);
  $("director-backdrop").onclick = () => {
    setDirectorModal(false);
    setDirectorOpen(false);
  };
  window.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if ($("director-dock").classList.contains("modal-open")) {
      setDirectorModal(false);
    } else if (!$("director-dock").classList.contains("collapsed")) {
      setDirectorOpen(false);
    }
  });

  // Drag-resize removed — it covered the studio. Use − / + / ⛶ only.
  (() => {
    const dock = $("director-dock");
    if (!dock) return;
    dock.style.height = "";
    dock.style.removeProperty("--director-h");
  })();

  // restore size prefs (panel stays collapsed until user types)
  try {
    const saved = localStorage.getItem("h3_director_size");
    if (saved && DIR_SIZES.includes(saved)) {
      DIR_SIZES.forEach((c) => $("director-dock").classList.remove(c));
      $("director-dock").classList.add(saved);
    }
  } catch {
    /* ignore */
  }

  function setDuration(sec) {
    const n = Number(sec);
    if (![4, 5, 6, 8, 10, 15].includes(n)) return;
    state.duration = n;
    document
      .querySelectorAll("#dur-chips .chip, #dur-chips-cont .chip, #dur-chips-story .chip")
      .forEach((b) => {
        b.classList.toggle("on", Number(b.dataset.dur) === n);
      });
    if (typeof keepLoraApplied === "function") keepLoraApplied();
    if (typeof syncProjectChips === "function") syncProjectChips();
  }

  // Official H3 sizes (multiple of 32). UI "720" key → real 1280×736 (736p).
  const H3_QUALITY_SIZES = {
    "16:9": { 480: [864, 480], 720: [1280, 736], 1080: [1920, 1088] },
    "9:16": { 480: [480, 864], 720: [736, 1280], 1080: [1088, 1920] },
    "1:1": { 480: [480, 480], 720: [736, 736], 1080: [1088, 1088] },
    "21:9": { 480: [1024, 448], 720: [1536, 672], 1080: [2176, 960] },
    "4:3": { 480: [640, 480], 720: [960, 736], 1080: [1440, 1088] },
  };

  function resolveSize(aspect, quality) {
    const q = Number(quality) || 720;
    const preset = H3_QUALITY_SIZES[aspect] && H3_QUALITY_SIZES[aspect][q];
    if (preset) return preset;
    const base = ASPECT_BASE[aspect] || ASPECT_BASE["16:9"];
    // Map marketing tiers to H3 short-edge (×32): 480→480, 720→736, 1080→1088
    const shortTarget = { 480: 480, 720: 736, 1080: 1088 }[q] || 736;
    const short = Math.min(base[0], base[1]) || 1;
    const scale = shortTarget / short;
    const snap32 = (v) => Math.max(32, Math.round(v / 32) * 32);
    return [snap32(base[0] * scale), snap32(base[1] * scale)];
  }

  function qualityChipLabel(quality, aspect) {
    const [w, h] = resolveSize(aspect, quality);
    const short = Math.min(w, h);
    return `${short}p`;
  }

  function setAspect(a) {
    const allowed = ["16:9", "9:16", "1:1", "21:9", "4:3"];
    const v = allowed.includes(a) ? a : "16:9";
    state.aspect = v;
    document.querySelectorAll("#aspect-chips .chip").forEach((b) => {
      b.classList.toggle("on", b.dataset.aspect === v);
    });
    setQuality(state.quality);
  }

  function setQuality(q) {
    const v = String(q);
    if (!["480", "720", "1080"].includes(v)) return;
    state.quality = v;
    const aspect = state.aspect || "16:9";
    document.querySelectorAll("#quality-chips .chip, #quality-chips-cont .chip").forEach((b) => {
      b.classList.toggle("on", b.dataset.q === v);
      // Show real H3 short edge (736p / 1088p), not marketing 720/1080
      b.textContent = qualityChipLabel(b.dataset.q, aspect);
    });
    const [w, h] = resolveSize(aspect, v);
    const hintTxt = `${w}×${h} · H3 (×32)`;
    const hint = $("quality-hint");
    if (hint) hint.textContent = hintTxt;
    const hintCont = $("quality-hint-cont");
    if (hintCont) hintCont.textContent = hintTxt;
    if (typeof keepLoraApplied === "function") keepLoraApplied();
  }

  function refreshModeHints() {
    const m = state.produceMode || "t2v";
    const hintNew = $("mode-hint-new");
    if (hintNew) {
      const key =
        m === "ref"
          ? "hint.ref"
          : m === "face"
            ? "hint.face"
            : m === "v2v"
              ? "hint.v2v"
              : "hint.t2v";
      hintNew.textContent = tt(key);
    }
    const hint = $("gen-hint");
    if (!hint) return;
    let text = tt("hint.mode." + (m === "storyboard" ? "cinema" : m));
    if (!text || text.indexOf("hint.mode.") === 0) text = tt("hint.mode.t2v");
    if (state.projectPurpose === "music_video" || state.projectSilent) {
      text += tt("hint.silent");
    } else if (state.projectPurpose) {
      text += ` · ${purposeLabel(state.projectPurpose)}${tt("hint.av")}`;
    }
    hint.textContent = text;
  }

  function setProduceMode(mode) {
    const allowed = ["t2v", "continue", "ref", "face", "v2v", "cinema", "storyboard"];
    const m = allowed.includes(mode) ? (mode === "storyboard" ? "cinema" : mode) : "t2v";
    state.produceMode = m;
    document.querySelectorAll("#mode-chips .chip").forEach((b) => {
      b.classList.toggle("on", b.dataset.mode === m);
    });
    const showSettings = m === "t2v" || m === "ref" || m === "face" || m === "v2v";
    $("panel-mode-new")?.classList.toggle("hidden", !showSettings);
    $("fl2va-frames")?.classList.toggle("hidden", m !== "t2v");
    $("panel-mode-continue")?.classList.toggle("hidden", m !== "continue");
    $("panel-mode-ref")?.classList.toggle("hidden", m !== "ref");
    $("panel-mode-face")?.classList.toggle("hidden", m !== "face");
    $("panel-mode-v2v")?.classList.toggle("hidden", m !== "v2v");
    $("panel-mode-cinema")?.classList.toggle("hidden", m !== "cinema");
    $("panel-mode-storyboard")?.classList.toggle("hidden", true);
    refreshModeHints();
    if (m === "continue") {
      const prefer = state.continueFrom || state.selectedJobId || "";
      void fillContinueSource().then(() => {
        const src = prefer || $("continue-source")?.value || "";
        if (src) void setContinueMode(src, { silent: true });
      });
    } else {
      state.continueFrom = null;
      $("continue-box")?.classList.add("hidden");
    }
    if (m === "cinema") void openCinemaStudio();
    if (typeof keepLoraApplied === "function") keepLoraApplied();
  }

  function renderRefThumbs(kind) {
    const isFace = kind === "face";
    const list = isFace ? state.faceImages : state.refImages;
    const grid = $(isFace ? "face-thumbs" : "ref-thumbs");
    if (!grid) return;
    grid.innerHTML = "";
    list.forEach((item, i) => {
      const card = document.createElement("div");
      card.className = "ref-thumb";
      card.innerHTML = `<span class="ref-ord">&lt;Picture ${i + 1}&gt;</span><img src="${item.url}" alt="ref ${i + 1}" /><button type="button" title="Kaldır">×</button>`;
      card.querySelector("button").onclick = () => {
        list.splice(i, 1);
        renderRefThumbs(kind);
      };
      grid.appendChild(card);
    });
  }

  async function uploadRefFiles(fileList, kind) {
    const isFace = kind === "face";
    const target = isFace ? state.faceImages : state.refImages;
    const max = isFace ? 3 : 9;
    const files = Array.from(fileList || []);
    if (!files.length) return;
    for (const file of files) {
      if (target.length >= max) {
        toast(isFace ? "Yüz için en fazla 3 foto" : "En fazla 9 referans");
        break;
      }
      const fd = new FormData();
      fd.append("file", file);
      toast(`Yükleniyor · ${file.name}`);
      try {
        const r = await fetch("/api/refs/upload", { method: "POST", body: fd });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errDetail(data));
        target.push({ name: data.name, url: data.url || `#` });
      } catch (e) {
        toast(String(e.message || e));
      }
    }
    renderRefThumbs(kind);
    toast(isFace ? `${target.length} yüz hazır` : `${target.length} referans hazır`);
  }

  function renderNamedThumbs(list, gridId, labelFn) {
    const grid = $(gridId);
    if (!grid) return;
    grid.innerHTML = "";
    list.forEach((item, i) => {
      const card = document.createElement("div");
      card.className = "ref-thumb";
      const label = labelFn ? labelFn(i, item) : `#${i + 1}`;
      const media = item.kind === "video"
        ? `<video src="${item.url}" muted preload="metadata"></video>`
        : `<img src="${item.url}" alt="${label}" />`;
      card.innerHTML = `<span class="ref-ord">${label}</span>${media}<button type="button" title="Kaldır">×</button>`;
      card.querySelector("button").onclick = () => {
        list.splice(i, 1);
        renderNamedThumbs(list, gridId, labelFn);
      };
      grid.appendChild(card);
    });
  }

  async function uploadVideoFiles(fileList, targetList, gridId) {
    const files = Array.from(fileList || []);
    for (const file of files) {
      if (targetList.length >= 3) {
        toast("En fazla 3 video");
        break;
      }
      const fd = new FormData();
      fd.append("file", file);
      toast(`Video yükleniyor · ${file.name}`);
      try {
        const r = await fetch("/api/refs/upload-video", { method: "POST", body: fd });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errDetail(data));
        targetList.push({
          name: data.name,
          url: data.url || "#",
          kind: "video",
        });
      } catch (e) {
        toast(String(e.message || e));
      }
    }
    renderNamedThumbs(targetList, gridId, (i) => `Video ${i + 1}`);
    toast(`${targetList.length} video hazır`);
  }

  async function uploadImageToList(fileList, targetList, gridId, max, labelFn) {
    const files = Array.from(fileList || []);
    for (const file of files) {
      if (targetList.length >= max) {
        toast(`En fazla ${max} görsel`);
        break;
      }
      const fd = new FormData();
      fd.append("file", file);
      toast(`Yükleniyor · ${file.name}`);
      try {
        const r = await fetch("/api/refs/upload", { method: "POST", body: fd });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errDetail(data));
        targetList.push({ name: data.name, url: data.url || "#" });
      } catch (e) {
        toast(String(e.message || e));
      }
    }
    renderNamedThumbs(targetList, gridId, labelFn);
  }

  async function uploadSingleFrame(file, which) {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    toast(`${which} frame yükleniyor…`);
    try {
      const r = await fetch("/api/refs/upload", { method: "POST", body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (which === "first") {
        state.firstFrameName = data.name;
        renderNamedThumbs(
          [{ name: data.name, url: data.url }],
          "first-frame-thumb",
          () => "First"
        );
      } else {
        state.lastFrameName = data.name;
        renderNamedThumbs(
          [{ name: data.name, url: data.url }],
          "last-frame-thumb",
          () => "Last"
        );
      }
      toast(`${which} frame hazır`);
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function loadCinema() {
    try {
      const data = await fetch("/api/cinema").then((r) => r.json());
      const base = emptyCinema();
      state.cinema = {
        ...base,
        title: data.title || "",
        script: data.script || "",
        shots: Array.isArray(data.shots) ? data.shots : [],
        setup: { ...base.setup, ...(data.setup || {}) },
        audio: { ...base.audio, ...(data.audio || {}) },
        duration: data.duration || 5,
        quality: String(data.quality || "720"),
        steps: data.steps || 20,
        characters: Array.isArray(data.characters) ? data.characters : [],
        locations: Array.isArray(data.locations) ? data.locations : [],
      };
    } catch {
      state.cinema = ensureCinema();
    }
    renderCinema();
  }

  function flushCinemaFields() {
    const c = ensureCinema();
    const pull = (rootId, kind) => {
      $(rootId)
        ?.querySelectorAll(".cinema-card")
        .forEach((card) => {
          const item = cinemaItem(kind, card.dataset.id);
          if (!item) return;
          card.querySelectorAll("[data-field]").forEach((el) => {
            const field = el.dataset.field;
            if (!field) return;
            item[field] = el.value;
          });
        });
    };
    pull("cinema-chars", "character");
    pull("cinema-locs", "location");
    $("cinema-shots")
      ?.querySelectorAll(".cinema-shot")
      .forEach((card) => {
        const shot = cinemaShotById(card.dataset.id);
        const ta = card.querySelector("[data-field='text']");
        if (shot && ta) shot.text = ta.value;
      });
    if ($("cinema-title")) c.title = $("cinema-title").value || c.title || "";
    if ($("cinema-duration")) c.duration = Number($("cinema-duration").value) || 5;
    if ($("cinema-steps")) c.steps = Number($("cinema-steps").value) || 20;
    return c;
  }

  function cinemaPayload() {
    const c = flushCinemaFields();
    c.title = $("cinema-title")?.value || c.title || "";
    if ($("cinema-duration")) c.duration = Number($("cinema-duration").value) || 5;
    if ($("cinema-steps")) c.steps = Number($("cinema-steps").value) || 20;
    return {
      title: c.title,
      script: (c.shots || [])
        .map((s) => (s.text || "").trim())
        .filter(Boolean)
        .join("\n\n---\n\n"),
      shots: c.shots || [],
      setup: c.setup || {},
      audio: c.audio || {},
      duration: c.duration || 5,
      quality: c.quality || "720",
      steps: c.steps || 20,
      characters: c.characters || [],
      locations: c.locations || [],
    };
  }

  async function saveCinema(quiet) {
    const payload = cinemaPayload();
    try {
      const r = await fetch("/api/cinema", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await r.json().catch(() => payload);
      if (!r.ok) throw new Error(errDetail(data));
      const base = emptyCinema();
      state.cinema = {
        ...base,
        title: data.title || payload.title,
        script: data.script || payload.script,
        shots: data.shots || payload.shots,
        setup: { ...base.setup, ...(data.setup || payload.setup || {}) },
        audio: { ...base.audio, ...(data.audio || payload.audio || {}) },
        duration: data.duration || payload.duration,
        quality: String(data.quality || payload.quality),
        steps: data.steps || payload.steps,
        characters: data.characters || payload.characters,
        locations: data.locations || payload.locations,
      };
      if (!quiet) toast("Sinema stüdyosu kaydedildi");
    } catch (e) {
      if (!quiet) toast(String(e.message || e));
    }
  }

  function cinemaLoraOptions(selected) {
    const catalog = state.loraCatalog || [];
    const opts = ['<option value="">LoRA yok</option>'];
    catalog.forEach((spec) => {
      if (!spec.id || !spec.file) return;
      if (spec.ready === false) return;
      const graphs = spec.graphs || ["fl2va", "ref2va"];
      if (!graphs.includes("ref2va")) return;
      const sel = spec.id === selected ? " selected" : "";
      opts.push(
        '<option value="' +
          htmlEsc(spec.id) +
          '"' +
          sel +
          ">" +
          htmlEsc(spec.label || spec.id) +
          "</option>"
      );
    });
    return opts.join("");
  }

  function htmlEsc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function cinemaCardHtml(item, kind) {
    const img = item.image
      ? '<img src="' + htmlEsc(item.url || "/api/refs/" + item.image) + '" alt="" />'
      : '<span class="empty">görsel yok</span>';
    const isChar = kind === "character";
    const nameLabel = isChar ? "Karakter adı" : "Bölge adı";
    const descLabel = isChar ? "Karakter tanımı" : "Tanım";
    const namePh = isChar ? "Ada" : "Rooftop";
    const descPh = isChar
      ? "Yaş, görünüm, giyim, kişilik…"
      : "Mekân, saat, atmosfer…";
    const lora = isChar
      ? '<label class="cinema-field-label">Karakter LoRA (isteğe bağlı)</label><select data-field="lora_id">' +
        cinemaLoraOptions(item.lora_id || "") +
        "</select>"
      : "";
    return (
      '<div class="cinema-card" data-id="' +
      htmlEsc(item.id) +
      '" data-kind="' +
      kind +
      '"><div class="thumb">' +
      img +
      '</div><div class="fields">' +
      '<label class="cinema-field-label">' +
      nameLabel +
      "</label>" +
      '<input data-field="name" placeholder="' +
      namePh +
      '" value="' +
      htmlEsc(item.name) +
      '" />' +
      '<label class="cinema-field-label">' +
      descLabel +
      "</label>" +
      '<textarea data-field="notes" rows="3" placeholder="' +
      descPh +
      '">' +
      htmlEsc(item.notes) +
      "</textarea>" +
      (isChar
        ? '<label class="cinema-field-label">Ses tarifi (her shot aynı)</label>' +
          '<textarea data-field="voice" rows="2" placeholder="ör. 28 yaş, düşük sıcak alto, İstanbul aksanı, asla fısıldamaz">' +
          htmlEsc(item.voice) +
          "</textarea>"
        : "") +
      lora +
      '<div class="row-btns"><label class="file-pick file-pick-inline">' +
      '<input type="file" class="file-pick-input cinema-img" accept="image/*" />' +
      '<span class="file-pick-btn">Görsel yükle</span></label>' +
      '<button type="button" class="btn-ghost cinema-del">Sil</button></div></div></div>'
    );
  }

  function filmPillHtml(key, value) {
    const meta = CINEMA_SETUP_META[key] || { label: key, icon: "•" };
    const opts = cinemaSetupOptions(key)
      .map((row) => {
        const on = row[0] === value ? " on" : "";
        return (
          '<button type="button" class="film-pill-option' +
          on +
          '" data-id="' +
          htmlEsc(row[0]) +
          '">' +
          htmlEsc(row[1]) +
          "</button>"
        );
      })
      .join("");
    return (
      '<div class="film-pill" data-setup="' +
      htmlEsc(key) +
      '" role="button" tabindex="0"><span class="film-pill-icon">' +
      htmlEsc(meta.icon) +
      '</span><span class="film-pill-copy"><span class="film-pill-label">' +
      htmlEsc(meta.label) +
      '</span><span class="film-pill-value">' +
      htmlEsc(cinemaSetupValueLabel(key, value)) +
      '</span></span><div class="film-pill-menu">' +
      opts +
      "</div></div>"
    );
  }

  function cinemaShotHtml(shot, index) {
    const mode = shot.mode === "continue" ? "continue" : "t2v";
    return (
      '<article class="cinema-shot" data-id="' +
      htmlEsc(shot.id) +
      '"><div class="cinema-shot-head"><span class="idx">Shot ' +
      (index + 1) +
      '</span><div class="cinema-shot-mode">' +
      '<button type="button" class="t2v' +
      (mode === "t2v" ? " on" : "") +
      '" data-mode="t2v">Yeni video</button>' +
      '<button type="button" class="continue' +
      (mode === "continue" ? " on" : "") +
      '" data-mode="continue">Continue</button></div>' +
      '<button type="button" class="btn-ghost cinema-shot-del">Sil</button></div>' +
      '<textarea data-field="text" rows="3" placeholder="Bu shot’ta ne olur?">' +
      htmlEsc(shot.text) +
      "</textarea></article>"
    );
  }

  function renderCinemaPills() {
    const host = $("cinema-pills");
    if (!host) return;
    const c = ensureCinema();
    const keys = ["look", "camera", "palette", "lighting", "era", "purpose", "style"];
    if (host.querySelector(".film-pill.open")) {
      host.querySelectorAll(".film-pill").forEach((pill) => {
        const key = pill.dataset.setup;
        const val = (c.setup && c.setup[key]) || "auto";
        const valueEl = pill.querySelector(".film-pill-value");
        if (valueEl) valueEl.textContent = cinemaSetupValueLabel(key, val);
        pill.querySelectorAll(".film-pill-option").forEach((opt) => {
          opt.classList.toggle("on", opt.dataset.id === val);
        });
      });
      return;
    }
    host.innerHTML = keys
      .map((key) => filmPillHtml(key, (c.setup && c.setup[key]) || "auto"))
      .join("");
  }

  function renderCinemaKnobs() {
    const c = ensureCinema();
    const dur = $("cinema-duration");
    if (dur && document.activeElement !== dur) dur.value = String(c.duration || 5);
    const steps = $("cinema-steps");
    if (steps && document.activeElement !== steps) steps.value = String(c.steps || 20);
    const chips = $("cinema-quality-chips");
    if (chips) {
      chips.querySelectorAll("button").forEach((btn) => {
        btn.classList.toggle("on", btn.dataset.quality === String(c.quality || "720"));
      });
    }
  }

  function cinemaAudio() {
    const c = ensureCinema();
    c.audio = c.audio || {};
    if (!c.audio.mode) c.audio.mode = "film";
    return c.audio;
  }

  function renderCinemaAudio() {
    const audio = cinemaAudio();
    const host = $("cinema-audio-mode");
    if (host) {
      host.querySelectorAll("[data-audio]").forEach((btn) => {
        btn.classList.toggle("on", btn.dataset.audio === audio.mode);
      });
    }
    const name = $("cinema-score-name");
    if (name) {
      name.textContent = audio.score_name
        ? audio.score_name
        : "yok — H3 her klipte yeni şarkı uydurur; bir kez yükle";
    }
    const mux = $("btn-cinema-mux");
    if (mux) {
      const ready = Boolean(audio.score_id && audio.last_batch);
      mux.classList.toggle("hidden", !audio.score_id);
      mux.disabled = !ready;
      mux.textContent = ready
        ? "Aynı müziği filme karıştır"
        : audio.score_id
          ? "Önce filmi üret, sonra karıştır"
          : "Aynı müziği filme karıştır";
    }
    const final = $("cinema-final-link");
    if (final) {
      if (audio.last_batch) {
        final.href = "/api/cinema/final/" + encodeURIComponent(audio.last_batch);
        final.classList.remove("hidden");
      } else {
        final.classList.add("hidden");
      }
    }
  }

  function renderCinemaShots() {
    const host = $("cinema-shots");
    if (!host) return;
    const shots = ensureCinema().shots || [];
    host.innerHTML = shots.map((s, i) => cinemaShotHtml(s, i)).join("");
  }

  function renderCinema() {
    const c = ensureCinema();
    if ($("cinema-title") && document.activeElement !== $("cinema-title")) {
      $("cinema-title").value = c.title || "";
    }
    renderCinemaPills();
    renderCinemaKnobs();
    renderCinemaAudio();
    const chars = $("cinema-chars");
    const locs = $("cinema-locs");
    const active = document.activeElement;
    const typingCards =
      active &&
      ((chars && chars.contains(active)) || (locs && locs.contains(active)));
    if (chars && !typingCards) {
      chars.innerHTML = (c.characters || []).map((x) => cinemaCardHtml(x, "character")).join("");
    }
    if (locs && !typingCards) {
      locs.innerHTML = (c.locations || []).map((x) => cinemaCardHtml(x, "location")).join("");
    }
    if (
      $("cinema-shots") &&
      document.activeElement &&
      $("cinema-shots").contains(document.activeElement)
    ) {
      /* keep typing */
    } else {
      renderCinemaShots();
    }
    const nC = (c.characters || []).length;
    const nL = (c.locations || []).length;
    const nS = (c.shots || []).filter((s) => (s.text || "").trim()).length;
    if ($("cinema-hint")) {
      $("cinema-hint").textContent =
        `${nC} karakter · ${nL} mekan · ${nS} shot — ses tarifi kilitlenir, müzik bir kez yüklenir.`;
    }
    syncCinemaFold();
  }

  const CINEMA_FOLD_KEY = "h3-cinema-fold";

  function cinemaFoldState() {
    let stored = {};
    try {
      stored = JSON.parse(localStorage.getItem(CINEMA_FOLD_KEY) || "{}") || {};
    } catch {
      stored = {};
    }
    return {
      characters: stored.characters !== false,
      locations: stored.locations !== false,
    };
  }

  function setCinemaFold(key, open) {
    const next = cinemaFoldState();
    next[key] = !!open;
    try {
      localStorage.setItem(CINEMA_FOLD_KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
    syncCinemaFold();
  }

  function cinemaFoldSummaryHtml(items, emptyLabel) {
    const chips = (items || [])
      .map((x) => (x.name || "").trim() || "isimsiz")
      .map((name) => '<span class="cinema-fold-chip">' + htmlEsc(name) + "</span>");
    if (!chips.length) {
      return '<span class="muted">' + htmlEsc(emptyLabel) + "</span>";
    }
    return chips.join("");
  }

  function syncCinemaFold() {
    const fold = cinemaFoldState();
    const c = ensureCinema();
    const nC = (c.characters || []).length;
    const nL = (c.locations || []).length;
    if ($("cinema-char-count")) $("cinema-char-count").textContent = String(nC);
    if ($("cinema-loc-count")) $("cinema-loc-count").textContent = String(nL);
    if ($("cinema-char-summary")) {
      $("cinema-char-summary").innerHTML = cinemaFoldSummaryHtml(
        c.characters,
        "karakter yok"
      );
    }
    if ($("cinema-loc-summary")) {
      $("cinema-loc-summary").innerHTML = cinemaFoldSummaryHtml(c.locations, "mekan yok");
    }
    document.querySelectorAll(".cinema-stack[data-fold]").forEach((stack) => {
      const key = stack.dataset.fold;
      const open = fold[key] !== false;
      stack.classList.toggle("is-collapsed", !open);
      const btn = stack.querySelector(".cinema-fold-toggle");
      if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  function cinemaItem(kind, id) {
    const key = kind === "character" ? "characters" : "locations";
    return (state.cinema[key] || []).find((x) => x.id === id);
  }

  async function openCinemaStudio() {
    $("view-gallery")?.classList.add("hidden");
    $("view-settings")?.classList.add("hidden");
    $("view-support")?.classList.add("hidden");
    setDirectorOpen(false);
    $("view-cinema")?.classList.remove("hidden");
    if (!state.loraCatalog || !state.loraCatalog.length) {
      try {
        await loadLoras();
      } catch {
        /* ignore */
      }
    }
    await loadCinema();
  }

  function closeCinemaStudio() {
    $("view-cinema")?.classList.add("hidden");
    void saveCinema(true);
  }

  async function addCinemaAsset(kind) {
    const path = kind === "character" ? "/api/cinema/character" : "/api/cinema/location";
    setCinemaFold(kind === "character" ? "characters" : "locations", true);
    try {
      const r = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "", trigger: "" }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      await loadCinema();
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  function addCinemaShot(mode) {
    const draft = $("cinema-shot-draft");
    const text = (draft?.value || "").trim();
    if (!text) {
      toast("Önce shot metnini yaz, sonra Yeni video veya Continue ile ekle");
      return;
    }
    const c = ensureCinema();
    const want = mode === "continue" ? "continue" : "t2v";
    c.shots.push({ id: cinemaId(), text, mode: want });
    if (draft) draft.value = "";
    renderCinemaShots();
    renderCinema();
    void saveCinema(true);
  }

  function cinemaShotById(id) {
    return (ensureCinema().shots || []).find((s) => s.id === id);
  }

  async function patchCinemaAsset(kind, id, fields) {
    const item = cinemaItem(kind, id);
    if (item) Object.assign(item, fields);
    const path =
      kind === "character" ? `/api/cinema/character/${id}` : `/api/cinema/location/${id}`;
    try {
      const r = await fetch(path, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fields),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      const key = kind === "character" ? "characters" : "locations";
      const idx = (state.cinema[key] || []).findIndex((x) => x.id === id);
      if (idx >= 0) state.cinema[key][idx] = data;
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function uploadCinemaImage(kind, id, file) {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    toast(`Yükleniyor · ${file.name}`);
    try {
      const r = await fetch("/api/refs/upload", { method: "POST", body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      await patchCinemaAsset(kind, id, { image: data.name, url: data.url });
      renderCinema();
      toast("Görsel bağlandı");
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function produceCinema() {
    const btn = $("btn-cinema-produce");
    if (btn) btn.disabled = true;
    try {
      const c = ensureCinema();
      flushCinemaFields();
      const draft = $("cinema-shot-draft");
      const leftover = (draft?.value || "").trim();
      if (leftover) {
        c.shots = c.shots || [];
        c.shots.push({ id: cinemaId(), text: leftover, mode: "t2v" });
        if (draft) draft.value = "";
      }
      await saveCinema(true);
      const shots = (ensureCinema().shots || [])
        .map((s) => ({
          text: (s.text || "").trim(),
          mode: s.mode === "continue" ? "continue" : "t2v",
        }))
        .filter((s) => s.text);
      if (!shots.length) {
        toast("Shot ekle — yaz, sonra Yeni video veya Continue");
        return;
      }
      const audio = cinemaAudio();
      const filmMode = audio.mode !== "silent";
      const purpose =
        c.setup && c.setup.purpose && c.setup.purpose !== "auto"
          ? c.setup.purpose
          : "short_film";
      const r = await fetch("/api/cinema/produce", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shots,
          setup: c.setup || {},
          audio,
          duration: Number($("cinema-duration")?.value) || c.duration || 5,
          aspect: state.aspect || "16:9",
          quality: c.quality || state.quality || "720",
          steps: Number($("cinema-steps")?.value) || c.steps || 20,
          seed: numOr("seed", -1),
          purpose,
          silent_audio: !filmMode,
          link_continue: false,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (data.cinema_batch) {
        audio.last_batch = data.cinema_batch;
        await saveCinema(true);
        renderCinemaAudio();
      }
      toast(
        filmMode
          ? `Direktör: ${data.count || 0} shot kuyruğa alındı — diyalog+SFX, müzik sonra karışır`
          : `Direktör: ${data.count || 0} shot (sessiz görüntü)`
      );
      closeCinemaStudio();
      await refreshJobs();
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function uploadCinemaScore(file) {
    if (!file) return;
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch("/api/music/upload", { method: "POST", body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      const audio = cinemaAudio();
      audio.score_id = (data.music && data.music.id) || "";
      audio.score_name = (data.music && data.music.filename) || file.name;
      renderCinemaAudio();
      await saveCinema(true);
      toast("Film müziği kilitlendi — her shot’ta aynı yatak karışacak");
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function muxCinemaScore() {
    const audio = cinemaAudio();
    if (!audio.score_id) {
      toast("Önce bir film müziği yükle");
      return;
    }
    const btn = $("btn-cinema-mux");
    if (btn) btn.disabled = true;
    try {
      const r = await fetch("/api/cinema/mux", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          batch_id: audio.last_batch || "",
          score_id: audio.score_id,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (data.batch_id) audio.last_batch = data.batch_id;
      renderCinemaAudio();
      toast(`Film hazır: ${data.clips || 0} klip + aynı müzik`);
      if (data.final_url) window.open(data.final_url, "_blank");
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      renderCinemaAudio();
    }
  }

  async function fillContinueSource() {
    const sel = $("continue-source");
    if (!sel) return;
    if (document.activeElement === sel) return;
    if (!state.galleryItems.length) {
      try {
        const data = await fetch("/api/gallery").then((r) => r.json());
        state.galleryItems = data.items || [];
      } catch {
        state.galleryItems = [];
      }
    }
    const prev = state.continueFrom || state.selectedJobId || sel.value || "";
    const tip = chainTipJob();
    const seen = new Set();
    const pool = [];
    const add = (j, tag) => {
      if (!j || !j.id || seen.has(j.id)) return;
      seen.add(j.id);
      pool.push({ job: j, tag });
    };
    state.jobs
      .filter((j) => ["done", "running", "queued"].includes(j.status))
      .sort((a, b) => (Number(b.created_at) || 0) - (Number(a.created_at) || 0))
      .forEach((j) => {
        const tag =
          j.status === "done" ? "bitmiş" : j.status === "running" ? "üretiliyor" : "sırada";
        add(j, tag);
      });
    (state.galleryItems || []).forEach((g) => add(g, "galeri"));
    const sig = pool.map((x) => x.job.id + ":" + x.tag).join("|");
    if (sig === state._continueSourceSig && sel.options.length === pool.length + 1) {
      if (prev && [...sel.options].some((o) => o.value === prev)) sel.value = prev;
      else if (!prev && tip) sel.value = tip.id;
      return;
    }
    state._continueSourceSig = sig;
    sel.innerHTML = `<option value="">— otomatik: kuyruk sonu / son video —</option>`;
    pool.forEach((x, i) => {
      const j = x.job;
      const opt = document.createElement("option");
      opt.value = j.id;
      const label = (j.prompt || "").slice(0, 42).replace(/\s+/g, " ");
      opt.textContent = `${i + 1}. [${x.tag}] ${j.duration || "?"}sn · ${label || j.id.slice(0, 8)}`;
      sel.appendChild(opt);
    });
    if (prev && pool.some((x) => x.job.id === prev)) sel.value = prev;
    else if (tip) sel.value = tip.id;
  }

  function clearPlayer(opts) {
    const quiet = !!(opts && opts.quiet);
    const player = $("player");
    const stage = document.querySelector(".player-stage");
    if (player) {
      player.pause();
      player.removeAttribute("src");
      player.load();
    }
    stage?.classList.add("cleared");
    stage?.classList.remove("has-video");
    $("btn-player-close")?.classList.add("hidden");
    $("btn-download")?.setAttribute("href", "#");
    state.playerCleared = true;
    state.selectedJobId = null;
    setClipPrompt("");
    if (!quiet) toast("Player kapatıldı");
  }

  /** FIFO üretim sırası: önce eklenen / düşük batch_index önde. */
  function productionOrderCmp(a, b) {
    const ca = Number(a.created_at) || 0;
    const cb = Number(b.created_at) || 0;
    if (ca !== cb) return ca - cb;
    const ba = Number(a.batch_index) || 0;
    const bb = Number(b.batch_index) || 0;
    if (ba !== bb) return ba - bb;
    return String(a.id || "").localeCompare(String(b.id || ""));
  }

  function showPlayerVideo(url, jobId, prompt) {
    const player = $("player");
    const stage = document.querySelector(".player-stage");
    if (!player || !url) return;
    state.playerCleared = false;
    state.selectedJobId = jobId || state.selectedJobId;
    if (prompt !== undefined) setClipPrompt(prompt);
    stage?.classList.remove("cleared");
    stage?.classList.add("has-video");
    $("btn-player-close")?.classList.remove("hidden");
    player.src = url + (url.includes("?") ? "&" : "?") + "t=" + Date.now();
    $("btn-download").href = url;
    $("btn-download").removeAttribute("aria-disabled");
  }

  function appendDirectorMsg(role, content) {
    const text = (content == null ? "" : String(content)).trimEnd();
    if (!text && role === "assistant") return;
    const log = $("director-log");
    if (!log) return;
    const msg = { role, content: text };
    const session = findSession(state.directorSessionId);
    if (session) {
      session.messages = session.messages || [];
      session.messages.push(msg);
    }
    const div = document.createElement("div");
    div.className = `dir-msg ${role}`;
    const who = role === "user" ? tt("dir.you") : tt("dir.who");
    div.innerHTML = `<span class="who">${who}</span>`;
    div.appendChild(document.createTextNode(text || tt("dir.empty")));
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function dirThinkPhases() {
    return [tt("dir.think0"), tt("dir.think1"), tt("dir.think2"), tt("dir.think3")];
  }
  let _dirThinkTimer = null;
  let _dirThinkStarted = 0;
  let _dirThinkFull = "";

  function clearDirectorThinking() {
    if (_dirThinkTimer) {
      clearInterval(_dirThinkTimer);
      _dirThinkTimer = null;
    }
    _dirThinkFull = "";
    document.getElementById("director-thinking")?.remove();
  }

  function beginDirectorThinking(label) {
    clearDirectorThinking();
    const log = $("director-log");
    if (!log) return null;
    const div = document.createElement("div");
    div.id = "director-thinking";
    div.className = "dir-msg assistant thinking";
    div.innerHTML =
      `<span class="who">${tt("dir.who")}</span>` +
      `<div class="think-meta"><span class="think-dots">${tt("dir.thinkDots")}</span>` +
      `<span class="think-elapsed">0s</span></div>` +
      `<div class="think-body"></div>`;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    _dirThinkStarted = Date.now();
    _dirThinkFull = "";
    const body = div.querySelector(".think-body");
    const elapsed = div.querySelector(".think-elapsed");
    let phase = 0;
    if (label) body.textContent = label;
    else body.textContent = dirThinkPhases()[0] + "…";
    _dirThinkTimer = setInterval(() => {
      const el = document.getElementById("director-thinking");
      if (!el) return;
      const sec = Math.floor((Date.now() - _dirThinkStarted) / 1000);
      const e = el.querySelector(".think-elapsed");
      if (e) e.textContent = `${sec}s`;
      // Rotate phases only when no live model thoughts yet
      if (!_dirThinkFull) {
        const phases = dirThinkPhases();
        phase = Math.floor(sec / 4) % phases.length;
        const b = el.querySelector(".think-body");
        if (b) b.textContent = phases[phase] + "…";
      }
      log.scrollTop = log.scrollHeight;
    }, 1000);
    return div;
  }

  function updateDirectorThinking(ev) {
    const el = document.getElementById("director-thinking");
    if (!el) return;
    const body = el.querySelector(".think-body");
    if (!body) return;
    const type = (ev && ev.type) || "";
    if (type === "thinking") {
      _dirThinkFull = (ev.full || _dirThinkFull + (ev.text || "")).slice(-1600);
      body.textContent = _dirThinkFull;
      el.classList.remove("answering");
    } else if (type === "answer") {
      el.classList.add("answering");
      _dirThinkFull = (_dirThinkFull + (ev.text || "")).slice(-2000);
      body.textContent = _dirThinkFull;
      const dots = el.querySelector(".think-dots");
      if (dots) dots.textContent = "yazıyor";
    } else if (type === "status" && ev.text) {
      if (!_dirThinkFull) body.textContent = ev.text;
    }
    $("director-log").scrollTop = $("director-log").scrollHeight;
  }

  function renderDirectorMessages(messages) {
    const log = $("director-log");
    if (!log) return;
    const panelWasOpen = !!$("director-shot-panel")?.open;
    log.innerHTML = "";
    for (const m of messages || []) {
      if (m.role === "system") continue;
      const body = m.content;
      if (body == null || String(body).trim() === "") continue;
      appendDirectorMsg(m.role === "user" ? "user" : "assistant", body);
    }
    if (state.directorBrief) {
      renderDirectorShotPanel(state.directorBrief, { open: panelWasOpen });
    }
    log.scrollTop = log.scrollHeight;
  }

  function _shotPromptText(shot) {
    if (!shot || typeof shot !== "object") return "";
    return (
      (shot.h3Prompt || shot.prompt || shot.action || shot.description || "")
    ).toString().trim();
  }

  function renderDirectorShotPanel(brief, opts) {
    const log = $("director-log");
    if (!log) return;
    const shots = (brief && Array.isArray(brief.shots) ? brief.shots : []).filter(Boolean);
    const existing = $("director-shot-panel");
    if (!shots.length) {
      existing?.remove();
      return;
    }
    const keepOpen = opts && typeof opts.open === "boolean"
      ? opts.open
      : !!(existing && existing.open);
    const panel = document.createElement("details");
    panel.id = "director-shot-panel";
    panel.className = "dir-shot-panel";
    panel.open = keepOpen;

    const n = shots.length;
    const need = brief.expectedShotCount || n;
    const clip = brief.clipDurationSec || state.duration || 5;
    const total = brief.totalDurationSec || n * clip;
    const title = (brief.title || brief.logline || "").toString().trim();

    const summary = document.createElement("summary");
    summary.innerHTML =
      `<span class="dir-shot-sum-main">Shot’ları gör (${n}${need && need !== n ? ` / ${need}` : ""})</span>` +
      `<span class="dir-shot-sum-meta">${clip}sn · ~${total}sn · tıkla aç/kapa</span>`;
    panel.appendChild(summary);

    const body = document.createElement("div");
    body.className = "dir-shot-body";
    if (title) {
      const h = document.createElement("div");
      h.className = "dir-shot-title";
      h.textContent = title;
      body.appendChild(h);
    }
    const hint = document.createElement("p");
    hint.className = "dir-shot-hint muted";
    hint.textContent =
      "Beğenmezsen Plan sekmesinde düzenle veya aşağıya yaz. Beğendiysen Üretime al.";
    body.appendChild(hint);

    const list = document.createElement("div");
    list.className = "dir-shot-list";
    shots.forEach((shot, i) => {
      const item = document.createElement("article");
      item.className = "dir-shot-item";
      const dur = shot.durationSec || clip;
      const link = (shot.linkToPrev || (i === 0 ? "standalone" : "continue")).toString();
      const head = document.createElement("div");
      head.className = "dir-shot-head";
      head.textContent = `#${i + 1} · ${dur}sn · ${link}`;
      const pre = document.createElement("pre");
      pre.className = "dir-shot-prompt";
      pre.textContent = _shotPromptText(shot) || "(prompt yok)";
      item.appendChild(head);
      if (shot.camera) {
        const cam = document.createElement("div");
        cam.className = "dir-shot-cam muted";
        cam.textContent = shot.camera;
        item.appendChild(cam);
      }
      item.appendChild(pre);
      list.appendChild(item);
    });
    body.appendChild(list);

    const actions = document.createElement("div");
    actions.className = "dir-shot-actions";
    const btnQ = document.createElement("button");
    btnQ.type = "button";
    btnQ.className = "cta";
    btnQ.textContent = `Üretime al (${n} shot)`;
    btnQ.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      applyBrief(true);
    };
    const btnClose = document.createElement("button");
    btnClose.type = "button";
    btnClose.className = "btn-ghost";
    btnClose.textContent = "Kapat · yazmaya devam";
    btnClose.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      panel.open = false;
      $("director-msg")?.focus();
    };
    const btnPlan = document.createElement("button");
    btnPlan.type = "button";
    btnPlan.className = "btn-secondary";
    btnPlan.textContent = "Plan’da düzenle";
    btnPlan.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      setDirectorTab("plan");
    };
    actions.appendChild(btnQ);
    actions.appendChild(btnPlan);
    actions.appendChild(btnClose);
    body.appendChild(actions);

    panel.appendChild(body);
    existing?.remove();
    log.appendChild(panel);
    log.scrollTop = log.scrollHeight;
  }

  function syncDirectorBriefFromResponse(data) {
    const brief = data && data.brief;
    const shots = brief && Array.isArray(brief.shots) ? brief.shots : [];
    if (shots.length) {
      state.directorBrief = brief;
      renderDirectorShotPanel(brief, { open: !!$("director-shot-panel")?.open });
      if (state.directorTab === "plan") renderDirectorPlanBoard();
      return;
    }
    if (data && data.ready === false && !shots.length) {
      // Don't wipe an existing brief on a casual reply that omitted brief
      if (!state.directorBrief) return;
    }
    if (data && data.ready && !shots.length && state.directorBrief) {
      renderDirectorShotPanel(state.directorBrief);
    }
  }

  function hydratePlanFromCinema() {
    if ((state.directorBrief?.shots || []).length) return;
    const c = typeof ensureCinema === "function" ? ensureCinema() : state.cinema;
    const shots = (c && c.shots) || [];
    if (!shots.length) return;
    const clip = Number(c.duration) || state.duration || 5;
    state.directorBrief = {
      logline: c.title || "",
      clipDurationSec: clip,
      expectedShotCount: shots.length,
      shots: shots.map((s, i) => ({
        durationSec: clip,
        camera: "",
        action: "",
        dialogue: [],
        h3Prompt: s.text || "",
        linkToPrev: s.mode === "continue" ? "continue" : "standalone",
      })),
    };
  }

  function renderDirectorPlanBoard() {
    const host = $("director-plan-shots");
    const meta = $("director-plan-meta");
    if (!host) return;
    hydratePlanFromCinema();
    const brief = state.directorBrief || {};
    const shots = Array.isArray(brief.shots) ? brief.shots : [];
    const clip = brief.clipDurationSec || state.duration || 5;
    const n = shots.length;
    if (meta) {
      const title = (brief.logline || brief.title || "").toString().trim();
      meta.textContent = n
        ? `${n} shot · ${clip}${tt("sec")}` + (title ? ` · ${title}` : "")
        : tt("plan.empty");
    }
    if (!n) {
      host.innerHTML = '<p class="muted">' + tt("plan.boardEmpty") + "</p>";
      return;
    }
    host.innerHTML = shots
      .map((shot, i) => {
        const link = (shot.linkToPrev || (i === 0 ? "standalone" : "continue")).toString();
        const dlg = Array.isArray(shot.dialogue)
          ? shot.dialogue.join("\n")
          : shot.dialogue || "";
        const prompt = _shotPromptText(shot);
        return (
          '<article class="dir-plan-shot" data-idx="' +
          i +
          '">' +
          '<div class="dir-plan-shot-head">Shot ' +
          (i + 1) +
          "</div>" +
          "<label>" +
          tt("plan.link") +
          ' <select data-field="link">' +
          '<option value="standalone"' +
          (link === "standalone" ? " selected" : "") +
          ">" +
          tt("plan.new") +
          "</option>" +
          '<option value="continue"' +
          (link === "continue" ? " selected" : "") +
          ">" +
          tt("plan.cont") +
          "</option>" +
          "</select></label>" +
          "<label>" +
          tt("plan.camera") +
          ' <input type="text" data-field="camera" value="' +
          htmlEsc(shot.camera || "") +
          '" /></label>' +
          "<label>" +
          tt("plan.action") +
          ' <input type="text" data-field="action" value="' +
          htmlEsc(shot.action || "") +
          '" /></label>' +
          "<label>" +
          tt("plan.dialogue") +
          ' <textarea rows="2" data-field="dialogue">' +
          htmlEsc(dlg) +
          "</textarea></label>" +
          "<label>" +
          tt("plan.prompt") +
          ' <textarea rows="8" data-field="h3Prompt">' +
          htmlEsc(prompt) +
          "</textarea></label>" +
          "</article>"
        );
      })
      .join("");
  }

  function collectPlanShotsFromDom() {
    const host = $("director-plan-shots");
    if (!host) return [];
    const clip = (state.directorBrief && state.directorBrief.clipDurationSec) || state.duration || 5;
    return [...host.querySelectorAll(".dir-plan-shot")].map((el, i) => {
      const dlg = (el.querySelector("[data-field=dialogue]")?.value || "")
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      return {
        durationSec: clip,
        camera: el.querySelector("[data-field=camera]")?.value || "",
        action: el.querySelector("[data-field=action]")?.value || "",
        dialogue: dlg,
        h3Prompt: el.querySelector("[data-field=h3Prompt]")?.value || "",
        linkToPrev:
          el.querySelector("[data-field=link]")?.value || (i === 0 ? "standalone" : "continue"),
      };
    });
  }

  async function saveDirectorPlan(applyCinema) {
    if (!state.directorSessionId) {
      toast("Önce yönetmenle konuş");
      return;
    }
    const shots = collectPlanShotsFromDom();
    if (!shots.length) {
      toast("Kaydedilecek shot yok");
      return;
    }
    try {
      const r = await fetch("/api/director/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.directorSessionId,
          brief: state.directorBrief || {},
          shots,
          apply_cinema: !!applyCinema,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (data.brief) state.directorBrief = data.brief;
      state.directorReady = !!data.ready;
      const session = findSession(state.directorSessionId);
      if (session && data.brief) {
        session.brief = data.brief;
        session.ready = !!data.ready;
      }
      setDirectorReadyUi(state.directorReady, data.shot_count || shots.length);
      renderDirectorPlanBoard();
      if (data.cinema) {
        state.cinema = { ...ensureCinema(), ...data.cinema };
        if (typeof renderCinema === "function") renderCinema();
      }
      toast(applyCinema ? "Plan kaydedildi · stüdyoya aktarıldı" : "Plan kaydedildi");
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  function setDirectorUi(online, detail) {
    state.directorOnline = !!online;
    const st = $("director-status");
    st.textContent = detail;
    st.classList.toggle("on", !!online);
    st.classList.toggle("off", !online);
    // Input always typeable — only Send locks while busy (offline still allows drafting)
    $("director-msg").disabled = false;
    $("director-msg").readOnly = !!state.directorBusy;
    $("btn-director-send").disabled = !!state.directorBusy;
    document.querySelectorAll("#director-chips .chip, #scene-purpose-chips .chip, #scene-style-chips .chip").forEach((b) => {
      b.disabled = !!state.directorBusy;
    });
  }

  const LLM_KEY_FIELDS = [
    { id: "llm-openai-key", set: "openai_api_key_set", mask: "openai_api_key_masked", body: "openai_api_key" },
    { id: "llm-gemini-key", set: "gemini_api_key_set", mask: "gemini_api_key_masked", body: "gemini_api_key" },
    { id: "llm-grok-key", set: "grok_api_key_set", mask: "grok_api_key_masked", body: "grok_api_key" },
    { id: "llm-claude-key", set: "claude_api_key_set", mask: "claude_api_key_masked", body: "claude_api_key" },
  ];

  function _fillModelSelect(sel, models, preferred) {
    if (!sel) return;
    const prev = sel.value;
    sel.innerHTML = "";
    if (!models.length) {
      sel.innerHTML = `<option value="">model yok</option>`;
      return;
    }
    for (const name of models) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      if (name === (prev || preferred)) opt.selected = true;
      sel.appendChild(opt);
    }
  }

  function syncLlmSettingsUi(pub, probe) {
    const prov = (pub && pub.provider) || (probe && probe.provider) || "ollama";
    const selProd = $("llm-provider");
    const selSet = $("llm-provider-settings");
    if (selProd && !selProd.dataset.userTouched) selProd.value = prov;
    if (selSet && !selSet.dataset.userTouched) selSet.value = prov;
    const urlWrap = $("llm-ollama-url-wrap");
    if (urlWrap) urlWrap.classList.toggle("hidden", prov !== "ollama");
    const prodModelWrap = $("llm-prod-model-wrap");
    if (prodModelWrap) prodModelWrap.classList.remove("hidden");
    const urlIn = $("llm-ollama-url");
    if (urlIn && pub && !urlIn.dataset.dirty) {
      urlIn.value = pub.ollama_base_url || "";
      urlIn.placeholder = "http://127.0.0.1:11434";
    }
    for (const f of LLM_KEY_FIELDS) {
      const el = $(f.id);
      if (!el || !pub) continue;
      if (pub[f.set] && !el.dataset.dirty) {
        el.placeholder = pub[f.mask] || "•••• kaydedildi";
      }
    }
    const ready = {
      openai: pub && pub.openai_api_key_set,
      gemini: pub && pub.gemini_api_key_set,
      grok: pub && pub.grok_api_key_set,
      claude: pub && pub.claude_api_key_set,
    };
    const tips = {
      ollama: "Ollama yerel — `ollama serve` + model. Key gerekmez.",
      openai: ready.openai ? "OpenAI key kayıtlı." : "platform.openai.com → API key yapıştır → Kaydet.",
      gemini: ready.gemini ? "Gemini key kayıtlı." : "aistudio.google.com/apikey → Kaydet.",
      grok: ready.grok ? "Grok key kayıtlı." : "console.x.ai → Kaydet.",
      claude: ready.claude ? "Claude key kayıtlı." : "console.anthropic.com → Kaydet.",
    };
    const hint = $("llm-settings-hint");
    if (hint) hint.textContent = tips[prov] || "Key doldur → Kaydet.";
    const prodHint = $("llm-prod-hint");
    if (prodHint) {
      prodHint.innerHTML =
        `Şu an: <strong>${prov}</strong>. API anahtarları sağ üst <strong>Ayarlar</strong>’da. Üretim (Comfy/H3) bundan etkilenmez.`;
    }
  }

  function _modelBodyForProvider(provider, model) {
    if (!model) return {};
    if (provider === "openai") return { openai_model: model };
    if (provider === "gemini") return { gemini_model: model };
    if (provider === "grok") return { grok_model: model };
    if (provider === "claude") return { claude_model: model };
    return { ollama_model: model };
  }

  async function _postLlmSettings(body) {
    const r = await fetch("/api/llm/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(errDetail(data));
    return data;
  }

  /** Production drawer: switch active provider/model — never touches keys. */
  async function saveLlmProviderOnly() {
    const provider = ($("llm-provider") && $("llm-provider").value) || "ollama";
    const model = $("director-model") ? $("director-model").value : "";
    try {
      const data = await _postLlmSettings({
        provider,
        ..._modelBodyForProvider(provider, model),
      });
      if ($("llm-provider")) delete $("llm-provider").dataset.userTouched;
      if ($("llm-provider-settings")) {
        $("llm-provider-settings").value = provider;
        delete $("llm-provider-settings").dataset.userTouched;
      }
      toast(
        data.online
          ? `Yönetmen: ${data.provider} · ${data.default_model || "ok"}`
          : `Seçildi ama online değil (${data.detail || "?"}) — sağ üst Ayarlar’dan key kontrol et`
      );
      await refreshDirectorStatus();
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  /** Top-right Settings: save API keys + provider. */
  async function saveLlmSettings() {
    const provider =
      ($("llm-provider-settings") && $("llm-provider-settings").value) ||
      ($("llm-provider") && $("llm-provider").value) ||
      "ollama";
    const body = { provider };
    const model =
      ($("director-model-settings") && $("director-model-settings").value) ||
      ($("director-model") && $("director-model").value);
    const urlIn = $("llm-ollama-url");
    if (urlIn) body.ollama_base_url = urlIn.value.trim();
    for (const f of LLM_KEY_FIELDS) {
      const el = $(f.id);
      if (el && el.value.trim()) body[f.body] = el.value.trim();
    }
    Object.assign(body, _modelBodyForProvider(provider, model));
    try {
      const data = await _postLlmSettings(body);
      for (const f of LLM_KEY_FIELDS) {
        const el = $(f.id);
        if (el) {
          el.value = "";
          delete el.dataset.dirty;
        }
      }
      if (urlIn) delete urlIn.dataset.dirty;
      if ($("llm-provider-settings")) delete $("llm-provider-settings").dataset.userTouched;
      if ($("llm-provider")) {
        $("llm-provider").value = provider;
        delete $("llm-provider").dataset.userTouched;
      }
      toast(
        data.online
          ? `LLM: ${data.provider} · ${data.default_model || "ok"}`
          : `Kaydedildi ama online değil (${data.detail || "?"})`
      );
      await refreshDirectorStatus();
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function refreshDirectorStatus() {
    try {
      const s = await fetch("/api/director/status?lang=" + encodeURIComponent(uiLang())).then((r) => r.json());
      const provider = s.provider || (s.llm && s.llm.provider) || "ollama";
      syncLlmSettingsUi(s.llm || {}, s);
      const models = s.models || [];
      _fillModelSelect($("director-model"), models, s.default_model);
      _fillModelSelect($("director-model-settings"), models, s.default_model);
      if (s.online) {
        const label = state.directorReady
          ? tt("dir.briefReady")
          : state.directorBusy
            ? tt("dir.thinkingStatus")
            : `${provider} · ${($("director-model") && $("director-model").value) || s.default_model || "model"}`;
        setDirectorUi(true, label);
        if (!$("director-log").children.length && s.opening && !state.directorSessions.length) {
          appendDirectorMsg("assistant", s.opening);
        }
      } else {
        const why = s.detail || "";
        let msg = tf("dir.offline", { provider });
        let help = "Yönetmen LLM hazır değil — sağ üst Ayarlar’dan API key ekle.";
        if (why === "api_key_missing") {
          const links = {
            openai: "OpenAI key yok — sağ üst Ayarlar → platform.openai.com",
            gemini: "Gemini key yok — sağ üst Ayarlar → aistudio.google.com/apikey",
            grok: "Grok key yok — sağ üst Ayarlar → console.x.ai",
            claude: "Claude key yok — sağ üst Ayarlar → console.anthropic.com",
          };
          help = links[provider] || help;
        } else if (provider === "ollama" && why === "connect_refused") {
          help = "Ollama 11434 kapalı — `ollama serve` veya sağ üst Ayarlar’dan bulut LLM.";
        } else if (provider === "ollama" && why === "timeout") {
          help = "Ollama timeout — sağ üst Ayarlar’dan OpenAI/Gemini/Claude key ekle.";
        } else if (why && why !== "offline") {
          help = `${provider}: ${why}`;
        }
        setDirectorUi(false, msg);
        if (!$("director-log").children.length && !state.directorSessions.length) {
          appendDirectorMsg("assistant", help);
        }
      }
    } catch {
      setDirectorUi(false, "Yönetmen API yok");
    }
  }

  function errDetail(data) {
    const d = data && data.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
    return data ? JSON.stringify(data) : "hata";
  }

  function updateProjectAudioHint() {
    const el = $("project-audio-hint");
    if (!el) return;
    const silent = state.projectSilent || state.projectPurpose === "music_video";
    if (state.projectPurpose === "music_video") {
      el.textContent = tt("project.mvHint");
    } else if (state.projectPurpose) {
      const label = purposeLabel(state.projectPurpose) || state.projectPurpose;
      const style = state.projectStyle
        ? ` · ${styleLabel(state.projectStyle) || state.projectStyle}`
        : "";
      el.textContent = tf("project.typeHint", { label, style });
    } else if (state.projectStyle) {
      el.textContent = tf("project.styleHint", {
        style: styleLabel(state.projectStyle) || state.projectStyle,
      });
    } else {
      el.textContent = tt("project.pickHint");
    }
    const ta = $("prompt");
    if (ta) {
      ta.placeholder = silent ? tt("prompt.phSilent") : tt("prompt.ph");
    }
    refreshModeHints();
  }

  function syncProjectChips() {
    document
      .querySelectorAll("#director-chips .chip, #scene-purpose-chips .chip, #scene-style-chips .chip")
      .forEach((btn) => {
        const g = btn.dataset.group;
        let on = false;
        if (g === "purpose") on = btn.dataset.purpose === state.projectPurpose;
        else if (g === "style") on = btn.dataset.style === state.projectStyle;
        else if (g === "clip") on = Number(btn.dataset.clip) === Number(state.duration);
        btn.classList.toggle("on", on);
        btn.setAttribute("aria-pressed", on ? "true" : "false");
      });
    const musicBar = $("director-music");
    if (musicBar) {
      musicBar.classList.toggle("music-mode", state.projectPurpose === "music_video");
    }
    const badge = $("director-project");
    if (badge) {
      const bits = [];
      if (state.projectPurpose) bits.push(purposeLabel(state.projectPurpose) || state.projectPurpose);
      if (state.projectStyle) bits.push(styleLabel(state.projectStyle) || state.projectStyle);
      bits.push(`${state.duration} ${tt("sec")}`);
      if (state.projectSilent || state.projectPurpose === "music_video") bits.push(tt("project.silentVisual"));
      badge.textContent = bits.length ? tf("project.badge", { bits: bits.join(" · ") }) : tt("project.pick");
    }
    updateProjectAudioHint();
    const bg = $("bible-genre");
    if (bg && state.projectPurpose) bg.value = state.projectPurpose;
    const bs = $("bible-style");
    if (bs && state.projectStyle) bs.value = state.projectStyle;
  }

  function selectProjectChip(btn, opts) {
    const g = btn.dataset.group;
    const fromScene = !!(opts && opts.fromScene);
    if (!fromScene) setDirectorOpen(true);
    if (g === "purpose") {
      const p = btn.dataset.purpose;
      state.projectPurpose = state.projectPurpose === p ? null : p;
      // Music video = silent visual only; all other purposes keep MiniMax audio
      state.projectSilent = state.projectPurpose === "music_video";
      syncProjectChips();
      const label = purposeLabel(state.projectPurpose) || "—";
      if (!state.projectPurpose) {
        if (!fromScene) appendDirectorMsg("assistant", tt("dir.purposeCleared"));
        else toast(tt("toast.purposeCleared"));
        return;
      }
      let note = tf("dir.purposeSet", { label });
      if (state.projectPurpose === "music_video") {
        note += tt("dir.purposeMv");
        if (fromScene) toast(tt("toast.purposeMv"));
      } else {
        const extra =
          state.projectPurpose === "documentary"
            ? tt("dir.extra.documentary")
            : state.projectPurpose === "intro"
              ? tt("dir.extra.intro")
              : state.projectPurpose === "outro"
                ? tt("dir.extra.outro")
                : "";
        note += tt("dir.purposeAv") + extra;
        if (fromScene) toast(tf("toast.purposeAv", { label }));
      }
      if (!fromScene) appendDirectorMsg("assistant", note);
      return;
    }
    if (g === "style") {
      const s = btn.dataset.style;
      state.projectStyle = state.projectStyle === s ? null : s;
      syncProjectChips();
      if (!state.projectStyle) {
        if (!fromScene) appendDirectorMsg("assistant", tt("dir.styleCleared"));
        else toast(tt("toast.styleCleared"));
        return;
      }
      const sl = styleLabel(state.projectStyle) || state.projectStyle;
      if (fromScene) toast(tf("toast.style", { style: sl }));
      else appendDirectorMsg("assistant", tf("dir.styleSet", { style: sl }));
      return;
    }
    if (g === "clip") {
      const d = Number(btn.dataset.clip) || 5;
      setDuration(d);
      syncProjectChips();
      appendDirectorMsg("assistant", tf("dir.clipSet", { d, sec: tt("sec") }));
    }
  }

  function _directorReplyLooksBroken(text) {
    const t = (text || "").trim();
    if (!t) return true;
    return /yanıt boş geldi|yanıt alınamadı|boş geldi/i.test(t);
  }

  async function directorChatRequest(message, onProgress) {
    const payload = {
      session_id: state.directorSessionId,
      message,
      model: $("director-model").value || null,
      purpose: state.projectPurpose,
      visual_style: state.projectStyle,
      silent_audio: state.projectSilent || state.projectPurpose === "music_video",
      clip_duration: state.duration || 5,
      plan_mode: state.directorTab === "plan",
      ui_lang: uiLang(),
    };
    // Prefer SSE stream so thinking shows in the same assistant row
    try {
      const r = await fetch("/api/director/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(payload),
      });
      if (!r.ok || !r.body) {
        // Fall through to classic JSON
        throw new Error("stream_unavailable");
      }
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      let result = null;
      let err = null;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const chunks = buf.split("\n\n");
        buf = chunks.pop() || "";
        for (const chunk of chunks) {
          const line = chunk
            .split("\n")
            .map((l) => l.trim())
            .find((l) => l.startsWith("data:"));
          if (!line) continue;
          let ev;
          try {
            ev = JSON.parse(line.slice(5).trim());
          } catch {
            continue;
          }
          if (!ev || !ev.type) continue;
          if (ev.type === "result") {
            result = ev.data || ev;
          } else if (ev.type === "error") {
            err = new Error(ev.detail || "Yönetmen stream hatası");
            err.status = ev.status;
          } else if (typeof onProgress === "function") {
            onProgress(ev);
          }
        }
      }
      if (err) throw err;
      if (result) return result;
      throw new Error("stream_empty");
    } catch (e) {
      if (
        e &&
        !/stream_unavailable|stream_empty|Failed to fetch|NetworkError/i.test(
          String(e.message || e)
        ) &&
        e.status
      ) {
        throw e;
      }
      // Classic JSON fallback (older server / proxy without SSE)
      const r = await fetch("/api/director/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      return data;
    }
  }

  async function directorSend(text, opts) {
    const message = (text || "").trim();
    if (!message || state.directorBusy) return;
    const isRetry = !!(opts && opts.retry);
    setDirectorOpen(true);
    // Show chat while waiting for reply
    setDirectorModal(true);
    if (!state.directorOnline) {
      appendDirectorMsg(
        "assistant",
        "Yönetmen LLM kapalı — sağ üst Ayarlar’dan API key kaydet (veya Ollama’yı aç), sonra Gönder."
      );
      await refreshDirectorStatus();
      if (!state.directorOnline) return;
    }
    state.directorBusy = true;
    setDirectorUi(true, isRetry ? tt("dir.retryStatus") : tt("dir.thinkingStatus"));
    if (!isRetry) {
      appendDirectorMsg("user", message);
      $("director-msg").value = "";
    }
    beginDirectorThinking(isRetry ? "Yeniden deniyor…" : null);
    let handedOffRetry = false;
    try {
      const data = await directorChatRequest(message, updateDirectorThinking);
      clearDirectorThinking();
      state.directorSessionId = data.session_id;
      syncDirectorSessionFromResponse(data);
      state.directorReady = !!data.ready;
      let reply = (data.reply || "").trim();
      // Prefer full server history so mid/final replies always show
      if (Array.isArray(data.messages) && data.messages.length) {
        renderDirectorMessages(data.messages);
        const lastAsst = [...data.messages]
          .reverse()
          .find((m) => m.role === "assistant" && (m.content || "").trim());
        reply = ((lastAsst && lastAsst.content) || reply || "").trim();
      } else {
        appendDirectorMsg(
          "assistant",
          reply || "Yanıt alınamadı — tekrar dene veya modeli değiştir."
        );
      }
      // One automatic retry if still empty / legacy empty-error string
      if (!isRetry && _directorReplyLooksBroken(reply)) {
        appendDirectorMsg(
          "assistant",
          "Boş yanıt yakalandı — bir kez daha deniyorum…"
        );
        handedOffRetry = true;
        state.directorBusy = false;
        return directorSend(
          "Önceki çıktın boştu. Türkçe 2–4 cümle yönetmen cevabı ver; " +
            "hikâyeyi ilerlet veya net bir soru sor.",
          { retry: true }
        );
      }
      syncDirectorBriefFromResponse(data);
      if (state.directorTab === "plan") renderDirectorPlanBoard();
      const nShots =
        data.shot_count ||
        (state.directorBrief && state.directorBrief.shots && state.directorBrief.shots.length) ||
        0;
      setDirectorReadyUi(state.directorReady || !!nShots, nShots);
      setDirectorUi(
        true,
        state.directorReady || nShots
          ? `Hazır · ${nShots || "?"} shot — Shot’ları gör / Üretime al`
          : `Ollama · ${data.model || ""}`
      );
      setDirectorModal(true);
    } catch (e) {
      clearDirectorThinking();
      const msg = String(e.message || e);
      const prov = (state.llmProvider || $("llm-provider")?.value || "").toLowerCase();
      let hint = "";
      if (prov === "gemini" || /gemini/i.test(msg)) {
        hint =
          " — Ayarlar’da modeli gemini-3.6-flash veya gemini-3.5-flash seç (2.5 yeni anahtarlarda kapalı).";
      } else if (prov === "ollama" || /ollama/i.test(msg)) {
        hint = " — Ollama açık mı? Model listesinden qwen3:8b deneyebilirsin.";
      } else {
        hint = " — Sağ üst Ayarlar’dan provider / model / API key kontrol et.";
      }
      appendDirectorMsg("assistant", msg + hint);
      await refreshDirectorStatus();
    } finally {
      clearDirectorThinking();
      if (!handedOffRetry) {
        state.directorBusy = false;
        await refreshDirectorStatus();
        if (state.directorReady || (state.directorBrief && state.directorBrief.shots?.length)) {
          const n = state.directorBrief?.shots?.length || 0;
          setDirectorReadyUi(true, n);
          setDirectorUi(true, n ? `Hazır · ${n} shot — Shot’ları gör` : "Hazır — Üretime al");
          renderDirectorShotPanel(state.directorBrief);
        }
        $("director-msg").focus();
      }
    }
  }

  function setDirectorReadyUi(ready, shotCount) {
    state.directorReady = !!ready;
    const n =
      shotCount ||
      (state.directorBrief && state.directorBrief.shots && state.directorBrief.shots.length) ||
      0;
    const q = $("btn-queue-brief");
    if (q) {
      q.classList.toggle("hidden", !state.directorReady);
      if (state.directorReady) {
        q.textContent = n ? `Üretime al (${n} shot)` : "Üretime al";
      }
    }
    if (state.directorBrief && (state.directorBrief.shots || []).length) {
      renderDirectorShotPanel(state.directorBrief);
    } else {
      $("director-shot-panel")?.remove();
    }
    updateMusicMuxUi();
  }

  function updateMusicMetaUi() {
    const el = $("music-meta");
    const analyze = $("btn-music-analyze");
    if (!el) return;
    if (!state.musicMeta) {
      el.textContent = "yok";
      if (analyze) analyze.disabled = true;
      updateMusicMuxUi();
      return;
    }
    const m = state.musicMeta;
    const shots = m.suggestedShots5 || Math.ceil((m.durationSec || 0) / 5);
    const prog =
      m.linked_jobs != null
        ? ` · klipler ${m.linked_done || 0}/${m.linked_jobs}${m.linked_pending ? ` (+${m.linked_pending})` : ""}`
        : "";
    el.textContent = `${m.filename || "track"} · ${(m.durationSec || 0).toFixed(1)}sn · ~${shots}×5${prog}`;
    el.title = el.textContent;
    if (analyze) analyze.disabled = !!state.directorBusy;
    updateMusicMuxUi();
  }

  function updateMusicMuxUi() {
    const mux = $("btn-music-mux");
    const link = $("music-final-link");
    if (!mux) return;
    const has = !!state.musicId;
    mux.classList.toggle("hidden", !has);
    mux.disabled = !has || !!state.directorBusy;
    if (link) {
      const ready = !!(state.musicMeta && state.musicMeta.final_ready && state.musicMeta.final_url);
      link.classList.toggle("hidden", !ready);
      if (ready) link.href = state.musicMeta.final_url;
    }
  }

  async function refreshMusicStatus() {
    if (!state.musicId) return;
    try {
      const s = await fetch(`/api/music/status?music_id=${encodeURIComponent(state.musicId)}`).then(
        (r) => r.json()
      );
      if (s.music) {
        state.musicMeta = { ...(state.musicMeta || {}), ...s.music };
        updateMusicMetaUi();
      }
    } catch {
      /* ignore */
    }
  }

  async function uploadMusicFile(file) {
    if (!file) return;
    setDirectorOpen(true);
    toast("Şarkı yükleniyor…");
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await fetch("/api/music/upload", { method: "POST", body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      state.musicId = data.music.id;
      state.musicMeta = data.music;
      state.projectPurpose = "music_video";
      state.projectSilent = true;
      syncProjectChips();
      updateMusicMetaUi();
      appendDirectorMsg(
        "assistant",
        `Şarkı alındı → proje **müzik klibi** (sessiz görüntü). ${data.music.filename} · ${data.music.durationSec}sn → ~${data.music.suggestedShots5}×5sn. Söz/konsept yazıp **Şarkıdan brief**’e bas; finalde şarkı mux.`
      );
      toast("Şarkı hazır — Şarkıdan brief");
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function analyzeMusic() {
    if (!state.musicId || state.directorBusy) return;
    setDirectorOpen(true);
    if (!state.directorOnline) {
      await refreshDirectorStatus();
      if (!state.directorOnline) {
        toast("Yönetmen LLM kapalı — sağ üst Ayarlar’dan key ekle");
        return;
      }
    }
    state.directorBusy = true;
    setDirectorUi(true, "Şarkı analiz ediliyor…");
    $("btn-music-analyze").disabled = true;
    try {
      toast("Şarkıdan SCENE brief üretiliyor (uzun sürebilir)…");
      const r = await fetch("/api/music/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          music_id: state.musicId,
          session_id: state.directorSessionId,
          lyrics: ($("music-lyrics") && $("music-lyrics").value) || "",
          concept: ($("music-concept") && $("music-concept").value) || "",
          clip_duration: state.duration || 5,
          visual_style: state.projectStyle || "realistic",
          model: $("director-model").value || null,
          expand: true,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      state.directorSessionId = data.session_id;
      state.directorReady = !!data.ready;
      state.projectPurpose = "music_video";
      state.projectSilent = true;
      syncProjectChips();
      appendDirectorMsg("assistant", data.reply || "Brief hazır");
      syncDirectorBriefFromResponse(data);
      setDirectorTab("plan");
      setDirectorReadyUi(true, data.shot_count);
      setDirectorUi(true, `Brief hazır · ${data.shot_count || "?"} shot — Shot’ları gör`);
      toast(`${data.shot_count || "?"} shot — kuyruğa al, bitince Şarkılı final`);
    } catch (e) {
      appendDirectorMsg("assistant", String(e.message || e));
      toast(String(e.message || e));
    } finally {
      state.directorBusy = false;
      updateMusicMetaUi();
      await refreshDirectorStatus();
      if (state.directorReady) {
        setDirectorReadyUi(true);
        setDirectorUi(true, "Brief hazır — kuyruğa al");
      }
    }
  }

  async function muxMusicFinal() {
    if (!state.musicId) {
      toast("Önce şarkı yükle");
      return;
    }
    try {
      await refreshMusicStatus();
      const m = state.musicMeta || {};
      const done = Number(m.linked_done || 0);
      const pending = Number(m.linked_pending || 0);
      if (!done && pending) {
        toast(`Bu şarkı için ${pending} klip hâlâ üretiliyor — bitmesini bekle`);
        appendDirectorMsg(
          "assistant",
          `Şarkılı final eski galeriyi birleştirmez. Bu şarkıya özel ${pending} klip kuyrukta/çalışıyor — bitince tekrar bas.`
        );
        return;
      }
      if (!done) {
        toast("Önce yeni sahneleri kuyruğa al ve üret");
        appendDirectorMsg(
          "assistant",
          "Şarkılı final = sadece **bu şarkı için yeni üretilen** klipler + şarkı. "
            + "Sıra: **Şarkıdan brief** → **Tüm shot’ları kuyruğa al** → bitince **Şarkılı final**. "
            + "Eski klipler kullanılmaz."
        );
        return;
      }
      toast(`Bu şarkının ${done} yeni klibi + şarkı birleştiriliyor…`);
      $("btn-music-mux").disabled = true;
      const r = await fetch("/api/music/mux", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ music_id: state.musicId }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (state.musicMeta) {
        state.musicMeta.final_ready = true;
        state.musicMeta.final_url = data.final_url;
      }
      updateMusicMuxUi();
      appendDirectorMsg(
        "assistant",
        `Şarkılı final hazır — bu şarkıya özel ${data.clip_count} yeni klip + şarkı.`
      );
      toast("Final hazır");
      if (data.final_url) window.open(data.final_url, "_blank");
    } catch (e) {
      toast(String(e.message || e));
      appendDirectorMsg("assistant", String(e.message || e));
    } finally {
      updateMusicMuxUi();
    }
  }

  function renderQueue() {
    const ol = $("batch-list");
    if (!ol) return;
    ol.innerHTML = "";
    state.queueItems.forEach((item, i) => {
      const li = document.createElement("li");
      li.className = "batch-item";
      li.dataset.id = item.id;
      const num = document.createElement("span");
      num.className = "batch-num";
      num.textContent = String(i + 1);
      const ta = document.createElement("textarea");
      ta.value = item.text;
      ta.rows = 2;
      ta.oninput = () => {
        item.text = ta.value;
      };
      const rm = document.createElement("button");
      rm.type = "button";
      rm.className = "btn-ghost";
      rm.textContent = "Sil";
      rm.onclick = () => {
        state.queueItems = state.queueItems.filter((x) => x.id !== item.id);
        renderQueue();
      };
      li.appendChild(num);
      li.appendChild(ta);
      li.appendChild(rm);
      ol.appendChild(li);
    });
    $("batch-empty")?.classList.toggle("hidden", state.queueItems.length > 0);
  }

  const PRODUCTION_LS_KEY = "h3_production_v1";

  function collectProductionState() {
    return {
      version: 1,
      duration: state.duration,
      quality: state.quality,
      aspect: state.aspect || "16:9",
      seed: numOr("seed", -1),
      steps: numOr("steps", 20) || 20,
      sampler: $("sampler")?.value || "res_multistep",
      scheduler: $("scheduler")?.value || "simple",
      loraId: $("lora-select") ? $("lora-select").value : (state.loraId || ""),
      produceMode: state.produceMode || "t2v",
      batchContinue: true,
      projectPurpose: state.projectPurpose,
      projectStyle: state.projectStyle,
      projectSilent: !!state.projectSilent,
      musicId: state.musicId || null,
      prompt: ($("prompt")?.value || "").trim(),
      queueItems: state.queueItems.map((x) => ({
        id: x.id,
        text: (x.text || "").trim(),
      })),
      continueFrom: state.continueFrom || null,
      refImageSize: state.refImageSize || "match",
    };
  }

  function applyProductionState(snap, opts) {
    if (!snap || typeof snap !== "object") return false;
    const quiet = !!(opts && opts.quiet);
    if (snap.duration != null) setDuration(snap.duration);
    if (snap.quality != null) setQuality(snap.quality);
    if (snap.aspect) setAspect(snap.aspect);
    if ($("seed") && snap.seed != null) $("seed").value = String(snap.seed);
    if ($("steps") && snap.steps != null) $("steps").value = String(snap.steps);
    if ($("sampler") && snap.sampler) $("sampler").value = snap.sampler;
    if ($("scheduler") && snap.scheduler) $("scheduler").value = snap.scheduler;
    if (snap.loraId !== undefined && $("lora-select")) {
      $("lora-select").value = snap.loraId || "";
      state.loraId = snap.loraId || "";
      state.loraApplied = !!(snap.loraId && snap.loraApplied !== false);
      keepLoraApplied();
    }
    if (snap.projectPurpose !== undefined) state.projectPurpose = snap.projectPurpose;
    if (snap.projectStyle !== undefined) state.projectStyle = snap.projectStyle;
    if (snap.projectSilent !== undefined) {
      state.projectSilent = !!snap.projectSilent;
    } else {
      state.projectSilent = state.projectPurpose === "music_video";
    }
    if (snap.musicId !== undefined) state.musicId = snap.musicId;
    if (typeof snap.prompt === "string" && $("prompt")) $("prompt").value = snap.prompt;
    if (Array.isArray(snap.queueItems)) {
      state.queueItems = snap.queueItems
        .map((x, i) => ({
          id: (x && x.id) || `restored-${i}`,
          text: ((x && x.text) || "").trim(),
        }))
        .filter((x) => x.text);
      renderQueue();
    }
    if (snap.produceMode) setProduceMode(snap.produceMode);
    if (snap.continueFrom) state.continueFrom = snap.continueFrom;
    if (snap.refImageSize) state.refImageSize = snap.refImageSize;
    syncProjectChips();
    setQuality(state.quality);
    if (!quiet) {
      const n = state.queueItems.length;
      toast(n ? `Üretim yüklendi · ${n} prompt` : "Üretim ayarları yüklendi");
    }
    return true;
  }

  function persistProductionLocal(snap) {
    try {
      const copy = { ...(snap || {}), saved_at: (snap && snap.saved_at) || Date.now() / 1000 };
      localStorage.setItem(PRODUCTION_LS_KEY, JSON.stringify(copy));
    } catch {
      /* ignore quota */
    }
  }

  async function saveProduction(opts) {
    const quiet = !!(opts && opts.quiet);
    const snap = collectProductionState();
    snap.saved_at = Date.now() / 1000;
    persistProductionLocal(snap);
    try {
      const r = await fetch("/api/production", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(snap),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (data.production) applyProductionState({ ...snap, ...data.production }, { quiet: true });
      if (!quiet) {
        toast(`Üretim kaydedildi · ${snap.queueItems.length} prompt`);
      }
      return true;
    } catch (e) {
      if (!quiet) toast(`Yerel kaydedildi; sunucu: ${e.message || e}`);
      return false;
    }
  }

  async function loadProduction(opts) {
    const quiet = !!(opts && opts.quiet);
    const force = !!(opts && opts.force);
    let localSnap = null;
    try {
      const raw = localStorage.getItem(PRODUCTION_LS_KEY);
      if (raw) localSnap = JSON.parse(raw);
    } catch {
      localSnap = null;
    }
    try {
      const r = await fetch("/api/production");
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      let snap = data.saved && data.production ? data.production : null;
      // Prefer whichever snapshot is newer (local draft vs server)
      const localAt = Number(localSnap && localSnap.saved_at) || 0;
      const serverAt = Number(snap && snap.saved_at) || 0;
      if (localSnap && (!snap || localAt > serverAt)) snap = localSnap;
      if (!snap) {
        if (!quiet) toast("Kayıtlı üretim yok");
        return false;
      }
      if (
        force ||
        !state.queueItems.length ||
        confirm("Kayıtlı üretimi yükle? Mevcut prompt listesi / ayarlar değişir (Comfy kuyruğu kalır).")
      ) {
        applyProductionState(snap, { quiet });
        return true;
      }
      return false;
    } catch (e) {
      if (localSnap && (force || !state.queueItems.length)) {
        applyProductionState(localSnap, { quiet });
        return true;
      }
      if (!quiet) toast(String(e.message || e));
      return false;
    }
  }

  function addQueuePrompt(text) {
    const t = (text || "").trim();
    if (!t) {
      toast("Boş prompt eklenmez");
      return false;
    }
    state.queueItems.push({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      text: t,
    });
    renderQueue();
    toast(`Prompt ${state.queueItems.length} eklendi`);
    return true;
  }

  async function addPromptFromScene() {
    const ok = await submitGenerate();
    if (!ok) return false;
    const ta = $("prompt");
    if (ta) {
      ta.value = "";
      ta.focus();
    }
    return true;
  }

  function setQueueFromTexts(texts) {
    state.queueItems = (texts || [])
      .map((t) => (t || "").trim())
      .filter(Boolean)
      .map((text, i) => ({
        id: `q-${Date.now()}-${i}`,
        text,
      }));
    renderQueue();
  }

  async function applyBrief(queue) {
    if (!state.directorSessionId) {
      toast("Önce yönetmenle konuş");
      return;
    }
    try {
      toast(queue ? "Shot’lar kuyruğa alınıyor…" : "Shot listesi aktarılıyor…");
      const r = await fetch("/api/director/commit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.directorSessionId,
          queue: !!queue,
          // use UI checkbox to control continue-linking (default checked)
          link_continue: !!$("link-continue")?.checked,
          append_to_chain: true,
          quality: state.quality,
          aspect: state.aspect || "16:9",
          purpose: state.projectPurpose,
          silent_audio: state.projectSilent || state.projectPurpose === "music_video",
          clip_duration: state.duration || 5,
          ...collectGenerateKnobs(),
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(errDetail(data));
      const a = data.applied || {};
      const prompts = Array.isArray(a.prompts)
        ? a.prompts
        : String(a.batch_prompts || "")
            .split(/\n\s*---\s*\n/)
            .map((s) => s.trim())
            .filter(Boolean);
      if (a.prompt) $("prompt").value = a.prompt;
      if (prompts.length) setQueueFromTexts(prompts);
      const n = a.shot_count || prompts.length;
      const total = a.total_duration_sec ? ` · ${a.total_duration_sec}sn` : "";
      toast(
        queue
          ? `Üretim: ${n} iş sıraya alındı (continue zinciri)${total}`
          : `${n} shot listede${total}`
      );
      if (queue) {
        setDirectorOpen(false);
        await refreshJobs();
      }
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function refreshHealth() {
    try {
      const h = await fetch("/api/health").then((r) => r.json());
      const pill = $("comfy-pill");
      pill.textContent = h.comfy ? "Comfy online" : "Comfy offline";
      pill.classList.toggle("on", !!h.comfy);
      pill.classList.toggle("off", !h.comfy);
    } catch {
      $("comfy-pill").textContent = "Studio?";
    }
  }

  async function pollSystem() {
    try {
      const s = await fetch("/api/system").then((r) => r.json());
      $("sys-cpu").textContent = `${s.cpu_percent ?? "—"}%`;
      $("sys-ram").textContent =
        s.ram_used_gb != null
          ? `${s.ram_used_gb}/${s.ram_total_gb}G`
          : "—";
      if ($("sys-ram")) {
        $("sys-ram").title =
          s.ram_percent != null
            ? `${s.ram_used_gb} / ${s.ram_total_gb} GB (${s.ram_percent}%)`
            : "";
      }
      {
        const raw = String(s.gpu_name || "GPU");
        const short = raw.replace(/^NVIDIA GeForce\s+/i, "").replace(/^NVIDIA\s+/i, "");
        const util = s.gpu_util != null ? ` ${Math.round(s.gpu_util)}%` : "";
        $("sys-gpu").textContent = `${short}${util}`;
        $("sys-gpu").title = raw + (s.gpu_util != null ? ` · ${Math.round(s.gpu_util)}%` : "");
      }
      $("sys-vram").textContent =
        s.vram_total_gb != null
          ? `${s.vram_used_gb}/${s.vram_total_gb}G`
          : "—";
      if ($("sys-vram") && s.vram_percent != null) {
        $("sys-vram").title = `${s.vram_used_gb} / ${s.vram_total_gb} GB (${s.vram_percent}%) · nvidia-smi`;
      }
      $("sys-disk").textContent =
        s.disk_free_gb != null ? `${s.disk_free_gb}G` : "—";
      if ($("sys-disk") && s.disk_free_gb != null) {
        $("sys-disk").title = `${s.disk_free_gb} GB boş`;
      }
      $("sys-comfy").textContent = s.comfy_online ? "on" : "off";
      $("sys-comfy-item")?.classList.toggle("comfy-on", !!s.comfy_online);
      $("sys-comfy-item")?.classList.toggle("comfy-off", !s.comfy_online);
    } catch {
      /* ignore */
    }
  }

  function selectJob(job, { play = true } = {}) {
    state.selectedJobId = job.id;
    const meta = `${job.duration || "?"}sn · ${job.width || "?"}×${job.height || "?"} · ${job.mode || "t2v"}`;
    setClipPrompt(job.prompt || "", meta);
    if (play && job.output?.url) {
      showPlayerVideo(job.output.url, job.id, job.prompt || "");
    }
    if (state.produceMode === "continue") {
      const sel = $("continue-source");
      if (sel) sel.value = job.id;
      void setContinueMode(job.id, { silent: true });
    }
    toast(
      job.status === "done"
        ? `Hazır · ${job.duration}sn · seed ${job.seed}`
        : `${job.status} · ${job.progress || 0}%`
    );
  }

  function renderJobs() {
    const ul = $("job-list");
    ul.innerHTML = "";
    // Active = eski üretim sırası (FIFO). Finished = yeniler üstte (40 cap).
    const finishedRank = (j) => {
      if (j.status === "error" || j.status === "cancelled") return 0;
      return 1;
    };
    const byFinishedThenRecent = (a, b) => {
      const ra = finishedRank(a);
      const rb = finishedRank(b);
      if (ra !== rb) return ra - rb;
      return (Number(b.created_at) || 0) - (Number(a.created_at) || 0);
    };
    const active = state.jobs
      .filter((j) => j.status === "running" || j.status === "queued")
      .sort(productionOrderCmp);
    const finished = state.jobs
      .filter((j) => j.status !== "running" && j.status !== "queued")
      .sort(byFinishedThenRecent)
      .slice(0, 40);
    const jobs = active.concat(finished);
    const head = document.querySelector(".job-queue-head");
    if (head) {
      const qn = active.filter((j) => j.status === "queued").length;
      const rn = active.some((j) => j.status === "running");
      head.textContent = rn
        ? `Kuyruk · üretiliyor + ${qn} sırada`
        : qn
          ? `Kuyruk · ${qn} sırada`
          : "Kuyruk";
    }
    const activeOrder = new Map(active.map((j, i) => [j.id, i + 1]));
    for (const j of jobs) {
      const li = document.createElement("li");
      if (j.status === "running") li.classList.add("job-running");
      const left = document.createElement("div");
      const st =
        j.status === "done" ? "st-done" : j.status === "running" ? "st-run" : j.status === "error" ? "st-err" : "";
      const pct =
        j.status === "running"
          ? ` <span class="job-prog">${j.progress || 0}%</span>`
          : j.status === "queued"
            ? ""
            : "";
      const err = j.status === "error" && j.error ? ` — ${String(j.error).slice(0, 60)}` : "";
      const sira = activeOrder.has(j.id)
        ? `<span class="job-sira">#${activeOrder.get(j.id)}</span> `
        : "";
      left.innerHTML = `${sira}<span class="${st}">${j.status}</span>${pct} · ${(j.prompt || "").slice(0, 36)}${err}`;
      left.title = j.error || j.prompt || "";
      left.style.cursor = j.prompt ? "pointer" : "";
      if (j.prompt) {
        left.onclick = (e) => {
          e.stopPropagation();
          openPromptView(
            j.prompt,
            `${j.duration || "?"}sn · ${j.width || "?"}×${j.height || "?"} · ${j.mode || "t2v"}`
          );
        };
      }
      const right = document.createElement("div");
      if (j.prompt) {
        const cp = document.createElement("button");
        cp.textContent = "Prompt";
        cp.className = "btn-ghost";
        cp.title = "Promptu gör";
        cp.onclick = (e) => {
          e.stopPropagation();
          openPromptView(
            j.prompt,
            `${j.duration || "?"}sn · ${j.width || "?"}×${j.height || "?"} · ${j.mode || "t2v"}`
          );
        };
        right.appendChild(cp);
      }
      if (j.status === "done") {
        const b = document.createElement("button");
        b.textContent = "Oynat";
        b.onclick = () => selectJob(j);
        right.appendChild(b);
        const rm = document.createElement("button");
        rm.textContent = "Sil";
        rm.className = "btn-ghost";
        rm.onclick = (e) => {
          e.stopPropagation();
          void deleteJob(j.id);
        };
        right.appendChild(rm);
      } else if (j.status === "error" || j.status === "cancelled") {
        const b = document.createElement("button");
        b.textContent = "Tekrar dene";
        b.onclick = async (e) => {
          e.stopPropagation();
          b.disabled = true;
          try {
            const r = await fetch(`/api/jobs/${j.id}/retry`, { method: "POST" });
            const data = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(errDetail(data));
            toast("Tekrar kuyruğa alındı");
            await refreshJobs();
          } catch (err) {
            toast(String(err.message || err));
            b.disabled = false;
          }
        };
        right.appendChild(b);
        const rm = document.createElement("button");
        rm.textContent = "Sil";
        rm.className = "btn-ghost";
        rm.onclick = (e) => {
          e.stopPropagation();
          void deleteJob(j.id);
        };
        right.appendChild(rm);
      } else if (j.batch_index) {
        right.textContent = `${j.batch_index}/${j.batch_total}`;
      } else if (activeOrder.has(j.id)) {
        right.textContent = `sıra ${activeOrder.get(j.id)}/${active.length}`;
      }
      li.appendChild(left);
      li.appendChild(right);
      ul.appendChild(li);
    }
    const running = active.find((j) => j.status === "running")
      || state.jobs.find((j) => j.status === "running");
    const queuedJobs = active.filter((j) => j.status === "queued");
    const queued = queuedJobs.length;

    /** Progress bar = THIS clip's Comfy % (same idea as ComfyUI). Batch is text-only. */
    function productionBar(job) {
      if (!job) return { pct: 0, label: "" };
      const bi = Number(job.batch_index) || 0;
      const bt = Number(job.batch_total) || 0;
      const step = job.comfy_step;
      const stepMax = job.comfy_step_max;
      let clipPct = Math.max(0, Math.min(100, Number(job.progress) || 0));
      // Prefer live Comfy sampler fraction when present
      if (step != null && stepMax > 0) {
        clipPct = Math.max(0, Math.min(100, Math.round((100 * Number(step)) / Number(stepMax))));
      }
      let clipLabel = job.progress_label || "Comfy…";
      if (step != null && stepMax > 0 && !/örnekleme\s+\d+\/\d+/i.test(clipLabel)) {
        clipLabel = `örnekleme ${step}/${stepMax}`;
      }
      const bits = [];
      if (bi > 0 && bt > 0) bits.push(`${bi}/${bt}`);
      bits.push(clipLabel);
      if (bi > 0 && bt > 1) {
        const sameBatch = state.jobs.filter(
          (j) => Number(j.batch_total) === bt && Number(j.batch_index) > 0
        );
        const doneCount = sameBatch.filter((j) => j.status === "done").length;
        const completed = Math.max(doneCount, bi - 1);
        const overall = ((completed + clipPct / 100) / bt) * 100;
        bits.push(`seri ~${Math.round(overall)}%`);
      }
      return {
        pct: Math.max(1, clipPct || 1),
        label: bits.join(" · "),
      };
    }

    if (running) {
      // Active work — cancel any pending hide and show live %
      if (state.progressHideTimer) {
        clearTimeout(state.progressHideTimer);
        state.progressHideTimer = null;
      }
      state.lastRunningId = running.id;
      const batch = running.batch_index ? ` ${running.batch_index}/${running.batch_total}` : "";
      const res =
        running.width && running.height ? ` · ${running.width}×${running.height}` : "";
      toast(`Üretiliyor${batch}${res}`);
      const bar = productionBar(running);
      setProgress(bar.pct, bar.label, true);
    } else if (queued) {
      if (state.progressHideTimer) {
        clearTimeout(state.progressHideTimer);
        state.progressHideTimer = null;
      }
      const next = queuedJobs[0];
      const siraN = next && activeOrder.get(next.id);
      const idx = next?.batch_index
        ? ` ${next.batch_index}/${next.batch_total}`
        : siraN
          ? ` #${siraN}`
          : "";
      toast(`Sırada${idx} · ${queued} iş`);
      const bar = productionBar(next);
      setProgress(Math.max(0.5, bar.pct), bar.label || "sırada bekliyor", true);
    } else {
      // Idle: no running / queued — resolve last transition, then clear sticky bar
      const finishedId = state.lastRunningId;
      if (finishedId) {
        const j = state.jobs.find((x) => x.id === finishedId);
        state.lastRunningId = null;
        if (
          state.pendingContinueChild &&
          state.jobs.find((x) => x.id === state.pendingContinueChild && x.status === "done")
        ) {
          const childId = state.pendingContinueChild;
          state.pendingContinueChild = null;
          state.continueFrom = childId;
          setProduceMode("continue");
          void setContinueMode(childId, { silent: true });
        }
        if (j?.status === "done") {
          toast(
            `Hazır · ${j.duration}sn · ${j.width || "?"}×${j.height || "?"} · seed ${j.seed}`
          );
          setProgress(100, "bitti", true);
          scheduleHideProgress(2200);
          if (
            j.output?.url &&
            !state.playerCleared &&
            (!state.selectedJobId || state.selectedJobId === finishedId)
          ) {
            selectJob(j);
          }
          fillContinueSource();
        } else if (j?.status === "cancelled") {
          toast("Durduruldu");
          setProgress(0, "iptal edildi", true);
          scheduleHideProgress(1400);
        } else if (j?.status === "error") {
          toast(`Hata · ${String(j.error || "").slice(0, 80)}`);
          setProgress(0, "hata", true);
          scheduleHideProgress(2200);
        } else {
          // Job removed from list (geçmiş temiz / reset)
          hideProgressNow();
          toast("Hazır");
        }
      } else if (!state.progressHideTimer) {
        // Nothing active and not in brief post-finish display — kill sticky bar
        const wrap = $("progress-wrap");
        if (wrap && !wrap.classList.contains("hidden")) {
          setProgress(0, "", false);
        }
        const pt = $("prod-text");
        if (pt && /^(İptal istendi|Üretiliyor|Sırada|Durduruldu)/.test(pt.textContent || "")) {
          toast("Hazır");
        }
      }
    }
  }

  async function renderGallery() {
    const grid = $("gallery-grid");
    if (!grid) return;
    grid.innerHTML = `<p class="muted">Yükleniyor…</p>`;
    let done = [];
    try {
      const data = await fetch("/api/gallery").then((r) => r.json());
      done = (data.items || []).slice();
      state.galleryItems = done;
    } catch {
      grid.innerHTML = `<p class="muted">Galeri yüklenemedi.</p>`;
      return;
    }
    // Newest finished first (left) → oldest right
    done.sort((a, b) => {
      const ta = Number(a.done_at || a.created_at || 0);
      const tb = Number(b.done_at || b.created_at || 0);
      if (tb !== ta) return tb - ta;
      return (Number(b.batch_index) || 0) - (Number(a.batch_index) || 0);
    });
    if (!done.length) {
      grid.innerHTML = `<p class="muted">Henüz arşivlenmiş video yok. Üretilen her klip burada kalır (temiz başlat silmez).</p>`;
      return;
    }
    grid.innerHTML = "";
    done.forEach((j, i) => {
      const card = document.createElement("div");
      card.className = "gallery-card";
      const url = j.url || `/api/gallery/${j.id}/video`;
      const ord =
        j.batch_index && j.batch_total
          ? `${j.batch_index}/${j.batch_total}`
          : `#${done.length - i}`;
      const when = j.done_at || j.created_at;
      const clock = when
        ? new Date(Number(when) * 1000).toLocaleString("tr-TR", {
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          })
        : "";
      let renderLabel = "";
      let rs = j.render_sec;
      if (rs == null && j.started_at != null && j.done_at != null) {
        rs = Math.max(0, Math.round(Number(j.done_at) - Number(j.started_at)));
      } else if (rs == null && j.created_at != null && j.done_at != null) {
        rs = Math.max(0, Math.round(Number(j.done_at) - Number(j.created_at)));
      }
      if (rs != null && Number.isFinite(Number(rs))) {
        const sec = Math.max(0, Math.round(Number(rs)));
        if (sec < 60) renderLabel = `<1dk`;
        else {
          const h = Math.floor(sec / 3600);
          const m = Math.floor((sec % 3600) / 60);
          renderLabel = h > 0 ? `${h}s ${m}dk` : `${m}dk`;
        }
      }
      card.innerHTML = `
        <div class="gallery-ord">${i === 0 ? "Yeni · " : ""}${ord}</div>
        <button type="button" class="gallery-del" title="Galeriden sil" aria-label="Sil">×</button>
        <div class="gallery-thumb">
          <video src="${url}" muted preload="metadata"></video>
          ${j.prompt ? `<button type="button" class="gallery-prompt" title="Promptu aç">P</button>` : ""}
          <button type="button" class="gallery-cont" title="Bu videodan devam">Devam</button>
        </div>
        <div class="meta">${j.duration != null ? j.duration + "sn · " : ""}${j.width || "?"}×${j.height || "?"} · ${j.mode || "t2v"}${renderLabel ? " · " + renderLabel : ""}${clock ? " · " + clock : ""}</div>`;
      const delBtn = card.querySelector(".gallery-del");
      if (delBtn) {
        delBtn.onclick = (e) => {
          e.preventDefault();
          e.stopPropagation();
          void deleteGalleryItem(j.id);
        };
      }
      const pBtn = card.querySelector(".gallery-prompt");
      if (pBtn) {
        pBtn.onclick = (e) => {
          e.preventDefault();
          e.stopPropagation();
          openPromptView(
            j.prompt,
            `${j.duration != null ? j.duration + "sn · " : ""}${j.width || "?"}×${j.height || "?"}`
          );
        };
      }
      const contBtn = card.querySelector(".gallery-cont");
      if (contBtn) {
        contBtn.onclick = (e) => {
          e.preventDefault();
          e.stopPropagation();
          void useClipAsContinue(j);
        };
      }
      card.onclick = () => {
        const live = state.jobs.find((x) => x.id === j.id && x.status === "done");
        const meta = `${j.duration != null ? j.duration + "sn · " : ""}${j.width || "?"}×${j.height || "?"}`;
        if (live) {
          selectJob(live);
        } else {
          showPlayerVideo(url, j.id, j.prompt || "");
          setClipPrompt(j.prompt || "", meta);
          toast(`Arşiv · ${meta}`);
        }
        $("view-gallery").classList.add("hidden");
        closePromptView();
      };
      grid.appendChild(card);
    });
  }

  async function deleteGalleryItem(itemId) {
    if (!itemId) return;
    if (!confirm("Bu video galeriden silinsin mi?")) return;
    try {
      const r = await fetch(`/api/gallery/${encodeURIComponent(itemId)}`, {
        method: "DELETE",
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (state.selectedJobId === itemId) clearPlayer();
      toast("Galeriden silindi");
      await renderGallery();
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function refreshJobs() {
    try {
      const data = await fetch("/api/jobs").then((r) => r.json());
      state.jobs = data.jobs || [];
      renderJobs();
      fillContinueSource();
      if (!state.playerCleared && state.selectedJobId) {
        const j = state.jobs.find((x) => x.id === state.selectedJobId);
        if (j?.status === "done" && j.output?.url) {
          const player = $("player");
          if (player && !player.src.includes(j.id)) selectJob(j);
        }
      }
    } catch {
      /* ignore */
    }
  }

  function numOr(id, fallback) {
    const n = Number($(id)?.value);
    return Number.isFinite(n) ? n : fallback;
  }

  function clearContinueMode() {
    state.continueFrom = null;
    $("continue-box")?.classList.add("hidden");
  }

  async function ensureLastFrame(jobId) {
    const thumb = $("continue-thumb");
    const url = `/api/clips/${jobId}/last-frame?t=${Date.now()}`;
    try {
      const r = await fetch(`/api/jobs/${jobId}/prepare-last-frame`, { method: "POST" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data) || "last frame yok");
    } catch (e) {
      $("continue-box")?.classList.add("hidden");
      toast(String(e.message || e));
      return "";
    }
    if (thumb) {
      thumb.onload = () => $("continue-box")?.classList.remove("hidden");
      thumb.onerror = () => {
        $("continue-box")?.classList.add("hidden");
        toast("Last frame alınamadı — video dosyası eksik olabilir");
      };
      thumb.src = url;
      thumb.alt = "last frame";
    }
    return url;
  }

  function findContinueJob(jobId) {
    return (
      state.jobs.find((j) => j.id === jobId) ||
      (state.galleryItems || []).find((j) => j.id === jobId) ||
      null
    );
  }

  function chainTipJob() {
    const active = state.jobs
      .filter((j) => j.status === "queued" || j.status === "running")
      .sort((a, b) => (Number(a.created_at) || 0) - (Number(b.created_at) || 0));
    if (active.length) return active[active.length - 1];
    const done = state.jobs
      .filter((j) => j.status === "done")
      .sort((a, b) => (Number(a.created_at) || 0) - (Number(b.created_at) || 0));
    if (done.length) return done[done.length - 1];
    const gal = state.galleryItems || [];
    return gal.length ? gal[0] : null;
  }

  async function useClipAsContinue(clip) {
    const jobId = typeof clip === "string" ? clip : clip && clip.id;
    if (!jobId) {
      toast("Önce bir video seç");
      return false;
    }
    if (!(state.galleryItems || []).length) {
      try {
        const data = await fetch("/api/gallery").then((r) => r.json());
        state.galleryItems = data.items || [];
      } catch {
        /* ignore */
      }
    }
    const job =
      (typeof clip === "object" && clip) ||
      findContinueJob(jobId) ||
      { id: jobId, status: "done", url: `/api/gallery/${jobId}/video` };
    state.selectedJobId = jobId;
    state.continueFrom = jobId;
    $("view-gallery")?.classList.add("hidden");
    $("view-cinema")?.classList.add("hidden");
    $("view-support")?.classList.add("hidden");
    const url =
      job.url ||
      job.output?.url ||
      `/api/gallery/${jobId}/video`;
    showPlayerVideo(url, jobId, job.prompt || "");
    if (job.prompt) setClipPrompt(job.prompt);
    setProduceMode("continue");
    await fillContinueSource();
    const sel = $("continue-source");
    if (sel) {
      if (![...sel.options].some((o) => o.value === jobId)) {
        const opt = document.createElement("option");
        opt.value = jobId;
        opt.textContent = `galeri · ${(job.prompt || jobId).slice(0, 42)}`;
        sel.appendChild(opt);
      }
      sel.value = jobId;
    }
    const ok = await setContinueMode(jobId);
    if (ok) $("prompt")?.focus();
    return ok;
  }

  async function setContinueMode(jobId, { silent = false } = {}) {
    let job = findContinueJob(jobId);
    if (!job && jobId) {
      job = { id: jobId, status: "done", url: `/api/gallery/${jobId}/video` };
      if (!(state.galleryItems || []).some((x) => x.id === jobId)) {
        state.galleryItems = [job, ...(state.galleryItems || [])];
      }
    }
    const status = job?.status || (job ? "done" : "");
    if (!job || !["done", "running", "queued", "archive"].includes(status)) {
      if (!silent) toast("Devam için kuyrukta / bitmiş bir video seç");
      return false;
    }
    state.continueFrom = jobId;
    state.selectedJobId = jobId;
    const sel = $("continue-source");
    if (sel) sel.value = jobId;
    const lab = $("continue-label");
    if (lab) {
      lab.textContent =
        status === "done" || status === "archive"
          ? `Son kare · ${(job.prompt || "").slice(0, 40)}`
          : `Sıra sonrası · ${status} · ${(job.prompt || "").slice(0, 32)}`;
    }
    if (status === "done" || status === "archive") {
      $("continue-box")?.classList.remove("hidden");
      if (!silent) toast("Last frame hazırlanıyor…");
      await ensureLastFrame(jobId);
      if (!silent) toast("Devam kaynağı hazır");
    } else {
      $("continue-box")?.classList.add("hidden");
      if (!silent) toast("Devam kuyruğa eklenecek — önceki bitince üretilir");
    }
    return true;
  }

  async function submitGenerate() {
    const prompt = $("prompt").value.trim();
    if (!prompt) {
      toast("Prompt yaz");
      return false;
    }
    const mode = state.produceMode;
    if (mode === "cinema" || mode === "storyboard") {
      openCinemaStudio();
      toast("Direktör stüdyosundan filmi kuyruğa al");
      return false;
    }
    const isContinue = mode === "continue";
    const isRef = mode === "ref";
    const isFace = mode === "face";
    const isV2v = mode === "v2v";
    if (isContinue) {
      const pick = $("continue-source")?.value || state.continueFrom || "";
      if (pick) {
        await setContinueMode(pick, { silent: true });
      } else {
        const tip = chainTipJob();
        if (tip) await setContinueMode(tip.id, { silent: true });
      }
      if (!state.continueFrom) {
        toast("Devam için kaynak yok — video seç veya önce üret");
        fillContinueSource();
        return false;
      }
    }
    if (isRef && !state.refImages.length) {
      toast("Referans için en az 1 görsel yükle");
      return false;
    }
    if (isFace && !state.faceImages.length) {
      toast("Yüz referansı için en az 1 portre yükle");
      return false;
    }
    if (isV2v && !state.v2vVideos.length && !state.v2vImages.length) {
      toast("V2V için en az 1 video veya görsel yükle");
      return false;
    }

    const btn = $("btn-generate");
    if (btn) btn.disabled = true;
    try {
      const faceLockOn = !!$("face-lock-chain")?.checked && state.faceImages.length > 0;
      const body = {
        prompt: withStyleLock(prompt),
        duration: state.duration,
        aspect: state.aspect || "16:9",
        quality: state.quality,
        seed: numOr("seed", -1),
        ...collectGenerateKnobs(),
        mode: isContinue
          ? "continue"
          : isFace
            ? "face"
            : isV2v
              ? "v2v"
              : isRef
                ? "ref"
                : "t2v",
        continue_from_job_id: isContinue ? state.continueFrom : null,
        purpose: state.projectPurpose || null,
        silent_audio: state.projectSilent || state.projectPurpose === "music_video",
      };
      if (isRef) {
        body.ref_images = state.refImages.map((x) => x.name);
        body.ref_image_size = state.refImageSize || "match";
      }
      if (isFace) {
        body.ref_images = state.faceImages.map((x) => x.name);
        body.ref_image_size = "max";
      }
      if (isV2v) {
        body.ref_videos = state.v2vVideos.map((x) => x.name);
        body.ref_images = state.v2vImages.map((x) => x.name);
        body.ref_image_size = state.refImageSize || "match";
        body.include_video_audio = !!$("v2v-include-audio")?.checked;
      }
      if (!isContinue && !isRef && !isFace && !isV2v) {
        if (state.firstFrameName) body.first_frame_name = state.firstFrameName;
        if (state.lastFrameName) body.last_frame_name = state.lastFrameName;
      }
      // Continue + yüz kilidi → portreleri de gönder (sunucu last frame ile birleştirir)
      if (isContinue && faceLockOn) {
        body.ref_images = state.faceImages.map((x) => x.name);
        body.ref_image_size = "max";
      }
      const r = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      state.selectedJobId = data.id;
      state.playerCleared = false;
      state.pendingContinueChild = isContinue ? data.id : null;
      const queuedLabel = isContinue
        ? faceLockOn
          ? "Devam + yüz kilidi sıraya alındı"
          : "Devam sıraya alındı (önceki bitince)"
        : isFace
          ? "Yüz referansı kuyruğa alındı (sonraki kliplerde kilitlenebilir)"
          : isRef
            ? "Referans kuyruğa alındı"
            : "Yeni video kuyruğa alındı";
      toast(queuedLabel);
      setDirectorOpen(false);
      await refreshJobs();
      return true;
    } catch (e) {
      toast(String(e.message || e));
      return false;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  $("btn-generate").onclick = () => submitGenerate();
  $("btn-fast-preset")?.addEventListener("click", () => {
    setDuration(5);
    setQuality("480");
    if (!state.loraApplied) {
      const steps = $("steps");
      if (steps) steps.value = "12";
    }
    state.projectSilent = true;
    keepLoraApplied();
    toast(
      state.loraApplied
        ? `Fast: 5sn · 480p · LoRA step/sampler duruyor · sessiz`
        : "Fast: 5sn · 480p · 12 step · sessiz bayrağı açık"
    );
  });

  function currentLoraSpec() {
    const sel = $("lora-select");
    const id = sel ? sel.value : (state.loraId || "");
    return (state.loraCatalog || []).find((x) => x.id === id) || null;
  }

  function appliedLoraSpec() {
    if (!state.loraApplied || !state.loraId) return null;
    return (state.loraCatalog || []).find((x) => x.id === state.loraId) || null;
  }

  function keepLoraApplied() {
    const spec = appliedLoraSpec();
    if (!spec || !spec.file) return;
    // Do not force the dropdown — user must be able to pick "Yok" then Uygula.
    if (spec.preset && spec.steps && $("steps")) $("steps").value = String(spec.steps);
    if (spec.preset && spec.sampler && $("sampler")) {
      const samp = $("sampler");
      if (![...samp.options].some((o) => o.value === spec.sampler)) {
        const opt = document.createElement("option");
        opt.value = spec.sampler;
        opt.textContent = spec.sampler;
        samp.appendChild(opt);
      }
      samp.value = spec.sampler;
    }
    if (spec.preset && spec.scheduler && $("scheduler")) $("scheduler").value = spec.scheduler;
    updateLoraHint();
  }

  function collectLoraPayload() {
    const spec = appliedLoraSpec();
    if (!spec || !spec.file) return { lora_id: "", lora_name: "", lora_strength: null };
    return {
      lora_id: spec.id,
      lora_name: spec.file,
      lora_strength: spec.strength,
    };
  }

  function collectGenerateKnobs() {
    const spec = appliedLoraSpec();
    const steps =
      spec && spec.preset && spec.steps
        ? spec.steps
        : numOr("steps", 20) || 20;
    const sampler =
      spec && spec.preset && spec.sampler
        ? spec.sampler
        : $("sampler")?.value || "res_multistep";
    const scheduler =
      spec && spec.preset && spec.scheduler
        ? spec.scheduler
        : $("scheduler")?.value || "simple";
    return {
      steps,
      sampler,
      scheduler,
      ...collectLoraPayload(),
    };
  }

  function fillLoraSelect() {
    const sel = $("lora-select");
    if (!sel) return;
    const prev = state.loraApplied && state.loraId ? state.loraId : sel.value || state.loraId || "";
    const catalog = state.loraCatalog || [];
    sel.innerHTML = "";
    if (!catalog.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Yok (varsayılan)";
      sel.appendChild(opt);
    } else {
      catalog.forEach((spec) => {
        const opt = document.createElement("option");
        opt.value = spec.id;
        const graphs = spec.graphs || [];
        const flOnly = graphs.length && !graphs.includes("ref2va");
        const miss = spec.file && !spec.ready ? " — indirilecek" : "";
        const tag = flOnly ? " · T2V" : "";
        opt.textContent = `${spec.label}${tag}${miss}`;
        sel.appendChild(opt);
      });
    }
    if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
    keepLoraApplied();
    updateLoraHint();
  }

  function updateLoraHint() {
    const spec = appliedLoraSpec() || currentLoraSpec();
    const el = $("lora-hint");
    if (!el) return;
    if (!spec || !spec.file) {
      el.textContent = "Varsayılan: 20 step · res_multistep · süre chip’ten";
      return;
    }
    const dur = state.duration || 5;
    if (!state.loraApplied || spec.id !== state.loraId) {
      el.textContent = `${spec.label} seçili — Uygula. Süre ${dur}sn chip’te kalır.`;
      return;
    }
    if (spec.preset === false) {
      const graphs = spec.graphs || [];
      const flOnly = graphs.length && !graphs.includes("ref2va");
      const extra = flOnly ? " · Ref/yüz’de atlanır" : "";
      el.textContent = `${spec.hint || "Klasörden"} · uygulandı · süre ${dur}sn chip’ten${extra}`;
      return;
    }
    const ready = spec.ready ? "uygulandı" : "dosya yok — Uygula indirir (~2GB)";
    const st = spec.steps ? `${spec.steps} step` : "step aynı";
    el.textContent = `${spec.label} · ${ready} · ${st} · süre ${dur}sn (chip)`;
  }

  async function loadLoras() {
    try {
      const data = await fetch("/api/loras").then((r) => r.json());
      state.loraCatalog = data.loras || [];
      fillLoraSelect();
    } catch {
      /* until Studio restart */
    }
  }

  async function applyLora() {
    const spec = currentLoraSpec();
    state.loraId = spec?.id || "";
    if (!spec || !spec.file) {
      state.loraApplied = false;
      if ($("steps")) $("steps").value = "20";
      if ($("sampler")) $("sampler").value = "res_multistep";
      if ($("scheduler")) $("scheduler").value = "simple";
      state.loraStrength = 1;
      updateLoraHint();
      toast("LoRA kapatıldı · 20 step · süre chip aynı");
      return;
    }
    if (!spec.ready) {
      toast("LoRA indiriliyor (~2GB)…");
      try {
        const r = await fetch("/api/loras/download", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: spec.id }),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errDetail(data));
        if (!data.ready) {
          let ready = false;
          for (let i = 0; i < 600; i++) {
            await new Promise((res) => setTimeout(res, 2000));
            const st = await fetch("/api/loras").then((x) => x.json());
            if (st.download?.error) throw new Error(st.download.error);
            const now = (st.loras || []).find((x) => x.id === spec.id);
            if (now?.ready) {
              state.loraCatalog = st.loras || state.loraCatalog;
              fillLoraSelect();
              if ($("lora-select")) $("lora-select").value = spec.id;
              ready = true;
              break;
            }
            if (i % 5 === 0) toast("LoRA indiriliyor…");
          }
          if (!ready) {
            toast("LoRA hâlâ inmiyor — Pinokio → Download Models");
            return;
          }
        }
      } catch (e) {
        toast(String(e.message || e));
        return;
      }
    }
    if (spec.preset && spec.steps) {
      if ($("steps")) $("steps").value = String(spec.steps);
      const samp = $("sampler");
      if (samp && spec.sampler) {
        if (![...samp.options].some((o) => o.value === spec.sampler)) {
          const opt = document.createElement("option");
          opt.value = spec.sampler;
          opt.textContent = spec.sampler;
          samp.appendChild(opt);
        }
        samp.value = spec.sampler;
      }
      if ($("scheduler") && spec.scheduler) $("scheduler").value = spec.scheduler;
      toast(`LoRA uygulandı · ${spec.steps} step · ${spec.sampler} · süre ${state.duration}sn chip’ten`);
    } else {
      toast(`LoRA uygulandı · ${spec.label} · strength ${spec.strength} · süre ${state.duration}sn chip’ten`);
    }
    state.loraApplied = true;
    state.loraStrength = spec.strength;
    if ($("lora-select")) $("lora-select").value = spec.id;
    updateLoraHint();
  }

  async function uploadLoraFile(file) {
    if (!file) return;
    if (!/\.safetensors$/i.test(file.name || "")) {
      toast("Sadece .safetensors");
      return;
    }
    toast(`LoRA yükleniyor · ${file.name}`);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await fetch("/api/loras/upload", { method: "POST", body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      state.loraCatalog = data.loras || state.loraCatalog;
      fillLoraSelect();
      const id = data.id || `file:${data.file}`;
      if ($("lora-select")) $("lora-select").value = id;
      state.loraId = id;
      updateLoraHint();
      toast("LoRA eklendi — Uygula’ya bas");
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  $("lora-select")?.addEventListener("change", updateLoraHint);
  $("btn-lora-apply")?.addEventListener("click", () => void applyLora());
  $("lora-file")?.addEventListener("change", (e) => {
    syncFilePickName(e.target);
    const f = e.target.files && e.target.files[0];
    if (f) void uploadLoraFile(f);
    e.target.value = "";
  });

  function setDirectorTab(mode) {
    const m = mode === "bible" ? "bible" : mode === "plan" ? "plan" : "chat";
    state.directorTab = m;
    document.querySelectorAll("#director-mode-tabs .chip").forEach((b) => {
      b.classList.toggle("on", b.dataset.dirmode === m);
    });
    $("director-bible")?.classList.toggle("hidden", m !== "bible");
    $("director-plan")?.classList.toggle("hidden", m !== "plan");
    $("director-log")?.classList.toggle("hidden", m === "bible");
    $("director-input")?.classList.toggle("hidden", m === "bible");
    $("director-music")?.classList.toggle("hidden", m !== "chat");
    if (m === "plan") {
      setDirectorOpen(true);
      if (directorSizeIndex() < 2) setDirectorSize(2);
      renderDirectorPlanBoard();
    }
  }
  document.querySelectorAll("#director-mode-tabs .chip").forEach((btn) => {
    btn.addEventListener("click", () => setDirectorTab(btn.dataset.dirmode));
  });
  $("btn-plan-save")?.addEventListener("click", () => void saveDirectorPlan(false));
  $("btn-plan-to-cinema")?.addEventListener("click", () => void saveDirectorPlan(true));
  $("btn-plan-queue")?.addEventListener("click", async () => {
    await saveDirectorPlan(false);
    void applyBrief(true);
  });
  $("btn-bible-generate")?.addEventListener("click", async () => {
    const chars = ($("bible-characters")?.value || "")
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((line) => {
        const parts = line.split("|").map((x) => x.trim());
        return {
          role: parts[0] || "character",
          name: parts[1] || "",
          card: parts.slice(2).join(" | ") || parts[0] || "",
        };
      });
    const locations = ($("bible-locations")?.value || "")
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((name, i) => ({ id: `loc${i + 1}`, name, card: name }));
    const bible = {
      mode: "director",
      genre: $("bible-genre")?.value || "short_film",
      visualStyle: $("bible-style")?.value || state.projectStyle || "realistic",
      totalSeconds: Number($("bible-total")?.value) || 30,
      clipSeconds: Number($("bible-clip")?.value) || 5,
      logline: $("bible-logline")?.value || "",
      tone: ($("bible-tone")?.value || "")
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
      forbidden: ($("bible-forbidden")?.value || "")
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
      characters: chars,
      locations,
    };
    try {
      toast("Direktör brief üretiliyor…");
      const r = await fetch("/api/director/bible/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.directorSessionId,
          bible,
          clip_duration: bible.clipSeconds,
          purpose: bible.genre,
          visual_style: bible.visualStyle,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (data.session_id) state.directorSessionId = data.session_id;
      if (typeof syncDirectorBriefFromResponse === "function") {
        syncDirectorBriefFromResponse(data);
      } else if (data.brief) {
        state.directorBrief = data.brief;
      }
      state.directorReady = !!data.ready || !!(data.brief && data.brief.shots?.length);
      if (data.messages) renderDirectorMessages(data.messages);
      const n = state.directorBrief?.shots?.length || data.shot_count || 0;
      if (typeof setDirectorReadyUi === "function") setDirectorReadyUi(state.directorReady, n);
      setDirectorTab("plan");
      toast(
        state.directorReady
          ? `Direktör brief hazır · ${n} shot — Üretime al`
          : (data.reply || "Brief için sohbete bak").slice(0, 120)
      );
    } catch (e) {
      toast(String(e.message || e));
    }
  });

  document.querySelectorAll("#mode-chips .chip").forEach((btn) => {
    btn.addEventListener("click", () => setProduceMode(btn.dataset.mode));
  });
  document
    .querySelectorAll("#dur-chips .chip, #dur-chips-cont .chip, #dur-chips-story .chip")
    .forEach((btn) => {
      btn.addEventListener("click", () => setDuration(btn.dataset.dur));
    });
  document.querySelectorAll("#quality-chips .chip, #quality-chips-cont .chip").forEach((btn) => {
    btn.addEventListener("click", () => setQuality(btn.dataset.q));
  });
  document.querySelectorAll("#aspect-chips .chip").forEach((btn) => {
    btn.addEventListener("click", () => setAspect(btn.dataset.aspect));
  });
  document.querySelectorAll("#ref-size-chips .chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.refImageSize = btn.dataset.refsize || "match";
      document.querySelectorAll("#ref-size-chips .chip").forEach((b) => {
        b.classList.toggle("on", b.dataset.refsize === state.refImageSize);
      });
    });
  });
  $("ref-files")?.addEventListener("change", (e) => {
    syncFilePickName(e.target);
    void uploadRefFiles(e.target.files, "ref");
    e.target.value = "";
  });
  $("face-files")?.addEventListener("change", (e) => {
    syncFilePickName(e.target);
    void uploadRefFiles(e.target.files, "face");
    e.target.value = "";
  });
  $("v2v-video-files")?.addEventListener("change", (e) => {
    syncFilePickName(e.target);
    void uploadVideoFiles(e.target.files, state.v2vVideos, "v2v-video-thumbs");
    e.target.value = "";
  });
  $("v2v-image-files")?.addEventListener("change", (e) => {
    syncFilePickName(e.target);
    void uploadImageToList(
      e.target.files,
      state.v2vImages,
      "v2v-image-thumbs",
      9,
      (i) => `Picture ${i + 1}`
    );
    e.target.value = "";
  });
  $("btn-open-cinema")?.addEventListener("click", () => void openCinemaStudio());
  $("btn-cinema")?.addEventListener("click", () => {
    setProduceMode("cinema");
    void openCinemaStudio();
  });
  $("btn-cinema-close")?.addEventListener("click", () => closeCinemaStudio());
  $("view-cinema")?.addEventListener("click", (e) => {
    if (e.target === $("view-cinema")) closeCinemaStudio();
  });
  $("btn-cinema-add-char")?.addEventListener("click", () => void addCinemaAsset("character"));
  $("btn-cinema-add-loc")?.addEventListener("click", () => void addCinemaAsset("location"));
  $("view-cinema")?.addEventListener("click", (e) => {
    const toggle = e.target.closest(".cinema-fold-toggle");
    if (!toggle) return;
    const key = toggle.dataset.fold;
    if (key !== "characters" && key !== "locations") return;
    e.preventDefault();
    setCinemaFold(key, cinemaFoldState()[key] === false);
  });
  $("btn-cinema-add-t2v")?.addEventListener("click", () => addCinemaShot("t2v"));
  $("btn-cinema-add-cont")?.addEventListener("click", () => addCinemaShot("continue"));
  $("btn-cinema-save")?.addEventListener("click", () => void saveCinema(false));
  $("btn-cinema-produce")?.addEventListener("click", () => void produceCinema());
  $("cinema-title")?.addEventListener("change", () => {
    ensureCinema().title = $("cinema-title").value;
    void saveCinema(true);
  });
  $("cinema-duration")?.addEventListener("change", () => {
    ensureCinema().duration = Number($("cinema-duration").value) || 5;
    void saveCinema(true);
  });
  $("cinema-steps")?.addEventListener("change", () => {
    ensureCinema().steps = Number($("cinema-steps").value) || 20;
    void saveCinema(true);
  });
  $("cinema-quality-chips")?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-quality]");
    if (!btn) return;
    ensureCinema().quality = btn.dataset.quality;
    renderCinemaKnobs();
    void saveCinema(true);
  });
  $("cinema-audio-mode")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-audio]");
    if (!btn) return;
    cinemaAudio().mode = btn.dataset.audio === "silent" ? "silent" : "film";
    renderCinemaAudio();
    void saveCinema(true);
  });
  $("cinema-score-file")?.addEventListener("change", (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    void uploadCinemaScore(f);
  });
  $("btn-cinema-mux")?.addEventListener("click", () => void muxCinemaScore());
  $("cinema-pills")?.addEventListener("click", (e) => {
    const option = e.target.closest(".film-pill-option");
    const pill = e.target.closest(".film-pill");
    if (option && pill) {
      e.stopPropagation();
      const key = pill.dataset.setup;
      const id = option.dataset.id || "auto";
      ensureCinema().setup[key] = id;
      pill.classList.remove("open");
      renderCinemaPills();
      void saveCinema(true);
      return;
    }
    if (pill) {
      e.stopPropagation();
      const open = pill.classList.contains("open");
      $("cinema-pills")
        .querySelectorAll(".film-pill")
        .forEach((el) => el.classList.remove("open"));
      if (!open) pill.classList.add("open");
    }
  });
  document.addEventListener("click", (e) => {
    if (e.target.closest(".film-pill") || e.target.closest("#cinema-pills")) return;
    $("cinema-pills")
      ?.querySelectorAll(".film-pill.open")
      .forEach((el) => el.classList.remove("open"));
  });
  $("cinema-shots")?.addEventListener("change", (e) => {
    const card = e.target.closest(".cinema-shot");
    if (!card) return;
    const shot = cinemaShotById(card.dataset.id);
    if (!shot) return;
    if (e.target.dataset.field === "text") {
      shot.text = e.target.value;
      void saveCinema(true);
    }
  });
  $("cinema-shots")?.addEventListener("click", (e) => {
    const card = e.target.closest(".cinema-shot");
    if (!card) return;
    const shot = cinemaShotById(card.dataset.id);
    if (!shot) return;
    const del = e.target.closest(".cinema-shot-del");
    if (del) {
      ensureCinema().shots = (ensureCinema().shots || []).filter((s) => s.id !== card.dataset.id);
      renderCinemaShots();
      renderCinema();
      void saveCinema(true);
      return;
    }
    const modeBtn = e.target.closest("[data-mode]");
    if (modeBtn) {
      shot.mode = modeBtn.dataset.mode === "continue" ? "continue" : "t2v";
      renderCinemaShots();
      void saveCinema(true);
    }
  });
  const cinemaDelegate = (rootId, kind) => {
    $(rootId)?.addEventListener("change", (e) => {
      const card = e.target.closest(".cinema-card");
      if (!card) return;
      const id = card.dataset.id;
      if (e.target.classList.contains("cinema-img")) {
        const f = e.target.files && e.target.files[0];
        e.target.value = "";
        void uploadCinemaImage(kind, id, f);
        return;
      }
      const field = e.target.dataset.field;
      if (!field) return;
      void patchCinemaAsset(kind, id, { [field]: e.target.value });
    });
    $(rootId)?.addEventListener("click", (e) => {
      const del = e.target.closest(".cinema-del");
      if (!del) return;
      const card = del.closest(".cinema-card");
      if (!card) return;
      const id = card.dataset.id;
      if (!confirm("Bu kartı sil?")) return;
      const path =
        kind === "character" ? `/api/cinema/character/${id}` : `/api/cinema/location/${id}`;
      void fetch(path, { method: "DELETE" }).then(() => loadCinema());
    });
  };
  cinemaDelegate("cinema-chars", "character");
  cinemaDelegate("cinema-locs", "location");
  $("first-frame-file")?.addEventListener("change", (e) => {
    syncFilePickName(e.target);
    const f = e.target.files && e.target.files[0];
    void uploadSingleFrame(f, "first");
    e.target.value = "";
  });
  $("last-frame-file")?.addEventListener("change", (e) => {
    syncFilePickName(e.target);
    const f = e.target.files && e.target.files[0];
    void uploadSingleFrame(f, "last");
    e.target.value = "";
  });
  $("continue-source")?.addEventListener("change", () => {
    const id = $("continue-source").value;
    if (id) void setContinueMode(id);
    else clearContinueMode();
  });
  $("btn-player-close")?.addEventListener("click", () => clearPlayer());
  $("btn-open-prompt")?.addEventListener("click", () => openPromptView());
  $("btn-clip-prompt-close")?.addEventListener("click", () => closePromptView());
  $("view-clip-prompt")?.addEventListener("click", (e) => {
    if (e.target === $("view-clip-prompt")) closePromptView();
  });
  $("btn-copy-prompt")?.addEventListener("click", () => void copyText(state.clipPrompt));
  $("btn-use-prompt")?.addEventListener("click", () => {
    const t = (state.clipPrompt || "").trim();
    if (!t) {
      toast("Prompt yok");
      return;
    }
    const ta = $("prompt");
    if (ta) ta.value = t;
    closePromptView();
    toast("Prompt sahneye alındı");
  });
  $("btn-use-in-continue")?.addEventListener("click", async () => {
    const id = state.selectedJobId || $("continue-source")?.value || "";
    if (!id) {
      toast("Önce galeriden veya player’dan bir video seç");
      return;
    }
    const job =
      findContinueJob(id) ||
      (state.galleryItems || []).find((x) => x.id === id) ||
      { id, status: "done", url: `/api/gallery/${id}/video` };
    await useClipAsContinue(job);
  });

  $("btn-batch-add")?.addEventListener("click", () => addPromptFromScene());
  $("prompt")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      addPromptFromScene();
    }
  });
  $("btn-batch-clear")?.addEventListener("click", () => {
    state.queueItems = [];
    renderQueue();
    toast("Liste temizlendi");
  });

  $("btn-batch")?.addEventListener("click", async () => {
    const lines = state.queueItems.map((x) => x.text.trim()).filter(Boolean);
    if (!lines.length) {
      toast("Önce Prompt / Sahne’den Sıraya ekle");
      return;
    }
    state.queueItems.forEach((item, i) => {
      const ta = $("batch-list")?.querySelectorAll("textarea")[i];
      if (ta) item.text = ta.value;
    });
    const prompts = state.queueItems.map((x) => x.text.trim()).filter(Boolean);
    const tip = chainTipJob();
    const faceLockOn = !!$("face-lock-chain")?.checked && state.faceImages.length > 0;
    try {
      const payload = {
        prompts: prompts.map(withStyleLock),
        duration: state.duration,
        aspect: state.aspect || "16:9",
        quality: state.quality,
        link_continue: true,
        append_to_chain: true,
        face_lock: true,
        seed: numOr("seed", -1),
        purpose: state.projectPurpose || null,
        silent_audio: state.projectSilent || state.projectPurpose === "music_video",
        music_id: state.projectPurpose === "music_video" ? state.musicId : null,
        ...collectGenerateKnobs(),
      };
      if (faceLockOn) {
        payload.ref_images = state.faceImages.map((x) => x.name);
        payload.ref_image_size = "max";
        payload.ref_role = "face";
      }
      const r = await fetch("/api/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(errDetail(data));
      toast(
        faceLockOn
          ? `${data.count} iş sıraya + yüz kilidi`
          : tip
            ? `${data.count} iş sıraya eklendi (önceki son kareden continue)`
            : data.count > 1
              ? `${data.count} iş: 1 yeni → 2–${data.count} continue`
              : `${data.count} iş kuyrukta`
      );
      setDirectorOpen(false);
      await refreshJobs();
    } catch (e) {
      toast(String(e.message || e));
    }
  });

  $("btn-stop").onclick = async () => {
    try {
      // Only stop the running clip — keep the rest of the batch queued
      await fetch("/api/interrupt", { method: "POST" });
      toast("Durduruldu");
      // If nothing was running, clear sticky bar immediately
      const hadRunning = state.jobs.some((j) => j.status === "running");
      if (!hadRunning && !state.jobs.some((j) => j.status === "queued")) {
        hideProgressNow();
        toast("Hazır");
      }
      await refreshJobs();
    } catch (e) {
      toast(String(e.message || e));
    }
  };

  async function deleteJob(jobId) {
    try {
      const r = await fetch(`/api/jobs/${jobId}?delete_files=true`, { method: "DELETE" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (state.selectedJobId === jobId) {
        clearPlayer();
      }
      if (state.continueFrom === jobId) clearContinueMode();
      toast("Kayıt silindi");
      await refreshJobs();
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function clearJobs(scope) {
    const labels = {
      errors: "hatalı / iptal kayıtları",
      finished: "bitmiş + hatalı geçmişi",
      done: "başarılı klipleri",
    };
    if (!confirm(`${labels[scope] || scope} silinsin mi?`)) return;
    try {
      const r = await fetch("/api/jobs/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope, delete_files: true }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      toast(data.removed ? `${data.removed} kayıt temizlendi` : "Silinecek kayıt yok");
      if (!state.jobs.some((j) => j.status === "running" || j.status === "queued")) {
        hideProgressNow();
      }
      await refreshJobs();
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  $("btn-clear-errors").onclick = () => clearJobs("errors");
  $("btn-clear-finished").onclick = () => clearJobs("finished");


  $("btn-reset-production")?.addEventListener("click", async () => {
    if (
      !confirm(
        "Temiz başlat: kuyruk, çalışma klipleri ve last-frame dosyaları silinecek.\nGaleri arşivi ve yönetmen sohbeti kalır. Devam?"
      )
    ) {
      return;
    }
    try {
      const r = await fetch("/api/reset-production", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wipe_logs: false }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      state.queueItems = [];
      renderQueue();
      clearPlayer();
      hideProgressNow();
      toast("Sıfırlandı — temizden üretebilirsin");
      await refreshJobs();
    } catch (e) {
      toast(String(e.message || e));
    }
  });

  $("btn-open-logs")?.addEventListener("click", async () => {
    try {
      const r = await fetch("/api/logs?which=latest&lines=180");
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      const w = window.open("", "h3-studio-logs", "width=900,height=640");
      if (!w) {
        toast(data.file || "Log açılamadı (popup engeli?)");
        return;
      }
      const esc = (s) =>
        String(s || "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;");
      w.document.write(
        `<!doctype html><title>H3 Studio Logs</title>
        <style>body{margin:0;background:#140f0c;color:#f2e6d8;font:12px/1.45 ui-monospace,Consolas,monospace}
        header{padding:10px 14px;border-bottom:1px solid #3a2e24;color:#c4a574}
        pre{margin:0;padding:14px;white-space:pre-wrap;word-break:break-word}</style>
        <header>${esc(data.file)} · son ${esc(data.lines)} satır · errors için /api/logs?which=errors</header>
        <pre>${esc(data.text) || "(boş — henüz log yok, Studio’yu yeniden başlat)"}</pre>`
      );
      w.document.close();
    } catch (e) {
      toast(String(e.message || e));
    }
  });

  $("btn-director-send").onclick = () => directorSend($("director-msg").value);
  $("director-msg").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      directorSend($("director-msg").value);
    }
    // Shift+Enter → new line (default textarea behavior)
  });
  $("director-msg").addEventListener("focus", () => setDirectorOpen(true));
  $("director-msg").addEventListener("input", () => {
    if (($("director-msg").value || "").trim()) setDirectorOpen(true);
  });
  document.querySelectorAll("#director-chips .chip").forEach((btn) => {
    btn.addEventListener("click", () => selectProjectChip(btn));
  });
  document.querySelectorAll("#scene-purpose-chips .chip, #scene-style-chips .chip").forEach((btn) => {
    btn.addEventListener("click", () => selectProjectChip(btn, { fromScene: true }));
  });
  syncProjectChips();
  $("llm-provider")?.addEventListener("change", () => {
    if ($("llm-provider")) $("llm-provider").dataset.userTouched = "1";
    const prov = $("llm-provider").value;
    if ($("llm-provider-settings")) $("llm-provider-settings").value = prov;
    syncLlmSettingsUi({ provider: prov }, { provider: prov });
  });
  $("llm-provider-settings")?.addEventListener("change", () => {
    if ($("llm-provider-settings")) $("llm-provider-settings").dataset.userTouched = "1";
    const prov = $("llm-provider-settings").value;
    if ($("llm-provider")) $("llm-provider").value = prov;
    $("llm-ollama-url-wrap")?.classList.toggle("hidden", prov !== "ollama");
    syncLlmSettingsUi({ provider: prov }, { provider: prov });
  });
  $("llm-ollama-url")?.addEventListener("input", () => {
    if ($("llm-ollama-url")) $("llm-ollama-url").dataset.dirty = "1";
  });
  const KEY_TO_PROVIDER = {
    "llm-openai-key": "openai",
    "llm-gemini-key": "gemini",
    "llm-grok-key": "grok",
    "llm-claude-key": "claude",
  };
  for (const f of LLM_KEY_FIELDS) {
    $(f.id)?.addEventListener("input", () => {
      const el = $(f.id);
      if (el) el.dataset.dirty = "1";
      // Key yapıştırınca o sağlayıcıyı otomatik seç (Ollama’da kalıp “bağlanamadım” olmasın)
      const prov = KEY_TO_PROVIDER[f.id];
      if (prov && el && el.value.trim()) {
        if ($("llm-provider-settings")) {
          $("llm-provider-settings").value = prov;
          $("llm-provider-settings").dataset.userTouched = "1";
        }
        if ($("llm-provider")) {
          $("llm-provider").value = prov;
          $("llm-provider").dataset.userTouched = "1";
        }
        $("llm-ollama-url-wrap")?.classList.toggle("hidden", true);
        syncLlmSettingsUi({ provider: prov }, { provider: prov });
      }
    });
  }
  $("btn-llm-save")?.addEventListener("click", () => saveLlmSettings());
  $("btn-llm-provider-save")?.addEventListener("click", () => saveLlmProviderOnly());

  function syncNotifyProviderUi() {
    const prov = ($("notify-provider")?.value || "telegram").toLowerCase();
    $("notify-telegram-wrap")?.classList.toggle("hidden", prov !== "telegram");
    $("notify-ntfy-wrap")?.classList.toggle("hidden", prov !== "ntfy");
  }

  function fillNotifySettings(s) {
    if (!s) return;
    if ($("notify-enabled")) $("notify-enabled").checked = !!s.enabled;
    if ($("notify-provider")) $("notify-provider").value = s.provider || "telegram";
    if ($("notify-tg-chat")) $("notify-tg-chat").value = s.telegram_chat_id || "";
    if ($("notify-tg-token")) {
      $("notify-tg-token").value = "";
      $("notify-tg-token").placeholder = s.telegram_bot_token_masked
        ? `kayıtlı: ${s.telegram_bot_token_masked}`
        : "AkiFactory’den aktar veya yapıştır";
    }
    if ($("notify-tg-token-hint")) {
      $("notify-tg-token-hint").textContent = s.telegram_configured
        ? `Hazır · chat ${s.telegram_chat_id || "?"}${s.telegram_bot_username ? ` · @${s.telegram_bot_username}` : ""}`
        : "Boş bırakırsan kayıtlı token korunur";
    }
    if ($("notify-server")) $("notify-server").value = s.ntfy_server || "https://ntfy.sh";
    if ($("notify-topic")) $("notify-topic").value = s.ntfy_topic || "";
    if ($("notify-batch-done")) $("notify-batch-done").checked = s.on_batch_done !== false;
    if ($("notify-each-clip")) $("notify-each-clip").checked = !!s.on_each_clip;
    if ($("notify-error")) $("notify-error").checked = s.on_error !== false;
    const hint = $("notify-subscribe-hint");
    if (hint) {
      hint.textContent = s.subscribe_url
        ? `Telefonda abone ol: ${s.subscribe_url}`
        : "Abone URL kayıttan sonra";
    }
    const sh = $("notify-settings-hint");
    if (sh) {
      if (!s.enabled) sh.textContent = "Kapalı";
      else if ((s.provider || "telegram") === "telegram") {
        sh.textContent = s.telegram_configured
          ? `Telegram açık · Test mesajı gönder`
          : "Telegram eksik — AkiFactory’den aktar";
      } else {
        sh.textContent = s.subscribe_url ? `ntfy · ${s.subscribe_url}` : "ntfy konu kaydet";
      }
    }
    syncNotifyProviderUi();
  }

  async function refreshNotifySettings() {
    try {
      const s = await fetch("/api/notify/settings").then((r) => r.json());
      fillNotifySettings(s);
    } catch {
      /* ignore until Studio restart */
    }
  }

  async function saveNotifySettings({ quiet = false } = {}) {
    try {
      const body = {
        enabled: !!$("notify-enabled")?.checked,
        provider: ($("notify-provider")?.value || "telegram").trim(),
        telegram_chat_id: ($("notify-tg-chat")?.value || "").trim(),
        ntfy_server: ($("notify-server")?.value || "").trim() || "https://ntfy.sh",
        ntfy_topic: ($("notify-topic")?.value || "").trim(),
        on_batch_done: !!$("notify-batch-done")?.checked,
        on_each_clip: !!$("notify-each-clip")?.checked,
        on_error: !!$("notify-error")?.checked,
      };
      const tok = ($("notify-tg-token")?.value || "").trim();
      if (tok) body.telegram_bot_token = tok;
      const r = await fetch("/api/notify/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      fillNotifySettings(data);
      if (quiet) {
        const sh = $("notify-settings-hint");
        if (sh) sh.textContent = "Bildirim ayarları kaydedildi";
      } else {
        toast("Bildirim ayarları kaydedildi");
      }
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  let _notifyAutosaveTimer = null;
  function scheduleNotifyAutosave() {
    if (_notifyAutosaveTimer) clearTimeout(_notifyAutosaveTimer);
    _notifyAutosaveTimer = setTimeout(() => {
      _notifyAutosaveTimer = null;
      void saveNotifySettings({ quiet: true });
    }, 280);
  }

  async function importNotifyAki() {
    try {
      const r = await fetch("/api/notify/import-akifactory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: "C:\\\\Users\\\\ERDIN\\\\Desktop\\\\AkiFactory\\\\data\\\\telegram.json",
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      fillNotifySettings(data);
      toast("AkiFactory Telegram aktarıldı");
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function testNotify() {
    try {
      await saveNotifySettings();
      const r = await fetch("/api/notify/test", { method: "POST" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      toast("Test mesajı gönderildi — Telegram’a bak");
      if ($("notify-settings-hint")) {
        $("notify-settings-hint").textContent =
          "Test gitti — gelmediyse bota /start yazıp chat id kontrol et";
      }
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  $("notify-provider")?.addEventListener("change", () => {
    syncNotifyProviderUi();
    scheduleNotifyAutosave();
  });
  [
    "notify-enabled",
    "notify-batch-done",
    "notify-each-clip",
    "notify-error",
  ].forEach((id) => {
    $(id)?.addEventListener("change", () => scheduleNotifyAutosave());
  });
  ["notify-tg-chat", "notify-tg-token", "notify-server", "notify-topic"].forEach((id) => {
    $(id)?.addEventListener("change", () => scheduleNotifyAutosave());
  });
  $("btn-notify-save")?.addEventListener("click", () => saveNotifySettings());
  $("btn-notify-test")?.addEventListener("click", () => testNotify());
  $("btn-notify-import-aki")?.addEventListener("click", () => importNotifyAki());
  $("btn-queue-brief")?.addEventListener("click", () => applyBrief(true));

  $("music-file")?.addEventListener("change", (e) => {
    syncFilePickName(e.target);
    const f = e.target.files && e.target.files[0];
    if (f) uploadMusicFile(f);
  });
  $("btn-music-analyze")?.addEventListener("click", () => analyzeMusic());
  $("btn-music-mux")?.addEventListener("click", () => muxMusicFinal());
  $("btn-gallery")?.addEventListener("click", () => {
    $("view-settings")?.classList.add("hidden");
    $("view-support")?.classList.add("hidden");
    $("view-cinema")?.classList.add("hidden");
    $("view-gallery")?.classList.remove("hidden");
    void renderGallery();
  });
  $("btn-gallery-close")?.addEventListener("click", () => $("view-gallery")?.classList.add("hidden"));
  $("btn-settings")?.addEventListener("click", () => {
    $("view-gallery")?.classList.add("hidden");
    $("view-support")?.classList.add("hidden");
    $("view-cinema")?.classList.add("hidden");
    $("view-settings")?.classList.remove("hidden");
    void refreshDirectorStatus();
    void refreshNotifySettings();
  });
  $("btn-settings-close")?.addEventListener("click", () => {
    void saveNotifySettings({ quiet: true });
    $("view-settings")?.classList.add("hidden");
  });
  const SUPPORT_REPO = "https://github.com/erdinoral/minimax-h3-studio";
  $("btn-support")?.addEventListener("click", () => {
    $("view-gallery")?.classList.add("hidden");
    $("view-settings")?.classList.add("hidden");
    $("view-cinema")?.classList.add("hidden");
    $("view-support")?.classList.remove("hidden");
  });
  $("btn-support-close")?.addEventListener("click", () => $("view-support")?.classList.add("hidden"));
  $("btn-support-bug")?.addEventListener("click", () => {
    window.open(SUPPORT_REPO + "/issues/new?template=bug.md", "_blank", "noopener");
  });
  $("btn-support-idea")?.addEventListener("click", () => {
    window.open(SUPPORT_REPO + "/issues/new?template=feature.md", "_blank", "noopener");
  });

  /* —— Layout edit (handles only; never stops production) —— */
  const LAYOUT_KEY = "h3_layout_v8";
  /* scene|player / prompt|ayar|prod */
  const LAYOUT_DEFAULTS = {
    colLeft: 28,
    drawerAyar: 22,
    gap: 10,
    fontScale: 100,
    promptH: 64,
    sceneH: 420,
    batchH: 100,
    batchListH: 120,
    queueH: 120,
    playerH: 280,
    prodH: 400,
    ayarH: 400,
  };
  const LAYOUT_BOUNDS = {
    colLeft: [20, 40],
    drawerAyar: [16, 36],
    gap: [6, 16],
    fontScale: [90, 120],
    promptH: [48, 140],
    sceneH: [200, 900],
    batchH: [72, 240],
    batchListH: [72, 280],
    queueH: [80, 240],
    playerH: [180, 520],
    prodH: [240, 720],
    ayarH: [240, 720],
  };
  let layoutState = { ...LAYOUT_DEFAULTS };
  let layoutEditOn = false;

  function clamp(n, lo, hi) {
    return Math.max(lo, Math.min(hi, Number(n) || lo));
  }

  function applyLayout(prefs) {
    const merged = { ...LAYOUT_DEFAULTS, ...(prefs || {}) };
    if (!merged.prodH || merged.prodH < 280) merged.prodH = LAYOUT_DEFAULTS.prodH;
    // Ayarlar + Üretim aynı satır yüksekliği (çakışma/kesilme olmasın)
    merged.ayarH = merged.prodH;
    if (!merged.promptH || merged.promptH < 56 || merged.promptH > 160) {
      merged.promptH = LAYOUT_DEFAULTS.promptH;
    }
    const b = LAYOUT_BOUNDS;
    const n = (k) => clamp(merged[k], b[k][0], b[k][1]);
    const rowH = n("prodH");
    layoutState = {
      colLeft: n("colLeft"),
      drawerAyar: n("drawerAyar"),
      gap: n("gap"),
      fontScale: n("fontScale"),
      promptH: n("promptH"),
      sceneH: n("sceneH"),
      batchH: n("batchH"),
      batchListH: n("batchListH"),
      queueH: n("queueH"),
      playerH: n("playerH"),
      prodH: rowH,
      ayarH: rowH,
    };
    const root = document.documentElement;
    root.style.setProperty("--layout-col-left", `${layoutState.colLeft}%`);
    root.style.setProperty("--layout-ayar-w", `${layoutState.drawerAyar}%`);
    root.style.setProperty("--layout-gap", `${layoutState.gap}px`);
    root.style.setProperty("--layout-font-scale", String(layoutState.fontScale / 100));
    root.style.setProperty("--layout-prompt-h", `${layoutState.promptH}px`);
    root.style.setProperty("--layout-scene-h", "auto");
    root.style.setProperty("--layout-batch-h", `${layoutState.batchH}px`);
    root.style.setProperty("--layout-batch-list-h", `${layoutState.batchListH}px`);
    root.style.setProperty("--layout-queue-h", `${layoutState.queueH}px`);
    root.style.setProperty("--layout-player-h", `${layoutState.playerH}px`);
    const map = {
      "layout-col-left": "colLeft",
      "layout-drawer-ayar": "drawerAyar",
      "layout-gap": "gap",
      "layout-font": "fontScale",
      "layout-prompt-h": "promptH",
      "layout-scene-h": "sceneH",
      "layout-batch-h": "batchH",
      "layout-batch-list-h": "batchListH",
      "layout-queue-h": "queueH",
      "layout-player-h": "playerH",
      "layout-prod-h": "prodH",
      "layout-ayar-h": "ayarH",
    };
    for (const [id, key] of Object.entries(map)) {
      const el = $(id);
      if (el && document.activeElement !== el) el.value = String(Math.round(layoutState[key]));
    }
  }

  function loadLayoutPrefs() {
    try {
      // Prefer clean v3; ignore broken nested v1/v2 if values look insane
      const raw = localStorage.getItem(LAYOUT_KEY);
      if (raw) {
        applyLayout(JSON.parse(raw));
        return;
      }
      applyLayout(LAYOUT_DEFAULTS);
    } catch {
      applyLayout(LAYOUT_DEFAULTS);
    }
  }

  function saveLayoutPrefs(quiet) {
    try {
      localStorage.setItem(LAYOUT_KEY, JSON.stringify(layoutState));
      localStorage.removeItem("h3_layout_v1");
      localStorage.removeItem("h3_layout_v2");
      localStorage.removeItem("h3_layout_v3");
      localStorage.removeItem("h3_layout_v4");
      localStorage.removeItem("h3_layout_v5");
      localStorage.removeItem("h3_layout_v6");
      localStorage.removeItem("h3_layout_v7");
      if (!quiet) toast("Arayüz kaydedildi · üretim devam ediyor");
    } catch (e) {
      if (!quiet) toast(String(e.message || e));
    }
  }

  function setLayoutEditMode(on) {
    layoutEditOn = !!on;
    document.body.classList.toggle("layout-editing", layoutEditOn);
    $("layout-edit-bar")?.classList.toggle("hidden", !layoutEditOn);
    const btn = $("btn-layout-edit");
    if (btn) btn.textContent = layoutEditOn ? "Düzenle · açık" : "Düzenle";
    if (layoutEditOn) applyLayout(layoutState);
  }

  function readLayoutInputs() {
    const num = (id, fallback) => {
      const v = Number($(id)?.value);
      return Number.isFinite(v) ? v : fallback;
    };
    applyLayout({
      colLeft: num("layout-col-left", layoutState.colLeft),
      drawerAyar: num("layout-drawer-ayar", layoutState.drawerAyar),
      gap: num("layout-gap", layoutState.gap),
      fontScale: num("layout-font", layoutState.fontScale),
      promptH: num("layout-prompt-h", layoutState.promptH),
      sceneH: num("layout-scene-h", layoutState.sceneH),
      batchH: num("layout-batch-h", layoutState.batchH),
      batchListH: num("layout-batch-list-h", layoutState.batchListH),
      queueH: num("layout-queue-h", layoutState.queueH),
      playerH: num("layout-player-h", layoutState.playerH),
      prodH: num("layout-prod-h", layoutState.prodH),
      ayarH: num("layout-ayar-h", layoutState.ayarH),
    });
  }

  document.querySelectorAll("#layout-edit-bar input").forEach((el) => {
    el.addEventListener("input", () => {
      if (!layoutEditOn) return;
      readLayoutInputs();
    });
  });

  $("btn-layout-edit")?.addEventListener("click", () => setLayoutEditMode(!layoutEditOn));
  $("btn-layout-done")?.addEventListener("click", () => {
    saveLayoutPrefs(true);
    setLayoutEditMode(false);
    toast("Düzenleme kapandı · kaydedildi");
  });
  $("btn-layout-save")?.addEventListener("click", () => {
    readLayoutInputs();
    saveLayoutPrefs(false);
  });
  $("btn-layout-reset")?.addEventListener("click", () => {
    try {
      localStorage.removeItem(LAYOUT_KEY);
      localStorage.removeItem("h3_layout_v1");
      localStorage.removeItem("h3_layout_v2");
      localStorage.removeItem("h3_layout_v3");
      localStorage.removeItem("h3_layout_v4");
      localStorage.removeItem("h3_layout_v5");
      localStorage.removeItem("h3_layout_v6");
      localStorage.removeItem("h3_layout_v7");
    } catch {
      /* ignore */
    }
    applyLayout(LAYOUT_DEFAULTS);
    saveLayoutPrefs(true);
    toast("Varsayılan düzen — bozulmuş kayıt temizlendi");
  });

  const HANDLE_MAP = {
    "col-left": { key: "colLeft", axis: "x", unit: "pct", ref: () => $("view-studio")?.clientWidth || window.innerWidth },
    "drawer-ayar": { key: "drawerAyar", axis: "x", unit: "pct", ref: () => $("view-studio")?.clientWidth || window.innerWidth },
    prompt: { key: "promptH", axis: "y" },
    scene: { key: "sceneH", axis: "y" },
    player: { key: "playerH", axis: "y" },
    "batch-add": { key: "batchH", axis: "y" },
    "batch-list": { key: "batchListH", axis: "y" },
    "job-queue": { key: "queueH", axis: "y" },
    "prod-h": { key: "prodH", axis: "y" },
    "ayar-h": { key: "prodH", axis: "y" }, // aynı satır yüksekliği
  };

  let drag = null;
  document.querySelectorAll(".layout-handle").forEach((handle) => {
    handle.addEventListener("mousedown", (e) => {
      if (!layoutEditOn) return;
      e.preventDefault();
      e.stopPropagation();
      const conf = HANDLE_MAP[handle.dataset.handle];
      if (!conf) return;
      drag = {
        conf,
        startX: e.clientX,
        startY: e.clientY,
        start: { ...layoutState },
      };
      document.body.classList.add("layout-dragging");
    });
  });
  window.addEventListener("mousemove", (e) => {
    if (!drag) return;
    const { conf, start, startX, startY } = drag;
    const next = { ...start };
    const [lo, hi] = LAYOUT_BOUNDS[conf.key];
    if (conf.axis === "x") {
      const refW = typeof conf.ref === "function" ? conf.ref() : 400;
      next[conf.key] = clamp(start[conf.key] + ((e.clientX - startX) / Math.max(refW, 1)) * 100, lo, hi);
    } else {
      next[conf.key] = clamp(start[conf.key] + (e.clientY - startY), lo, hi);
    }
    applyLayout(next);
  });
  window.addEventListener("mouseup", () => {
    if (!drag) return;
    drag = null;
    document.body.classList.remove("layout-dragging");
    saveLayoutPrefs(true);
  });

  // Director tabs: per-session chat state and tab UI
  state.directorSessions = state.directorSessions || [];
  state.directorSessionCounter = state.directorSessionCounter || 0;

  function directorSessionIdFrom(data) {
    return (data && (data.session_id || data.id || data.session)) || null;
  }

  function findSession(sid) {
    return state.directorSessions.find((s) => s.id === sid);
  }

  function clearDirectorSessionState() {
    state.directorBrief = null;
    state.directorReady = false;
    $("director-shot-panel")?.remove();
    setDirectorReadyUi(false);
  }

  function syncDirectorSessionFromResponse(data) {
    const sid = directorSessionIdFrom(data);
    if (!sid) return null;
    let session = findSession(sid);
    if (!session) {
      state.directorSessionCounter += 1;
      session = {
        id: sid,
        title: `Sohbet ${state.directorSessionCounter}`,
        messages: [],
      };
      state.directorSessions.push(session);
    }
    if (Array.isArray(data.messages) && data.messages.length) {
      session.messages = data.messages.slice();
    }
    if (data.brief && Array.isArray(data.brief.shots) && data.brief.shots.length) {
      state.directorBrief = data.brief;
      session.brief = data.brief;
      session.ready = !!data.ready;
    } else if (data.ready === false && !data.brief) {
      /* keep existing brief while chatting */
    } else if (data.ready) {
      session.ready = true;
    }
    state.directorSessionId = sid;
    renderDirectorTabs();
    return session;
  }

  function renderDirectorTabs() {
    const wrap = $("director-tabs");
    if (!wrap) return;
    wrap.innerHTML = "";
    state.directorSessions.forEach((s, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "dir-tab";
      if (state.directorSessionId === s.id) btn.classList.add("on");
      const label = document.createElement("span");
      label.textContent = s.title || `Sohbet ${i + 1}`;
      btn.appendChild(label);
      const close = document.createElement("button");
      close.type = "button";
      close.className = "dir-tab-close";
      close.textContent = "✕";
      close.title = "Sekmeyi kapat";
      close.onclick = (e) => {
        e.stopPropagation();
        void closeDirectorTab(s.id);
      };
      btn.onclick = () => switchDirectorTab(s.id);
      btn.appendChild(close);
      wrap.appendChild(btn);
    });
  }

  function renderDirectorMessages(messages) {
    const log = $("director-log");
    if (!log) return;
    log.innerHTML = "";
    const arr = Array.isArray(messages) ? messages : [];
    const session = findSession(state.directorSessionId);
    if (session) session.messages = arr.slice();
    arr.forEach((m) => {
      const role = m.role === "user" ? "user" : "assistant";
      const text = (m.content == null ? "" : String(m.content)).trimEnd();
      if (!text && role === "assistant") return;
      const div = document.createElement("div");
      div.className = `dir-msg ${role}`;
      const who = role === "user" ? tt("dir.you") : tt("dir.who");
      div.innerHTML = `<span class="who">${who}</span>`;
      div.appendChild(document.createTextNode(text || tt("dir.empty")));
      log.appendChild(div);
    });
    log.scrollTop = log.scrollHeight;
  }

  async function newDirectorSession() {
    if (state.directorBusy) {
      toast("Yönetmen yanıt verirken yeni sohbet açılamaz");
      return;
    }
    try {
      const r = await fetch("/api/director/session?lang=" + encodeURIComponent(uiLang()), { method: "POST" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      const sid = directorSessionIdFrom(data);
      if (!sid) throw new Error("Oturum oluşturulamadı");
      state.directorSessionCounter += 1;
      const sess = {
        id: sid,
        title: `Sohbet ${state.directorSessionCounter}`,
        messages: Array.isArray(data.messages) ? data.messages : [],
      };
      state.directorSessions.push(sess);
      state.directorSessionId = sid;
      clearDirectorSessionState();
      renderDirectorTabs();
      renderDirectorMessages(sess.messages);
      setDirectorOpen(true);
      setDirectorTab("chat");
      $("director-msg")?.focus();
      toast("Yeni sohbet açıldı");
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  function switchDirectorTab(sid) {
    if (state.directorBusy) {
      toast("Yönetmen yanıt verirken sekme değiştirilemez");
      return;
    }
    state.directorSessionId = sid;
    const s = findSession(sid);
    renderDirectorTabs();
    renderDirectorMessages(s ? s.messages || [] : []);
    clearDirectorSessionState();
    if (s && s.brief) {
      state.directorBrief = s.brief;
      setDirectorReadyUi(!!s.ready, (s.brief.shots || []).length);
    }
    setDirectorTab("chat");
    setDirectorOpen(true);
  }

  async function closeDirectorTab(sid) {
    if (state.directorBusy) {
      toast("Yönetmen yanıt verirken sekme kapatılamaz");
      return;
    }
    const idx = state.directorSessions.findIndex((s) => s.id === sid);
    if (idx === -1) return;
    try {
      await fetch(`/api/director/session/${sid}`, { method: "DELETE" });
    } catch {
      /* local close even if server miss */
    }
    const wasActive = state.directorSessionId === sid;
    state.directorSessions.splice(idx, 1);
    if (wasActive) {
      const next = state.directorSessions[idx] || state.directorSessions[idx - 1];
      state.directorSessionId = next ? next.id : null;
      clearDirectorSessionState();
      renderDirectorMessages(next ? next.messages || [] : []);
      if (next && next.brief) {
        state.directorBrief = next.brief;
        setDirectorReadyUi(!!next.ready, (next.brief.shots || []).length);
      }
    }
    renderDirectorTabs();
  }

  async function resetDirectorSession() {
    if (state.directorBusy) {
      toast("Yönetmen yanıt verirken sıfırlanamaz");
      return;
    }
    if (
      !confirm(
        "Bu sohbeti sıfırlayıp yeni oturum açmak istiyor musun? Mesajlar ve brief silinir."
      )
    ) {
      return;
    }
    const oldSid = state.directorSessionId;
    const oldTitle =
      (oldSid && findSession(oldSid) && findSession(oldSid).title) ||
      `Sohbet ${state.directorSessionCounter + 1}`;
    try {
      if (oldSid) {
        await fetch(`/api/director/session/${oldSid}`, { method: "DELETE" }).catch(() => {});
        const idx = state.directorSessions.findIndex((s) => s.id === oldSid);
        if (idx !== -1) state.directorSessions.splice(idx, 1);
      }
      const r = await fetch("/api/director/session?lang=" + encodeURIComponent(uiLang()), { method: "POST" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      const sid = directorSessionIdFrom(data);
      if (!sid) throw new Error("Yeni oturum oluşturulamadı");
      if (!oldSid) state.directorSessionCounter += 1;
      const sess = {
        id: sid,
        title: oldTitle,
        messages: Array.isArray(data.messages) ? data.messages : [],
      };
      state.directorSessions.push(sess);
      state.directorSessionId = sid;
      clearDirectorSessionState();
      renderDirectorTabs();
      renderDirectorMessages(sess.messages);
      setDirectorOpen(true);
      setDirectorTab("chat");
      $("director-msg")?.focus();
      toast("Sohbet sıfırlandı");
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function loadDirectorSessions() {
    try {
      const r = await fetch("/api/director/sessions");
      const data = await r.json().catch(() => ({}));
      if (!r.ok) return;
      const list = data.sessions || [];
      if (!Array.isArray(list) || !list.length) return;
      state.directorSessions = list.map((s, i) => ({
        id: s.id || s.session_id,
        title: s.title || `Sohbet ${i + 1}`,
        messages: Array.isArray(s.messages) ? s.messages : [],
        brief: s.brief || null,
        ready: !!s.ready,
      }));
      state.directorSessionCounter = state.directorSessions.length;
      const last = state.directorSessions[state.directorSessions.length - 1];
      state.directorSessionId = last.id;
      if (last.brief) {
        state.directorBrief = last.brief;
        state.directorReady = !!last.ready;
      }
      renderDirectorTabs();
      renderDirectorMessages(last.messages || []);
      if (state.directorReady || (state.directorBrief && state.directorBrief.shots?.length)) {
        setDirectorReadyUi(true, state.directorBrief?.shots?.length || 0);
        renderDirectorShotPanel(state.directorBrief);
      }
    } catch {
      /* ignore — status endpoint still seeds opening line */
    }
  }

  $("btn-director-new-session")?.addEventListener("click", () => void newDirectorSession());
  $("btn-director-reset")?.addEventListener("click", () => void resetDirectorSession());

  document.addEventListener("h3-lang", () => {
    syncProjectChips();
    refreshModeHints();
    if (state.directorTab === "plan") renderDirectorPlanBoard();
    document.querySelectorAll("#director-log .dir-msg").forEach((el) => {
      const who = el.querySelector(".who");
      if (!who) return;
      who.textContent = el.classList.contains("user") ? tt("dir.you") : tt("dir.who");
    });
    if ($("view-cinema") && !$("view-cinema").classList.contains("hidden") && typeof renderCinema === "function") {
      renderCinema();
    }
  });

  loadLayoutPrefs();

  setQuality(state.quality);
  setProduceMode("t2v");
  // Açılış / yenileme: player hattı sıfır; Comfy kuyruğuna dokunulmaz
  clearPlayer({ quiet: true });
  setDirectorOpen(false);
  syncDirectorDockHeight();
  renderQueue();
  syncProjectChips();
  refreshHealth();
  pollSystem();
  refreshJobs();
  void loadDirectorSessions().then(() => refreshDirectorStatus());
  void loadLoras();
  syncDirectorDockHeight();
  window.addEventListener("resize", syncDirectorDockHeight);
  setInterval(syncDirectorDockHeight, 2000);
  setInterval(refreshHealth, 5000);
  setInterval(pollSystem, 2000);
  setInterval(refreshJobs, 1000);
  setInterval(refreshDirectorStatus, 10000);
})();
