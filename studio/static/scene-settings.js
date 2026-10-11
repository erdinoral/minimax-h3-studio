/* Mirror global engine and appearance controls using their existing handlers. */
(() => {
  for (const [sourceId, targetId] of [['h3-engine-control','scene-engine-settings'], ['studio-theme-settings','scene-appearance-settings']]) {
    const source = document.getElementById(sourceId), target = document.getElementById(targetId);
    if (!source || !target) continue;
    const sync = () => { target.innerHTML = source.innerHTML; target.querySelectorAll('[id]').forEach(el => el.removeAttribute('id')); };
    new MutationObserver(sync).observe(source, {subtree:true, childList:true, attributes:true, characterData:true});
    target.addEventListener('click', event => {
      const button = event.target.closest('button'); if (!button || button.disabled) return;
      for (const key of ['engine','themeChoice','styleChoice']) {
        if (button.dataset[key]) {
          const original = [...source.querySelectorAll('button')].find(el => el.dataset[key] === button.dataset[key]);
          original?.click(); break;
        }
      }
    });
    target.addEventListener('change', event => {
      const input = event.target.closest('input[data-acceleration]');
      if (!input || input.disabled) return;
      const original = source.querySelector('input[data-acceleration="' + input.dataset.acceleration + '"]');
      if (!original || original.disabled) return;
      original.checked = input.checked;
      original.dispatchEvent(new Event('change', {bubbles:true}));
    });
    sync();
  }
})();
