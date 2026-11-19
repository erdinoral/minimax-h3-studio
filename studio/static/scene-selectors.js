/* Shared compact selector cards retain each workspace's existing input handlers. */
(() => {
  const groups = [
    { host: 'scene-project', fields: [
      ['scene-purpose-chips', '🎬'], ['scene-style-chips', '🎨'],
      ['dur-chips', '◷'], ['aspect-chips', '▣'], ['quality-chips', '▦'],
    ] },
    { host: 'director-chips', fields: [
      ['director-purpose-choices', '🎬', 'director-purpose-title'],
      ['director-style-choices', '🎨', 'director-style-title'],
      ['director-clip-choices', '◷', 'director-clip-title'],
    ] },
    { host: 'music-video-controls', fields: [
      ['music-video-styles', '🎨'], ['music-video-duration', '◷'],
      ['music-video-aspects', '▣'], ['music-video-quality', '▦'],
    ] },
  ];
  const selectors = [];
  function close(item) {
    item.classList.remove('open');
    item.querySelector('button').setAttribute('aria-expanded', 'false');
  }

  for (const group of groups) {
    const host = document.getElementById(group.host);
    if (!host) continue;
    for (const [id, glyph, labelId] of group.fields) {
      const input = document.getElementById(id);
      if (!input) continue;
      const label = labelId ? document.getElementById(labelId) : input.previousElementSibling;
      const isSelect = input.tagName === 'SELECT';
      const list = isSelect ? document.createElement('div') : input;
      if (isSelect) {
        list.id = id + '-options';
        list.className = 'chips';
        input.hidden = true;
        input.after(list);
        for (const option of input.options) {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'chip';
          button.dataset.value = option.value;
          button.textContent = option.textContent + (id.endsWith('duration') ? ' s' : '');
          button.addEventListener('click', () => {
            input.value = option.value;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
          });
          list.append(button);
        }
      }
      const field = document.createElement('div');
      field.className = 'scene-select-field';
      const details = document.createElement('div');
      details.className = 'res-drop scene-selector-drop';
      const summary = document.createElement('button');
      summary.type = 'button';
      summary.className = 'res-drop-toggle';
      summary.setAttribute('aria-expanded', 'false');
      summary.setAttribute('aria-controls', list.id);
      const value = document.createElement('span');
      value.className = 'scene-select-value';
      const chevron = document.createElement('span');
      chevron.className = 'res-drop-chevron';
      chevron.setAttribute('aria-hidden', 'true');
      const icon = document.createElement('span');
      icon.className = 'scene-card-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = glyph;
      const copy = document.createElement('span');
      copy.className = 'scene-card-copy';
      label.classList.add('scene-card-title');
      // The card button labels the disclosure. A nested form label would also
      // focus the hidden native select when the disclosure is pressed.
      label.removeAttribute('for');
      copy.append(label, value);
      summary.append(icon, copy, chevron);
      details.append(summary);
      list.classList.add('res-drop-panel');
      details.append(list);
      field.append(details);
      host.append(field);
      if (isSelect) field.append(input);

      function sync() {
        const selected = isSelect ? input.selectedOptions[0]
          : list.querySelector('.chip.on, .chip[aria-pressed="true"]');
        value.textContent = (selected?.textContent || (window.h3Lang?.() === 'tr' ? 'Seç' : 'Select'))
          + (isSelect && id.endsWith('duration') ? ' s' : '');
        if (id === 'quality-chips') label.textContent = window.h3Lang?.() === 'tr' ? 'Kalite' : 'Quality';
        summary.setAttribute('aria-label', label.textContent + ': ' + value.textContent);
        summary.disabled = isSelect ? input.disabled : [...list.querySelectorAll('.chip')].every(button => button.disabled);
        details.classList.toggle('has-selection', !!selected);
        if (isSelect) {
          for (const button of list.children) {
            const on = button.dataset.value === input.value;
            button.classList.toggle('on', on);
            button.setAttribute('aria-pressed', String(on));
            button.disabled = input.disabled;
          }
        }
      }
      new MutationObserver(sync).observe(isSelect ? input : list, {
        subtree: true, attributes: true,
        attributeFilter: ['class', 'aria-pressed', 'disabled'], childList: true, characterData: true,
      });
      input.addEventListener('change', sync);
      document.addEventListener('h3-lang', sync);
      document.addEventListener('h3-music-settings', sync);
      list.addEventListener('click', event => {
        if (event.target.closest('.chip')) { close(details); summary.focus(); }
      });
      summary.addEventListener('click', () => {
        const open = !details.classList.contains('open');
        selectors.forEach(close);
        details.classList.toggle('open', open);
        summary.setAttribute('aria-expanded', String(open));
      });
      details.addEventListener('keydown', event => {
        if (event.key === 'Escape') { close(details); summary.focus(); }
      });
      selectors.push(details);
      sync();
    }
  }
  document.addEventListener('click', event => {
    for (const item of selectors) if (!item.contains(event.target)) close(item);
  });
})();
