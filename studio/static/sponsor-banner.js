(() => {
  const banner = document.getElementById("sponsor-banner");
  if (!banner) return;
  const text = banner.querySelector("span");
  let names = ["Diamond204a"];
  let turn = 0;
  let hideTimer;
  const english = () => document.documentElement.lang === "en";
  function show() {
    if (document.hidden) return;
    banner.style.setProperty("--sponsor-travel", `${banner.clientWidth}px`);
    const sponsorTurn = turn % 2 === 0;
    const name = names[Math.floor(turn / 2) % names.length];
    text.textContent = sponsorTurn
      ? name === "Diamond204a"
        ? english() ? "THANK YOU · Diamond204a · Our first sponsor · $25 support + valuable feedback" : "TEŞEKKÜRLER · Diamond204a · İlk sponsorumuz · $25 destek ve değerli geri bildirimler"
        : `${english() ? "THANK YOU" : "TEŞEKKÜRLER"} · ${name}`
      : english() ? "Support H3 Studio · Become a sponsor on Buy me a coffee ☕" : "H3 Studio’ya destek ol · Buy me a coffee üzerinden sponsor olun ☕";
    banner.classList.remove("is-showing");
    void banner.offsetWidth;
    banner.classList.add("is-showing");
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => banner.classList.remove("is-showing"), 7000);
    turn++;
  }
  document.addEventListener("h3-donors", (event) => {
    names = [...new Set(["Diamond204a", ...(event.detail?.names || [])])];
  });
  document.addEventListener("h3-lang", () => {
    if (banner.classList.contains("is-showing")) { turn = Math.max(0, turn - 1); show(); }
  });
  setTimeout(show, 1000);
  setInterval(show, 10000);
})();
