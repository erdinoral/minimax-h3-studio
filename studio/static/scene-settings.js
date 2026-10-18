/* Mirror global engine and appearance controls using their existing handlers. */
(() => {
  for (const [sourceId, targetId] of [['h3-engine-control','scene-engine-settings'], ['studio-theme-settings','scene-appearance-settings']]) {
    const source = document.getElementById(sourceId), target = document.getElementById(targetId);
    if (!source || !target) continue;
    const sync = () => { target.innerHTML = source.innerHTML; target.querySelectorAll('[id]').forEach(el => el.removeAttribute('id')); };
    new MutationObserver(sync).observe(source, {subtree:true, childList:true, attributes:true, characterData:true});
    target.addEventListener('click', event => {
      const button = event.target.closest('button'); if (!button || button.disabled) return;
      for (const key of ['engine','themeChoice','styleChoice','spectrumPreset']) {
        if (button.dataset[key]) {
          const original = [...source.querySelectorAll('button')].find(el => el.dataset[key] === button.dataset[key]);
          original?.click(); break;
        }
      }
    });
    const forwardInput = event => {
      const input = event.target.closest('input[data-acceleration], input[data-spectrum-range], input[data-spectrum-weight]');
      if (!input || input.disabled) return;
      const selector = input.hasAttribute('data-spectrum-range') ? 'input[data-spectrum-range]'
        : input.hasAttribute('data-spectrum-weight') ? 'input[data-spectrum-weight]'
        : 'input[data-acceleration="' + input.dataset.acceleration + '"]';
      const original = source.querySelector(selector);
      if (!original || original.disabled) return;
      if (input.hasAttribute('data-acceleration')) original.checked = input.checked;
      else original.value = input.value;
      original.dispatchEvent(new Event(event.type, {bubbles:true}));
      // Value properties do not trigger MutationObserver. Keep the paired
      // mirror input in sync without replacing the slider during a drag.
      if (event.type === 'input') {
        for (const attr of ['data-spectrum-range', 'data-spectrum-weight']) {
          const paired = target.querySelector('input[' + attr + ']');
          const confirmed = source.querySelector('input[' + attr + ']');
          if (paired && confirmed && paired !== input) paired.value = confirmed.value;
        }
      }
    };
    target.addEventListener('input', forwardInput);
    target.addEventListener('change', forwardInput);
    sync();
  }
})();
