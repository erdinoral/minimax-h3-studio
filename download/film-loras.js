module.exports = {
  requires: { bundle: "ai" },
  run: [{
    method: "shell.run",
    params: { venv: "env", path: "../app", message: "python ../studio/tools/install_film_loras.py" }
  }]
};
