(() => {
  const element = (id) => document.getElementById(id);
  const categories = {
    camera: ["Kamera Teknikleri", "Camera Techniques"],
    lighting: ["Işık ve Renk", "Lighting & Color"],
    action: ["Aksiyon", "Action"],
    character: ["Karakter", "Character"],
    effects: ["Efektler", "Effects"],
  };
  const labels = {
    title: ["Prompt Kütüphanesi", "Prompt Library"],
    add: ["Yeni prompt", "New prompt"],
    all: ["Tümü", "All"],
    mine: ["Kaydettiklerim", "My prompts"],
    catalog: ["Hazır prompt’lar", "Starter prompts"],
    category: ["Kategori", "Category"],
    back: ["← Kategoriler", "← Categories"],
    collection: ["Koleksiyon", "Collection"],
    search: ["Ara", "Search"],
    name: ["Başlık", "Title"],
    save: ["Kütüphaneye kaydet", "Save to library"],
    cancel: ["Vazgeç", "Cancel"],
    close: ["Kapat", "Close"],
    copy: ["Kopyala", "Copy"],
    copied: ["Prompt kopyalandı.", "Prompt copied."],
    edit: ["Düzenle", "Edit"],
    remove: ["Sil", "Delete"],
    confirm: ["Silmeyi onayla", "Confirm deletion"],
    empty: ["Bu filtrelere uyan prompt bulunamadı.", "No prompts match these filters."],
    missing: ["Önizleme yok", "No preview"],
    watch: ["Önizlemeyi oynat", "Play preview"],
    required: ["Başlık ve prompt gerekli.", "A title and prompt are required."],
    storageError: ["Yerel kayıt kullanılamıyor.", "Local storage is unavailable."],
    catalogError: ["Hazır prompt’lar yüklenemedi.", "Starter prompts could not be loaded."],
    copyError: ["Kopyalanamadı. Metni karttan seçebilirsin.", "Could not copy. You can select the text on the card."],
  };
  const translate = (pair) => pair[document.documentElement.lang === "tr" ? 0 : 1];
  const t = (key) => translate(labels[key]);
  const storageKey = "h3-prompt-library-v1";
  const view = element("view-prompt-library");
  const cards = element("pl-cards");
  const folders = element("pl-folders");
  const folder = element("pl-folder");
  const folderTitle = element("pl-folder-title");
  const dialog = element("pl-dialog");
  let saved = [];
  let catalog = [];
  let catalogRequest;
  let draft;
  let category = "";
  let catalogError = false;
  let storageAvailable = true;
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || "[]");
    if (Array.isArray(stored)) saved = stored;
  } catch {
    storageAvailable = false;
  }

  function previewUrl(value, local) {
    if (local && /^\/api\/(gallery\/[^/]+\/video|clips\/[^/]+\/video)(?:\?.*)?$/.test(value || "")) return value;
    if (/^\/static\/prompt-previews\/[\w.-]+\.(mp4|webm)$/.test(value || "")) return value;
    try {
      const url = new URL(value);
      return url.protocol === "https:" ? url.href : "";
    } catch {
      return "";
    }
  }

  function persist(items) {
    try {
      localStorage.setItem(storageKey, JSON.stringify(items));
      saved = items;
      storageAvailable = true;
      render();
      return true;
    } catch {
      element(dialog.open ? "pl-form-status" : "pl-status").textContent = t("storageError");
      return false;
    }
  }

  function openEditor(item = {}) {
    draft = item;
    element("pl-name").value = item.title || "";
    element("pl-text").value = item.prompt || "";
    element("pl-edit-category").value = item.category || category || "camera";
    element("pl-form-status").textContent = "";
    dialog.showModal();
  }

  function action(key, handle) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn-secondary";
    button.textContent = t(key);
    button.addEventListener("click", handle);
    return button;
  }

  const observer = new IntersectionObserver((entries) => {
    for (const { target, isIntersecting } of entries) {
      if (isIntersecting && view.open && !document.hidden) {
        target.play().catch(() => {});
      } else {
        target.pause();
      }
    }
  });
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function makeCard(item, local) {
    const card = document.createElement("article");
    const preview = document.createElement("div");
    preview.className = "prompt-library-preview";
    if (item.previewAspect === "1:1") preview.classList.add("is-square");
    const source = previewUrl(item.video, local);
    if (source) {
      const video = document.createElement("video");
      video.preload = "none";
      video.muted = true;
      video.loop = true;
      video.playsInline = true;
      video.controls = true;
      video.setAttribute("aria-label", t("watch"));
      video.src = source;
      video.addEventListener("error", () => { preview.textContent = t("missing"); });
      preview.append(video);
      if (!reducedMotion.matches) observer.observe(video);
    } else {
      preview.textContent = t("missing");
    }
    const content = document.createElement("div");
    content.className = "prompt-library-content";
    const category = document.createElement("small");
    category.textContent = translate(categories[item.category]);
    const title = document.createElement("h2");
    title.textContent = item.title;
    const prompt = document.createElement("p");
    prompt.textContent = item.prompt;
    const actions = document.createElement("div");
    actions.className = "prompt-library-actions";
    actions.append(action("copy", async () => {
      try {
        await navigator.clipboard.writeText(item.prompt);
        element("pl-status").textContent = t("copied");
      } catch {
        element("pl-status").textContent = t("copyError");
      }
    }));
    actions.append(action(local ? "edit" : "save", () => openEditor(local ? item : { ...item, id: undefined })));
    if (local) {
      let confirming = false;
      const remove = action("remove", () => {
        if (confirming) {
          persist(saved.filter((entry) => entry.id !== item.id));
        } else {
          confirming = true;
          remove.textContent = t("confirm");
        }
      });
      remove.addEventListener("blur", () => {
        confirming = false;
        remove.textContent = t("remove");
      });
      actions.append(remove);
    }
    content.append(category, title, prompt, actions);
    card.append(preview, content);
    return card;
  }

  function render() {
    observer.disconnect();
    folders.classList.toggle("hidden", Boolean(category));
    folder.hidden = !category;
    if (!category) {
      cards.replaceChildren();
      return;
    }
    folderTitle.textContent = translate(categories[category]);
    const collection = element("pl-collection").value;
    const search = element("pl-search").value.trim().toLocaleLowerCase();
    const matches = (item) => item && Object.hasOwn(categories, item.category)
      && item.category === category
      && `${item.title} ${item.prompt}`.toLocaleLowerCase().includes(search);
    const visible = [
      ...(collection === "catalog" ? [] : saved.filter(matches).map((item) => makeCard(item, true))),
      ...(collection === "mine" ? [] : catalog.filter(matches).map((item) => makeCard(item, false))),
    ];
    cards.replaceChildren(...visible);
    element("pl-status").textContent = !storageAvailable ? t("storageError")
      : catalogError && collection !== "mine" ? t("catalogError") : visible.length ? "" : t("empty");
  }

  function localize() {
    for (const node of document.querySelectorAll("[data-pl]")) node.textContent = t(node.dataset.pl);
    const select = element("pl-edit-category");
    const selected = select.value;
    const entries = Object.entries(categories);
    select.replaceChildren(...entries.map(([key, pair]) => new Option(translate(pair), key)));
    if (selected) select.value = selected;
    folders.replaceChildren(...entries.map(([key, pair]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn-secondary prompt-library-folder";
      button.dataset.category = key;
      button.textContent = translate(pair);
      button.addEventListener("click", () => {
        category = key;
        element("pl-search").value = "";
        render();
        folderTitle.focus();
      });
      return button;
    }));
    render();
  }

  element("pl-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const title = element("pl-name").value.trim();
    const prompt = element("pl-text").value.trim();
    if (!title || !prompt) {
      element("pl-form-status").textContent = t("required");
      return;
    }
    const item = { id: draft.id || crypto.randomUUID(), title, prompt, category: element("pl-edit-category").value,
      video: draft.prompt === prompt ? previewUrl(draft.video, true) : "" };
    if (persist([item, ...saved.filter((entry) => entry.id !== item.id)])) dialog.close();
  });
  element("pl-new").addEventListener("click", () => openEditor());
  element("pl-cancel").addEventListener("click", () => dialog.close());
  element("pl-back").addEventListener("click", () => {
    const previous = category;
    category = "";
    render();
    folders.querySelector(`[data-category="${previous}"]`)?.focus();
  });
  for (const id of ["pl-collection", "pl-search"]) element(id).addEventListener("input", render);
  document.addEventListener("h3-lang", localize);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) cards.querySelectorAll("video").forEach((video) => video.pause());
    else if (view.open) render();
  });
  for (const modal of [view, dialog]) {
    modal.addEventListener("keydown", (event) => {
      if (event.key === "Escape") event.stopPropagation();
    });
  }
  element("pl-close").addEventListener("click", () => view.close());
  view.addEventListener("close", () => {
    observer.disconnect();
    cards.querySelectorAll("video").forEach((video) => video.pause());
  });
  element("ws-prompts").addEventListener("click", () => {
    view.showModal();
    render();
    catalogRequest ||= fetch("/static/prompt-library.json", { cache: "no-cache" }).then((response) => {
      if (!response.ok) throw new Error(response.status);
      return response.json();
    }).then((items) => {
      catalog = items;
      catalogError = false;
      render();
    }).catch(() => {
      catalogError = true;
      render();
    }).finally(() => {
      catalogRequest = null;
    });
  });
  window.h3PromptLibrary = { openEditor };
  localize();
})();
