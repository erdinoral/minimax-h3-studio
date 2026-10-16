(() => {
  const banner = document.getElementById("sponsor-banner");
  if (!banner) return;
  const text = banner.querySelector("span");
  let names = ["Diamond204a", "Corey"];
  let turn = 0;
  let hideTimer;
  const english = () => document.documentElement.lang === "en";
  function show() {
    if (document.hidden) return;
    banner.style.setProperty("--sponsor-travel", `${banner.clientWidth}px`);
    const position = turn % (names.length + 1);
    const sponsorTurn = position < names.length;
    const name = names[position];
    text.textContent = sponsorTurn
      ? name === "Diamond204a"
        ? english() ? "THANK YOU · Diamond204a · Our first sponsor · $25 support" : "TEŞEKKÜRLER · Diamond204a · İlk sponsorumuz · $25 destek"
        : name === "Corey"
          ? english() ? "THANK YOU · Corey · $5 support" : "TEŞEKKÜRLER · Corey · $5 destek"
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
    names = [...new Set(["Diamond204a", "Corey", ...(event.detail?.names || [])])];
  });
  document.addEventListener("h3-lang", () => {
    if (banner.classList.contains("is-showing")) { turn = Math.max(0, turn - 1); show(); }
  });
  setTimeout(show, 1000);
  setInterval(show, 10000);
})();
