(() => {
  const dialog = document.getElementById("view-roadmap");
  if (!dialog) return;

  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const trail = [[0, 92], [34, 90], [58, 99], [89, 96], [121, 83], [149, 90],
    [178, 99], [208, 92], [237, 80], [266, 88], [297, 95], [320, 89]];
  const palettes = [["#a29e99", "#f0aa5c"], ["#8395a6", "#7ac6cd"], ["#94899e", "#c8abe3"]];
  const paths = Array.from(dialog.querySelectorAll(".roadmap-group"), (group, index) => {
    const items = [...group.querySelectorAll("li")];
    const [stone, banner] = palettes[index];
    const forts = items.map((item, position) => {
      const x = (position + .5) * 320 / items.length;
      return { item, x, y: trailHeight(x) - 15, stone, banner,
        completed: item.dataset.completed === "true" };
    });
    const current = forts.find((fort) => !fort.completed);
    group.querySelector(".roadmap-carnival").hidden = Boolean(current);
    return { context: group.querySelector("canvas").getContext("2d"), forts, current };
  });
  const activePath = paths.find((path) => path.current);
  activePath?.current.item.setAttribute("aria-current", "step");
  let ctx;
  const traveler = [
    "..hhh...",
    ".hhhhh..",
    "..sss...",
    ".cscss..",
    "ccccc...",
    ".ccccb..",
    "..bbb...",
  ];
  const travelerColors = { h: "#f1b96c", s: "#f6d4a0", c: "#e36c52", b: "#293844" };
  let frame = 0;
  let start;

  function rect(color, x, y, width, height) {
    ctx.fillStyle = color;
    ctx.fillRect(Math.round(x), Math.round(y), width, height);
  }

  function polygon(color, points) {
    ctx.fillStyle = color;
    ctx.beginPath();
    points.forEach(([x, y], index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
    ctx.closePath();
    ctx.fill();
  }

  function trailHeight(x) {
    const index = trail.findIndex(([point]) => point >= x);
    if (index < 1) return trail[0][1];
    const [left, top] = trail[index - 1];
    const [right, bottom] = trail[index];
    return top + (bottom - top) * ((x - left) / (right - left));
  }

  function drawLandscape() {
    rect("#183749", 0, 0, 320, 112);
    rect("#edb878", 257, 12, 13, 13);
    rect("#edb878", 254, 15, 19, 7);
    polygon("#2b5260", [[0, 55], [26, 35], [46, 48], [74, 23], [112, 53], [147, 32],
      [181, 51], [213, 27], [252, 50], [282, 36], [320, 53], [320, 112], [0, 112]]);
    polygon("#28493e", [[0, 66], [28, 59], [72, 73], [112, 57], [149, 67],
      [187, 58], [224, 70], [269, 55], [320, 68], [320, 112], [0, 112]]);
    for (let index = 0; index < 52; index++) {
      const x = (index * 73 + 7) % 320;
      const y = 72 + ((index * 31) % 39);
      rect(index % 2 ? "#385c48" : "#204036", x, y, 2 + index % 4, 1);
    }
    for (let x = 0; x < 320; x += 2) {
      const y = trailHeight(x);
      rect("#725743", x, y - 4, 2, 12);
      rect("#b18a5d", x, y - 3, 2, 8);
      if (x % 14 === 0) rect("#c7a273", x, y + (x % 3), 2, 1);
    }
  }

  function drawFort({ x, y, stone, banner, completed }, time) {
    rect("#253b33", x - 23, y, 46, 4);
    if (completed) {
      rect(stone, x - 19, y - 11, 9, 12);
      rect("#a6afa2", x - 18, y - 14, 5, 3);
      rect(stone, x + 9, y - 7, 9, 8);
      rect("#5f7068", x - 10, y - 4, 19, 5);
      for (let index = 0; index < 5; index++) {
        const age = (time / 1800 + index / 5) % 1;
        const size = 3 + Math.floor(age * 5);
        ctx.globalAlpha = (1 - age) * .65;
        rect("#b4c3bb", x - 3 + age * 12 + Math.sin(age * 6) * 3, y - 7 - age * 28, size, size);
      }
      ctx.globalAlpha = 1;
      return;
    }
    rect("#3c4b52", x - 22, y - 18, 44, 19);
    rect(stone, x - 19, y - 20, 38, 17);
    for (const offset of [-19, 11]) {
      rect(stone, x + offset, y - 28, 8, 28);
      rect("#c3c2a9", x + offset, y - 29, 8, 2);
      rect(stone, x + offset, y - 32, 3, 4);
      rect(stone, x + offset + 5, y - 32, 3, 4);
      rect("#32444c", x + offset + 3, y - 23, 2, 4);
    }
    for (const offset of [-9, -3, 3, 9]) rect(stone, x + offset, y - 23, 3, 4);
    rect("#304149", x - 4, y - 9, 8, 10);
    rect("#304149", x - 2, y - 11, 4, 2);
    rect("#d7c7a2", x + 10, y - 42, 1, 13);
    rect(banner, x + 11, y - 41, 8 + Math.floor(time / 160) % 3, 5);
  }

  function drawTraveler(time, fort) {
    const destination = fort.x - 12;
    const arrival = (destination - 4) / .014;
    const x = Math.min(destination, 4 + time * .014);
    const step = time < arrival ? Math.floor(time / 130) % 4 : 0;
    const y = trailHeight(x) - 9 - step % 2;
    rect("#6e573d", x - 1, y + 10, 9, 2);
    traveler.forEach((row, dy) => [...row].forEach((pixel, dx) => {
      if (travelerColors[pixel]) rect(travelerColors[pixel], x + dx, y + dy, 1, 1);
    }));
    const stride = [0, 1, 0, -1][step];
    rect("#293844", x + 2 - stride, y + 7, 2, 2);
    rect("#293844", x + 5 + stride, y + 7, 2, 2);
  }

  function drawCarnival(time) {
    const colors = ["#f4bd67", "#df7487", "#8accca", "#c9aceb"];
    for (const [index, x] of [57, 130, 203, 267].entries()) {
      const y = trailHeight(x) - 14;
      polygon(colors[index], [[x - 21, y - 14], [x, y - 34], [x + 21, y - 14]]);
      rect("#dfc9a6", x - 18, y - 14, 36, 14);
      rect("#5c4656", x - 4, y - 9, 8, 9);
      rect(colors[index], x, y - 39, 8, 4);
    }
    for (let index = 0; index < 28; index++) {
      const x = (index * 47) % 320;
      const y = 8 + ((index * 13 + time / 26) % 50);
      rect(colors[index % colors.length], x, y, 2, 2);
    }
  }

  function render(time) {
    for (const path of paths) {
      ctx = path.context;
      if (!ctx) continue;
      drawLandscape();
      if (!path.current) {
        drawCarnival(time);
      } else {
        path.forts.forEach((fort) => drawFort(fort, time));
        if (path === activePath) drawTraveler(time, path.current);
      }
    }
  }

  function tick(now) {
    frame = 0;
    if (!dialog.open || document.hidden) return;
    start ??= now;
    render(now - start);
    frame = requestAnimationFrame(tick);
  }

  function stop() {
    cancelAnimationFrame(frame);
    frame = 0;
  }

  window.startRoadmapMap = () => {
    stop();
    start = undefined;
    render(reducedMotion.matches ? 12200 : 0);
    if (dialog.open && !document.hidden && !reducedMotion.matches) {
      frame = requestAnimationFrame(tick);
    }
  };
  dialog.addEventListener("close", stop);
  reducedMotion.addEventListener("change", window.startRoadmapMap);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
    else if (dialog.open) window.startRoadmapMap();
  });
})();
