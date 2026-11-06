(() => {
  const $ = (id) => document.getElementById(id);
  const t = (key) => (window.t ? window.t(key) : key);
  // Same canvases as the robot takes; the server pads to Qwen's own size for the aspect.
  const SIZES = { "16:9": [1280, 720], "9:16": [720, 1280], "1:1": [960, 960], "21:9": [1344, 576], "4:3": [1152, 864] };
  const COLORS = ["#111111", "#e53935", "#fb8c00", "#fdd835", "#43a047", "#1e88e5", "#8e24aa", "#6d4c41", "#f2b48c", "#9e9e9e"];
  const UNDO_LIMIT = 15;

  const canvas = $("sk-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let tool = "pen", size = 10, color = COLORS[0], hasInk = false, drawing = null, aspectKey = "";
  const undo = [];

  const aspect = () => document.querySelector("#aspect-chips .chip.on")?.dataset.aspect || "16:9";
  const visible = () => document.body.classList.contains("ws-motion") && window.h3MotionSource?.() === "sketch";

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
    }
    undo.length = 0;
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
    const show = visible();
    $("sk-stage")?.classList.toggle("hidden", !show);
    if (!show) {
      if (document.fullscreenElement === $("sk-stage")) document.exitFullscreen?.();
      return;
    }
    $("player")?.pause();
    applyAspect();
    fit();
  }

  function snapshot() {
    undo.push(ctx.getImageData(0, 0, canvas.width, canvas.height));
    if (undo.length > UNDO_LIMIT) undo.shift();
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
  const end = (event) => { if (drawing && event.pointerId === drawing.id) drawing = null; };
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
  }

  function fullscreenLabel() {
    const button = $("sk-fullscreen");
    if (button) button.textContent = t(document.fullscreenElement === $("sk-stage") ? "motion.exitFullscreen" : "motion.fullscreen");
  }

  document.querySelectorAll("[data-sk-tool]").forEach((b) => b.addEventListener("click", () => setTool(b.dataset.skTool)));
  document.querySelectorAll("[data-sk-size]").forEach((b) => b.addEventListener("click", () => {
    size = Number(b.dataset.skSize) || 10;
    document.querySelectorAll("[data-sk-size]").forEach((x) => x.classList.toggle("on", x === b));
  }));
  document.querySelectorAll("#sk-fidelity-chips [data-sk-fidelity]").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("#sk-fidelity-chips .chip").forEach((x) => x.classList.toggle("on", x === b));
  }));
  $("sk-undo")?.addEventListener("click", () => {
    const last = undo.pop();
    if (last) ctx.putImageData(last, 0, 0);
  });
  $("sk-clear")?.addEventListener("click", () => {
    snapshot();
    paper(canvas.width, canvas.height);
    hasInk = false;
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
  document.addEventListener("h3-lang", fullscreenLabel);

  window.h3SketchFidelity = () => document.querySelector("#sk-fidelity-chips .chip.on")?.dataset.skFidelity || "balanced";
  window.h3SketchBlob = () => new Promise((resolve) => {
    if (!hasInk) return resolve(null);
    canvas.toBlob(resolve, "image/png");
  });

  paper(...SIZES["16:9"]);
  aspectKey = "16:9";
  renderColors();
  sync();
})();
