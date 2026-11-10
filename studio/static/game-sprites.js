(() => {
  const $ = (id) => document.getElementById(id);
  const t = (key, args = {}) => Object.entries(args).reduce((s, [k, v]) => s.split(`{${k}}`).join(v), window.t ? window.t(key) : key);
  /** The shared status line is overwritten by every job refresh, so the Game panel keeps its own copy. */
  const toast = (msg) => {
    const notice = document.getElementById("gs-notice");
    if (notice) notice.textContent = msg;
    if (window.h3Toast) window.h3Toast(msg); else console.info(msg);
  };
  const SETTINGS_KEY = "h3.gameSettings";
  const SELECTED_KEY = "h3.gameSelected";

  // Game sprite helpers.
  const GAME_ANIMATIONS = [
    { id: "idle", loop: true }, { id: "walk", loop: true }, { id: "run", loop: true },
    { id: "jump", loop: false }, { id: "attack", loop: false }, { id: "hurt", loop: false },
    { id: "death", loop: false }, { id: "crouch", loop: true }, { id: "cast", loop: false },
    { id: "victory", loop: false },
  ];
  const GAME_CELLS = [32, 64, 128];
  const GAME_ORDER = GAME_ANIMATIONS.map((a) => a.id);

  /** Game jobs grouped by set, newest set first, animations in preset order. */
  function gameSets(jobs) {
    const sets = new Map();
    for (const job of jobs || []) {
      const game = job && job.game;
      if (!game || !game.set_id) continue;
      if (!sets.has(game.set_id)) sets.set(game.set_id, { id: game.set_id, created: 0, jobs: [] });
      const set = sets.get(game.set_id);
      set.jobs.push(job);
      set.created = Math.max(set.created, Number(job.created_at) || 0);
    }
    const out = [...sets.values()];
    for (const set of out) set.jobs.sort((a, b) => GAME_ORDER.indexOf(a.game.animation) - GAME_ORDER.indexOf(b.game.animation));
    return out.sort((a, b) => b.created - a.created);
  }

  /** One state per job: H3 status first, then the sprite result. A failed mask is never "ok". */
  function gameJobState(job) {
    const status = job && job.status;
    if (status === "queued" || status === "running") return status;
    if (status === "error" || status === "cancelled") return "error";
    if (status !== "done") return "queued";
    const result = job.game && job.game.result;
    if (!result) return "ready";
    if (!result.ok) return "failed";
    return result.status === "warn" ? "warn" : "ok";
  }

  /** Request body for sprite settings; blank frames/fps/loop fields fall back to the animation preset. */
  function spriteSettingsPayload(s) {
    const out = {
      cell: GAME_CELLS.includes(Number(s.cell)) ? Number(s.cell) : 64,
      palette: Number(s.palette) || 0,
      tolerance: Number(s.tolerance),
      hole_tolerance: Number(s.hole),
      edge_clean: Number(s.edge),
      detail: s.detail || "balanced",
    };
    for (const [key, src] of [["frames", "frames"], ["fps", "fps"], ["loop_start", "loopStart"], ["loop_end", "loopEnd"]]) {
      const raw = s[src];
      if (raw === "" || raw == null) continue;
      const n = Number(raw);
      if (Number.isFinite(n)) out[key] = n;
    }
    return out;
  }

  /** Largest whole-number zoom that keeps the drawing inside the box (never below 1). */
  function fitZoom(w, h, boxW, boxH) {
    if (!w || !h) return 1;
    return Math.max(1, Math.floor(Math.min(boxW / w, boxH / h)));
  }

  /** Frames shown around the loop boundary: the last two, then the first two. */
  function seamFrames(n) {
    if (n < 2) return [];
    const picks = n >= 4 ? [n - 2, n - 1, 0, 1] : [n - 1, 0];
    return picks.filter((v, i, all) => all.indexOf(v) === i);
  }
  // End game sprite helpers.

  const ui = {
    ref: null,
    backdrop: "green",
    backdropManual: false,
    suggestion: null,
    anims: new Set(["idle", "walk", "run", "jump"]),
    preset: "balanced",
    description: "",
    sprite: { cell: 64, frames: "", fps: "", palette: 0, tolerance: 30, hole: 18, edge: 1, detail: "balanced", loopStart: "", loopEnd: "" },
  };
  const live = {
    jobs: [],
    prev: {},
    setId: null,
    selected: null,
    busy: new Set(),
    autoTried: new Set(),
    view: "anim",
    bg: "checker",
    zoom: 0,
    pivot: true,
    playing: true,
    frames: [],
    frameIndex: 0,
    loadedKey: "",
    loadingKey: "",
    generateError: "",
    sheet: null,
    maskUrl: "",
    timer: 0,
    presets: null,
    accel: null,
  };
  const RENDER_PRESETS = ["fast", "balanced", "quality"];

  const present = () => document.body.classList.contains("ws-game");
  const workspaceShown = () => present() && (window.h3MotionView?.() || "workspace") === "workspace";

  function loadSettings() {
    try {
      const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "null");
      if (!saved) return;
      if (saved.ref && saved.ref.name) ui.ref = saved.ref;
      if (["green", "blue"].includes(saved.backdrop)) ui.backdrop = saved.backdrop;
      ui.backdropManual = !!saved.backdropManual;
      if (Array.isArray(saved.anims)) ui.anims = new Set(saved.anims.filter((a) => GAME_ORDER.includes(a)));
      if (RENDER_PRESETS.includes(saved.preset)) ui.preset = saved.preset;
      ui.description = String(saved.description || "").slice(0, 400);
      Object.assign(ui.sprite, saved.sprite || {});
      const sel = JSON.parse(localStorage.getItem(SELECTED_KEY) || "null");
      if (sel) { live.setId = sel.setId || null; live.selected = sel.job || null; }
    } catch {
      /* ignore */
    }
  }

  function saveSettings() {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...ui, anims: [...ui.anims] }));
      localStorage.setItem(SELECTED_KEY, JSON.stringify({ setId: live.setId, job: live.selected }));
    } catch {
      /* ignore */
    }
  }

  async function errorText(response) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 404 && !data.detail?.code) return t("game.backendOld");
    return window.h3ErrDetail ? window.h3ErrDetail(data) : String(data.detail || response.statusText);
  }

  async function postJson(url, body) {
    const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    if (!response.ok) throw new Error(await errorText(response));
    return response.json();
  }

  // Left panel.
  function animLabel(id) {
    return t(`game.anim.${id}`);
  }

  function presetFor(id) {
    return live.presets?.animations?.find((a) => a.id === id) || null;
  }

  function renderAnims() {
    const host = $("gs-anims");
    if (!host) return;
    host.innerHTML = "";
    for (const anim of GAME_ANIMATIONS) {
      const label = document.createElement("label");
      label.className = "gs-anim";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = anim.id;
      box.checked = ui.anims.has(anim.id);
      box.addEventListener("change", () => {
        if (box.checked) ui.anims.add(anim.id); else ui.anims.delete(anim.id);
        saveSettings();
        syncGenerate();
      });
      const name = document.createElement("span");
      name.textContent = animLabel(anim.id);
      const tag = document.createElement("small");
      tag.textContent = t(anim.loop ? "game.loop" : "game.once");
      tag.className = anim.loop ? "gs-tag-loop" : "gs-tag-once";
      label.append(box, name, tag);
      host.append(label);
    }
  }

  function renderRef() {
    const has = !!ui.ref;
    $("gs-ref")?.classList.toggle("hidden", !has);
    $("gs-drop")?.classList.toggle("hidden", has);
    const img = $("gs-ref-img");
    if (img) {
      if (has && img.dataset.src !== ui.ref.url) { img.src = ui.ref.url; img.dataset.src = ui.ref.url; }
      if (!has) { img.removeAttribute("src"); img.dataset.src = ""; }
    }
  }

  function renderBackdrop() {
    document.querySelectorAll("#gs-backdrop [data-gs-backdrop]").forEach((chip) => {
      const on = chip.dataset.gsBackdrop === ui.backdrop;
      chip.classList.toggle("on", on);
      chip.setAttribute("aria-pressed", on ? "true" : "false");
    });
    const hint = $("gs-backdrop-hint");
    if (!hint) return;
    const s = ui.suggestion;
    if (!s) { hint.textContent = t("game.backdropHint"); return; }
    const color = t(`backdrop.${s.suggested}`);
    hint.textContent = s.conflict ? t("game.backdropConflict", { color })
      : ui.backdrop === s.suggested ? t("game.backdropSuggested", { color })
      : t("game.backdropOverride", { color });
    hint.classList.toggle("warn", !!s.conflict || ui.backdrop !== s.suggested);
  }

  function chipGroup(id, attr, value) {
    document.querySelectorAll(`#${id} [${attr}]`).forEach((chip) => {
      const on = chip.getAttribute(attr) === String(value);
      chip.classList.toggle("on", on);
      chip.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  /** Accelerators the preset needs that are off in the shared Studio settings (never a speed LoRA). */
  function missingAccel() {
    const a = live.accel;
    if (!a) return [];
    return [!a.spectrum_enabled && a.spectrum_installed && "Spectrum", !a.sparse_enabled && "Sol-Attn"].filter(Boolean);
  }

  function renderPreset() {
    chipGroup("gs-preset", "data-gs-preset", ui.preset);
    const render = live.presets?.render || [];
    document.querySelectorAll("#gs-preset [data-gs-preset]").forEach((chip) => {
      const p = render.find((r) => r.id === chip.dataset.gsPreset);
      if (p) chip.title = t("game.presetInfo", { q: p.quality, steps: p.steps });
    });
    const hint = $("gs-preset-hint");
    if (!hint) return;
    const p = render.find((r) => r.id === ui.preset);
    const lines = p ? [t("game.presetInfo", { q: p.quality, steps: p.steps })] : [];
    const missing = missingAccel();
    if (live.accel) lines.push(missing.length ? t("game.accelPending", { list: missing.join(", ") }) : t("game.accelOn"));
    if (live.accel?.sage_available) lines.push(t(live.accel.sage_enabled ? "game.sageOn" : "game.sageOff"));
    if (live.accel && !live.accel.spectrum_installed) lines.push(t("game.accelNoSpectrum"));
    hint.textContent = lines.join(" ");
  }

  /** Same rule as the Scene speed presets: switch on only what is off, and keep the user's other choices. */
  async function ensureAccel() {
    try {
      const response = await fetch("/api/h3-acceleration");
      if (!response.ok) return;
      live.accel = await response.json();
      const changes = {};
      if (!live.accel.spectrum_enabled && live.accel.spectrum_installed) changes.spectrum_enabled = true;
      if (!live.accel.sparse_enabled) changes.sparse_enabled = true;
      if (!Object.keys(changes).length) return;
      const saved = await fetch("/api/h3-acceleration", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes),
      });
      if (!saved.ok) throw new Error(await errorText(saved));
      live.accel = await saved.json();
    } catch (e) {
      toast(t("game.accelFailed", { err: e.message || String(e) }));
    } finally {
      renderPreset();
    }
  }

  function renderSettings() {
    renderPreset();
    chipGroup("gs-cell", "data-gs-cell", ui.sprite.cell);
    chipGroup("gs-detail", "data-gs-detail", ui.sprite.detail);
    const set = (id, v) => { const el = $(id); if (el && el.value !== String(v)) el.value = String(v); };
    set("gs-desc", ui.description);
    set("gs-frames", ui.sprite.frames);
    set("gs-fps", ui.sprite.fps);
    set("gs-palette", ui.sprite.palette);
    set("gs-tolerance", ui.sprite.tolerance);
    set("gs-hole", ui.sprite.hole);
    set("gs-edge", ui.sprite.edge);
    set("gs-loop-start", ui.sprite.loopStart);
    set("gs-loop-end", ui.sprite.loopEnd);
    const out = (id, v) => { const el = $(id); if (el) el.textContent = String(v); };
    out("gs-tolerance-val", ui.sprite.tolerance);
    out("gs-hole-val", Number(ui.sprite.hole) ? ui.sprite.hole : t("game.off"));
    out("gs-edge-val", ui.sprite.edge);
    const job = selectedJob();
    const preset = presetFor(job?.game?.animation);
    if ($("gs-frames")) $("gs-frames").placeholder = preset ? t("game.autoValue", { n: preset.frames }) : t("game.auto");
    if ($("gs-fps")) $("gs-fps").placeholder = preset ? t("game.autoValue", { n: preset.fps }) : t("game.auto");
  }

  function syncGenerate() {
    const btn = $("gs-generate");
    if (!btn) return;
    btn.disabled = !ui.ref || !ui.anims.size || btn.dataset.busy === "1";
    const hint = $("gs-generate-hint");
    if (hint) {
      hint.textContent = live.generateError || (!ui.ref ? t("game.needRef") : !ui.anims.size ? t("game.needAnim")
        : t("game.generateHint", { n: ui.anims.size }));
      hint.classList.toggle("warn", !!live.generateError);
    }
  }

  const IMAGE_EXT = /\.(png|jpe?g|webp|gif|bmp)$/i;

  /**
   * A file from Explorer, or an image dragged from a Studio page or another tab, which arrives as a URL.
   * Must be called synchronously from the drop handler: drag data is unreadable after the first await.
   */
  async function droppedImage(dt) {
    const file = [...(dt?.files || [])].find((f) => f.type.startsWith("image/") || IMAGE_EXT.test(f.name));
    if (file) return file;
    const src = (dt?.getData("text/html") || "").match(/<img[^>]+src="([^"]+)"/i)?.[1]?.replace(/&amp;/g, "&");
    const url = src || (dt?.getData("text/uri-list") || "").split(/\r?\n/).find((line) => line && !line.startsWith("#"));
    if (!url) return null;
    const href = new URL(url, location.href);
    const response = await fetch(href);
    if (!response.ok) throw new Error(response.statusText);
    const blob = await response.blob();
    if (!blob.type.startsWith("image/")) return null;
    const name = href.pathname.split("/").pop() || "character";
    return new File([blob], IMAGE_EXT.test(name) ? name : `${name}.${blob.type.split("/")[1] || "png"}`, { type: blob.type });
  }

  async function dropRef(dt) {
    let file = null;
    try {
      file = await droppedImage(dt);
    } catch {
      toast(t("game.dropFetchFailed"));
      return;
    }
    if (file) uploadRef(file); else toast(t("game.dropNotImage"));
  }

  async function uploadRef(file) {
    if (!file) return;
    const drop = $("gs-drop");
    drop?.classList.add("is-uploading");
    $("gs-ref")?.classList.add("is-uploading");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const response = await fetch("/api/refs/upload", { method: "POST", body: fd });
      if (!response.ok) throw new Error(await errorText(response));
      const data = await response.json();
      ui.ref = { name: data.name, filename: data.filename, url: data.url };
      ui.suggestion = null;
      saveSettings();
      renderRef();
      syncGenerate();
      await suggestBackdrop();
    } catch (e) {
      toast(t("game.uploadFailed", { err: e.message || e }));
    } finally {
      drop?.classList.remove("is-uploading");
      $("gs-ref")?.classList.remove("is-uploading");
      const input = $("gs-file");
      if (input) input.value = "";
    }
  }

  async function suggestBackdrop() {
    if (!ui.ref) return;
    try {
      ui.suggestion = await postJson("/api/game/backdrop", { ref: ui.ref.name });
      if (!ui.backdropManual) ui.backdrop = ui.suggestion.suggested;
      saveSettings();
    } catch {
      ui.suggestion = null;
    }
    renderBackdrop();
  }

  async function generate() {
    const btn = $("gs-generate");
    if (!ui.ref || !ui.anims.size || btn?.dataset.busy === "1") return;
    if (btn) { btn.dataset.busy = "1"; btn.disabled = true; }
    live.generateError = "";
    try {
      await ensureAccel();
      const anims = GAME_ORDER.filter((a) => ui.anims.has(a));
      const data = await postJson("/api/game/animations", {
        ref: ui.ref.name,
        animations: anims,
        backdrop: ui.backdrop,
        description: ui.description,
        preset: ui.preset,
        sprite: spriteSettingsPayload(ui.sprite),
      });
      live.setId = data.set_id;
      live.selected = data.jobs[0]?.id || null;
      for (const job of data.jobs) live.prev[job.id] = "queued";
      saveSettings();
      toast(t("game.queued", { n: data.jobs.length }));
      if (data.failed?.length) toast(t("game.someFailed", { n: data.failed.length }));
      await window.h3RefreshJobs?.();
    } catch (e) {
      live.generateError = t("game.queueFailed", { err: e.message || String(e) });
      toast(live.generateError);
    } finally {
      if (btn) btn.dataset.busy = "0";
      syncGenerate();
    }
  }

  // Jobs and results.
  function selectedJob() {
    return live.jobs.find((j) => j.id === live.selected) || null;
  }

  function currentSet() {
    const sets = gameSets(live.jobs);
    return sets.find((s) => s.id === live.setId) || sets[0] || null;
  }

  function stateLabel(job) {
    const st = gameJobState(job);
    if (live.busy.has(job.id)) return t("game.stateProcessing");
    if (st === "running") return t("game.stateRunning", { pct: Math.round(Number(job.progress) || 0) });
    return t(`game.state.${st}`);
  }

  function renderSets() {
    const select = $("gs-set");
    if (!select) return;
    const sets = gameSets(live.jobs);
    const set = currentSet();
    select.innerHTML = "";
    for (const s of sets) {
      const opt = document.createElement("option");
      opt.value = s.id;
      const when = s.created ? new Date(s.created * 1000).toLocaleString({ tr: "tr-TR", fr: "fr-FR", es: "es-ES", de: "de-DE" }[window.h3Lang?.()] || "en-GB", { dateStyle: "short", timeStyle: "short" }) : s.id;
      opt.textContent = `${when} · ${s.jobs.map((j) => animLabel(j.game.animation)).join(", ")}`;
      select.append(opt);
    }
    select.value = set?.id || "";
    select.disabled = sets.length < 2;
    $("gs-results-empty")?.classList.toggle("hidden", !!sets.length);
  }

  function renderJobsList() {
    const ul = $("gs-jobs");
    if (!ul) return;
    const set = currentSet();
    ul.innerHTML = "";
    for (const job of set ? set.jobs : []) {
      const st = gameJobState(job);
      const li = document.createElement("li");
      li.className = "gs-job";
      li.dataset.state = live.busy.has(job.id) ? "processing" : st;
      li.classList.toggle("on", job.id === live.selected);
      const main = document.createElement("button");
      main.type = "button";
      main.className = "gs-job-main";
      main.dataset.act = "select";
      main.dataset.id = job.id;
      const anim = GAME_ANIMATIONS.find((a) => a.id === job.game.animation);
      const result = job.game.result;
      const meta = result?.ok ? t("game.jobMeta", { n: result.frames, cell: result.cell, fps: result.fps }) : t(anim?.loop ? "game.loop" : "game.once");
      main.innerHTML = `<b></b><small></small><span class="gs-job-state"></span>`;
      main.querySelector("b").textContent = animLabel(job.game.animation);
      main.querySelector("small").textContent = meta;
      main.querySelector(".gs-job-state").textContent = stateLabel(job);
      li.append(main);
      const actions = document.createElement("div");
      actions.className = "gs-job-actions";
      const add = (act, key) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn-ghost";
        b.dataset.act = act;
        b.dataset.id = job.id;
        b.textContent = t(key);
        actions.append(b);
      };
      if (st === "error") add("retry", "game.retry");
      if (st === "ready" || st === "failed") add("process", "game.process");
      if (job.status === "done") add("source", "game.source");
      if (actions.children.length) li.append(actions);
      ul.append(li);
    }
  }

  function issueText(issue) {
    return t(`game.q.${issue.code}`, { value: issue.value ?? "" });
  }

  function renderResult() {
    const job = selectedJob();
    const result = job?.game?.result || null;
    const status = $("gs-status");
    const zip = $("gs-zip");
    const ready = job && job.status === "done";
    const busy = job && live.busy.has(job.id);
    $("gs-process") && ($("gs-process").disabled = !ready || busy);
    $("gs-preview") && ($("gs-preview").disabled = !ready || busy);
    const set = currentSet();
    const okCount = set ? set.jobs.filter((j) => j.game.result?.ok).length : 0;
    $("gs-atlas") && ($("gs-atlas").disabled = okCount < 1);
    if (zip) {
      const href = result?.ok ? result.base_url + result.files.zip : "";
      zip.classList.toggle("disabled", !href);
      zip.setAttribute("aria-disabled", href ? "false" : "true");
      if (href) zip.href = href; else zip.removeAttribute("href");
    }
    if (status) {
      const lines = [];
      if (!job) lines.push(t("game.pickJob"));
      else if (busy) lines.push(t("game.stateProcessing"));
      else if (!result) lines.push(stateLabel(job));
      else {
        lines.push(result.ok ? t(result.status === "warn" ? "game.resultWarn" : "game.resultOk") : t("game.resultFailed"));
        for (const issue of result.issues || []) lines.push("• " + issueText(issue));
        if (result.ok && result.loop && result.seam) lines.push(t("game.seam", { grade: t(`game.seam.${result.seam.grade}`), ratio: Number.isFinite(result.seam.ratio) ? result.seam.ratio.toFixed(1) : "–" }));
        if (result.ok) lines.push(t("game.naturalFps", { fps: result.natural_fps }));
      }
      status.textContent = lines.join("\n");
      status.dataset.state = !result ? "" : result.ok ? result.status : "failed";
    }
    renderInfo();
  }

  async function processJob(id, { auto = false } = {}) {
    const job = live.jobs.find((j) => j.id === id);
    if (!job || live.busy.has(id)) return;
    live.busy.add(id);
    renderJobsList();
    renderResult();
    try {
      const payload = spriteSettingsPayload(ui.sprite);
      const result = await postJson(`/api/game/jobs/${id}/process`, { sprite: auto ? {} : payload });
      // The job list may have been refreshed while processing; update the current copy too.
      for (const copy of new Set([job, live.jobs.find((j) => j.id === id)])) if (copy) copy.game.result = result;
      if (id === live.selected) {
        live.loadedKey = "";
        if (!result.ok) { live.maskUrl = result.base_url + result.files.mask_preview; setView("mask"); }
      }
      if (!auto || !result.ok) toast(result.ok ? t("game.processed", { name: animLabel(job.game.animation) }) : t("game.processFailedToast", { name: animLabel(job.game.animation) }));
    } catch (e) {
      toast(e.message || String(e));
    } finally {
      live.busy.delete(id);
      renderJobsList();
      renderResult();
      void loadSelected();
      window.h3RefreshJobs?.();
    }
  }

  async function previewMask() {
    const job = selectedJob();
    if (!job || job.status !== "done") return;
    const btn = $("gs-preview");
    if (btn) btn.disabled = true;
    try {
      const data = await postJson(`/api/game/jobs/${job.id}/preview`, { sprite: spriteSettingsPayload(ui.sprite) });
      live.maskUrl = data.url;
      setView("mask");
      const warn = (data.issues || []).map(issueText);
      toast(warn.length ? warn.join(" · ") : t("game.previewReady", { pct: (data.coverage || []).map((c) => Math.round(c * 100) + "%").join(" / ") }));
    } catch (e) {
      toast(e.message || String(e));
    } finally {
      renderResult();
    }
  }

  async function buildAtlas() {
    const set = currentSet();
    if (!set) return;
    try {
      const data = await postJson(`/api/game/sets/${set.id}/atlas`, {});
      const a = document.createElement("a");
      a.href = data.base_url + data.zip;
      a.download = data.zip;
      document.body.append(a);
      a.click();
      a.remove();
      toast(t("game.atlasReady", { n: data.animations.length }));
    } catch (e) {
      toast(e.message || String(e));
    }
  }

  async function retryJob(id) {
    try {
      const response = await fetch(`/api/jobs/${id}/retry`, { method: "POST" });
      if (!response.ok) throw new Error(await errorText(response));
      live.prev[id] = "queued";
      toast(t("game.retried"));
      await window.h3RefreshJobs?.();
    } catch (e) {
      toast(e.message || String(e));
    }
  }

  function selectJob(id) {
    live.selected = id;
    const job = selectedJob();
    if (job) live.setId = job.game.set_id;
    live.maskUrl = job?.game?.result?.files?.mask_preview ? job.game.result.base_url + job.game.result.files.mask_preview : "";
    saveSettings();
    renderJobsList();
    renderSettings();
    renderResult();
    void loadSelected();
  }

  function onJobs(jobs) {
    const game = (jobs || []).filter((j) => j && j.game && j.game.set_id);
    live.jobs = game;
    for (const job of game) {
      const was = live.prev[job.id];
      // Only clips that finish while the page is open are processed automatically.
      if (job.status === "done" && was && was !== "done" && !job.game.result && !live.autoTried.has(job.id)) {
        live.autoTried.add(job.id);
        void processJob(job.id, { auto: true });
      }
      live.prev[job.id] = job.status;
    }
    if (live.selected && !selectedJob()) live.selected = null;
    if (!live.selected) {
      const set = currentSet();
      if (set) { live.setId = set.id; live.selected = set.jobs[0]?.id || null; }
    }
    renderSets();
    renderJobsList();
    renderResult();
    void loadSelected();
  }

  // Stage.
  /** Room for the drawing between the HUD rows that overlay the top and bottom of the stage. */
  function stageBox() {
    const view = $("gs-view");
    const r = view ? view.getBoundingClientRect() : { width: 0, height: 0 };
    const hud = [...document.querySelectorAll("#gs-stage .mb-hud-top, #gs-stage .mb-hud-bottom")]
      .reduce((sum, row) => sum + row.getBoundingClientRect().height, 0);
    return { w: Math.max(0, r.width - 24), h: Math.max(0, r.height - hud - 32) };
  }

  /**
   * While H3 renders, slow status polls fill the browser's per-host connections and low-priority
   * images can starve; frames ask for high priority and time out so the next job refresh retries.
   */
  function loadImage(src, ms = 15000) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.fetchPriority = "high";
      const timer = setTimeout(() => { img.onload = img.onerror = null; reject(new Error(src)); }, ms);
      img.onload = () => { clearTimeout(timer); resolve(img); };
      img.onerror = () => { clearTimeout(timer); reject(new Error(src)); };
      img.src = src;
    });
  }

  async function loadSelected() {
    const job = selectedJob();
    const result = job?.game?.result;
    const key = result?.ok ? `${job.id}:${result.run}` : "";
    if (key === live.loadedKey && (!key || live.frames.length || live.loadingKey === key)) { draw(); return; }
    live.loadedKey = key;
    live.loadingKey = key;
    live.frames = [];
    live.sheet = null;
    live.frameIndex = 0;
    if (key) {
      try {
        const [sheet, ...frames] = await Promise.all(
          [result.files.sheet, ...result.files.frames].map((f) => loadImage(result.base_url + f)),
        );
        if (live.loadedKey !== key) return;
        live.frames = frames;
        live.sheet = sheet;
        if (!live.maskUrl) live.maskUrl = result.base_url + result.files.mask_preview;
      } catch {
        // Left empty so the next job refresh tries again.
      } finally {
        if (live.loadingKey === key) live.loadingKey = "";
      }
    }
    draw();
    schedule();
  }

  function setView(view) {
    live.view = ["anim", "seam", "mask", "sheet"].includes(view) ? view : "anim";
    chipGroup("gs-views", "data-gs-view", live.view);
    draw();
    schedule();
  }

  function cellSize() {
    return live.frames[0]?.naturalWidth || selectedJob()?.game?.result?.cell || 64;
  }

  function drawPivot(ctx, x0, y0, zoom) {
    const pivot = selectedJob()?.game?.result?.pivot;
    if (!live.pivot || !pivot) return;
    ctx.fillStyle = "rgba(255, 64, 96, 0.9)";
    const px = x0 + pivot.x * zoom;
    const py = y0 + pivot.y * zoom;
    ctx.fillRect(px - zoom * 2, py, zoom * 5, Math.max(1, Math.floor(zoom / 2)));
    ctx.fillRect(px, py - zoom * 2, Math.max(1, Math.floor(zoom / 2)), zoom * 4);
  }

  function draw() {
    const canvas = $("gs-canvas");
    const mask = $("gs-mask-img");
    const empty = $("gs-empty");
    const view = $("gs-view");
    if (!canvas || !mask || !view) return;
    view.dataset.bg = live.bg;
    mask.alt = t("game.maskAlt");
    const hasFrames = live.frames.length > 0;
    const showMask = live.view === "mask" && !!live.maskUrl;
    mask.classList.toggle("hidden", !showMask);
    if (showMask && mask.dataset.src !== live.maskUrl) { mask.src = live.maskUrl; mask.dataset.src = live.maskUrl; }
    canvas.classList.toggle("hidden", showMask || !hasFrames);
    if (empty) {
      empty.classList.toggle("hidden", showMask || hasFrames);
      const job = selectedJob();
      const body = $("gs-empty-body");
      if (body) body.textContent = !job ? t("game.emptyBody") : job.game.result && !job.game.result.ok ? t("game.emptyFailed") : stateLabel(job);
    }
    if (showMask || !hasFrames) return;
    const ctx = canvas.getContext("2d");
    const cell = cellSize();
    const box = stageBox();
    const n = live.frames.length;
    if (live.view === "sheet" && live.sheet) {
      const z = live.zoom || fitZoom(live.sheet.naturalWidth, live.sheet.naturalHeight, box.w, box.h);
      canvas.width = live.sheet.naturalWidth * z;
      canvas.height = live.sheet.naturalHeight * z;
      ctx.imageSmoothingEnabled = false;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(live.sheet, 0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = "rgba(255, 170, 60, 0.55)";
      ctx.lineWidth = 1;
      for (let x = 0; x <= live.sheet.naturalWidth; x += cell) { ctx.beginPath(); ctx.moveTo(x * z + 0.5, 0); ctx.lineTo(x * z + 0.5, canvas.height); ctx.stroke(); }
      for (let y = 0; y <= live.sheet.naturalHeight; y += cell) { ctx.beginPath(); ctx.moveTo(0, y * z + 0.5); ctx.lineTo(canvas.width, y * z + 0.5); ctx.stroke(); }
      return;
    }
    if (live.view === "seam") {
      const picks = seamFrames(n);
      const gap = 6;
      const z = live.zoom || fitZoom(cell * picks.length + gap * (picks.length - 1), cell, box.w, box.h);
      canvas.width = picks.length * cell * z + (picks.length - 1) * gap;
      canvas.height = cell * z;
      ctx.imageSmoothingEnabled = false;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      picks.forEach((idx, i) => {
        const x = i * (cell * z + gap);
        ctx.drawImage(live.frames[idx], x, 0, cell * z, cell * z);
        if (idx === 0 && i > 0) {
          ctx.fillStyle = "rgba(255, 170, 60, 0.95)";
          ctx.fillRect(x - gap / 2 - 1, 0, 2, canvas.height);
        }
      });
      return;
    }
    const z = live.zoom || fitZoom(cell, cell, box.w, box.h);
    canvas.width = cell * z;
    canvas.height = cell * z;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(live.frames[live.frameIndex % n], 0, 0, cell * z, cell * z);
    drawPivot(ctx, 0, 0, z);
  }

  function renderInfo() {
    const info = $("gs-info");
    if (!info) return;
    const result = selectedJob()?.game?.result;
    if (!result?.ok) { info.textContent = ""; return; }
    const n = result.frames;
    const frame = live.view === "anim" && live.frames.length ? `${(live.frameIndex % n) + 1}/${n} · ` : "";
    const seam = live.view === "seam" ? (result.loop ? `${t("game.seamLabel")} · ` : `${t("game.onceNoSeam")} · `) : "";
    info.textContent = `${seam}${frame}${result.cell}×${result.cell} · ${result.fps} fps · ${t("game.pivotAt", { x: result.pivot.x, y: result.pivot.y })}`;
  }

  function schedule() {
    clearTimeout(live.timer);
    if (!workspaceShown() || live.view !== "anim" || !live.playing || live.frames.length < 2) { renderInfo(); return; }
    const result = selectedJob()?.game?.result;
    const fps = Math.max(1, Number(result?.fps) || 10);
    live.timer = setTimeout(() => {
      const n = live.frames.length;
      const next = live.frameIndex + 1;
      // One-shot animations pause on the last frame before replaying.
      live.frameIndex = result && !result.loop && next >= n ? 0 : next % n;
      draw();
      renderInfo();
      const hold = result && !result.loop && live.frameIndex === n - 1 ? 600 : 0;
      if (hold) setTimeout(schedule, hold); else schedule();
    }, 1000 / fps);
    renderInfo();
  }

  function syncStage() {
    $("gs-stage")?.classList.toggle("hidden", !present());
    $("panel-workspace-game")?.classList.toggle("hidden", !present());
    const play = $("gs-play");
    if (play) play.textContent = t(live.playing ? "game.pause" : "game.play");
    chipGroup("gs-bg", "data-gs-bg", live.bg);
    chipGroup("gs-zoom", "data-gs-zoom", live.zoom);
    chipGroup("gs-views", "data-gs-view", live.view);
    $("gs-pivot")?.setAttribute("aria-pressed", live.pivot ? "true" : "false");
    $("gs-pivot")?.classList.toggle("on", live.pivot);
    draw();
    schedule();
  }

  // Bindings.
  function bindNumber(id, key, { live: instant = false } = {}) {
    const el = $(id);
    if (!el) return;
    el.addEventListener(instant ? "input" : "change", () => {
      ui.sprite[key] = el.type === "range" ? Number(el.value) : el.value.trim();
      saveSettings();
      renderSettings();
    });
  }

  function bind() {
    $("gs-file")?.addEventListener("change", (e) => uploadRef(e.target.files?.[0]));
    // Files are accepted anywhere on the panel; dragged page images only on the character area,
    // so text dragged into the description field still works.
    const panel = $("panel-workspace-game");
    const accepts = (e) => e.dataTransfer?.types?.includes("Files") || !!e.target.closest?.("#gs-drop, #gs-ref");
    const highlight = (on) => ["gs-drop", "gs-ref"].forEach((id) => $(id)?.classList.toggle("is-dragover", on));
    panel?.addEventListener("dragover", (e) => {
      if (!accepts(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      highlight(true);
    });
    panel?.addEventListener("dragleave", (e) => { if (!panel.contains(e.relatedTarget)) highlight(false); });
    panel?.addEventListener("drop", (e) => {
      highlight(false);
      if (!accepts(e)) return;
      e.preventDefault();
      dropRef(e.dataTransfer);
    });
    $("gs-ref-remove")?.addEventListener("click", () => {
      ui.ref = null;
      ui.suggestion = null;
      saveSettings();
      renderRef();
      renderBackdrop();
      syncGenerate();
    });
    $("gs-desc")?.addEventListener("input", (e) => { ui.description = e.target.value.slice(0, 400); saveSettings(); });
    $("gs-backdrop")?.addEventListener("click", (e) => {
      const chip = e.target.closest("[data-gs-backdrop]");
      if (!chip) return;
      ui.backdrop = chip.dataset.gsBackdrop;
      ui.backdropManual = !ui.suggestion || ui.backdrop !== ui.suggestion.suggested;
      saveSettings();
      renderBackdrop();
    });
    const chips = (id, attr, apply) => $(id)?.addEventListener("click", (e) => {
      const chip = e.target.closest(`[${attr}]`);
      if (!chip) return;
      apply(chip.getAttribute(attr));
      saveSettings();
      renderSettings();
    });
    chips("gs-preset", "data-gs-preset", (v) => { if (RENDER_PRESETS.includes(v)) ui.preset = v; });
    chips("gs-cell", "data-gs-cell", (v) => { ui.sprite.cell = Number(v); });
    chips("gs-detail", "data-gs-detail", (v) => { ui.sprite.detail = v; });
    bindNumber("gs-frames", "frames");
    bindNumber("gs-fps", "fps");
    bindNumber("gs-loop-start", "loopStart");
    bindNumber("gs-loop-end", "loopEnd");
    bindNumber("gs-tolerance", "tolerance", { live: true });
    bindNumber("gs-hole", "hole", { live: true });
    bindNumber("gs-edge", "edge", { live: true });
    $("gs-palette")?.addEventListener("change", (e) => { ui.sprite.palette = Number(e.target.value) || 0; saveSettings(); });
    $("gs-generate")?.addEventListener("click", generate);
    $("gs-set")?.addEventListener("change", (e) => {
      live.setId = e.target.value;
      live.selected = currentSet()?.jobs[0]?.id || null;
      selectJob(live.selected);
    });
    $("gs-jobs")?.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-act]");
      if (!btn) return;
      const id = btn.dataset.id;
      if (btn.dataset.act === "select") selectJob(id);
      if (btn.dataset.act === "retry") retryJob(id);
      if (btn.dataset.act === "process") { selectJob(id); processJob(id); }
      if (btn.dataset.act === "source") window.h3PlayJob?.(id);
    });
    $("gs-process")?.addEventListener("click", () => { if (live.selected) processJob(live.selected); });
    $("gs-preview")?.addEventListener("click", previewMask);
    $("gs-atlas")?.addEventListener("click", buildAtlas);
    $("gs-zip")?.addEventListener("click", (e) => { if (!$("gs-zip").getAttribute("href")) e.preventDefault(); });
    $("gs-bg")?.addEventListener("click", (e) => { const c = e.target.closest("[data-gs-bg]"); if (c) { live.bg = c.dataset.gsBg; syncStage(); } });
    $("gs-zoom")?.addEventListener("click", (e) => { const c = e.target.closest("[data-gs-zoom]"); if (c) { live.zoom = Number(c.dataset.gsZoom) || 0; syncStage(); } });
    $("gs-views")?.addEventListener("click", (e) => { const c = e.target.closest("[data-gs-view]"); if (c) { setView(c.dataset.gsView); renderInfo(); } });
    $("gs-mask-img")?.addEventListener("click", () => { if (live.maskUrl) window.open(live.maskUrl, "_blank", "noopener"); });
    $("gs-play")?.addEventListener("click", () => { live.playing = !live.playing; syncStage(); });
    $("gs-pivot")?.addEventListener("click", () => { live.pivot = !live.pivot; syncStage(); });
    document.addEventListener("h3-jobs", (e) => onJobs(e.detail?.jobs));
    document.addEventListener("h3-workspace", syncStage);
    document.addEventListener("h3-motion-view", syncStage);
    document.addEventListener("h3-lang", () => { renderAnims(); renderBackdrop(); renderSettings(); syncGenerate(); renderSets(); renderJobsList(); renderResult(); syncStage(); });
    window.addEventListener("resize", () => { if (present()) draw(); });
  }

  async function loadPresets() {
    try {
      const [presets, accel] = await Promise.all([fetch("/api/game/presets"), fetch("/api/h3-acceleration")]);
      if (presets.ok) live.presets = await presets.json();
      if (accel.ok) live.accel = await accel.json();
    } catch {
      /* the panel still works with server-side defaults */
    }
    renderSettings();
  }

  function init() {
    if (!$("panel-workspace-game")) return;
    loadSettings();
    renderAnims();
    renderRef();
    renderBackdrop();
    renderSettings();
    syncGenerate();
    bind();
    syncStage();
    void loadPresets();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
