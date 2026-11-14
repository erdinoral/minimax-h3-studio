(() => {
  const banner = document.getElementById("sponsor-banner");
  if (!banner) return;
  const text = banner.querySelector("span");
  const defaults = ["Diamond204a", "Corey", "Jürgen"];
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let names = defaults;
  let supportTurn = false;

  function show() {
    if (document.hidden || !banner.clientWidth) {
      setTimeout(show, 1000);
      return;
    }
    const turkish = window.h3Lang?.() === "tr";
    banner.classList.remove("is-showing");
    if (supportTurn) {
      text.textContent = turkish ? "Buy Me a Coffee üzerinden destek olun" : "Support us on Buy Me a Coffee";
    } else {
      text.replaceChildren(...names.map(name => {
        const credit = document.createElement("span");
        credit.textContent = turkish ? name + " · Teşekkürler" : name + " · Thank you";
        return credit;
      }));
    }
    const duration = reducedMotion.matches ? 7000 :
      Math.max(6000, Math.round((banner.clientWidth + text.scrollWidth) / 104 * 1000));
    banner.style.setProperty("--sponsor-travel", banner.clientWidth + "px");
    banner.style.setProperty("--sponsor-duration", duration + "ms");
    banner.classList.add("is-showing");
    supportTurn = !supportTurn;
    setTimeout(show, duration + 250);
  }

  document.addEventListener("h3-donors", event => {
    names = [...new Set([...defaults, ...(event.detail?.names || [])])];
  });
  setTimeout(show, 1000);
})();
