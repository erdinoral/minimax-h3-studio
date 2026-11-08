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
  // [back, left, height] from the robot along its facing when the shot is framed.
  const CAMERAS = { behind: [4.2, 1.2, 1.6], side: [0.3, 4.5, 1.3], front: [-4.5, 0.6, 1.5], tripod: [-6, 4, 1.6], wide: [8.5, 2.5, 4.2] };
  // "course" is MotionBricks' built-in layout: every object in one lane along +X from the start at x = -5.5,
  // vault at 4, duck-under at 12, jump at 19.5, seat at (19.3, 11). Presets are authored for it.
  const LAYOUTS = ["gym", "course"];
  const PRESETS = {
    vault: { seconds: 10, steps: [{ goal: [7, 0] }] },
    parkour: { seconds: 15, steps: [{ goal: [24, 0], run: true }] },
    parkourSit: { seconds: 20, steps: [{ goal: [21.5, 0], run: true }, { goal: [19.8, 8.5], run: true }, { goal: [19.3, 11] }] },
    zombie: { seconds: 10, steps: [{ mode: "zombie_1d", goal: [0, 0] }] },
    sneak: { seconds: 10, steps: [{ mode: "crouch_directional_2d", goal: [2, 0] }] },
    vogue: { seconds: 15, steps: [{ mode: "vogue_1d", goal: [-1.5, 0] }, { goal: [-1.5, 3] }, { goal: [-5, 3] }, { goal: [-5, 0] }] },
    injured: { seconds: 10, steps: [{ mode: "injured_leg_1d", goal: [-1, 0] }] },
  };
  const OBJECTS = ["MidJumpSP", "AvoidanceSP", "SmallJumpSP", "SitSP"];

  const SOURCES = ["video", "robot", "sketch"];
  const stored = (key, allowed, fallback) => {
    try { const value = localStorage.getItem(key); return allowed.includes(value) ? value : fallback; } catch { return fallback; }
  };
  let source = stored("h3.motionSource", SOURCES, "video");
  let cameraMode = stored("h3.mbCamera", Object.keys(CAMERAS), "behind");
  let layout = stored("h3.mbLayout", LAYOUTS, "gym");
  let preset = stored("h3.mbPreset", Object.keys(PRESETS), "parkour");
  let script = null, presetBusy = false;
  window.h3MotionSource = () => source;
  let frame = null, win = null, prepared = false, looping = false, lastTick = 0, lastPose = null;
  let gait = GAITS[0], running = false, recording = null, uploading = false, takeSeconds = 10;
  let stepping = Promise.resolve(), previewBusy = false, notice = null, pendingTake = null, lastTake = null;
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
    frame.src = frameUrl();
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

  function frameUrl() {
    return `/motionbricks/index.html?capture=1${layout === "course" ? "&scene=course" : ""}`;
  }

  function frameCamera() {
    const { character: ch, camera, controls } = mb();
    const p = ch.pose, f = ch.movement.currentFacing;
    const [back, side, height] = CAMERAS[cameraMode];
    // MotionBricks is Z-up; three.js shows world (x, y, z) at (x, z, -y).
    const x = p[0] - f[0] * back - f[1] * side, y = p[1] - f[1] * back + f[0] * side;
    camera.position.set(x, height, -y);
    controls.target.set(p[0], 0.85, -p[1]);
    camera.lookAt(controls.target);
    lastPose = null;
  }

  // Same delta follow as the playground's live mode, which capture mode turns off.
  // The tripod camera stays put and only pans to keep the robot in frame.
  function follow() {
    const { character: ch, camera, controls } = mb();
    if (cameraMode === "tripod") { controls.target.set(ch.pose[0], 0.85, -ch.pose[1]); return; }
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
        presetTick();
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
    const presetOff = !!recording || uploading || presetBusy || !modelReady();
    ["mb-preset-try", "mb-preset-record"].forEach((id) => { if ($(id)) $(id).disabled = presetOff; });
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
    const frames = [], events = [];
    let lastActive = null;
    recording = { stop: false, frames: 0, seconds: takeSeconds };
    document.body.classList.add("mb-recording");
    $("motion-view-workspace")?.setAttribute("title", t("motion.recording"));
    renderTake();
    renderOptions();
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
        presetTick();
        await step(1 / FPS);
        const active = mb().director?.active || null;
        if (active && active !== lastActive && OBJECTS.includes(active.name)) {
          events.push({ t: frames.length / FPS, kind: active.name });
        }
        lastActive = active;
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
      endScript();
      document.body.classList.remove("mb-recording");
      $("motion-view-workspace")?.removeAttribute("title");
      renderTake();
      renderOptions();
    }
    if (frames.length < MIN_SECONDS * FPS) {
      notify(t("motion.tooShort"));
      return;
    }
    await upload({ blob: new Blob(frames, { type: "video/x-motion-jpeg" }), frames: frames.length, savedAt: Date.now(), events });
  }

  async function upload(take) {
    let ready = null;
    uploading = true;
    renderStatus();
    renderTake();
    renderOptions();
    try {
      const body = new FormData();
      body.append("file", take.blob, "robot_take.mjpeg");
      const response = await fetch("/api/motionbricks/take", { method: "POST", body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : response.statusText);
      window.h3SetMotionReference?.(data);
      ready = { url: data.url, seconds: Number(data.seconds) || take.frames / FPS, events: take.events || [] };
      dropTake();
    } catch (error) {
      keepTake(take);
      notify(t("motion.uploadFailed", { error: String(error.message || error) }));
    } finally {
      uploading = false;
      renderStatus();
      renderTake();
      renderOptions();
    }
    if (ready) { lastTake = ready; openReview(); }
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

  function openReview() {
    if (!lastTake?.url) return;
    const video = $("mb-review-video");
    if (video.getAttribute("src") !== lastTake.url) video.src = lastTake.url;
    $("mb-review-msg").textContent = t("motion.reviewMsg", { sec: lastTake.seconds.toFixed(1) });
    $("mb-review").classList.remove("hidden");
    $("mb-watch").classList.remove("hidden");
    renderObjects();
    video.currentTime = 0;
    void video.play().catch(() => {});
  }

  // A preset walks the robot through its goals one after another; the next goal is given only once
  // the previous one is reached and any interaction (vault, sit…) it triggered on the way has ended.
  function presetTick() {
    if (!script || !mb()) return;
    const { ui, character: ch } = mb();
    if (ui.goal || ch.sm.isInteracting) return;
    const next = script.steps[script.index++];
    if (!next) return;
    const mode = next.mode || (script.index === 1 ? GAITS[0] : null);
    if (mode) { gait = mode; mb().setMode(mode); renderGaits(); }
    ui.run = !!next.run || running;
    ui.goal = next.goal.slice();
    ui.goalRun = !!next.run;
  }

  function endScript() {
    if (!script) return;
    script = null;
    if (!mb()) return;
    mb().ui.goal = null;
    mb().ui.run = running;
  }

  async function until(test, ms) {
    const end = performance.now() + ms;
    while (performance.now() < end) {
      if (test()) return true;
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    return false;
  }

  // Presets always start from a fresh course layout, so the robot stands at the start facing the lane.
  async function runPreset(withRecording) {
    const plan = PRESETS[preset];
    if (!plan || recording || uploading || presetBusy) return;
    presetBusy = true;
    renderOptions();
    try {
      setLayout("course", true);
      if (!(await until(() => mb() && prepared && modelReady(), 120000))) { notify(t("motion.presetTimeout")); return; }
      script = { steps: plan.steps, index: 0 };
      if (withRecording) { setSeconds(plan.seconds); await record(); }
    } finally {
      presetBusy = false;
      renderOptions();
      focusFrame();
    }
  }

  function setSeconds(seconds) {
    takeSeconds = seconds;
    document.querySelectorAll("#mb-seconds-chips [data-mb-seconds]").forEach((chip) => {
      chip.classList.toggle("on", Number(chip.dataset.mbSeconds) === seconds);
    });
  }

  function setLayout(next, reload) {
    if (recording || uploading) return;
    const changed = next !== layout;
    layout = LAYOUTS.includes(next) ? next : "gym";
    try { localStorage.setItem("h3.mbLayout", layout); } catch {}
    renderOptions();
    if (!frame || !(changed || reload)) return;
    endScript();
    win = null;
    prepared = false;
    frame.src = frameUrl();
  }

  function setCamera(next) {
    if (recording) return;
    cameraMode = CAMERAS[next] ? next : "behind";
    try { localStorage.setItem("h3.mbCamera", cameraMode); } catch {}
    renderOptions();
    if (mb()) frameCamera();
    focusFrame();
  }

  function chipRow(hostId, values, current, labelKey, attr, onPick) {
    const host = $(hostId);
    if (!host) return;
    host.innerHTML = "";
    values.forEach((value) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = `chip${value === current ? " on" : ""}`;
      chip.dataset[attr] = value;
      chip.textContent = t(`${labelKey}.${value}`);
      chip.setAttribute("aria-pressed", value === current ? "true" : "false");
      chip.disabled = !!recording || uploading || presetBusy;
      chip.onclick = () => onPick(value);
      host.append(chip);
    });
  }

  function renderOptions() {
    chipRow("mb-presets", Object.keys(PRESETS), preset, "motion.preset", "mbPreset", (value) => {
      preset = value;
      try { localStorage.setItem("h3.mbPreset", preset); } catch {}
      renderOptions();
    });
    chipRow("mb-cameras", Object.keys(CAMERAS), cameraMode, "motion.cam", "mbCamera", setCamera);
    chipRow("mb-layouts", LAYOUTS, layout, "motion.world", "mbLayout", (value) => setLayout(value, false));
    const busy = !!recording || uploading || presetBusy;
    ["mb-preset-try", "mb-preset-record"].forEach((id) => { if ($(id)) $(id).disabled = busy || !modelReady(); });
  }

  function objectNames() {
    try { return JSON.parse(localStorage.getItem("h3.mbObjects") || "{}") || {}; } catch { return {}; }
  }

  function renderObjects() {
    const host = $("mb-objects");
    if (host && !host.childElementCount) {
      const names = objectNames();
      OBJECTS.forEach((kind) => {
        const label = document.createElement("label");
        label.className = "mb-object";
        const span = document.createElement("span");
        span.dataset.objLabel = kind;
        const input = document.createElement("input");
        input.type = "text";
        input.maxLength = 80;
        input.dataset.mbObject = kind;
        input.value = names[kind] || "";
        input.oninput = () => {
          const all = objectNames();
          all[kind] = input.value.trim();
          try { localStorage.setItem("h3.mbObjects", JSON.stringify(all)); } catch {}
        };
        label.append(span, input);
        host.append(label);
      });
    }
    host?.querySelectorAll("[data-obj-label]").forEach((span) => { span.textContent = t(`motion.obj.${span.dataset.objLabel}`); });
    host?.querySelectorAll("[data-mb-object]").forEach((input) => { input.placeholder = t(`motion.objPh.${input.dataset.mbObject}`); });
    const events = lastTake?.events || [];
    ["mb-prompt-add", "mb-review-prompt"].forEach((id) => {
      const button = $(id);
      if (!button) return;
      button.disabled = !events.length;
      button.title = events.length ? "" : t("motion.promptNone");
    });
  }

  function promptTimeline(events) {
    const names = objectNames();
    return events.map((event) => t(`motion.verb.${event.kind}`, {
      t: event.t.toFixed(1),
      obj: names[event.kind] || t(`motion.objDefault.${event.kind}`),
    })).join(" ");
  }

  function addTimelineToPrompt() {
    const events = lastTake?.events || [];
    const prompt = $("prompt");
    if (!events.length || !prompt) { notify(t("motion.promptNone")); return; }
    const line = promptTimeline(events);
    prompt.value = prompt.value.trim() ? `${prompt.value.trim()}\n${line}` : line;
    prompt.dispatchEvent(new Event("input", { bubbles: true }));
    notify(t("motion.promptAdded"));
  }

  function closeReview() {
    $("mb-review-video")?.pause();
    $("mb-review")?.classList.add("hidden");
    focusFrame();
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
    $("mb-watch")?.addEventListener("click", openReview);
    $("mb-review-keep")?.addEventListener("click", closeReview);
    $("mb-review-retake")?.addEventListener("click", () => { closeReview(); notify(t("motion.retakeHint")); });
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
      if (!frame || recording || uploading || presetBusy) return;
      endScript();
      win = null;
      frame.contentWindow.location.reload();
    });
    $("mb-preset-try")?.addEventListener("click", () => { void runPreset(false); });
    $("mb-preset-record")?.addEventListener("click", () => { void runPreset(true); });
    $("mb-prompt-add")?.addEventListener("click", addTimelineToPrompt);
    $("mb-review-prompt")?.addEventListener("click", addTimelineToPrompt);
    $("mb-fullscreen")?.addEventListener("click", () => {
      if (document.fullscreenElement) document.exitFullscreen?.();
      else $("mb-stage")?.requestFullscreen?.();
    });
    document.addEventListener("fullscreenchange", () => requestAnimationFrame(fit));
    document.querySelector("#aspect-chips")?.addEventListener("click", () => requestAnimationFrame(fit));
    if ($("mb-stage") && window.ResizeObserver) new ResizeObserver(fit).observe($("mb-stage"));
    document.addEventListener("h3-workspace", sync);
    document.addEventListener("h3-motion-view", sync);
    document.addEventListener("h3-lang", () => { renderGaits(); renderTake(); renderOptions(); renderObjects(); if (present()) renderStatus(); });
  }

  bind();
  renderGaits();
  renderOptions();
  renderObjects();
  setSource(source);
  void restoreTake();
})();
