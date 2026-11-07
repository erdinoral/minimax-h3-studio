(() => {
  const $ = (id) => document.getElementById(id);
  const t = (key, args = {}) => Object.entries(args).reduce((s, [k, v]) => s.replace(`{${k}}`, v), window.t ? window.t(key) : key);
  const FPS = 24;
  const MIN_SECONDS = 4;
  // Long side 1280, even sizes; the stage keeps this aspect so the live view matches the take.
  const TAKE_SIZES = { "16:9": [1280, 720], "9:16": [720, 1280], "1:1": [960, 960], "21:9": [1344, 576], "4:3": [1152, 864] };
  const GAITS = ["linear_1d", "directional_2d", "crouch_directional_2d", "skipping_1d", "vogue_1d",
    "injured_torso_1d", "injured_leg_1d", "zombie_1d", "combat_1d"];
  // Capture mode keeps the page's own HUD; the Studio stage replaces it.
  const FRAME_CSS = "#title,#stats,#log,#timeline-wrap,#caption,#card{display:none!important}";

  const SOURCES = ["video", "robot", "sketch"];
  let source = "video";
  try { source = SOURCES.includes(localStorage.getItem("h3.motionSource")) ? localStorage.getItem("h3.motionSource") : "video"; } catch {}
  window.h3MotionSource = () => source;
  let frame = null, win = null, prepared = false, looping = false, lastTick = 0, lastPose = null;
  let gait = GAITS[0], running = false, recording = null, uploading = false, takeSeconds = 10;
  let stepping = Promise.resolve(), previewBusy = false, notice = null, pendingTake = null;
  const TAKE_KEY = "robot-take";

  const mb = () => (win && win.MB && win.MBCapture ? win.MB : null);
  const modelReady = () => !!(mb() && win.MBCapture.ready());
  // The stage stays in the DOM whenever the robot is the source; Result only fades it out,
  // so the iframe, pose and camera survive and a running take keeps recording.
  const present = () => document.body.classList.contains("ws-motion") && source === "robot";
  const active = () => present() && (window.h3MotionView?.() || "workspace") === "workspace";
  const aspect = () => document.querySelector("#aspect-chips .chip.on")?.dataset.aspect || "16:9";
  const takeSize = () => TAKE_SIZES[aspect()] || TAKE_SIZES["16:9"];
  // A macrotask yield: unlike requestAnimationFrame it keeps running in a background tab.
  const yieldTask = () => new Promise((resolve) => setTimeout(resolve, 0));

  // MBCapture.step must never overlap: concurrent deliver() calls splice the same pending
  // inference twice, drop a result and stall the page.
  function step(dt) {
    const target = win;
    const run = stepping.then(() => target.MBCapture.step(1, dt, null, false));
    stepping = run.catch(() => {});
    return run;
  }

  function setSource(next) {
    source = SOURCES.includes(next) ? next : "video";
    try { localStorage.setItem("h3.motionSource", source); } catch {}
    document.querySelectorAll("#motion-source [data-motion-source]").forEach((button) => {
      const on = button.dataset.motionSource === source;
      button.classList.toggle("on", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
    sync();
  }

  function sync() {
    const robot = source === "robot";
    document.body.classList.toggle("motion-src-robot", robot);
    document.body.classList.toggle("motion-src-sketch", source === "sketch");
    $("motion-robot-panel")?.classList.toggle("hidden", !robot);
    $("motion-sketch-panel")?.classList.toggle("hidden", source !== "sketch");
    $("v2v-video-pick")?.classList.toggle("hidden", source !== "video");
    document.dispatchEvent(new CustomEvent("h3-motion-source", { detail: source }));
    $("mb-stage")?.classList.toggle("hidden", !present());
    if (!active()) {
      if (document.fullscreenElement === $("mb-stage")) document.exitFullscreen?.();
      return;
    }
    $("player")?.pause();
    ensureFrame();
    fit();
    if (!looping) { looping = true; lastTick = performance.now(); requestAnimationFrame(loop); }
  }

  function ensureFrame() {
    if (frame) return;
    frame = document.createElement("iframe");
    frame.title = "MotionBricks";
    frame.src = "/motionbricks/index.html?capture=1";
    frame.addEventListener("load", () => {
      win = frame.contentWindow;
      // Steps queued on the unloaded page never settle.
      stepping = Promise.resolve();
      previewBusy = false;
      prepared = false;
      lastPose = null;
      const style = win.document.createElement("style");
      style.textContent = FRAME_CSS;
      win.document.head.append(style);
    });
    $("mb-frame").append(frame);
  }

  function fit() {
    const stage = $("mb-stage"), box = $("mb-frame");
    if (!stage || !box) return;
    const [w, h] = takeSize();
    const scale = Math.min(stage.clientWidth / w, stage.clientHeight / h);
    if (!(scale > 0)) return;
    box.style.width = `${Math.floor(w * scale)}px`;
    box.style.height = `${Math.floor(h * scale)}px`;
  }

  function prepare() {
    const { ui } = mb();
    Object.assign(ui, { ghosts: false, plan: false, boxes: false, probe: false, contacts: false, trail: false, run: running });
    mb().setMode(gait);
    frameCamera();
    prepared = true;
  }

  function frameCamera() {
    const { character: ch, camera, controls } = mb();
    const p = ch.pose, f = ch.movement.currentFacing;
    const back = 4.2, side = 1.2;
    // MotionBricks is Z-up; three.js shows world (x, y, z) at (x, z, -y).
    const x = p[0] - f[0] * back - f[1] * side, y = p[1] - f[1] * back + f[0] * side;
    camera.position.set(x, 1.6, -y);
    controls.target.set(p[0], 0.85, -p[1]);
    camera.lookAt(controls.target);
    lastPose = null;
  }

  // Same delta follow as the playground's live mode, which capture mode turns off.
  function follow() {
    const { character: ch, camera, controls } = mb();
    const p = [ch.pose[0], ch.pose[2] * 0.9, -ch.pose[1]];
    if (!lastPose) { lastPose = p; return; }
    const d = [p[0] - lastPose[0], (p[1] - lastPose[1]) * 0.3, p[2] - lastPose[2]];
    camera.position.set(camera.position.x + d[0], camera.position.y + d[1], camera.position.z + d[2]);
    controls.target.set(controls.target.x + d[0], controls.target.y + d[1], controls.target.z + d[2]);
    lastPose = [lastPose[0] + d[0], lastPose[1] + d[1], lastPose[2] + d[2]];
  }

  function draw() {
    follow();
    mb().controls.update();
    win.MBCapture.render();
  }

  // Capture mode hands each plan over a fixed sim latency after the request and blocks until the
  // worker answers; single-thread WASM needs ~250 ms, so a 0.12 s latency froze every plan.
  function tuneLatency() {
    const { character: ch } = mb();
    const ms = ch.stats?.avgMs;
    if (!ch.inference || !(ms > 0)) return;
    ch.inference.latency = Math.min(0.6, Math.max(0.12, (ms * 1.25) / 1000 + 1 / FPS));
  }

  function loop(now) {
    if (!active() && !recording) { looping = false; return; }
    if (mb() && !recording) {
      if (!prepared) prepare();
      tuneLatency();
      const dt = Math.min(Math.max((now - lastTick) / 1000, 1 / 240), 1 / 20);
      if (modelReady() && !previewBusy) {
        const target = win;
        previewBusy = true;
        step(dt).finally(() => { if (win === target) previewBusy = false; });
      }
      draw();
    }
    lastTick = now;
    renderStatus();
    requestAnimationFrame(loop);
  }

  function renderStatus() {
    const status = $("mb-status");
    const error = win?.document.getElementById("load-error")?.textContent.trim();
    if (notice && performance.now() > notice.until) notice = null;
    const message = error ? t("motion.loadError", { error })
      : notice ? notice.message
      : uploading ? t("motion.uploading")
      : !mb() ? t("motion.loadingScene")
      : !modelReady() ? t("motion.loadingModel") : "";
    if (status.textContent !== message) status.textContent = message;
    status.classList.toggle("hidden", !message);
    const record = $("mb-record");
    record.disabled = uploading || (!recording && !modelReady());
    record.classList.toggle("on", !!recording);
    record.textContent = recording
      ? t("motion.stop", { t: (recording.frames / FPS).toFixed(1), total: String(recording.seconds) })
      : t("motion.record");
    $("mb-rec").classList.toggle("hidden", !recording);
    if (recording) $("mb-rec-time").textContent = `${(recording.frames / FPS).toFixed(1)} s`;
    $("mb-fullscreen").textContent = t(document.fullscreenElement ? "motion.exitFullscreen" : "motion.fullscreen");
  }

  function sceneHelpers() {
    const helpers = [];
    mb().world.traverse((object) => {
      if (object.isSprite || object.geometry?.type === "RingGeometry") helpers.push(object);
    });
    return helpers;
  }

  async function record() {
    if (recording) { recording.stop = true; return; }
    if (!modelReady() || uploading) return;
    const { renderer, camera } = mb();
    const canvas = renderer.domElement;
    const [w, h] = takeSize();
    const frames = [];
    recording = { stop: false, frames: 0, seconds: takeSeconds };
    document.body.classList.add("mb-recording");
    $("motion-view-workspace")?.setAttribute("title", t("motion.recording"));
    renderTake();
    const helpers = sceneHelpers();
    const total = takeSeconds * FPS;
    try {
      while (frames.length < total && !recording.stop) {
        // A window resize (fullscreen toggle) resets the canvas, so the take size is re-applied per frame.
        if (canvas.width !== w || canvas.height !== h) {
          renderer.setSize(w, h, false);
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
        }
        // A fixed step per frame keeps the take at a true 24 fps however slow the browser is.
        await step(1 / FPS);
        helpers.forEach((object) => { object.visible = false; });
        draw();
        frames.push(await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92)));
        recording.frames = frames.length;
        renderStatus();
        await yieldTask();
      }
    } finally {
      helpers.forEach((object) => { object.visible = true; });
      renderer.setSize(win.innerWidth, win.innerHeight);
      camera.aspect = win.innerWidth / win.innerHeight;
      camera.updateProjectionMatrix();
      recording = null;
      document.body.classList.remove("mb-recording");
      $("motion-view-workspace")?.removeAttribute("title");
      renderTake();
    }
    if (frames.length < MIN_SECONDS * FPS) {
      notify(t("motion.tooShort"));
      return;
    }
    await upload({ blob: new Blob(frames, { type: "video/x-motion-jpeg" }), frames: frames.length, savedAt: Date.now() });
  }

  async function upload(take) {
    uploading = true;
    renderStatus();
    renderTake();
    try {
      const body = new FormData();
      body.append("file", take.blob, "robot_take.mjpeg");
      const response = await fetch("/api/motionbricks/take", { method: "POST", body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : response.statusText);
      window.h3SetMotionReference?.(data);
      dropTake();
    } catch (error) {
      keepTake(take);
      notify(t("motion.uploadFailed", { error: String(error.message || error) }));
    } finally {
      uploading = false;
      renderStatus();
      renderTake();
    }
  }

  // A take that failed to upload stays here (and in IndexedDB) until it is sent, saved or discarded.
  function keepTake(take) {
    pendingTake = take;
    window.h3MotionStore?.put(TAKE_KEY, take).catch(() => {});
  }

  function dropTake() {
    pendingTake = null;
    void window.h3MotionStore?.delete(TAKE_KEY);
  }

  function renderTake() {
    const bar = $("mb-take-retry");
    if (!bar) return;
    bar.classList.toggle("hidden", !pendingTake);
    if (!pendingTake) return;
    $("mb-take-retry-msg").textContent = t("motion.takePending", { sec: (pendingTake.frames / FPS).toFixed(1) });
    bar.querySelectorAll("button").forEach((button) => { button.disabled = uploading || !!recording; });
  }

  function downloadTake() {
    if (!pendingTake) return;
    const url = URL.createObjectURL(pendingTake.blob);
    const link = document.createElement("a");
    const stamp = new Date(pendingTake.savedAt || Date.now()).toISOString().slice(0, 19).replace(/[:T]/g, "-");
    link.href = url;
    link.download = `robot_take_${stamp}.mjpeg`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  async function restoreTake() {
    const take = await window.h3MotionStore?.get(TAKE_KEY);
    if (take?.blob && !pendingTake) {
      pendingTake = take;
      renderTake();
    }
  }

  function notify(message) {
    notice = { message, until: performance.now() + 5000 };
    renderStatus();
    setTimeout(renderStatus, 5100);
  }

  function renderGaits() {
    const host = $("mb-gaits");
    if (!host) return;
    host.innerHTML = "";
    GAITS.forEach((name) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `mb-btn${name === gait ? " on" : ""}`;
      button.textContent = t(`gait.${name}`);
      button.onclick = () => {
        gait = name;
        if (mb()) mb().setMode(name);
        renderGaits();
        focusFrame();
      };
      host.append(button);
    });
  }

  // HUD clicks take focus from the iframe; give it back so WASD keeps steering.
  function focusFrame() { win?.focus(); }

  function bind() {
    document.querySelectorAll("#motion-source [data-motion-source]").forEach((button) => {
      button.addEventListener("click", () => setSource(button.dataset.motionSource));
    });
    document.querySelectorAll("#mb-seconds-chips [data-mb-seconds]").forEach((chip) => {
      chip.addEventListener("click", () => {
        takeSeconds = Number(chip.dataset.mbSeconds) || 10;
        document.querySelectorAll("#mb-seconds-chips .chip").forEach((c) => c.classList.toggle("on", c === chip));
      });
    });
    $("mb-record")?.addEventListener("click", () => { void record(); focusFrame(); });
    $("mb-take-upload")?.addEventListener("click", () => { if (pendingTake && !uploading) void upload(pendingTake); });
    $("mb-take-download")?.addEventListener("click", downloadTake);
    $("mb-take-discard")?.addEventListener("click", () => {
      if (pendingTake && window.confirm(t("motion.takeDiscardConfirm"))) { dropTake(); renderTake(); }
    });
    $("mb-run")?.addEventListener("click", (event) => {
      running = !running;
      event.currentTarget.classList.toggle("on", running);
      event.currentTarget.setAttribute("aria-pressed", running ? "true" : "false");
      if (mb()) mb().ui.run = running;
      focusFrame();
    });
    $("mb-interact")?.addEventListener("click", () => { if (mb()) mb().ui.interact = true; focusFrame(); });
    $("mb-camera")?.addEventListener("click", () => { if (mb()) frameCamera(); focusFrame(); });
    $("mb-restart")?.addEventListener("click", () => {
      if (!frame || recording || uploading) return;
      win = null;
      frame.contentWindow.location.reload();
    });
    $("mb-fullscreen")?.addEventListener("click", () => {
      if (document.fullscreenElement) document.exitFullscreen?.();
      else $("mb-stage")?.requestFullscreen?.();
    });
    document.addEventListener("fullscreenchange", () => requestAnimationFrame(fit));
    document.querySelector("#aspect-chips")?.addEventListener("click", () => requestAnimationFrame(fit));
    if ($("mb-stage") && window.ResizeObserver) new ResizeObserver(fit).observe($("mb-stage"));
    document.addEventListener("h3-workspace", sync);
    document.addEventListener("h3-motion-view", sync);
    document.addEventListener("h3-lang", () => { renderGaits(); renderTake(); if (present()) renderStatus(); });
  }

  bind();
  renderGaits();
  setSource(source);
  void restoreTake();
})();
