(() => {
  const $ = (id) => document.getElementById(id);
  const t = (key, args = {}) => Object.entries(args).reduce((s, [k, v]) => s.replace(`{${k}}`, v), window.t ? window.t(key) : key);
  // Same canvases as the robot takes; the server pads to H3-Image's size for the aspect.
  const SIZES = { "16:9": [1280, 720], "9:16": [720, 1280], "1:1": [960, 960], "21:9": [1344, 576], "4:3": [1152, 864] };
  const COLORS = ["#111111", "#e53935", "#fb8c00", "#fdd835", "#43a047", "#1e88e5", "#8e24aa", "#6d4c41", "#f2b48c", "#9e9e9e"];
  const UNDO_LIMIT = 15;
  const DRAFT_KEY = "sketch-draft";
  const SETTINGS_KEY = "h3.sketchSettings";

  // Drafts and unsent robot takes live in IndexedDB: a reload or a failed upload must not lose them.
  const store = (() => {
    const open = () => new Promise((resolve, reject) => {
      const request = indexedDB.open("h3-motion", 1);
      request.onupgradeneeded = () => request.result.createObjectStore("items");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const run = async (mode, action) => {
      const db = await open();
      try {
        return await new Promise((resolve, reject) => {
          const tx = db.transaction("items", mode);
          const request = action(tx.objectStore("items"));
          tx.oncomplete = () => resolve(request.result);
          tx.onerror = () => reject(tx.error);
          tx.onabort = () => reject(tx.error);
        });
      } finally {
        db.close();
      }
    };
    return {
      get: (key) => run("readonly", (s) => s.get(key)).catch(() => undefined),
      put: (key, value) => run("readwrite", (s) => s.put(value, key)),
      delete: (key) => run("readwrite", (s) => s.delete(key)).catch(() => {}),
    };
  })();
  window.h3MotionStore = store;

  // Sketch history.
  // Each step keeps the ink flag with the pixels, so undoing a Clear re-enables Create frame.
  function createHistory(limit) {
    const items = [];
    return {
      push(image, ink) {
        items.push({ image, ink });
        if (items.length > limit) items.shift();
      },
      pop(width, height) {
        const last = items.pop();
        return last && last.image.width === width && last.image.height === height ? last : null;
      },
      clear() { items.length = 0; },
      get size() { return items.length; },
    };
  }
  // End sketch history.

  const canvas = $("sk-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let settings = {};
  try { settings = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") || {}; } catch {}
  let tool = settings.tool === "eraser" ? "eraser" : "pen";
  let size = [4, 10, 24].includes(settings.size) ? settings.size : 10;
  let color = COLORS.includes(settings.color) ? settings.color : COLORS[0];
  let hasInk = false, drawing = null, aspectKey = "", editMissing = null, capsAt = 0, saveTimer = 0, touched = false;
  const history = createHistory(UNDO_LIMIT);

  const aspect = () => document.querySelector("#aspect-chips .chip.on")?.dataset.aspect || "16:9";
  // Result only fades the board out, so the canvas and its undo history are kept.
  const present = () => document.body.classList.contains("ws-motion") && window.h3MotionSource?.() === "sketch";
  const visible = () => present() && (window.h3MotionView?.() || "workspace") === "workspace";
  const fidelity = () => document.querySelector("#sk-fidelity-chips .chip.on")?.dataset.skFidelity || "balanced";

  function saveSettings() {
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify({ tool, size, color, fidelity: fidelity() })); } catch {}
  }

  function paper(w, h) {
    canvas.width = w;
    canvas.height = h;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, w, h);
  }

  function drawContained(source) {
    const scale = Math.min(canvas.width / source.width, canvas.height / source.height);
    const w = source.width * scale, h = source.height * scale;
    ctx.drawImage(source, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
  }

  // A new aspect gets a fresh canvas; the drawing so far is fitted onto it, not cropped.
  function applyAspect() {
    const key = SIZES[aspect()] ? aspect() : "16:9";
    if (key === aspectKey) return;
    aspectKey = key;
    const [w, h] = SIZES[key];
    if (!hasInk) {
      paper(w, h);
    } else {
      const old = document.createElement("canvas");
      old.width = canvas.width;
      old.height = canvas.height;
      old.getContext("2d").drawImage(canvas, 0, 0);
      paper(w, h);
      drawContained(old);
      scheduleSave();
    }
    history.clear();
    fit();
  }

  function fit() {
    const stage = $("sk-stage"), board = $("sk-board");
    if (!stage || !board || stage.classList.contains("hidden")) return;
    // Leave room for the tool rows so they never cover the paper.
    const scale = Math.min((stage.clientWidth - 16) / canvas.width, (stage.clientHeight - 96) / canvas.height);
    if (!(scale > 0)) return;
    board.style.width = `${Math.floor(canvas.width * scale)}px`;
    board.style.height = `${Math.floor(canvas.height * scale)}px`;
  }

  function sync() {
    $("sk-stage")?.classList.toggle("hidden", !present());
    if (present() && Date.now() - capsAt > 30000) void loadCapabilities();
    if (!visible()) {
      if (document.fullscreenElement === $("sk-stage")) document.exitFullscreen?.();
      return;
    }
    $("player")?.pause();
    applyAspect();
    fit();
  }

  function snapshot() {
    touched = true;
    history.push(ctx.getImageData(0, 0, canvas.width, canvas.height), hasInk);
  }

  function saveDraft() {
    saveTimer = 0;
    if (!hasInk) { void store.delete(DRAFT_KEY); return; }
    canvas.toBlob((blob) => {
      if (blob) store.put(DRAFT_KEY, { blob, width: canvas.width, height: canvas.height, aspect: aspectKey, savedAt: Date.now() }).catch(() => {});
    }, "image/png");
  }

  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 400);
  }

  async function restoreDraft() {
    const draft = await store.get(DRAFT_KEY);
    if (!draft?.blob || touched || hasInk) return;
    const bitmap = await createImageBitmap(draft.blob).catch(() => null);
    if (!bitmap || touched || hasInk) return;
    paper(draft.width || bitmap.width, draft.height || bitmap.height);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close?.();
    hasInk = true;
    aspectKey = SIZES[draft.aspect] ? draft.aspect : aspectKey;
    history.clear();
    sync();
    if (present()) window.h3Toast?.(t("sketch.restored"));
  }

  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return [(event.clientX - rect.left) * canvas.width / rect.width, (event.clientY - rect.top) * canvas.height / rect.height];
  }

  function stroke(from, to) {
    ctx.strokeStyle = tool === "eraser" ? "#fff" : color;
    ctx.lineWidth = tool === "eraser" ? size * 2.5 : size;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(from[0], from[1]);
    ctx.lineTo(to[0], to[1]);
    ctx.stroke();
  }

  canvas.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    try { canvas.setPointerCapture(event.pointerId); } catch {}
    snapshot();
    const p = point(event);
    drawing = { id: event.pointerId, last: p };
    stroke(p, p);
    if (tool === "pen") hasInk = true;
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drawing || event.pointerId !== drawing.id) return;
    const events = event.getCoalescedEvents ? event.getCoalescedEvents() : [event];
    for (const e of events.length ? events : [event]) {
      const p = point(e);
      stroke(drawing.last, p);
      drawing.last = p;
    }
  });
  const end = (event) => {
    if (!drawing || event.pointerId !== drawing.id) return;
    drawing = null;
    scheduleSave();
  };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);

  async function loadImage(file) {
    if (!file || !String(file.type).startsWith("image/")) return;
    const bitmap = await createImageBitmap(file);
    snapshot();
    paper(canvas.width, canvas.height);
    drawContained(bitmap);
    bitmap.close?.();
    hasInk = true;
    scheduleSave();
    const label = $("sk-file")?.closest(".file-pick")?.querySelector(".file-pick-name");
    if (label) label.textContent = file.name || "image.png";
  }

  function renderColors() {
    const host = $("sk-colors");
    host.innerHTML = "";
    COLORS.forEach((value) => {
      const swatch = document.createElement("button");
      swatch.type = "button";
      swatch.className = `sk-swatch${value === color && tool === "pen" ? " on" : ""}`;
      swatch.style.background = value;
      swatch.title = value;
      swatch.onclick = () => { color = value; setTool("pen"); };
      host.append(swatch);
    });
  }

  function setTool(next) {
    tool = next;
    document.querySelectorAll("[data-sk-tool]").forEach((b) => b.classList.toggle("on", b.dataset.skTool === tool));
    renderColors();
    saveSettings();
  }

  function setSize(next) {
    size = next;
    document.querySelectorAll("[data-sk-size]").forEach((b) => b.classList.toggle("on", Number(b.dataset.skSize) === size));
  }

  function setFidelity(next) {
    document.querySelectorAll("#sk-fidelity-chips [data-sk-fidelity]").forEach((b) => b.classList.toggle("on", b.dataset.skFidelity === next));
  }

  // H3-Image always reads the drawing as Picture 1; the note names its missing files.
  function effectiveMethod() {
    return "edit";
  }

  function renderMethod() {
    const note = $("sk-method-note");
    if (!note) return;
    note.textContent = editMissing?.length ? t("sketch.editMissingNote", { files: editMissing.join(", ") }) : "";
    note.classList.toggle("hidden", !editMissing?.length);
  }

  async function loadCapabilities() {
    capsAt = Date.now();
    try {
      const response = await fetch("/api/sketch/capabilities");
      if (!response.ok) return;
      editMissing = (await response.json()).methods?.edit?.missing || [];
    } catch {
      return;
    }
    renderMethod();
  }

  function fullscreenLabel() {
    const button = $("sk-fullscreen");
    if (button) button.textContent = t(document.fullscreenElement === $("sk-stage") ? "motion.exitFullscreen" : "motion.fullscreen");
  }

  document.querySelectorAll("[data-sk-tool]").forEach((b) => b.addEventListener("click", () => setTool(b.dataset.skTool)));
  document.querySelectorAll("[data-sk-size]").forEach((b) => b.addEventListener("click", () => {
    setSize(Number(b.dataset.skSize) || 10);
    saveSettings();
  }));
  document.querySelectorAll("#sk-fidelity-chips [data-sk-fidelity]").forEach((b) => b.addEventListener("click", () => {
    setFidelity(b.dataset.skFidelity);
    saveSettings();
  }));
  $("sk-undo")?.addEventListener("click", () => {
    const last = history.pop(canvas.width, canvas.height);
    if (!last) return;
    ctx.putImageData(last.image, 0, 0);
    hasInk = last.ink;
    scheduleSave();
  });
  $("sk-clear")?.addEventListener("click", () => {
    snapshot();
    paper(canvas.width, canvas.height);
    hasInk = false;
    scheduleSave();
  });
  $("sk-fullscreen")?.addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen?.();
    else $("sk-stage")?.requestFullscreen?.();
  });
  $("sk-file")?.addEventListener("change", (event) => { void loadImage(event.target.files?.[0]); event.target.value = ""; });
  $("sk-stage")?.addEventListener("dragover", (event) => event.preventDefault());
  $("sk-stage")?.addEventListener("drop", (event) => {
    event.preventDefault();
    void loadImage(event.dataTransfer?.files?.[0]);
  });
  document.addEventListener("paste", (event) => {
    if (!visible()) return;
    const item = [...(event.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
    if (!item) return;
    event.preventDefault();
    void loadImage(item.getAsFile());
  });
  document.addEventListener("fullscreenchange", () => { fullscreenLabel(); requestAnimationFrame(fit); });
  document.querySelector("#aspect-chips")?.addEventListener("click", () => requestAnimationFrame(() => { if (visible()) applyAspect(); }));
  if ($("sk-stage") && window.ResizeObserver) new ResizeObserver(fit).observe($("sk-stage"));
  document.addEventListener("h3-motion-source", sync);
  document.addEventListener("h3-workspace", sync);
  document.addEventListener("h3-motion-view", sync);
  document.addEventListener("h3-lang", () => { fullscreenLabel(); renderMethod(); });
  // A pending debounce would otherwise drop the last stroke on reload.
  window.addEventListener("pagehide", () => { if (saveTimer) { clearTimeout(saveTimer); saveDraft(); } });

  window.h3SketchFidelity = fidelity;
  window.h3SketchMethod = effectiveMethod;
  window.h3SketchBlob = () => new Promise((resolve) => {
    if (!hasInk) return resolve(null);
    canvas.toBlob(resolve, "image/png");
  });

  paper(...SIZES["16:9"]);
  aspectKey = "16:9";
  setSize(size);
  if (["faithful", "balanced", "free"].includes(settings.fidelity)) setFidelity(settings.fidelity);
  setTool(tool);
  renderMethod();
  sync();
  void restoreDraft();
})();
