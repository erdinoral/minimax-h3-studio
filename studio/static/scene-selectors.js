/* Compact Scene selectors retain the original chip selection handlers. */
(() => {
  const host = document.getElementById('scene-project');
  if (!host) return;
  const selectors = [];
  const close = item => { item.classList.remove('open'); item.querySelector('button').setAttribute('aria-expanded', 'false'); }; 
  for (const id of ['scene-purpose-chips', 'scene-style-chips', 'dur-chips', 'aspect-chips', 'quality-chips']) {
    const list = document.getElementById(id);
    const label = list.previousElementSibling;
    const field = document.createElement('div'); field.className = 'scene-select-field';
    const details = document.createElement('div'); details.className = 'res-drop scene-selector-drop';
    const summary = document.createElement('button'); summary.type = 'button'; summary.className = 'res-drop-toggle'; summary.setAttribute('aria-expanded', 'false'); summary.setAttribute('aria-controls', id);
    const value = document.createElement('span'); value.className = 'scene-select-value';
    const chevron = document.createElement('span'); chevron.className = 'res-drop-chevron'; chevron.setAttribute('aria-hidden', 'true'); summary.append(value, chevron); details.append(summary); list.classList.add('res-drop-panel');
    host.append(field); field.append(details); details.append(list);
    const icon = document.createElement('span'); icon.className = 'scene-card-icon'; icon.setAttribute('aria-hidden', 'true'); icon.textContent = {'scene-purpose-chips':'🎬','scene-style-chips':'🎨','dur-chips':'◷','aspect-chips':'▣','quality-chips':'▦'}[id];
    const copy = document.createElement('span'); copy.className = 'scene-card-copy'; label.classList.add('scene-card-title'); copy.append(label, value); summary.replaceChildren(icon, copy, chevron);
    const sync = () => {
      const selected = list.querySelector('.chip.on, .chip[aria-pressed="true"]');
      value.textContent = selected?.textContent || (window.h3Lang?.() === 'en' ? 'Select' : 'Seç');
      if (id === 'quality-chips') label.textContent = window.h3Lang?.() === 'en' ? 'Quality' : 'Kalite';
      summary.setAttribute('aria-label', label.textContent + ': ' + value.textContent);
      details.classList.toggle('has-selection', !!selected);
    };
    new MutationObserver(sync).observe(list, {subtree:true, attributes:true, attributeFilter:['class','aria-pressed'], childList:true, characterData:true});
    document.addEventListener('h3-lang', sync);
    list.addEventListener('click', event => { if (event.target.closest('.chip')) { close(details); summary.focus(); } });
    summary.addEventListener('click', () => { const open = !details.classList.contains('open'); selectors.forEach(close); details.classList.toggle('open', open); summary.setAttribute('aria-expanded', String(open)); });
    details.addEventListener('keydown', event => { if (event.key === 'Escape') {close(details); summary.focus();} });
    selectors.push(details); sync();
  }
  document.addEventListener('click', event => { if (!host.contains(event.target)) selectors.forEach(close); });
})();