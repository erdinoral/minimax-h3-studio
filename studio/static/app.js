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
    quality: "736",
    aspect: "16:9",
    produceMode: "t2v", // t2v | continue | ref | face | v2v | cinema
    newVideoInput: "t2v", // t2v | i2v (both use the FL2VA graph)
    selectedJobId: null,
    clipPrompt: "",
    clipSeed: "",
    continueFrom: null,
    pendingContinueChild: null,
    playerCleared: true,
    jobStatusSnapshot: {},
    jobs: [],
    queueItems: [],
    refImages: [], // { name, url }
    faceImages: [],
    v2vVideos: [], // { name, url }
    v2vImages: [],
    storyboardImages: [],
    cinema: { title: "", script: "", characters: [], locations: [], creatures: [] },
    cinemaLibrary: { characters: [], locations: [], creatures: [] },
    cinemaSheetRefs: { character: null, location: null, creature: null },
    selectedCharacter: null,
    galleryItems: [],
    mergePickIds: [],
    galleryMergeMode: false,
    cinemaStudioMode: "seamless",
    filmMode: true,
    filmPlanBusy: false,
    firstFrameName: null,
    lastFrameName: null,
    refImageSize: "match",
    directorSessionId: null,
    directorReady: false,
    directorBrief: null,
    directorBusy: false,
    directorOnline: false,
    directorOfflineDetail: "",
    prodLane: "scene",
    studioWorkspace: "scene", // scene | director
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
    loraDownload: {},
    multishot: false,
    postPass: "",
    vfiModel: "",
    // Director tabs: per-session chat state
    directorSessions: [], // { id, title, messages: [ {role, content} ] }
    directorSessionCounter: 0,
    directorTab: "chat",
    llmPub: null,
    llmDraftProvider: "",
    llmModelsSeq: 0,
    ollamaModels: [],
    lmstudioModels: [],
    llamacppModels: [],
  };

  const CHROME_FIT_KEY = "h3-chrome-fit";
  function chromeFitEnabled() {
    try {
      const v = localStorage.getItem(CHROME_FIT_KEY);
      if (v === null || v === undefined || v === "") return true;
      return v === "1" || v === "true";
    } catch {
      return true;
    }
  }
  function applyChromeFit(on) {
    const enabled = on !== false;
    document.documentElement.classList.toggle("chrome-fit", enabled);
    document.body.classList.toggle("chrome-fit", enabled);
    const cb = $("settings-chrome-fit");
    if (cb) cb.checked = enabled;
    try {
      localStorage.setItem(CHROME_FIT_KEY, enabled ? "1" : "0");
    } catch {
      /* ignore */
    }
  }
  function syncChromeFitFromStorage() {
    applyChromeFit(chromeFitEnabled());
  }

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
  function purposeKeysForUi() {
    return PURPOSE_KEYS.slice();
  }

  function isAdultLoraSpec() { return false; }
  function visibleLoraCatalog() { return state.loraCatalog || []; }
  function isStillLoraSpec(spec) { return !!(spec && (spec.graphs || []).includes("still")); }
  function videoLoraCatalog() { return visibleLoraCatalog().filter((spec) => !isStillLoraSpec(spec)); }

  function setPostPass(v) {
    const raw = String(v || "").trim().toLowerCase();
    const next = raw === "upscale" || (raw === "vfi" && state.vfiModel) ? raw : "";
    state.postPass = next;
    document.querySelectorAll("#post-pass-chips .chip, #post-pass-chips-cont .chip, #cinema-post-pass-chips .chip, #director-post-pass-chips .chip").forEach((b) => {
      const p = b.dataset.post || "";
      b.classList.toggle("on", p === next);
      b.textContent = p === "upscale" ? tt("ayar.postUpscale") : p === "vfi" ? tt("ayar.postVfi") : tt("ayar.postOff");
    });
  }

  function syncVfiChips() {
    const on = !!state.vfiModel;
    document.querySelectorAll(".post-pass-vfi").forEach((el) => {
      el.classList.toggle("hidden", !on);
    });
    if (!on && state.postPass === "vfi") setPostPass("");
  }

  function syncAdultContentUi() {
    const on = !!state.adultContentEnabled;
    document.querySelectorAll(".adult-only").forEach((el) => {
      el.classList.toggle("hidden", !on);
    });
    $("settings-adult-on")?.classList.toggle("hidden", !on);
    $("settings-adult-off")?.classList.toggle("hidden", on);
    const status = $("settings-adult-status");
    if (status) status.textContent = on ? tt("settings.adultOn") : "";
    if (!on) {
      if (state.projectPurpose === ADULT_PURPOSE) {
        state.projectPurpose = null;
        syncProjectChips();
      }
      if (state.loraApplied && (state.loraId === ADULT_LORA_ID || isAdultLoraSpec(appliedLoraSpec()))) {
        if ($("lora-select")) $("lora-select").value = "";
        if ($("cinema-lora-select")) $("cinema-lora-select").value = "";
        state.loraId = "";
        state.loraApplied = false;
        if ($("steps")) $("steps").value = "20";
        if ($("sampler")) $("sampler").value = "res_multistep";
        updateLoraHint();
      }
      const bg = $("bible-genre");
      if (bg && bg.value === ADULT_PURPOSE) bg.value = "short_film";
    }
    fillLoraSelect();
    fillLoraShop();
  }
  window.syncAdultContentUi = syncAdultContentUi;

  async function loadStudioSettings() {
    try {
      const data = await fetch("/api/studio/settings").then((r) => r.json());
      state.adultContentEnabled = !!data.adult_content_enabled;
    } catch (_) {
      state.adultContentEnabled = false;
    }
    syncAdultContentUi();
  }

  async function setAdultContentEnabled(enabled) {
    const on = !!enabled;
    if (on) {
      const ok = !!$("settings-adult-confirm")?.checked;
      if (!ok) {
        toast(tt("settings.adultNeedConfirm"));
        return;
      }
    }
    try {
      const r = await fetch("/api/studio/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ adult_content_enabled: on }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data) || tt("settings.adultSaveFail"));
      state.adultContentEnabled = !!data.adult_content_enabled;
      syncAdultContentUi();
      toast(on ? tt("settings.adultEnabledToast") : tt("settings.adultDisabledToast"));
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function applyAdultProductionPreset() {
    setProduceMode("t2v");
    setDuration(5);
    setQuality("736");
    if ($("steps")) $("steps").value = "4";
    const samp = $("sampler");
    if (samp) {
      if (![...samp.options].some((o) => o.value === "er_sde")) {
        const opt = document.createElement("option");
        opt.value = "er_sde";
        opt.textContent = "er_sde";
        samp.appendChild(opt);
      }
      samp.value = "er_sde";
    }
    if ($("prompt-rewriter-enabled")) $("prompt-rewriter-enabled").checked = false;
    if (!state.loraCatalog.length) await loadLoras();
    const sel = $("lora-select");
    if (sel && [...sel.options].some((o) => o.value === ADULT_LORA_ID)) {
      sel.value = ADULT_LORA_ID;
      if ($("cinema-lora-select")) $("cinema-lora-select").value = ADULT_LORA_ID;
    }
    await applyLora();
    toast(tt("toast.adultPreset"));
  }
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

  function queueBtnLabel(n) {
    const count = Number(n) || 0;
    return count ? tf("dir.queueN", { n: String(count) }) : tt("dir.queue");
  }

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
  function tToast(key, map) {
    toast(tf(key, map || {}));
  }
  function tConfirm(key, map) {
    return confirm(tf(key, map || {}));
  }
  function uiLang() {
    return typeof h3Lang === "function" ? h3Lang() : "tr";
  }

  const CINEMA_LOOK_PRESETS = {
    auto: {
      camera: "auto",
      palette: "auto",
      lighting: "auto",
      era: "auto",
      purpose: "auto",
      style: "auto",
      audio: "film",
    },
    feature: {
      camera: "35mm",
      palette: "kodak",
      lighting: "volumetric",
      era: "present",
      purpose: "short_film",
      style: "realistic",
      audio: "film",
    },
    handheld: {
      camera: "handheld",
      palette: "rec709",
      lighting: "natural",
      era: "present",
      purpose: "social",
      style: "realistic",
      audio: "film",
    },
    documentary: {
      camera: "16mm",
      palette: "rec709",
      lighting: "natural",
      era: "present",
      purpose: "documentary",
      style: "realistic",
      audio: "film",
    },
    commercial: {
      camera: "35mm",
      palette: "teal_orange",
      lighting: "studio",
      era: "present",
      purpose: "ad",
      style: "realistic",
      audio: "film",
    },
    music_video: {
      camera: "anamorphic2x",
      palette: "neon",
      lighting: "neon",
      era: "present",
      purpose: "music_video",
      style: "realistic",
      audio: "silent",
    },
    anamorphic: {
      camera: "anamorphic2x",
      palette: "teal_orange",
      lighting: "volumetric",
      era: "present",
      purpose: "short_film",
      style: "realistic",
      audio: "film",
    },
    found_footage: {
      camera: "handheld",
      palette: "bleach",
      lighting: "natural",
      era: "present",
      purpose: "documentary",
      style: "found_footage",
      audio: "film",
    },
    noir: {
      camera: "35mm",
      palette: "noir",
      lighting: "practical",
      era: "present",
      purpose: "short_film",
      style: "realistic",
      audio: "film",
    },
    golden: {
      camera: "35mm",
      palette: "golden_hour",
      lighting: "natural",
      era: "present",
      purpose: "short_film",
      style: "realistic",
      audio: "film",
    },
    retro_80s: {
      camera: "35mm",
      palette: "neon",
      lighting: "neon",
      era: "1980s",
      purpose: "music_video",
      style: "realistic",
      audio: "silent",
    },
    sci_fi_hard: {
      camera: "35mm",
      palette: "cold",
      lighting: "practical",
      era: "near_future",
      purpose: "short_film",
      style: "realistic",
      audio: "film",
    },
    sci_fi_opera: {
      camera: "imax65",
      palette: "bleach",
      lighting: "natural",
      era: "near_future",
      purpose: "short_film",
      style: "realistic",
      audio: "film",
    },
    sci_fi_wasteland: {
      camera: "35mm",
      palette: "warm",
      lighting: "hard_sun",
      era: "near_future",
      purpose: "short_film",
      style: "realistic",
      audio: "film",
    },
    sci_fi_alien: {
      camera: "anamorphic2x",
      palette: "cold",
      lighting: "volumetric",
      era: "near_future",
      purpose: "short_film",
      style: "realistic",
      audio: "film",
    },
    micro_expression: {
      camera: "35mm",
      palette: "rec709",
      lighting: "studio",
      era: "present",
      purpose: "short_film",
      style: "realistic",
      audio: "film",
    },
    product_minimal: {
      camera: "35mm",
      palette: "rec709",
      lighting: "studio",
      era: "present",
      purpose: "commercial",
      style: "realistic",
      audio: "film",
    },
    title_sequence: {
      camera: "35mm",
      palette: "noir",
      lighting: "practical",
      era: "present",
      purpose: "intro",
      style: "realistic",
      audio: "film",
    },
    handdrawn_live: {
      camera: "35mm",
      palette: "pastel",
      lighting: "natural",
      era: "present",
      purpose: "short_film",
      style: "illustration",
      audio: "film",
    },
    cgi_short: {
      camera: "35mm",
      palette: "teal_orange",
      lighting: "studio",
      era: "present",
      purpose: "short_film",
      style: "cgi_3d",
      audio: "film",
    },
    music_video_cool: {
      camera: "steadicam",
      palette: "neon",
      lighting: "neon",
      era: "present",
      purpose: "music_video",
      style: "realistic",
      audio: "silent",
    },
  };
  const CINEMA_SETUP_OPTIONS = {
    look: [
      ["auto", "Auto"],
      ["feature", "Sinematik"],
      ["handheld", "Handheld doc"],
      ["documentary", "Belgesel"],
      ["commercial", "Reklam"],
      ["music_video", "Klip"],
      ["anamorphic", "Anamorphic"],
      ["found_footage", "Found footage"],
      ["noir", "Noir"],
      ["golden", "Golden hour"],
      ["retro_80s", "80s"],
      ["sci_fi_hard", "Sci-fi · deep space"],
      ["sci_fi_opera", "Sci-fi · space opera"],
      ["sci_fi_wasteland", "Sci-fi · wasteland"],
      ["sci_fi_alien", "Sci-fi · alien ecology"],
      ["micro_expression", "Micro-expression"],
      ["product_minimal", "Product minimal"],
      ["title_sequence", "Title sequence"],
      ["handdrawn_live", "Hand-drawn live"],
      ["cgi_short", "3D CGI short"],
      ["music_video_cool", "Music video cool"],
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
      ["present", "Present"],
      ["near_future", "Near future"],
      ["medieval", "Medieval"],
      ["ancient", "Ancient"],
    ],
  };
  const CINEMA_SETUP_META = {
    look: { labelKey: "cinema.setup.look", icon: "🎞" },
    camera: { labelKey: "cinema.setup.camera", icon: "📷" },
    palette: { labelKey: "cinema.setup.palette", icon: "🎨" },
    lighting: { labelKey: "cinema.setup.lighting", icon: "💡" },
    era: { labelKey: "cinema.setup.era", icon: "📅" },
    purpose: { labelKey: "cinema.setup.purpose", icon: "🎬" },
    style: { labelKey: "cinema.setup.style", icon: "✦" },
  };

  function cinemaId() {
    return (
      (crypto.randomUUID && crypto.randomUUID()) ||
      "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
    );
  }

  function emptyCinema() {
    return {
      film_id: "",
      title: "",
      script: "",
      role_script: "",
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
      quality: "736",
      steps: 20,
      seed: -1,
      seed_lock: false,
      audio: {
        mode: "film",
        score_id: "",
        score_name: "",
        voice_lang: "English",
        last_batch: "",
      },
      characters: [],
      locations: [],
      creatures: [],
      studio_mode: "",
    };
  }

  function ensureCinema() {
    const base = emptyCinema();
    state.cinema = { ...base, ...(state.cinema || {}) };
    state.cinema.setup = { ...base.setup, ...(state.cinema.setup || {}) };
    state.cinema.audio = { ...base.audio, ...(state.cinema.audio || {}) };
    // Spoken dialogue defaults to English. EN UI always pins English; TR UI keeps
    // whatever is set (default English) so users can still get pure English clips.
    if (typeof window.h3Lang === "function" && window.h3Lang() === "en") {
      state.cinema.audio.voice_lang = "English";
    }
    if (!Array.isArray(state.cinema.shots)) state.cinema.shots = [];
    if (state.cinema.role_script == null) state.cinema.role_script = "";
    if (!Array.isArray(state.cinema.characters)) state.cinema.characters = [];
    if (!Array.isArray(state.cinema.locations)) state.cinema.locations = [];
    if (!Array.isArray(state.cinema.creatures)) state.cinema.creatures = [];
    return state.cinema;
  }

  function cinemaSetupOptions(key) {
    if (key === "purpose") {
      return [["auto", tt("cinema.auto")]].concat(
        purposeKeysForUi().map((id) => [id, purposeLabel(id)])
      );
    }
    if (key === "style") {
      return [["auto", tt("cinema.auto")]].concat(STYLE_KEYS.map((id) => [id, styleLabel(id)]));
    }
    const rows = CINEMA_SETUP_OPTIONS[key] || [["auto", "Auto"]];
    return rows.map(([id, fallback]) => {
      if (id === "auto") return [id, tt("cinema.auto")];
      if (key === "look") return [id, tt("cinema.look." + id) || fallback];
      if (key === "era") {
        const k = "cinema.era." + id;
        const v = tt(k);
        return [id, v !== k ? v : fallback];
      }
      return [id, fallback];
    });
  }

  function applyCinemaLookPreset(lookId) {
    const id = CINEMA_LOOK_PRESETS[lookId] ? lookId : "auto";
    const bundle = CINEMA_LOOK_PRESETS[id];
    const c = ensureCinema();
    c.setup = c.setup || {};
    c.setup.look = id;
    c.setup.camera = bundle.camera;
    c.setup.palette = bundle.palette;
    c.setup.lighting = bundle.lighting;
    c.setup.era = bundle.era;
    c.setup.purpose = bundle.purpose;
    c.setup.style = bundle.style;
    if (bundle.audio) cinemaAudio().mode = bundle.audio;
  }

  function cinemaSetupValueLabel(key, id) {
    const found = cinemaSetupOptions(key).find((row) => row[0] === id);
    return (found && found[1]) || tt("cinema.auto");
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

  /** Feedback visible in director dock (prod bar is often off-screen when modal is open). */
  function directorLlmFeedback(msg, kind) {
    const hint = $("llm-prod-hint");
    if (hint && msg) {
      hint.textContent = msg;
      hint.classList.remove("llm-feedback-ok", "llm-feedback-warn", "llm-feedback-err");
      if (kind === "ok") hint.classList.add("llm-feedback-ok");
      if (kind === "warn") hint.classList.add("llm-feedback-warn");
      if (kind === "err") hint.classList.add("llm-feedback-err");
    }
    const st = $("director-status");
    if (st && msg && kind && kind !== "ok") {
      st.textContent = msg.length > 96 ? msg.slice(0, 93) + "…" : msg;
      st.classList.toggle("on", false);
      st.classList.toggle("off", true);
    }
    if (msg) toast(msg);
  }

  async function copyText(text, okMsg) {
    const t = (text == null ? "" : String(text)).trim();
    if (!t) {
      toast(tt("toast.noPrompt"));
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
    toast(okMsg || tt("toast.copied"));
    return true;
  }

  function setClipPrompt(text, meta, seed) {
    state.clipPrompt = text == null ? "" : String(text);
    const has = !!state.clipPrompt.trim();
    const pre = $("clip-prompt-text");
    if (pre) pre.textContent = has ? state.clipPrompt : tt("clip.empty");
    const metaEl = $("clip-prompt-meta");
    if (metaEl) metaEl.textContent = meta || "";
    if (seed !== undefined) {
      state.clipSeed =
        seed != null && seed !== "" && Number(seed) >= 0 ? String(seed) : "";
    } else if (!has) {
      state.clipSeed = "";
    }
    const s = state.clipSeed || "";
    const seedEl = $("clip-prompt-seed");
    if (seedEl) {
      if (s) {
        seedEl.hidden = false;
        seedEl.textContent = tf("clip.seed", { seed: s }) || `Seed: ${s}`;
      } else {
        seedEl.hidden = true;
        seedEl.textContent = "";
      }
    }
    $("btn-open-prompt")?.classList.toggle("hidden", !has);
  }

  function openPromptView(text, meta, seed) {
    if (text !== undefined) setClipPrompt(text, meta, seed);
    const t = (state.clipPrompt || "").trim();
    if (!t) {
      toast(tt("toast.noClipPrompt"));
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

  function clearFilePickLabel(input) {
    const el = typeof input === "string" ? $(input) : input;
    const wrap = el?.closest?.(".file-pick");
    const nameEl = wrap?.querySelector(".file-pick-name");
    if (!nameEl) return;
    const emptyKey = nameEl.getAttribute("data-i18n-empty");
    nameEl.textContent = emptyKey ? tt(emptyKey) : tt("pick.none");
    nameEl.classList.remove("has-file");
    nameEl.removeAttribute("title");
    if (el && "value" in el) el.value = "";
  }

  const FILE_PICK_GRID_INPUT = {
    "first-frame-thumb": "first-frame-file",
    "last-frame-thumb": "last-frame-file",
    "v2v-video-thumbs": "v2v-video-files",
    "v2v-image-thumbs": "v2v-image-files",
  };

  function onFilePickListEmpty(gridId, list) {
    if (list.length) return;
    const inputId = FILE_PICK_GRID_INPUT[gridId];
    if (inputId) clearFilePickLabel($(inputId));
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
    root.style.removeProperty("--director-h");
    // Dock is in document flow — workspace no longer needs a fake bottom pad
    root.style.setProperty("--director-pad", "0px");
  }

  function setDirectorOpen(open) {
    setDirectorModal(!!open);
  }

  function setDirectorLlmOpen(open) {
    setDirectorModal(!!open);
  }

  function setDirectorModal(open) {
    const dock = $("director-dock");
    const backdrop = $("director-backdrop");
    if (!dock) return;
    const on = !!open;
    dock.classList.toggle("modal-open", on);
    dock.setAttribute("aria-hidden", on ? "false" : "true");
    backdrop?.classList.toggle("hidden", !on);
    document.body.classList.toggle("director-modal-open", on);
    $("btn-director-llm-tab")?.setAttribute("aria-expanded", on ? "true" : "false");
    if (!on) {
      dock.style.removeProperty("left");
      dock.style.removeProperty("right");
      dock.style.removeProperty("top");
      dock.style.removeProperty("bottom");
      dock.style.removeProperty("height");
      dock.style.removeProperty("width");
    }
    syncDirectorDockHeight();
    const log = $("director-log");
    if (log) log.scrollTop = log.scrollHeight;
    if (on) $("director-msg")?.focus();
  }

  $("btn-dir-collapse")?.addEventListener("click", () => setDirectorModal(false));
  $("director-backdrop")?.addEventListener("click", () => setDirectorModal(false));
  window.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if ($("director-dock")?.classList.contains("modal-open")) {
      e.preventDefault();
      setDirectorModal(false);
    }
  });

  (() => {
    const dock = $("director-dock");
    if (!dock) return;
    dock.style.height = "";
    dock.style.removeProperty("--director-h");
  })();

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

  // Official H3 sizes (ResolutionSelector, multiple of 32). Six practical MP tiers.
  // Legacy UI keys 720/1080 alias to 736/1088.
  const H3_QUALITY_ALIASES = { 720: "736", 1080: "1088", "720": "736", "1080": "1088" };
  const H3_QUALITY_KEYS = ["352", "480", "608", "736", "768", "1088"];
  const H3_QUALITY_SIZES = {
    "16:9": {
      352: [608, 352],
      480: [864, 480],
      608: [1056, 608],
      736: [1280, 736],
      768: [1344, 768],
      1088: [1920, 1088],
    },
    "9:16": {
      352: [352, 608],
      480: [480, 864],
      608: [608, 1056],
      736: [736, 1280],
      768: [768, 1344],
      1088: [1088, 1920],
    },
    "1:1": {
      352: [448, 448],
      480: [640, 640],
      608: [800, 800],
      736: [960, 960],
      768: [1024, 1024],
      1088: [1440, 1440],
    },
    "21:9": {
      352: [704, 288],
      480: [992, 416],
      608: [1216, 512],
      736: [1472, 640],
      768: [1536, 672],
      1088: [2208, 960],
    },
    "4:3": {
      352: [544, 384],
      480: [736, 576],
      608: [928, 672],
      736: [1120, 832],
      768: [1184, 864],
      1088: [1664, 1248],
    },
  };

  function normalizeQuality(quality) {
    let q = String(quality == null ? "736" : quality);
    q = H3_QUALITY_ALIASES[q] || q;
    return H3_QUALITY_KEYS.includes(q) ? q : "736";
  }

  function resolveSize(aspect, quality) {
    const q = normalizeQuality(quality);
    const preset = H3_QUALITY_SIZES[aspect] && H3_QUALITY_SIZES[aspect][q];
    if (preset) return preset;
    const base = ASPECT_BASE[aspect] || ASPECT_BASE["16:9"];
    const shortTarget = { 352: 352, 480: 480, 608: 608, 736: 736, 768: 768, 1088: 1088 }[q] || 736;
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

  function aspectFromClip(job) {
    const allowed = ["16:9", "9:16", "1:1", "21:9", "4:3"];
    const saved = String(job?.aspect || "").trim();
    if (allowed.includes(saved)) return saved;

    const width = Number(job?.width);
    const height = Number(job?.height);
    if (!(width > 0 && height > 0)) return "";

    const ratio = width / height;
    return allowed.reduce((closest, candidate) => {
      const [w, h] = candidate.split(":").map(Number);
      return Math.abs(ratio - w / h) < Math.abs(ratio - closest[0] / closest[1])
        ? [w, h, candidate]
        : closest;
    }, [16, 9, "16:9"])[2];
  }

  function syncContinueAspect(job) {
    const aspect = aspectFromClip(job);
    if (aspect) setAspect(aspect);
  }

  function setQuality(q) {
    const v = normalizeQuality(q);
    state.quality = v;
    const aspect = state.aspect || "16:9";
    document.querySelectorAll("#quality-chips .chip, #quality-chips-cont .chip").forEach((b) => {
      const key = normalizeQuality(b.dataset.q);
      b.classList.toggle("on", key === v);
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
    $("fl2va-frames")?.classList.toggle("hidden", m !== "t2v" || state.newVideoInput !== "i2v");
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

  function setNewVideoInput(mode) {
    const input = mode === "i2v" ? "i2v" : "t2v";
    state.newVideoInput = input;
    document.querySelectorAll("#new-video-input-chips .chip").forEach((btn) => {
      btn.classList.toggle("on", btn.dataset.newinput === input);
    });
    $("fl2va-frames")?.classList.toggle(
      "hidden",
      state.produceMode !== "t2v" || input !== "i2v"
    );
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
      card.innerHTML = `<span class="ref-ord">&lt;Picture ${i + 1}&gt;</span><img src="${item.url}" alt="ref ${i + 1}" /><button type="button" title="${tt("pick.remove")}">×</button>`;
      card.querySelector("button").onclick = async () => {
        if (!(await deleteUploadedMedia(item))) return;
        list.splice(i, 1);
        renderRefThumbs(kind);
        if (!list.length) {
          clearFilePickLabel($(isFace ? "face-files" : "ref-files"));
        }
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
        tToast(isFace ? "toast.faceMax3" : "toast.refMax9");
        break;
      }
      const fd = new FormData();
      fd.append("file", file);
      tToast("toast.uploading", { name: file.name });
      try {
        const r = await fetch("/api/refs/upload", { method: "POST", body: fd });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errDetail(data));
        target.push({ name: data.name, filename: data.filename, url: data.url || `#` });
        renderRefThumbs(kind);
      } catch (e) {
        toast(String(e.message || e));
      }
    }
    renderRefThumbs(kind);
    tToast(isFace ? "toast.faceReady" : "toast.refReady", { n: String(target.length) });
  }

  async function generateImageStudioReference() {
    const button = $("btn-image-studio-ref");
    const status = $("image-studio-ref-status");
    const prompt = $("prompt")?.value.trim() || "";
    if (!prompt) {
      toast(tt("prompt.ph"));
      return;
    }
    if (state.refImages.length >= 9) {
      tToast("imageStudio.limit");
      return;
    }
    if (button) button.disabled = true;
    if (status) status.textContent = tt("imageStudio.working");
    try {
      const r = await fetch("/api/image-studio/reference", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          aspect: state.aspect || "16:9",
          steps: 30,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      state.refImages.push({ name: data.name, filename: data.filename, url: data.url || "#" });
      renderRefThumbs("ref");
      tToast("imageStudio.imported");
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      if (button) button.disabled = false;
      if (status) status.textContent = tt("imageStudio.hint");
    }
  }

  async function deleteUploadedMedia(item) {
    const filename = item?.filename || item?.name;
    if (!filename) return true;
    const path = item.kind === "video"
      ? `/api/ref-videos/${encodeURIComponent(filename)}`
      : `/api/refs/${encodeURIComponent(filename)}`;
    try {
      const r = await fetch(path, { method: "DELETE" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok && r.status !== 404) throw new Error(errDetail(data));
      return true;
    } catch (e) {
      toast(String(e.message || e));
      return false;
    }
  }

  function renderNamedThumbs(list, gridId, labelFn, onListChange) {
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
      card.innerHTML = `<span class="ref-ord">${label}</span>${media}<button type="button" title="${tt("pick.remove")}">×</button>`;
      card.querySelector("button").onclick = async () => {
        if (!(await deleteUploadedMedia(item))) return;
        list.splice(i, 1);
        if (typeof onListChange === "function") onListChange(list);
        renderNamedThumbs(list, gridId, labelFn, onListChange);
      };
      grid.appendChild(card);
    });
  }

  async function uploadVideoFiles(fileList, targetList, gridId) {
    const files = Array.from(fileList || []);
    for (const file of files) {
      if (targetList.length >= 3) {
        tToast("toast.videoMax3");
        break;
      }
      const fd = new FormData();
      fd.append("file", file);
      tToast("toast.videoUploading", { name: file.name });
      try {
        const r = await fetch("/api/refs/upload-video", { method: "POST", body: fd });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errDetail(data));
        targetList.push({
          name: data.name,
          filename: data.filename,
          url: data.url || "#",
          kind: "video",
        });
        renderNamedThumbs(targetList, gridId, (i) => `Video ${i + 1}`, (list) => onFilePickListEmpty(gridId, list));
      } catch (e) {
        toast(String(e.message || e));
      }
    }
    renderNamedThumbs(targetList, gridId, (i) => `Video ${i + 1}`, (list) => onFilePickListEmpty(gridId, list));
    tToast("toast.videosReady", { n: String(targetList.length) });
  }

  async function uploadImageToList(fileList, targetList, gridId, max, labelFn) {
    const files = Array.from(fileList || []);
    for (const file of files) {
      if (targetList.length >= max) {
        tToast("toast.imageMax", { n: String(max) });
        break;
      }
      const fd = new FormData();
      fd.append("file", file);
      toast(tf("toast.uploading", { name: file.name }));
      try {
        const r = await fetch("/api/refs/upload", { method: "POST", body: fd });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errDetail(data));
        targetList.push({ name: data.name, filename: data.filename, url: data.url || "#" });
        renderNamedThumbs(targetList, gridId, labelFn, (list) => onFilePickListEmpty(gridId, list));
      } catch (e) {
        toast(String(e.message || e));
      }
    }
    renderNamedThumbs(targetList, gridId, labelFn, (list) => onFilePickListEmpty(gridId, list));
  }

  function setFrameSource(which, source) {
    const kind = source === "generate" ? "generate" : "upload";
    document.querySelectorAll(`.ios-segment [data-frame="${which}"]`).forEach((btn) => {
      btn.classList.toggle("on", btn.dataset.frameSource === kind);
    });
    $(`${which}-frame-upload-pane`)?.classList.toggle("hidden", kind !== "upload");
    $(`${which}-frame-generate-pane`)?.classList.toggle("hidden", kind !== "generate");
  }

  function applySingleFrame(data, which) {
    const gridId = which === "first" ? "first-frame-thumb" : "last-frame-thumb";
    const onFrameListChange = (list) => {
      if (list.length) return;
      if (which === "first") state.firstFrameName = null;
      else state.lastFrameName = null;
      onFilePickListEmpty(gridId, list);
    };
    if (which === "first") state.firstFrameName = data.name;
    else state.lastFrameName = data.name;
    renderNamedThumbs(
      [{ name: data.name, filename: data.filename, url: data.url }],
      gridId,
      () => (which === "first" ? "First" : "Last"),
      onFrameListChange
    );
  }

  async function uploadSingleFrame(file, which) {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    tToast("toast.frameUploading", { which });
    try {
      const r = await fetch("/api/refs/upload", { method: "POST", body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      applySingleFrame(data, which);
      tToast("toast.frameReady", { which });
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function generateSingleFrame(which) {
    // A dedicated frame prompt is optional: re-use the scene prompt so that
    // pressing the Image Studio button always has an intuitive result.
    const prompt = ($(`${which}-frame-prompt`)?.value || $("prompt")?.value || "").trim();
    const button = $(`btn-${which}-frame-generate`);
    const status = $(`${which}-frame-generate-status`);
    if (!prompt) {
      toast(tt("frame.promptPh"));
      return;
    }
    if (button) {
      button.disabled = true;
      button.textContent = tt("imageStudio.working");
    }
    if (status) status.textContent = tt("imageStudio.working");
    try {
      const r = await fetch("/api/image-studio/reference", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, aspect: state.aspect || "16:9", steps: 30 }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      applySingleFrame(data, which);
      tToast("frame.generated");
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = tt("frame.generateWithStudio");
      }
      if (status) status.textContent = "";
    }
  }

  async function loadCinema() {
    try {
      const data = await fetch("/api/cinema").then((r) => r.json());
      const base = emptyCinema();
      state.cinema = {
        ...base,
        film_id: data.film_id || "",
        title: data.title || "",
        script: data.script || "",
        role_script: data.role_script || "",
        shots: Array.isArray(data.shots) ? data.shots : [],
        setup: { ...base.setup, ...(data.setup || {}) },
        audio: { ...base.audio, ...(data.audio || {}) },
        duration: data.duration || 5,
        quality: normalizeQuality(data.quality || "736"),
        steps: data.steps || 20,
        seed: data.seed != null ? data.seed : -1,
        seed_lock: !!data.seed_lock,
        characters: Array.isArray(data.characters) ? data.characters : [],
        locations: Array.isArray(data.locations) ? data.locations : [],
        creatures: Array.isArray(data.creatures) ? data.creatures : [],
        studio_mode: data.studio_mode || "",
      };
      state.cinemaLoaded = true;
      if (data.studio_mode === "seamless" || data.studio_mode === "assets") {
        setCinemaStudioMode(data.studio_mode, { persist: true });
      }
    } catch {
      state.cinema = ensureCinema();
      state.cinemaLoaded = true;
    }
    renderCinema();
    void fillCinemaFilms();
    void refreshCinemaPreview();
    syncFilmModeSummary();
    fetch("/api/cinema/film-plan")
      .then((r) => r.json())
      .then((st) => syncFilmStillsWarn(st.missing_stills))
      .catch(() => {});
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
    pull("cinema-creatures", "creature");
    $("cinema-shots")
      ?.querySelectorAll(".cinema-shot")
      .forEach((card) => {
        const shot = cinemaShotById(card.dataset.id);
        if (!shot) return;
        const ta = card.querySelector("[data-field='text']");
        if (ta) shot.text = ta.value;
      });
    if ($("cinema-title")) c.title = $("cinema-title").value || c.title || "";
    if ($("cinema-role-script")) c.role_script = $("cinema-role-script").value || "";
    if ($("cinema-duration")) c.duration = Number($("cinema-duration").value) || 5;
    if ($("cinema-steps")) c.steps = Number($("cinema-steps").value) || 20;
    if ($("cinema-seed")) c.seed = Number($("cinema-seed").value);
    if ($("cinema-seed-lock")) c.seed_lock = !!$("cinema-seed-lock").checked;
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
      role_script: $("cinema-role-script")?.value || c.role_script || "",
      shots: c.shots || [],
      setup: c.setup || {},
      audio: c.audio || {},
      duration: c.duration || 5,
      quality: normalizeQuality(c.quality || "736"),
      steps: c.steps || 20,
      film_id: c.film_id || "",
      seed: Number.isFinite(Number(c.seed)) ? Number(c.seed) : -1,
      seed_lock: !!c.seed_lock,
      characters: c.characters || [],
      locations: c.locations || [],
      creatures: c.creatures || [],
      studio_mode: cinemaStudioMode(),
    };
  }

  let cinemaSaveGen = 0;
  let cinemaForceLocalShots = false;
  const cinemaSaveRequests = new Set();
  const cinemaSaveControllers = new Map();
  const cinemaAssetVersions = new Map();

  function nextCinemaAssetVersion(kind, id) {
    const key = `${kind}:${String(id || "")}`;
    const next = (cinemaAssetVersions.get(key) || 0) + 1;
    cinemaAssetVersions.set(key, next);
    return next;
  }

  function abortCinemaSaves() {
    for (const controller of cinemaSaveControllers.values()) {
      try {
        controller.abort();
      } catch {
        /* ignore */
      }
    }
    cinemaSaveControllers.clear();
    cinemaSaveRequests.clear();
  }

  function mergeCinemaStillsFromServer(payload, latest) {
    if (!payload || !latest) return payload;
    ["characters", "locations", "creatures"].forEach((key) => {
      const byId = Object.fromEntries(
        (latest[key] || [])
          .filter((x) => x && x.id)
          .map((x) => [String(x.id), x])
      );
      (payload[key] || []).forEach((item) => {
        if (!item) return;
        const srv = byId[String(item.id || "")];
        if (!srv || !cinemaAssetImages(srv).length) return;
        const localN = cinemaAssetImages(item).length;
        const srvN = cinemaAssetImages(srv).length;
        if (localN && localN >= srvN) return;
        item.images = (srv.images || []).slice();
        item.image = srv.image || item.images[0]?.file || "";
        item.url = srv.url || item.images[0]?.url || "";
      });
    });
    return payload;
  }

  async function saveCinema(quiet) {
    if (!state.cinemaLoaded && !(state.cinema && (state.cinema.shots || []).length)) {
      return;
    }
    const gen = ++cinemaSaveGen;
    const payload = cinemaPayload();
    try {
      const latest = await fetch("/api/cinema").then((r) => r.json());
      mergeCinemaStillsFromServer(payload, latest);
    } catch {
      /* keep local payload */
    }
    abortCinemaSaves();
    const controller = new AbortController();
    cinemaSaveControllers.set(gen, controller);
    try {
      const request = fetch("/api/cinema", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      cinemaSaveRequests.add(request);
      let r;
      try {
        r = await request;
      } finally {
        cinemaSaveRequests.delete(request);
        if (cinemaSaveControllers.get(gen) === controller) {
          cinemaSaveControllers.delete(gen);
        }
      }
      if (gen !== cinemaSaveGen) return;
      const data = await r.json().catch(() => payload);
      if (!r.ok) throw new Error(errDetail(data));
      if (gen !== cinemaSaveGen) return;
      const base = emptyCinema();
      // Prefer what we just sent for characters/locations so a racing DELETE/PATCH
      // cannot resurrect cards that the UI already removed.
      const chars = Array.isArray(payload.characters)
        ? payload.characters
        : data.characters || [];
      const locs = Array.isArray(payload.locations)
        ? payload.locations
        : data.locations || [];
      const creatures = Array.isArray(payload.creatures)
        ? payload.creatures
        : data.creatures || [];
      state.cinema = {
        ...base,
        film_id: data.film_id || payload.film_id,
        title: data.title || payload.title,
        script: data.script || payload.script,
        role_script: cinemaTypingIn("cinema-role-script")
          ? ensureCinema().role_script
          : data.role_script || payload.role_script,
        shots:
          cinemaTypingShots() || cinemaForceLocalShots
            ? ensureCinema().shots
            : data.shots || payload.shots,
        setup: { ...base.setup, ...(data.setup || payload.setup || {}) },
        audio: { ...base.audio, ...(data.audio || payload.audio || {}) },
        duration: data.duration || payload.duration,
        quality: String(data.quality || payload.quality),
        steps: data.steps || payload.steps,
        seed: data.seed != null ? data.seed : payload.seed,
        seed_lock: !!(data.seed_lock != null ? data.seed_lock : payload.seed_lock),
        characters: chars,
        locations: locs,
        creatures,
      };
      if (gen === cinemaSaveGen) cinemaForceLocalShots = false;
      if (!quiet) toast(tt("cinema.saved"));
    } catch (e) {
      if (controller.signal.aborted || gen !== cinemaSaveGen) return;
      if (!quiet) toast(String(e.message || e));
    }
  }

  function cinemaLoraOptions(selected) {
    const catalog = state.loraCatalog || [];
    const opts = ['<option value="">' + htmlEsc(tt("ayar.loraNoneOpt")) + "</option>"];
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

  
  function cinemaRefUrl(file) {
    const f = String(file || "").trim();
    if (!f) return "";
    if (/^https?:\/\//i.test(f) || f.startsWith("/api/")) return f;
    return "/api/refs/" + encodeURIComponent(f);
  }

  function cinemaAssetImages(item) {
    const imgs = Array.isArray(item?.images) ? item.images.filter((x) => x && (x.file || x.url)) : [];
    if (imgs.length) return imgs.slice(0, 5);
    if (item?.image) {
      return [{ name: "", file: item.image, url: item.url || "/api/refs/" + item.image }];
    }
    return [];
  }

  function cinemaCallSlug(name) {
    return String(name || "")
      .trim()
      .toLowerCase()
      .replace(/ç/g, "c")
      .replace(/ğ/g, "g")
      .replace(/ı/g, "i")
      .replace(/ö/g, "o")
      .replace(/ş/g, "s")
      .replace(/ü/g, "u")
      .replace(/[^a-z0-9]+/g, "") || "asset";
  }

  function openCinemaStill(url, name) {
    const src = String(url || "").trim();
    if (!src) return;
    const img = $("cinema-still-modal-img");
    const dl = $("cinema-still-modal-dl");
    const modal = $("cinema-still-modal");
    if (img) {
      img.src = src;
      img.alt = name || "";
    }
    if (dl) {
      dl.href = src;
      dl.setAttribute("download", name || "still.png");
    }
    modal?.classList.remove("hidden");
    if (modal) modal.setAttribute("aria-hidden", "false");
  }

  function closeCinemaStill() {
    const modal = $("cinema-still-modal");
    const img = $("cinema-still-modal-img");
    modal?.classList.add("hidden");
    if (modal) modal.setAttribute("aria-hidden", "true");
    if (img) img.removeAttribute("src");
  }

  function cinemaFolderHtml(item) {
    const imgs = cinemaAssetImages(item);
    const slug = cinemaCallSlug(item?.name);
    const n = imgs.length;
    const tab =
      '<div class="cinema-folder-tab"><span>📁</span><b>' +
      htmlEsc((item?.name || "").trim() || tt("cinema.untitled")) +
      "</b><span>" +
      n +
      "/5</span></div>";
    const body = !imgs.length
      ? '<div class="cinema-folder is-empty"><span class="empty">' +
        htmlEsc(tt("cinema.noImg")) +
        "</span></div>"
      : '<div class="cinema-folder">' +
        imgs
          .map((im, i) => {
            const call = im.name || slug + (i + 1);
            const src = htmlEsc(im.url || "/api/refs/" + im.file);
            const file = htmlEsc(im.file || "");
            return (
              '<figure class="cinema-asset">' +
              '<img src="' +
              src +
              '" alt="' +
              htmlEsc(call) +
              '" data-full="' +
              src +
              '" data-name="' +
              htmlEsc((im.file || call) + "") +
              '" />' +
              '<figcaption class="cinema-call" data-call="' +
              htmlEsc(call) +
              '" title="' +
              htmlEsc(tt("cinema.copyCallHint")) +
              '">' +
              htmlEsc(call) +
              "</figcaption>" +
              '<a class="cinema-img-dl" href="' +
              src +
              '" download="' +
              htmlEsc(im.file || call + ".png") +
              '" title="' +
              htmlEsc(tt("cinema.dlStill")) +
              '">↓</a>' +
              '<button type="button" class="cinema-img-zoom" data-url="' +
              src +
              '" data-name="' +
              htmlEsc(im.file || call + ".png") +
              '" title="' +
              htmlEsc(tt("cinema.zoom")) +
              '">⤢</button>' +
              '<button type="button" class="cinema-img-del" data-file="' +
              file +
              '" title="' +
              htmlEsc(tt("cinema.del")) +
              '">×</button>' +
              "</figure>"
            );
          })
          .join("") +
        "</div>";
    return '<div class="cinema-folder-wrap">' + tab + body + "</div>";
  }

  function cinemaCardHtml(item, kind) {
    const isChar = kind === "character";
    const nameLabel = isChar ? tt("cinema.charName") : tt("cinema.locName");
    const descLabel = tt("cinema.desc");
    const namePh = isChar ? "Ada" : "Rooftop";
    const descPh = isChar ? tt("cinema.charDescPh") : tt("cinema.locDescPh");
    const lora = isChar
      ? '<label class="cinema-field-label">' +
        htmlEsc(tt("cinema.charLora")) +
        '</label><select data-field="lora_id">' +
        cinemaLoraOptions(item.lora_id || "") +
        "</select>"
      : "";
    return (
      '<div class="cinema-card" data-id="' +
      htmlEsc(item.id) +
      '" data-kind="' +
      kind +
      '">' +
      cinemaFolderHtml(item) +
      '<div class="fields">' +
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
        ? '<label class="cinema-field-label">' +
          htmlEsc(tt("cinema.voice")) +
          "</label>" +
          '<textarea data-field="voice" rows="2" placeholder="' +
          htmlEsc(tt("cinema.voicePh")) +
          '">' +
          htmlEsc(item.voice) +
          "</textarea>"
        : "") +
      lora +
      '<div class="row-btns"><label class="file-pick file-pick-inline">' +
      '<input type="file" class="file-pick-input cinema-img" accept="image/*" multiple' +
      (cinemaAssetImages(item).length >= 5 ? " disabled" : "") +
      " />" +
      '<span class="file-pick-btn">' +
      htmlEsc(tt("cinema.uploadImg")) +
      "</span></label>" +
      '<span class="muted cinema-img-cap">' +
      htmlEsc(tf("cinema.imgMax", { slug: cinemaCallSlug(item.name) })) +
      "</span>" +
      '<button type="button" class="btn-ghost cinema-del">' +
      htmlEsc(tt("cinema.del")) +
      "</button></div></div></div>"
    );
  }

  function renderCinemaCharacterModal() {
    const modal = $("cinema-character-modal");
    const item = state.selectedCharacter;
    if (!modal || !item) return;
    $("cinema-character-name").value = item.name || "";
    $("cinema-character-notes").value = item.notes || "";
    $("cinema-character-voice").value = item.voice || "";
    const voiceName = $("cinema-character-voice-file-name");
    if (voiceName) {
      voiceName.textContent = item.voice_audio
        ? item.voice_audio
        : tt("pick.none");
    }
    $("cinema-character-lora").innerHTML = cinemaLoraOptions(item.lora_id || "");
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
  }

  async function uploadCinemaVoiceClip(file) {
    const item = state.selectedCharacter;
    if (!item || !file) return;
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch("/api/refs/upload-audio", { method: "POST", body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      const name = data.name || data.filename || "";
      if (!name) throw new Error(tt("err.voiceUpload"));
      item.voice_audio = name;
      const voiceName = $("cinema-character-voice-file-name");
      if (voiceName) voiceName.textContent = name;
      toast(tt("toast.voiceClipOk"));
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  function closeCinemaCharacterModal() {
    const modal = $("cinema-character-modal");
    state.selectedCharacter = null;
    modal?.classList.add("hidden");
    modal?.setAttribute("aria-hidden", "true");
  }

  async function saveCinemaCharacterModal() {
    const item = state.selectedCharacter;
    if (!item) return;
    const payload = {
      name: $("cinema-character-name")?.value || "",
      notes: $("cinema-character-notes")?.value || "",
      voice: $("cinema-character-voice")?.value || "",
      lora_id: $("cinema-character-lora")?.value || "",
    };
    if (item.voice_audio) payload.voice_audio = item.voice_audio;
    const saved = await patchCinemaAsset("character", item.id, payload);
    if (!saved) return;
    closeCinemaCharacterModal();
    renderCinema();
  }

  function filmPillHtml(key, value) {
    const meta = CINEMA_SETUP_META[key] || { labelKey: "", icon: "•" };
    const label = meta.labelKey ? tt(meta.labelKey) : key;
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
      htmlEsc(label) +
      '</span><span class="film-pill-value">' +
      htmlEsc(cinemaSetupValueLabel(key, value)) +
      '</span></span><div class="film-pill-menu">' +
      opts +
      "</div></div>"
    );
  }

  function cinemaShotCalls(text) {
    const raw = String(text || "");
    const low = raw.toLowerCase();
    const out = [];
    const seen = new Set();
    const c = ensureCinema();
    const push = (n) => {
      const s = String(n || "").trim();
      if (!s || seen.has(s.toLowerCase())) return;
      seen.add(s.toLowerCase());
      out.push(s);
    };
    (c.characters || []).concat(c.locations || []).forEach((item) => {
      cinemaAssetImages(item).forEach((im) => {
        if (im.name && low.includes(String(im.name).toLowerCase())) push(im.name);
      });
      const name = (item.name || "").trim();
      if (name.length >= 2) {
        const re = new RegExp("(?:^|[^\\w])" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?:$|[^\\w])", "i");
        if (re.test(raw)) push(name);
      }
    });
    return out;
  }

  function cinemaJobForShot(shotId, index) {
    const batch = (ensureCinema().audio || {}).last_batch || "";
    const jobs = state.jobs || [];
    const byId = jobs.find((j) => j.shot_id && j.shot_id === shotId);
    if (byId) return byId;
    if (!batch) return null;
    const multi = jobs.find(
      (j) => String(j.cinema_batch || "") === String(batch) && j.mode === "multishot"
    );
    if (multi) return multi;
    return jobs.find(
      (j) =>
        String(j.cinema_batch || "") === String(batch) &&
        Number(j.shot_index || j.batch_index) === index + 1
    ) || null;
  }

  function cinemaTypingIn(id) {
    const el = document.activeElement;
    const host = $(id);
    if (!el || !host) return false;
    return host === el || host.contains(el);
  }

  function cinemaTypingShots() {
    return cinemaTypingIn("cinema-shots") || cinemaTypingIn("cinema-shot-draft");
  }

  function cinemaShotJobMeta(shotId, index) {
    const job = cinemaJobForShot(shotId, index);
    const st = job ? job.status : "";
    return {
      cls: st === "done" ? " is-ok" : st === "error" ? " is-err" : st ? " is-run" : "",
      label: job
        ? st === "done"
          ? tt("cinema.shotDone")
          : st === "error"
            ? tt("cinema.shotErr")
            : tt("cinema.shotRun")
        : "",
    };
  }

  function emptyCinemaStructured() {
    return {
      title: "",
      location: "",
      character: "",
      action: "",
      dialogue: "",
      dialogue_lang: "auto",
      camera: "",
      visual_style: "",
      audio: "",
      music: "",
      important: "",
    };
  }

  const GENRE_CRAFT = {
    sci_fi_hard: {
      visual_style: "Live-action, cinematic, hard-science deep-space realism",
      craft: "maintainable aerospace structures, practical cabin point lights, worn titanium, reflective spacesuits, instrument displays, cold controlled contrast, physically plausible floating dust",
      avoid: "neon cyberpunk pollution, holographic UI clutter, cybernetic bodies, rain-soaked neon streets",
      camera_bias: "Favor medium, close, and close-up. Use wide only for true scale of space architecture.",
      soundscape: "mechanical cabin hum, soft suit fabric, distant instrument beeps, controlled air recirculation",
      music: "N/A",
    },
    sci_fi_opera: {
      visual_style: "Live-action, cinematic, epic space-opera scale",
      craft: "monumental minimalist brutalist architecture, vast negative space, solemn natural light, weathered stone, heavy matte metal, protective fabrics, dry drifting dust",
      avoid: "cheap neon cyberpunk shorthand, cluttered holograms, cartoon proportions",
      camera_bias: "Wide only when monumental architecture or fleet scale is the story; otherwise medium and close for faces.",
      soundscape: "vast hall reverb, distant boots on stone, low wind across plaza, solemn quiet between lines",
      music: "N/A",
    },
    sci_fi_wasteland: {
      visual_style: "Live-action, cinematic, wasteland relic science fiction",
      craft: "eroded technological ruins, harsh daylight, sand-scattered particles, rusted steel, weathered armor, worn leather, cracked surfaces, restrained dusty earth tones",
      avoid: "clean chrome utopia, neon cyberpunk nights, glossy VFX-first look",
      camera_bias: "Eye-level and low angles emphasizing isolation; wide for ruin scale when needed.",
      soundscape: "wind over sand, metal creak, distant debris, dry fabric and boot grit",
      music: "N/A",
    },
    sci_fi_alien: {
      visual_style: "Live-action, cinematic, alien organic ecology",
      craft: "internally consistent organic architecture, plants and fungi, wet surfaces, translucent veins, water droplets, keratin scales, refraction, localized soft biological light only on living organisms",
      avoid: "city neon cyberpunk, generic green goo tropes, overlit bioluminescence flooding the frame",
      camera_bias: "Push-ins and tracking through wet organic corridors; macro for texture, medium for characters.",
      soundscape: "wet drip, soft organic membrane stretch, distant creature breath, humid air",
      music: "N/A",
    },
    micro_expression: {
      visual_style: "Live-action, cinematic, intimate micro-expression study",
      craft: "tight facial close-up, readable eye/brow/mouth micro-changes, shallow depth of field, skin texture retained, performance-first framing",
      avoid: "wide establishing unless briefly motivated, busy background action stealing focus, over-smoothed plastic skin",
      camera_bias: "Close-up and extreme close-up; subtle push-in on emotional beats.",
      soundscape: "quiet room tone, breath, subtle fabric, clear dialogue when present",
      music: "N/A",
    },
    product_minimal: {
      visual_style: "Live-action, cinematic, minimalist product hero",
      craft: "clean negative space, precise product silhouette, controlled studio key and soft rim, material truth (metal, glass, fabric), slow confident camera",
      avoid: "busy lifestyle clutter, neon cyberpunk, cartoon CGI look, unreadable logo distortion",
      camera_bias: "Macro and medium hero angles; slow orbit or push-in.",
      soundscape: "soft studio hush, tactile material SFX on contact, no busy street bed",
      music: "N/A",
    },
    title_sequence: {
      visual_style: "Live-action, cinematic title-sequence energy",
      craft: "graphic composition, timed title reveals, strong silhouettes, editorial pacing",
      avoid: "random watermark text, unreadable typography, slideshow of unrelated shots",
      camera_bias: "Motivated moves that land on title cards or iconic objects.",
      soundscape: "stylized impacts synced to cuts, sparse atmosphere",
      music: "N/A",
    },
    handdrawn_live: {
      visual_style: "Hand-drawn live hybrid, ink and paper texture over photographic staging",
      craft: "visible line work, paper grain, controlled color fill, live-action blocking translated into drawn performance",
      avoid: "pure photoreal skin lock, generic anime sakuga unless requested, plastic 3D CGI",
      camera_bias: "Medium and close with drawn parallax; keep motion readable.",
      soundscape: "paper rustle accents optional, clear dialogue, light ambient",
      music: "N/A",
    },
    cgi_short: {
      visual_style: "Premium 3D CGI cinematic short",
      craft: "PBR materials, coherent lighting, appealing proportions, clear silhouette animation",
      avoid: "live-action skin claims, low-poly game leftovers, noisy cyberpunk neon default",
      camera_bias: "Cinematic lenses with motivated moves; hold hero poses.",
      soundscape: "designed Foley matching CGI materials, clear dialogue if any",
      music: "N/A",
    },
    music_video_cool: {
      visual_style: "Live-action music-video cool, rhythmic graphic frames",
      craft: "bold lighting accents, rhythmic camera energy, stylized wardrobe, graphic negative space",
      avoid: "forced dialogue lip-sync unless requested, random cyberpunk clutter without beat motivation",
      camera_bias: "Tracking and handheld pulses timed to imagined beat; punch-ins on peaks.",
      soundscape: "diegetic room / crowd only if needed; primary song muxed later",
      music: "N/A",
    },
  };

  function enrichStructuredFromLook(structured) {
    const s = cleanCinemaStructured(structured);
    const look = String((ensureCinema().setup || {}).look || "").trim();
    const pack = GENRE_CRAFT[look];
    if (!pack) return s;
    if (!s.visual_style && pack.visual_style) s.visual_style = pack.visual_style;
    if (!s.important) {
      const bits = [pack.camera_bias, pack.avoid ? "Avoid: " + pack.avoid : ""].filter(Boolean);
      if (bits.length) s.important = bits.join(" ");
    }
    if (!s.audio && pack.soundscape) s.audio = pack.soundscape;
    if (!s.music && pack.music) s.music = pack.music;
    if (!s.camera && pack.camera_bias) s.camera = pack.camera_bias;
    return s;
  }

  function cleanCinemaStructured(raw) {
    const src = raw && typeof raw === "object" ? raw : {};
    const out = emptyCinemaStructured();
    Object.keys(out).forEach((k) => {
      out[k] = String(src[k] || "").trim();
    });
    if (!out.dialogue_lang) out.dialogue_lang = "auto";
    return out;
  }

  function cinemaHasAuthorFields(s) {
    return Object.keys(s || {}).some((k) => k !== "dialogue_lang" && String(s[k] || "").trim());
  }

  function parseH3Prompt(text) {
    const raw = String(text || "").trim();
    const out = emptyCinemaStructured();
    if (!raw) return out;
    const packed = raw.replace(/\s+/g, " ").trim();
    const blocks = packed.match(
      /integrated[_\s]+multimodal[_\s]+description\s*[?:]\s*(.*?)(?:\s+overall_soundscape\s*[?:]\s*(.*?))?(?:\s+non_diegetic_music\s*[?:]\s*(.*?))?$/i
    );
    let body = packed;
    if (blocks) {
      body = String(blocks[1] || "").trim();
      out.audio = String(blocks[2] || "").trim();
      out.music = String(blocks[3] || "").trim();
    }
    const markers = [
      ["location", /\bLocation:\s*/i],
      ["character", /\bMain character:\s*/i],
      ["action", /\bAction:\s*/i],
      ["camera", /\bCamera:\s*/i],
      ["important", /\bConstraints:\s*/i],
    ];
    const hits = [];
    markers.forEach(([key, rx]) => {
      const m = rx.exec(body);
      if (m) hits.push({ key, start: m.index, end: m.index + m[0].length });
    });
    if (!hits.length && !blocks) return emptyCinemaStructured();
    hits.sort((a, b) => a.start - b.start);
    const head = (hits.length ? body.slice(0, hits[0].start) : body).trim();
    const hm = head.match(
      /^(?:SCENE\s*[–—-]\s*(.+?)\.\s+)?\[Shot\s*\d+\]\s*(.*?)\s*$/i
    );
    if (hm) {
      out.title = String(hm[1] || "").trim();
      out.visual_style = String(hm[2] || "").trim();
    } else if (/^scene/i.test(head)) {
      out.title = head.replace(/^SCENE\s*[–—-]\s*/i, "").replace(/[. ]+$/, "");
    }
    hits.forEach((hit, i) => {
      const stop = i + 1 < hits.length ? hits[i + 1].start : body.length;
      out[hit.key] = body.slice(hit.end, stop).trim();
    });
    const cam = String(out.camera || "");
    const dm = cam.match(
      /\s+\(S\d+\)\s+says:\s*(?:<d>\[([^\]]+)\]\s*)?(.*?)<\/d>\s*$/i
    );
    if (dm) {
      const before = cam.slice(0, dm.index).trim();
      const who = String(out.character || "").trim();
      if (who && before.endsWith(who)) {
        out.camera = before.slice(0, -who.length).trim();
      } else {
        const wm = before.match(/^(.+)\s+([A-Z][^()]+)$/);
        if (wm) {
          out.camera = String(wm[1] || "").trim();
          if (!who) out.character = String(wm[2] || "").trim();
        } else {
          out.camera = before;
        }
      }
      const line = String(dm[2] || "").trim();
      if (line) {
        out.dialogue = line;
        if (dm[1]) out.dialogue_lang = String(dm[1]).trim();
      }
    }
    if (out.music && /^(n\/a|na|none|no|yok|off)$/i.test(out.music)) out.music = "N/A";
    return out;
  }

  function cinemaShotStructured(shot) {
    const s = cleanCinemaStructured(shot && shot.structured);
    const blob = String((shot && shot.text) || s.action || "").trim();
    const onlyBlob =
      /integrated[_\s]+multimodal[_\s]+description/i.test(blob) &&
      !s.title &&
      !s.location &&
      !s.character &&
      !s.camera;
    if (cinemaHasAuthorFields(s) && !onlyBlob) return s;
    const parsed = parseH3Prompt(blob);
    return cinemaHasAuthorFields(parsed) ? parsed : s;
  }

  function hydrateCinemaStructuredShots(c) {
    const film = c || ensureCinema();
    (film.shots || []).forEach((shot) => {
      const recovered = cinemaShotStructured(shot);
      if (!cinemaHasAuthorFields(recovered)) return;
      const rawS = cleanCinemaStructured(shot.structured);
      const dumped =
        /integrated[_\s]+multimodal[_\s]+description/i.test(rawS.action || shot.text || "") &&
        !rawS.title &&
        !rawS.location;
      if (!cinemaHasAuthorFields(rawS) || dumped) shot.structured = recovered;
    });
    return film;
  }

  function cinemaDialogueLangLabel(structured) {
    const explicit = String(structured.dialogue_lang || "").trim();
    if (explicit && explicit.toLowerCase() !== "auto") return explicit;
    const dialogue = structured.dialogue || "";
    if (/[\u0600-\u06FF]/.test(dialogue)) return "Arabic";
    if (/[\u0400-\u04FF]/.test(dialogue)) return "Russian";
    if (/[\u3040-\u30FF\u4E00-\u9FFF]/.test(dialogue)) {
      return /[\u3040-\u30FF]/.test(dialogue) ? "Japanese" : "Chinese";
    }
    if (/[\uAC00-\uD7AF]/.test(dialogue)) return "Korean";
    if (/[ğüşıöçĞÜŞİÖÇ]/.test(dialogue)) return "Turkish";
    return "English";
  }

  function wrapCinemaDialogue(dialogue, lang) {
    const text = String(dialogue || "").trim();
    if (!text) return "";
    if (/<d>/i.test(text)) return text;
    const label = String(lang || "English").trim() || "English";
    return "says: <d>[" + label + "] " + text + "</d>";
  }

  function composeH3Prompt(structuredRaw) {
    const s = enrichStructuredFromLook(structuredRaw);
    const hasBody = Object.keys(s).some(
      (k) => k !== "dialogue_lang" && String(s[k] || "").trim()
    );
    if (!hasBody) return "";
    const style = s.visual_style || "Live-action, cinematic";
    const parts = ["[Shot 1] " + style];
    if (s.location) parts.push("Location: " + s.location);
    if (s.character) parts.push("Main character: " + s.character);
    if (s.action) parts.push("Action: " + s.action);
    if (s.camera) parts.push("Camera: " + s.camera);
    if (s.dialogue) {
      const lang = cinemaDialogueLangLabel(s);
      const who = s.character || "The speaker (S1)";
      if (/\(S[12]\)/.test(who)) {
        parts.push(who + " " + wrapCinemaDialogue(s.dialogue, lang));
      } else {
        parts.push(who + " (S1) " + wrapCinemaDialogue(s.dialogue, lang));
      }
    }
    if (s.important) parts.push("Constraints: " + s.important);
    let multimodal = parts.map((p) => p.trim()).filter(Boolean).join(" ");
    if (s.title) multimodal = "SCENE – " + s.title + ". " + multimodal;
    const soundscape =
      s.audio ||
      "Natural ambient sound matching the scene, with clear dialogue when present.";
    const musicRaw = String(s.music || "").trim();
    const music =
      !musicRaw || /^(n\/a|na|none|no|yok|off)$/i.test(musicRaw)
        ? "N/A"
        : musicRaw;
    return (
      "integrated_multimodal_description: " +
      multimodal +
      "\n\noverall_soundscape: " +
      soundscape +
      "\n\nnon_diegetic_music: " +
      music
    );
  }

  function cinemaShotSummary(shot) {
    const s = cinemaShotStructured(shot);
    if (s.title) return s.title;
    const bits = [s.location, s.character, s.action, s.dialogue].filter(Boolean);
    if (bits.length) return bits.join(" · ");
    const text = String((shot && shot.text) || "").trim();
    if (!text) return "";
    const oneLine = text.replace(/\s+/g, " ");
    return oneLine.length > 140 ? oneLine.slice(0, 137) + "…" : oneLine;
  }

  function cinemaShotHtml(shot, index) {
    const mode = shot.mode === "continue" ? "continue" : "t2v";
    const enabled = shot.enabled !== false;
    const calls = cinemaShotCalls(shot.text);
    const jobMeta = cinemaShotJobMeta(shot.id, index);
    const jobCls = jobMeta.cls;
    const jobLabel = jobMeta.label;
    const structured = cinemaShotStructured(shot);
    const title = structured.title;
    const summary = cinemaShotSummary(shot) || tt("cinema.sectionEmpty");
    const modeHtml =
      cinemaStudioMode() === "seamless"
        ? '<span class="cinema-shot-link muted">' +
          (mode === "continue" ? tt("filmMode.linkCont") : tt("filmMode.linkNew")) +
          "</span>"
        : '<div class="cinema-shot-mode">' +
          '<button type="button" class="t2v' +
          (mode === "t2v" ? " on" : "") +
          '" data-mode="t2v">' +
          tt("mode.t2v") +
          "</button>" +
          '<button type="button" class="continue' +
          (mode === "continue" ? " on" : "") +
          '" data-mode="continue">' +
          tt("plan.cont") +
          "</button></div>";
    return (
      '<article class="cinema-shot' +
      (enabled ? "" : " is-disabled") +
      '" data-id="' +
      htmlEsc(shot.id) +
      '"><div class="cinema-shot-head"><span class="idx">' +
      htmlEsc(tf("cinema.sectionLabel", { n: String(index + 1) })) +
      "</span>" +
      modeHtml +
      (jobLabel
        ? '<span class="cinema-shot-job' + jobCls + '">' + htmlEsc(jobLabel) + "</span>"
        : "") +
      '<button type="button" class="btn-ghost cinema-shot-toggle" aria-pressed="' +
      (enabled ? "true" : "false") +
      '">' +
      tt(enabled ? "cinema.sectionDisable" : "cinema.sectionEnable") +
      "</button>" +
      '<button type="button" class="btn-ghost cinema-shot-duplicate">' +
      tt("cinema.sectionDuplicate") +
      "</button>" +
      '<button type="button" class="btn-ghost cinema-shot-del">' +
      tt("cinema.del") +
      "</button></div>" +
      (title
        ? '<p class="cinema-shot-title">' + htmlEsc(title) + "</p>"
        : "") +
      '<p class="cinema-shot-summary">' +
      htmlEsc(summary) +
      "</p>" +
      '<div class="cinema-shot-actions">' +
      '<button type="button" class="btn-secondary cinema-shot-edit">' +
      tt("cinema.sectionEdit") +
      "</button></div>" +
      (calls.length
        ? '<div class="cinema-shot-binds">' +
          calls.map((n) => '<span class="cinema-bind">' + htmlEsc(n) + "</span>").join("") +
          "</div>"
        : "") +
      "</article>"
    );
  }

  let cinemaSceneEditId = null;
  let cinemaSceneEditMode = "t2v";

  function readCinemaSceneForm() {
    const out = emptyCinemaStructured();
    $("cinema-scene-modal")
      ?.querySelectorAll("[data-scene-field]")
      .forEach((el) => {
        const key = el.dataset.sceneField;
        if (!key || !(key in out)) return;
        out[key] = String(el.value || "").trim();
      });
    return out;
  }

  function fillCinemaSceneForm(structured) {
    const s = cleanCinemaStructured(structured);
    $("cinema-scene-modal")
      ?.querySelectorAll("[data-scene-field]")
      .forEach((el) => {
        const key = el.dataset.sceneField;
        if (!key) return;
        el.value = s[key] || (key === "dialogue_lang" ? "auto" : "");
      });
  }

  function refreshCinemaScenePreview() {
    const pre = $("cinema-scene-preview");
    if (!pre) return;
    pre.textContent = composeH3Prompt(readCinemaSceneForm()) || "—";
  }

  function openCinemaSceneModal(shotId, mode) {
    const modal = $("cinema-scene-modal");
    if (!modal) return;
    cinemaSceneEditId = shotId || null;
    cinemaSceneEditMode =
      cinemaStudioMode() === "seamless"
        ? "t2v"
        : mode === "continue"
          ? "continue"
          : "t2v";
    const shot = shotId ? cinemaShotById(shotId) : null;
    if (shot) {
      cinemaSceneEditMode = shot.mode === "continue" ? "continue" : "t2v";
      const structured = cinemaShotStructured(shot);
      if (cinemaHasAuthorFields(structured)) {
        fillCinemaSceneForm(structured);
        const rawS = cleanCinemaStructured(shot.structured);
        const dumped =
          /integrated[_\s]+multimodal[_\s]+description/i.test(rawS.action || shot.text || "") &&
          !rawS.title &&
          !rawS.location;
        if (!cinemaHasAuthorFields(rawS) || dumped) shot.structured = structured;
      } else if (shot.text) {
        const seeded = emptyCinemaStructured();
        seeded.action = shot.text;
        fillCinemaSceneForm(seeded);
      } else {
        fillCinemaSceneForm(emptyCinemaStructured());
      }
    } else {
      const draft = ($("cinema-shot-draft")?.value || "").trim();
      const seeded = emptyCinemaStructured();
      if (draft) seeded.action = draft;
      fillCinemaSceneForm(seeded);
    }
    refreshCinemaScenePreview();
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    $("cinema-scene-title")?.focus();
  }

  function closeCinemaSceneModal() {
    const modal = $("cinema-scene-modal");
    cinemaSceneEditId = null;
    modal?.classList.add("hidden");
    modal?.setAttribute("aria-hidden", "true");
  }

  function saveCinemaSceneModal() {
    const structured = readCinemaSceneForm();
    const composed = composeH3Prompt(structured);
    const hasBody = Object.keys(structured).some(
      (k) => k !== "dialogue_lang" && structured[k]
    );
    if (!hasBody && !composed) {
      toast(tt("cinema.needShotText"));
      return;
    }
    const c = ensureCinema();
    cinemaForceLocalShots = true;
    const text = composed || structured.action || "";
    if (cinemaSceneEditId) {
      const shot = cinemaShotById(cinemaSceneEditId);
      if (!shot) return;
      shot.structured = structured;
      shot.text = text;
      if (cinemaStudioMode() !== "seamless") {
        shot.mode = cinemaSceneEditMode;
      }
    } else {
      c.shots.push({
        id: cinemaId(),
        text,
        mode: cinemaSceneEditMode,
        structured,
      });
      const draft = $("cinema-shot-draft");
      if (draft) draft.value = "";
    }
    closeCinemaSceneModal();
    renderCinemaShots();
    renderCinema();
    void saveCinema(true);
    scheduleCinemaPreview();
  }

  function addCinemaShot(mode) {
    openCinemaSceneModal(null, mode);
  }

  function addCinemaDraftShot() {
    const draft = $("cinema-shot-draft");
    const text = (draft?.value || "").trim();
    if (!text) {
      toast(tt("cinema.needShotText"));
      return;
    }
    const c = ensureCinema();
    cinemaForceLocalShots = true;
    c.shots.push({
      id: cinemaId(),
      text,
      mode: cinemaStudioMode() === "seamless" ? "t2v" : "t2v",
    });
    if (draft) draft.value = "";
    renderCinemaShots();
    renderCinema();
    void saveCinema(true);
  }

  function cinemaShotById(id) {
    return (ensureCinema().shots || []).find((s) => s.id === id);
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
    syncFilmModeSummary();
    const steps = $("cinema-steps");
    if (steps && document.activeElement !== steps) steps.value = String(c.steps || 20);
    const seed = $("cinema-seed");
    const lock = $("cinema-seed-lock");
    if (lock) lock.checked = !!c.seed_lock;
    if (seed && document.activeElement !== seed && !lock?.checked) {
      seed.value = String(c.seed != null && c.seed !== "" ? c.seed : -1);
    }
    const q = normalizeQuality(c.quality || "736");
    const st = Number(c.steps || 20);
    const speed = $("cinema-speed-chips");
    if (speed) {
      speed.querySelectorAll("button").forEach((btn) => {
        const on =
          btn.dataset.speed === "draft"
            ? (q === "352" || q === "480") && st <= 12
            : (q === "736" || q === "768") && st >= 18;
        btn.classList.toggle("on", on);
      });
    }
    const hint = $("cinema-prod-hint");
    if (hint) {
      const spec = ($("cinema-lora-select") ? state.loraCatalog || [] : []).find(
        (x) => x.id === $("cinema-lora-select")?.value
      );
      const graphs = spec && spec.file ? (spec.graphs || ["fl2va", "ref2va"]).join("+") : "";
      const vram =
        q === "1088" || q === "768"
          ? tt("quality.vramHigh")
          : q === "352" || q === "480"
            ? tt("quality.vramLow")
            : tt("quality.vramMid");
      hint.textContent = graphs
        ? tf("cinema.prodHintLora", { graphs, vram, q, st })
        : tf("cinema.prodHint", { vram, q, st });
    }
    const chips = $("cinema-quality-chips");
    if (chips) {
      chips.querySelectorAll("button").forEach((btn) => {
        btn.classList.toggle("on", normalizeQuality(btn.dataset.quality) === q);
        btn.textContent = qualityChipLabel(btn.dataset.quality, state.aspect || "16:9");
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
        : tt("cinema.scoreNone");
    }
      const remove = $("btn-cinema-score-remove");
      if (remove) remove.classList.toggle("hidden", !audio.score_id);
    const concat = $("btn-cinema-concat");
    if (concat) {
      const n = finishedClipsForMerge().length;
      concat.classList.remove("hidden");
      concat.disabled = n < 2;
      concat.title = n < 2 ? tt("merge.needTwo") : tt("merge.openPicker");
    }
    syncMergeToolbar();
    const mux = $("btn-cinema-mux");
    if (mux) {
      const ready = Boolean(audio.score_id && audio.last_batch);
      mux.classList.toggle("hidden", !audio.score_id);
      mux.disabled = !ready;
      mux.textContent = ready
        ? tt("cinema.mux")
        : audio.score_id
          ? tt("cinema.muxWait")
          : tt("cinema.mux");
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
    if (filmWorkspace) renderFilmWorkspace();
  }

  let filmWorkspace = null;
  let filmSaveStatus = "Kaydedildi";
  let filmNavList = [];
  function renderFilmWorkspace() {
    if (!window.createFilmWorkspace) return;
    if (!filmWorkspace) {
      filmWorkspace = window.createFilmWorkspace({
        get: ensureCinema,
        jobs: () => state.jobs || [],
        toast,
        saveStatus: () => filmSaveStatus,
        films: () => filmNavList,
        switchFilm: async (id) => {
          if (!id || id === ensureCinema().film_id) return;
          await cinemaFilmAction("switch", id);
          await fillCinemaFilms();
          toast(tt("cinema.filmSwitched") || "Film değiştirildi");
        },
        openLibrary: () => {
          toast(tt("cinema.libSoon") || "Varlık kütüphanesi bu sürümde ayrı panelde.");
        },
        saveAllToLibrary: async () => {
          toast(tt("cinema.libSoon") || "Kütüphane aktarımı henüz bağlı değil.");
        },
        save: async () => {
          renderCinemaShots();
          if ((await saveCinema(true)) === false) {
            throw new Error("Kayıt başarısız; değişiklikler henüz diske yazılmadı.");
          }
        },
        select: (id) => {
          const card = document.querySelector(`#cinema-shots .cinema-shot[data-id="${CSS.escape(String(id))}"]`);
          card?.scrollIntoView({ block: "nearest", behavior: "smooth" });
          if (typeof openCinemaSceneModal === "function") openCinemaSceneModal(id);
        },
        filter: (chapter) => {
          document.querySelectorAll("#cinema-shots .cinema-shot").forEach((el) => {
            const s = cinemaShotById(el.dataset.id);
            el.hidden = !!s && (s.chapter || "Bölüm 1") !== chapter;
          });
        },
        produce: async () => {
          await produceCinema();
        },
        approve: async () => {
          throw new Error("Onay API bu sürümde yok — klasik shot listesinden devam et.");
        },
        importFilm: async () => {
          throw new Error("MD içe aktarma API bu sürümde yok.");
        },
      });
    }
    filmWorkspace.render();
  }

  function renderCinemaTimeline() {
    const c = ensureCinema();
    const shots = (c.shots || []).filter((shot) => (shot.text || "").trim());
    const shotDuration = Number(c.duration) || 5;
    const duration = shots.length * shotDuration;
    const scale = Math.max(1, duration);
    const ruler = $("cinema-timeline-ruler");
    if (ruler) {
      ruler.innerHTML = Array.from({ length: Math.ceil(scale / 5) + 1 }, (_, i) =>
        `<span style="left:${(i * 5 / scale) * 100}%">${i * 5}s</span>`
      ).join("");
    }
    const lanes = { video: $("cinema-timeline-video"), dialogue: $("cinema-timeline-dialogue"), music: $("cinema-timeline-music") };
    [lanes.video, lanes.dialogue, lanes.music].forEach((lane) => { if (lane) lane.innerHTML = ""; });
    let offset = 0;
    shots.forEach((shot, index) => {
      const left = (offset / scale) * 100;
      const width = (shotDuration / scale) * 100;
      const block = `<button type="button" class="timeline-clip" data-shot-id="${htmlEsc(shot.id)}" style="left:${left}%;width:${width}%" title="Shot ${index + 1} · ${shotDuration} sn"><b>${index + 1}</b><span>${htmlEsc(shot.text.slice(0, 32))}</span></button>`;
      if (lanes.video) lanes.video.insertAdjacentHTML("beforeend", block);
      if (lanes.dialogue && cinemaAudio().mode === "film") lanes.dialogue.insertAdjacentHTML("beforeend", block);
      offset += shotDuration;
    });
    if (lanes.music) lanes.music.innerHTML = cinemaAudio().score_name
      ? `<div class="timeline-audio-clip" style="width:100%"><span>♪ ${htmlEsc(cinemaAudio().score_name)}</span><em>waveform</em></div>`
      : `<div class="timeline-empty">${tt("cinema.timelineNoScore")}</div>`;
    const total = $("cinema-timeline-total");
    if (total) total.textContent = tf("cinema.timelineTotal", { clip: String(shotDuration), total: duration.toFixed(1).replace(".0", "") });
  }

  function syncCinemaShotJobs() {
    const host = $("cinema-shots");
    if (!host) return;
    if (!cinemaTypingShots()) {
      renderCinemaShots();
      return;
    }
    host.querySelectorAll(".cinema-shot").forEach((card, i) => {
      const meta = cinemaShotJobMeta(card.dataset.id, i);
      let badge = card.querySelector(".cinema-shot-job");
      if (!meta.label) {
        if (badge) badge.remove();
        return;
      }
      if (!badge) {
        badge = document.createElement("span");
        const head = card.querySelector(".cinema-shot-head");
        const del = card.querySelector(".cinema-shot-del");
        if (head && del) head.insertBefore(badge, del);
        else if (head) head.appendChild(badge);
      }
      badge.className = "cinema-shot-job" + meta.cls;
      badge.textContent = meta.label;
    });
  }

  function cinemaAssetCardsRoot(kind) {
    const meta = typeof cinemaKindMeta === "function" ? cinemaKindMeta(kind) : null;
    if (meta?.host) return $(meta.host);
    return kind === "character" ? $("cinema-chars") : $("cinema-locs");
  }

  function cinemaAssetCardsTyping(kind) {
    const root = cinemaAssetCardsRoot(kind);
    const active = document.activeElement;
    return !!(
      root &&
      active &&
      root.contains(active) &&
      active.matches("input:not([type=file]):not([type=button]), textarea, select")
    );
  }

  function renderCinemaAssetCards(kind, opts) {
    const force = !!(opts && opts.force);
    const meta = typeof cinemaKindMeta === "function" ? cinemaKindMeta(kind) : null;
    const key = meta?.key || (kind === "character" ? "characters" : "locations");
    const root = cinemaAssetCardsRoot(kind);
    if (!root) return;
    const items = ensureCinema()[key] || [];
    const domCount = root.querySelectorAll(".cinema-card").length;
    if (!force && cinemaAssetCardsTyping(kind) && domCount === items.length) return;
    root.innerHTML = items.map((x) => cinemaCardHtml(x, kind)).join("");
  }

  function renderCinema() {
    const c = hydrateCinemaStructuredShots(ensureCinema());
    if ($("cinema-title") && document.activeElement !== $("cinema-title")) {
      $("cinema-title").value = c.title || "";
    }
    if ($("cinema-role-script") && document.activeElement !== $("cinema-role-script")) {
      $("cinema-role-script").value = c.role_script || "";
    }
    renderCinemaPills();
    renderCinemaKnobs();
    renderCinemaAudio();
    renderCinemaTimeline();
    renderCinemaAssetCards("character");
    renderCinemaAssetCards("creature");
    renderCinemaAssetCards("location");
    if (typeof renderCinemaLibrary === "function") {
      try {
        renderCinemaLibrary("character");
        renderCinemaLibrary("creature");
        renderCinemaLibrary("location");
      } catch {
        /* ignore until library hosts exist */
      }
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
    syncCinemaStudioMode();
    if ($("cinema-hint") && cinemaStudioMode() === "assets") {
      $("cinema-hint").textContent =
        nC || nL || nS
          ? tf("cinema.hintCounts", { c: nC, l: nL, s: nS })
          : tt("cinema.hintAssets");
    }
    syncCinemaFold();
    scheduleCinemaPreview();
  }

  let cinemaPreviewTimer = 0;
  function scheduleCinemaPreview() {
    clearTimeout(cinemaPreviewTimer);
    cinemaPreviewTimer = setTimeout(() => void refreshCinemaPreview(), 450);
  }

  async function fillCinemaFilms() {
    const sel = $("cinema-film-select");
    if (!sel) return;
    try {
      const data = await fetch("/api/cinema/films").then((r) => r.json());
      const films = data.films || [];
      filmNavList = films.map((f) => ({
        id: f.id,
        title: f.title || f.id,
        meta: f.meta || "",
      }));
      const active = ensureCinema().film_id || data.active || "";
      sel.innerHTML = films
        .map((f) => {
          const on = f.id === active ? " selected" : "";
          return (
            '<option value="' +
            htmlEsc(f.id) +
            '"' +
            on +
            ">" +
            htmlEsc(f.title || f.id) +
            "</option>"
          );
        })
        .join("");
      if (!films.length) {
        sel.innerHTML = '<option value="">—</option>';
      }
      if (filmWorkspace) renderFilmWorkspace();
    } catch {
      /* ignore */
    }
  }

  async function refreshCinemaPreview() {
    const pre = $("cinema-preview-text");
    if (!pre) return;
    if (cinemaTypingShots() || cinemaTypingIn("cinema-role-script")) return;
    try {
      await saveCinema(true);
      const data = await fetch("/api/cinema/preview").then((r) => r.json());
      const shots = data.shots || [];
      if (!shots.length) {
        pre.textContent = tt("cinema.previewEmpty");
        return;
      }
      const bits = [];
      if (data.look) bits.push("LOOK\n" + data.look);
      shots.forEach((s, i) => {
        const calls = (s.calls || []).join(", ");
        bits.push(
          "SHOT " +
            (i + 1) +
            (calls ? " · " + calls : "") +
            (s.refs ? " · " + s.refs + " still" : "") +
            "\n" +
            (s.prompt || "")
        );
      });
      pre.textContent = bits.join("\n\n---\n\n");
    } catch {
      /* ignore */
    }
  }

  function applyCinemaSpeed(kind) {
    const c = ensureCinema();
    if (kind === "draft") {
      c.quality = "480";
      c.steps = 10;
      c.duration = Number($("cinema-duration")?.value) || c.duration || 5;
    } else {
      c.quality = "736";
      c.steps = 20;
    }
    if ($("steps")) $("steps").value = String(c.steps);
    setQuality(c.quality);
    renderCinemaKnobs();
    void saveCinema(true);
    toast(kind === "draft" ? tt("cinema.draftToast") : tt("cinema.finalToast"));
  }

  async function cinemaFilmAction(action, id) {
    const r = await fetch("/api/cinema/films", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, id: id || "" }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(errDetail(data));
    const base = emptyCinema();
    state.cinema = {
      ...base,
      ...data,
      setup: { ...base.setup, ...(data.setup || {}) },
      audio: { ...base.audio, ...(data.audio || {}) },
    };
    renderCinema();
    await fillCinemaFilms();
    void refreshCinemaPreview();
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
      creatures: stored.creatures !== false,
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
      .map((x) => (x.name || "").trim() || tt("cinema.untitled"))
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
    const nCr = (c.creatures || []).length;
    const nL = (c.locations || []).length;
    if ($("cinema-char-count")) $("cinema-char-count").textContent = String(nC);
    if ($("cinema-creature-count")) $("cinema-creature-count").textContent = String(nCr);
    if ($("cinema-loc-count")) $("cinema-loc-count").textContent = String(nL);
    if ($("cinema-char-summary")) {
      $("cinema-char-summary").innerHTML = cinemaFoldSummaryHtml(
        c.characters,
        tt("cinema.noChars")
      );
    }
    if ($("cinema-creature-summary")) {
      $("cinema-creature-summary").innerHTML = cinemaFoldSummaryHtml(
        c.creatures,
        tt("cinema.noCreatures") || "Yaratık yok"
      );
    }
    if ($("cinema-loc-summary")) {
      $("cinema-loc-summary").innerHTML = cinemaFoldSummaryHtml(c.locations, tt("cinema.noLocs"));
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
    const key = cinemaKindMeta(kind).key;
    const aid = String(id || "").trim();
    return (state.cinema[key] || []).find((x) => String(x.id || "") === aid);
  }

  async function deleteCinemaAsset(kind, id) {
    const aid = String(id || "").trim();
    if (!aid) return;
    if (!tConfirm("confirm.deleteCard")) return;
    clearTimeout(cinemaPreviewTimer);
    cinemaSaveGen += 1;
    abortCinemaSaves();
    const assetKey = `${kind}:${aid}`;
    cinemaAssetVersions.set(assetKey, (cinemaAssetVersions.get(assetKey) || 0) + 1);
    const key = cinemaKindMeta(kind).key;
    const c = ensureCinema();
    const removedName = String((cinemaItem(kind, aid) || {}).name || "").trim();
    if (kind === "character" && String(state.selectedCharacter?.id || "") === aid) {
      closeCinemaCharacterModal();
    }
    c[key] = (c[key] || []).filter((x) => String(x.id || "") !== aid);
    renderCinemaAssetCards(kind, { force: true });
    renderCinema();
    clearTimeout(cinemaPreviewTimer);
    const path =
      kind === "character"
        ? `/api/cinema/character/${encodeURIComponent(aid)}`
        : `/api/cinema/location/${encodeURIComponent(aid)}`;
    try {
      const r = await fetch(path, { method: "DELETE" });
      const data = await r.json().catch(() => ({}));
      // 404 = already gone on disk; still lock the filtered local list via PUT
      if (!r.ok && r.status !== 404) throw new Error(errDetail(data) || "silinemedi");
      // Persist filtered cards so a late saveCinema/PATCH cannot resurrect them
      await saveCinema(true);
      if ((cinemaAssetVersions.get(assetKey) || 0) > 0) {
        cinemaAssetVersions.delete(assetKey);
      }
      if (removedName) scrubDirectorBriefName(removedName);
      toast(kind === "character" ? tt("cinema.charDeleted") : tt("cinema.locDeleted"));
    } catch (e) {
      if ((cinemaAssetVersions.get(assetKey) || 0) > 0) {
        cinemaAssetVersions.delete(assetKey);
      }
      toast(String(e.message || e));
      await loadCinema();
    }
  }

  function cinemaStudioMode() {
    return state.cinemaStudioMode === "assets" ? "assets" : "seamless";
  }

  function readCinemaStudioMode() {
    try {
      const s = localStorage.getItem("h3-cinema-mode");
      if (s === "assets" || s === "seamless") return s;
    } catch {
      /* ignore */
    }
    return "seamless";
  }

  function setCinemaStudioMode(mode, { persist = true } = {}) {
    state.cinemaStudioMode = mode === "assets" ? "assets" : "seamless";
    state.filmMode = state.cinemaStudioMode === "seamless";
    if (state.cinema) state.cinema.studio_mode = state.cinemaStudioMode;
    if (persist) {
      try {
        localStorage.setItem("h3-cinema-mode", state.cinemaStudioMode);
      } catch {
        /* ignore */
      }
    }
    syncCinemaStudioMode();
    if ($("view-cinema") && !$("view-cinema").classList.contains("hidden")) {
      renderCinemaShots();
    }
  }

  function syncCinemaStudioMode() {
    const mode = cinemaStudioMode();
    const panel = document.querySelector("#view-cinema .cinema-panel");
    panel?.classList.toggle("is-mode-seamless", mode === "seamless");
    panel?.classList.toggle("is-mode-assets", mode === "assets");
    document.querySelectorAll("#cinema-studio-mode [data-cinemamode]").forEach((btn) => {
      btn.classList.toggle("on", btn.dataset.cinemamode === mode);
    });
    const seam = $("cinema-seamless");
    if (seam) {
      if (mode === "seamless") {
        seam.checked = !!state.multishot;
        seam.disabled = !state.multishot;
      } else {
        seam.checked = false;
        seam.disabled = true;
      }
    }
    const modeHint = $("cinema-mode-hint");
    if (modeHint) {
      modeHint.textContent =
        mode === "seamless"
          ? state.multishot
            ? tt("cinema.modeSeamlessHint")
            : tt("cinema.modeSeamlessNeedPack")
          : tt("cinema.modeAssetsHint");
    }
    const hint = $("cinema-hint");
    if (hint) {
      hint.textContent = mode === "seamless" ? tt("cinema.hintSeamless") : tt("cinema.hintAssets");
    }
    const addCont = $("btn-cinema-add-cont");
    if (addCont) addCont.classList.toggle("hidden", mode === "seamless");
    const addT2v = $("btn-cinema-add-t2v");
    if (addT2v) addT2v.textContent = mode === "seamless" ? tt("cinema.addShot") : tt("cinema.addT2v");
  }
  window.syncCinemaStudioMode = syncCinemaStudioMode;

  async function planCinemaWithDirector() {
    await saveCinema(true);
    state.cinemaDirector = true;
    setDirectorModal(true);
    setDirectorTab("chat");
    appendDirectorMsg("assistant", tt("cinema.planOpen"));
    toast(tt("cinema.planToast"));
    $("director-msg")?.focus();
  }

function cinemaKindMeta(kind) {
    const k = String(kind || "character").toLowerCase();
    if (k === "location") {
      return {
        kind: "location",
        key: "locations",
        host: "cinema-locs",
        libHost: "cinema-loc-library",
        api: "/api/cinema/location",
        fold: "locations",
      };
    }
    if (k === "creature") {
      return {
        kind: "creature",
        key: "creatures",
        host: "cinema-creatures",
        libHost: "cinema-creature-library",
        api: "/api/cinema/creature",
        fold: "creatures",
      };
    }
    return {
      kind: "character",
      key: "characters",
      host: "cinema-chars",
      libHost: "cinema-char-library",
      api: "/api/cinema/character",
      fold: "characters",
    };
  }

function filmHasStillCards() {
    const c = ensureCinema();
    return ["characters", "creatures", "locations"].some((key) =>
      (c[key] || []).some((a) => cinemaAssetImages(a).length || (a.name || "").trim())
    );
  }

function setCinemaAssetTab(kind, tab) {
    const k = cinemaKindMeta(kind).kind;
    const t = tab === "create" ? "create" : tab === "library" ? "library" : "list";
    document.querySelectorAll(`.cinema-asset-tabs[data-asset-kind="${k}"] .chip`).forEach((btn) => {
      btn.classList.toggle("on", btn.dataset.assetTab === t);
    });
    document.querySelectorAll(`.cinema-asset-tab-panel[data-asset-kind="${k}"]`).forEach((panel) => {
      panel.classList.toggle("hidden", panel.dataset.assetPanel !== t);
    });
    if (t === "library") void loadCinemaLibrary();
  }

function cinemaSheetRefUi(kind) {
    const k = cinemaKindMeta(kind).kind;
    if (k === "location") {
      return {
        key: "location",
        preview: "cinema-loc-ref-preview",
        name: "cinema-loc-ref-name",
        clear: "btn-cinema-loc-ref-clear",
        file: "cinema-loc-ref-file",
        readyKey: "cinema.sheetPlaceReady",
      };
    }
    if (k === "creature") {
      return {
        key: "creature",
        preview: "cinema-creature-ref-preview",
        name: "cinema-creature-ref-name",
        clear: "btn-cinema-creature-ref-clear",
        file: "cinema-creature-ref-file",
        readyKey: "cinema.sheetCreatureReady",
      };
    }
    return {
      key: "character",
      preview: "cinema-char-face-preview",
      name: "cinema-char-face-name",
      clear: "btn-cinema-char-face-clear",
      file: "cinema-char-face-file",
      readyKey: "cinema.sheetFaceReady",
    };
  }


function renderCinemaSheetRefPreview(kind) {
    const ui = cinemaSheetRefUi(kind);
    const item = state.cinemaSheetRefs[ui.key];
    const preview = $(ui.preview);
    const nameEl = $(ui.name);
    const clearBtn = $(ui.clear);
    if (preview) {
      if (item && item.url) {
        preview.classList.remove("hidden");
        if (preview.tagName === "IMG") {
          preview.src = item.url;
        } else {
          preview.innerHTML = '<img src="' + item.url + '" alt="ref" />';
        }
      } else {
        preview.classList.add("hidden");
        if (preview.tagName === "IMG") preview.removeAttribute("src");
        else preview.innerHTML = "";
      }
    }
    if (nameEl) {
      nameEl.textContent = item
        ? item.filename || item.name || tt("pick.ready") || "Hazır"
        : tt("pick.none") || "Seçilmedi";
      nameEl.classList.toggle("has-file", !!item);
    }
    clearBtn?.classList.toggle("hidden", !item);
  }

async function clearCinemaSheetRef(kind) {
    const ui = cinemaSheetRefUi(kind);
    const item = state.cinemaSheetRefs[ui.key];
    if (item) {
      try {
        await deleteUploadedMedia(item);
      } catch {
        /* ignore */
      }
    }
    state.cinemaSheetRefs[ui.key] = null;
    const input = $(ui.file);
    if (input) input.value = "";
    clearFilePickLabel(input);
    renderCinemaSheetRefPreview(ui.key);
  }

async function generateCinemaSheet(kind) {
    const meta = cinemaKindMeta(kind);
    const ids =
      meta.kind === "location"
        ? {
            name: "cinema-loc-create-name",
            notes: "cinema-loc-create-notes",
            status: "cinema-loc-create-status",
            btn: "btn-cinema-create-loc",
            needKey: "cinema.sheetNeedLocName",
          }
        : meta.kind === "creature"
          ? {
              name: "cinema-creature-create-name",
              notes: "cinema-creature-create-notes",
              status: "cinema-creature-create-status",
              btn: "btn-cinema-create-creature",
              needKey: "cinema.sheetNeedCreatureName",
            }
          : {
              name: "cinema-char-create-name",
              notes: "cinema-char-create-notes",
              status: "cinema-char-create-status",
              btn: "btn-cinema-create-char",
              needKey: "cinema.sheetNeedCharName",
            };
    const nameEl = $(ids.name);
    const notesEl = $(ids.notes);
    const statusEl = $(ids.status);
    const btn = $(ids.btn);
    const name = (nameEl?.value || "").trim();
    const notes = (notesEl?.value || "").trim();
    if (!name) {
      toast(tt(ids.needKey));
      return;
    }
    if (btn) btn.disabled = true;
    if (statusEl) statusEl.textContent = tt("cinema.sheetQueuing");
    try {
      const cine = ensureCinema();
      const setup = cine.setup || {};
      const style =
        state.projectStyle ||
        (setup.style && setup.style !== "auto" ? setup.style : null) ||
        null;
      const quality = normalizeQuality(
        cine.quality || state.quality || "736"
      );
      const steps =
        Number($("cinema-steps")?.value) ||
        Number($("steps")?.value) ||
        Number(cine.steps) ||
        18;
      const duration =
        Number($("cinema-duration")?.value) ||
        Number(cine.duration) ||
        Number(state.duration) ||
        5;
      const sheetRef = state.cinemaSheetRefs[meta.kind];
      const payload = {
        kind: meta.kind,
        name,
        notes,
        style,
        duration,
        quality,
        steps,
        aspect: state.aspect || "16:9",
      };
      if (sheetRef?.name) {
        payload.ref_image = sheetRef.name;
        payload.ref_images = [sheetRef.name];
      }
      const r = await fetch("/api/cinema/generate-sheet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      const asset = data.asset;
      if (asset && asset.id) {
        const c = ensureCinema();
        const list = Array.isArray(c[meta.key]) ? c[meta.key].slice() : [];
        const i = list.findIndex((x) => String(x.id) === String(asset.id));
        if (i >= 0) list[i] = { ...list[i], ...asset };
        else list.push(asset);
        c[meta.key] = list;
      }
      setCinemaAssetTab(meta.kind, "list");
      setCinemaFold(meta.fold, true);
      renderCinema();
      state.prodLane = "director";
      setProdLane("director");
      await refreshJobs();
      if (statusEl) {
        statusEl.textContent = tf("cinema.sheetQueued", {
          name,
          id: String(data.job?.id || "").slice(0, 8),
        });
      }
      toast(tf("cinema.sheetQueuedToast", { name }));
    } catch (e) {
      if (statusEl) statusEl.textContent = String(e.message || e);
      toast(String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
    }
  }

async function loadCinemaLibrary() {
    try {
      const data = await fetch("/api/cinema/library").then((r) => r.json());
      state.cinemaLibrary = {
        characters: Array.isArray(data.characters) ? data.characters : [],
        locations: Array.isArray(data.locations) ? data.locations : [],
        creatures: Array.isArray(data.creatures) ? data.creatures : [],
      };
    } catch {
      state.cinemaLibrary = state.cinemaLibrary || {
        characters: [],
        locations: [],
        creatures: [],
      };
    }
    renderCinemaLibrary("character");
    renderCinemaLibrary("creature");
    renderCinemaLibrary("location");
  }

function cinemaLibraryCardHtml(item, kind) {
    const imgs = cinemaAssetImages(item);
    const thumb = imgs[0];
    const src = thumb
      ? htmlEsc(thumb.url || cinemaRefUrl(thumb.file))
      : "";
    return (
      '<div class="cinema-lib-card" data-id="' +
      htmlEsc(item.id) +
      '" data-kind="' +
      kind +
      '">' +
      (src
        ? '<img class="cinema-lib-thumb" src="' +
          src +
          '" alt="" data-full="' +
          src +
          '" data-file="' +
          htmlEsc(thumb?.file || "") +
          '" data-name="' +
          htmlEsc((item.name || "asset") + ".png") +
          '" />'
        : '<div class="cinema-lib-thumb is-empty"></div>') +
      '<div class="cinema-lib-meta">' +
      "<b>" +
      htmlEsc(item.name || tt("cinema.untitled")) +
      "</b>" +
      '<span class="muted">' +
      htmlEsc((item.notes || "").slice(0, 80)) +
      "</span>" +
      '<div class="row-btns">' +
      '<button type="button" class="cta cinema-lib-pull">' +
      htmlEsc(tt("cinema.pullLib")) +
      "</button>" +
      (item._inFilm
        ? '<span class="muted">' + htmlEsc(tt("cinema.libInFilm") || "Filmde") + "</span>"
        : "") +
      '<button type="button" class="btn-ghost cinema-lib-del">' +
      htmlEsc(tt("cinema.del")) +
      "</button>" +
      "</div></div></div>"
    );
  }

function renderCinemaLibrary(kind) {
    const meta = cinemaKindMeta(kind);
    const root = $(meta.libHost);
    if (!root) return;
    const filmItems = ensureCinema()[meta.key] || [];
    const inFilm = new Set(
      filmItems.flatMap((x) =>
        [String(x.library_id || ""), String(x.id || ""), String(x.name || "").toLowerCase()].filter(Boolean)
      )
    );
    const items = ((state.cinemaLibrary && state.cinemaLibrary[meta.key]) || []).map((x) => ({
      ...x,
      _inFilm:
        inFilm.has(String(x.id || "")) ||
        inFilm.has(String(x.library_id || "")) ||
        inFilm.has(String(x.name || "").toLowerCase()),
    }));
    if (!items.length) {
      root.innerHTML =
        '<p class="muted cinema-lib-empty">' + htmlEsc(tt("cinema.libEmpty")) + "</p>";
      return;
    }
    root.innerHTML = items.map((x) => cinemaLibraryCardHtml(x, meta.kind)).join("");
  }

async function saveAllCinemaAssetsToLibrary() {
    const c = ensureCinema();
    let n = 0;
    for (const kind of ["character", "creature", "location"]) {
      const meta = cinemaKindMeta(kind);
      for (const asset of c[meta.key] || []) {
        if (!asset?.id) continue;
        try {
          await saveCinemaAssetToLibrary(meta.kind, asset.id, { quiet: true });
          n += 1;
        } catch {
          /* keep going */
        }
      }
    }
    await loadCinemaLibrary();
    toast(tf("cinema.savedAllLib", { n: String(n) }));
    return n;
  }

function openCinemaAssetLibrary() {
    const grid = document.querySelector("#view-cinema .cinema-grid");
    if (grid) grid.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setCinemaAssetTab("character", "list");
    setCinemaAssetTab("creature", "list");
    setCinemaAssetTab("location", "list");
    setCinemaFold("characters", true);
    setCinemaFold("creatures", true);
    setCinemaFold("locations", true);
    void loadCinemaLibrary();
  }

async function saveCinemaAssetToLibrary(kind, assetId, opts) {
    const meta = cinemaKindMeta(kind);
    const r = await fetch("/api/cinema/library/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: meta.kind, asset_id: assetId }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(errDetail(data));
    if (data.library) {
      state.cinemaLibrary = state.cinemaLibrary || {
        characters: [],
        locations: [],
        creatures: [],
      };
      state.cinemaLibrary.characters =
        data.library.characters || state.cinemaLibrary.characters;
      state.cinemaLibrary.locations =
        data.library.locations || state.cinemaLibrary.locations;
      state.cinemaLibrary.creatures =
        data.library.creatures || state.cinemaLibrary.creatures;
    } else {
      await loadCinemaLibrary();
    }
    renderCinemaLibrary(meta.kind);
    if (!opts?.quiet) toast(tf("cinema.savedLib", { name: data.asset?.name || "" }));
    return data.asset;
  }

async function pullCinemaLibraryAsset(kind, libraryId) {
    const meta = cinemaKindMeta(kind);
    const r = await fetch("/api/cinema/library/pull", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: meta.kind, library_id: libraryId }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(errDetail(data));
    if (data.cinema) {
      const base = emptyCinema();
      state.cinema = {
        ...base,
        ...data.cinema,
        setup: { ...base.setup, ...(data.cinema.setup || {}) },
        audio: { ...base.audio, ...(data.cinema.audio || {}) },
        characters: data.cinema.characters || [],
        locations: data.cinema.locations || [],
        creatures: data.cinema.creatures || [],
      };
      state.cinemaLoaded = true;
    } else {
      await loadCinema();
    }
    setCinemaAssetTab(meta.kind, "library");
    setCinemaFold(meta.fold, true);
    renderCinema();
    if (filmWorkspace) filmWorkspace.render();
    toast(tf("cinema.pulledLib", { name: data.asset?.name || "" }));
  }


  async function openCinemaStudio() {
    if (state.studioWorkspace !== "director") {
      state.studioWorkspace = "director";
      document.body.classList.add("ws-director");
      document.body.classList.remove("ws-scene");
      document.querySelectorAll("#workspace-switch .chip[data-ws]").forEach((btn) => {
        const on = btn.dataset.ws === "director";
        btn.classList.toggle("on", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
      });
      $("panel-workspace-director")?.classList.add("hidden");
      $("panel-workspace-scene")?.classList.add("hidden");
      refreshStudioWorkspaceChrome();
      setProdLane("director");
    }
    $("view-gallery")?.classList.add("hidden");
    $("view-settings")?.classList.add("hidden");
    $("view-support")?.classList.add("hidden");
    setDirectorLlmOpen(false);
    setDirectorOpen(false);
    state.cinemaDirector = true;
    state.cinemaStudioMode = readCinemaStudioMode();
    state.filmMode = state.cinemaStudioMode === "seamless";
    $("view-cinema")?.classList.remove("hidden");
    document.body.classList.add("cinema-dock-open");
    if (!state.loraCatalog || !state.loraCatalog.length) {
      try {
        await loadLoras();
      } catch {
        /* ignore */
      }
    }
    await loadCinema();
    void loadCinemaLibrary();
    if (typeof filmHasStillCards === "function" && filmHasStillCards()) {
      setCinemaStudioMode("assets", { persist: false });
    } else {
      syncCinemaStudioMode();
    }
    renderFilmWorkspace();
  }

  function closeCinemaStudio() {
    $("view-cinema")?.classList.add("hidden");
    document.body.classList.remove("cinema-dock-open");
    state.cinemaDirector = false;
    void saveCinema(true);
  }

  async function addCinemaAsset(kind) {
    const meta = typeof cinemaKindMeta === "function" ? cinemaKindMeta(kind) : null;
    const path = meta?.api || (kind === "character" ? "/api/cinema/character" : kind === "creature" ? "/api/cinema/creature" : "/api/cinema/location");
    const key = meta?.key || (kind === "character" ? "characters" : kind === "creature" ? "creatures" : "locations");
    const fold = meta?.fold || (kind === "character" ? "characters" : kind === "creature" ? "creatures" : "locations");
    setCinemaFold(fold, true);
    clearTimeout(cinemaPreviewTimer);
    cinemaSaveGen += 1;
    abortCinemaSaves();
    // Flush any pending local deletes to disk before creating a new card
    try {
      await saveCinema(true);
    } catch {
      /* continue — create may still work */
    }
    try {
      const r = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "", trigger: "" }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      const c = ensureCinema();
      const list = Array.isArray(c[key]) ? c[key].slice() : [];
      if (data && data.id) {
        const i = list.findIndex((x) => String(x.id || "") === String(data.id));
        if (i >= 0) list[i] = data;
        else list.push(data);
        c[key] = list;
      }
      setCinemaFold(fold, true);
      renderCinemaAssetCards(kind, { force: true });
      renderCinema();
      const card = document.querySelector(
        (kind === "character" ? "#cinema-chars" : "#cinema-locs") +
          ' .cinema-card[data-id="' +
          (data.id || "") +
          '"]'
      );
      const name = card?.querySelector("[data-field=name]");
      card?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      name?.focus();
    } catch (e) {
      toast(String(e.message || e));
      await loadCinema();
    }
  }

  function deleteCinemaShot(shotId) {
    const id = String(shotId || "").trim();
    if (!id) return;
    cinemaForceLocalShots = true;
    cinemaSaveGen += 1;
    flushCinemaFields();
    const c = ensureCinema();
    const before = (c.shots || []).length;
    c.shots = (c.shots || []).filter((s) => String(s.id) !== id);
    if (c.shots.length === before) {
      $("cinema-shots")
        ?.querySelectorAll(".cinema-shot")
        .forEach((card) => {
          if (card.dataset.id === id) card.remove();
        });
    }
    if (!c.shots.length) c.script = "";
    const active = document.activeElement;
    if (active && $("cinema-shots")?.contains(active)) active.blur();
    renderCinemaShots();
    renderCinema();
    void saveCinema(true);
  }

  function duplicateCinemaShot(shotId) {
    const c = ensureCinema();
    const shots = c.shots || [];
    const index = shots.findIndex((shot) => String(shot.id) === String(shotId));
    if (index < 0) return;
    const source = shots[index];
    const clone = {
      ...source,
      id: typeof crypto?.randomUUID === "function"
        ? crypto.randomUUID()
        : `shot-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      structured: source.structured ? { ...source.structured } : undefined,
      enabled: source.enabled !== false,
    };
    cinemaForceLocalShots = true;
    shots.splice(index + 1, 0, clone);
    renderCinemaShots();
    renderCinema();
    void saveCinema(true);
  }

  async function patchCinemaAsset(kind, id, fields) {
    const aid = String(id || "").trim();
    if (!aid) return false;
    // Deleted cards must not be re-created by a late PATCH
    if (!cinemaItem(kind, aid)) return false;
    const assetKey = `${kind}:${aid}`;
    const version = nextCinemaAssetVersion(kind, aid);
    const item = cinemaItem(kind, aid);
    if (item) Object.assign(item, fields);
    const path =
      kind === "character"
        ? `/api/cinema/character/${encodeURIComponent(aid)}`
        : `/api/cinema/location/${encodeURIComponent(aid)}`;
    try {
      const r = await fetch(path, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fields),
      });
      const data = await r.json().catch(() => ({}));
      if (r.status === 404) return false;
      if (!r.ok) throw new Error(errDetail(data));
      if ((cinemaAssetVersions.get(assetKey) || 0) !== version) return false;
      if (!cinemaItem(kind, aid)) return false;
      const key = kind === "character" ? "characters" : "locations";
      const idx = (state.cinema[key] || []).findIndex((x) => String(x.id || "") === aid);
      if (idx >= 0) state.cinema[key][idx] = data;
      return true;
    } catch (e) {
      if ((cinemaAssetVersions.get(assetKey) || 0) !== version) return false;
      toast(String(e.message || e));
      return false;
    }
  }

  async function uploadCinemaImage(kind, id, files) {
    const list = files ? [...files].filter(Boolean) : [];
    if (!list.length) return;
    const item = cinemaItem(kind, id);
    const have = cinemaAssetImages(item).length;
    const room = Math.max(0, 5 - have);
    if (!room) {
      toast(tt("cinema.imgFull"));
      return;
    }
    const take = list.slice(0, room);
    const images = cinemaAssetImages(item).map((x) => ({
      name: x.name || "",
      file: x.file,
      url: x.url,
    }));
    for (const file of take) {
      toast(tf("toast.uploading", { name: file.name }));
      const previewUrl = URL.createObjectURL(file);
      images.push({ name: file.name, file: `preview:${file.name}`, url: previewUrl });
      if (item) {
        item.images = images.slice();
        renderCinemaAssetCards(kind, { force: true });
        renderCinema();
      }
      try {
        const fd = new FormData();
        fd.append("file", file);
        const r = await fetch("/api/refs/upload", { method: "POST", body: fd });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errDetail(data));
        images.splice(images.length - 1, 1);
        URL.revokeObjectURL(previewUrl);
        images.push({ name: "", file: data.name, url: data.url });
        await patchCinemaAsset(kind, id, { images });
        renderCinemaAssetCards(kind, { force: true });
        renderCinema();
      } catch (e) {
        images.splice(images.length - 1, 1);
        URL.revokeObjectURL(previewUrl);
        if (item) {
          item.images = images.slice();
          renderCinemaAssetCards(kind, { force: true });
          renderCinema();
        }
        toast(String(e.message || e));
        return;
      }
    }
    await patchCinemaAsset(kind, id, { images });
    renderCinemaAssetCards(kind, { force: true });
    renderCinema();
    toast(tt("cinema.imgBound"));
  }

  async function removeCinemaImage(kind, id, file) {
    const item = cinemaItem(kind, id);
    if (!item) return;
    const images = cinemaAssetImages(item).filter((x) => x.file !== file);
    const saved = await patchCinemaAsset(kind, id, { images, image: images[0]?.file || "", url: images[0]?.url || "" });
    if (!saved) return;
    if (file && !String(file).startsWith("preview:")) {
      const r = await fetch(`/api/refs/${encodeURIComponent(file)}`, { method: "DELETE" });
      if (!r.ok && r.status !== 404) {
        const data = await r.json().catch(() => ({}));
        throw new Error(errDetail(data) || tt("err.imageDeleteFailed"));
      }
    }
    renderCinema();
  }

  async function ingestCinemaRole() {
    const text = ($("cinema-role-script")?.value || "").trim();
    ensureCinema().role_script = text;
    const c = ensureCinema();
    if (c.duration) setDuration(Number(c.duration) || state.duration || 5);
    const purpose = c.setup && c.setup.purpose && c.setup.purpose !== "auto" ? c.setup.purpose : "";
    if (purpose) {
      state.projectPurpose = purpose;
      state.projectSilent = purpose === "music_video" || cinemaAudio().mode === "silent";
    }
    const style = c.setup && c.setup.style && c.setup.style !== "auto" ? c.setup.style : "";
    if (style) state.projectStyle = style;
    syncProjectChips();
    state.cinemaDirector = true;
    await saveCinema(true);
    setDirectorModal(true);
    appendDirectorMsg(
      "assistant",
      tt("cinema.directorOpen")
    );
    const msg = text
      ? tt("cinema.directorBuild") + "\n\n" + text
      : tt("cinema.directorAsk");
    await directorSend(msg);
  }

  async function generateCinemaShots() {
    const btn = $("btn-cinema-generate-shots");
    if (btn) btn.disabled = true;
    try {
      await saveCinema(true);
      const c = ensureCinema();
      const chars = (c.characters || []).filter((x) => String(x.name || "").trim());
      const locs = (c.locations || []).filter((x) => String(x.name || "").trim());
      if (!chars.length && !locs.length) {
        toast(tt("cinema.needCast"));
        return;
      }
      toast(tt("cinema.writingShots"));
      const r = await fetch("/api/cinema/generate-shots", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          duration: Number($("cinema-duration")?.value) || c.duration || state.duration || 5,
          logline: (c.title || "").trim() || null,
          prompt_rewriter_enabled: !!$("prompt-rewriter-enabled")?.checked,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (data.cinema) {
        const base = emptyCinema();
        state.cinema = {
          ...base,
          ...data.cinema,
          setup: { ...base.setup, ...(data.cinema.setup || {}) },
          audio: { ...base.audio, ...(data.cinema.audio || {}) },
        };
        renderCinema();
      }
      toast(tf("cinema.shotsWritten", { n: data.shot_count || 0 }));
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function runCinemaDirector() {
    const btn = $("btn-cinema-director");
    if (btn) btn.disabled = true;
    try {
      await saveCinema(true);
      const c = ensureCinema();
      const chars = (c.characters || []).filter((x) => String(x.name || "").trim());
      const locs = (c.locations || []).filter((x) => String(x.name || "").trim());
      const role = String(c.role_script || $("cinema-role-script")?.value || "").trim();
      if (!chars.length && !locs.length && role.length < 40) {
        toast(tt("cinema.needCastOrRole"));
        return;
      }
      toast(tt("cinema.directorRunning"));
      const clip = Number($("cinema-duration")?.value) || c.duration || state.duration || 5;
      const r = await fetch("/api/cinema/director", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({
          stream: true,
          duration: clip,
          logline: (c.title || "").trim() || null,
          prompt_rewriter_enabled: !!$("prompt-rewriter-enabled")?.checked,
        }),
      });
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        throw new Error(errDetail(data) || tt("err.directorStream"));
      }
      const reader = r.body?.getReader();
      if (!reader) throw new Error(tt("err.directorStream"));
      const dec = new TextDecoder();
      let buf = "";
      let result = null;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const block of parts) {
          const line = block.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          let ev;
          try {
            ev = JSON.parse(line.slice(6));
          } catch {
            continue;
          }
          if (ev.type === "status" && ev.text) {
            toast(String(ev.text));
          } else if (ev.type === "error") {
            throw new Error(ev.detail || tt("err.directorStream"));
          } else if (ev.type === "result" && ev.data) {
            result = ev.data;
          }
        }
      }
      if (!result || !result.cinema) {
        throw new Error(tt("cinema.directorFailed"));
      }
      const base = emptyCinema();
      state.cinema = {
        ...base,
        ...result.cinema,
        setup: { ...base.setup, ...(result.cinema.setup || {}) },
        audio: { ...base.audio, ...(result.cinema.audio || {}) },
      };
      renderCinema();
      toast(tf("cinema.directorDone", { n: result.shot_count || 0 }));
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function syncFilmModeSummary() {
    const total = Number($("cinema-film-total")?.value) || 60;
    const clip = Number($("cinema-duration")?.value) || Number(ensureCinema().duration) || 10;
    const seg = Number($("cinema-film-segment")?.value) || 6;
    const shots = Math.max(1, Math.ceil(total / clip));
    const segs = Math.max(1, Math.ceil(shots / seg));
    const el = $("cinema-film-summary");
    if (el) {
      el.textContent = tf("filmMode.summary", {
        total: String(total),
        clip: String(clip),
        sec: tt("sec"),
        shots: String(shots),
        segs: String(segs),
        segSize: String(seg),
      });
    }
  }

  function syncFilmStillsWarn(names) {
    const el = $("cinema-film-stills-warn");
    if (!el) return;
    const list = Array.isArray(names) ? names.filter(Boolean) : [];
    if (!list.length) {
      el.classList.add("hidden");
      el.textContent = "";
      return;
    }
    el.classList.remove("hidden");
    el.textContent = tf("filmMode.missingStills", { names: list.join(", ") });
  }

  async function produceCinemaFilm(opts) {
    opts = opts || {};
    const btn = $("btn-cinema-produce-film");
    if (btn) btn.disabled = true;
    state.filmPlanBusy = true;
    try {
      await saveCinema(true);
      const cine = ensureCinema();
      const shots = (cine.shots || []).filter(
        (s) => (s.text || "").trim() && s.enabled !== false
      );
      if (!shots.length) {
        toast(tt("filmMode.needShots"));
        return;
      }
      const audio = cinemaAudio();
      const filmMode = audio.mode !== "silent";
      const purpose =
        cine.setup && cine.setup.purpose && cine.setup.purpose !== "auto"
          ? cine.setup.purpose
          : "short_film";
      if ($("cinema-lora-select") && $("lora-select")) {
        $("lora-select").value = $("cinema-lora-select").value;
      }
      const r = await fetch("/api/cinema/produce-film", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          total_sec: Number($("cinema-film-total")?.value) || 60,
          clip_sec: Number($("cinema-duration")?.value) || cine.duration || 10,
          segment_size: Number($("cinema-film-segment")?.value) || 6,
          auto_concat: !!$("cinema-film-auto-concat")?.checked,
          reset_plan: opts.reset_plan !== false && !opts.advance,
          advance: !!opts.advance,
          segment_index: opts.segment_index,
          shots,
          setup: cine.setup || {},
          aspect: state.aspect || "16:9",
          quality: normalizeQuality(cine.quality || state.quality || "736"),
          steps: Number($("cinema-steps")?.value) || cine.steps || 20,
          seed: Number($("cinema-seed")?.value) || -1,
          silent_audio: !filmMode,
          purpose,
          brief: state.directorBrief || undefined,
          post_pass: state.postPass || "",
          ...collectLoraPayload(),
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (data.cinema_batch) {
        audio.last_batch = data.cinema_batch;
        await saveCinema(true);
        renderCinemaAudio();
      }
      syncFilmStillsWarn(data.missing_stills);
      if (Array.isArray(data.missing_stills) && data.missing_stills.length) {
        toast(tf("filmMode.missingStillsToast", { names: data.missing_stills.join(", ") }));
      }
      toast(
        opts.advance
          ? tf("filmMode.segmentQueued", {
              seg: String((data.segment_index || 0) + 1),
              total: String(data.segment_count || 1),
            })
          : tf("filmMode.started", {
              seg: String((data.segment_index || 0) + 1),
              total: String(data.segment_count || 1),
              n: String(data.count || 0),
            })
      );
      setProdLane("director");
      await refreshJobs();
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      state.filmPlanBusy = false;
      if (btn) btn.disabled = false;
    }
  }

  async function pollFilmPlan() {
    if (state.filmPlanBusy) return;
    try {
      const st = await fetch("/api/cinema/film-plan").then((r) => r.json());
      const plan = st.plan;
      if (!plan || plan.status === "concat" || plan.concat_done) return;
      syncFilmStillsWarn(st.missing_stills);
      const autoConcat = !!$("cinema-film-auto-concat")?.checked;
      const segCount = Number(plan.segment_count) || 1;
      const cur = Number(plan.current_segment) || 0;
      if (st.segment_complete && cur < segCount - 1) {
        state.filmPlanBusy = true;
        await produceCinemaFilm({ advance: true, reset_plan: false });
        state.filmPlanBusy = false;
        return;
      }
      if (st.all_complete && autoConcat && !plan.concat_done) {
        if (!state._filmConcatAsked) {
          state._filmConcatAsked = true;
          const ok = tConfirm("confirm.filmConcat");
          if (!ok) return;
        }
        state.filmPlanBusy = true;
        const r = await fetch("/api/cinema/film-plan/concat", { method: "POST" });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errDetail(data));
        toast(tt("filmMode.concatOk"));
        if (data.final_url) window.open(data.final_url, "_blank");
        renderCinemaAudio();
        state.filmPlanBusy = false;
      }
    } catch {
      state.filmPlanBusy = false;
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
          id: s.id,
          text: (s.text || "").trim(),
          mode: s.mode === "continue" ? "continue" : "t2v",
          enabled: s.enabled !== false,
        }))
        .filter((s) => s.text && s.enabled);
      if (!shots.length) {
        toast(tt("cinema.addShotFirst"));
        return;
      }
      const studioMode = cinemaStudioMode();
      const wantSeamless = studioMode === "seamless";
      if (wantSeamless) {
        if (!state.multishot) {
          toast(tt("cinema.modeSeamlessNeedPack"));
          return;
        }
        /* JSON takes[] = one Multishot job each; unmarked shots still pack every 8 */
      }
      const audio = cinemaAudio();
      const filmMode = audio.mode !== "silent";
      const purpose =
        c.setup && c.setup.purpose && c.setup.purpose !== "auto"
          ? c.setup.purpose
          : "short_film";
      if ($("cinema-lora-select") && $("lora-select")) {
        $("lora-select").value = $("cinema-lora-select").value;
        const spec = currentLoraSpec();
        if (spec && spec.file && spec.ready) {
          state.loraApplied = true;
          state.loraId = spec.id;
          state.loraStrength = spec.strength;
        } else if (!spec || !spec.file) {
          state.loraApplied = false;
          state.loraId = "";
        }
      }
      let seed = Number($("cinema-seed")?.value);
      if (!Number.isFinite(seed)) seed = numOr("seed", -1);
      if ($("cinema-seed-lock")?.checked) {
        const prev = (state.jobs || [])
          .filter((j) => j.cinema_batch && Number(j.seed) >= 0)
          .slice(-1)[0];
        if (prev) seed = Number(prev.seed);
      }
      const cine = ensureCinema();
      cine.seed = seed;
      const queueShots = wantSeamless
        ? shots.map((s, i) => ({
            ...s,
            mode: i === 0 ? "t2v" : "continue",
          }))
        : shots;
      const r = await fetch("/api/cinema/produce", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shots: queueShots,
          setup: cine.setup || {},
          audio,
          duration: Number($("cinema-duration")?.value) || cine.duration || 5,
          aspect: state.aspect || "16:9",
          quality: normalizeQuality(cine.quality || state.quality || "736"),
          steps: Number($("cinema-steps")?.value) || cine.steps || 20,
          seed,
          sage_attention: "disabled",
          purpose,
          silent_audio: !filmMode,
          link_continue: true,
          seamless: wantSeamless,
          prepare_sheets: !wantSeamless,
          force_sheets: !!$("cinema-force-sheets")?.checked,
          post_pass: state.postPass || "",
          ...collectLoraPayload(),
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (data.cinema_batch) {
        audio.last_batch = data.cinema_batch;
        await saveCinema(true);
        renderCinemaAudio();
      }
      if (data.phase === "sheets") {
        const n = Array.isArray(data.sheets_queued) ? data.sheets_queued.length : 0;
        toast(n ? tf("cinema.produceSheetsFirst", { n: String(n) }) : tt("cinema.produceSheetsWait"));
        setProdLane("director");
        await refreshJobs();
        return;
      }
      toast(
        data.still_lock && wantSeamless
          ? tt("cinema.stillOverSeamless")
          : data.seamless
            ? tf("cinema.produceSeamless", {
                n: queueShots.length,
                takes: data.takes || Math.max(1, Math.ceil(queueShots.length / 8)),
              })
            : studioMode === "assets"
              ? tf("cinema.produceAssets", { n: data.count || 0 })
              : filmMode
                ? tf("cinema.produceFilm", { n: data.count || 0 })
                : tf("cinema.produceSilent", { n: data.count || 0 })
      );
      renderCinemaShots();
      fillPromptFromShots(queueShots.map((s) => s.text));
      setQueueFromTexts(queueShots.map((s) => s.text));
      setProdLane("director");
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
      toast(tt("cinema.scoreLocked"));
      return true;
    } catch (e) {
      toast(String(e.message || e));
      return false;
    }
  }

  async function deleteUploadedMusic(id, kind) {
    const musicId = String(id || "").trim();
    if (!musicId || !tConfirm("confirm.removeSong")) return;
    try {
      const r = await fetch(`/api/music/${encodeURIComponent(musicId)}`, { method: "DELETE" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data) || tt("err.songDeleteFailed"));
      if (state.musicId === musicId) {
        state.musicId = null;
        state.musicMeta = null;
        updateMusicMetaUi();
      }
      const audio = cinemaAudio();
      if (audio.score_id === musicId) {
        audio.score_id = "";
        audio.score_name = "";
        renderCinemaAudio();
        await saveCinema(true);
      }
      tToast(kind === "cinema" ? "toast.musicRemovedFilm" : "toast.musicRemovedSong");
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function muxCinemaScore() {
    const audio = cinemaAudio();
    if (!audio.score_id) {
      toast(tt("cinema.needScore"));
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
      tToast("toast.filmClipsReady", { n: String(data.clips || 0) });
      if (data.final_url) window.open(data.final_url, "_blank");
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      renderCinemaAudio();
    }
  }

  function syncMergeToolbar() {
    const n = finishedClipsForMerge().length;
    const mergeBtn = $("btn-merge-clips");
    if (mergeBtn) {
      mergeBtn.disabled = n < 2;
      mergeBtn.title = n < 2 ? tt("merge.needTwo") : tt("merge.openPicker");
    }
    if (!state.galleryMergeMode) {
      const galleryConcat = $("btn-gallery-concat");
      if (galleryConcat) {
        galleryConcat.disabled = n < 2;
        galleryConcat.title = n < 2 ? tt("merge.needTwo") : tt("merge.openPicker");
      }
    } else {
      syncGalleryMergeHeader();
    }
  }

  function finishedClipsForMerge() {
    const seen = new Set();
    const out = [];
    const add = (j) => {
      if (!j || !j.id || seen.has(j.id)) return;
      const st = String(j.status || "done").toLowerCase();
      if (st && st !== "done") return;
      seen.add(j.id);
      out.push(j);
    };
    (state.jobs || []).forEach(add);
    (state.galleryItems || []).forEach(add);
    out.sort((a, b) => {
      const ba = Number(a.batch_index) || 0;
      const bb = Number(b.batch_index) || 0;
      if (ba && bb && ba !== bb) return ba - bb;
      const ta = Number(a.done_at || a.created_at || 0);
      const tb = Number(b.done_at || b.created_at || 0);
      return tb - ta;
    });
    return out;
  }

  function syncGalleryMergeHeader() {
    const panel = $("gallery-panel");
    const hint = $("gallery-merge-hint");
    const count = $("gallery-merge-count");
    const cancel = $("btn-gallery-merge-cancel");
    const concat = $("btn-gallery-concat");
    const orderHint = $("gallery-order-hint");
    const picked = state.mergePickIds || [];
    const on = !!state.galleryMergeMode;
    panel?.classList.toggle("gallery-merge-mode", on);
    hint?.classList.toggle("hidden", !on);
    count?.classList.toggle("hidden", !on);
    cancel?.classList.toggle("hidden", !on);
    orderHint?.classList.toggle("hidden", on);
    if (hint && on) hint.textContent = tt("merge.galleryHint");
    if (count && on) {
      count.textContent =
        picked.length >= 2
          ? tf("merge.countOk", { n: String(picked.length) })
          : tf("merge.countNeed", { n: String(picked.length) });
    }
    if (concat) {
      if (on) {
        concat.textContent = tt("merge.ok");
        concat.classList.add("cta");
        concat.classList.remove("btn-secondary");
        concat.disabled = picked.length < 2;
      } else {
        concat.textContent = tt("merge.toolbar");
        concat.classList.remove("cta");
        concat.classList.add("btn-secondary");
        concat.disabled = finishedClipsForMerge().length < 2;
      }
    }
  }
  window.syncGalleryMergeHeader = syncGalleryMergeHeader;

  function patchGalleryMergeBadges() {
    const picked = state.mergePickIds || [];
    document.querySelectorAll("#gallery-grid .gallery-card").forEach((card) => {
      const id = card.dataset.id;
      if (!id) return;
      const order = picked.indexOf(id);
      const sel = order >= 0;
      card.classList.toggle("is-merge-picked", sel);
      const badge = card.querySelector(".gallery-merge-badge");
      if (badge) {
        badge.textContent = sel ? String(order + 1) : "";
        badge.classList.toggle("is-on", sel);
      }
      const ring = card.querySelector(".gallery-merge-ring");
      ring?.classList.toggle("is-on", sel);
    });
    syncGalleryMergeHeader();
  }

  function toggleGalleryMergePick(id) {
    if (!state.galleryMergeMode || !id) return;
    const ids = state.mergePickIds || (state.mergePickIds = []);
    const i = ids.indexOf(id);
    if (i >= 0) ids.splice(i, 1);
    else ids.push(id);
    patchGalleryMergeBadges();
  }

  function exitGalleryMergeMode() {
    state.galleryMergeMode = false;
    state.mergePickIds = [];
    syncGalleryMergeHeader();
    if ($("view-gallery") && !$("view-gallery").classList.contains("hidden")) {
      void renderGallery();
    } else {
      patchGalleryMergeBadges();
    }
  }

  function galleryMergeUiLive() {
    return !!(
      state.galleryMergeMode &&
      $("gallery-grid")?.querySelector(".gallery-card .gallery-merge-pick")
    );
  }

  function refreshGalleryMergeUi() {
    syncGalleryMergeHeader();
    if (galleryMergeUiLive()) {
      document.querySelectorAll("#gallery-grid .gallery-merge-pick").forEach((btn) => {
        btn.classList.remove("hidden");
      });
      patchGalleryMergeBadges();
      return;
    }
    void renderGallery();
  }

  async function enterGalleryMergeMode(opts) {
    opts = opts || {};
    if (!state.galleryItems.length) {
      try {
        const data = await fetch("/api/gallery").then((r) => r.json());
        state.galleryItems = data.items || [];
      } catch {
        state.galleryItems = [];
      }
    }
    state.galleryMergeMode = true;
    state.mergePickIds = [];
    const batchId = (opts.batchId || "").trim();
    if (batchId) {
      const batchClips = finishedClipsForMerge()
        .filter((j) => String(j.cinema_batch || "") === batchId)
        .sort((a, b) => (Number(a.batch_index) || 0) - (Number(b.batch_index) || 0));
      if (batchClips.length >= 2) {
        state.mergePickIds = batchClips.map((j) => j.id);
      }
    }
    setDirectorLlmOpen(false);
    $("view-settings")?.classList.add("hidden");
    $("view-support")?.classList.add("hidden");
    $("view-gallery")?.classList.remove("hidden");
    refreshGalleryMergeUi();
    if (!state.galleryItems.length) toast(tt("merge.empty"));
  }

  async function submitClipMerge() {
    const ids = (state.mergePickIds || []).filter(Boolean);
    if (ids.length < 2) {
      toast(tt("merge.needTwo"));
      return;
    }
    const concat = $("btn-gallery-concat");
    if (concat) concat.disabled = true;
    try {
      let batchId = "";
      try {
        batchId = cinemaAudio().last_batch || "";
      } catch {
        batchId = "";
      }
      const r = await fetch("/api/clips/concat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_ids: ids,
          batch_id: batchId,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (data.batch_id) {
        try {
          const audio = cinemaAudio();
          audio.last_batch = data.batch_id;
          renderCinemaAudio();
        } catch {
          /* gallery-only merge */
        }
      }
      exitGalleryMergeMode();
      toast(tf("cinema.concatOk", { n: data.clips || ids.length }));
      if (data.final_url) window.open(data.final_url, "_blank");
      await renderGallery();
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      syncGalleryMergeHeader();
    }
  }

  async function concatCinemaFilm() {
    let batchId = "";
    try {
      batchId = cinemaAudio().last_batch || "";
    } catch {
      batchId = "";
    }
    await enterGalleryMergeMode({ batchId });
  }

  function onGalleryConcatClick() {
    if (state.galleryMergeMode) {
      const n = (state.mergePickIds || []).length;
      if (n < 2) {
        toast(tt("merge.needTwo"));
        return;
      }
      void submitClipMerge();
      return;
    }
    void enterGalleryMergeMode({});
  }

  async function stillFromGalleryClip(job) {
    const chars = ensureCinema().characters || [];
    if (!chars.length) {
      toast(tt("cinema.needChar"));
      void openCinemaStudio();
      return;
    }
    const lines = chars.map((c, i) => i + 1 + ") " + (c.name || tt("cinema.untitled")));
    const pick = window.prompt(tt("cinema.stillPick") + "\n" + lines.join("\n"), "1");
    const idx = Number(pick) - 1;
    const asset = chars[idx];
    if (!asset) return;
    try {
      const r = await fetch("/api/cinema/still-from-clip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: job.id, asset_id: asset.id, kind: "character" }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      const list = ensureCinema().characters || [];
      const i = list.findIndex((x) => x.id === asset.id);
      if (i >= 0) list[i] = data;
      renderCinema();
      toast(tf("cinema.stillSaved", { name: asset.name || "asset" }));
    } catch (e) {
      toast(String(e.message || e));
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
          j.status === "done" ? tt("job.continueTagDone") : j.status === "running" ? tt("job.continueTagRunning") : tt("job.continueTagQueued");
        add(j, tag);
      });
    (state.galleryItems || []).forEach((g) => add(g, tt("job.continueTagGallery")));
    const sig = pool.map((x) => x.job.id + ":" + x.tag).join("|");
    if (sig === state._continueSourceSig && sel.options.length === pool.length + 1) {
      if (prev && [...sel.options].some((o) => o.value === prev)) sel.value = prev;
      else if (!prev && tip) sel.value = tip.id;
      return;
    }
    state._continueSourceSig = sig;
    sel.innerHTML = `<option value="">${tt("cont.sourceAuto")}</option>`;
    pool.forEach((x, i) => {
      const j = x.job;
      const opt = document.createElement("option");
      opt.value = j.id;
      const label = (j.prompt || "").slice(0, 42).replace(/\s+/g, " ");
      opt.textContent = tf("cont.sourceOption", {
        i: String(i + 1),
        tag: x.tag,
        dur: String(j.duration || "?"),
        sec: tt("sec"),
        label: label || j.id.slice(0, 8),
      });
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
    if (!quiet) tToast("toast.playerClosed");
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

  function showPlayerVideo(url, jobId, prompt, downloadName) {
    const player = $("player");
    const stage = document.querySelector(".player-stage");
    if (!player || !url) return;
    state.playerCleared = false;
    state.selectedJobId = jobId || state.selectedJobId;
    if (prompt !== undefined) setClipPrompt(prompt);
    stage?.classList.remove("cleared");
    stage?.classList.add("has-video");
    $("btn-player-close")?.classList.remove("hidden");
    const playUrl = url.split("?")[0];
    player.src = playUrl + (playUrl.includes("?") ? "&" : "?") + "t=" + Date.now();
    const job =
      (jobId && state.jobs && state.jobs.find((j) => j.id === jobId)) ||
      (jobId && state.galleryItems && state.galleryItems.find((j) => j.id === jobId)) ||
      null;
    const name =
      downloadName ||
      job?.download_name ||
      (jobId
        ? `h3_clip_${String(jobId).replace(/-/g, "").slice(0, 8)}.mp4`
        : "h3_clip.mp4");
    const dl = $("btn-download");
    if (dl) {
      const base = playUrl.split("?")[0];
      dl.href = base + (base.includes("?") ? "&" : "?") + "dl=1";
      dl.setAttribute("download", name);
      dl.removeAttribute("aria-disabled");
    }
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
      if (dots) dots.textContent = tt("dir.writing");
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
      `<span class="dir-shot-sum-main">${tf("dir.shotViewMain", { n, extra: need && need !== n ? tf("dir.shotViewExtra", { need }) : "" })}</span>` +
      `<span class="dir-shot-sum-meta">${tf("dir.shotSumMeta", { clip, total, sec: tt("sec") })}</span>`;
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
    hint.textContent = tt("dir.shotPanelHint");
    body.appendChild(hint);

    const list = document.createElement("div");
    list.className = "dir-shot-list";
    shots.forEach((shot, i) => {
      const item = document.createElement("article");
      item.className = "dir-shot-item";
      const dur = shot.durationSec || clip;
      const link = (shot.linkToPrev || "standalone").toString();
      const head = document.createElement("div");
      head.className = "dir-shot-head";
      head.textContent = tf("dir.shotHead", { i: i + 1, dur, sec: tt("sec"), link });
      const pre = document.createElement("pre");
      pre.className = "dir-shot-prompt";
      pre.textContent = _shotPromptText(shot) || tt("clip.empty");
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
    const btnRw = document.createElement("button");
    btnRw.type = "button";
    btnRw.className = "btn-secondary";
    btnRw.textContent = tt("plan.rewrite");
    btnRw.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      void rewriteDirectorShots();
    };
    const btnQ = document.createElement("button");
    btnQ.type = "button";
    btnQ.className = "cta";
    btnQ.textContent = queueBtnLabel(n);
    btnQ.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      applyBrief(true);
    };
    actions.appendChild(btnRw);
    actions.appendChild(btnQ);
    const btnClose = document.createElement("button");
    btnClose.type = "button";
    btnClose.className = "btn-ghost";
    btnClose.textContent = tt("dir.closeKeep");
    btnClose.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      panel.open = false;
      $("director-msg")?.focus();
    };
    const btnPlan = document.createElement("button");
    btnPlan.type = "button";
    btnPlan.className = "btn-secondary";
    btnPlan.textContent = tt("dir.editPlan");
    btnPlan.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      setDirectorTab("plan");
    };
    actions.appendChild(btnPlan);
    actions.appendChild(btnClose);
    body.appendChild(actions);

    panel.appendChild(body);
    existing?.remove();
    log.appendChild(panel);
    log.scrollTop = log.scrollHeight;
  }

  function applyCinemaFromDirector(data) {
    const cine = data && data.cinema;
    // Never resurrect cards from a null/stale cinema payload
    if (!cine || typeof cine !== "object") return;
    if (!Array.isArray(cine.characters) && !Array.isArray(cine.locations) && !Array.isArray(cine.shots)) {
      return;
    }
    const base = emptyCinema();
    state.cinema = {
      ...base,
      ...cine,
      setup: { ...base.setup, ...(cine.setup || {}) },
      audio: { ...base.audio, ...(cine.audio || {}) },
    };
    renderCinema();
    toast(
      tf("cinema.roleDone", {
        c: (state.cinema.characters || []).length,
        l: (state.cinema.locations || []).length,
        s: (state.cinema.shots || []).length,
      })
    );
  }

  function scrubDirectorBriefName(name) {
    const n = String(name || "").trim().toLowerCase();
    if (!n || !state.directorBrief) return;
    const brief = { ...state.directorBrief };
    const filterNamed = (arr) =>
      (Array.isArray(arr) ? arr : []).filter(
        (x) => String((x && x.name) || "").trim().toLowerCase() !== n
      );
    brief.characters = filterNamed(brief.characters);
    brief.locations = filterNamed(brief.locations);
    state.directorBrief = brief;
    if ((brief.shots || []).length) {
      renderDirectorShotPanel(brief, { open: !!$("director-shot-panel")?.open });
      if (state.directorTab === "plan") renderDirectorPlanBoard();
    }
  }

  function syncDirectorBriefFromResponse(data) {
    applyCinemaFromDirector(data);
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
        const link = (shot.linkToPrev || "standalone").toString();
        const prompt = _shotPromptText(shot);
        return (
          '<article class="dir-plan-shot" data-idx="' +
          i +
          '">' +
          '<div class="dir-plan-shot-head"><span>Shot ' +
          (i + 1) +
          '</span><button type="button" class="btn-ghost dir-plan-shot-del" title="' +
          htmlEsc(tt("cinema.del")) +
          '">' +
          htmlEsc(tt("cinema.del")) +
          "</button></div>" +
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
          tt("plan.prompt") +
          ' <textarea rows="6" data-field="h3Prompt" placeholder="' +
          htmlEsc(tt("cinema.shotWhat")) +
          '">' +
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
      const prompt = (el.querySelector("[data-field=h3Prompt]")?.value || "").trim();
      return {
        durationSec: clip,
        camera: "",
        action: "",
        dialogue: [],
        h3Prompt: prompt,
        linkToPrev:
          el.querySelector("[data-field=link]")?.value || "standalone",
      };
    });
  }

  function deletePlanShot(idx) {
    const brief = state.directorBrief || {};
    const shots = Array.isArray(brief.shots) ? brief.shots.slice() : [];
    if (idx < 0 || idx >= shots.length) return;
    shots.splice(idx, 1);
    state.directorBrief = { ...brief, shots };
    renderDirectorPlanBoard();
    if (state.directorBrief.shots.length) {
      renderDirectorShotPanel(state.directorBrief, { open: !!$("director-shot-panel")?.open });
    } else {
      $("director-shot-panel")?.remove();
    }
  }

  async function saveDirectorPlan(applyCinema) {
    if (!state.directorSessionId) {
      tToast("toast.directorTalkFirst");
      return;
    }
    const shots = collectPlanShotsFromDom();
    if (!shots.length) {
      tToast("toast.noShotsToSave");
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
      tToast(applyCinema ? "toast.planSavedCinema" : "toast.planSaved");
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
    document.querySelectorAll("#director-chips .chip").forEach((b) => {
      b.disabled = !!state.directorBusy;
    });
    // Sahne / Proje chips stay clickable while director thinks
    document.querySelectorAll("#scene-purpose-chips .chip, #scene-style-chips .chip").forEach((b) => {
      b.disabled = false;
    });
  }

  const LLM_KEY_FIELDS = [
    { id: "llm-openai-key", set: "openai_api_key_set", mask: "openai_api_key_masked", body: "openai_api_key" },
    { id: "llm-nvidia-key", set: "nvidia_api_key_set", mask: "nvidia_api_key_masked", body: "nvidia_api_key" },
    { id: "llm-gemini-key", set: "gemini_api_key_set", mask: "gemini_api_key_masked", body: "gemini_api_key" },
    { id: "llm-grok-key", set: "grok_api_key_set", mask: "grok_api_key_masked", body: "grok_api_key" },
    { id: "llm-claude-key", set: "claude_api_key_set", mask: "claude_api_key_masked", body: "claude_api_key" },
  ];

  const LLM_PROVIDER_KEY_SET = {
    openai: "openai_api_key_set",
    nvidia: "nvidia_api_key_set",
    gemini: "gemini_api_key_set",
    grok: "grok_api_key_set",
    claude: "claude_api_key_set",
  };

  function llmPubHasKey(pub, provider) {
    const p = (provider || "").toLowerCase();
    if (p === "ollama" || p === "lmstudio" || p === "llamacpp") return true;
    const field = LLM_PROVIDER_KEY_SET[p];
    return !!(field && pub && pub[field]);
  }

  const LOCAL_LLM_URLS = {
    ollama: {
      wrap: "llm-ollama-url-wrap",
      input: "llm-ollama-url",
      field: "ollama_base_url",
      ph: "http://127.0.0.1:11434",
    },
    lmstudio: {
      wrap: "llm-lmstudio-url-wrap",
      input: "llm-lmstudio-url",
      field: "lmstudio_base_url",
      ph: "http://127.0.0.1:1234/v1",
    },
    llamacpp: {
      wrap: "llm-llamacpp-url-wrap",
      input: "llm-llamacpp-url",
      field: "llamacpp_base_url",
      ph: "http://127.0.0.1:8080/v1",
    },
  };

  function syncLocalLlmUrlWraps(prov, pub) {
    const p = (prov || "ollama").toLowerCase();
    for (const [id, spec] of Object.entries(LOCAL_LLM_URLS)) {
      $(spec.wrap)?.classList.toggle("hidden", p !== id);
      const el = $(spec.input);
      if (el && pub && el.dataset.dirty !== "1") {
        el.value = pub[spec.field] || "";
        el.placeholder = spec.ph;
      }
    }
  }

  function _urlBodyForProvider(provider) {
    const spec = LOCAL_LLM_URLS[(provider || "").toLowerCase()];
    if (!spec) return {};
    const el = $(spec.input);
    return el ? { [spec.field]: (el.value || "").trim() } : {};
  }

  function syncProviderSelects(prov) {
    const p = (prov || "ollama").toLowerCase();
    if ($("llm-provider")) $("llm-provider").value = p;
    if ($("llm-provider-settings")) $("llm-provider-settings").value = p;
    syncLocalLlmUrlWraps(p, state.llmPub);
  }

  function syncModelSelects(model) {
    const m = (model || "").trim();
    if (!m) return;
    if ($("director-model")) $("director-model").value = m;
    if ($("director-model-settings")) $("director-model-settings").value = m;
  }

  function syncLlmKeyFields(pub) {
    if (!pub) return;
    for (const f of LLM_KEY_FIELDS) {
      const el = $(f.id);
      if (!el) continue;
      if (el.dataset.dirty === "1" && el.value.trim()) continue;
      if (pub[f.set]) {
        const mask = pub[f.mask] || tt("llm.keySaved");
        el.value = "";
        el.placeholder = "✓ " + mask + " (" + tt("llm.keySavedHint") + ")";
        el.classList.add("key-saved");
      } else {
        el.classList.remove("key-saved");
      }
    }
  }

  const FALLBACK_LLM_MODELS = {
    openai: ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1", "o4-mini"],
    nvidia: [
      "minimaxai/minimax-m3",
      "meta/llama-3.3-70b-instruct",
      "meta/llama-3.1-70b-instruct",
      "meta/llama-3.1-8b-instruct",
      "google/gemma-2-9b-it",
      "mistralai/mistral-nemo-12b-instruct",
    ],
    gemini: [
      "gemini-3.6-flash",
      "gemini-3.5-flash",
      "gemini-3.1-flash-lite",
      "gemini-3-flash-preview",
      "gemini-2.5-flash",
      "gemini-2.5-pro",
    ],
    grok: ["grok-3-mini", "grok-3", "grok-2-latest"],
    claude: [
      "claude-sonnet-4-20250514",
      "claude-3-5-haiku-latest",
      "claude-3-5-sonnet-latest",
      "claude-opus-4-20250514",
    ],
  };

  function _fillModelSelect(sel, models, preferred, opts) {
    if (!sel) return "";
    const reset = !!(opts && opts.reset);
    const prev = reset ? "" : sel.value;
    const list = [...(models || [])];
    const want = (prev || preferred || list[0] || "").trim();
    if (want && !list.includes(want)) list.unshift(want);
    sel.innerHTML = "";
    if (!list.length) {
      sel.innerHTML = `<option value="">${tt("llm.noModel")}</option>`;
      return "";
    }
    let picked = false;
    for (const name of list) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      if (name === want) {
        opt.selected = true;
        picked = true;
      }
      sel.appendChild(opt);
    }
    if (!picked && sel.options.length) sel.options[0].selected = true;
    return (sel.options[sel.selectedIndex] && sel.options[sel.selectedIndex].value) || want || "";
  }

  function _selectedLlmProvider(which) {
    const fromDirector =
      ($("llm-provider") && $("llm-provider").value) ||
      ($("llm-provider-settings") && $("llm-provider-settings").value) ||
      "ollama";
    const fromSettings =
      ($("llm-provider-settings") && $("llm-provider-settings").value) ||
      ($("llm-provider") && $("llm-provider").value) ||
      "ollama";
    const pick = which === "settings" ? fromSettings : fromDirector;
    return String(pick).toLowerCase();
  }

  function _unsavedLlmKeyForProvider(provider) {
    const p = (provider || "").toLowerCase();
    const fieldByProv = {
      openai: "llm-openai-key",
      nvidia: "llm-nvidia-key",
      gemini: "llm-gemini-key",
      grok: "llm-grok-key",
      claude: "llm-claude-key",
    };
    const id = fieldByProv[p];
    if (!id) return "";
    const el = $(id);
    if (!el || el.dataset.dirty !== "1") return "";
    return (el.value || "").trim();
  }

  function _catalogForProvider(prov, pub) {
    const p = (prov || "ollama").toLowerCase();
    const cfg = pub || state.llmPub || {};
    if (p === "openai") {
      return {
        models: cfg.openai_models || FALLBACK_LLM_MODELS.openai,
        preferred: cfg.openai_model,
      };
    }
    if (p === "nvidia") {
      return {
        models: cfg.nvidia_models || FALLBACK_LLM_MODELS.nvidia,
        preferred: cfg.nvidia_model,
      };
    }
    if (p === "gemini") {
      return {
        models: cfg.gemini_models || FALLBACK_LLM_MODELS.gemini,
        preferred: cfg.gemini_model,
      };
    }
    if (p === "grok") {
      return {
        models: cfg.grok_models || FALLBACK_LLM_MODELS.grok,
        preferred: cfg.grok_model,
      };
    }
    if (p === "claude") {
      return {
        models: cfg.claude_models || FALLBACK_LLM_MODELS.claude,
        preferred: cfg.claude_model,
      };
    }
    if (p === "lmstudio") {
      return { models: state.lmstudioModels || [], preferred: cfg.lmstudio_model };
    }
    if (p === "llamacpp") {
      return { models: state.llamacppModels || [], preferred: cfg.llamacpp_model };
    }
    return { models: state.ollamaModels || [], preferred: cfg.ollama_model };
  }

  function fillDirectorModelsForProvider(prov, pub, opts) {
    const p = (prov || "ollama").toLowerCase();
    const useLive = opts && opts.liveModels && opts.liveModels.length;
    const cat = _catalogForProvider(p, pub);
    const models = useLive ? opts.liveModels : cat.models;
    const preferred =
      (opts && opts.preferred) ||
      cat.preferred ||
      (models && models[0]) ||
      "";
    const reset = !(opts && opts.keepSelection);
    const m1 = _fillModelSelect($("director-model"), models, preferred, { reset });
    const m2 = _fillModelSelect($("director-model-settings"), models, preferred, { reset });
    syncModelSelects(m1 || m2 || preferred);
  }

  function _setModelSelectLoading() {
    const label = tt("llm.loadingModels");
    for (const id of ["director-model", "director-model-settings"]) {
      const sel = $(id);
      if (!sel) continue;
      sel.innerHTML = `<option value="">${label}</option>`;
    }
  }

  function _rememberLiveModels(prov, models) {
    const p = (prov || "").toLowerCase();
    if (!models || !models.length) return;
    if (p === "ollama") state.ollamaModels = models;
    else if (p === "lmstudio") state.lmstudioModels = models;
    else if (p === "llamacpp") state.llamacppModels = models;
    else if (state.llmPub) {
      const key = p + "_models";
      if (state.llmPub[key] || p === "openai" || p === "nvidia" || p === "gemini" || p === "grok" || p === "claude") {
        state.llmPub[key] = models;
      }
    }
  }

  function _draftUrlForProvider(prov) {
    const spec = LOCAL_LLM_URLS[(prov || "").toLowerCase()];
    if (!spec) return "";
    return ($(spec.input)?.value || "").trim();
  }

  async function fetchLlmModels(prov) {
    const p = String(prov || "ollama").toLowerCase();
    const q = new URLSearchParams({ provider: p });
    const url = _draftUrlForProvider(p);
    if (url) q.set("base_url", url);
    const r = await fetch("/api/llm/models?" + q.toString());
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(errDetail(data));
    return data;
  }

  async function ensureLlmPub(opts) {
    const fresh = !!(opts && opts.fresh);
    if (
      !fresh &&
      state.llmPub &&
      (state.llmPub.gemini_models || state.llmPub.openai_models)
    ) {
      return state.llmPub;
    }
    try {
      const d = await fetch("/api/llm/settings").then((r) => r.json());
      state.llmPub = d;
      return d;
    } catch {
      return state.llmPub || {};
    }
  }

  async function onLlmProviderChanged(prov) {
    const p = String(prov || "ollama").toLowerCase();
    state.llmDraftProvider = p;
    const seq = ++state.llmModelsSeq;
    syncProviderSelects(p);
    const pub = await ensureLlmPub();
    if (state.llmModelsSeq !== seq) return;
    syncLlmSettingsUi({ ...pub, provider: p }, { provider: p });
    const cat = _catalogForProvider(p, pub);
    const local = p === "ollama" || p === "lmstudio" || p === "llamacpp";
    if (local && !(cat.models && cat.models.length)) {
      _setModelSelectLoading();
    } else {
      fillDirectorModelsForProvider(p, pub, { keepSelection: false });
    }
    try {
      const live = await fetchLlmModels(p);
      if (state.llmModelsSeq !== seq || state.llmDraftProvider !== p) return;
      if (live.models && live.models.length) {
        _rememberLiveModels(p, live.models);
        fillDirectorModelsForProvider(p, state.llmPub || pub, {
          liveModels: live.models,
          preferred: live.preferred,
          keepSelection: false,
        });
      } else if (local) {
        fillDirectorModelsForProvider(p, pub, { keepSelection: false });
      }
    } catch {
      if (state.llmModelsSeq === seq) {
        fillDirectorModelsForProvider(p, pub, { keepSelection: false });
      }
    }
  }

  function syncLlmSettingsUi(pub, probe) {
    const prov = (pub && pub.provider) || (probe && probe.provider) || "ollama";
    syncProviderSelects(prov);
    syncLocalLlmUrlWraps(prov, pub);
    const prodModelWrap = $("llm-prod-model-wrap");
    if (prodModelWrap) prodModelWrap.classList.remove("hidden");
    for (const f of LLM_KEY_FIELDS) {
      const el = $(f.id);
      if (!el || !pub) continue;
      if (pub[f.set] && !el.dataset.dirty) {
        const mask = pub[f.mask] || tt("llm.keySaved");
        el.placeholder = "✓ " + mask + " (" + tt("llm.keySavedHint") + ")";
        el.classList.add("key-saved");
      } else if (!el.dataset.dirty) {
        el.classList.remove("key-saved");
      }
    }
    syncLlmKeyFields(pub);
    const ready = {
      openai: pub && pub.openai_api_key_set,
      nvidia: pub && pub.nvidia_api_key_set,
      gemini: pub && pub.gemini_api_key_set,
      grok: pub && pub.grok_api_key_set,
      claude: pub && pub.claude_api_key_set,
    };
    const tips = {
      ollama: tt("llm.tip.ollama"),
      lmstudio: tt("llm.tip.lmstudio"),
      llamacpp: tt("llm.tip.llamacpp"),
      openai: ready.openai ? tt("llm.tip.openaiReady") : tt("llm.tip.openai"),
      nvidia: ready.nvidia ? tt("llm.tip.nvidiaReady") : tt("llm.tip.nvidia"),
      gemini: ready.gemini ? tt("llm.tip.geminiReady") : tt("llm.tip.gemini"),
      grok: ready.grok ? tt("llm.tip.grokReady") : tt("llm.tip.grok"),
      claude: ready.claude ? tt("llm.tip.claudeReady") : tt("llm.tip.claude"),
    };
    const hint = $("llm-settings-hint");
    if (hint) hint.textContent = tips[prov] || tt("llm.tipFallback");
    const prodHint = $("llm-prod-hint");
    if (prodHint) {
      prodHint.textContent = tf("llm.prodNow", { provider: prov });
    }
  }

  function _modelBodyForProvider(provider, model) {
    if (!model) return {};
    if (provider === "openai") return { openai_model: model };
    if (provider === "nvidia") return { nvidia_model: model };
    if (provider === "gemini") return { gemini_model: model };
    if (provider === "grok") return { grok_model: model };
    if (provider === "claude") return { claude_model: model };
    if (provider === "lmstudio") return { lmstudio_model: model };
    if (provider === "llamacpp") return { llamacpp_model: model };
    return { ollama_model: model };
  }

  async function _postLlmSettings(body) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 90000);
    try {
      const r = await fetch("/api/llm/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      return data;
    } catch (e) {
      if (e && e.name === "AbortError") {
        throw new Error(tt("err.timeout90"));
      }
      throw e;
    } finally {
      clearTimeout(timer);
    }
  }

  function _setLlmBtnBusy(id, busy, busyLabelKey, idleLabelKey) {
    const btn = $(id);
    if (!btn) return;
    if (busy) {
      btn.dataset.busy = "1";
      btn.disabled = true;
      btn.textContent = tt(busyLabelKey) || btn.textContent;
    } else {
      delete btn.dataset.busy;
      btn.disabled = false;
      btn.textContent = tt(idleLabelKey) || btn.textContent;
    }
  }

  function _applyLlmProbeToDirectorUi(data, provider, model) {
    const prov = (data.provider || provider || "ollama").toLowerCase();
    const activeModel =
      model ||
      data.default_model ||
      _catalogForProvider(prov, data).preferred ||
      "model";
    state.llmProvider = prov;
    state.directorOnline = !!data.online;
    state.directorOfflineDetail = data.detail || "";
    if (data.online) {
      const nvidiaWarn = _directorNvidiaStatusLabel(activeModel, data.detail);
      setDirectorUi(
        true,
        nvidiaWarn || `${prov} · ${activeModel}`
      );
    } else {
      setDirectorUi(false, tf("dir.offline", { provider: prov }));
    }
  }

  /** Production drawer: switch active provider/model — uses keys already saved in Ayarlar. */
  async function saveLlmProviderOnly() {
    if ($("btn-llm-provider-save")?.dataset.busy === "1") return;
    const provider = _selectedLlmProvider("director");
    syncProviderSelects(provider);
    const model =
      ($("director-model") && $("director-model").value) ||
      ($("director-model-settings") && $("director-model-settings").value) ||
      "";
    syncModelSelects(model);
    _setLlmBtnBusy("btn-llm-provider-save", true, "ayar.llmApplying", "ayar.llmApply");
    try {
      let pub = await ensureLlmPub({ fresh: true });
      const unsavedKey = _unsavedLlmKeyForProvider(provider);
      if (!llmPubHasKey(pub, provider)) {
        if (unsavedKey) {
          directorLlmFeedback(
            tf("toast.llmKeyDirty", { provider }),
            "warn"
          );
          return;
        }
        directorLlmFeedback(
          tf("toast.llmNeedKey", { provider }),
          "warn"
        );
        return;
      }
      const data = await _postLlmSettings({
        provider,
        ..._modelBodyForProvider(provider, model),
        ..._urlBodyForProvider(provider),
      });
      state.llmPub = data;
      state.llmDraftProvider = (data.provider || provider || "").toLowerCase();
      syncProviderSelects(data.provider || provider);
      syncLlmKeyFields(data);
      const activeModel =
        model ||
        data.default_model ||
        _catalogForProvider(data.provider || provider, data).preferred;
      fillDirectorModelsForProvider(data.provider || provider, data, {
        liveModels: data.models,
        preferred: activeModel,
        keepSelection: true,
      });
      const msg = data.online
        ? data.detail && String(data.detail).startsWith("default_model_unavailable")
          ? _directorNvidiaStatusLabel(activeModel, data.detail) ||
            tf("toast.llmOn", {
              provider: data.provider || provider,
              model: data.default_model || activeModel || "ok",
            })
          : tf("toast.llmOn", {
              provider: data.provider || provider,
              model: data.default_model || activeModel || "ok",
            })
        : tf("toast.llmOff", { detail: data.detail || "?" });
      directorLlmFeedback(msg, data.online ? "ok" : "warn");
      _applyLlmProbeToDirectorUi(data, provider, activeModel);
    } catch (e) {
      directorLlmFeedback(String(e.message || e), "err");
    } finally {
      _setLlmBtnBusy("btn-llm-provider-save", false, "ayar.llmApplying", "ayar.llmApply");
    }
    void refreshDirectorStatus();
  }

  /** Top-right Settings: save API keys + provider. */
  async function saveLlmSettings() {
    if ($("btn-llm-save")?.dataset.busy === "1") return;
    const provider = _selectedLlmProvider("settings");
    const body = { provider };
    const model =
      ($("director-model-settings") && $("director-model-settings").value) ||
      ($("director-model") && $("director-model").value);
    const urlIn = $("llm-ollama-url");
    if (urlIn) body.ollama_base_url = urlIn.value.trim();
    const lmsIn = $("llm-lmstudio-url");
    if (lmsIn) body.lmstudio_base_url = lmsIn.value.trim();
    const llcIn = $("llm-llamacpp-url");
    if (llcIn) body.llamacpp_base_url = llcIn.value.trim();
    for (const f of LLM_KEY_FIELDS) {
      const el = $(f.id);
      if (el && el.value.trim()) body[f.body] = el.value.trim();
    }
    const oa = $("llm-openai-key");
    const nv = $("llm-nvidia-key");
    if (oa && nv && /^nvapi-/i.test((oa.value || "").trim()) && !(nv.value || "").trim()) {
      body.nvidia_api_key = oa.value.trim();
      body.openai_api_key = "";
      body.provider = "nvidia";
    }
    Object.assign(body, _modelBodyForProvider(provider, model));
    _setLlmBtnBusy("btn-llm-save", true, "settings.saveApiBusy", "settings.saveApi");
    try {
      const data = await _postLlmSettings(body);
      state.llmPub = data;
      state.llmDraftProvider = (data.provider || provider || "").toLowerCase();
      syncProviderSelects(data.provider || provider);
      syncLlmKeyFields(data);
      for (const f of LLM_KEY_FIELDS) {
        const el = $(f.id);
        if (el && el.value.trim()) {
          el.value = "";
          delete el.dataset.dirty;
        }
      }
      if (urlIn) delete urlIn.dataset.dirty;
      if (lmsIn) delete lmsIn.dataset.dirty;
      if (llcIn) delete llcIn.dataset.dirty;
      fillDirectorModelsForProvider(data.provider || provider, data, {
        liveModels: data.models,
        preferred:
          model ||
          data.default_model ||
          _catalogForProvider(data.provider || provider, data).preferred,
        keepSelection: true,
      });
      syncLlmSettingsUi(data, data);
      toast(
        data.online
          ? tf("toast.llmSavedOn", { provider: data.provider, model: data.default_model || "ok" })
          : tf("toast.llmSavedOff", { detail: data.detail || "?" })
      );
      _applyLlmProbeToDirectorUi(data, provider, model);
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      _setLlmBtnBusy("btn-llm-save", false, "settings.saveApiBusy", "settings.saveApi");
    }
    void refreshDirectorStatus();
  }

  function _directorNvidiaStatusLabel(activeModel, detail) {
    const d = String(detail || "");
    if (!d.startsWith("default_model_unavailable")) return null;
    if (/429|too many requests/i.test(d)) {
      return (
        tf("dir.nvidiaRateLimit", { model: activeModel })
      );
    }
    return (
      tf("dir.nvidiaModelDown", { model: activeModel })
    );
  }

  async function refreshDirectorStatus() {
    try {
      const s = await fetch("/api/director/status?lang=" + encodeURIComponent(uiLang())).then((r) => r.json());
      const provider = s.provider || (s.llm && s.llm.provider) || "ollama";
      state.llmProvider = provider;
      state.directorOfflineDetail = s.detail || "";
      if (s.llm) state.llmPub = s.llm;
      const models = s.models || [];
      if (provider === "ollama") state.ollamaModels = models;
      if (provider === "lmstudio") state.lmstudioModels = models;
      if (provider === "llamacpp") state.llamacppModels = models;
      const draft = (state.llmDraftProvider || "").toLowerCase();
      const browsing = draft && draft !== String(provider || "").toLowerCase();
      let savedModel = "";
      if (!browsing) {
        state.llmDraftProvider = String(provider || "").toLowerCase();
        syncProviderSelects(provider);
        syncLlmSettingsUi(s.llm || {}, s);
        const cat = _catalogForProvider(provider, s.llm || state.llmPub);
        savedModel = cat.preferred;
        fillDirectorModelsForProvider(provider, s.llm || state.llmPub, {
          liveModels: models,
          preferred: savedModel || s.default_model,
          keepSelection: true,
        });
      } else {
        syncLlmKeyFields(s.llm || state.llmPub);
      }
      const activeModel = browsing
        ? (s.default_model || "model")
        : (
            ($("director-model") && $("director-model").value) ||
            savedModel ||
            s.default_model ||
            "model"
          );
      if (s.online) {
        const nvidiaWarn = _directorNvidiaStatusLabel(activeModel, s.detail);
        state.directorOfflineDetail = nvidiaWarn ? s.detail || "" : "";
        const label = state.directorReady
          ? tt("dir.briefReady")
          : state.directorBusy
            ? tt("dir.thinkingStatus")
            : nvidiaWarn || `${provider} · ${activeModel}`;
        setDirectorUi(true, label);
        if (!$("director-log").children.length && s.opening && !state.directorSessions.length) {
          appendDirectorMsg("assistant", s.opening);
        }
      } else {
        const why = s.detail || "";
        let msg = tf("dir.offline", { provider });
        let help = tt("llm.helpOff");
        if (why === "api_key_missing") {
          help = tt("llm.help." + provider) || help;
        } else if (
          (provider === "ollama" || provider === "lmstudio" || provider === "llamacpp") &&
          why === "connect_refused"
        ) {
          help = tt("llm.help." + provider + "Refused") || help;
        } else if (
          (provider === "ollama" || provider === "lmstudio" || provider === "llamacpp") &&
          why === "timeout"
        ) {
          help = tt("llm.help." + provider + "Timeout") || help;
        } else if (why && why !== "offline") {
          help = `${provider}: ${why}`;
        }
        setDirectorUi(false, msg);
        if (!$("director-log").children.length && !state.directorSessions.length) {
          appendDirectorMsg("assistant", help);
        }
      }
    } catch {
      state.directorOfflineDetail = "";
      setDirectorUi(false, tt("llm.help.noApi"));
    }
  }

  function errDetail(data) {
    if (data == null) return "hata";
    const d = data.detail;
    if (typeof d === "string" && d.trim()) return d;
    if (typeof d === "object" && d !== null) {
      if (typeof d.message === "string" && d.message.trim()) return d.message;
      if (typeof d.detail === "string" && d.detail.trim()) return d.detail;
      const s = JSON.stringify(d);
      if (s && s !== "{}") return s;
    }
    if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
    if (typeof data.message === "string" && data.message.trim()) return data.message;
    const s = JSON.stringify(data);
    return s && s !== "{}" ? s : tt("err.requestFailed");
  }

  function formatStreamError(detail) {
    if (detail == null) return tt("err.directorStream");
    if (typeof detail === "string") return detail.trim() || tt("err.directorStream");
    if (typeof detail === "object") {
      if (typeof detail.message === "string") return detail.message;
      if (typeof detail.detail === "string") return detail.detail;
      const s = JSON.stringify(detail);
      return s && s !== "{}" ? s : tt("err.directorStream");
    }
    return String(detail);
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
    if (!btn || btn.disabled) return;
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
        if (fromScene) toast(tt("toast.purposeMv")); } else {
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
    return /yanıt boş geldi|yanıt alınamadı|boş geldi|empty reply|no reply|reply was empty/i.test(t);
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
      cinema_studio:
        !!state.cinemaDirector || !$("view-cinema")?.classList.contains("hidden"),
      prompt_rewriter_enabled: !!$("prompt-rewriter-enabled")?.checked,
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
            err = new Error(formatStreamError(ev.detail));
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
      if (!r.ok) {
        const fallback =
          r.status === 500
            ? tt("err.server500")
            : `HTTP ${r.status}`;
        throw new Error(errDetail(data) === tt("err.requestFailed") ? fallback : errDetail(data));
      }
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
      await refreshDirectorStatus();
      const prov = state.llmProvider || _selectedLlmProvider();
      const why = state.directorOfflineDetail || "";
      appendDirectorMsg(
        "assistant",
        why
          ? tf("dir.offlineDetail", { provider: prov, detail: why })
          : tt("dir.llmOfflineFull")
      );
      if (!state.directorOnline) return;
    }
    state.directorBusy = true;
    setDirectorUi(true, isRetry ? tt("dir.retryStatus") : tt("dir.thinkingStatus"));
    if (!isRetry) {
      appendDirectorMsg("user", message);
      $("director-msg").value = "";
    }
    beginDirectorThinking(isRetry ? tt("dir.retryStatus") : null);
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
          reply || tt("toast.emptyReply")
        );
      }
      // One automatic retry if still empty / legacy empty-error string
      if (!isRetry && _directorReplyLooksBroken(reply)) {
        appendDirectorMsg(
          "assistant",
          tt("toast.retryEmpty")
        );
        handedOffRetry = true;
        state.directorBusy = false;
        return directorSend(
          tt("dir.retryUserMsg"),
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
          ? tf("dir.readyStatusFull", { n: String(nShots || "?") })
          : `Ollama · ${data.model || ""}`
      );
      setDirectorModal(true);
    } catch (e) {
      clearDirectorThinking();
      const msg = String(e.message || e);
      const prov = (state.llmProvider || $("llm-provider")?.value || "").toLowerCase();
      let hint = "";
      if (/403|forbidden|authorization failed/i.test(msg)) {
        hint =
          prov === "nvidia"
            ? tt("hint.nvidia403")
            : tt("hint.api403");
      } else if (/429|too many requests|rate limit/i.test(msg)) {
        hint =
          prov === "nvidia"
            ? tt("hint.nvidia429")
            : tt("hint.api429");
      } else if (
        (prov === "gemini" || /gemini/i.test(msg)) &&
        /gemini|api key|403|404|model|quota|invalid/i.test(msg)
      ) {
        hint = tt("hint.geminiModel");
      } else if (prov === "nvidia" || /nvidia|nvapi/i.test(msg)) {
        hint =
          tt("hint.nvidiaSetup");
      } else if (prov === "ollama" || /ollama/i.test(msg)) {
        hint = tt("hint.ollamaTry");
      } else {
        hint = tt("hint.checkSettings");
      }
      appendDirectorMsg("assistant", msg + hint);
      await refreshDirectorStatus();
    } finally {
      clearDirectorThinking();
      if (!handedOffRetry) {
        state.directorBusy = false;
        setDirectorUi(
          state.directorOnline,
          state.directorOnline ? $("director-status")?.textContent : tt("llm.help.noApi")
        );
        await refreshDirectorStatus();
        if (state.directorReady || (state.directorBrief && state.directorBrief.shots?.length)) {
          const n = state.directorBrief?.shots?.length || 0;
          setDirectorReadyUi(true, n);
          setDirectorUi(
            true,
            n ? tf("dir.readyStatusN", { n: String(n) }) : tt("dir.readyStatusQueue")
          );
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
    const rw = $("btn-rewrite-brief");
    if (q) {
      q.classList.toggle("hidden", !state.directorReady);
      if (state.directorReady) {
        q.textContent = queueBtnLabel(n);
      }
    }
    if (rw) {
      rw.classList.toggle("hidden", !state.directorReady);
    }
    if (state.directorBrief && (state.directorBrief.shots || []).length) {
      renderDirectorShotPanel(state.directorBrief);
    } else {
      $("director-shot-panel")?.remove();
    }
    updateMusicMuxUi();
  }

  async function rewriteDirectorShots() {
    if (!state.directorSessionId) {
      toast(tt("plan.needSession"));
      return;
    }
    const btns = [$("btn-plan-rewrite"), $("btn-rewrite-brief")].filter(Boolean);
    btns.forEach((b) => {
      b.disabled = true;
    });
    try {
      toast(tt("plan.rewriting"));
      if (state.directorTab === "plan") {
        await saveDirectorPlan(false);
      }
      const r = await fetch("/api/director/rewrite-shots", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: state.directorSessionId, force: true }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (data.brief) {
        state.directorBrief = data.brief;
        renderDirectorShotPanel(data.brief, { open: true });
        if (state.directorTab === "plan") renderDirectorPlanBoard();
      }
      toast(
        tf("plan.rewritten", { n: data.rewritten || 0 }) ||
          tf("toast.shotsRewritten", { n: String(data.rewritten || 0) })
      );
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      btns.forEach((b) => {
        b.disabled = false;
      });
    }
  }

  function updateMusicMetaUi() {
    const el = $("music-meta");
    const analyze = $("btn-music-analyze");
    const remove = $("btn-music-remove");
    if (!el) return;
    if (!state.musicMeta) {
      el.textContent = tt("dir.songNone");
      if (analyze) analyze.disabled = true;
      if (remove) remove.classList.add("hidden");
      updateMusicMuxUi();
      return;
    }
    const m = state.musicMeta;
    const shots = m.suggestedShots5 || Math.ceil((m.durationSec || 0) / 5);
    const prog =
      m.linked_jobs != null
        ? tf("dir.musicClipProg", {
            done: String(m.linked_done || 0),
            total: String(m.linked_jobs),
            pending: m.linked_pending ? tf("dir.musicClipPending", { n: String(m.linked_pending) }) : "",
          })
        : "";
    el.textContent = tf("dir.musicTrackMeta", {
      file: m.filename || "track",
      dur: (m.durationSec || 0).toFixed(1),
      sec: tt("sec"),
      shots: String(shots),
      prog,
    });
    el.title = el.textContent;
    if (analyze) analyze.disabled = !!state.directorBusy;
    if (remove) remove.classList.remove("hidden");
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
    tToast("toast.songUploading");
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
        tf("dir.songReceived", { file: data.music.filename, dur: String(data.music.durationSec), sec: tt("sec"), shots: String(data.music.suggestedShots5) })
      );
      tToast("toast.songReadyBrief");
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
      tToast("dir.llmOfflineFull");
        return;
      }
    }
    state.directorBusy = true;
    setDirectorUi(true, tt("toast.songAnalyzing"));
    $("btn-music-analyze").disabled = true;
    try {
      tToast("toast.songMeasuring");
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
      appendDirectorMsg("assistant", data.reply || tt("dir.briefReady"));
      syncDirectorBriefFromResponse(data);
      setDirectorTab("plan");
      setDirectorReadyUi(true, data.shot_count);
      setDirectorUi(true, tf("dir.briefReadyStatus", { n: data.shot_count || "?" }));
      tToast("toast.songBriefReady", { n: String(data.shot_count || "?") });
    } catch (e) {
      appendDirectorMsg("assistant", String(e.message || e));
      toast(String(e.message || e));
    } finally {
      state.directorBusy = false;
      updateMusicMetaUi();
      await refreshDirectorStatus();
      if (state.directorReady) {
        setDirectorReadyUi(true);
        setDirectorUi(true, tt("dir.briefQueueStatus"));
      }
    }
  }

  async function muxMusicFinal() {
    if (!state.musicId) {
      tToast("toast.uploadSongFirst");
      return;
    }
    try {
      await refreshMusicStatus();
      const m = state.musicMeta || {};
      const done = Number(m.linked_done || 0);
      const pending = Number(m.linked_pending || 0);
      if (!done && pending) {
        tToast("toast.songClipsPending", { n: String(pending) });
        appendDirectorMsg(
          "assistant",
          tf("toast.songMuxOldWarn", { n: String(pending) })
        );
        return;
      }
      if (!done) {
        tToast("toast.songQueueFirst");
        appendDirectorMsg(
          "assistant",
          tt("toast.songMuxHelp")
        );
        return;
      }
      toast(tf("toast.songMuxWorking", { n: String(done) }));
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
        tf("toast.songFinalReady", { n: String(data.clip_count) })
      );
      tToast("toast.finalReady");
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
      rm.textContent = tt("job.del");
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
      promptRewriterEnabled: !!$("prompt-rewriter-enabled")?.checked,
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
    if ($("prompt-rewriter-enabled") && snap.promptRewriterEnabled !== undefined) {
      $("prompt-rewriter-enabled").checked = !!snap.promptRewriterEnabled;
    }
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
      tToast(n ? "toast.prodLoaded" : "toast.prodSettingsLoaded", n ? { n: String(n) } : {});
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
        tToast("toast.prodSaved", { n: String(snap.queueItems.length) });
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
        if (!quiet) tToast("toast.noSavedProd");
        return false;
      }
      if (
        force ||
        !state.queueItems.length ||
        tConfirm("confirm.loadSavedProd")
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
      tToast("toast.emptyPromptNoAdd");
      return false;
    }
    state.queueItems.push({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      text: t,
    });
    renderQueue();
    toast(tf("toast.promptAdded", { n: String(state.queueItems.length) }));
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

  /** Show shot package in Prompt / Sahne so director → produce is visible there too. */
  function fillPromptFromShots(texts) {
    const list = (texts || [])
      .map((t) => (t || "").trim())
      .filter(Boolean);
    const el = $("prompt");
    if (!el || !list.length) return;
    el.value = list.join("\n\n---\n\n");
    el.rows = Math.min(14, Math.max(3, 2 + list.length * 2));
    try {
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch {
      /* ignore */
    }
  }

  function promptsFromBrief(brief) {
    const shots = (brief && Array.isArray(brief.shots) ? brief.shots : []) || [];
    return shots.map(_shotPromptText).filter(Boolean);
  }

  async function applyBrief(queue) {
    if (!state.directorSessionId) {
      tToast("toast.directorTalkFirst");
      return;
    }
    const queueBtns = [$("btn-queue-brief"), $("btn-plan-queue")].filter(Boolean);
    queueBtns.forEach((b) => {
      b.disabled = true;
    });
    const inCinema =
      !!state.cinemaDirector || !$("view-cinema")?.classList.contains("hidden");
    // Immediate UX: mirror local plan shots into Prompt / Sahne before commit returns
    const localPrompts = promptsFromBrief(state.directorBrief);
    if (localPrompts.length) {
      fillPromptFromShots(localPrompts);
      setQueueFromTexts(localPrompts);
    }
    if (queue) {
      // Show the right production tab immediately (don't wait for slow commit)
      setProdLane(inCinema ? "director" : "scene");
      toast(
        inCinema
          ? tt("toast.queueDirectorLane")
          : tt("toast.queueSceneLane")
      );
    } else {
      tToast("toast.shotListTransfer");
    }
    try {
      const knobs = collectGenerateKnobs();
      // Don't block commit on per-shot LLM polish — that can take minutes
      delete knobs.prompt_rewriter_enabled;
      const r = await fetch("/api/director/commit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.directorSessionId,
          queue: !!queue,
          link_continue: !!$("link-continue")?.checked,
          append_to_chain: !!$("link-continue")?.checked,
          quality: state.quality,
          aspect: state.aspect || "16:9",
          purpose: state.projectPurpose,
          silent_audio: state.projectSilent || state.projectPurpose === "music_video",
          clip_duration: state.duration || 5,
          prompt_rewriter_enabled: false,
          ...knobs,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(errDetail(data));
      const a = data.applied || {};
      if (data.brief) state.directorBrief = data.brief;
      if (Array.isArray(data.missing_stills) && data.missing_stills.length) {
        syncFilmStillsWarn(data.missing_stills);
        toast(tf("filmMode.missingStillsToast", { names: data.missing_stills.join(", ") }));
      }
      if (data.cinema_studio && queue && data.queued) {
        await loadCinema();
        renderCinemaShots();
      }
      let prompts = Array.isArray(a.prompts)
        ? a.prompts.map((s) => String(s || "").trim()).filter(Boolean)
        : String(a.batch_prompts || "")
            .split(/\n\s*---\s*\n/)
            .map((s) => s.trim())
            .filter(Boolean);
      if (!prompts.length) {
        prompts = promptsFromBrief(data.brief || state.directorBrief);
      }
      if (prompts.length) {
        fillPromptFromShots(prompts);
        setQueueFromTexts(prompts);
      } else if (a.prompt) {
        fillPromptFromShots([a.prompt]);
      }
      const n = a.shot_count || prompts.length || (data.queued && data.queued.count) || 0;
      const total = a.total_duration_sec ? ` · ${a.total_duration_sec}sn` : "";
      const lane = a.lane || (inCinema ? "director" : "scene");
      if (queue) setProdLane(lane === "director" ? "director" : "scene");
      toast(
        queue
          ? tf("toast.prodQueued", { n: String(n), lane: lane === "director" ? tt("prod.laneDirector") : tt("prod.laneScene"), total: a.total_duration_sec ? tf("toast.prodQueuedTotal", { sec: String(a.total_duration_sec), unit: tt("sec") }) : "" })
          : tf("toast.shotListed", { n: String(n), total: a.total_duration_sec ? ` · ${a.total_duration_sec}${tt("sec")}` : "" })
      );
      if (queue) {
        setDirectorOpen(false);
        state.playerCleared = false;
        await refreshJobs();
      }
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      queueBtns.forEach((b) => {
        b.disabled = false;
      });
    }
  }

  async function refreshHealth() {
    try {
      const h = await fetch("/api/health").then((r) => r.json());
      const pill = $("comfy-pill");
      pill.textContent = h.comfy ? tt("comfy.online") : tt("comfy.offline");
      pill.classList.toggle("on", !!h.comfy);
      pill.classList.toggle("off", !h.comfy);
    } catch {
      $("comfy-pill").textContent = tt("comfy.unknown");
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
        $("sys-disk").title = tf("sys.diskFree", { gb: String(s.disk_free_gb) });
      }
      $("sys-comfy").textContent = s.comfy_online ? "on" : "off";
      $("sys-comfy-item")?.classList.toggle("comfy-on", !!s.comfy_online);
      $("sys-comfy-item")?.classList.toggle("comfy-off", !s.comfy_online);
      state.multishot = !!s.multishot;
      state.vfiModel = s.vfi_model || "";
      syncVfiChips();
      syncCinemaStudioMode();
    } catch {
      /* ignore */
    }
  }

  function selectJob(job, { play = true, quiet = false } = {}) {
    state.selectedJobId = job.id;
    state.playerCleared = false;
    const meta = `${job.duration || "?"}${tt("sec")} · ${job.width || "?"}×${job.height || "?"} · ${job.mode || "t2v"}`;
    setClipPrompt(job.prompt || "", meta, job.seed);
    if (play && job.output?.url) {
      showPlayerVideo(job.output.url, job.id, job.prompt || "");
    }
    if (state.produceMode === "continue") {
      const sel = $("continue-source");
      if (sel) sel.value = job.id;
      void setContinueMode(job.id, { silent: true });
    }
    if (!quiet) {
      toast(
        job.status === "done"
          ? tf("job.metaReady", { dur: String(job.duration), sec: tt("sec"), seed: String(job.seed) })
          : tf("job.metaProgress", { status: job.status, pct: String(job.progress || 0) })
      );
    }
  }

  /** When a job flips to done, put that clip in the player (latest finish wins). */
  function autoPlayNewestFinished(prevStatus) {
    const newly = [];
    for (const j of state.jobs || []) {
      const was = prevStatus[j.id];
      if (j.status === "done" && j.output?.url && was && was !== "done") {
        newly.push(j);
      }
    }
    if (!newly.length) return;
    newly.sort((a, b) => {
      const ta = Number(a.done_at || a.created_at || 0);
      const tb = Number(b.done_at || b.created_at || 0);
      if (tb !== ta) return tb - ta;
      return (Number(b.batch_index) || 0) - (Number(a.batch_index) || 0);
    });
    selectJob(newly[0], { play: true, quiet: true });
  }

  function jobLane(j) {
    const lane = String(j?.lane || "").trim().toLowerCase();
    if (lane === "director" || lane === "scene") return lane;
    if (j?.cinema_batch || j?.batch_id) return "director";
    return "scene";
  }

  function setProdLane(lane) {
    const next = lane === "director" ? "director" : "scene";
    state.prodLane = next;
    document.querySelectorAll("#prod-lane-tabs .chip").forEach((btn) => {
      btn.classList.toggle("on", btn.dataset.lane === next);
    });
    renderJobs();
  }

  function refreshStudioWorkspaceChrome() {
    const ws = state.studioWorkspace === "director" ? "director" : "scene";
    const titleEl = $("scene-zone-title");
    const subEl = $("scene-zone-sub");
    if (titleEl) {
      titleEl.textContent = ws === "director" ? tt("ws.directorTitle") : tt("ws.sceneTitle");
    }
    if (subEl) {
      subEl.innerHTML = ws === "director" ? tt("ws.directorSub") : tt("ws.sceneSub");
    }
  }

  function setStudioWorkspace(ws) {
    const next = ws === "director" ? "director" : "scene";
    const changed = state.studioWorkspace !== next;
    state.studioWorkspace = next;
    document.body.classList.toggle("ws-director", next === "director");
    document.body.classList.toggle("ws-scene", next === "scene");
    document.querySelectorAll("#workspace-switch .chip[data-ws]").forEach((btn) => {
      const on = btn.dataset.ws === next;
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    // Landing unused — Direktör opens cinema dock directly
    $("panel-workspace-director")?.classList.add("hidden");
    $("panel-workspace-scene")?.classList.toggle("hidden", next !== "scene");
    refreshStudioWorkspaceChrome();
    if (changed) {
      setProdLane(next);
      if (next === "director") {
        void openCinemaStudio();
      } else {
        if (state.produceMode === "cinema") setProduceMode("t2v");
        if (!$("view-cinema")?.classList.contains("hidden")) closeCinemaStudio();
      }
    }
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
    const laneJobs = state.jobs.filter((j) => jobLane(j) === state.prodLane);
    const active = laneJobs
      .filter((j) => j.status === "running" || j.status === "queued")
      .sort(productionOrderCmp);
    const finished = laneJobs
      .filter((j) => j.status !== "running" && j.status !== "queued")
      .sort(byFinishedThenRecent)
      .slice(0, 40);
    const jobs = active.concat(finished);
    const head = document.querySelector(".job-queue-head");
    if (head) {
      const qn = active.filter((j) => j.status === "queued").length;
      const rn = active.some((j) => j.status === "running");
      const laneLabel = state.prodLane === "director" ? tt("prod.laneDirector") : tt("prod.laneScene");
      head.textContent = rn
        ? `${laneLabel} · ${tf("prod.queueRun", { n: qn })}`
        : qn
          ? `${laneLabel} · ${tf("prod.queueN", { n: qn })}`
          : `${laneLabel} · ${tt("prod.queue")}`;
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
      const stName = tt("job." + j.status);
      const stText = stName.indexOf("job.") === 0 ? j.status : stName;
      left.innerHTML = `${sira}<span class="${st}">${stText}</span>${pct} · ${(j.prompt || "").slice(0, 36)}${err}`;
      left.title = j.error || j.prompt || "";
      left.style.cursor = j.prompt ? "pointer" : "";
      if (j.prompt) {
        left.onclick = (e) => {
          e.stopPropagation();
          openPromptView(
            j.prompt,
            `${j.duration || "?"}${tt("sec")} · ${j.width || "?"}×${j.height || "?"} · ${j.mode || "t2v"}`,
            j.seed
          );
        };
      }
      const right = document.createElement("div");
      if (j.prompt) {
        const cp = document.createElement("button");
        cp.textContent = tt("job.prompt");
        cp.className = "btn-ghost";
        cp.title = tt("job.promptTitle");
        cp.onclick = (e) => {
          e.stopPropagation();
          openPromptView(
            j.prompt,
            `${j.duration || "?"}${tt("sec")} · ${j.width || "?"}×${j.height || "?"} · ${j.mode || "t2v"}`,
            j.seed
          );
        };
        right.appendChild(cp);
      }
      if (j.status === "done") {
        const b = document.createElement("button");
        b.textContent = tt("job.play");
        b.onclick = () => selectJob(j);
        right.appendChild(b);
        const rm = document.createElement("button");
        rm.textContent = tt("job.del");
        rm.className = "btn-ghost";
        rm.onclick = (e) => {
          e.stopPropagation();
          void deleteJob(j.id);
        };
        right.appendChild(rm);
      } else if (j.status === "error" || j.status === "cancelled") {
        const b = document.createElement("button");
        b.textContent = tt("job.retry");
        b.onclick = async (e) => {
          e.stopPropagation();
          b.disabled = true;
          try {
            const r = await fetch(`/api/jobs/${j.id}/retry`, { method: "POST" });
            const data = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(errDetail(data));
            toast(tt("toast.retryQueued"));
            await refreshJobs();
          } catch (err) {
            toast(String(err.message || err));
            b.disabled = false;
          }
        };
        right.appendChild(b);
        const rm = document.createElement("button");
        rm.textContent = tt("job.del");
        rm.className = "btn-ghost";
        rm.onclick = (e) => {
          e.stopPropagation();
          void deleteJob(j.id);
        };
        right.appendChild(rm);
      } else {
        // Each live queue row can be stopped independently. This deliberately
        // differs from the toolbar action, which cancels the whole queue.
        const stop = document.createElement("button");
        stop.textContent = tt("job.stop");
        stop.className = "btn-ghost btn-job-stop";
        stop.title = tt("job.stopTitle");
        stop.onclick = async (e) => {
          e.stopPropagation();
          stop.disabled = true;
          try {
            const r = await fetch(`/api/jobs/${j.id}/cancel`, { method: "POST" });
            const data = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(errDetail(data));
            tToast("toast.stopped");
            await refreshJobs();
          } catch (err) {
            toast(String(err.message || err));
            stop.disabled = false;
          }
        };
        right.appendChild(stop);
        const order = document.createElement("span");
        order.className = "job-order";
        if (j.batch_index) {
          order.textContent = `${j.batch_index}/${j.batch_total}`;
        } else if (activeOrder.has(j.id)) {
          order.textContent = tf("job.order", { i: String(activeOrder.get(j.id)), total: String(active.length) });
        }
        if (order.textContent) right.appendChild(order);
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
      const progressSource = job.progress_source;
      let clipPct = Math.max(0, Math.min(100, Number(job.progress) || 0));
      // Prefer live Comfy sampler fraction when present
      if (progressSource !== "queue" && step != null && stepMax > 0) {
        clipPct = Math.max(0, Math.min(100, Math.round((100 * Number(step)) / Number(stepMax))));
      }
      let clipLabel = job.progress_label || tt("prod.comfyProgress");
      if (progressSource !== "queue" && step != null && stepMax > 0 && !/örnekleme\s+\d+\/\d+/i.test(clipLabel)) {
        clipLabel = tf("job.sampling", { step: String(step), max: String(stepMax) });
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
        bits.push(tf("job.batchSeries", { pct: String(Math.round(overall)) }));
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
      toast(tf("toast.rendering", { batch, res }));
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
      toast(tf("toast.queuedN", { idx, n: String(queued) }));
      const bar = productionBar(next);
      setProgress(Math.max(0.5, bar.pct), bar.label || tt("prod.wait"), true);
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
            tf("job.metaReady", { dur: String(j.duration), sec: tt("sec"), seed: String(j.seed) }) + (j.width ? ` · ${j.width}×${j.height}` : "")
          );
          setProgress(100, tt("prod.done"), true);
          scheduleHideProgress(2200);
          if (j.output?.url) {
            selectJob(j, { play: true, quiet: true });
          }
          fillContinueSource();
        } else if (j?.status === "cancelled") {
          tToast("toast.stopped");
          setProgress(0, tt("job.cancelled"), true);
          scheduleHideProgress(1400);
        } else if (j?.status === "error") {
          toast(tf("toast.errorShort", { msg: String(j.error || "").slice(0, 80) }));
          setProgress(0, "hata", true);
          scheduleHideProgress(2200);
        } else {
          // Job removed from list (geçmiş temiz / reset)
          hideProgressNow();
          tToast("prod.ready");
        }
      } else if (!state.progressHideTimer) {
        // Nothing active and not in brief post-finish display — kill sticky bar
        const wrap = $("progress-wrap");
        if (wrap && !wrap.classList.contains("hidden")) {
          setProgress(0, "", false);
        }
        const pt = $("prod-text");
        if (pt && /^(İptal|Üret|Sirada|Sırada|Stopped|Rendering|Queued|Cancel)/i.test(pt.textContent || "")) {
          toast(tt("prod.ready"));
        }
      }
    }
  }

  async function renderGallery() {
    const grid = $("gallery-grid");
    if (!grid) return;
    grid.innerHTML = `<p class="muted">${tt("gallery.loading")}</p>`;
    let done = [];
    try {
      const data = await fetch("/api/gallery").then((r) => r.json());
      done = (data.items || []).slice();
      state.galleryItems = done;
    } catch {
      grid.innerHTML = `<p class="muted">${tt("gallery.fail")}</p>`;
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
      grid.innerHTML = `<p class="muted">${tt("gallery.empty")}</p>`;
      syncMergeToolbar();
      return;
    }
    grid.innerHTML = "";
    const mergeOn = !!state.galleryMergeMode;
    const picked = state.mergePickIds || [];
    done.forEach((j, i) => {
      const card = document.createElement("div");
      card.className = "gallery-card";
      card.dataset.id = j.id;
      const pickOrder = picked.indexOf(j.id);
      if (pickOrder >= 0) card.classList.add("is-merge-picked");
      const url = j.url || `/api/gallery/${j.id}/video`;
      const ord =
        j.batch_index && j.batch_total
          ? `${j.batch_index}/${j.batch_total}`
          : `#${done.length - i}`;
      const when = j.done_at || j.created_at;
      const clock = when
        ? new Date(Number(when) * 1000).toLocaleString(uiLang() === "en" ? "en-US" : "tr-TR", {
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
        if (sec < 60) renderLabel = tt("gallery.renderUnderMin");
        else {
          const h = Math.floor(sec / 3600);
          const m = Math.floor((sec % 3600) / 60);
          renderLabel = h > 0 ? tf("gallery.renderHM", { h: String(h), m: String(m) }) : tf("gallery.renderM", { m: String(m) });
        }
      }
      card.innerHTML = `
        <div class="gallery-ord">${i === 0 ? tt("gallery.newPrefix") : ""}${ord}</div>
        <button type="button" class="gallery-del" title="${tt("gallery.deleteTitle")}" aria-label="${tt("gallery.deleteAria")}">×</button>
        <div class="gallery-thumb">
          <video src="${url}" muted preload="metadata"></video>
          <button type="button" class="gallery-merge-pick${mergeOn ? "" : " hidden"}" aria-label="${tt("merge.pick")}">
            <span class="gallery-merge-ring${pickOrder >= 0 ? " is-on" : ""}"></span>
            <span class="gallery-merge-badge${pickOrder >= 0 ? " is-on" : ""}">${pickOrder >= 0 ? pickOrder + 1 : ""}</span>
          </button>
          ${j.prompt ? `<button type="button" class="gallery-prompt" title="${tt("gallery.promptTitle")}">P</button>` : ""}
          <button type="button" class="gallery-cont" title="${tt("gallery.contTitle")}">${tt("gallery.contBtn")}</button>
          <button type="button" class="gallery-still btn-ghost" title="${tt("gallery.stillTitle")}">${tt("gallery.stillBtn")}</button>
        </div>
        <div class="meta">${j.duration != null ? j.duration + tt("sec") + " · " : ""}${j.width || "?"}×${j.height || "?"} · ${j.mode || "t2v"}${renderLabel ? " · " + renderLabel : ""}${clock ? " · " + clock : ""}</div>`;
      const pickBtn = card.querySelector(".gallery-merge-pick");
      if (pickBtn) {
        pickBtn.classList.toggle("hidden", !mergeOn);
        pickBtn.onclick = (e) => {
          e.preventDefault();
          e.stopPropagation();
          toggleGalleryMergePick(j.id);
        };
      }
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
            `${j.duration != null ? j.duration + tt("sec") + " · " : ""}${j.width || "?"}×${j.height || "?"}`,
            j.seed
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
      const stillBtn = card.querySelector(".gallery-still");
      if (stillBtn) {
        stillBtn.onclick = (e) => {
          e.preventDefault();
          e.stopPropagation();
          void stillFromGalleryClip(j);
        };
      }
      card.onclick = () => {
        if (state.galleryMergeMode) {
          toggleGalleryMergePick(j.id);
          return;
        }
        const live = state.jobs.find((x) => x.id === j.id && x.status === "done");
        const meta = `${j.duration != null ? j.duration + tt("sec") + " · " : ""}${j.width || "?"}×${j.height || "?"}`;
        if (live) {
          selectJob(live);
        } else {
          showPlayerVideo(url, j.id, j.prompt || "", j.download_name || "");
          setClipPrompt(j.prompt || "", meta, j.seed);
          toast(tf("gallery.archiveMeta", { meta }));
        }
        $("view-gallery").classList.add("hidden");
        closePromptView();
      };
      grid.appendChild(card);
    });
    syncMergeToolbar();
    syncGalleryMergeHeader();
  }

  async function deleteGalleryItem(itemId) {
    if (!itemId) return;
    if (!tConfirm("confirm.deleteGalleryVideo")) return;
    if (state.selectedJobId === itemId) clearPlayer();
    document.querySelectorAll("#gallery-grid video").forEach((v) => {
      const src = v.getAttribute("src") || v.src || "";
      if (!src.includes(itemId)) return;
      try {
        v.pause();
      } catch {
        /* ignore */
      }
      v.removeAttribute("src");
      v.load();
    });
    try {
      const r = await fetch(`/api/gallery/${encodeURIComponent(itemId)}`, {
        method: "DELETE",
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      tToast("toast.galleryDeleted");
      await renderGallery();
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  function applySheetStillsFromJobs() {
    const c = ensureCinema();
    if (!c) return false;
    let changed = false;
    (state.jobs || []).forEach((j) => {
      if (!j?.sheet_attached || !j.sheet_asset_id) return;
      const urls = Array.isArray(j.sheet_still_urls) && j.sheet_still_urls.length
        ? j.sheet_still_urls
        : (j.sheet_still_url ? [j.sheet_still_url] : []);
      if (!urls.length) return;
      const item = cinemaItem(j.sheet_kind || "character", j.sheet_asset_id);
      if (!item || cinemaAssetImages(item).length >= urls.length) return;
      item.images = urls.map((url) => {
        const file = String(url).split("/").pop() || "";
        return { name: "", file, url };
      });
      item.image = item.images[0].file;
      item.url = item.images[0].url;
      changed = true;
    });
    return changed;
  }

  async function refreshJobs() {
    try {
      const data = await fetch("/api/jobs").then((r) => r.json());
      const prevStatus = state.jobStatusSnapshot || {};
      state.jobs = data.jobs || [];
      state.jobStatusSnapshot = Object.fromEntries(
        (state.jobs || []).map((j) => [j.id, j.status])
      );
      const sheetJustDone = (state.jobs || []).some(
        (j) =>
          j.sheet_attached &&
          j.status === "done" &&
          prevStatus[j.id] &&
          prevStatus[j.id] !== "done"
      );
      if (sheetJustDone) {
        const typing =
          cinemaAssetCardsTyping("character") ||
          cinemaAssetCardsTyping("creature") ||
          cinemaAssetCardsTyping("location");
        if (!typing) await loadCinema();
        else if (applySheetStillsFromJobs()) {
          renderCinemaAssetCards("character", { force: true });
          renderCinemaAssetCards("creature", { force: true });
          renderCinemaAssetCards("location", { force: true });
        }
      } else if (applySheetStillsFromJobs()) {
        renderCinemaAssetCards("character", { force: true });
        renderCinemaAssetCards("creature", { force: true });
        renderCinemaAssetCards("location", { force: true });
      }
      renderJobs();
      autoPlayNewestFinished(prevStatus);
      fillContinueSource();
      if (!$("view-cinema")?.classList.contains("hidden")) {
        syncCinemaShotJobs();
        if (!cinemaTypingShots()) renderCinemaAudio();
      }
      if (!state.playerCleared && state.selectedJobId) {
        const j = state.jobs.find((x) => x.id === state.selectedJobId);
        if (j?.status === "done" && j.output?.url) {
          const player = $("player");
          if (player && !player.src.includes(j.id)) selectJob(j, { quiet: true });
        }
      }
      syncMergeToolbar();
      void pollFilmPlan();
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
        tToast("toast.lastFrameFail");
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
      tToast("toast.pickVideoFirst");
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
    $("view-support")?.classList.add("hidden");
    const url =
      job.url ||
      job.output?.url ||
      `/api/gallery/${jobId}/video`;
    showPlayerVideo(url, jobId, job.prompt || "");
    if (job.prompt) setClipPrompt(job.prompt, undefined, job.seed);
    setProduceMode("continue");
    await fillContinueSource();
    const sel = $("continue-source");
    if (sel) {
      if (![...sel.options].some((o) => o.value === jobId)) {
        const opt = document.createElement("option");
        opt.value = jobId;
        opt.textContent = tf("cont.galleryOption", { label: (job.prompt || jobId).slice(0, 42) });
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
      if (!silent) tToast("toast.continuePickJob");
      return false;
    }
    state.continueFrom = jobId;
    state.selectedJobId = jobId;
    // A continuation begins from this clip's last frame, so preserve its canvas.
    // Older gallery entries may lack `aspect`; derive it from their saved dimensions.
    syncContinueAspect(job);
    const sel = $("continue-source");
    if (sel) sel.value = jobId;
    const lab = $("continue-label");
    if (lab) {
      lab.textContent =
        status === "done" || status === "archive"
          ? `Son kare · ${(job.prompt || "").slice(0, 40)}`
          : tf("toast.continueAfterJob", { status, preview: (job.prompt || "").slice(0, 32) });
    }
    if (status === "done" || status === "archive") {
      $("continue-box")?.classList.remove("hidden");
      if (!silent) tToast("toast.continueFramePrep");
      await ensureLastFrame(jobId);
      if (!silent) tToast("toast.continueSourceReady");
    } else {
      $("continue-box")?.classList.add("hidden");
      if (!silent) tToast("toast.continueWillQueue");
    }
    return true;
  }

  async function submitGenerate() {
    const prompt = $("prompt").value.trim();
    if (!prompt) {
      tToast("toast.writePrompt");
      return false;
    }
    const mode = state.produceMode;
    if (mode === "cinema" || mode === "storyboard") {
      openCinemaStudio();
      tToast("toast.cinemaQueueFromStudio");
      return false;
    }
    const isContinue = mode === "continue";
    const isRef = mode === "ref";
    const isFace = mode === "face";
    const isV2v = mode === "v2v";
    const isI2v = mode === "t2v" && state.newVideoInput === "i2v";
    const motionChain = isV2v && !!$("motion-chain-15")?.checked;
    if (isContinue) {
      const pick = $("continue-source")?.value || state.continueFrom || "";
      if (pick) {
        await setContinueMode(pick, { silent: true });
      } else {
        const tip = chainTipJob();
        if (tip) await setContinueMode(tip.id, { silent: true });
      }
      if (!state.continueFrom) {
        tToast("toast.continueNoSource");
        fillContinueSource();
        return false;
      }
    }
    if (isRef && !state.refImages.length) {
      tToast("toast.refNeedImage");
      return false;
    }
    if (isFace && !state.faceImages.length) {
      tToast("toast.faceNeedPortrait");
      return false;
    }
    if (isV2v && !state.v2vVideos.length) {
      tToast("toast.v2vNeedMedia");
      return false;
    }
    if (motionChain && state.duration !== 5) {
      tToast("toast.motionChainFiveSec");
      return false;
    }
    if (isI2v && !state.firstFrameName) {
      toast(tt("scene.firstFrame"));
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
                : isI2v
                  ? "i2v"
                  : "t2v",
        continue_from_job_id: isContinue ? state.continueFrom : null,
        audio_continuity: isContinue && !!$("continue-audio-continuity")?.checked,
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
      if (motionChain) body.segments = 3;
      if (isI2v) {
        if (state.firstFrameName) body.first_frame_name = state.firstFrameName;
      }
      // Continue + yüz kilidi → portreleri de gönder (sunucu last frame ile birleştirir)
      if (isContinue && faceLockOn) {
        body.ref_images = state.faceImages.map((x) => x.name);
        body.ref_image_size = "max";
      }
      const r = await fetch(motionChain ? "/api/motion-transfer/chain" : "/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (data.prompt && data.prompt_rewritten) {
        $("prompt").value = data.prompt;
      } else if (data.prompt && !!$("prompt-rewriter-enabled")?.checked) {
        $("prompt").value = data.prompt;
      }
      state.selectedJobId = data.id;
      state.playerCleared = false;
      state.pendingContinueChild = isContinue ? data.id : null;
      state.prodLane = "scene";
      setProdLane("scene");
      const queuedLabel = motionChain
        ? tt("toast.motionChainQueued")
        : isContinue
        ? faceLockOn
          ? tt("toast.continueFaceQueued")
          : tt("toast.continueQueued")
        : isFace
          ? tt("toast.faceRefQueued")
          : isRef
            ? tt("toast.refQueued")
            : data.prompt_rewritten
              ? tt("toast.newVideoQueuedRewrite")
              : tt("toast.newVideoQueued");
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

  function applySpeedProfile(kind) {
    if (kind === "draft") {
      setDuration(5);
      setQuality("480");
      const steps = $("steps");
      if (steps) steps.value = "12";
      applyCinemaSpeed("draft");
      return;
    }
    if (kind === "quick") {
      setDuration(5);
      setQuality("736");
      const steps = $("steps");
      if (steps) steps.value = "15";
      tToast("toast.quickPreset");
    }
  }

  $("btn-generate").onclick = () => submitGenerate();
  $("btn-fast-preset")?.addEventListener("click", () => applySpeedProfile("draft"));
  $("btn-speed-quick")?.addEventListener("click", () => applySpeedProfile("quick"));

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
    updateLoraHint();
  }

  function collectLoraPayload() {
    const picked = [...($("lora-select")?.selectedOptions || [])]
      .map((opt) => (state.loraCatalog || []).find((spec) => spec.id === opt.value))
      .filter((spec) => spec && spec.file && spec.ready)
      .slice(0, 3);
    const spec = picked[0] || appliedLoraSpec();
    if (!spec || !spec.file) return { lora_id: "", lora_name: "", lora_strength: null };
    return {
      lora_id: spec.id,
      lora_name: picked.length ? picked.map((item) => item.file).join("|") : spec.file,
      lora_strength: spec.strength,
    };
  }

  function collectGenerateKnobs() {
    return {
      steps: numOr("steps", 20) || 20,
      sampler: $("sampler")?.value || "res_multistep",
      scheduler: $("scheduler")?.value || "simple",
      sage_attention: "disabled",
      prompt_rewriter_enabled: !!$("prompt-rewriter-enabled")?.checked,
      post_pass: state.postPass || "",
      ...collectLoraPayload(),
    };
  }

  function fillLoraSelect() {
    const sel = $("lora-select");
    if (!sel) return;
    const prev = state.loraApplied && state.loraId ? state.loraId : sel.value || state.loraId || "";
    const catalog = videoLoraCatalog();
    sel.innerHTML = "";
    if (!catalog.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = tt("ayar.loraNoneOpt");
      sel.appendChild(opt);
    } else {
      catalog.forEach((spec) => {
        const opt = document.createElement("option");
        opt.value = spec.id;
        const graphs = spec.graphs || [];
        const still = graphs.includes("still");
        const refOnly = graphs.includes("ref2va") && !graphs.includes("fl2va") && !still;
        const flOnly = graphs.length && !graphs.includes("ref2va") && !still;
        const miss = spec.file && !spec.ready ? tt("ayar.loraNeed") : "";
        const tag = still ? " · still" : refOnly ? " · Ref" : flOnly ? " · T2V" : "";
        opt.textContent = `${spec.label}${tag}${miss}`;
        sel.appendChild(opt);
      });
    }
    if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
    const checks = $("lora-check-list");
    if (checks) {
      const selected = new Set([...sel.selectedOptions].map((o) => o.value));
      checks.innerHTML = catalog
        .filter((spec) => spec.id && spec.file && spec.ready)
        .map((spec) => `<label><input type="checkbox" value="${htmlEsc(spec.id)}" ${selected.has(spec.id) ? "checked" : ""} /> ${htmlEsc(spec.label)}</label>`)
        .join("");
      checks.onchange = () => {
        const ids = [...checks.querySelectorAll("input:checked")].map((box) => box.value).slice(0, 3);
        [...sel.options].forEach((opt) => { opt.selected = ids.includes(opt.value); });
        state.loraId = ids[0] || "";
        state.loraApplied = ids.length > 0;
        updateLoraHint();
      };
    }
    const cine = $("cinema-lora-select");
    if (cine) {
      const cinePrev = cine.value || prev;
      cine.innerHTML = sel.innerHTML;
      if ([...cine.options].some((o) => o.value === cinePrev)) cine.value = cinePrev;
    }
    keepLoraApplied();
    updateLoraHint();
    fillLoraShop();
  }

  function loraSizeLabel(spec) {
    const n = Number(spec?.bytes || 0);
    if (n > 1024 * 1024 * 1024) return `${(n / (1024 * 1024 * 1024)).toFixed(1)} GB`;
    if (n > 1024 * 1024) return `${Math.round(n / (1024 * 1024))} MB`;
    return spec?.size_hint || "";
  }

  function fillLoraShop() {
    const box = $("lora-shop");
    if (!box) return;
    const catalog = visibleLoraCatalog().filter((spec) => spec && spec.file);
    const busyId = state.loraDownload?.busy ? state.loraDownload.id : "";
    box.innerHTML = "";
    catalog.forEach((spec) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "lora-shop-item";
      btn.dataset.id = spec.id;
      if (spec.ready) btn.classList.add("is-ready");
      if (busyId && busyId === spec.id) btn.classList.add("is-busy");
      const graphs = spec.graphs || [];
      const still = graphs.includes("still");
      const refOnly = graphs.includes("ref2va") && !graphs.includes("fl2va") && !still;
      const flOnly = graphs.length && !graphs.includes("ref2va") && !still;
      const size = loraSizeLabel(spec);
      const bits = [size, still ? "still" : refOnly ? "Ref" : flOnly ? "T2V" : ""].filter(Boolean);
      let status = spec.ready ? tt("ayar.loraReady") : (spec.downloadable ? tt("ayar.loraGet") : "");
      if (busyId && busyId === spec.id) status = tt("ayar.loraGetting");
      const name = document.createElement("span");
      name.className = "lora-shop-name";
      name.textContent = spec.label || spec.file;
      const meta = document.createElement("span");
      meta.className = "lora-shop-meta";
      meta.textContent = bits.join(" · ");
      const st = document.createElement("span");
      st.className = "lora-shop-status";
      st.textContent = status;
      btn.appendChild(name);
      btn.appendChild(st);
      btn.appendChild(meta);
      box.appendChild(btn);
    });
  }

  function updateLoraHint() {
    const spec = appliedLoraSpec() || currentLoraSpec();
    const el = $("lora-hint");
    if (!el) return;
    if (!spec || !spec.file) {
      el.textContent = tt("ayar.loraHintEmpty");
      return;
    }
    const dur = state.duration || 5;
    const uiSteps = $("steps") ? $("steps").value : "";
    const rec = spec.steps ? tf("ayar.loraRec", { n: spec.steps }) : tt("ayar.loraRecYou");
    if (!state.loraApplied || spec.id !== state.loraId) {
      el.textContent = tf("ayar.loraHintPick", { label: spec.label, rec, dur, sec: tt("sec") });
      return;
    }
    const graphs = spec.graphs || [];
    const still = graphs.includes("still");
    const refOnly = graphs.includes("ref2va") && !graphs.includes("fl2va") && !still;
    const flOnly = graphs.length && !graphs.includes("ref2va") && !still;
    const extra = still
      ? tt("ayar.loraStillOnly")
      : refOnly
        ? tt("ayar.loraSkipT2v")
        : flOnly
          ? tt("ayar.loraSkipRef")
          : "";
    el.textContent = tf("ayar.loraHintOn", {
      label: spec.label,
      steps: uiSteps || "?",
      rec,
      extra,
      dur,
      sec: tt("sec"),
    });
  }

  async function loadH3Models() {
    const status = $("h3-models-status");
    try {
      const data = await fetch("/api/h3-models").then((r) => r.json());
      if (!data || !data.ok) throw new Error(data?.detail || "fail");
      const selected = data.selected || {};
      const defaults = data.defaults || {};
      const options = data.options || {};
      const slots = [
        ["h3-unet", "unet"],
        ["h3-unet-ref2va", "unet_ref2va"],
        ["h3-clip", "clip"],
        ["h3-vae", "vae"],
        ["h3-audio-vae", "audio_vae"],
      ];
      slots.forEach(([elId, key]) => {
        const sel = $(elId);
        if (!sel) return;
        const files = options[key] || [];
        const cur = selected[key] || "";
        const def = defaults[key] || "";
        sel.innerHTML = "";
        const opt0 = document.createElement("option");
        opt0.value = "";
        opt0.textContent = def
          ? `${tt("settings.h3Default")} (${def})`
          : tt("settings.h3Default");
        sel.appendChild(opt0);
        files.forEach((name) => {
          const opt = document.createElement("option");
          opt.value = name;
          opt.textContent = name === def ? `${name} ★` : name;
          sel.appendChild(opt);
        });
        if (cur && [...sel.options].some((o) => o.value === cur)) sel.value = cur;
        else sel.value = "";
      });
      if (status) status.textContent = "";
    } catch (e) {
      if (status) status.textContent = String(e.message || e);
    }
  }

  async function saveH3Models(reset) {
    const status = $("h3-models-status");
    try {
      const body = reset
        ? { reset: true }
        : {
            unet: $("h3-unet")?.value || "",
            unet_ref2va: $("h3-unet-ref2va")?.value || "",
            clip: $("h3-clip")?.value || "",
            vae: $("h3-vae")?.value || "",
            audio_vae: $("h3-audio-vae")?.value || "",
          };
      const r = await fetch("/api/h3-models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data) || tt("settings.h3Fail"));
      await loadH3Models();
      toast(reset ? tt("settings.h3ResetOk") : tt("settings.h3Saved"));
      if (status) status.textContent = reset ? tt("settings.h3ResetOk") : tt("settings.h3Saved");
    } catch (e) {
      toast(String(e.message || e));
      if (status) status.textContent = String(e.message || e);
    }
  }

  async function loadLoras(retry = true) {
    const checks = $("lora-check-list");
    try {
      const response = await fetch("/api/loras", { cache: "no-store" });
      if (!response.ok) throw new Error(`LoRA listesi alınamadı (${response.status})`);
      const data = await response.json();
      if (!Array.isArray(data.loras)) throw new Error("LoRA listesi geçersiz yanıt verdi");
      state.loraCatalog = data.loras || [];
      state.loraDownload = data.download || {};
      fillLoraSelect();
    } catch (e) {
      if (checks) {
        checks.innerHTML = `<span class="muted">${htmlEsc(String(e.message || e))}</span>`;
      }
      // A Studio restart / cold Comfy start can race the first request. Retry
      // once so the picker does not remain blank without feedback.
      if (retry) setTimeout(() => void loadLoras(false), 1200);
    }
  }

  async function downloadCatalogLora(spec) {
    if (!spec?.id || !spec.file) return spec;
    if (spec.ready) return spec;
    if (!spec.downloadable) {
      throw new Error(tt("err.loraNoUrl"));
    }
    toast(tf("toast.loraDownloadingLabel", { label: spec.label }));
    const r = await fetch("/api/loras/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: spec.id }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(errDetail(data));
    if (data.ready) {
      await loadLoras();
      return (state.loraCatalog || []).find((x) => x.id === spec.id) || spec;
    }
    state.loraDownload = { busy: true, id: spec.id };
    fillLoraShop();
    for (let i = 0; i < 600; i++) {
      await new Promise((res) => setTimeout(res, 2000));
      const st = await fetch("/api/loras").then((x) => x.json());
      state.loraDownload = st.download || {};
      if (st.download?.error) throw new Error(st.download.error);
      const now = (st.loras || []).find((x) => x.id === spec.id);
      if (now?.ready) {
        state.loraCatalog = st.loras || state.loraCatalog;
        fillLoraSelect();
        if ($("lora-select")) $("lora-select").value = spec.id;
        if ($("cinema-lora-select")) $("cinema-lora-select").value = spec.id;
        return now;
      }
      fillLoraShop();
      if (i % 5 === 0) toast(tf("toast.loraDownloadingProgress", { label: spec.label }));
    }
    throw new Error(tt("err.loraStillDownloadingPinokio"));
  }

  async function applyLora() {
    const spec = currentLoraSpec();
    state.loraId = spec?.id || "";
    if (spec && isStillLoraSpec(spec)) {
      toast(tt("toast.loraStillOnly"));
      return;
    }
    if (!spec || !spec.file) {
      state.loraApplied = false;
      if ($("steps")) $("steps").value = "20";
      if ($("sampler")) $("sampler").value = "res_multistep";
      if ($("scheduler")) $("scheduler").value = "simple";
      state.loraStrength = 1;
      updateLoraHint();
      tToast("toast.loraOff");
      return;
    }
    if (!spec.ready) {
      try {
        const got = await downloadCatalogLora(spec);
        if (!got?.ready) return;
      } catch (e) {
        toast(String(e.message || e));
        return;
      }
    }
    const samp = $("sampler");
    if (samp && spec.sampler && ![...samp.options].some((o) => o.value === spec.sampler)) {
      const opt = document.createElement("option");
      opt.value = spec.sampler;
      opt.textContent = spec.sampler;
      samp.appendChild(opt);
    }
    const stepsNow = $("steps") ? $("steps").value : "?";
    const rec = spec.steps ? tf("toast.loraRec", { steps: String(spec.steps) }) : "";
    toast(
      rec
        ? tf("toast.loraAppliedRec", { label: spec.label, steps: String(stepsNow), rec })
        : tf("toast.loraApplied", { label: spec.label, steps: String(stepsNow) })
    );
    state.loraApplied = true;
    state.loraStrength = spec.strength;
    if ($("lora-select")) $("lora-select").value = spec.id;
    if ($("cinema-lora-select")) $("cinema-lora-select").value = spec.id;
    updateLoraHint();
  }

  async function uploadLoraFile(file) {
    if (!file) return;
    if (!/\.safetensors$/i.test(file.name || "")) {
      tToast("toast.safetensorsOnly");
      return;
    }
    toast(tf("toast.loraUploading", { name: file.name }));
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
      tToast("toast.loraAdded");
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function importLoraFromUrl() {
    const url = ($("lora-url")?.value || "").trim();
    if (!url) {
      tToast("toast.loraUrlHint");
      return;
    }
    try {
      tToast("toast.loraDownloadingUrl");
      const r = await fetch("/api/loras/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      const want = data.id || (data.file ? `file:${data.file}` : "");
      if (data.ready) {
        await loadLoras();
        if (want && $("lora-select")) $("lora-select").value = want;
        tToast("toast.loraReadyApply");
        return;
      }
      let ready = false;
      for (let i = 0; i < 600; i++) {
        await new Promise((res) => setTimeout(res, 2000));
        const st = await fetch("/api/loras").then((x) => x.json());
        if (st.download?.error) throw new Error(st.download.error);
        const now = (st.loras || []).find((x) => x.id === want || x.file === data.file);
        if (now?.ready) {
          state.loraCatalog = st.loras || state.loraCatalog;
          fillLoraSelect();
          if ($("lora-select") && want) $("lora-select").value = want;
          ready = true;
          break;
        }
        if (i % 5 === 0) tToast("toast.loraDownloadingUrl");
      }
      if (!ready) tToast("toast.loraStillDownloading");
      else tToast("toast.loraReadyApply");
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  $("lora-select")?.addEventListener("change", () => {
    if ($("cinema-lora-select") && $("lora-select")) {
      $("cinema-lora-select").value = $("lora-select").value;
    }
    updateLoraHint();
  });
  $("btn-lora-refresh")?.addEventListener("click", () => void loadLoras());
  $("cinema-lora-select")?.addEventListener("change", () => {
    if ($("lora-select") && $("cinema-lora-select")) {
      $("lora-select").value = $("cinema-lora-select").value;
    }
    updateLoraHint();
  });
  $("steps")?.addEventListener("input", () => updateLoraHint());
  $("sampler")?.addEventListener("change", () => updateLoraHint());
  $("cinema-seamless")?.addEventListener("change", () => {
    const el = $("cinema-seamless");
    if (el) el.dataset.userSet = "1";
  });
  async function pickLoraFromShop(id) {
    if (!id) return;
    let spec = (state.loraCatalog || []).find((x) => x.id === id);
    if (!spec) return;
    if (isStillLoraSpec(spec)) {
      if (!spec.ready) {
        try {
          spec = await downloadCatalogLora(spec);
        } catch (e) {
          toast(String(e.message || e));
          return;
        }
      }
      toast(tt("toast.loraStillOnly"));
      return;
    }
    if ($("lora-select")) $("lora-select").value = id;
    if ($("cinema-lora-select")) $("cinema-lora-select").value = id;
    state.loraId = id;
    updateLoraHint();
    if (spec.ready) {
      toast(tf("toast.loraSelectedSettings", { label: spec.label }));
      return;
    }
    try {
      spec = await downloadCatalogLora(spec);
      toast(tf("toast.loraDownloadedSettings", { label: spec.label }));
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  $("btn-lora-apply")?.addEventListener("click", () => void applyLora());
  $("lora-shop")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".lora-shop-item");
    if (!btn || !$("lora-shop").contains(btn)) return;
    void pickLoraFromShop(btn.dataset.id || "");
  });
  $("btn-lora-url")?.addEventListener("click", () => void importLoraFromUrl());
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
      renderDirectorPlanBoard();
    }
  }
  document.querySelectorAll("#director-mode-tabs .chip").forEach((btn) => {
    btn.addEventListener("click", () => setDirectorTab(btn.dataset.dirmode));
  });
  $("btn-plan-save")?.addEventListener("click", () => void saveDirectorPlan(false));
  $("btn-plan-to-cinema")?.addEventListener("click", () => void saveDirectorPlan(true));
  $("btn-plan-rewrite")?.addEventListener("click", () => void rewriteDirectorShots());
  $("btn-rewrite-brief")?.addEventListener("click", () => void rewriteDirectorShots());
  $("director-plan-shots")?.addEventListener("click", (e) => {
    const del = e.target.closest(".dir-plan-shot-del");
    if (!del) return;
    e.preventDefault();
    const card = del.closest(".dir-plan-shot");
    if (!card) return;
    const idx = Number(card.dataset.idx);
    if (!Number.isFinite(idx)) return;
    deletePlanShot(idx);
  });
  $("btn-plan-queue")?.addEventListener("click", async () => {
    await saveDirectorPlan(false);
    setProdLane("director");
    void applyBrief(true);
  });
  $("btn-prompt-rewrite")?.addEventListener("click", async () => {
    const prompt = $("prompt")?.value?.trim();
    if (!prompt) {
      toast("Prompt yaz");
      return;
    }
    const btn = $("btn-prompt-rewrite");
    if (btn) btn.disabled = true;
    try {
      toast(tt("prompt.rewriting"));
      const r = await fetch("/api/prompt/rewrite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          prompt_rewriter_enabled: true,
          context: `mode=${state.produceMode || "t2v"}`,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (data.prompt) $("prompt").value = data.prompt;
      toast(data.rewritten ? tt("prompt.rewritten") : tt("prompt.unchanged"));
    } catch (e) {
      toast(String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
    }
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
      tToast("toast.directorBriefGenerating");
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
          ? tf("dir.briefToastReady", { n: String(n) })
          : (data.reply || tt("dir.briefReady")).slice(0, 120)
      );
    } catch (e) {
      toast(String(e.message || e));
    }
  });

  document.querySelectorAll("#mode-chips .chip").forEach((btn) => {
    btn.addEventListener("click", () => setProduceMode(btn.dataset.mode));
  });
  document.querySelectorAll("#new-video-input-chips .chip").forEach((btn) => {
    btn.addEventListener("click", () => setNewVideoInput(btn.dataset.newinput));
  });
  document
    .querySelectorAll("#dur-chips .chip, #dur-chips-cont .chip, #dur-chips-story .chip")
    .forEach((btn) => {
      btn.addEventListener("click", () => setDuration(btn.dataset.dur));
    });
  document.querySelectorAll("#quality-chips .chip, #quality-chips-cont .chip").forEach((btn) => {
    btn.addEventListener("click", () => setQuality(btn.dataset.q));
  });
  document
    .querySelectorAll("#post-pass-chips .chip, #post-pass-chips-cont .chip, #cinema-post-pass-chips .chip, #director-post-pass-chips .chip")
    .forEach((btn) => {
      btn.addEventListener("click", () => setPostPass(btn.dataset.post || ""));
    });
  $("cinema-character-voice-file")?.addEventListener("change", (e) => {
    syncFilePickName(e.target);
    const f = e.target.files && e.target.files[0];
    if (f) void uploadCinemaVoiceClip(f);
    e.target.value = "";
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
  $("btn-image-studio-ref")?.addEventListener("click", () => void generateImageStudioReference());
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
  async function refreshPromptRewriterStatus() {
    const status = $("prompt-rewriter-status");
    if (!status) return;
    try {
      const data = await fetch("/api/prompt-rewriter/status").then((r) => r.json());
      status.textContent = data.available ? tt("prompt.optimizeReady") : tt("prompt.optimizeOffline");
      const toggle = $("prompt-rewriter-enabled");
      if (toggle) toggle.disabled = !data.available;
    } catch {
      status.textContent = tt("prompt.optimizeStatusFail");
    }
  }

  
  document.querySelectorAll(".cinema-asset-tabs").forEach((tabs) => {
    tabs.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-asset-tab]");
      if (!btn) return;
      setCinemaAssetTab(tabs.dataset.assetKind, btn.dataset.assetTab);
    });
  });
  
  document.querySelectorAll("#cinema-char-library, #cinema-loc-library, #cinema-creature-library").forEach((root) => {
    root.addEventListener("click", (e) => {
      const kind = root.id.includes("creature")
        ? "creature"
        : root.id.includes("loc")
          ? "location"
          : "character";
      const pull = e.target.closest(".cinema-lib-pull");
      if (pull) {
        e.preventDefault();
        const card = pull.closest(".cinema-lib-card");
        if (!card) return;
        void pullCinemaLibraryAsset(kind, card.dataset.id || "").catch((err) =>
          toast(String(err.message || err))
        );
        return;
      }
      const thumb = e.target.closest(".cinema-lib-thumb");
      if (thumb && thumb.dataset.full) {
        e.preventDefault();
        openCinemaStill(thumb.dataset.full, thumb.dataset.name || "still.png");
        return;
      }
      const del = e.target.closest(".cinema-lib-del");
      if (del) {
        e.preventDefault();
        const card = del.closest(".cinema-lib-card");
        if (!card) return;
        if (!confirm(tt("confirm.deleteCard") || "Sil?")) return;
        void fetch(
          "/api/cinema/library/" +
            encodeURIComponent(kind) +
            "/" +
            encodeURIComponent(card.dataset.id || ""),
          { method: "DELETE" }
        )
          .then(async (r) => {
            const data = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(data.detail || "silinemedi");
            toast(tt("cinema.libDeleted") || "Silindi");
            await loadCinemaLibrary();
          })
          .catch((err) => toast(String(err.message || err)));
      }
    });
  });

  $("btn-cinema-create-char")?.addEventListener("click", () => void generateCinemaSheet("character"));
  $("btn-cinema-create-loc")?.addEventListener("click", () => void generateCinemaSheet("location"));
  $("btn-cinema-create-creature")?.addEventListener("click", () => void generateCinemaSheet("creature"));
  $("btn-cinema-save-char-lib")?.addEventListener("click", () => void saveCinemaAssetToLibrary("character"));
  $("btn-cinema-save-loc-lib")?.addEventListener("click", () => void saveCinemaAssetToLibrary("location"));
  $("btn-cinema-save-creature-lib")?.addEventListener("click", () => void saveCinemaAssetToLibrary("creature"));
  $("btn-cinema-add-creature")?.addEventListener("click", () => void addCinemaAsset("creature"));
  ["cinema-char-face-file", "cinema-loc-ref-file", "cinema-creature-ref-file"].forEach((id) => {
    $(id)?.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const kind = id.includes("loc") ? "location" : id.includes("creature") ? "creature" : "character";
      const ui = cinemaSheetRefUi(kind);
      try {
        const fd = new FormData();
        fd.append("file", file);
        const r = await fetch("/api/refs/upload", { method: "POST", body: fd });
        const body = await r.json();
        if (!r.ok) throw new Error(body.detail || "upload failed");
        const name = body.name || body.filename || "";
        state.cinemaSheetRefs = state.cinemaSheetRefs || { character: null, location: null, creature: null };
        state.cinemaSheetRefs[ui.key] = {
          name,
          filename: name,
          url: body.url || ("/api/refs/" + encodeURIComponent(name)),
          file: name,
        };
        renderCinemaSheetRefPreview(kind);
      } catch (err) {
        toast(String(err.message || err));
      }
    });
  });
  $("btn-cinema-char-face-clear")?.addEventListener("click", () => clearCinemaSheetRef("character"));
  $("btn-cinema-loc-ref-clear")?.addEventListener("click", () => clearCinemaSheetRef("location"));
  $("btn-cinema-creature-ref-clear")?.addEventListener("click", () => clearCinemaSheetRef("creature"));

  $("btn-open-cinema")?.addEventListener("click", () => void openCinemaStudio());
  $("btn-open-cinema-landing")?.addEventListener("click", () => void openCinemaStudio());
  $("workspace-switch")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-ws]");
    if (!btn) return;
    e.preventDefault();
    setStudioWorkspace(btn.dataset.ws);
  });
  $("btn-cinema")?.addEventListener("click", () => {
    setStudioWorkspace("director");
    void openCinemaStudio();
  });
  $("btn-cinema-close")?.addEventListener("click", () => closeCinemaStudio());
  $("btn-cinema-plan")?.addEventListener("click", () => void planCinemaWithDirector());
  $("cinema-studio-mode")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-cinemamode]");
    if (!btn) return;
    setCinemaStudioMode(btn.dataset.cinemamode);
  });
  $("prompt-rewriter-enabled")?.addEventListener("change", () => {
    void saveProduction({ quiet: true });
  });
  (async () => {
    await refreshPromptRewriterStatus();
  })();
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
  $("btn-cinema-add-draft")?.addEventListener("click", () => addCinemaDraftShot());
  $("btn-cinema-save")?.addEventListener("click", () => void saveCinema(false));
  $("btn-cinema-produce")?.addEventListener("click", () => void produceCinema());
  $("cinema-duration")?.addEventListener("change", () => {
    ensureCinema().duration = Number($("cinema-duration").value) || 5;
    void saveCinema(true);
  });
  $("cinema-title")?.addEventListener("change", () => {
    ensureCinema().title = $("cinema-title").value;
    void saveCinema(true);
  });
  $("cinema-steps")?.addEventListener("change", () => {
    ensureCinema().steps = Number($("cinema-steps").value) || 20;
    void saveCinema(true);
  });
  $("cinema-quality-chips")?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-quality]");
    if (!btn) return;
    ensureCinema().quality = normalizeQuality(btn.dataset.quality);
    renderCinemaKnobs();
    void saveCinema(true);
  });
  $("cinema-audio-mode")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-audio]");
    if (!btn) return;
    cinemaAudio().mode = btn.dataset.audio === "silent" ? "silent" : "film";
    renderCinemaAudio();
    renderCinemaTimeline();
    void saveCinema(true);
  });
  $("cinema-score-file")?.addEventListener("change", (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    void uploadCinemaScore(f);
  });
  $("btn-cinema-mux")?.addEventListener("click", () => void muxCinemaScore());
  $("btn-cinema-score-remove")?.addEventListener("click", () => {
    void deleteUploadedMusic(cinemaAudio().score_id, "cinema");
  });
  $("btn-cinema-concat")?.addEventListener("click", () => void concatCinemaFilm());
  $("btn-gallery-concat")?.addEventListener("click", () => onGalleryConcatClick());
  $("btn-gallery-merge-cancel")?.addEventListener("click", () => exitGalleryMergeMode());
  $("btn-merge-clips")?.addEventListener("click", () => void enterGalleryMergeMode({}));
  $("btn-cinema-film-new")?.addEventListener("click", () => {
    void cinemaFilmAction("new")
      .then(() => toast(tt("cinema.filmNew")))
      .catch((err) => toast(String(err.message || err)));
  });
  $("btn-cinema-film-delete")?.addEventListener("click", async () => {
    const id = ($("cinema-film-select")?.value || ensureCinema().film_id || "").trim();
    if (!id) return;
    if (!confirm("Bu filmi silmek istediğine emin misin?")) return;
    try {
      const r = await fetch("/api/cinema/films", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "delete", id }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      state.cinema = { ...emptyCinema(), ...data };
      renderCinema();
      await fillCinemaFilms();
      toast("Film silindi");
    } catch (e) {
      toast(String(e.message || e));
    }
  });
  $("cinema-film-select")?.addEventListener("change", (e) => {
    const id = e.target.value;
    if (!id || id === ensureCinema().film_id) return;
    void cinemaFilmAction("switch", id)
      .then(() => toast(tt("cinema.filmSwitched")))
      .catch((err) => toast(String(err.message || err)));
  });
  $("btn-cinema-export")?.addEventListener("click", () => {
    window.location.href = "/api/cinema/export";
  });

  function openCinemaJsonModal() {
    const modal = $("cinema-json-modal");
    if (!modal) return;
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    $("cinema-json-text")?.focus();
  }

  function closeCinemaJsonModal() {
    const modal = $("cinema-json-modal");
    modal?.classList.add("hidden");
    modal?.setAttribute("aria-hidden", "true");
  }

  async function applyCinemaJsonResult(data) {
    const cinemaData = data && data.cinema ? data.cinema : data;
    if (!cinemaData || typeof cinemaData !== "object") {
      throw new Error(tt("cinema.jsonBad"));
    }
    const base = emptyCinema();
    state.cinema = {
      ...base,
      ...cinemaData,
      setup: { ...base.setup, ...(cinemaData.setup || {}) },
      audio: { ...base.audio, ...(cinemaData.audio || {}) },
      characters: cinemaData.characters || [],
      locations: cinemaData.locations || [],
      creatures: cinemaData.creatures || [],
      shots: cinemaData.shots || [],
    };
    renderCinema();
    await fillCinemaFilms();
    const c = data && data.counts ? data.counts : null;
    const extra = c
      ? ` · ${c.characters || 0} char / ${c.locations || 0} loc / ${c.creatures || 0} yaratık / ${c.takes || 0} take / ${c.sections || 0} shot`
      : "";
    const kept = data && data.stills_kept ? data.stills_kept : {};
    const keptN =
      Number(kept.characters || 0) +
      Number(kept.locations || 0) +
      Number(kept.creatures || 0);
    const keptTxt = keptN ? ` · ${tf("cinema.jsonStillsKept", { n: String(keptN) })}` : "";
    const warn = Array.isArray(data.warnings) ? data.warnings.filter(Boolean) : [];
    toast(tt("cinema.jsonImported") + extra + keptTxt + (warn.length ? " · " + warn[0] : ""));
    const isSeamless = !!(data.seamless || cinemaData.studio_mode === "seamless" || data.studio_mode === "seamless");
    if (isSeamless) setCinemaStudioMode("seamless");
    const hint = $("cinema-prod-hint");
    if (hint) {
      hint.textContent = isSeamless
        ? tt("cinema.jsonReadyProduceSeamless")
        : tt("cinema.jsonReadyProduce");
      hint.classList.remove("hidden");
    }
    $("btn-cinema-produce")?.classList.add("is-ready");
    $("btn-cinema-produce")?.focus();
  }

  async function importCinemaJsonPayload(payload) {
    const merge = !!$("cinema-json-merge")?.checked;
    const toLib = !!$("cinema-json-library")?.checked;
    const redoChars = !!$("cinema-json-redo-chars")?.checked;
    if ($("cinema-force-sheets")) $("cinema-force-sheets").checked = redoChars;
    const r = await fetch("/api/cinema/import-json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        payload: payload,
        mode: merge ? "merge" : "replace",
        save_to_library: toLib,
        new_film: !merge,
        generate_sheets: false,
        keep_stills: true,
        redo_characters: redoChars,
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(errDetail(data));
    await applyCinemaJsonResult(data);
    closeCinemaJsonModal();
  }

  $("btn-cinema-json")?.addEventListener("click", () => openCinemaJsonModal());
  $("btn-cinema-json-close")?.addEventListener("click", () => closeCinemaJsonModal());
  $("cinema-still-modal-close")?.addEventListener("click", closeCinemaStill);
  $("cinema-still-modal")?.addEventListener("click", (e) => {
    if (e.target === $("cinema-still-modal")) closeCinemaStill();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("cinema-still-modal")?.classList.contains("hidden")) {
      closeCinemaStill();
    }
  });
  $("btn-cinema-json-cancel")?.addEventListener("click", () => closeCinemaJsonModal());
  $("cinema-json-modal")?.addEventListener("click", (e) => {
    if (e.target === $("cinema-json-modal")) closeCinemaJsonModal();
  });
  $("cinema-json-file")?.addEventListener("change", (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      if ($("cinema-json-text")) $("cinema-json-text").value = text;
    };
    reader.readAsText(f, "utf-8");
  });
  $("btn-cinema-json-export")?.addEventListener("click", () => {
    void fetch("/api/cinema/export-json")
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errDetail(data));
        const blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json;charset=utf-8",
        });
        const a = document.createElement("a");
        const title = String(data.title || "film").replace(/[^\w\-]+/g, "_").slice(0, 40) || "film";
        a.href = URL.createObjectURL(blob);
        a.download = title + ".h3cinema.json";
        a.click();
        URL.revokeObjectURL(a.href);
        toast(tt("cinema.jsonExported"));
      })
      .catch((err) => toast(String(err.message || err)));
  });
  function downloadCinemaJsonTemplate(kind) {
    const qs = kind === "seamless" ? "?kind=seamless" : "";
    const file =
      kind === "seamless"
        ? "h3-cinema-seamless-v1-template.json"
        : "h3-cinema-v1-template.json";
    void fetch("/api/cinema/json-template" + qs)
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errDetail(data));
        const text = JSON.stringify(data, null, 2);
        if ($("cinema-json-text")) $("cinema-json-text").value = text;
        const blob = new Blob([text], { type: "application/json;charset=utf-8" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = file;
        a.click();
        URL.revokeObjectURL(a.href);
        toast(
          kind === "seamless"
            ? tt("cinema.jsonTemplateSeamlessDone")
            : tt("cinema.jsonTemplateDone")
        );
      })
      .catch((err) => toast(String(err.message || err)));
  }

  $("btn-cinema-json-template")?.addEventListener("click", () => {
    downloadCinemaJsonTemplate("");
  });
  $("btn-cinema-json-template-seamless")?.addEventListener("click", () => {
    downloadCinemaJsonTemplate("seamless");
  });
  $("btn-cinema-json-import")?.addEventListener("click", () => {
    void (async () => {
      const raw = ($("cinema-json-text")?.value || "").trim();
      if (!raw) {
        toast(tt("cinema.jsonNeed"));
        return;
      }
      let payload;
      try {
        payload = JSON.parse(raw);
      } catch (err) {
        toast(tt("cinema.jsonBad") + ": " + String(err.message || err));
        return;
      }
      try {
        await importCinemaJsonPayload(payload);
      } catch (err) {
        toast(String(err.message || err));
      }
    })();
  });

  $("cinema-import-file")?.addEventListener("change", (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    const name = String(f.name || "").toLowerCase();
    if (name.endsWith(".json")) {
      const reader = new FileReader();
      reader.onload = () => {
        void (async () => {
          try {
            const payload = JSON.parse(String(reader.result || ""));
            await importCinemaJsonPayload(payload);
          } catch (err) {
            toast(String(err.message || err));
          }
        })();
      };
      reader.readAsText(f, "utf-8");
      return;
    }
    const fd = new FormData();
    fd.append("file", f);
    void fetch("/api/cinema/import", { method: "POST", body: fd })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errDetail(data));
        const base = emptyCinema();
        state.cinema = {
          ...base,
          ...data,
          setup: { ...base.setup, ...(data.setup || {}) },
          audio: { ...base.audio, ...(data.audio || {}) },
        };
        renderCinema();
        await fillCinemaFilms();
        toast(tt("cinema.filmImported"));
      })
      .catch((err) => toast(String(err.message || err)));
  });
  $("cinema-speed-chips")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-speed]");
    if (!btn) return;
    applyCinemaSpeed(btn.dataset.speed);
  });
  $("cinema-seed")?.addEventListener("change", () => {
    ensureCinema().seed = Number($("cinema-seed").value);
    void saveCinema(true);
  });
  $("cinema-seed-lock")?.addEventListener("change", () => {
    ensureCinema().seed_lock = !!$("cinema-seed-lock").checked;
    void saveCinema(true);
  });
  $("cinema-pills")?.addEventListener("click", (e) => {
    const option = e.target.closest(".film-pill-option");
    const pill = e.target.closest(".film-pill");
    if (option && pill) {
      e.stopPropagation();
      const key = pill.dataset.setup;
      const id = option.dataset.id || "auto";
      if (key === "look") {
        applyCinemaLookPreset(id);
        pill.classList.remove("open");
        renderCinemaPills();
        renderCinemaAudio();
        toast(tt("cinema.presetApplied"));
        void saveCinema(true);
        return;
      }
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
      scheduleCinemaPreview();
      renderCinemaTimeline();
    }
  });
  $("cinema-shots")?.addEventListener("click", (e) => {
    const del = e.target.closest(".cinema-shot-del");
    if (del) {
      e.preventDefault();
      e.stopPropagation();
      const card = del.closest(".cinema-shot");
      if (!card?.dataset.id) return;
      deleteCinemaShot(card.dataset.id);
      return;
    }
    const edit = e.target.closest(".cinema-shot-edit");
    if (edit) {
      e.preventDefault();
      e.stopPropagation();
      const card = edit.closest(".cinema-shot");
      if (!card?.dataset.id) return;
      openCinemaSceneModal(card.dataset.id);
      return;
    }
    const duplicate = e.target.closest(".cinema-shot-duplicate");
    if (duplicate) {
      e.preventDefault();
      e.stopPropagation();
      const card = duplicate.closest(".cinema-shot");
      if (card?.dataset.id) duplicateCinemaShot(card.dataset.id);
      return;
    }
    const toggle = e.target.closest(".cinema-shot-toggle");
    if (toggle) {
      e.preventDefault();
      e.stopPropagation();
      const card = toggle.closest(".cinema-shot");
      const shot = card ? cinemaShotById(card.dataset.id) : null;
      if (!shot) return;
      shot.enabled = shot.enabled === false;
      renderCinemaShots();
      renderCinema();
      void saveCinema(true);
      return;
    }
    const card = e.target.closest(".cinema-shot");
    if (!card) return;
    const shot = cinemaShotById(card.dataset.id);
    if (!shot) return;
    const modeBtn = e.target.closest("[data-mode]");
    if (modeBtn) {
      shot.mode = modeBtn.dataset.mode === "continue" ? "continue" : "t2v";
      renderCinemaShots();
      void saveCinema(true);
    }
  });
  $("btn-cinema-scene-close")?.addEventListener("click", closeCinemaSceneModal);
  $("btn-cinema-scene-cancel")?.addEventListener("click", closeCinemaSceneModal);
  $("btn-cinema-scene-save")?.addEventListener("click", () => saveCinemaSceneModal());
  $("cinema-scene-modal")?.addEventListener("click", (e) => {
    if (e.target === $("cinema-scene-modal")) closeCinemaSceneModal();
  });
  $("cinema-scene-modal")?.addEventListener("input", (e) => {
    if (e.target.closest("[data-scene-field]")) refreshCinemaScenePreview();
  });
  $("cinema-scene-modal")?.addEventListener("change", (e) => {
    if (e.target.closest("[data-scene-field]")) refreshCinemaScenePreview();
  });
  const cinemaDelegate = (rootId, kind) => {
    $(rootId)?.addEventListener("change", (e) => {
      const card = e.target.closest(".cinema-card");
      if (!card) return;
      const id = card.dataset.id;
      if (e.target.classList.contains("cinema-img")) {
        void uploadCinemaImage(kind, id, e.target.files);
        e.target.value = "";
        return;
      }
      const field = e.target.dataset.field;
      if (!field) return;
      void patchCinemaAsset(kind, id, { [field]: e.target.value }).then(() => {
        if (field === "name") renderCinema();
      });
    });
    $(rootId)?.addEventListener("click", (e) => {
      if (e.target.closest(".cinema-img-dl")) {
        e.stopPropagation();
        return;
      }
      const zoom = e.target.closest(".cinema-img-zoom");
      if (zoom) {
        e.preventDefault();
        e.stopPropagation();
        openCinemaStill(zoom.dataset.url || "", zoom.dataset.name || "");
        return;
      }
      const stillImg = e.target.closest(".cinema-asset img");
      if (stillImg) {
        e.preventDefault();
        e.stopPropagation();
        openCinemaStill(stillImg.dataset.full || stillImg.getAttribute("src") || "", stillImg.dataset.name || "");
        return;
      }
      const callEl = e.target.closest(".cinema-call");
      if (callEl) {
        e.preventDefault();
        e.stopPropagation();
        const call = callEl.dataset.call || callEl.textContent || "";
        if (call) void copyText(call, tf("cinema.copiedCall", { call }));
        return;
      }
      const imgDel = e.target.closest(".cinema-img-del");
      if (imgDel) {
        e.preventDefault();
        e.stopPropagation();
        const card = imgDel.closest(".cinema-card");
        if (!card) return;
        void removeCinemaImage(kind, card.dataset.id || "", imgDel.dataset.file || "").catch((error) => {
          toast(String(error.message || error));
        });
        return;
      }
      const del = e.target.closest(".cinema-del");
      if (del) {
        e.preventDefault();
        e.stopPropagation();
        const card = del.closest(".cinema-card");
        if (!card) return;
        void deleteCinemaAsset(kind, card.dataset.id || "");
        return;
      }
      if (kind !== "character" || e.target.closest("input, textarea, select, button, label")) return;
      const card = e.target.closest(".cinema-card");
      if (!card) return;
      const item = cinemaItem(kind, card.dataset.id || "");
      if (!item) return;
      e.preventDefault();
      e.stopPropagation();
      state.selectedCharacter = item;
      renderCinemaCharacterModal();
    });
  };
  cinemaDelegate("cinema-chars", "character");
  cinemaDelegate("cinema-locs", "location");
  $("btn-cinema-character-close")?.addEventListener("click", closeCinemaCharacterModal);
  $("btn-cinema-character-cancel")?.addEventListener("click", closeCinemaCharacterModal);
  $("btn-cinema-character-save")?.addEventListener("click", () => void saveCinemaCharacterModal());
  $("cinema-character-modal")?.addEventListener("click", (e) => {
    if (e.target === $("cinema-character-modal")) closeCinemaCharacterModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("cinema-scene-modal")?.classList.contains("hidden")) {
      closeCinemaSceneModal();
      e.preventDefault();
    }
  });
  $("first-frame-file")?.addEventListener("change", (e) => {
    syncFilePickName(e.target);
    const f = e.target.files && e.target.files[0];
    void uploadSingleFrame(f, "first");
    e.target.value = "";
  });
  document.querySelectorAll(".ios-segment [data-frame-source]").forEach((btn) => {
    btn.addEventListener("click", () => setFrameSource(btn.dataset.frame, btn.dataset.frameSource));
  });
  $("btn-first-frame-generate")?.addEventListener("click", () => void generateSingleFrame("first"));
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
      toast(tt("toast.noPrompt"));
      return;
    }
    const ta = $("prompt");
    if (ta) ta.value = t;
    closePromptView();
    tToast("toast.promptToScene");
  });
  $("btn-use-in-continue")?.addEventListener("click", async () => {
    const id = state.selectedJobId || $("continue-source")?.value || "";
    if (!id) {
      tToast("toast.pickFromGallery");
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
    tToast("toast.listCleared");
  });

  $("btn-batch")?.addEventListener("click", async () => {
    const lines = state.queueItems.map((x) => x.text.trim()).filter(Boolean);
    if (!lines.length) {
      tToast("toast.batchAddFirst");
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
        link_continue: !!$("link-continue")?.checked,
        append_to_chain: !!$("link-continue")?.checked,
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
          ? tf("toast.batchFaceLock", { n: String(data.count) })
          : tip
            ? tf("toast.batchContinueChain", { n: String(data.count) })
            : data.count > 1
              ? tf("toast.batchMixed", { n: String(data.count) })
              : tf("toast.batchQueued", { n: String(data.count) })
      );
      setDirectorOpen(false);
      state.playerCleared = false;
      await refreshJobs();
    } catch (e) {
      toast(String(e.message || e));
    }
  });

  $("btn-stop").onclick = async () => {
    try {
      // Only stop the running clip — keep the rest of the batch queued
      await fetch("/api/interrupt", { method: "POST" });
      tToast("toast.stopped");
      // If nothing was running, clear sticky bar immediately
      const hadRunning = state.jobs.some((j) => j.status === "running");
      if (!hadRunning && !state.jobs.some((j) => j.status === "queued")) {
        hideProgressNow();
        toast(tt("prod.ready"));
      }
      await refreshJobs();
    } catch (e) {
      toast(String(e.message || e));
    }
  };

  $("btn-cancel-queue")?.addEventListener("click", async () => {
    if (!tConfirm("confirm.cancelQueue")) return;
    try {
      const r = await fetch("/api/interrupt?cancel_queued=true", { method: "POST" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      tToast("toast.queueCancelled", { n: String((data.cancelled || []).length) });
      await refreshJobs();
    } catch (e) {
      toast(String(e.message || e));
    }
  });

  async function deleteJob(jobId) {
    try {
      const r = await fetch(`/api/jobs/${jobId}?delete_files=true`, { method: "DELETE" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      if (state.selectedJobId === jobId) {
        clearPlayer();
      }
      if (state.continueFrom === jobId) clearContinueMode();
      tToast("toast.recordDeleted");
      await refreshJobs();
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  async function clearJobs(scope) {
    const lane = state.prodLane === "director" ? "director" : "scene";
    const laneLabel = lane === "director" ? tt("prod.laneDirector") : tt("prod.laneScene");
    const labels = {
      errors: tt("clearScope.errors"),
      finished: tt("clearScope.finished"),
      done: tt("clearScope.done"),
    };
    if (!tConfirm("confirm.clearScope", { lane: laneLabel, scope: labels[scope] || scope })) return;
    try {
      const r = await fetch("/api/jobs/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope, delete_files: true, lane }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      tToast(data.removed ? "toast.recordsCleared" : "toast.nothingToClear", data.removed ? { n: String(data.removed) } : {});
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
  document.querySelectorAll("#prod-lane-tabs .chip").forEach((btn) => {
    btn.addEventListener("click", () => setProdLane(btn.dataset.lane));
  });


  $("btn-reset-production")?.addEventListener("click", async () => {
    if (
      !confirm(
        tt("confirm.resetProd")
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
      tToast("toast.resetDone");
      await refreshJobs();
    } catch (e) {
      toast(String(e.message || e));
    }
  });

  $("btn-open-logs")?.addEventListener("click", async () => {
    try {
      const r = await fetch("/api/logs?which=errors&lines=180");
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      $("error-logs-meta").textContent = tf("logs.header", { file: data.file, lines: String(data.lines) });
      $("error-logs-text").textContent = data.text || tt("logs.empty");
      $("view-error-logs")?.classList.remove("hidden");
      $("view-error-logs")?.setAttribute("aria-hidden", "false");
      $("btn-copy-error-logs")?.focus();
    } catch (e) {
      toast(String(e.message || e));
    }
  });
  const closeErrorLogs = () => {
    $("view-error-logs")?.classList.add("hidden");
    $("view-error-logs")?.setAttribute("aria-hidden", "true");
  };
  $("btn-error-logs-close")?.addEventListener("click", closeErrorLogs);
  $("view-error-logs")?.addEventListener("click", (e) => {
    if (e.target === $("view-error-logs")) closeErrorLogs();
  });
  $("btn-copy-error-logs")?.addEventListener("click", () =>
    void copyText($("error-logs-text")?.textContent, "Hata logları kopyalandı")
  );
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("view-error-logs")?.classList.contains("hidden")) {
      closeErrorLogs();
      e.preventDefault();
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
  const sceneProject = $("scene-project");
  if (sceneProject) {
    sceneProject.addEventListener("click", (e) => {
      const btn = e.target.closest("#scene-purpose-chips .chip, #scene-style-chips .chip");
      if (btn) selectProjectChip(btn, { fromScene: true });
    });
  }
  syncProjectChips();
  $("llm-provider")?.addEventListener("change", () => {
    void onLlmProviderChanged($("llm-provider").value);
  });
  $("llm-provider-settings")?.addEventListener("change", () => {
    void onLlmProviderChanged($("llm-provider-settings").value);
  });
  $("director-model")?.addEventListener("change", () => {
    syncModelSelects($("director-model").value);
  });
  $("director-model-settings")?.addEventListener("change", () => {
    syncModelSelects($("director-model-settings").value);
  });
  $("llm-ollama-url")?.addEventListener("input", () => {
    if ($("llm-ollama-url")) $("llm-ollama-url").dataset.dirty = "1";
  });
  $("llm-lmstudio-url")?.addEventListener("input", () => {
    if ($("llm-lmstudio-url")) $("llm-lmstudio-url").dataset.dirty = "1";
  });
  $("llm-llamacpp-url")?.addEventListener("input", () => {
    if ($("llm-llamacpp-url")) $("llm-llamacpp-url").dataset.dirty = "1";
  });
  const KEY_TO_PROVIDER = {
    "llm-openai-key": "openai",
    "llm-nvidia-key": "nvidia",
    "llm-gemini-key": "gemini",
    "llm-grok-key": "grok",
    "llm-claude-key": "claude",
  };
  function _providerForKeyInput(id, value) {
    const raw = (value || "").trim();
    if (id === "llm-openai-key" && /^nvapi-/i.test(raw)) return "nvidia";
    return KEY_TO_PROVIDER[id];
  }
  for (const f of LLM_KEY_FIELDS) {
    $(f.id)?.addEventListener("input", () => {
      const el = $(f.id);
      if (el) el.dataset.dirty = "1";
      const prov = _providerForKeyInput(f.id, el && el.value);
      if (prov && el && el.value.trim()) {
        syncProviderSelects(prov);
        void onLlmProviderChanged(prov);
      }
    });
  }
  $("btn-llm-save")?.addEventListener("click", () => saveLlmSettings());
  $("btn-llm-provider-save")?.addEventListener("click", () => saveLlmProviderOnly());
  $("btn-director-llm-tab")?.addEventListener("click", () => {
    setDirectorModal(!$("director-dock")?.classList.contains("modal-open"));
  });

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
        ? tf("notify.tokenSaved", { mask: s.telegram_bot_token_masked })
        : tt("notify.tokenPlaceholder");
    }
    if ($("notify-tg-token-hint")) {
      $("notify-tg-token-hint").textContent = s.telegram_configured
        ? tf("notify.tgReady", { chat: s.telegram_chat_id || "?", user: s.telegram_bot_username ? tf("notify.tgUser", { user: s.telegram_bot_username }) : "" })
        : tt("notify.tokenKeep");
    }
    if ($("notify-server")) $("notify-server").value = s.ntfy_server || "https://ntfy.sh";
    if ($("notify-topic")) $("notify-topic").value = s.ntfy_topic || "";
    if ($("notify-batch-done")) $("notify-batch-done").checked = s.on_batch_done !== false;
    if ($("notify-each-clip")) $("notify-each-clip").checked = !!s.on_each_clip;
    if ($("notify-error")) $("notify-error").checked = s.on_error !== false;
    const hint = $("notify-subscribe-hint");
    if (hint) {
      hint.textContent = s.subscribe_url
        ? tf("notify.subscribeReady", { url: s.subscribe_url })
        : tt("notify.subscribe");
    }
    const sh = $("notify-settings-hint");
    if (sh) {
      if (!s.enabled) sh.textContent = tt("notify.off");
      else if ((s.provider || "telegram") === "telegram") {
        sh.textContent = s.telegram_configured
          ? tt("notify.tgOn")
          : tt("notify.tgMissing");
      } else {
        sh.textContent = s.subscribe_url ? `ntfy · ${s.subscribe_url}` : tt("notify.ntfyTopic");
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
        if (sh) sh.textContent = tt("notify.saved");
      } else {
        tToast("notify.saved");
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
      tToast("toast.akiImported");
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
      tToast("toast.testSent");
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
  $("btn-music-remove")?.addEventListener("click", () => {
    void deleteUploadedMusic(state.musicId, "director");
  });
  $("btn-music-mux")?.addEventListener("click", () => muxMusicFinal());
  $("btn-gallery")?.addEventListener("click", () => {
    setDirectorLlmOpen(false);
    $("view-settings")?.classList.add("hidden");
    $("view-support")?.classList.add("hidden");
    $("view-gallery")?.classList.remove("hidden");
    void renderGallery();
  });
  $("btn-gallery-close")?.addEventListener("click", () => {
    exitGalleryMergeMode();
    $("view-gallery")?.classList.add("hidden");
  });
  $("btn-settings")?.addEventListener("click", () => {
    setDirectorLlmOpen(false);
    $("view-gallery")?.classList.add("hidden");
    $("view-support")?.classList.add("hidden");
    $("view-settings")?.classList.remove("hidden");
    syncChromeFitFromStorage();
    void refreshDirectorStatus();
    void refreshNotifySettings();
    void loadLoras();
    void loadH3Models();
  });
  $("settings-chrome-fit")?.addEventListener("change", (e) => {
    applyChromeFit(!!e.target.checked);
  });
  $("btn-h3-models-save")?.addEventListener("click", () => void saveH3Models(false));
  $("btn-h3-models-reset")?.addEventListener("click", () => void saveH3Models(true));
  $("btn-settings-close")?.addEventListener("click", () => {
    void saveNotifySettings({ quiet: true });
    $("view-settings")?.classList.add("hidden");
  });
  const SUPPORT_REPO = "https://github.com/erdinoral/minimax-h3-studio";
  $("btn-support")?.addEventListener("click", () => {
    setDirectorLlmOpen(false);
    $("view-gallery")?.classList.add("hidden");
    $("view-settings")?.classList.add("hidden");
    $("view-support")?.classList.remove("hidden");
  });
  $("btn-support-close")?.addEventListener("click", () => $("view-support")?.classList.add("hidden"));
  $("btn-support-bug")?.addEventListener("click", () => {
    window.open(SUPPORT_REPO + "/issues/new?template=bug.md", "_blank", "noopener");
  });
  $("btn-support-idea")?.addEventListener("click", () => {
    window.open(SUPPORT_REPO + "/issues/new?template=feature.md", "_blank", "noopener");
  });

  const OC_SLUG = "minimax-h3-studio";

  function setDonorRoll(names, donateUrl) {
    const bar = $("donor-ticker");
    const track = $("donor-ticker-track");
    const list = $("support-donors-list");
    const empty = $("support-donors-empty");
    const oc = $("btn-support-oc");
    const clean = (names || []).map((n) => String(n || "").trim()).filter(Boolean);
    if (donateUrl && oc) oc.href = donateUrl;
    if (!clean.length) {
      document.body.classList.remove("has-donors");
      bar?.classList.add("hidden");
      if (bar) bar.hidden = true;
      if (track) track.innerHTML = "";
      if (list) {
        list.textContent = "";
        list.classList.add("hidden");
        list.hidden = true;
      }
      empty?.classList.remove("hidden");
      return;
    }
    document.body.classList.add("has-donors");
    if (bar) {
      bar.classList.remove("hidden");
      bar.hidden = false;
    }
    const chips = clean.map((n) => `<span>${htmlEsc(n)}</span>`).join("");
    if (track) track.innerHTML = chips + chips;
    if (list) {
      list.textContent = clean.join(" · ");
      list.classList.remove("hidden");
      list.hidden = false;
    }
    empty?.classList.add("hidden");
  }

  async function loadDonorRoll() {
    let names = [];
    let donateUrl = `https://opencollective.com/${OC_SLUG}`;
    try {
      const data = await fetch("/api/donors").then((r) => (r.ok ? r.json() : null));
      if (data) {
        names = Array.isArray(data.names) ? data.names : [];
        if (data.donate_url) donateUrl = data.donate_url;
        if (data.github_sponsors && $("btn-support-sponsor")) {
          $("btn-support-sponsor").href = data.github_sponsors;
        }
      }
    } catch {
      /* old Studio process — try public Open Collective */
    }
    if (!names.length) {
      try {
        const rows = await fetch(`https://opencollective.com/${OC_SLUG}/members.json`).then((r) =>
          r.ok ? r.json() : []
        );
        names = (Array.isArray(rows) ? rows : [])
          .filter(
            (x) =>
              String(x?.role || "").toUpperCase() === "BACKER" &&
              Number(x?.totalAmountDonated || 0) > 0
          )
          .map((x) => String(x.name || "").trim())
          .filter(Boolean);
      } catch {
        names = [];
      }
    }
    setDonorRoll(names, donateUrl);
  }

  $("btn-donor-ticker")?.addEventListener("click", () => $("btn-support")?.click());
  $("btn-donor-join")?.addEventListener("click", () => $("btn-support")?.click());
  void loadDonorRoll();

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
      tToast("toast.directorBusyNewChat");
      return;
    }
    try {
      const r = await fetch("/api/director/session?lang=" + encodeURIComponent(uiLang()), { method: "POST" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errDetail(data));
      const sid = directorSessionIdFrom(data);
      if (!sid) throw new Error(tt("err.sessionCreate"));
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
      tToast("toast.newChatOpened");
    } catch (e) {
      toast(String(e.message || e));
    }
  }

  function switchDirectorTab(sid) {
    if (state.directorBusy) {
      tToast("toast.directorBusyTab");
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
      tToast("toast.directorBusyClose");
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
      tToast("toast.directorBusyReset");
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
      if (!sid) throw new Error(tt("err.sessionCreate"));
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
      tToast("toast.chatReset");
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
    ensureCinema();
    refreshStudioWorkspaceChrome();
    syncProjectChips();
    refreshModeHints();
    updateProjectAudioHint();
    fillLoraSelect();
    fillLoraShop();
    updateLoraHint();
    renderJobs();
    renderQueue();
    if (state.directorBrief?.shots?.length) {
      renderDirectorShotPanel(state.directorBrief, { open: !!$("director-shot-panel")?.open });
    }
    if (state.directorReady) {
      setDirectorReadyUi(true, state.directorBrief?.shots?.length || 0);
    }
    if (state.musicMeta) updateMusicMetaUi();
    void refreshPromptRewriterStatus();
    if ($("gallery-grid")) void renderGallery();
    if (typeof syncLlmSettingsUi === "function") {
      const prov = _selectedLlmProvider();
      syncLlmSettingsUi({ ...(state.llmPub || {}), provider: prov }, { provider: prov });
    }
    if (state.directorTab === "plan") renderDirectorPlanBoard();
    document.querySelectorAll("#director-log .dir-msg").forEach((el) => {
      const who = el.querySelector(".who");
      if (!who) return;
      who.textContent = el.classList.contains("user") ? tt("dir.you") : tt("dir.who");
    });
    if (typeof renderCinema === "function") renderCinema();
    const ph = [
      ["bible-logline", "dir.bibleLogPh"],
      ["bible-characters", "dir.bibleCharPh"],
      ["bible-locations", "dir.bibleLocPh"],
      ["bible-tone", "dir.tonePh"],
      ["bible-forbidden", "dir.forbidPh"],
      ["music-concept", "dir.musicPh"],
      ["music-lyrics", "dir.lyricsPh"],
    ];
    ph.forEach(([id, key]) => {
      const el = $(id);
      if (el) el.placeholder = tt(key);
    });
  });

  try {
    ["h3_layout_v1", "h3_layout_v2", "h3_layout_v3", "h3_layout_v4", "h3_layout_v5", "h3_layout_v6", "h3_layout_v7", "h3_layout_v8"].forEach((k) => {
      localStorage.removeItem(k);
    });
  } catch {
    /* ignore */
  }

  setQuality(state.quality);
  setPostPass(state.postPass);
  setProduceMode("t2v");
  syncChromeFitFromStorage();
  setStudioWorkspace("scene");
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
  // LoRAs are independent from optional Studio settings. Do not make their
  // picker wait for that request: a missing/older settings endpoint used to
  // leave the otherwise healthy local LoRA list permanently blank.
  void loadStudioSettings();
  void loadLoras();
  setTimeout(() => void loadLoras(), 1200);
  syncDirectorDockHeight();
  window.addEventListener("resize", syncDirectorDockHeight);
  setInterval(syncDirectorDockHeight, 2000);
  setInterval(refreshHealth, 5000);
  setInterval(pollSystem, 2000);
  setInterval(refreshJobs, 1000);
  setInterval(refreshDirectorStatus, 10000);
})();
