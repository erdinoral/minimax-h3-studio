(() => {
  // Peak sampling memory grows with output pixels × seconds. On a 16 GB card,
  // 1088p × 5 s with 3 reference images (11.1 M) renders, while 1088p × 6 s (12.5 M) sometimes runs out.
  const BUDGET_PER_16GB = 12.0e6;
  const DURATIONS = [2, 3, 4, 5, 6, 8, 10, 15];
  const QUALITIES = ["1088", "768", "736", "608", "480", "352"];
  const REF_IMAGE_SECONDS = 0.1;
  const CONTINUUM_CONTEXT_SECONDS = 22 / 24;
  const MOTION_PART_SECONDS = 5;

  function budget(vramGb) {
    return vramGb > 0 ? BUDGET_PER_16GB * (vramGb / 16) : 0;
  }

  // Seconds of latent the sampler holds at once, including references and context.
  function load(req, seconds) {
    const images = (req.refImages || 0) * REF_IMAGE_SECONDS;
    const context = req.continuum ? CONTINUUM_CONTEXT_SECONDS : 0;
    if (req.motion) return MOTION_PART_SECONDS * 2 + images + context;
    return seconds + images + context;
  }

  function cost(req, size, seconds) {
    return size[0] * size[1] * load(req, seconds);
  }

  // req: { quality, duration, motion, continuum, refImages, canSplit }; sizeOf(quality) -> [w, h].
  function plan(req, sizeOf, vramGb) {
    const limit = budget(vramGb);
    const need = cost(req, sizeOf(req.quality), req.duration);
    if (!limit || need <= limit) return null;
    const out = { ratio: need / limit, options: [] };
    if (!req.motion) {
      const shorter = DURATIONS.filter((d) => d < req.duration && cost(req, sizeOf(req.quality), d) <= limit).pop();
      if (shorter) out.options.push({ kind: "shorter", duration: shorter });
    }
    const lower = QUALITIES.slice(QUALITIES.indexOf(String(req.quality)) + 1)
      .find((q) => cost(req, sizeOf(q), req.duration) <= limit);
    if (lower) out.options.push({ kind: "lower", quality: lower });
    if (req.canSplit && !req.motion && !req.continuum) {
      const split = { ...req, continuum: true };
      const chunk = DURATIONS.filter((d) => d >= 4 && d < req.duration && cost(split, sizeOf(req.quality), d) <= limit).pop();
      if (chunk) out.options.push({ kind: "split", duration: chunk, chunks: Math.ceil(req.duration / chunk) });
    }
    return out;
  }

  const api = { plan, budget, BUDGET_PER_16GB };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window === "undefined") return;

  const t = (key, args = {}) => Object.entries(args).reduce((s, [k, v]) => s.split(`{${k}}`).join(v), window.t ? window.t(key) : key);

  function label(option) {
    if (option.kind === "shorter") return t("vram.shorter", { sec: option.duration });
    if (option.kind === "lower") return t("vram.lower", { q: option.quality });
    return t("vram.split", { n: option.chunks, sec: option.duration, total: option.chunks * option.duration });
  }

  // Resolves to null (proceed unchanged), "cancel", or a body patch to apply.
  function confirm(req, sizeOf, vramGb) {
    const result = plan(req, sizeOf, vramGb);
    if (!result) return Promise.resolve(null);
    return new Promise((resolve) => {
      const modal = document.createElement("dialog");
      modal.className = "h3-refine-dialog vram-guard-dialog";
      const form = document.createElement("form");
      form.method = "dialog";
      const title = document.createElement("h3");
      title.textContent = t("vram.title");
      const text = document.createElement("p");
      text.textContent = t("vram.body", { q: req.quality, sec: req.duration, vram: Math.round(vramGb), pct: Math.round(result.ratio * 100) });
      const buttons = document.createElement("div");
      buttons.className = "row-btns vram-guard-options";
      let choice = "cancel";
      const add = (caption, value, cls) => {
        const button = document.createElement("button");
        button.type = "submit";
        button.className = cls;
        button.textContent = caption;
        button.onclick = () => { choice = value; };
        buttons.append(button);
      };
      result.options.forEach((option, i) => add(label(option), option, i === 0 ? "cta" : "btn-secondary"));
      add(t("vram.anyway"), null, "btn-secondary");
      add(t("vram.cancel"), "cancel", "btn-secondary");
      form.append(title, text, buttons);
      modal.append(form);
      document.body.append(modal);
      modal.onclose = () => {
        modal.remove();
        if (choice === "cancel" || choice === null) return resolve(choice);
        if (choice.kind === "shorter") return resolve({ duration: choice.duration });
        if (choice.kind === "lower") return resolve({ quality: choice.quality });
        resolve({ duration: choice.duration, continuation_method: "continuum", continuum_chunks: choice.chunks });
      };
      modal.showModal();
    });
  }

  window.h3VramGuard = { ...api, confirm };
})();
