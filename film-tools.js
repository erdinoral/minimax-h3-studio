// Optional tools; no weight download and no change to the default generation path.
module.exports = {
  requires: { bundle: "ai" },
  run: [{
    when: "{{!exists('app/custom_nodes/ComfyUI-Minimax-H3-Reference-Library')}}",
    method: "shell.run",
    params: { path: "app/custom_nodes", message: "git clone https://github.com/nikaskeba/ComfyUI-Minimax-H3-Reference-Library.git" }
  }, {
    when: "{{!exists('app/custom_nodes/ComfyUI-HyperFlow-H3')}}",
    method: "shell.run",
    params: { path: "app/custom_nodes", message: "git clone https://github.com/Adudeguyman/ComfyUI-HyperFlow-H3.git" }
  }, {
    when: "{{!exists('app/custom_nodes/ComfyUI-H3LookSheets')}}",
    method: "shell.run",
    params: { path: "app/custom_nodes", message: "git clone https://github.com/shisa84/ComfyUI-H3LookSheets.git" }
  }, {
    when: "{{!exists('app/custom_nodes/Herrgotts-H3-Infinite-Continuation-Suite')}}",
    method: "shell.run",
    params: { path: "app/custom_nodes", message: "git clone https://github.com/HerrgottMargott/Herrgotts-H3-Infinite-Continuation-Suite.git" }
  }, {
    method: "shell.run",
    params: { venv: "env", path: "app", message: "python ../studio/tools/install_film_workflows.py" }
  }]
};
